# audio/audio_processor.py
import os
import platform
import time
from dotenv import load_dotenv
import sounddevice as sd
import speech_recognition as sr
import tempfile
import pygame
import soundfile as sf
import threading
import numpy as np
from collections import deque
from contextlib import contextmanager
from langdetect import detect
import re
import azure.cognitiveservices.speech as speechsdk
# For Hindi transliteration
try:
    from indic_transliteration import sanscript
    from indic_transliteration.sanscript import transliterate
    TRANSLITERATION_AVAILABLE = True
except ImportError:
    print("Warning: indic-transliteration not installed. Hindi transliteration disabled.")
    TRANSLITERATION_AVAILABLE = False

# Load environment variables
load_dotenv()

# Suppress ALSA/JACK errors that are just warnings
@contextmanager
def suppress_alsa_errors():
    """Context manager to suppress ALSA/JACK error output"""
    try:
        # Redirect stderr to devnull to suppress ALSA errors
        devnull = os.open(os.devnull, os.O_WRONLY)
        old_stderr = os.dup(2)
        os.dup2(devnull, 2)
        os.close(devnull)
        yield
    finally:
        # Restore stderr
        os.dup2(old_stderr, 2)
        os.close(old_stderr)


CONVERSATION_FILE = "conversation_history.json"

def clean_text_for_speech(text: str) -> str:
    """
    Clean text before passing to speech synthesis.
    Preserves sentence structure and punctuation needed for natural TTS.
    
    Args:
        text: Text to clean
        
    Returns:
        Cleaned text - keeps punctuation and structure for TTS
    """
    
    
    # Remove ONLY problematic characters: markdown bullets, angle brackets
    # KEEP: periods, commas, question marks, exclamation marks (essential for TTS)
    problematic_chars = ['*', '>', '<']
    cleaned_text = text
    for char in problematic_chars:
        cleaned_text = cleaned_text.replace(char, '')

    # Convert markdown links [label](url) -> label (keep visible text, drop URL)
    cleaned_text = re.sub(r"\[([^\]]+)\]\((?:http[s]?://[^)]+)\)", r"\1", cleaned_text)

    # Remove standalone URLs (http(s) and www) that may remain
    cleaned_text = re.sub(r'http[s]?://\S+', '', cleaned_text)
    cleaned_text = re.sub(r'www\.\S+', '', cleaned_text)

    # Remove markdown list symbols (-, •) at line start
    cleaned_text = re.sub(r'^[-•]\s+', '', cleaned_text, flags=re.MULTILINE)

    # Clean up leftover parentheses that only contained URLs
    cleaned_text = re.sub(r"\(\s*\)", '', cleaned_text)

    # Clean up extra spaces but preserve structure
    lines = cleaned_text.split('\n')
    lines = [' '.join(line.split()) for line in lines if line.strip()]
    cleaned_text = ' '.join(lines)

    return cleaned_text

# Wake word detection parameters (matching training)
n_mfcc = 40
n_fft = 2048
hop_length = 512
n_mels = 128

class AudioProcessors:
    def __init__(self):
        """Initialize the voice assistant components"""
        print("Initializing Voice Assistant...")

        self.recognizer = None  # Will be set by SpeechRecognizer if needed
        self.microphone = None
        self.audio_channels = 1 # Channel configuration for microphone recording (stereo)
        self.tts_speed = 1.3     # Speech speed multiplier (1.0 = normal, 1.3 = 30% faster)
        self.mic_device_id = 0   # Google voiceHAT with stereo INMP mics (hw:3,0)
        self.mic_gain_factor = 1.0  # Increased for voiceHAT stereo INMP mics

        # Audio processing
        self.sample_rate = 22050
        self.duration = 1.0
        self.debug_mode = True           

        # Speech interruption control
        self.is_speaking = False
        self.speech_interrupted = False
        self.speech_thread = None
        self.pixel_led = None  # Will be set by voice assistant if available
        
        # Initialize pygame mixer once to prevent double initialization corruption
        self._init_pygame_mixer()
    
    def _init_pygame_mixer(self):
        """Initialize pygame mixer once to prevent double initialization corruption"""
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.pre_init(frequency=22050, size=-16, channels=2, buffer=512)
                pygame.mixer.init()
                print("Pygame mixer initialized successfully")
            else:
                print("Pygame mixer already initialized")
        except Exception as e:
            print(f"Warning: Failed to initialize pygame mixer: {e}")
    
    def set_pixel_led(self, pixel_led):
        """Set pixel LED controller for visual feedback during speech"""
        self.pixel_led = pixel_led
    
    def set_template_matcher(self, template_matcher):
        """Set template matcher for pre-filtering audio stream to speech only"""
        self._template_matcher = template_matcher
    
   
    def set_audio_buffer(self, buffer, buffer_lock):
        """Set external audio buffer for the callback to use
        
        Args:
            buffer: The deque buffer to store audio data
            buffer_lock: Threading lock for the buffer
        """
        self._external_buffer = buffer
        self._external_buffer_lock = buffer_lock
        print(f"External audio buffer configured with capacity: {buffer.maxlen}")
    
    # Function to record audio (from test_cnn_model.py)
    def record_audio(self, duration, sample_rate, save_path=None, device=None):
        """Record audio with INMP441 support and ALSA error suppression"""
        try:
            print("Recording...")
            # Use suppress_alsa_errors to hide JACK/ALSA warnings
            with suppress_alsa_errors():
                # If device is specified, use it
                if device is not None:
                    audio = sd.rec(
                        int(duration * sample_rate), 
                        samplerate=sample_rate, 
                        channels=self.audio_channels, 
                        dtype='float32',
                        device=device
                    )
                else:
                    audio = sd.rec(
                        int(duration * sample_rate), 
                        samplerate=sample_rate, 
                        channels=self.audio_channels, 
                        dtype='float32'
                    )
                sd.wait()
            
            print("Recording complete.")
            
            # Balance gain across stereo channels before flattening
            if self.audio_channels == 2 and audio.ndim == 2:
                # Normalize each channel to same RMS level
                channel_left = audio[:, 0]
                channel_right = audio[:, 1]
                
                # Calculate RMS for each channel
                rms_left = np.sqrt(np.mean(channel_left ** 2))
                rms_right = np.sqrt(np.mean(channel_right ** 2))
                
                if rms_left > 0 and rms_right > 0:
                    # Gain balance: scale both channels to average RMS
                    avg_rms = (rms_left + rms_right) / 2
                    gain_left = avg_rms / rms_left
                    gain_right = avg_rms / rms_right
                    
                    audio[:, 0] = channel_left * gain_left
                    audio[:, 1] = channel_right * gain_right
                    
                    print(f"Balanced stereo gain - Left gain: {gain_left:.3f}, Right gain: {gain_right:.3f}")
            
            audio_flat = audio.flatten()
            
            if save_path:
                sf.write(save_path, audio_flat, sample_rate)
                print(f"Audio saved to {save_path}")
            return audio_flat
        except Exception as e:
            print(f"Error recording audio: {e}")
            return None
        

    def transliterate_to_devanagari(self, text):
        """Convert romanized Hindi text to Devanagari script"""
        if not TRANSLITERATION_AVAILABLE:
            print("Transliteration unavailable - returning original text")
            return text
        
        try:
            # Transliterate from ITRANS (common romanization) to Devanagari
            devanagari_text = transliterate(text, sanscript.ITRANS, sanscript.DEVANAGARI)
            print(f"Transliterated: '{text}' -> '{devanagari_text}'")
            return devanagari_text
        except Exception as e:
            print(f"Transliteration error: {e}, returning original text")
            return text
    
    def speak(self, text, prompt=None, lang=None):
        """
        Threaded TTS function with interruption support and improved Hindi handling
        """
        # Clean text before processing (remove links/URLs etc.)
        text = clean_text_for_speech(text)
        
        # Stop any current speech first
        if self.is_speaking:
            self.stop_speech()
            time.sleep(0.1)  # Brief pause to ensure cleanup
        
     
        if hasattr(self, '_external_buffer') and hasattr(self, '_external_buffer_lock'):
            try:
                with self._external_buffer_lock:
                    self._external_buffer.clear()
                    if self.debug_mode:
                        print("Audio buffer cleared before TTS to prevent false wake word triggers")
            except Exception as e:
                if self.debug_mode:
                    print(f"Warning: Could not clear audio buffer: {e}")
        
        # Reset interruption flag
        self.speech_interrupted = False
        
        # Detect language - if Hindi characters found, use Hindi
        lang = 'en'
        hindi_pattern = r'[\u0900-\u097F]'  # Hindi Unicode range
        if re.search(hindi_pattern, text):
            lang = 'hi'
        else:
            lang = detect(text) if text.strip() else 'en'
                
        print(f"Final TTS text (lang={lang}): {text}")
        # Start new speech thread
        self.speech_thread = threading.Thread(
            target=self._speak_threaded, 
            args=(text, prompt, lang)
        )
        self.speech_thread.daemon = True
        self.speech_thread.start()

    def generate_and_play_azure_tts(self, text, speech_file_path=None, lang="en"):
        """Generate speech with Azure TTS and save to file for playback control.
        
        Returns the path to the generated file on success, or None on failure.
        """
        start_time = time.time()
        
        try:
            # Get Azure credentials from environment
            azure_key = os.getenv("tts_key")
            azure_region = os.getenv("tts_region", "centralindia")
            
            if not azure_key:
                raise ValueError("Azure TTS key not found in environment (tts_key)")
            
            if not speech_file_path:
                tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
                speech_file_path = tmp.name
                tmp.close()
            
            # Select voice based on language
            if lang == "hi":
                voice_name = "hi-IN-AartiNeural"
            else:
                voice_name =  "en-IN-AartiNeural"
            
            # Create Azure speech config
            azure_config = speechsdk.SpeechConfig(subscription=azure_key, region=azure_region)
            azure_config.speech_synthesis_voice_name = voice_name
            
            # Output to file for playback control (supports interruption)
            audio_config = speechsdk.audio.AudioOutputConfig(filename=speech_file_path)
            
            # Create synthesizer
            synthesizer = speechsdk.SpeechSynthesizer(speech_config=azure_config, audio_config=audio_config)
            
            print(f"Generating Azure TTS (voice={voice_name}, lang={lang})")
            
            # Synthesize speech to file
            result = synthesizer.speak_text_async(text).get()
            
            # Check result
            if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
                generation_time = time.time() - start_time
                print(f"Azure TTS generation took: {generation_time:.2f} seconds -> {speech_file_path}")
                return speech_file_path
            elif result.reason == speechsdk.ResultReason.Canceled:
                cancellation_details = result.cancellation_details
                print(f"Azure TTS canceled: {cancellation_details.reason}")
                if cancellation_details.error_details:
                    print(f"Error details: {cancellation_details.error_details}")
                return None
            
        except Exception as e:
            print(f"Azure TTS error: {e}")
            return None

    def _generate_and_play_simple(self, text, prompt=None, lang="en"):
        """Generate speech with Azure TTS and play with pygame for interruption support."""
        tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
        tmp_file_path = tmp_file.name
        tmp_file.close()

        try:
            # Generate Azure TTS to file
            gen_path = self.generate_and_play_azure_tts(text, speech_file_path=tmp_file_path, lang=lang)
            if not gen_path:
                raise RuntimeError('Azure TTS generation failed')

            # Play audio with pygame (supports interruption via stop_speech)
            if os.path.exists(tmp_file_path):
                try:
                    # Ensure mixer is initialized
                    if not pygame.mixer.get_init():
                        self._init_pygame_mixer()
                    
                    pygame.mixer.music.load(tmp_file_path)
                    pygame.mixer.music.set_volume(0.8)
                    pygame.mixer.music.play()

                    # Play while monitoring for interruption
                    while pygame.mixer.music.get_busy() and not self.speech_interrupted:
                        time.sleep(0.1)

                    pygame.mixer.music.stop()
                except Exception as pygame_error:
                    print(f"Pygame audio failed: {pygame_error}")
                  

        except Exception as e:
            print(f"TTS error: {e}")
        finally:
            # Clean up temp file
            try:
                if os.path.exists(tmp_file_path):
                    time.sleep(0.2)
                    os.unlink(tmp_file_path)
            except Exception:
                pass
    
    
    def _speak_threaded(self, text, prompt, lang="en"):
        """Threaded speech function with interruption support and improved Hindi processing"""
        self.is_speaking = True
        self.speech_interrupted = False
        
        # Set LED to green when starting to speak
        if self.pixel_led:
            print("[DEBUG] Setting LED to GREEN (speaking)")
            self.pixel_led.set_speaking()
        else:
            print("[DEBUG] pixel_led is None - LED not available")
        
        try:
            print(f"Speaking with TTS (lang={lang}): {text}")
            # Call the unified generation/play function with language
            self._generate_and_play_simple(text, prompt=prompt, lang=lang)
                
        except Exception as e:
            print(f"Edge TTS failed: {e}")
        finally:
            self.is_speaking = False
            # Turn off LED when done speaking
            if self.pixel_led:
                print("[DEBUG] Turning LED OFF (finished speaking)")
                self.pixel_led.off()
            else:
                print("[DEBUG] pixel_led is None - LED not available")
    

    
    
    def stop_speech(self):
        """Stop current speech immediately"""
        if self.is_speaking:
            print("DEBUG: stop_speech() called - interrupting current speech")
            self.speech_interrupted = True
            try:
                if pygame.mixer.get_init():
                    pygame.mixer.music.stop()
            except:
                pass
            
            # Wait briefly for thread to finish
            if self.speech_thread and self.speech_thread.is_alive():
                self.speech_thread.join(timeout=0.5)
    

    def wait_for_speech_completion(self, timeout=10):
        """Wait for current speech to complete (optional utility method)"""
        start_time = time.time()
        while self.is_speaking and (time.time() - start_time) < timeout:
            time.sleep(0.1)
        return not self.is_speaking  #
    
    
    def _system_beep(self):
        """Generate a system beep as fallback"""
        try:
            if platform.system() == "Windows":
                import winsound
                winsound.Beep(800, 300)  # 800Hz for 300ms
            else:
                print("\a")  # ASCII bell character
        except Exception:
            print("\a")  # Ultimate fallback
    
        
    def pause_listening(self, seconds=3):
        """Pause listening to avoid detecting the assistant's own voice"""
        import time
        print(f"Pausing listening for {seconds} seconds...")
        time.sleep(seconds)
    
    
    def check_microphones(self):
        """Check available microphones and their indices"""
        print("\nAvailable microphones:")
        try:
            names = sr.Microphone.list_microphone_names()
            for i, microphone_name in enumerate(names):
                print(f"  {i}: {microphone_name}")
            print(f"Currently using microphone index: {self.mic_device_id}")
        except Exception as e:
            print(f"Error listing microphones: {e}")
            return
        
        # Test current microphone
        try:
            # Create a temporary recognizer just for testing
            test_recognizer = sr.Recognizer()
            mic_kwargs = {}
            if self.mic_device_id is not None:
                mic_kwargs['device_index'] = self.mic_device_id
            # Use a context manager to test the microphone briefly
            with sr.Microphone(**mic_kwargs) as source:
                print(f"Testing microphone {mic_kwargs.get('device_index', 'default')}...")
                test_recognizer.adjust_for_ambient_noise(source, duration=1)
                print(f"Energy threshold: {test_recognizer.energy_threshold}")
                print(f"Current digital gain: {self.digital_gain}x")
                print("Microphone is working!")
        except Exception as e:
            print(f"Error with current microphone: {e}")
            print("Consider calling check_microphones() and updating mic_device_id")
    


    def play_beep_sound(self, beep_file = None):
        """Play a simple beep sound to indicate assistant is listening"""
        try:
            # Use the specific beep file
            if not beep_file:
                beep_file = "beep/short-beep-tone-47916.mp3"
            
            # Convert relative path to absolute if needed
            if not os.path.isabs(beep_file):
                script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                beep_file = os.path.join(script_dir, beep_file)
                print(f"[DEBUG] Resolved beep file path: {beep_file}")

            if os.path.exists(beep_file):
                try:
                    # Ensure mixer is initialized (single initialization per session)
                    if not pygame.mixer.get_init():
                        self._init_pygame_mixer()
                    
                    pygame.mixer.music.load(beep_file)
                    pygame.mixer.music.set_volume(0.6)  # Lower volume for beep
                    pygame.mixer.music.play()
                    
                    # Wait for the short beep to finish
                    while pygame.mixer.music.get_busy():
                        pygame.time.wait(10)
                    
                except Exception as pygame_error:
                    print(f"Pygame beep failed: {pygame_error}")
                    # Fallback to system beep
                    self._system_beep()
            else:
                print(f"Beep file not found: {beep_file}")
                print(f"[DEBUG] Checked absolute path: {os.path.abspath(beep_file)}")
                print(f"[DEBUG] Current working directory: {os.getcwd()}")
                self._system_beep()

        except Exception as e:
            print(f"Error playing beep: {e}")
            self._system_beep()



    def audio_callback(self, indata, frames, time_info, status):
        """Audio callback function - stores raw audio to buffer.
        
        All detection logic (VAD or pipeline) happens during processing.
        """
        if status:
            print(f"Audio callback status: {status}")
        
        if indata is None or len(indata) == 0:
            return

        try:
            # Average both stereo channels
            if indata.ndim > 1 and indata.shape[1] == 2:
                audio_samples = np.mean(indata, axis=1)
            else:
                audio_samples = indata[:, 0]
        except Exception:
            audio_samples = indata.flatten()
        
        # Store raw audio in buffer
        if hasattr(self, '_external_buffer') and hasattr(self, '_external_buffer_lock'):
            try:
                with self._external_buffer_lock:
                    self._external_buffer.extend(audio_samples)
            except Exception:
                pass

        
 