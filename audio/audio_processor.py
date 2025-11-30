# audio/audio_processor.py
import os
import platform
import time
import sys
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

        # Initialize speech recognizer. Do NOT open a Microphone here with a
        # hardcoded device index — that works on Windows but often fails on
        # Linux where device indices differ and ALSA will complain. The
        # SpeechRecognizer class will choose a working device.
        self.recognizer = sr.Recognizer()
        self.microphone = None
        self.audio_channels = 1  # Channel configuration for microphone recording
        self.tts_speed = 1.3     # Speech speed multiplier (1.0 = normal, 1.3 = 30% faster)
        self.mic_device_id = None   # Will use system default unless configured
        self.mic_gain_factor = 0.8  # Reduce gain for sensitive USB mic

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
                        channels=1, 
                        dtype='float32',
                        device=device
                    )
                else:
                    audio = sd.rec(
                        int(duration * sample_rate), 
                        samplerate=sample_rate, 
                        channels=1, 
                        dtype='float32'
                    )
                sd.wait()
            
            print("Recording complete.")
            audio_flat = audio.flatten()
            if save_path:
                sf.write(save_path, audio_flat, sample_rate)
                print(f"Audio saved to {save_path}")
            return audio_flat
        except Exception as e:
            print(f"Error recording audio: {e}")
            return None
        

    def detect_language(self, text):
        """Detect if text is in Hindi or English"""
        import re
        
        # Check for Hindi (Devanagari) characters
        hindi_pattern = r'[\u0900-\u097F]'
        if re.search(hindi_pattern, text):
            return "hi"
        return "en"
    
    def speak(self, text, voice="en-IN-AartiNeural", rate="+10%", speed_multiplier=1.0, lang=None):
        """
        Threaded TTS function with interruption support and improved Hindi handling
        """
        # Stop any current speech first
        if self.is_speaking:
            self.stop_speech()
            time.sleep(0.1)  # Brief pause to ensure cleanup
        
        # Clear the wake word audio buffer to prevent TTS from triggering false detections
        # This allows interruption (since new audio will refill buffer) but prevents 
        # the assistant's own voice from causing false positives
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
        
        # Auto-detect language if not specified
        if lang is None:
            lang = self.detect_language(text)
        
        # Improve Hindi voice selection and rate
        if lang == "hi":
            voice = "hi-IN-AartiNeural"  # Better Hindi voice
            rate = "+0%"  # Slower rate for better Hindi pronunciation
        
        # Start new speech thread
        self.speech_thread = threading.Thread(
            target=self._speak_threaded, 
            args=(text, voice, rate, speed_multiplier, lang)
        )
        self.speech_thread.daemon = True
        self.speech_thread.start()

    def _generate_and_play_simple(self, text, voice, rate, speed_multiplier):
        """Simple TTS generation and playback with Bluetooth speaker support"""
        tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
        tmp_file_path = tmp_file.name
        tmp_file.close()
        
        try:
            # Generate TTS
            communicate = edge_tts.Communicate(text, voice, rate=rate)
            asyncio.run(communicate.save(tmp_file_path))
            
            # Play audio with better concurrent audio support
            if os.path.exists(tmp_file_path):
                try:
                    # Initialize pygame mixer with parameters that work better with other audio apps
                    pygame.mixer.pre_init(frequency=22050, size=-16, channels=2, buffer=512)
                    pygame.mixer.init()
                    
                    # Wake up Bluetooth speaker with brief silence before actual audio
                    # This prevents first words from being cut off
                    self._play_bluetooth_wakeup()
                    
                    pygame.mixer.music.load(tmp_file_path)
                    pygame.mixer.music.set_volume(0.8)  # Slightly lower volume to avoid conflicts
                    pygame.mixer.music.play()
                    
                    # Wait for playback to finish
                    while pygame.mixer.music.get_busy() and not self.speech_interrupted:
                        time.sleep(0.1)
                    
                    # Cleanup
                    pygame.mixer.music.stop()
                    pygame.mixer.quit()
                    
                except Exception as pygame_error:
                    print(f"Pygame audio failed: {pygame_error}")
                    # Try alternative method if pygame fails
                    self._try_alternative_audio_playback(tmp_file_path)
                
        except Exception as e:
            print(f"TTS error: {e}")
        finally:
            # Delete temp file
            try:
                if os.path.exists(tmp_file_path):
                    time.sleep(0.2)  # Brief wait
                    os.unlink(tmp_file_path)
            except:
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
    
    def _speak_threaded(self, text, voice, rate, speed_multiplier, lang):
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
            # Enhanced voice selection based on language
            if lang == "hi":
                # Use better Hindi voices and adjust rate
                available_hindi_voices = [
                    "hi-IN-AartiNeural"      # Female, fallback
                ]
                voice = available_hindi_voices[0]  # Use the best one
                rate = "+0%"  # Normal rate for better clarity
                
                # Clean up text for better Hindi pronunciation
                text = self._clean_hindi_text(text)
            
            print(f"Speaking with Edge TTS ({voice}): {text}")
            
            # Call the simplified function directly
            self._generate_and_play_simple(text, voice, rate, speed_multiplier)
                
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
    
    def _try_alternative_audio_playback(self, tmp_file_path):
        """Alternative audio playback method when pygame fails"""
        try:
            # Try using Windows' built-in audio player
            if platform.system() == "Windows":
                import subprocess
                subprocess.run([
                    'powershell', '-c', 
                    f'Add-Type -AssemblyName presentationCore; '
                    f'$mediaPlayer = New-Object system.windows.media.mediaplayer; '
                    f'$mediaPlayer.open([uri]"{tmp_file_path}"); '
                    f'$mediaPlayer.Play(); '
                    f'Start-Sleep -Seconds 3'
                ], capture_output=True, timeout=10)
            else:
                # For other platforms, try system commands
                subprocess.run(['play', tmp_file_path], capture_output=True, timeout=10)
        except Exception as alt_error:
            print(f"Alternative audio playback also failed: {alt_error}")
            self._system_beep()  # Final fallback
    
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
            recognizer = sr.Recognizer()
            mic_kwargs = {}
            if self.mic_device_id is not None:
                mic_kwargs['device_index'] = self.mic_device_id
            # Use a context manager to test the microphone briefly
            with sr.Microphone(**mic_kwargs) as source:
                print(f"Testing microphone {mic_kwargs.get('device_index', 'default')}...")
                recognizer.adjust_for_ambient_noise(source, duration=1)
                print(f"Energy threshold: {recognizer.energy_threshold}")
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
        
        Note: This callback stores audio data in the VoiceAssistant's buffer,
        not in AudioProcessors itself.
        """
        if status:
            print(f"Audio callback status: {status}")
        # Defensive checks
        if indata is None or len(indata) == 0:
            return

        try:
            audio_samples = indata[:, 0]
        except Exception:
            # Fallback if audio is already 1-D
            audio_samples = indata.flatten()

        # Store in the VoiceAssistant's buffer (if available)
        if hasattr(self, '_external_buffer') and hasattr(self, '_external_buffer_lock'):
            try:
                with self._external_buffer_lock:
                    self._external_buffer.extend(audio_samples)
            except Exception as e:
                if self.debug_mode:
                    print(f"Error appending to external audio buffer: {e}")
        elif self.debug_mode:
            print("No external buffer configured for audio callback")