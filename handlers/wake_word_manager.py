import time
import numpy as np
import threading
import librosa
import os


class SimpleTemplateMatcher:
    """Simple template matcher using cosine similarity on MFCC features"""
    
    def __init__(self, sample_rate=16000, n_mfcc=40):
        self.sample_rate = sample_rate
        self.n_mfcc = n_mfcc
        self.templates = []
        self.template_labels = []
    
    def extract_features(self, audio):
        """Extract mean MFCC features from audio"""
        try:
            mfcc = librosa.feature.mfcc(y=audio, sr=self.sample_rate, n_mfcc=self.n_mfcc)
            # Return mean of each MFCC coefficient across time
            return np.mean(mfcc, axis=1)
        except Exception as e:
            print(f"[TM] Error extracting features: {e}")
            return None
    
    def load_template(self, audio, label="template"):
        """Load a template from audio data"""
        try:
            features = self.extract_features(audio)
            if features is not None:
                self.templates.append(features)
                self.template_labels.append(label)
        except Exception as e:
            print(f"[TM] Error loading template: {e}")
    
    def load_templates_from_directory(self, directory_path):
        """Load all audio files from directory as templates"""
        if not os.path.isdir(directory_path):
            return 0
        
        loaded = 0
        for filename in sorted(os.listdir(directory_path)):
            if filename.endswith(('.wav', '.mp3', '.ogg', '.flac')):
                try:
                    file_path = os.path.join(directory_path, filename)
                    audio, sr = librosa.load(file_path, sr=self.sample_rate)
                    self.load_template(audio, filename)
                    loaded += 1
                except Exception as e:
                    print(f"[TM] Error loading {filename}: {e}")
        
        if loaded > 0:
            print(f"[TM] Loaded {loaded} templates")
        return loaded
    
    def cosine_similarity(self, vec1, vec2):
        """Calculate cosine similarity between two vectors (0-1 range)"""
        dot_product = np.dot(vec1, vec2)
        norm1 = np.linalg.norm(vec1) + 1e-10
        norm2 = np.linalg.norm(vec2) + 1e-10
        # Returns 0-1: 1.0 = identical, 0.0 = orthogonal
        return dot_product / (norm1 * norm2)
    
    def match(self, audio, threshold=0.70):
        """
        Match audio against templates using cosine similarity.
        Returns: (matched, best_score, best_label)
        """
        if not self.templates:
            return True, 1.0, "no_templates"
        
        try:
            features = self.extract_features(audio)
            if features is None:
                return True, 1.0, "extraction_failed"
            
            best_score = -1.0
            best_label = None
            
            for template, label in zip(self.templates, self.template_labels):
                similarity = self.cosine_similarity(features, template)
                if similarity > best_score:
                    best_score = similarity
                    best_label = label
            
            matched = best_score >= threshold
            return matched, best_score, best_label
            
        except Exception as e:
            print(f"[TM] Matching error: {e}")
            return True, 1.0, "error"


class WakeWordManager:
    """Manages wake word detection"""
    
    def __init__(self, wake_word_detector, audio_processors, recognizer, 
                 pixel_led=None, sample_rate=16000, energy_threshold=0.0001, 
                 confidence_threshold=0.91, templates_dir=None):
        """Initialize wake word manager"""
        self.wake_word_detector = wake_word_detector
        self.audio_processors = audio_processors
        self.recognizer = recognizer
        self.pixel_led = pixel_led
        self.sample_rate = sample_rate
        self.energy_threshold = energy_threshold
        self.confidence_threshold = confidence_threshold
        
        # Template matching for verification (secondary check)
        self.template_matcher = SimpleTemplateMatcher(sample_rate=sample_rate)
        self.use_template_matching = False
        # NN is already 95% precise at 0.933. Templates catch remaining edge cases
        self.template_match_threshold = 0.70
        
        # Load templates if directory provided
        if templates_dir and os.path.exists(templates_dir):
            num_templates = self.template_matcher.load_templates_from_directory(templates_dir)
            if num_templates > 0:
                self.use_template_matching = True
                print(f"[WWM] Loaded {num_templates} templates | NN(0.933, 100% recall, 95% precision) + Templates(70% match)\n")
        
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
    
    def set_template_threshold(self, threshold):
        """Adjust template matching threshold (0.0 to 1.0)"""
        if 0.0 <= threshold <= 1.0:
            self.template_match_threshold = threshold
            print(f"[WWM] Template threshold set to {threshold:.2f} ({threshold*100:.1f}%)")
        else:
            print(f"[WWM] Invalid threshold. Must be between 0.0 and 1.0")
    
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
                # Verify with template matching if enabled
                if self.use_template_matching:
                    matched, score, label = self.template_matcher.match(
                        audio_window, 
                        threshold=self.template_match_threshold
                    )
                    if not matched:
                        print(f"[TM] Rejected: {score:.2f} < {self.template_match_threshold:.2f}")
                        time.sleep(self.step_duration)
                        continue
                
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
