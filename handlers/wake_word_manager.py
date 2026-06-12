import time
import numpy as np
import threading
from audio.wakeword_matcher import WakeWordMatcher

class WakeWordManager:
    """Manages wake word detection"""

    
    def __init__(self, wake_word_detector, audio_processors, recognizer, 
                 pixel_led=None, sample_rate=16000, energy_threshold=0.0001, 
                 confidence_threshold=0.75, templates_dir=None):
        """Initialize wake word manager"""
        self.wake_word_detector = wake_word_detector
        self.audio_processors = audio_processors
        self.recognizer = recognizer
        self.pixel_led = pixel_led
        self.sample_rate = sample_rate
        self.energy_threshold = energy_threshold
        self.confidence_threshold = confidence_threshold
        self.wakword_matcher = WakeWordMatcher()
        # Detection parameters
        self.window_duration =2.0  # seconds
        self.transcribe_duration = 1.3  # seconds (use first 1s for transcription)
        self.transcribe_cooldown_sec = 1.2  # debounce repeated transcribe calls
        self.last_transcribe_time = 0.0
        self.step_duration = 0.02   # seconds
        self.window_samples = int(self.window_duration * self.sample_rate)
        self.transcribe_samples = int(self.transcribe_duration * self.sample_rate)
        
        # State
        self.detection_running = False
        self.audio_stream = None
        self.audio_buffer = None
        self.buffer_lock = None
        
        # Parallel transcription state
        self.transcription_thread = None
        self.transcription_result = None
        self.transcription_lock = threading.Lock()
    
    def set_audio_stream(self, stream):
        """Store reference to audio stream"""
        self.audio_stream = stream
    
    def _transcribe_in_parallel(self, audio_window):
        """
        Run transcription in a separate thread.
        
        Args:
            audio_window: Audio data to transcribe
        """
        try:
            # Use last 1 second from the detected window for faster transcription
            transcribe_window = audio_window[-self.transcribe_samples:]
            result = self.wakword_matcher.transcribe_chunk(transcribe_window, sample_rate=self.sample_rate)
            return result
        except Exception as e:
            print(f"[ERROR] Transcription thread: {e}")
         
    
    def check_text_contains_wake_word(self, text, wake_word_ls= ["sophie"]):
        """
        Check if text contains any of the wake words.
        
        Args:
            text: Text to check
            wake_word_ls: List of wake words to search for
        
        Returns:
            True if contains any wake word, False otherwise
        """
        text = text.replace(" ", "").lower()  # Normalize text by removing spaces and converting to lowercase
        for word in wake_word_ls:
            if word.lower() in text.lower():
                return True
        return False
    
    
    def setup_audio_buffer(self):
        """Setup audio buffer for wake word detection"""
        from collections import deque
        
        self.audio_buffer = deque(maxlen=self.window_samples)
        self.buffer_lock = threading.Lock()
        print(f"[WWD] Audio buffer created ({self.window_duration}s window)")
        self.audio_processors.set_audio_buffer(self.audio_buffer, self.buffer_lock)
        return self.audio_buffer, self.buffer_lock
    
    def handle_wake_word_detection(self, process_command_callback):
        """Handle wake word detected - listen for command"""
        print("[WWD] Wake word detected!")
        
        try:
            self.audio_processors.play_beep_sound()
            user_command = self.recognizer.listen_for_command()
            
            if user_command:
                print(f"[COMMAND] {user_command}")
                result = process_command_callback(user_command)
                
                # Exit signal
                if result is None:
                    return True
            
            # Turn off LED
            if self.pixel_led:
                self.pixel_led.off()
            
            return False
            
        except Exception as e:
            print(f"[ERROR] Wake word handling: {e}")
            return False
    
    def main_detection_loop(self, process_command_callback):
        """Main wake word detection loop"""
        print("[WWD] Detection thread started\n")
        
        while self.detection_running:
            # Wait for enough audio data
            if len(self.audio_buffer) < self.window_samples:
                time.sleep(self.step_duration)
                continue
            
            if not self.wake_word_detector or not self.wake_word_detector.model:
                time.sleep(self.step_duration)
                continue
            
            # Get current energy threshold from recognizer
            recognizer_threshold = getattr(self.recognizer, 'energy_threshold', self.energy_threshold)
            
            # Perform detection
            audio_window = np.array(self.audio_buffer)
            detected, energy, confidence = self.wake_word_detector.detect_wakeword(
                audio_window, 
                self.sample_rate,
                energy_threshold=recognizer_threshold,
                confidence_threshold=self.confidence_threshold
            )
            
            # Log high-energy events for debugging
            if energy and energy > 0.001:
                status = "✓ DETECTED" if detected else "✗"
                print(f"[WWD] {status} | Energy: {energy:.6f} | Confidence: {confidence:.4f}")
            
            # Handle detection
            if detected:
                now = time.time()
                if (now - self.last_transcribe_time) < self.transcribe_cooldown_sec:
                    time.sleep(self.step_duration)
                    continue
                if confidence is not None and confidence > 0.93:
                    print("[WWD] High confidence wake word detected - processing immediately")
                    self.last_transcribe_time = now
                    if getattr(self.audio_processors, 'is_speaking', False):
                        try:
                            self.audio_processors.stop_speech()
                        except Exception:
                            pass
                        time.sleep(0.1)

                    should_exit = self.handle_wake_word_detection(process_command_callback)
                        
                    if should_exit:
                        self.detection_running = False
                        break
                
                else:
                    self.last_transcribe_time = now
                    # Start transcription in parallel thread
                    text = self._transcribe_in_parallel(audio_window)
                    print(f"[WWD] Transcribed text: '{text}'")
                
                # Check if text contains wake word "sophie"
                    word_list = ["sophie","soapy","Sobe", "Sofew", "Softening", "sobig","Selfie","Something", "sodeep"]  # Can be extended with more wake words
                    contains_sophie = self.check_text_contains_wake_word(text,word_list)
                            
                    print(f"[WWD] Contains 'sophie': {contains_sophie}")
            
                
               
                    if contains_sophie:
                        print("[WWD] Valid wake word + command detected!")
                        # Process wake word event

                        should_exit = self.handle_wake_word_detection(process_command_callback)
                        
                        if should_exit:
                            self.detection_running = False
                            break
                    else:
                        print("[WWD] Invalid command - ignoring")
                
                print("[WWD] Listening for wake word...\n")
            
            time.sleep(self.step_duration)
    
    def start_detection(self):
        """Start wake word detection"""
        self.detection_running = True
    
    def stop_detection(self):
        """Stop wake word detection"""
        self.detection_running = False
