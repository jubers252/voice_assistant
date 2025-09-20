# audio/audio_processor.py
import os
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
from collections import deque

# Load environment variables
load_dotenv()


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

        # Initialize speech recognizer
        self.recognizer = sr.Recognizer()
        self.microphone = sr.Microphone(device_index=1) 
        self.audio_channels = 1  # Channel configuration for microphone recording
        self.tts_speed = 1.3     # Speech speed multiplier (1.0 = normal, 1.3 = 30% faster)
        self.mic_device_id = 1   # USB microphone device ID
        self.mic_gain_factor = 0.8  # Reduce gain for sensitive USB mic

        # Audio processing
        self.sample_rate = 22050
        self.duration = 1.5
        self.debug_mode = True           

        # Speech interruption control
        self.is_speaking = False
        self.speech_interrupted = False
        self.speech_thread = None
    
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
    def record_audio(self, duration, sample_rate, save_path=None):
        try:
            print("Recording...")
            audio = sd.rec(int(duration * sample_rate), samplerate=sample_rate, channels=1, dtype='float32')
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
        

    def speak(self, text, voice="en-IN-AartiNeural", rate="+10%", speed_multiplier=1.0, lang="en"):
        """
        Threaded TTS function with interruption support
        """
        # Stop any current speech first
        self.stop_speech()
        
        # Start new speech thread
        self.speech_thread = threading.Thread(
            target=self._speak_threaded, 
            args=(text, voice, rate, speed_multiplier, lang)
        )
        self.speech_thread.daemon = True
        self.speech_thread.start()

    def _generate_and_play_simple(self, text, voice, rate, speed_multiplier):
        """Simplified synchronous TTS generation and playback with interruption"""
        # Generate TTS
        tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
        tmp_file_path = tmp_file.name
        tmp_file.close()
        
        try:
            # Generate TTS synchronously
            communicate = edge_tts.Communicate(text, voice, rate=rate)
            asyncio.run(communicate.save(tmp_file_path))
            
            # Play with interruption
            if os.path.exists(tmp_file_path) and not self.speech_interrupted:
                pygame.mixer.init(frequency=22050, size=-16, channels=2, buffer=512)
                pygame.mixer.music.load(tmp_file_path)
                pygame.mixer.music.play()
                
                while pygame.mixer.music.get_busy() and not self.speech_interrupted:
                    time.sleep(0.05)  # Check every 50ms for interruption
                
                if self.speech_interrupted:
                    pygame.mixer.music.stop()
                    print("Speech interrupted!")
                
                pygame.mixer.quit()
                
        except Exception as e:
            print(f"TTS generation/playback error: {e}")
        finally:
            if os.path.exists(tmp_file_path):
                os.unlink(tmp_file_path)
    
    def _speak_threaded(self, text, voice, rate, speed_multiplier, lang):
        """Threaded speech function with interruption support"""
        self.is_speaking = True
        self.speech_interrupted = False
        
        try:
            # Set voice based on language
            if lang == "hi":
                voice = "hi-IN-AartiNeural"
            
            print(f"Speaking with Edge TTS: {text}")
            
            # Call the simplified function directly
            self._generate_and_play_simple(text, voice, rate, speed_multiplier)
                
        except Exception as e:
            print(f"Edge TTS failed: {e}")
        finally:
            self.is_speaking = False
    
    def stop_speech(self):
        """Stop current speech immediately"""
        if self.is_speaking:
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
    
        
    def pause_listening(self, seconds=3):
        """Pause listening to avoid detecting the assistant's own voice"""
        import time
        print(f"Pausing listening for {seconds} seconds...")
        time.sleep(seconds)
    
    def check_microphones(self):
        """Check available microphones and their indices"""
        print("\nAvailable microphones:")
        for i, microphone_name in enumerate(sr.Microphone.list_microphone_names()):
            print(f"  {i}: {microphone_name}")
        print(f"Currently using microphone index: {self.mic_device_id}")
        
        # Test current microphone
        try:
            recognizer = sr.Recognizer()
            with sr.Microphone(device_index=self.mic_device_id) as source:
                print(f"Testing microphone {self.mic_device_id}...")
                recognizer.adjust_for_ambient_noise(source, duration=1)
                print(f"Energy threshold: {recognizer.energy_threshold}")
                print("Microphone is working!")
        except Exception as e:
            print(f"Error with current microphone: {e}")
            print("Consider changing the device_index in the code")
    
    def play_beep_sound(self, beep_file = None):
        """Play a simple beep sound to indicate assistant is listening"""
        try:
            import pygame
            
            # Use the specific beep file
            if not beep_file:
                beep_file = "beep/short-beep-tone-47916.mp3"

            if os.path.exists(beep_file):
                pygame.mixer.init()
                pygame.mixer.music.load(beep_file)
                pygame.mixer.music.play()
                
                # Wait for the short beep to finish
                while pygame.mixer.music.get_busy():
                    pygame.time.wait(10)
                
                pygame.mixer.quit()
            else:
                print(f"Beep file not found: {beep_file}")
                # Fallback to system beep

        except Exception as e:
            print(f"Error playing beep: {e}")

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