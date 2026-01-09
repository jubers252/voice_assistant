
from dotenv import load_dotenv
import speech_recognition as sr
import os
from contextlib import contextmanager
import numpy as np
import time
import io
import wave
import openai
from openai import OpenAI
import time as timing_module
import gc
import azure.cognitiveservices.speech as speechsdk
try:
    from google.cloud.speech_v2 import SpeechClient
    from google.cloud.speech_v2.types import cloud_speech
    GOOGLE_CLOUD_V2_AVAILABLE = True
except ImportError:
    GOOGLE_CLOUD_V2_AVAILABLE = False
    print("[WARNING] Google Cloud Speech-to-Text v2 not available. Install with: pip install google-cloud-speech")

# Load environment variables
load_dotenv()

# Suppress ALSA/JACK errors
@contextmanager
def suppress_alsa_errors():
    """Context manager to suppress ALSA/JACK error output"""
    try:
        devnull = os.open(os.devnull, os.O_WRONLY)
        old_stderr = os.dup(2)
        os.dup2(devnull, 2)
        os.close(devnull)
        yield
    finally:
        os.dup2(old_stderr, 2)
        os.close(old_stderr)

class SpeechRecognizer:
    def __init__(self, audio_processor, device_index=None, pixel_led=None, use_azure=False, use_google_cloud_v2=False):
        """Initialize recognizer and pick a safe microphone device index.

        On Linux the device index used on Windows (e.g. 1) may be invalid and
        attempting to open it causes ALSA/PyAudio errors. We try to pick a
        working device automatically and fall back to the system default.
        
        Args:
            audio_processor: Audio processor instance
            device_index: Optional microphone device index
            pixel_led: Optional LED control instance
            use_azure: If True, use Azure Speech Recognition
            use_google_cloud_v2: If True, use Google Cloud Speech-to-Text v2
        """
        self.device_index = None
        self.recognizer = sr.Recognizer()
        self.audio_processor = audio_processor
        self.pixel_led = pixel_led
        self.use_azure = use_azure
        self.use_google_cloud_v2 = use_google_cloud_v2
        self.spotify_connector = None  # Will be set by voice assistant
        self.is_music_playing = False  # Flag to track if music is currently playing
        
        # Initialize Google Cloud Speech v2 client if requested
        self.google_cloud_client = None
        self.google_cloud_recognizer = None
        if self.use_google_cloud_v2:
            if not GOOGLE_CLOUD_V2_AVAILABLE:
                print("[ERROR] Google Cloud Speech-to-Text v2 requested but not available!")
                print("[ERROR] Install with: pip install google-cloud-speech")
                self.use_google_cloud_v2 = False
            else:
                self._setup_google_cloud_v2()
        
        # Set Whisper language from environment variable (default: English)
        self.whisper_language = os.getenv('WHISPER_LANGUAGE', 'en')
        
        # Initialize OpenAI client if using Whisper
        if self.use_azure:
            speech_key = os.getenv('tts_key')
            endpoint = os.getenv('tts_endpoint')
   
            azure_languages = os.getenv('AZURE_LANGUAGES', 'en-US,hi-IN').split(',')
       
            self.speech_config = speechsdk.SpeechConfig(subscription=speech_key, endpoint=endpoint)
            
            self.speech_config.set_property(
                speechsdk.PropertyId.SpeechServiceConnection_InitialSilenceTimeoutMs, "8000"
            )
            self.speech_config.set_property(
                speechsdk.PropertyId.SpeechServiceConnection_EndSilenceTimeoutMs, "2000"
            )
            self.speech_config.set_property(
                speechsdk.PropertyId.SpeechServiceResponse_PostProcessingOption, "TrueText"
            )
            # Configure auto language detection
            self.auto_detect_source_language_config = speechsdk.languageconfig.AutoDetectSourceLanguageConfig(
                languages=azure_languages
            )
            print(f"[RECOGNIZER] Azure Speech Recognition initialized with auto-detect for: {', '.join(azure_languages)}")
         
        
        self._setup_recognizer()
     
        self.device_index = 2
        
        # Warm up microphone to avoid 100ms+ latency on first use
        self._warmup_microphone()
    
    def _warmup_microphone(self):
        """Pre-open and close microphone to prime the device driver"""
        try:
            mic_kwargs = {}
            if self.device_index is not None:
                mic_kwargs['device_index'] = self.device_index
            with suppress_alsa_errors():
                microphone = sr.Microphone(**mic_kwargs)
                with microphone as source:
                    pass  # Just open and close to warm up
            print("[RECOGNIZER] Microphone warmed up")
        except Exception as e:
            print(f"[RECOGNIZER] Microphone warm-up failed (non-critical): {e}")

    
    def _setup_google_cloud_v2(self):
        """Initialize Google Cloud Speech-to-Text v2 client and recognizer"""
        try:
            # Set credentials from environment or file
            credentials_path = os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
            if credentials_path and os.path.exists(credentials_path):
                os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = credentials_path
                print(f"[RECOGNIZER] Using Google Cloud credentials from: {credentials_path}")
            
            self.google_cloud_client = SpeechClient()
            
            # Get project ID and recognizer ID from environment
            project_id = os.getenv('GOOGLE_CLOUD_PROJECT')
            if not project_id:
                print("[ERROR] GOOGLE_CLOUD_PROJECT environment variable not set!")
                self.use_google_cloud_v2 = False
                return
            
            recognizer_id = os.getenv('GOOGLE_CLOUD_RECOGNIZER_ID', 'voice-assistant-recognizer')
            recognizer_name = f"projects/{project_id}/locations/global/recognizers/{recognizer_id}"
            
            # Try to get existing recognizer or create new one
            try:
                request = cloud_speech.GetRecognizerRequest(name=recognizer_name)
                self.google_cloud_recognizer = self.google_cloud_client.get_recognizer(request=request)
                print(f"[RECOGNIZER] Using existing Google Cloud recognizer: {recognizer_name}")
            except Exception as e:
                print(f"[RECOGNIZER] Recognizer not found, creating new one: {recognizer_id}")
                self.google_cloud_recognizer = self._create_google_cloud_recognizer(project_id, recognizer_id)
            
            print("[RECOGNIZER] Google Cloud Speech-to-Text v2 initialized successfully")
            
        except Exception as e:
            print(f"[ERROR] Failed to initialize Google Cloud Speech v2: {e}")
            self.use_google_cloud_v2 = False
    
    def _create_google_cloud_recognizer(self, project_id, recognizer_id):
        """Create a new Google Cloud Speech recognizer with custom configuration"""
        language_codes = os.getenv('GOOGLE_CLOUD_LANGUAGES', 'en-US,hi-IN').split(',')
        model = os.getenv('GOOGLE_CLOUD_MODEL', 'long')
        
        request = cloud_speech.CreateRecognizerRequest(
            parent=f"projects/{project_id}/locations/global",
            recognizer_id=recognizer_id,
            recognizer=cloud_speech.Recognizer(
                default_recognition_config=cloud_speech.RecognitionConfig(
                    language_codes=language_codes,
                    model=model
                ),
            ),
        )
        
        operation = self.google_cloud_client.create_recognizer(request=request)
        recognizer = operation.result()
        print(f"[RECOGNIZER] Created Google Cloud recognizer: {recognizer.name}")
        return recognizer
    
    def set_spotify_connector(self, spotify_connector):
        """Set Spotify connector to check music playback status"""
        self.spotify_connector = spotify_connector
    
    def set_music_playing(self, is_playing: bool):
        """Set the music playing state flag"""
        self.is_music_playing = is_playing
        if is_playing:
            print("[RECOGNIZER] Music playback started - will use optimized settings")
        else:
            print("[RECOGNIZER] Music playback stopped - reverting to normal settings")
    
    def _setup_recognizer(self):
        # INMP441 is very sensitive - use low thresholds for quiet speech detection
        self.recognizer.energy_threshold = 20  # Lowered to detect quiet speech
        self.recognizer.dynamic_energy_threshold = True
        self.recognizer.dynamic_energy_adjustment_damping = 0.10 
        self.recognizer.dynamic_energy_ratio = 1.3 
        self.recognizer.pause_threshold = 1.0 
        self.recognizer.phrase_threshold = 0.2
        self.recognizer.non_speaking_duration = 0.7 
    def _print_attempt(self, retry_count, is_follow_up):
        if retry_count == 0:
            print("Please respond..." if is_follow_up else "Say your command...")
        else:
            print(f"I didn't catch that. Please try again... (attempt {retry_count + 1})")

    def _handle_listen_error(self, attempt, error_message):
        """Handle listen/recognition error with LED feedback and retry logic.
        
        Args:
            attempt: Current attempt number (0 for first, 1 for second)
            error_message: Message to speak to user (only spoken on final failure)
            
        Returns:
            True if should retry, False if should return None
        """
        if attempt == 0:
            if self.pixel_led:
                self.pixel_led.set_error()
            print(f"[ERROR] {error_message}")
            time.sleep(2.0)  # Give audio time to settle

            self.audio_processor.play_beep_sound()
            if self.pixel_led:
                self.pixel_led.set_listening()
            return True  
        else:
            if self.pixel_led:
                self.pixel_led.set_error()
            return False

    
    def _listen_with_azure(self, timeout=20, is_follow_up=False, max_retries=1):
        """Listen for command using Azure Speech Recognition - simple approach"""
        msg = "Listening for follow-up..." if is_follow_up else "Listening for command..."
        print(f"[ASSISTANT] {msg}")
        self._print_attempt(0, is_follow_up)
        
        # Temporarily increase microphone gain
        original_gain = self.audio_processor.get_digital_gain()
        quiet_speech_gain = float(os.getenv('AZURE_MIC_GAIN', '4.0'))
        self.audio_processor.set_digital_gain(quiet_speech_gain)
        print(f"[ASSISTANT] Increased mic gain to {quiet_speech_gain}x for Azure")
        
        try:
            for attempt in range(max_retries + 1):
                try:
                    if self.pixel_led:
                        self.pixel_led.set_listening()
                    
                    # Use Azure's default microphone capture (simple and working)
                    audio_config = speechsdk.audio.AudioConfig(use_default_microphone=True)
                    
                    # Create recognizer with auto language detection
                    recognizer = speechsdk.SpeechRecognizer(
                        speech_config=self.speech_config,
                        audio_config=audio_config,
                        auto_detect_source_language_config=self.auto_detect_source_language_config
                    )
                    
                    print("[ASSISTANT] Listening with Azure...")
                    result = recognizer.recognize_once_async().get()
                    
                    if result.reason == speechsdk.ResultReason.RecognizedSpeech:
                        detected_language = result.properties.get(
                            speechsdk.PropertyId.SpeechServiceConnection_AutoDetectSourceLanguageResult
                        )
                        command = result.text
                        print(f"[ASSISTANT] Azure recognized ({detected_language}): {command}")
                        cleaned_command = command.lower().strip()
                        
                        if len(cleaned_command) < 2:
                            print("[ASSISTANT] Command too short, trying again...")
                            if attempt < max_retries:
                                self._print_attempt(attempt + 1, is_follow_up)
                            continue
                        
                        if self.pixel_led:
                            self.pixel_led.off()
                        return cleaned_command
                        
                    elif result.reason == speechsdk.ResultReason.NoMatch:
                        print(f"[ASSISTANT] No speech detected: {result.no_match_details}")
                        if not self._handle_listen_error(attempt, "Sorry, no speech detected."):
                            break
                            
                    elif result.reason == speechsdk.ResultReason.Canceled:
                        cancellation = result.cancellation_details
                        print(f"[ASSISTANT] Recognition canceled: {cancellation.reason}")
                        if cancellation.reason == speechsdk.CancellationReason.Error:
                            print(f"[ASSISTANT] Error: {cancellation.error_details}")
                        if not self._handle_listen_error(attempt, "Sorry, couldn't hear you."):
                            break
                            
                except Exception as e:
                    print(f"[ASSISTANT] Azure error: {e}")
                    if not self._handle_listen_error(attempt, "Sorry, an error occurred."):
                        break
                        
        finally:
            # Restore original microphone gain
            self.audio_processor.set_digital_gain(original_gain)
            print(f"[ASSISTANT] Restored mic gain to {original_gain}x")
        
        if self.pixel_led:
            self.pixel_led.off()
        print("[ASSISTANT] No command detected after multiple attempts.")
        self.audio_processor.speak("I didn't hear anything. Please call if you need me.")
        return None
    
    def _listen_with_google_cloud_v2(self, timeout=20, is_follow_up=False, max_retries=1):
        """Listen for command using Google Cloud Speech-to-Text v2 API"""
        # Use shorter phrase limit when timeout is reduced (music playing)
        phrase_time_limit = 5 if timeout == 5 else 15
        
        msg = "Listening for follow-up..." if is_follow_up else "Listening for command..."
        print(f"[ASSISTANT] {msg}")
        self._print_attempt(0, is_follow_up)
        
        for attempt in range(max_retries + 1):
                microphone = None
                audio = None
                try:
                    if self.pixel_led:
                        self.pixel_led.set_listening()
                    
                    # Capture audio using speech_recognition library
                    mic_kwargs = {"device_index": self.device_index} if self.device_index is not None else {}
                    with suppress_alsa_errors():
                        microphone = sr.Microphone(**mic_kwargs)
                    
                    with suppress_alsa_errors():
                        with microphone as source:
                            print(f"Energy threshold: {self.recognizer.energy_threshold}")
                            print("Listening...")
                            try:
                                audio = self.recognizer.listen(source, timeout=timeout, phrase_time_limit=phrase_time_limit)
                            except sr.WaitTimeoutError:
                                print(f"[ASSISTANT] No speech detected. Attempt {attempt + 1}/{max_retries + 1}")
                                if self.pixel_led:
                                    self.pixel_led.off()
                                if attempt < max_retries:
                                    self._print_attempt(attempt + 1, is_follow_up)
                                continue
                    
                    if not audio or len(audio.frame_data) < 100:
                        print("[ASSISTANT] Audio too short, retrying...")
                        if attempt < max_retries:
                            self._print_attempt(attempt + 1, is_follow_up)
                        continue
                    
                    # Convert audio to format required by Google Cloud v2
                    print("Recognizing with Google Cloud Speech v2...")
                    command = self._recognize_with_google_cloud_v2(audio)
                    
                    if command:
                        if self.pixel_led:
                            self.pixel_led.off()
                        return command
                    else:
                        if not self._handle_listen_error(attempt, "Sorry, no speech detected."):
                            pass
                        
                except Exception as e:
                    print(f"[ASSISTANT] Google Cloud v2 error: {e}")
                    if not self._handle_listen_error(attempt, "Sorry, couldn't hear you."):
                        pass
                
                finally:
                    if audio is not None:
                        try:
                            if hasattr(audio, 'frame_data'):
                                del audio.frame_data
                            del audio
                        except:
                            pass
                    if microphone is not None:
                        try:
                            microphone.close()
                            del microphone
                        except:
                            pass
                    gc.collect()
        
        if self.pixel_led:
            self.pixel_led.off()
        print("[ASSISTANT] No command detected after multiple attempts.")
        self.audio_processor.speak("I didn't hear anything. Please call if you need me.")
        return None

    def listen_for_command(self, timeout=20, is_follow_up=False, max_retries=1):
        """Listen for user command with retry logic (retries once, then returns error)."""
        # Use music playing flag to adjust timeout for all services
        if self.is_music_playing:
            timeout = 5
            print("[ASSISTANT] Music is playing - using 5s timeout")
        
        # Use appropriate recognition service
        if self.use_google_cloud_v2:
            return self._listen_with_google_cloud_v2(timeout, is_follow_up, max_retries)
        elif self.use_azure:
            return self._listen_with_azure(timeout, is_follow_up, max_retries)
        
        phrase_time_limit = 15
        if timeout == 5:  # Music is playing
            phrase_time_limit = 5
        
        msg = "Listening for follow-up..." if is_follow_up else "Listening for command..."
        print(f"[ASSISTANT] {msg}")
        self._print_attempt(0, is_follow_up)
        
        for attempt in range(max_retries + 1):
                microphone = None
                audio = None
                try:
                    mic_kwargs = {"device_index": self.device_index} if self.device_index is not None else {}
                    if self.pixel_led:
                        self.pixel_led.set_listening()
                    with suppress_alsa_errors():
                        microphone = sr.Microphone(**mic_kwargs)
                    
                    with suppress_alsa_errors():
                        with microphone as source:
                            print(f"Energy threshold: {self.recognizer.energy_threshold}")
                            
                            print("Listening...")
                            try:
                                audio = self.recognizer.listen(source, timeout=timeout, phrase_time_limit=phrase_time_limit)
                            except sr.WaitTimeoutError:
                                print(f"[ASSISTANT] No speech detected. Attempt {attempt + 1}/{max_retries + 1}")
                                if self.pixel_led:
                                    self.pixel_led.off()
                                if attempt < max_retries:
                                    self._print_attempt(attempt + 1, is_follow_up)
                                continue

                    if not audio or len(audio.frame_data) < 100:
                        print("[ASSISTANT] Audio too short, retrying...")
                        if attempt < max_retries:
                            self._print_attempt(attempt + 1, is_follow_up)
                        continue
     
                    print("Recognizing...")
                    command = self._recognize_audio(audio)
                    if command:
                        return command
                    else:
                        # Recognition failed, treat as error
                        if not self._handle_listen_error(attempt, "Sorry, no speech detected."):
                            pass
                   
                except Exception as e:
                    print(f"[ASSISTANT] Error: {e}")
                    if not self._handle_listen_error(attempt, "Sorry, couldn't hear you. Let me try again."):
                        pass
                
                finally:
                    if audio is not None:
                        try:
                            if hasattr(audio, 'frame_data'):
                                del audio.frame_data
                            del audio
                        except:
                            pass
                    if microphone is not None:
                        try:
                            microphone.close()
                            del microphone
                        except:
                            pass
                    gc.collect()
        
        print("[ASSISTANT] No command detected after multiple attempts.")
        self.audio_processor.speak("I didn't hear anything. Please call if you need me.")
        return None

    def _recognize_audio(self, audio):
        """Recognize audio using either OpenAI Whisper or Google Speech Recognition"""
        try:
                 
            return self._recognize_with_google(audio)
        except Exception as e:
            print(f"[ASSISTANT] Unexpected recognition error: {e}")
            return None
        finally:
            # Clean up audio data after recognition
            try:
                import gc
                gc.collect()
            except:
                pass

    def _recognize_with_google(self, audio):
        """Recognize audio using Google Speech Recognition"""
        try:
            command = self.recognizer.recognize_google(audio,language="en-US")
            print(f"[ASSISTANT] You said: {command}")
            cleaned_command = command.lower().strip()
            if len(cleaned_command) < 2:
                print("[ASSISTANT] Command too short, trying again...")
                # Don't speak here - let it retry silently
                return None
            return cleaned_command
        except (sr.RequestError, sr.UnknownValueError) as e:
            print(f"[ASSISTANT] Google Recognition error: {e}.")
            # Don't speak here - let the caller handle it to avoid self-listening
            return None
    
    def _recognize_with_google_cloud_v2(self, audio):
        """Recognize audio using Google Cloud Speech-to-Text v2 API"""
        try:
            if not self.google_cloud_recognizer:
                print("[ERROR] Google Cloud recognizer not initialized")
                return None
            
            # Convert AudioData to the format required by Google Cloud
            # audio.frame_data is raw audio bytes
            audio_content = audio.get_wav_data()
            
            # Create recognition request
            request = cloud_speech.RecognizeRequest(
                recognizer=self.google_cloud_recognizer.name,
                content=audio_content,
                config=cloud_speech.RecognitionConfig(
                    auto_decoding_config=cloud_speech.AutoDetectDecodingConfig(),
                ),
            )
            
            # Perform recognition
            response = self.google_cloud_client.recognize(request=request)
            
            # Process results
            if response.results:
                # Get the first result (highest confidence)
                result = response.results[0]
                if result.alternatives:
                    command = result.alternatives[0].transcript
                    confidence = result.alternatives[0].confidence if hasattr(result.alternatives[0], 'confidence') else 0.0
                    language_code = result.language_code if hasattr(result, 'language_code') else 'unknown'
                    
                    print(f"[ASSISTANT] Google Cloud v2 recognized ({language_code}, confidence: {confidence:.2f}): {command}")
                    
                    cleaned_command = command.lower().strip()
                    if len(cleaned_command) < 2:
                        print("[ASSISTANT] Command too short, trying again...")
                        return None
                    
                    return cleaned_command
            
            print("[ASSISTANT] No speech recognized")
            return None
            
        except Exception as e:
            print(f"[ASSISTANT] Google Cloud v2 recognition error: {e}")
            import traceback
            traceback.print_exc()
            return None



    def list_available_microphones(self):
        """Return a list of available microphone names."""
        try:
            names = sr.Microphone.list_microphone_names()
            return names
        except Exception:
            return []

    def _choose_device_index(self, force_search=False):
        """Choose a working device index with priority for known good devices.

        Priority order:
        1. Google VoiceHAT (device 1)
        2. USB microphone (device 2)
        3. Test all other devices
        
        Returns True if a device was selected.
        """
        names = self.list_available_microphones()
        if not names:
            # No microphones found
            self.device_index = None
            return False

        # If caller provided an index, verify it's in range
        if self.device_index is not None and isinstance(self.device_index, int):
            if 0 <= self.device_index < len(names):
                return True

        # Prefer default (None) if not forcing a search
        if not force_search:
            self.device_index = None
            return True

        # Force search: try preferred devices first
        preferred_devices = [1, 2]  # Google VoiceHAT, then USB mic
        print(f"[MIC] Available devices: {len(names)}")
        
        # Try preferred devices first
        for idx in preferred_devices:
            if idx < len(names):
                try:
                    print(f"[MIC] Testing device {idx}: {names[idx]}")
                    with suppress_alsa_errors():
                        mic = sr.Microphone(device_index=idx)
                        with mic as source:
                            # Try to actually listen to verify the device works
                            try:
                                self.recognizer.listen(source, timeout=1.0, phrase_time_limit=1.0)
                            except sr.WaitTimeoutError:
                                # Timeout is ok - device is working, just no audio
                                pass
                        self.device_index = idx
                        print(f"[MIC] Using device {idx}: {names[idx]}")
                        return True
                except Exception as e:
                    print(f"[MIC] Device {idx} failed: {type(e).__name__}: {e}")
                    continue

        # Try all other devices
        for idx in range(len(names)):
            if idx in preferred_devices:
                continue  # Already tested
            try:
                print(f"[MIC] Testing device {idx}: {names[idx]}")
                with suppress_alsa_errors():
                    mic = sr.Microphone(device_index=idx)
                    with mic as source:
                        try:
                            self.recognizer.listen(source, timeout=1.0, phrase_time_limit=1.0)
                        except sr.WaitTimeoutError:
                            pass
                    self.device_index = idx
                    print(f"[MIC] Using device {idx}: {names[idx]}")
                    return True
            except Exception as e:
                print(f"[MIC] Device {idx} failed: {type(e).__name__}")
                continue

        # Last resort - use None (system default)
        print("[MIC] No working device found, using system default")
        self.device_index = None
        return False
