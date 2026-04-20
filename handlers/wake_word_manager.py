import time
import numpy as np
import threading


class WakeWordManager:
    """Manages wake word detection"""
    
    def __init__(self, wake_word_detector, audio_processors, recognizer, 
                 pixel_led=None, sample_rate=16000, energy_threshold=0.0001, 
                 confidence_threshold=0.91):
        """Initialize wake word manager"""
        self.wake_word_detector = wake_word_detector
        self.audio_processors = audio_processors
        self.recognizer = recognizer
        self.pixel_led = pixel_led
        self.sample_rate = sample_rate
        self.energy_threshold = energy_threshold
        self.confidence_threshold = confidence_threshold
        
        # Detection parameters
        self.window_duration = 2.0  # seconds
        self.step_duration = 0.05   # seconds
        self.window_samples = int(self.window_duration * self.sample_rate)
        
        # State
        self.detection_running = False
        self.audio_stream = None
        self.audio_buffer = None
        self.buffer_lock = None
    
    def set_audio_stream(self, stream):
        """Store reference to audio stream"""
        self.audio_stream = stream
    
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
                # Interrupt speech if speaking
                if getattr(self.audio_processors, 'is_speaking', False):
                    try:
                        self.audio_processors.stop_speech()
                    except Exception:
                        pass
                    time.sleep(0.1)
                
                # Process wake word event
                should_exit = self.handle_wake_word_detection(process_command_callback)
                
                if should_exit:
                    self.detection_running = False
                    break
                
                print("[WWD] Listening for wake word...\n")
            
            time.sleep(self.step_duration)
    
    def start_detection(self):
        """Start wake word detection"""
        self.detection_running = True
    
    def stop_detection(self):
        """Stop wake word detection"""
        self.detection_running = False
