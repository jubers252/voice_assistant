import time
import numpy as np
import threading
from audio.advanced_wake_word_pipeline import AdvancedWakeWordPipeline
from connectors.spotify_connector import SpotifyConnector

class WakeWordManager:
    """Manages wake word detection using advanced multi-stage pipeline"""
    
    def __init__(self, wake_word_detector, audio_processors, recognizer, pixel_led=None, sample_rate=22050):
        """Initialize wake word manager
        
        Args:
            wake_word_detector: Neural network wake word detector
            audio_processors: Audio processor instance
            recognizer: Speech recognizer
            pixel_led: Optional LED controller
            sample_rate: Audio sample rate (default: 22050)
        """
        self.wake_word_detector = wake_word_detector
        self.audio_processors = audio_processors
        self.recognizer = recognizer
        self.pixel_led = pixel_led
        self.sample_rate = sample_rate
        self.spotify_connector = SpotifyConnector(None)
     
        self.window_duration = 1.0
        self.step_duration = 0.15 
        self.window_samples = int(self.window_duration * self.sample_rate)

        # State variables
        self.detection_running = False
        self.debug_mode = False
        
        # Initialize advanced pipeline
        self.advanced_pipeline = AdvancedWakeWordPipeline(
            wake_word_detector=wake_word_detector,
            template_matcher=None,
            sample_rate=sample_rate
        )
        print("[PIPELINE] Advanced multi-stage pipeline initialized")
    
    def setup_audio_buffer(self):
        """Setup audio buffer for wake word detection"""
        from collections import deque
        import sounddevice as sd
        
        self.audio_buffer = deque(maxlen=self.window_samples)
        self.buffer_lock = threading.Lock()
        self.audio_stream = None  # Will be set later
        print(f"[BUFFER] Audio buffer created: {self.window_samples} samples ({self.window_duration}s)")
        
        # Configure AudioProcessors to use our buffer
        self.audio_processors.set_audio_buffer(self.audio_buffer, self.buffer_lock)
        return self.audio_buffer, self.buffer_lock
    
    def set_audio_stream(self, stream):
        """Set the audio stream reference so we can stop it during speech recognition"""
        self.audio_stream = stream

    
    def is_spotify_playing(self):
        """
        Check if Spotify is currently playing music.
        
        Returns:
            bool: True if Spotify is actively playing, False otherwise
        """
   
        try:
            result = self.spotify_connector.main({"action": "current_track"})
            if result and "Currently playing" in str(result):
                return True
            return False
        except Exception as e:
            if self.debug_mode:
                print(f"[SPOTIFY] Error checking playback: {e}")
            return False
    
    

    def handle_wake_word_detection(self, process_command_callback):
        """Handle actions when wake word is detected"""
        import time as timing_module
        import threading
        
        t0 = timing_module.time()
        print("Wake word detected! Listening for command...")
        
        # Set LED to red immediately
        if self.pixel_led:
            self.pixel_led.set_error()  # Red color
        
        # Start beep in background immediately (non-blocking)
        beep_thread = threading.Thread(target=self._play_beep_async, daemon=True)
        beep_thread.start()
        
        # Set LED to blue while listening (no delay)
        if self.pixel_led:
            self.pixel_led.set_listening()  # Blue color
        
        print("Starting speech recognition...")
        
        user_command = self.recognizer.listen_for_command()

        print(f"Speech recognition result: {user_command}")
        
        # Check if command is not empty AND has meaningful length (>3 characters)
        if user_command and len(user_command.strip()) > 3:
            print(f"Processing command: {user_command}")
            should_exit = process_command_callback(user_command)
            print(f"Command processing result - should_exit: {should_exit}")
            if should_exit:
                return True  # Signal to break from main loop
        else:
            # Empty or too short - likely false wake word, skip processing
            if user_command:
                print(f"Command too short ({len(user_command)} chars), skipping: '{user_command}'")
            else:
                print("No command detected, waiting for next input...")
        
        # Set LED back to off after processing
        if self.pixel_led:
            self.pixel_led.off()
    
    def _play_beep_async(self):
        """Play beep sound in background without blocking"""
        try:
            self.audio_processors.play_beep_sound()
        except Exception as e:
            print(f"Beep sound error: {e}")
    
    def main_detection_loop(self, process_command_callback):
        """Main wake word detection loop using advanced pipeline"""
        print("[PIPELINE] Wake word detection loop started")
        
        while self.detection_running:
            # Verify wake word detector is available
            if not getattr(self, 'wake_word_detector', None) or not getattr(self.wake_word_detector, 'model', None):
                time.sleep(self.step_duration)
                continue
                
            # Check if we have enough audio data in our buffer
            if len(self.audio_buffer) < self.window_samples:
                time.sleep(self.step_duration)
                continue

            # Capture a copy of the current audio window
            with self.buffer_lock:
                audio_window = np.array(self.audio_buffer).copy()
            
            # Process through advanced multi-stage pipeline
            results = self.advanced_pipeline.process_audio_chunk(
                audio_window, 
                debug=self.debug_mode
            )
            
            if results['triggered']:
                print(f"[PIPELINE] ✓ Wake word TRIGGERED (fused score: {results['fused_score']:.4f})")
                should_exit = self.handle_wake_word_detection(process_command_callback)
                if should_exit:
                    self.detection_running = False
                    break
                print("[PIPELINE] Returning to wake word listening...")
            
            time.sleep(self.step_duration)
    
    def start_detection(self):
        """Start wake word detection"""
        self.detection_running = True
    
    def stop_detection(self):
        """Stop wake word detection"""
        self.detection_running = False
