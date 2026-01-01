import time
import numpy as np
import threading
from audio.template_matcher import TemplateMatcher
from connectors.spotify_connector import SpotifyConnector
class WakeWordManager:
    """Manages wake word detection and related audio processing"""
    
    def __init__(self, wake_word_detector, audio_processors, recognizer, pixel_led=None, sample_rate=22050, energy_threshold=0.0001, confidence_threshold=0.95):
        """Initialize wake word manager"""
        self.wake_word_detector = wake_word_detector
        self.audio_processors = audio_processors
        self.recognizer = recognizer
        self.pixel_led = pixel_led
        self.sample_rate = sample_rate
        self.template_matcher = TemplateMatcher(sample_rate=sample_rate, n_mfcc=40) 
        self.spotify_connector = SpotifyConnector(None)
   
        self.energy_threshold = energy_threshold 
        self.confidence_threshold = confidence_threshold 
     
        self.window_duration = 1.5
        self.step_duration = 0.15 
        self.window_samples = int(self.window_duration * self.sample_rate)

        # State variables
        self.detection_running = False
        self.debug_mode = True
    
    def setup_audio_buffer(self):
        """Setup audio buffer for wake word detection"""
        from collections import deque
        import os
        import sounddevice as sd
        
        self.audio_buffer = deque(maxlen=self.window_samples)
        self.buffer_lock = threading.Lock()
        self.audio_stream = None  # Will be set later
        print(f"Audio buffer created with {self.window_samples} samples ({self.window_duration}s)")
        
        # Load templates for template matching verification
        audio_data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 
                                      'model_training', 'audio_data')
        if os.path.isdir(audio_data_dir):
            loaded = self.template_matcher.load_templates_from_directory(audio_data_dir)
            print(f"[TEMPLATES] Loaded {loaded} templates for wake word verification")
        else:
            print(f"[TEMPLATES] Warning: Audio data directory not found at {audio_data_dir}")
        
        # Configure AudioProcessors to use our buffer and template matcher for pre-filtering
        self.audio_processors.set_audio_buffer(self.audio_buffer, self.buffer_lock)
        self.audio_processors.set_template_matcher(self.template_matcher)  # For speech filtering
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

            # Capture a copy of the current audio window immediately
            # This prevents the sliding buffer from changing the data between detection and template matching
            with self.buffer_lock:
                audio_window = np.array(self.audio_buffer).copy()
            
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
                # ===== VERIFICATION STAGE 1: Voice Activity Detection =====
                is_speech = self.template_matcher.is_speech(audio_window, self.sample_rate, debug=self.debug_mode)
                
                if not is_speech:
                    if self.debug_mode:
                        print("Filtered: Detected false positive from music/background (VAD check)")
                    time.sleep(self.step_duration)
                    continue
                
                # ===== VERIFICATION STAGE 2: Template Matching (quick secondary filter) =====
            
                music_playing = self.is_spotify_playing()
                template_threshold = 0.25 if music_playing else 0.55  # Slightly relaxed thresholds
                
                is_match, similarity_score, best_label, all_scores = self.template_matcher.match_audio_window(
                    audio_window, self.sample_rate, match_threshold=template_threshold, debug=self.debug_mode
                    )
                    
                if not is_match:
                    if self.debug_mode:
                        print(f"Filtered: Template confidence too low ({similarity_score:.4f} < {template_threshold})")
                    time.sleep(self.step_duration)
                    continue
                else:
                    if self.debug_mode:
                        print(f"Template verified: Score={similarity_score:.4f}")
            
                
                # Both VAD and optionally template matching passed
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