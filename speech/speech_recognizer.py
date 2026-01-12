from dotenv import load_dotenv
import speech_recognition as sr
import os
from contextlib import contextmanager
import time
import gc

# Load environment variables
load_dotenv()

# Try to import OpenAI for Whisper fallback
try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    print("[WARNING] OpenAI not available. Install with: pip install openai")

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
        """Initialize recognizer with Google free API as primary and Whisper as fallback.
        
        Args:
            audio_processor: Audio processor instance
            device_index: Optional microphone device index
            pixel_led: Optional LED control instance
        """
        self.device_index = device_index or 2
        self.recognizer = sr.Recognizer()
        self.audio_processor = audio_processor
        self.pixel_led = pixel_led
        self.spotify_connector = None
        self.is_music_playing = False
        
        # Whisper configuration
        self.use_whisper_fallback = OPENAI_AVAILABLE and os.getenv('OPENAI_API_KEY')
        self.whisper_language = os.getenv('WHISPER_LANGUAGE', 'en')
        
        if self.use_whisper_fallback:
            self.openai_client = OpenAI()
            print("[RECOGNIZER] Whisper fallback enabled")
        
        self._setup_recognizer()
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
                    pass
            print("[RECOGNIZER] Microphone warmed up")
        except Exception as e:
            print(f"[RECOGNIZER] Microphone warm-up failed (non-critical): {e}")
    
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
        """Configure speech recognition parameters"""
        self.recognizer.energy_threshold = 20
        self.recognizer.dynamic_energy_threshold = False
        self.recognizer.dynamic_energy_adjustment_damping = 0.15
        self.recognizer.dynamic_energy_ratio = 1.5
        self.recognizer.pause_threshold = 1.0
        self.recognizer.phrase_threshold = 0.3
        self.recognizer.non_speaking_duration = 0.8
    
    def _print_attempt(self, retry_count, is_follow_up):
        """Print user-friendly prompt for speech input"""
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
            time.sleep(2.0)

            self.audio_processor.play_beep_sound()
            if self.pixel_led:
                self.pixel_led.set_listening()
            return True  
        else:
            if self.pixel_led:
                self.pixel_led.set_error()
            return False

    def listen_for_command(self, timeout=20, is_follow_up=False, max_retries=1):
        """Listen for user command with retry logic.
        
        Uses Google free API as primary, Whisper as fallback.
        """
        # Adjust timeout if music is playing
        if self.is_music_playing:
            timeout = 5
            print("[ASSISTANT] Music is playing - using 5s timeout")
        
        phrase_time_limit = 5 if timeout == 5 else 15
        
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
                    if self.pixel_led:
                        self.pixel_led.off()
                    return command
                else:
                    # Recognition failed, treat as error
                    if not self._handle_listen_error(attempt, "Sorry, no speech detected."):
                        pass
               
            except Exception as e:
                print(f"[ASSISTANT] Error: {e}")
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

    def _recognize_audio(self, audio):
        """Recognize audio using Google free API with Whisper fallback"""
        try:
            # Try Google free API first
            return self._recognize_with_google(audio)
        except Exception as e:
            print(f"[ASSISTANT] Google recognition failed: {e}")
            
            # Try Whisper fallback if available
            if self.use_whisper_fallback:
                print("[ASSISTANT] Trying Whisper fallback...")
                return self._recognize_with_whisper(audio)
            
            return None
        finally:
            gc.collect()

    def _recognize_with_google(self, audio):
        """Recognize audio using Google free Speech Recognition API"""
        try:
            command = self.recognizer.recognize_google(audio, language="en-US")
            print(f"[ASSISTANT] Google recognized: {command}")
            cleaned_command = command.lower().strip()
            
            if len(cleaned_command) < 2:
                print("[ASSISTANT] Command too short, trying again...")
                return None
            
            return cleaned_command
            
        except sr.UnknownValueError:
            print("[ASSISTANT] Google could not understand audio")
            return None
        except sr.RequestError as e:
            print(f"[ASSISTANT] Google API error: {e}")
            return None

    def _recognize_with_whisper(self, audio):
        """Recognize audio using OpenAI Whisper API as fallback"""
        try:
            # Save audio to temporary file
            import tempfile
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                f.write(audio.get_wav_data())
                temp_file = f.name
            
            # Send to Whisper
            with open(temp_file, 'rb') as f:
                transcript = self.openai_client.audio.transcriptions.create(
                    model="whisper-1",
                    file=f,
                    language=self.whisper_language
                )
            
            # Cleanup
            os.remove(temp_file)
            
            command = transcript.text.lower().strip()
            print(f"[ASSISTANT] Whisper recognized: {command}")
            
            if len(command) < 2:
                print("[ASSISTANT] Command too short")
                return None
            
            return command
            
        except Exception as e:
            print(f"[ASSISTANT] Whisper error: {e}")
            return None

    def list_available_microphones(self):
        """Return a list of available microphone names."""
        try:
            names = sr.Microphone.list_microphone_names()
            return names
        except Exception:
            return []

    def _choose_device_index(self, force_search=False):
        """Choose a working device index with priority for known good devices."""
        names = self.list_available_microphones()
        if not names:
            self.device_index = None
            return False

        if self.device_index is not None and isinstance(self.device_index, int):
            if 0 <= self.device_index < len(names):
                return True

        if not force_search:
            self.device_index = None
            return True

        # Try preferred devices
        preferred_devices = [1, 2]
        print(f"[MIC] Available devices: {len(names)}")
        
        for idx in preferred_devices:
            if idx < len(names):
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

        # Try all other devices
        for idx in range(len(names)):
            if idx in preferred_devices:
                continue
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

        print("[MIC] No working device found, using system default")
        self.device_index = None
        return False
