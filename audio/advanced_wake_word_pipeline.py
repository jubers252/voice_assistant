"""
Advanced Wake Word Detection Pipeline with Multi-Stage Processing

Pipeline Stages:
1. Mic Array Input
2. HPF (High Pass Filter 80-120 Hz)
3. Wake Model Detection (low threshold)
4. Speech Segment Capture (pre + post roll)
5. Feature Extraction (Log Mel / MFCC)
6. Template DTW + Duration Check
7. Score Fusion (combine multiple metrics)
8. Trigger Decision
"""

import numpy as np
import librosa
from scipy import signal
from scipy.spatial.distance import euclidean
import warnings
from datetime import datetime

warnings.filterwarnings('ignore')


class AudioFilter:
    """HPF and audio preprocessing"""
    
    @staticmethod
    def calculate_audio_energy(audio):
        """
        Calculate RMS energy of audio signal
        
        Args:
            audio (np.array): Audio signal
        
        Returns:
            float: RMS energy (0-1 normalized)
        """
        try:
            # Calculate RMS energy
            rms_energy = np.sqrt(np.mean(audio ** 2))
            # Normalize to 0-1 range (assuming audio is normalized)
            return float(rms_energy)
        except Exception as e:
            print(f"[AudioFilter] Energy calculation error: {e}")
            return 0.0
    
    @staticmethod
    def apply_hpf(audio, sample_rate, cutoff_freq=100):
        """
        Apply High Pass Filter to remove low frequency noise
        
        Args:
            audio (np.array): Audio signal
            sample_rate (int): Sample rate in Hz
            cutoff_freq (int): Cutoff frequency (80-120 Hz typical for speech)
        
        Returns:
            np.array: Filtered audio
        """
        try:
            # Butterworth HPF design
            nyquist = sample_rate / 2
            normalized_cutoff = cutoff_freq / nyquist
            
            if normalized_cutoff >= 1.0:
                return audio  # Can't filter at or above Nyquist
            
            # Design butterworth filter
            b, a = signal.butter(4, normalized_cutoff, btype='high')
            
            # Apply filter
            filtered_audio = signal.filtfilt(b, a, audio)
            return filtered_audio
        except Exception as e:
            print(f"[HPF] Filter error: {e}")
            return audio
    
    @staticmethod
    def remove_silence_edges(audio, sample_rate, energy_threshold=0.01, min_duration=0.1):
        """Remove silence from beginning and end"""
        frame_length = int(sample_rate * 0.025)  # 25ms frames
        hop_length = frame_length // 2
        
        # Calculate energy
        energy = librosa.feature.melspectrogram(y=audio, sr=sample_rate, n_fft=frame_length, hop_length=hop_length)
        energy = np.mean(energy, axis=0)
        
        # Find non-silent frames
        threshold = np.max(energy) * energy_threshold
        non_silent = np.where(energy > threshold)[0]
        
        if len(non_silent) == 0:
            return audio
        
        # Convert frame indices to sample indices
        start_frame = non_silent[0]
        end_frame = non_silent[-1]
        
        start_sample = start_frame * hop_length
        end_sample = (end_frame + 1) * hop_length
        
        return audio[start_sample:end_sample]


class SpeechSegmentCapture:
    """Capture speech with pre and post roll buffers"""
    
    def __init__(self, sample_rate=22050, pre_roll_ms=200, post_roll_ms=300):
        """
        Initialize segment capture
        
        Args:
            sample_rate (int): Sample rate
            pre_roll_ms (int): Pre-roll buffer (ms)
            post_roll_ms (int): Post-roll buffer (ms)
        """
        self.sample_rate = sample_rate
        self.pre_roll_samples = int(sample_rate * pre_roll_ms / 1000)
        self.post_roll_samples = int(sample_rate * post_roll_ms / 1000)
        self.pre_roll_buffer = np.array([])
    
    def add_pre_roll_buffer(self, audio_chunk):
        """Add audio to pre-roll buffer"""
        self.pre_roll_buffer = np.concatenate([self.pre_roll_buffer, audio_chunk])
        self.pre_roll_buffer = self.pre_roll_buffer[-self.pre_roll_samples:]
    
    def capture_segment(self, audio_chunk, post_roll_audio=None):
        """
        Capture speech segment with pre and post roll
        
        Args:
            audio_chunk (np.array): Current audio chunk
            post_roll_audio (np.array): Optional post-roll audio
        
        Returns:
            np.array: Complete segment with pre/post roll
        """
        segment = np.concatenate([self.pre_roll_buffer, audio_chunk])
        
        if post_roll_audio is not None:
            segment = np.concatenate([segment, post_roll_audio[:self.post_roll_samples]])
        
        return segment


class AdvancedFeatureExtractor:
    """Extract Log Mel and MFCC features"""
    
    def __init__(self, sample_rate=22050, n_mfcc=40, n_mels=128, n_fft=2048, hop_length=512):
        self.sample_rate = sample_rate
        self.n_mfcc = n_mfcc
        self.n_mels = n_mels
        self.n_fft = n_fft
        self.hop_length = hop_length
    
    def extract_log_mel_spectrogram(self, audio):
        """Extract log mel spectrogram"""
        try:
            mel_spec = librosa.feature.melspectrogram(
                y=audio,
                sr=self.sample_rate,
                n_fft=self.n_fft,
                hop_length=self.hop_length,
                n_mels=self.n_mels
            )
            # Convert to log scale
            log_mel = librosa.power_to_db(mel_spec, ref=np.max)
            return log_mel
        except Exception as e:
            print(f"[FeatureExtractor] Mel spectrogram error: {e}")
            return None
    
    def extract_mfcc(self, audio):
        """Extract MFCC features"""
        try:
            mfcc = librosa.feature.mfcc(
                y=audio,
                sr=self.sample_rate,
                n_mfcc=self.n_mfcc,
                n_fft=self.n_fft,
                hop_length=self.hop_length
            )
            return mfcc
        except Exception as e:
            print(f"[FeatureExtractor] MFCC error: {e}")
            return None
    
    def extract_deltas(self, mfcc):
        """Extract delta and delta-delta features"""
        delta = librosa.feature.delta(mfcc)
        delta_delta = librosa.feature.delta(mfcc, order=2)
        return np.concatenate([mfcc, delta, delta_delta], axis=0)


class DTWMatcher:
    """Dynamic Time Warping for template matching"""
    
    @staticmethod
    def dtw_distance(x, y, max_dist=None):
        """
        Compute Dynamic Time Warping distance
        
        Args:
            x (np.array): First sequence (features x time)
            y (np.array): Second sequence (features x time)
            max_dist (float): Maximum allowed distance
        
        Returns:
            float: DTW distance (normalized)
        """
        n, m = x.shape[1], y.shape[1]
        
        # Initialize DTW matrix
        dtw_matrix = np.full((n + 1, m + 1), np.inf)
        dtw_matrix[0, 0] = 0
        
        # Fill DTW matrix
        for i in range(1, n + 1):
            for j in range(1, m + 1):
                cost = np.sum((x[:, i-1] - y[:, j-1]) ** 2)
                dtw_matrix[i, j] = cost + min(dtw_matrix[i-1, j], dtw_matrix[i, j-1], dtw_matrix[i-1, j-1])
                
                # Early termination if exceeds max_dist
                if max_dist and dtw_matrix[i, j] > max_dist:
                    dtw_matrix[i, j] = np.inf
        
        # Normalize by path length
        path_length = n + m
        normalized_distance = dtw_matrix[n, m] / path_length if dtw_matrix[n, m] != np.inf else np.inf
        
        return normalized_distance
    
    @staticmethod
    def dtw_similarity(distance, max_distance=50.0):
        """
        Convert DTW distance to similarity score (0-1)
        
        Args:
            distance (float): DTW distance
            max_distance (float): Maximum expected distance
        
        Returns:
            float: Similarity score (0-1)
        """
        if distance == np.inf:
            return 0.0
        
        similarity = max(0, 1 - (distance / max_distance))
        return min(1.0, similarity)


class DurationValidator:
    """Validate audio duration matches expected wakeword duration"""
    
    def __init__(self, target_duration=1.0, tolerance=0.3):
        """
        Initialize duration validator
        
        Args:
            target_duration (float): Expected wakeword duration (seconds)
            tolerance (float): Tolerance (seconds)
        """
        self.target_duration = target_duration
        self.tolerance = tolerance
        self.min_duration = target_duration - tolerance
        self.max_duration = target_duration + tolerance
    
    def validate_duration(self, audio, sample_rate):
        """
        Validate audio duration
        
        Args:
            audio (np.array): Audio signal
            sample_rate (int): Sample rate
        
        Returns:
            tuple: (is_valid, duration, score)
                - is_valid: True if within range
                - duration: Actual duration in seconds
                - score: Duration confidence (0-1)
        """
        duration = len(audio) / sample_rate
        
        is_valid = self.min_duration <= duration <= self.max_duration
        
        # Calculate score based on distance from target
        distance = abs(duration - self.target_duration)
        score = max(0, 1 - (distance / self.tolerance))
        
        return is_valid, duration, score


class ScoreFusion:
    """Combine multiple detection scores"""
    
    def __init__(self, weights=None):
        """
        Initialize score fusion with weights
        
        Args:
            weights (dict): Weights for different scores
                - 'nn_confidence': Neural network confidence (default 0.4)
                - 'dtw_similarity': DTW template matching (default 0.4)
                - 'duration_score': Duration validation (default 0.2)
        """
        if weights is None:
            weights = {
                'nn_confidence': 0.4,
                'dtw_similarity': 0.4,
                'duration_score': 0.2
            }
        
        # Normalize weights
        total = sum(weights.values())
        self.weights = {k: v / total for k, v in weights.items()}
    
    def fuse_scores(self, nn_confidence, dtw_similarity, duration_score, debug=False):
        """
        Fuse multiple scores into single decision score
        
        Args:
            nn_confidence (float): NN model confidence (0-1)
            dtw_similarity (float): DTW similarity (0-1)
            duration_score (float): Duration validation score (0-1)
            debug (bool): Print debug info
        
        Returns:
            float: Fused score (0-1)
        """
        fused_score = (
            self.weights['nn_confidence'] * nn_confidence +
            self.weights['dtw_similarity'] * dtw_similarity +
            self.weights['duration_score'] * duration_score
        )
        
        if debug:
            print(f"[ScoreFusion] NN: {nn_confidence:.4f} | DTW: {dtw_similarity:.4f} | Duration: {duration_score:.4f} | Fused: {fused_score:.4f}")
        
        return fused_score


class AdvancedWakeWordPipeline:
    """Complete advanced wake word detection pipeline"""
    
    def __init__(self, wake_word_detector, template_matcher, sample_rate=22050):
        """
        Initialize pipeline
        
        Args:
            wake_word_detector: Neural network detector
            template_matcher: Template matching module
            sample_rate (int): Sample rate
        """
        self.wake_word_detector = wake_word_detector
        self.template_matcher = template_matcher
        self.sample_rate = sample_rate
        
        # Pipeline components
        self.audio_filter = AudioFilter()
        self.speech_capture = SpeechSegmentCapture(sample_rate)
        self.feature_extractor = AdvancedFeatureExtractor(sample_rate)
        self.dtw_matcher = DTWMatcher()
        self.duration_validator = DurationValidator(target_duration=1.0)
        self.score_fusion = ScoreFusion()
        
        # Store templates for DTW matching
        self.dtw_templates = []
        self.dtw_template_labels = []
    
    def get_time_based_thresholds(self):
        """
        Get thresholds adjusted for time of day (night mode support).
        
        Night mode (22:00 - 08:00): Lower thresholds for better detection at low volume
        Day mode (08:00 - 22:00): Normal thresholds
        
        Returns:
            dict: Threshold configuration with keys:
                - nn_confidence: NN model threshold (0-1)
                - trigger_threshold: Final trigger score threshold (0-1)
                - min_energy: Minimum audio energy for detection (RMS)
        """
        current_hour = datetime.now().hour
        
        # Night mode: 22:00 (22) to 08:00 (8)
        is_night_mode = current_hour >= 22 or current_hour < 8
        
        if is_night_mode:
            # Night: More sensitive for low-volume detection
            thresholds = {
                'nn_confidence': 0.70,      # Lowered from 0.70
                'trigger_threshold': 0.50,  # Lowered from 0.60
                'min_energy': 0.005,        # Much lower (accepts very quiet speech)
                'mode': 'NIGHT'
            }
        else:
            # Day: Standard thresholds
            thresholds = {
                'nn_confidence': 0.70,      # Standard
                'trigger_threshold': 0.60,  # Standard
                'min_energy': 0.02,         # Higher (requires moderate volume)
                'mode': 'DAY'
            }
        
        return thresholds
    
    def add_dtw_template(self, audio, label):
        """Add template for DTW matching"""
        try:
            mfcc = self.feature_extractor.extract_mfcc(audio)
            if mfcc is not None:
                self.dtw_templates.append(mfcc)
                self.dtw_template_labels.append(label)
        except Exception as e:
            print(f"[Pipeline] Error adding DTW template: {e}")
    
    def process_audio_chunk(self, audio_window, nn_confidence=None, debug=False):
        """
        Process audio through complete pipeline
        
        Args:
            audio_window (np.array): Audio chunk to process
            nn_confidence (float): Neural network confidence (0-1)
            debug (bool): Print debug output
        
        Returns:
            dict: Pipeline results
                - 'triggered': bool - Should wake word trigger
                - 'fused_score': float - Final decision score
                - 'components': dict - Individual component scores
                - 'metadata': dict - Additional info
        """
        try:
            # Get time-based thresholds (day/night mode)
            thresholds = self.get_time_based_thresholds()
            
            results = {
                'triggered': False,
                'fused_score': 0.0,
                'components': {},
                'metadata': {}
            }
            
            # Pre-check: Energy validation (to detect quiet speech)
            audio_energy = self.audio_filter.calculate_audio_energy(audio_window)
            if debug:
                print(f"[Pipeline] Audio energy: {audio_energy:.6f} (min required: {thresholds['min_energy']:.6f})")
            results['metadata']['audio_energy'] = audio_energy
            
            # Stage 1: HPF
            if debug:
                print("[Pipeline] Stage 1: Applying HPF (80-120 Hz)...")
            filtered_audio = self.audio_filter.apply_hpf(audio_window, self.sample_rate, cutoff_freq=100)
            results['metadata']['hpf_applied'] = True
            
            # Stage 2: NN Detection (adaptive threshold based on time of day)
            if debug:
                print(f"[Pipeline] Stage 2: NN Detection (threshold: {thresholds['nn_confidence']}, mode: {thresholds['mode']})...")
            if nn_confidence is None:
                detected, energy, nn_confidence = self.wake_word_detector.detect_wakeword(
                    filtered_audio, self.sample_rate, confidence_threshold=thresholds['nn_confidence']
                )
            
            results['components']['nn_confidence'] = nn_confidence
            
            # Stage 3: Speech Segment Capture
            if debug:
                print("[Pipeline] Stage 3: Capturing speech segment with pre/post roll...")
            segment = self.speech_capture.capture_segment(filtered_audio)
            results['metadata']['segment_duration'] = len(segment) / self.sample_rate
            
            # Stage 4: Feature Extraction
            if debug:
                print("[Pipeline] Stage 4: Extracting features...")
            mfcc = self.feature_extractor.extract_mfcc(segment)
            log_mel = self.feature_extractor.extract_log_mel_spectrogram(segment)
            
            if mfcc is None:
                return results
            
            results['metadata']['mfcc_shape'] = mfcc.shape
            results['metadata']['log_mel_shape'] = log_mel.shape if log_mel is not None else None
            
            # Stage 5: Template DTW + Duration
            if debug:
                print("[Pipeline] Stage 5: DTW matching and duration check...")
            
            # DTW matching
            dtw_similarity = 0.0
            if self.dtw_templates:
                dtw_distances = []
                for template in self.dtw_templates:
                    distance = self.dtw_matcher.dtw_distance(template, mfcc, max_dist=100)
                    similarity = self.dtw_matcher.dtw_similarity(distance, max_distance=50)
                    dtw_distances.append((distance, similarity))
                
                best_distance, best_similarity = min(dtw_distances, key=lambda x: x[0])
                dtw_similarity = best_similarity
                results['metadata']['best_dtw_distance'] = best_distance
            
            results['components']['dtw_similarity'] = dtw_similarity
            
            # Duration check
            is_valid_duration, duration, duration_score = self.duration_validator.validate_duration(
                segment, self.sample_rate
            )
            results['components']['duration_score'] = duration_score
            results['metadata']['duration_valid'] = is_valid_duration
            results['metadata']['duration_seconds'] = duration
            
            # Stage 6: Score Fusion
            if debug:
                print("[Pipeline] Stage 6: Fusing scores...")
            
            # Ensure all scores are valid floats
            nn_confidence = nn_confidence if nn_confidence is not None else 0.0
            dtw_similarity = dtw_similarity if dtw_similarity is not None else 0.0
            duration_score = duration_score if duration_score is not None else 0.0
            
            fused_score = self.score_fusion.fuse_scores(
                nn_confidence=nn_confidence,
                dtw_similarity=dtw_similarity,
                duration_score=duration_score,
                debug=debug
            )
            
            results['fused_score'] = fused_score
            
            # Stage 7: Trigger Decision
            if debug:
                print("[Pipeline] Stage 7: Making trigger decision...")
            
            # Trigger criteria: fused score > threshold AND duration valid AND sufficient energy
            trigger_threshold = thresholds['trigger_threshold']
            min_energy = thresholds['min_energy']
            
            energy_ok = audio_energy >= min_energy
            score_ok = fused_score > trigger_threshold
            duration_ok = is_valid_duration
            
            results['triggered'] = energy_ok and score_ok and duration_ok
            
            if debug:
                print(f"[Pipeline] Energy: {audio_energy:.6f} (min: {min_energy:.6f}) {'✓' if energy_ok else '✗'}")
                print(f"[Pipeline] Score: {fused_score:.4f} (threshold: {trigger_threshold}) {'✓' if score_ok else '✗'}")
                print(f"[Pipeline] Duration: {is_valid_duration} {'✓' if duration_ok else '✗'}")
                print(f"[Pipeline] Result: {'TRIGGERED' if results['triggered'] else 'REJECTED'} (mode: {thresholds['mode']})")
            
            # Add mode info to metadata
            results['metadata']['detection_mode'] = thresholds['mode']
            results['metadata']['nn_threshold'] = thresholds['nn_confidence']
            results['metadata']['trigger_threshold'] = thresholds['trigger_threshold']
            results['metadata']['min_energy'] = thresholds['min_energy']
            results['metadata']['energy_ok'] = energy_ok
            results['metadata']['score_ok'] = score_ok
            results['metadata']['duration_ok'] = duration_ok
            
            return results
        
        except Exception as e:
            print(f"[Pipeline] Error processing audio: {e}")
            return {'triggered': False, 'fused_score': 0.0, 'components': {}, 'metadata': {}}


# Example usage
if __name__ == "__main__":
    print("Advanced Wake Word Pipeline Module")
    print("This module provides multi-stage wake word detection:")
    print("1. Mic Array Input")
    print("2. HPF (80-120 Hz)")
    print("3. Wake Model (low threshold)")
    print("4. Speech Segment Capture")
    print("5. Feature Extraction (Log Mel / MFCC)")
    print("6. Template DTW + Duration Check")
    print("7. Score Fusion")
    print("8. Trigger Decision")
