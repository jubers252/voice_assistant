
from dotenv import load_dotenv
import speech_recognition as sr
import os
from contextlib import contextmanager
import numpy as np
import time
import time as timing_module
import gc
import threading
from google.cloud import speech_v2
from google.cloud.speech_v2.types import cloud_speech

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
    def __init__(self, recognizer, audio_processor, device_index=None, pixel_led=None):
        """Initialize recognizer with existing sr.Recognizer instance.

        Args:
            recognizer: Shared sr.Recognizer instance (created in voice_assistant.py)
            audio_processor: Audio processor instance
            device_index: Optional microphone device index
            pixel_led: Optional LED control instance
        """
        self.device_index = None
        self.recognizer = recognizer  # Use provided recognizer instead of creating new one
        self.audio_processor = audio_processor
        self.pixel_led = pixel_led
        self.is_music_playing = False
        self.spotify_connector = None
        self.project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
        
        try:
            self._choose_device_index()
        except Exception:
            self.device_index = None
        
        # Warm up microphone to avoid 100ms+ latency on first use
        self._warmup_microphone()  
    
    def _warmup_microphone(self):
        """Pre-open and close microphone to prime the device driver"""
        try:
            mic_kwargs = {}
            if self.device_index is not None:
                mic_kwargs['device_index'] = self.device_index
            mic_kwargs['sample_rate'] = 16000  # Force 16kHz sample rate
            with suppress_alsa_errors():
                microphone = sr.Microphone(**mic_kwargs)
                with microphone as source:
                    pass  # Just open and close to warm up
            print("[RECOGNIZER] Microphone warmed up at 16kHz")
        except Exception as e:
            print("[RECOGNIZER] Microphone warm-up failed (non-critical): {e}")

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

    def _print_attempt(self, retry_count, is_follow_up):
        if retry_count == 0:
            print("Please respond..." if is_follow_up else "Say your command...")
        else:
            print(f"I didn't catch that. Please try again... (attempt {retry_count + 1})")

    def _handle_listen_error(self, attempt, error_message, max_retries):
        """Handle listen/recognition error with LED feedback and retry logic.
        
        Args:
            attempt: Current attempt number (0 for first, 1 for second)
            error_message: Message to speak to user (only spoken on final failure)
            max_retries: Maximum number of retries allowed
            
        Returns:
            True if should retry, False if should stop (final failure)
        """
        # Check if we have more attempts left
        if attempt < max_retries:
            # Still have retries left - continue loop
            if self.pixel_led:
                self.pixel_led.set_error()
            print(f"[ERROR] {error_message} - Retrying...")
            time.sleep(1.0)  # Give audio time to settle
            if self.pixel_led:
                self.pixel_led.set_listening()
            return True  # Continue to next retry
        else:
            # No more retries - final failure
            if self.pixel_led:
                self.pixel_led.set_error()
            print(f"[ERROR] {error_message} - No more retries.")
            return False  # Stop trying

    def listen_for_command(self, timeout=20, is_follow_up=False, max_retries=1):
        """Listen for user command with retry logic (retries once, then returns error).
        
        Args:
            timeout: Maximum time to wait for speech (in seconds)
            is_follow_up: Whether this is a follow-up command
            max_retries: Number of times to retry if no speech detected
        """
       
        if self.is_music_playing:
            timeout = 5
            print("[ASSISTANT] Music is playing - using 5s timeout")
        phrase_time_limit = 5 if timeout == 5 else 20  # Increased from 15 to 20 seconds for more speaking time
        
        print(f"timeout={timeout}, phrase_time_limit={phrase_time_limit}")
        msg = "Listening for follow-up..." if is_follow_up else "Listening for command..."
        print(f"[ASSISTANT] {msg}")
        
        self._print_attempt(0, is_follow_up)

        try:
            for attempt in range(max_retries + 1):
                microphone = None
                audio = None
                try:
                    # Just listen
                    mic_kwargs = {"device_index": self.device_index} if self.device_index is not None else {}
                    mic_kwargs['sample_rate'] = 16000  # Force 16kHz sample rate
                    if self.pixel_led:
                        self.pixel_led.set_listening()
                    with suppress_alsa_errors():
                        microphone = sr.Microphone(**mic_kwargs)
                    
                    with suppress_alsa_errors():
                        with microphone as source:
                            print(f"Listening... [Energy Threshold: {int(self.recognizer.energy_threshold)}]")
                            try:
                                audio = self.recognizer.listen(source, timeout=timeout, phrase_time_limit=phrase_time_limit)
                            except sr.WaitTimeoutError:
                                print(f"[ASSISTANT] No speech detected. Attempt {attempt + 1}/{max_retries + 1}")
                                if attempt < max_retries:
                                    self._print_attempt(attempt + 1, is_follow_up)
                                continue

                    min_audio_bytes = 20000  # ~0.6 seconds for short words
                    if not audio or len(audio.frame_data) < min_audio_bytes:
                        print(f"[ASSISTANT] Audio too short: {len(audio.frame_data) if audio else 0} bytes, minimum required: {min_audio_bytes} bytes (~0.6s)")
                        if attempt < max_retries:
                            self._print_attempt(attempt + 1, is_follow_up)
                        continue

                    # Calculate and print audio energy for debugging
                    audio_data = np.frombuffer(audio.frame_data, dtype=np.int16)
                    audio_energy = np.sqrt(np.mean(np.square(audio_data.astype(float))))
                    print(f"[ASSISTANT] Audio captured: {len(audio.frame_data)} bytes | Energy: {audio_energy:.0f} (Threshold: {int(self.recognizer.energy_threshold)})")
        
                    command = self._recognize_audio(audio)
                    if command:
                        return command
                    else:
                        # Recognition failed, treat as error and retry if attempts left
                        should_retry = self._handle_listen_error(attempt, "Sorry, couldn't understand that.", max_retries)
                        if not should_retry:
                            break  # Stop loop if no more retries
                        # Otherwise continue to next iteration
                   
                except Exception as e:
                    print(f"[ASSISTANT] Error: {e}")
                    should_retry = self._handle_listen_error(attempt, f"Error during listening: {e}", max_retries)
                    if not should_retry:
                        break  # Stop loop if no more retries
                
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
            return None
        
        except Exception as e:
            print(f"[ASSISTANT] Unexpected error in listen_for_command: {e}")
            return None

    def _recognize_audio(self, audio):
        """Recognize audio using free Google first, fallback to paid Google Cloud"""
        try:
            # Try free Google Speech Recognition first
            result = self._recognize_with_google(audio)
            if result:
                return result
    
            print("[ASSISTANT] Free Google failed, trying paid Google Cloud...")
            return self.recognize_from_paid_google(audio)
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
            print(f"[ASSISTANT] Audio received - Sample rate: {audio.sample_rate}, Frames: {len(audio.frame_data)} bytes")
            command = self.recognizer.recognize_google(audio, language='en-US')
            print(f"[ASSISTANT] You said: {command}")
            return command
        except Exception as e:
            print(f"[ASSISTANT] Google Recognition unexpected error: {type(e).__name__}: {e}")
            return None

    def recognize_from_paid_google(self, audio):
        """Recognize audio using Google Cloud Speech-to-Text API (paid version)"""
        try:
            if not self.project_id:
                print("[ASSISTANT] Error: GOOGLE_CLOUD_PROJECT_ID not set, paid Google STT unavailable")
                return None
            
            # Pass raw PCM audio directly with proper explicit decoding config
            client = speech_v2.SpeechClient()
            config = cloud_speech.RecognitionConfig(
                explicit_decoding_config=cloud_speech.ExplicitDecodingConfig(
                    encoding=cloud_speech.ExplicitDecodingConfig.AudioEncoding.LINEAR16,
                    sample_rate_hertz=audio.sample_rate,
                    audio_channel_count=1,
                ),
                language_codes=["en-US", "hi-IN"],
                model="latest_long",
                features=cloud_speech.RecognitionFeatures(
                    enable_automatic_punctuation=True,
                ),
            )
            request = cloud_speech.RecognizeRequest(
                recognizer=f"projects/{self.project_id}/locations/global/recognizers/_",
                config=config,
                content=audio.frame_data,
            )

            print("[ASSISTANT] Sending to Google Cloud Speech-to-Text API...")
            response = client.recognize(request=request)
            
            # Validate results
            if not response.results or not response.results[0].alternatives:
                print("[ASSISTANT] No results from Google Cloud API")
                return None
            
            result = response.results[0]
            transcript = result.alternatives[0].transcript
            confidence = result.alternatives[0].confidence
            print(f"[ASSISTANT] Google Cloud - Transcript: {transcript} (Confidence: {confidence:.2%})")
            cleaned_command = transcript.lower().strip()
            if len(cleaned_command) < 2:
                print("[ASSISTANT] Command too short, trying again...")
                return None
            return cleaned_command
        
        except Exception as e:
            print(f"[ASSISTANT] Google Cloud recognition error: {type(e).__name__}: {e}")
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
        1. ReSpeaker device (for ReSpeaker Lite)
        2. Google VoiceHAT (device 1)
        3. USB microphone (device 2)
        4. Test all other devices
        
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

        # Force search: try preferred devices first, starting with ReSpeaker
        preferred_devices = []
        
        # First, look for ReSpeaker device
        for idx, name in enumerate(names):
            if any(key in name.lower() for key in ['respeaker', 'seeed', 'ac108', 'wm8', 'rv']):
                preferred_devices.append(idx)
                break
        
        # Then add standard devices
        preferred_devices.extend([1, 2])  # Google VoiceHAT, then USB mic
        print(f"[MIC] Available devices: {len(names)}")
        
        # Try preferred devices first
        for idx in preferred_devices:
            if idx < len(names):
                try:
                    print(f"[MIC] Testing device {idx}: {names[idx]}")
                    with suppress_alsa_errors():
                        mic = sr.Microphone(device_index=idx, sample_rate=16000)
                        with mic as source:
                            # Try to actually listen to verify the device works
                            try:
                                self.recognizer.listen(source, timeout=2.0, phrase_time_limit=2.0)
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
                    mic = sr.Microphone(device_index=idx, sample_rate=16000)
                    with mic as source:
                        try:
                            self.recognizer.listen(source, timeout=2.0, phrase_time_limit=2.0)
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
