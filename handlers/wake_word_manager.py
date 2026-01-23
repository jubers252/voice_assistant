import time
import numpy as np
import threading


class WakeWordManager:
    """Manages wake word detection and related audio processing"""
    
    def __init__(self, wake_word_detector, audio_processors, recognizer, pixel_led=None, sample_rate=22050, energy_threshold=0.0001, confidence_threshold=0.97
):
        """Initialize wake word manager"""
        self.wake_word_detector = wake_word_detector
        self.audio_processors = audio_processors
        self.recognizer = recognizer
        self.pixel_led = pixel_led
        self.sample_rate = sample_rate
        
        # Wake word detection thresholds (lowered for better sensitivity)
        self.energy_threshold = energy_threshold  # Lower energy threshold (0.035 vs default 0.050)
        self.confidence_threshold = confidence_threshold  # Lower confidence for better detection
        # Wake word detection parameters
        # Use a 2.0 second analysis window for wake-word detection (sliding window)
        self.window_duration = 1.0  # seconds (matches training duration)
        # How often (seconds) to step/check the buffer for a new window
        self.step_duration = 0.15    # seconds
        self.window_samples = int(self.window_duration * self.sample_rate)

        # State variables
        self.detection_running = False
        self.debug_mode = True
        self.audio_stream = None  # Will store reference to the audio stream
    
    def set_audio_stream(self, stream):
        """Store reference to audio stream for later control"""
        self.audio_stream = stream
    
    def setup_audio_buffer(self):
        """Setup audio buffer for wake word detection"""
        from collections import deque
        
        self.audio_buffer = deque(maxlen=self.window_samples)
        self.buffer_lock = threading.Lock()
        print(f"Audio buffer created with {self.window_samples} samples ({self.window_duration})")
        
        # Configure AudioProcessors to use our buffer
        self.audio_processors.set_audio_buffer(self.audio_buffer, self.buffer_lock)
        return self.audio_buffer, self.buffer_lock
    
    def handle_wake_word_detection(self, process_command_callback):
        """Handle actions when wake word is detected"""
        import time as timing_module
        
        t0 = timing_module.time()
        print("Wake word detected! Listening for command...")
        
        # Set LED to red for wake word detected
        if self.pixel_led:
            self.pixel_led.set_error()  # Red color
        time.sleep(0.2)  # Brief pause to show detection
        try:
            # Play beep sound asynchronously (non-blocking) to indicate readiness
            import threading
            beep_thread = threading.Thread(target=self._play_beep_async, daemon=True)
            beep_thread.start()

            # Set LED to blue while listening for command
            if self.pixel_led:
                self.pixel_led.set_listening()  # Blue color
            
            # Start speech recognition immediately without waiting for beep
            print("Starting speech recognition...")

            user_command = self.recognizer.listen_for_command()

            print(f"Speech recognition result: {user_command}")
            
            if user_command:
                print(f"Processing command: {user_command}")
                should_exit = process_command_callback(user_command)
                print(f"Command processing result - should_exit: {should_exit}")
                if should_exit:
                    return True  # Signal to break from main loop
            else:
                print("No command detected, waiting for next input...")
            
            # Set LED back to off after processing
            if self.pixel_led:
                self.pixel_led.off()
            
            return False  # Continue main loop
            
        except Exception as e:
            print(f"Error in handle_wake_word_detection: {e}")
            import traceback
            traceback.print_exc()
            return False  # Continue on error
            return False  # Continue on error
    
    def _play_beep_async(self):
        """Play beep sound in background without blocking"""
        try:
            self.audio_processors.play_beep_sound()
        except Exception as e:
            print(f"Beep sound error: {e}")
    
    def main_detection_loop(self, process_command_callback):
        """Main wake word detection loop"""
        print("Wake word detection loop started")
        
        while self.detection_running:
            # Ensure wake word detector and its model are available
            if not getattr(self, 'wake_word_detector', None) or not getattr(self.wake_word_detector, 'model', None):
                time.sleep(self.step_duration)
                continue
                
            # Check if we have enough audio data in our buffer
            if len(self.audio_buffer) < self.window_samples:
                time.sleep(self.step_duration)
                continue

            # Wake word detection (now always active, even during speech)
            audio_window = np.array(self.audio_buffer)
            detected, energy, confidence = self.wake_word_detector.detect_wakeword(
                audio_window, self.sample_rate, 
                energy_threshold=self.energy_threshold, 
                confidence_threshold=self.confidence_threshold
            )
            
            # Show detection attempts with energy > 0.010 for debugging
            if energy and energy > 0.010 and self.debug_mode:
                print(f"Wakeword check: Detected={detected}, Energy={energy:.4f}, Confidence={confidence}")
            
            # Handle wake word detection
            if detected:
                # If we're speaking, interrupt it via audio_processors
                if getattr(self.audio_processors, 'is_speaking', False):
                    print("Wake word detected while speaking - interrupting!")
                    try:
                        self.audio_processors.stop_speech()
                    except Exception:
                        pass
                    time.sleep(0.1)  # Reduced pause after interruption (was 0.3s)

                should_exit = self.handle_wake_word_detection(process_command_callback)
                if should_exit:
                    self.detection_running = False  # Set to False before breaking
                    break
                
                print("Returning to wake word listening...")
                
            time.sleep(self.step_duration)
    
    def start_detection(self):
        """Start wake word detection"""
        self.detection_running = True
    
    def stop_detection(self):
        """Stop wake word detection"""
        self.detection_running = False
