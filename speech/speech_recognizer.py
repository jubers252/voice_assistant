
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
    def __init__(self, device_index=None):
        """Initialize recognizer and pick a safe microphone device index.

        On Linux the device index used on Windows (e.g. 1) may be invalid and
        attempting to open it causes ALSA/PyAudio errors. We try to pick a
        working device automatically and fall back to the system default.
        """
        self.device_index = None
        self.recognizer = sr.Recognizer()
        self._setup_recognizer()
        try:
            self._choose_device_index()
        except Exception:
            # Non-fatal: leave device_index as-is (None will let speech_recognition
            # use the system default device)
            self.device_index = None

    def _setup_recognizer(self):
        # INMP441 is very sensitive - use lower thresholds
        self.recognizer.energy_threshold = 150  # Much lower for sensitive INMP441 (was 400)
        self.recognizer.dynamic_energy_threshold = True
        self.recognizer.dynamic_energy_adjustment_damping = 0.15
        self.recognizer.dynamic_energy_ratio = 1.5
        self.recognizer.pause_threshold = 0.8  # Shorter pause
        self.recognizer.phrase_threshold = 0.3  # Lower threshold
        self.recognizer.non_speaking_duration = 0.8  # Shorter duration

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
                    
                    # Suppress ALSA errors when opening microphone
                    with suppress_alsa_errors():
                        microphone = sr.Microphone(**mic_kwargs)
                    
                    with microphone as source:
                        t_mic_open = timing_module.time()
                        print(f"⏱️ Microphone open time: {(t_mic_open - t_mic_start)*1000:.0f}ms")
                        
                        # Adjust for ambient noise on first attempt to calibrate INMP441
                        if retry_count == 0:
                            print("Calibrating for ambient noise...")
                            self.recognizer.adjust_for_ambient_noise(source, duration=0.5)
                            print(f"Energy threshold adjusted to: {self.recognizer.energy_threshold}")
                        
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
                    # Try to recover by choosing a different device index once
                    print(f"[ASSISTANT] Microphone open failed: {mic_open_error}")
                    if self._choose_device_index(force_search=True):
                        print(f"[ASSISTANT] Retrying with device_index={self.device_index}")
                        retry_count += 1
                        continue
                    else:
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
                print(f"[ASSISTANT] No speech detected. Trying again... ({retry_count + 1}/{max_retries + 1})")
                retry_count += 1
                continue
            except Exception as e:
                # Keep trying but avoid crashing on unexpected errors
                print(f"[ASSISTANT] Recognition failed: {e}. Trying again... ({retry_count + 1}/{max_retries + 1})")
                retry_count += 1
                continue
        print("[ASSISTANT] No valid command detected after multiple attempts.")
        return None

    def _recognize_audio(self, audio):
        try:
            command = self.recognizer.recognize_google(audio, language='en-US')
            print(f"[ASSISTANT] You said: {command}")
            cleaned_command = command.lower().strip()
            if len(cleaned_command) < 2:
                print("[ASSISTANT] Command too short, trying again...")
                return None
            return cleaned_command
        except (sr.RequestError, sr.UnknownValueError) as e:
            print(f"[ASSISTANT] Recognition error: {e}.")
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
        """Choose a working device index.

        If self.device_index is already set and valid, keep it. Otherwise try
        to find a suitable index. Returns True if a device was selected.
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

        # Prefer default (None) so speech_recognition uses the system default
        if not force_search:
            self.device_index = None
            return True

        # Force search: try indices 0..len(names)-1 and test opening
        for idx in range(len(names)):
            try:
                # Try opening briefly to validate - suppress ALSA errors
                with suppress_alsa_errors():
                    with sr.Microphone(device_index=idx) as _:
                        self.device_index = idx
                        return True
            except Exception:
                continue

        # Last resort - use None
        self.device_index = None
        return False