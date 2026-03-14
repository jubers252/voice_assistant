
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
import threading

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
    def __init__(self, audio_processor, device_index=None, pixel_led=None, use_whisper=False):
        """Initialize recognizer and pick a safe microphone device index.

        On Linux the device index used on Windows (e.g. 1) may be invalid and
        attempting to open it causes ALSA/PyAudio errors. We try to pick a
        working device automatically and fall back to the system default.
        
        Args:
            audio_processor: Audio processor instance
            device_index: Optional microphone device index
            pixel_led: Optional LED control instance
            use_whisper: If True, use OpenAI Whisper for recognition instead of Google
        """
        self.device_index = None
        self.recognizer = sr.Recognizer()
        self.audio_processor = audio_processor
        self.pixel_led = pixel_led
        self.use_whisper = use_whisper
        self.is_music_playing = False
        self.spotify_connector = None
        # Set Whisper language from environment variable (default: English)
        self.whisper_language = os.getenv('WHISPER_LANGUAGE', 'en')
        
        # Initialize OpenAI client if using Whisper
        if self.use_whisper:
            api_key = os.getenv('OPENAI_API_KEY')
            if not api_key:
                print("[RECOGNIZER] Warning: OPENAI_API_KEY not found in environment. Falling back to Google Speech Recognition.")
                self.use_whisper = False
            else:
                self.openai_client = OpenAI(api_key=api_key)
                print("[RECOGNIZER] OpenAI Whisper initialized")
        
        self._setup_recognizer()
        try:
            self._choose_device_index()
        except Exception:
            # Non-fatal: leave device_index as-is (None will let speech_recognition
            # use the system default device)
            self.device_index = None
        
        # Warm up microphone to avoid 100ms+ latency on first use
        self._warmup_microphone()
        
        # Store reference to energy calibrator (will be set by voice_assistant.py)
        self.energy_calibrator = None  
    
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


   
    def _setup_recognizer(self):
        # Minimal energy threshold - will be set by initial calibration
        # This is just a temporary value until calibrate_initial() runs
        self.recognizer.energy_threshold = 100  # Minimal value (will be updated immediately)
        self.recognizer.dynamic_energy_threshold = False  # Keep fixed for consistency
        self.recognizer.dynamic_energy_adjustment_damping = 0.15
        self.recognizer.dynamic_energy_ratio = 1.5
        self.recognizer.pause_threshold = 1.5  # 1.5 seconds of silence before stopping
        self.recognizer.phrase_threshold = 0.3  # Minimum 300ms to catch speech start
        self.recognizer.non_speaking_duration = 1.3  # Allow up to 1.3 seconds pause mid-phrase
        
        print(f"[RECOGNIZER] Setup complete - Energy threshold will be auto-calibrated on startup")

    def _calibrate_ambient_energy(self, duration=1.0, multiplier=1.5):
        """Calibrate ambient energy by recording and measuring raw microphone audio"""
        try:
            mic_kwargs = {"device_index": self.device_index} if self.device_index is not None else {}
            mic_kwargs['sample_rate'] = 16000
            
            with suppress_alsa_errors():
                microphone = sr.Microphone(**mic_kwargs)
                with suppress_alsa_errors():
                    with microphone as source:
                        # Record raw audio directly (don't use listen() which waits for speech)
                        print(f"[RECOGNIZER] Sampling ambient audio for {duration}s...")
                        
                        # Get the stream to record raw audio
                        audio = source.stream.read(int(16000 * duration))  # Read duration seconds of raw audio
                        
                        # Convert bytes to audio data
                        audio_data = np.frombuffer(audio, dtype=np.int16)
                        
                        # Calculate RMS energy
                        rms_energy = np.sqrt(np.mean(np.square(audio_data.astype(float))))
                        new_threshold = int(rms_energy * multiplier)
                        new_threshold = max(new_threshold, 100)  # Minimum 100
                        old_threshold = int(self.recognizer.energy_threshold)
                        self.recognizer.energy_threshold = new_threshold
                        print(f"[RECOGNIZER] Calibrated: Energy {rms_energy:.0f} | Threshold: {old_threshold} → {new_threshold}")
                            
        except Exception as e:
            print(f"[RECOGNIZER] Calibration error: {e} - using default threshold")

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
            time.sleep(1.0)  # Give audio time to settle
            if self.pixel_led:
                self.pixel_led.set_listening()
            return True  
        else:

            if self.pixel_led:
                self.pixel_led.set_error()
            return False

    def listen_for_command(self, timeout=20, is_follow_up=False, max_retries=1, calibrate_ambient=True):
        """Listen for user command with retry logic (retries once, then returns error).
        
        Args:
            timeout: Maximum time to wait for speech (in seconds)
            is_follow_up: Whether this is a follow-up command
            max_retries: Number of times to retry if no speech detected
            calibrate_ambient: If True, calibrate ambient energy once before listening
        """
       
        if self.is_music_playing:
            timeout = 5
            print("[ASSISTANT] Music is playing - using 5s timeout")
        phrase_time_limit = 5 if timeout == 5 else 20  # Increased from 15 to 20 seconds for more speaking time

        # Calibrate ambient energy once before listening (longer duration to actually capture noise)
        # if calibrate_ambient:
        #     self._calibrate_ambient_energy(duration=1.0, multiplier=1.5)
        
        print(f"timeout={timeout}, phrase_time_limit={phrase_time_limit}")
        msg = "Listening for follow-up..." if is_follow_up else "Listening for command..."
        print(f"[ASSISTANT] {msg}")
        
       
        
        self._print_attempt(0, is_follow_up)

        for attempt in range(max_retries + 1):
            microphone = None
            audio = None
            try:
                # Just listen - energy threshold is continuously updated in background
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

                if not audio or len(audio.frame_data) < 400:
                    print(f"[ASSISTANT] Audio too short: {len(audio.frame_data) if audio else 0} bytes, minimum required: 400 bytes")
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
                # self.recognizer.energy_threshold =300
        
        # Resume energy calibration after listening is done
        if self.energy_calibrator:
            self.energy_calibrator.pause_calibration = False
        
        print("[ASSISTANT] No command detected after multiple attempts.")
        # self.audio_processor.speak("I didn't hear anything. Please call if you need me.")
        return None

    def _recognize_audio(self, audio):
        """Recognize audio using either OpenAI Whisper or Google Speech Recognition"""
        try:
            if self.use_whisper:
                return self._recognize_with_whisper(audio)
            else:
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
            print(f"[ASSISTANT] Audio received - Sample rate: {audio.sample_rate}, Frames: {len(audio.frame_data)} bytes")
            command = self.recognizer.recognize_google(audio, language='en-US')
            print(f"[ASSISTANT] You said: {command}")
            cleaned_command = command.lower().strip()
            if len(cleaned_command) < 2:
                print("[ASSISTANT] Command too short, trying again...")
                # Don't speak here - let it retry silently
                return None
            return cleaned_command
        except sr.RequestError as e:
            print(f"[ASSISTANT] Google API request error: {e}")
            return None
        except sr.UnknownValueError as e:
            print(f"[ASSISTANT] Google couldn't understand audio (speech too quiet or unclear)")
            return None
        except Exception as e:
            print(f"[ASSISTANT] Google Recognition unexpected error: {type(e).__name__}: {e}")
            return None

    def _recognize_with_whisper(self, audio):
        """Recognize audio using OpenAI Whisper API"""
        try:
            # Convert audio object to WAV file for Whisper API
            wav_data = self._audio_to_wav(audio)
            
            # Send to Whisper API
            print(f"[ASSISTANT] Sending audio to Whisper API (Language: {self.whisper_language})...")
            transcript = self.openai_client.audio.transcriptions.create(
                model="whisper-1",
                file=("audio.wav", wav_data, "audio/wav"),
               
            )
            
            command = transcript.text
            print(f"[ASSISTANT] Whisper recognized: {command}")
            cleaned_command = command.lower().strip()
            
            if len(cleaned_command) < 2:
                print("[ASSISTANT] Command too short, trying again...")
                return None
            
            return cleaned_command
            
        except openai.APIError as e:
            print(f"[ASSISTANT] OpenAI API error: {e}.")
            return None
        except Exception as e:
            print(f"[ASSISTANT] Whisper recognition error: {e}")
            return None

    def _audio_to_wav(self, audio):
        """Convert speech_recognition Audio object to WAV bytes"""
        try:
            # Create WAV file in memory
            wav_buffer = io.BytesIO()
            with wave.open(wav_buffer, 'wb') as wav_file:
                wav_file.setnchannels(1)  # Mono
                wav_file.setsampwidth(2)  # 16-bit
                wav_file.setframerate(audio.sample_rate)
                wav_file.writeframes(audio.frame_data)
            
            wav_buffer.seek(0)
            return wav_buffer.getvalue()
        except Exception as e:
            print(f"[ASSISTANT] Error converting audio to WAV: {e}")
            raise

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
