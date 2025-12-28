
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

    def _setup_recognizer(self):
        # INMP441 is very sensitive - use balanced thresholds for natural speech
        self.recognizer.energy_threshold = 20  # Lower threshold to catch quieter speech
        self.recognizer.dynamic_energy_threshold = True
        self.recognizer.dynamic_energy_adjustment_damping = 0.15
        self.recognizer.dynamic_energy_ratio = 1.5  # Reduced from 2.0 for better natural speech detection
        self.recognizer.pause_threshold = 3.0  # 3.0 seconds of silence before stopping (allow long natural pauses)
        self.recognizer.phrase_threshold = 0.1  # Minimum 100ms to catch speech start quickly
        self.recognizer.non_speaking_duration = 2.0  # Max 2.0 seconds pause mid-phrase for natural speaking (breathing, hesitation)

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
        import gc
        
        if is_follow_up:
            print("[ASSISTANT] Listening for follow-up response...")
            timeout = min(timeout, 20)
        else:
            print("[ASSISTANT] Listening for command...")

        retry_count = 0
        while retry_count <= max_retries:
            microphone = None
            audio = None
            try:
                # Try opening the microphone with ALSA error suppression
                mic_kwargs = {}
                if self.device_index is not None:
                    mic_kwargs['device_index'] = self.device_index
                
                # Suppress ALSA warnings only during microphone object creation
                t_mic_start = timing_module.time()
                with suppress_alsa_errors():
                    try:
                        microphone = sr.Microphone(**mic_kwargs)
                    except (OSError, AttributeError) as e:
                        # Failed to find/open microphone device
                        raise Exception(f"Cannot open microphone device: {type(e).__name__}: {e}")
                
                # Open microphone stream (also with ALSA suppression)
                with suppress_alsa_errors():
                    with microphone as source:
                        t_mic_open = timing_module.time()
                        print(f"⏱️ Microphone open time: {(t_mic_open - t_mic_start)*1000:.0f}ms")
                        
                        # RE-APPLY aggressive thresholds just before listening
                        # (in case they got reset somewhere)
                        self.recognizer.pause_threshold = 3.0  # 3 seconds of silence
                        self.recognizer.non_speaking_duration = 1.5  # 2.5 seconds pause mid-phrase
                        self.recognizer.phrase_threshold = 0.1  # Start capturing after 100ms
                        
                        # Skip ambient noise calibration - it's too aggressive
                        # Dynamic threshold will handle adjustment during listening
                        print(f"Energy threshold: {self.recognizer.energy_threshold:.0f}")
                        print(f"Phrase threshold: {self.recognizer.phrase_threshold:.2f}s")
                        print(f"Pause threshold: {self.recognizer.pause_threshold:.2f}s")
                        print(f"Non-speaking duration: {self.recognizer.non_speaking_duration:.2f}s")
                        
                        self._print_attempt(retry_count, is_follow_up)
                        print("i m listening...")
                        listen_timeout = timeout if retry_count == 0 else timeout + 3

                        # Ensure recognizer exists
                        if not self.recognizer:
                            print("[ASSISTANT] Speech recognizer not initialized")
                            raise Exception("Recognizer not initialized")

                        t_listen_start = timing_module.time()
                        try:
                            audio = self.recognizer.listen(source, timeout=listen_timeout, phrase_time_limit=20)
                        except sr.WaitTimeoutError as wte:
                            # This is expected - no speech detected
                            print(f"[ASSISTANT] No speech detected (timeout after {listen_timeout}s). Trying again... ({retry_count + 1}/{max_retries + 1})")
                            if self.pixel_led:
                                self.pixel_led.off()
                            retry_count += 1
                            continue
                        except Exception as listen_error:
                            print(f"[ASSISTANT] Listen error: {type(listen_error).__name__}: {listen_error}")
                            if self.pixel_led:
                                self.pixel_led.off()
                            retry_count += 1
                            continue
                        
                        t_listen_end = timing_module.time()
                        print(f"⏱️ Listen duration: {(t_listen_end - t_listen_start)*1000:.0f}ms")

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

            except Exception as e:
                if self.pixel_led:
                    self.pixel_led.off()
                
                error_msg = str(e) if str(e) else "Unknown error"
                print(f"[ASSISTANT] Microphone/listen error: {error_msg}")
                
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
            finally:
                # Explicitly clean up audio and microphone objects
                if audio is not None:
                    try:
                        # Delete audio frame data explicitly
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
                
                # Force garbage collection to free C resources
                gc.collect()
                    
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
        finally:
            # Clean up audio data after recognition
            try:
                import gc
                gc.collect()
            except:
                pass

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
                        print(f"[MIC] ✓ Using device {idx}: {names[idx]}")
                        return True
                except Exception as e:
                    print(f"[MIC] ✗ Device {idx} failed: {type(e).__name__}: {e}")
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
                    print(f"[MIC] ✓ Using device {idx}: {names[idx]}")
                    return True
            except Exception as e:
                print(f"[MIC] ✗ Device {idx} failed: {type(e).__name__}")
                continue

        # Last resort - use None (system default)
        print("[MIC] No working device found, using system default")
        self.device_index = None
        return False