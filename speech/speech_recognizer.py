
from dotenv import load_dotenv
import speech_recognition as sr
import os
from contextlib import contextmanager

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
    def __init__(self, audio_processor, device_index=None, pixel_led=None):
        """Initialize recognizer and pick a safe microphone device index.

        On Linux the device index used on Windows (e.g. 1) may be invalid and
        attempting to open it causes ALSA/PyAudio errors. We try to pick a
        working device automatically and fall back to the system default.
        """
        self.device_index = None
        self.recognizer = sr.Recognizer()
        self.audio_processor = audio_processor
        self.pixel_led = pixel_led
        self._setup_recognizer()
        try:
            self._choose_device_index()
        except Exception:
            # Non-fatal: leave device_index as-is (None will let speech_recognition
            # use the system default device)
            self.device_index = None

    def _setup_recognizer(self):
        # INMP441 is very sensitive - use balanced thresholds
        self.recognizer.energy_threshold = 100  # Balanced for sensitive INMP441
        self.recognizer.dynamic_energy_threshold = True
        self.recognizer.dynamic_energy_adjustment_damping = 0.15
        self.recognizer.dynamic_energy_ratio = 1.5  # Increased for better noise rejection
        self.recognizer.pause_threshold = 1.5  # 1.5 seconds of silence before stopping
        self.recognizer.phrase_threshold = 0.5  # Minimum 500ms to avoid noise triggers
        self.recognizer.non_speaking_duration = 1.0  # Max 1 second pause mid-phrase

    def _print_attempt(self, retry_count, is_follow_up):
        if retry_count == 0:
            print("Please respond..." if is_follow_up else "Say your command...")
        else:
            print(f"I didn't catch that. Please try again... (attempt {retry_count + 1})")

    def listen_for_command(self, timeout=20, is_follow_up=False, max_retries=2):
        """
        Listen for user command with follow-up functionality and retry logic.
        """
        import time as timing_module
        
        if is_follow_up:
            print("[ASSISTANT] Listening for follow-up response...")
            timeout = min(timeout, 20)
        else:
            print("[ASSISTANT] Listening for command...")

        retry_count = 0
        while retry_count <= max_retries:
            try:
                # Try opening the microphone with ALSA error suppression
                try:
                    t_mic_start = timing_module.time()
                    mic_kwargs = {}
                    if self.device_index is not None:
                        mic_kwargs['device_index'] = self.device_index
                    
                    # Suppress ALSA warnings only during microphone object creation
                    # ALSA prints warnings at C library level which we can't fully suppress
                    with suppress_alsa_errors():
                        try:
                            microphone = sr.Microphone(**mic_kwargs)
                        except OSError as e:
                            # Failed to find/open microphone device
                            raise Exception(f"Cannot open microphone device: {e}")
                    
                    # Open microphone stream (also with ALSA suppression)
                    with suppress_alsa_errors():
                        with microphone as source:
                            t_mic_open = timing_module.time()
                            print(f"⏱️ Microphone open time: {(t_mic_open - t_mic_start)*1000:.0f}ms")
                            
                            # Quick ambient noise check (reduced from 0.5s to 0.2s)
                            # Dynamic threshold handles ongoing adjustment, this is just initial baseline
                            if retry_count == 0 and not hasattr(self, '_calibrated_once'):
                                print("Quick ambient calibration...")
                                t_cal_start = timing_module.time()
                                # Store original threshold
                                original_threshold = self.recognizer.energy_threshold
                                self.recognizer.adjust_for_ambient_noise(source, duration=0.15)
                                t_cal_end = timing_module.time()
                                
                                # Don't let calibration set threshold too high - cap it
                                if self.recognizer.energy_threshold > original_threshold * 2:
                                    print(f"Calibration too aggressive ({self.recognizer.energy_threshold:.0f}), capping at {original_threshold * 1.5:.0f}")
                                    self.recognizer.energy_threshold = original_threshold * 1.5
                                
                                print(f"Energy threshold: {self.recognizer.energy_threshold:.0f} (calibration took {(t_cal_end - t_cal_start)*1000:.0f}ms)")
                                self._calibrated_once = True  # Only calibrate once per session
                            
                            self._print_attempt(retry_count, is_follow_up)
                            print("i m listening...")
                            listen_timeout = timeout if retry_count == 0 else timeout + 3

                            # Ensure recognizer exists
                            if not self.recognizer:
                                print("[ASSISTANT] Speech recognizer not initialized")
                                retry_count += 1
                                continue

                            t_listen_start = timing_module.time()
                            audio = self.recognizer.listen(source, timeout=listen_timeout, phrase_time_limit=12)
                            t_listen_end = timing_module.time()
                            print(f"⏱️ Listen duration: {(t_listen_end - t_listen_start)*1000:.0f}ms")

                except Exception as mic_open_error:
                    if self.pixel_led:
                        self.pixel_led.off()
                    
                    error_msg = str(mic_open_error) if str(mic_open_error) else "Unknown error"
                    print(f"[ASSISTANT] Microphone open failed: {error_msg}")
                    
                    # On first retry, try to find a working device
                    if retry_count == 0:
                        print("[ASSISTANT] Searching for working microphone device...")
                        if self._choose_device_index(force_search=True):
                            print(f"[ASSISTANT] Found device, retrying with device_index={self.device_index}")
                        retry_count += 1
                        continue
                    else:
                        print("[ASSISTANT] Microphone still unavailable, skipping retry")
                        retry_count += 1
                        continue

                # Basic validation of audio object
                if audio is None or not hasattr(audio, 'frame_data') or not hasattr(audio, 'sample_rate'):
                    print("[ASSISTANT] Invalid audio captured, retrying...")
                    retry_count += 1
                    continue

                print(f"[ASSISTANT] Audio length: {len(audio.frame_data) / audio.sample_rate:.2f} seconds")
                print("Recognizing...")

                if len(audio.frame_data) < 1000:
                    print("[ASSISTANT] Audio too short, trying again...")
                    retry_count += 1
                    continue

                command = self._recognize_audio(audio)
                if command:
                    return command
                else:
                    retry_count += 1
                    continue

            except sr.WaitTimeoutError:
                self.pixel_led.off()
                print(f"[ASSISTANT] No speech detected. Trying again... ({retry_count + 1}/{max_retries + 1})")
                retry_count += 1
                continue
            except Exception as e:
                print(f"[ASSISTANT] Recognition failed: {e}. Trying again... ({retry_count + 1}/{max_retries + 1})")
                retry_count += 1
                continue
        print("[ASSISTANT] No valid command detected after multiple attempts.")
        # Speak feedback only after all retries are exhausted
        self.audio_processor.speak("I didn't hear anything. Please call if you need me.")
        return None

    def _recognize_audio(self, audio):
        try:
            command = self.recognizer.recognize_google(audio, language='en-US')
            print(f"[ASSISTANT] You said: {command}")
            cleaned_command = command.lower().strip()
            if len(cleaned_command) < 2:
                print("[ASSISTANT] Command too short, trying again...")
                # Don't speak here - let it retry silently
                return None
            return cleaned_command
        except (sr.RequestError, sr.UnknownValueError) as e:
            print(f"[ASSISTANT] Recognition error: {e}.")
            # Don't speak here - let the caller handle it to avoid self-listening
            return None
        except Exception as e:
            print(f"[ASSISTANT] Unexpected recognition error: {e}")
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
                        with sr.Microphone(device_index=idx) as _:
                            self.device_index = idx
                            print(f"[MIC] ✓ Using device {idx}: {names[idx]}")
                            return True
                except Exception as e:
                    print(f"[MIC] ✗ Device {idx} failed: {type(e).__name__}")
                    continue

        # Try all other devices
        for idx in range(len(names)):
            if idx in preferred_devices:
                continue  # Already tested
            try:
                print(f"[MIC] Testing device {idx}: {names[idx]}")
                with suppress_alsa_errors():
                    with sr.Microphone(device_index=idx) as _:
                        self.device_index = idx
                        print(f"[MIC] ✓ Using device {idx}: {names[idx]}")
                        return True
            except Exception:
                continue

        # Last resort - use None (system default)
        print("[MIC] No working device found, using system default")
        self.device_index = None
        return False