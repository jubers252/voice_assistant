# audio/audio_processor.py
import os
import platform
import time
from dotenv import load_dotenv
import sounddevice as sd
import speech_recognition as sr
import edge_tts
import asyncio
import tempfile
import pygame
import soundfile as sf
import threading
import numpy as np
from collections import deque
from contextlib import contextmanager
from google.cloud import texttospeech
from google.oauth2 import service_account
from langdetect import detect
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
        self.audio_channels = 2  # Channel configuration for microphone recording (stereo)
        self.tts_speed = 1.3     # Speech speed multiplier (1.0 = normal, 1.3 = 30% faster)
        self.mic_device_id = 2   # Google voiceHAT with stereo INMP mics (hw:3,0)
        self.mic_gain_factor = 1.0  # Increased for voiceHAT stereo INMP mics
        self.digital_gain = 8.0     # BOOSTED 8x: for quieter speech detection with music playing

        # Audio processing
        self.sample_rate = 22050
        self.duration = 1.5
        self.debug_mode = True           

        # Speech interruption control
        self.is_speaking = False
        self.speech_interrupted = False
        self.speech_thread = None
        self.pixel_led = None  # Will be set by voice assistant if available
    
    def set_pixel_led(self, pixel_led):
        """Set pixel LED controller for visual feedback during speech"""
        self.pixel_led = pixel_led
    
    def set_template_matcher(self, template_matcher):
        """Set template matcher for pre-filtering audio stream to speech only"""
        self._template_matcher = template_matcher
    
    def enhance_speech(self, audio_chunk):
        """
        Enhance speech by removing background music using combined filtering.
        
        Uses high-pass filtering (250 Hz) + spectral gating (-30 dB).
        This approach removes music's bass interference while preserving wake word.
        
        Args:
            audio_chunk (ndarray): Audio samples to enhance
            
        Returns:
            ndarray: Enhanced audio with reduced background noise
        """
        try:
            from scipy import signal
            
            # ===== STRATEGY 1: High-pass filter (250 Hz, 4th order) =====
            # Aggressively removes music's bass while preserving speech formants
            # Frequency analysis shows:
            #   - Background music: Heavy energy in sub-bass (0-250 Hz)
            #   - Wake word: Dominant at 415.5 Hz with formants 250-4000 Hz
            nyquist = self.sample_rate / 2
            high_pass_freq = 250  # Hz (aggressive bass removal for music rejection)
            normalized_freq = high_pass_freq / nyquist
            
            # Use 4th order Butterworth filter for steeper rolloff (more aggressive)
            b, a = signal.butter(4, normalized_freq, btype='high')
            filtered = signal.filtfilt(b, a, audio_chunk)
            
            # ===== STRATEGY 2: Spectral gating (threshold -30 dB) =====
            # Suppress quiet frequency components where noise typically lives
            # More aggressive than -35 dB to better remove music masking
            try:
                import librosa
                
                # Compute STFT for spectral analysis
                D = librosa.stft(filtered, n_fft=2048, hop_length=512)
                S = np.abs(D)
                
                # Convert to dB with reference to max
                S_db = librosa.power_to_db(S ** 2, ref=np.max)
                
                # Create frequency mask: suppress components below -30 dB threshold (more aggressive)
                threshold_db = -30  # More aggressive than -35 (removes more noise)
                mask = S_db > threshold_db
                
                # Apply mask to suppress quiet noise
                S_gated = S * mask.astype(float)
                
                # Reconstruct time-domain signal
                D_gated = S_gated * np.exp(1j * np.angle(D))
                enhanced = librosa.istft(D_gated, hop_length=512)
                
                # Pad/trim to match original length if needed
                if len(enhanced) < len(audio_chunk):
                    enhanced = np.pad(enhanced, (0, len(audio_chunk) - len(enhanced)))
                elif len(enhanced) > len(audio_chunk):
                    enhanced = enhanced[:len(audio_chunk)]
                
            except (ImportError, Exception):
                # If librosa not available or STFT fails, skip spectral gating
                enhanced = filtered
            
            # ===== Subtle normalization =====
            max_val = np.max(np.abs(enhanced))
            if max_val > 1.2:  # Only normalize if needed
                enhanced = enhanced / max_val
            
            return enhanced
            
        except Exception as e:
            # On error, return original
            return audio_chunk
    
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
            audio_flat = audio.flatten()
            
            # Apply fixed digital gain
            if self.digital_gain != 1.0:
                audio_flat = audio_flat * self.digital_gain
                # Prevent clipping by normalizing if needed
                max_val = np.max(np.abs(audio_flat))
                if max_val > 1.0:
                    audio_flat = audio_flat / max_val
                    print(f"Applied digital gain {self.digital_gain}x (normalized to prevent clipping)")
                else:
                    print(f"Applied digital gain {self.digital_gain}x")
            
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
        
        lang = detect(text)
        # if lang != "hi" :
        #     is_hindi = self.detect_hindi_by_keywords(text)
        #     if is_hindi:
        #         text = self.transliterate_to_devanagari(text)
                
        print(f"Final TTS text (lang={lang}): {text}")
        # Start new speech thread
        self.speech_thread = threading.Thread(
            target=self._speak_threaded, 
            args=(text, prompt, lang)
        )
        self.speech_thread.daemon = True
        self.speech_thread.start()

        
    def generate_and_play_google_tts(self, text, speech_file_path=None, lang="en"):
        """Generate speech with Google Cloud TTS and save to `speech_file_path`.

        Returns the path to the generated file on success, or None on failure.
        """
        start_time = time.time()
        
        # Select voice based on language
        if lang == "hi":
            language_code = "hi-IN"
            voice_name = "hi-IN-Chirp3-HD-Achernar"
            speaking_rate = 1.0  # Normal rate for natural speech
        else:
            language_code = "en-IN"
            voice_name = "en-IN-Chirp3-HD-Achernar"
            speaking_rate = 1.0  # Normal rate for natural speech
        
        print(f"Generating audio with Google Cloud TTS (voice={voice_name}, lang={lang})")
        try:
            # Ensure a path was provided
            if not speech_file_path:
                tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
                speech_file_path = tmp.name
                tmp.close()

            # Google TTS has 5000 character limit per synthesis request
            # Split only if text exceeds limit, otherwise keep it whole for natural flow
            max_chunk_size = 5000
            
            if len(text) <= max_chunk_size:
                # Text fits in one request - best for natural speech
                chunks = [text]
            else:
                # Only split if absolutely necessary
                # Split by sentences to maintain naturalness
                import re
                
                # Split by sentence boundaries (. ! ? followed by space)
                # This preserves sentence structure
                sentences = re.split(r'(?<=[.!?।])\s+', text)
                
                chunks = []
                current_chunk = ""
                
                for sentence in sentences:
                    sentence = sentence.strip()
                    if not sentence:
                        continue
                    
                    # If adding this sentence exceeds max size, save and start new chunk
                    test_chunk = current_chunk + (" " if current_chunk else "") + sentence
                    if len(test_chunk) > max_chunk_size:
                        if current_chunk.strip():
                            chunks.append(current_chunk.strip())
                        current_chunk = sentence
                    else:
                        if current_chunk:
                            current_chunk += " " + sentence
                        else:
                            current_chunk = sentence
                
                # Add remaining chunk
                if current_chunk.strip():
                    chunks.append(current_chunk.strip())
                
                # If no chunks, use original text
                if not chunks:
                    chunks = [text]

            print(f"Text length: {len(text)} chars. Chunks: {len(chunks)}")

            # Load credentials from service account file
            creds = service_account.Credentials.from_service_account_file(
                "nimble-gate-366207-d1ca63590ec3.json"
            )
            
            # Create client
            client = texttospeech.TextToSpeechClient(credentials=creds)
            
            # Generate TTS for each chunk and combine
            audio_segments = []
            for i, chunk in enumerate(chunks):
                if not chunk.strip():
                    continue
                
                print(f"Generating TTS chunk {i+1}/{len(chunks)}: {len(chunk)} chars")
                    
                response = client.synthesize_speech(
                    input=texttospeech.SynthesisInput(text=chunk),
                    voice=texttospeech.VoiceSelectionParams(
                        language_code=language_code,
                        name=voice_name,
                    ),
                    audio_config=texttospeech.AudioConfig(
                        audio_encoding=texttospeech.AudioEncoding.MP3,
                        speaking_rate=speaking_rate,
                        pitch=0.0,  # Normal pitch
                    )
                )
                audio_segments.append(response.audio_content)
            
            # Combine all audio segments with small pause between them if multiple chunks
            if len(audio_segments) > 1:
                # Add small silence between chunks for natural pause
                # This is approximately 500ms of silence
                silence_duration = 0.5
                combined_audio = audio_segments[0]
                for segment in audio_segments[1:]:
                    combined_audio += segment
            else:
                combined_audio = audio_segments[0] if audio_segments else b''
            
            print(f"Combined {len(audio_segments)} audio segment(s)")
            
            # Save to file
            with open(speech_file_path, 'wb') as out:
                out.write(combined_audio)

            generation_time = time.time() - start_time
            print(f"Audio generation took: {generation_time:.2f} seconds -> {speech_file_path}")
            return speech_file_path
        except Exception as e:
            print(f"Google TTS generation error: {e}")
            return None


    def _generate_and_play_simple(self, text, prompt=None, lang="en"):
        """Generate speech (Google Cloud TTS preferred; Edge TTS fallback) and play it."""
        tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
        tmp_file_path = tmp_file.name
        tmp_file.close()

        try:
            # Try Google Cloud TTS first
            try:
                gen_path = self.generate_and_play_google_tts(text, speech_file_path=tmp_file_path, lang=lang)
                if not gen_path:
                    raise RuntimeError('Google TTS generation failed')
            except Exception as google_error:
                print(f"Google TTS failed, falling back to Edge TTS: {google_error}")
                # Edge TTS fallback with language support
                if lang == "hi":
                    voice_to_use = 'hi-IN-SwaraNeural'
                else:
                    voice_to_use = 'en-IN-AartiNeural'
                communicate = edge_tts.Communicate(text, voice_to_use)
                asyncio.run(communicate.save(tmp_file_path))

            # Play audio with pygame (with fallback)
            if os.path.exists(tmp_file_path):
                try:
                    pygame.mixer.pre_init(frequency=22050, size=-16, channels=2, buffer=512)
                    pygame.mixer.init()
                    self._play_bluetooth_wakeup()
                    pygame.mixer.music.load(tmp_file_path)
                    pygame.mixer.music.set_volume(0.8)
                    pygame.mixer.music.play()

                    while pygame.mixer.music.get_busy() and not self.speech_interrupted:
                        time.sleep(0.1)

                    pygame.mixer.music.stop()
                    pygame.mixer.quit()
                except Exception as pygame_error:
                    print(f"Pygame audio failed: {pygame_error}")
                  

        except Exception as e:
            print(f"TTS error: {e}")
        finally:
            try:
                if os.path.exists(tmp_file_path):
                    time.sleep(0.2)
                    os.unlink(tmp_file_path)
            except Exception:
                pass
    
    def _play_bluetooth_wakeup(self):
        """Play a very short, quiet sound to wake up Bluetooth speaker
        
        This prevents the first words from being cut off on Bluetooth speakers
        which have a startup delay.
        """
        try:
            # Generate a longer wakeup sound (300ms) for slower Bluetooth speakers
            duration = 0.3  # 300 milliseconds - longer for Bluetooth lag
            frequency = 440  # Hz (A4 note, but will be very quiet)
            sample_rate = 22050
            
            # Generate sine wave
            t = np.linspace(0, duration, int(sample_rate * duration))
            waveform = np.sin(2 * np.pi * frequency * t)
            
            # Make it very quiet (3% volume) so user barely hears it
            waveform = waveform * 0.03
            
            # Convert to 16-bit PCM
            waveform_int16 = (waveform * 32767).astype(np.int16)
            
            # Create a temporary WAV file
            import wave
            temp_wav = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
            temp_wav_path = temp_wav.name
            temp_wav.close()
            
            with wave.open(temp_wav_path, 'w') as wav_file:
                wav_file.setnchannels(1)  # Mono
                wav_file.setsampwidth(2)   # 16-bit
                wav_file.setframerate(sample_rate)
                wav_file.writeframes(waveform_int16.tobytes())
            
            # Play the wakeup sound
            sound = pygame.mixer.Sound(temp_wav_path)
            sound.set_volume(0.03)  # Very quiet
            sound.play()
            
            # Wait for it to finish (300ms + buffer for Bluetooth)
            time.sleep(0.4)
            
            # Clean up
            try:
                os.unlink(temp_wav_path)
            except:
                pass
                
        except Exception as e:
            # If wakeup fails, just continue - not critical
            if self.debug_mode:
                print(f"Bluetooth wakeup sound failed (non-critical): {e}")
    
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
    
    def _clean_hindi_text(self, text):
        """Clean and prepare Hindi text for better TTS pronunciation"""
        import re
        
        # Remove excessive punctuation that might affect pronunciation
        text = re.sub(r'[^\w\s\u0900-\u097F.,!?]', '', text)
        
        # Add pauses after sentences for better clarity
        text = re.sub(r'([.!?])', r'\1 ', text)
        
        # Ensure proper spacing
        text = re.sub(r'\s+', ' ', text).strip()
        
        return text
    
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
        return not self.is_speaking  # Returns True if speech completed, False if timeout
    
    
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
    
    def set_digital_gain(self, gain_value):
        """Set digital gain for MEMS microphone
        
        Args:
            gain_value (float): Gain multiplier (1.0 = no gain, 2.0 = double volume, 0.5 = half volume)
        """
        self.digital_gain = max(0.1, min(10.0, gain_value))  # Clamp between 0.1x and 10x
        print(f"Digital gain set to {self.digital_gain}x")
    
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

            if os.path.exists(beep_file):
                try:
                    # Try pygame with better parameters first
                    import pygame
                    pygame.mixer.pre_init(frequency=22050, size=-16, channels=2, buffer=512)
                    pygame.mixer.init()
                    pygame.mixer.music.load(beep_file)
                    pygame.mixer.music.set_volume(0.6)  # Lower volume for beep
                    pygame.mixer.music.play()
                    
                    # Wait for the short beep to finish
                    while pygame.mixer.music.get_busy():
                        pygame.time.wait(10)
                    
                    pygame.mixer.quit()
                except Exception as pygame_error:
                    print(f"Pygame beep failed: {pygame_error}")
                    # Fallback to system beep
                    self._system_beep()
            else:
                print(f"Beep file not found: {beep_file}")
                self._system_beep()

        except Exception as e:
            print(f"Error playing beep: {e}")
            self._system_beep()

    def audio_callback(self, indata, frames, time_info, status):
        """Audio callback function for real-time audio processing
        
        Applies speech filtering to reduce background music/noise from reaching
        the wake word detector. Only human speech is stored in the buffer.
        
        Note: This callback stores audio data in the VoiceAssistant's buffer,
        not in AudioProcessors itself.
        """
        if status:
            print(f"Audio callback status: {status}")
        # Defensive checks
        if indata is None or len(indata) == 0:
            return

        try:
            # Average both stereo channels for better audio quality
            if indata.ndim > 1 and indata.shape[1] == 2:
                audio_samples = np.mean(indata, axis=1)
            else:
                audio_samples = indata[:, 0]
        except Exception:
            # Fallback if audio is already 1-D
            audio_samples = indata.flatten()
        
        # Apply digital gain for MEMS microphones
        if hasattr(self, 'digital_gain') and self.digital_gain != 1.0:
            audio_samples = audio_samples * self.digital_gain
            # Prevent clipping
            audio_samples = np.clip(audio_samples, -1.0, 1.0)

        # ===== Store audio in buffer =====
        # Note: Audio is stored raw here. Filtering is applied only to the
        # detection window in wake_word_manager before model inference.
        should_store = True
        
        # Store in the VoiceAssistant's buffer (if available)
        if should_store and hasattr(self, '_external_buffer') and hasattr(self, '_external_buffer_lock'):
            try:
                with self._external_buffer_lock:
                    self._external_buffer.extend(audio_samples)
            except Exception as e:
                pass  # Silently skip buffer errors
        # Buffer not configured is OK - initialization happens asynchronously

        
    # Comprehensive list of romanized Hindi words
   

    def detect_hindi_by_keywords(self, text):
        """Simple and reliable: detect Hindi by counting Hindi words"""
        self.HINDI_WORDS = {
        # Pronouns
        'main', 'mein', 'hum', 'aap', 'tum', 'tu', 'yeh', 'ye', 'woh', 'wo', 
        'mera', 'meri', 'mere', 'tera', 'teri', 'tere', 'uska', 'uski', 'uske',
        'hamara', 'hamari', 'hamare', 'tumhara', 'tumhari', 'tumhare',
        
        # Verbs
        'hai', 'hain', 'ho', 'tha', 'thi', 'the', 'hoga', 'hogi', 'honge',
        'karna', 'karo', 'kar', 'kiya', 'kiye', 'karta', 'karti', 'karte',
        'jaana', 'jao', 'gaya', 'gayi', 'gaye', 'aana', 'aao', 'aaya', 'aayi',
        'rahe', 'raha', 'rahi', 'chahiye', 'chaiye', 'sakta', 'sakti', 'sakte',
        
        # Question words
        'kya', 'kaun', 'kab', 'kahan', 'kaise', 'kaisa', 'kaisi', 'kaise',
        'kyun', 'kyu', 'kitna', 'kitni', 'kitne',
        
        # Common words
        'abhi', 'aaj', 'kal', 'parso', 'subah', 'shaam', 'raat', 'din',
        'baje', 'minute', 'ghanta', 'samay', 'waqt',
        'bahut', 'thoda', 'jyada', 'kam', 'sab', 'kuch', 'koi',
        'achha', 'acha', 'bura', 'theek', 'thik',
        
        # Postpositions
        'ka', 'ki', 'ke', 'ko', 'se', 'mein', 'par', 'tak', 'ke liye',
        
        # Common phrases
        'namaste', 'namaskar', 'dhanyavad', 'shukriya', 'maaf',
        'haan', 'nahi', 'naa', 'ji', 'bilkul',
        
        # Weather/time
        'mausam', 'garmi', 'sardi', 'baarish', 'dhoop', 'hawa',
    }
        words = text.lower().split()
        
        # Count Hindi words
        hindi_count = sum(1 for word in words if word.strip('.,!?') in  self.HINDI_WORDS)
        total_words = len(words)
        
        if hindi_count >= 3:  # At least 3 Hindi words
            percentage = (hindi_count / total_words) * 100
            return True
        else:
            return False
