"""
Template matching module for secondary wake word verification.

This module provides chi-squared distance-based template matching for
verifying wake word detections detected by neural networks. It helps
reduce false positives by confirming detections with MFCC-based matching.

Two-stage detection pipeline:
1. Neural Network (fast, handles variations) -> confidence score
2. Template Matching (accurate, discriminative) -> verification score

Both must pass to trigger wake word action.
"""

import numpy as np
import librosa
import sounddevice as sd
import os


class TemplateMatcher:
    """
    Template-based wake word verification using chi-squared distance on MFCC features.
    
    Designed to work as second-stage verification in a two-stage wake word detection system:
    - Stage 1: Neural Network detects potential wake word
    - Stage 2: Template Matcher confirms it's actually the wake word (not false positive)
    
    Key metrics:
    - Chi-squared distance 30-40: Same word instances (similarity 0.76-0.90)
    - Chi-squared distance 100+: Different words (similarity <0.30)
    """
    
    def __init__(self, sample_rate=22050, n_mfcc=40, n_fft=2048, hop_length=512):
        """
        Initialize template matcher with audio processing parameters.
        
        Args:
            sample_rate (int): Audio sample rate in Hz. Default 22050 Hz.
            n_mfcc (int): Number of MFCC coefficients. Default 40.
            n_fft (int): FFT window size. Default 2048.
            hop_length (int): Hop length for STFT. Default 512.
        """
        self.sample_rate = sample_rate
        self.n_mfcc = n_mfcc
        self.n_fft = n_fft
        self.hop_length = hop_length
        self.templates = []
        self.template_labels = []
    
    # ==================== Voice Activity Detection ====================
    
    def is_speech(self, audio, sample_rate=None, debug=False):
        """
        Detect if audio contains human speech (even with loud background music).
        
        Uses formant detection to identify speech. Formants are distinctive peaks
        in human speech that persist even when music is playing. This method detects
        how formants vary over time - a key indicator of human speech.
        
        Args:
            audio (ndarray): Audio signal (1D array).
            sample_rate (int): Sample rate. Uses self.sample_rate if None.
            debug (bool): If True, print analysis details.
            
        Returns:
            bool: True if audio likely contains speech, False if only music/noise.
        """
        if sample_rate is None:
            sample_rate = self.sample_rate
        
        try:
            # Compute magnitude spectrogram
            S = librosa.stft(audio, n_fft=self.n_fft, hop_length=self.hop_length)
            mag_spec = np.abs(S)
            
            # Get frequency bins
            freqs = librosa.fft_frequencies(sr=sample_rate, n_fft=self.n_fft)
            
            # ===== Formant band analysis =====
            # F1 (first formant): 700-1220 Hz - strong in vowels
            # F2 (second formant): 1220-2600 Hz - discriminative
            # F3 (third formant): 2600-3500 Hz - present in speech
            
            f1_mask = (freqs >= 700) & (freqs <= 1220)
            f2_mask = (freqs >= 1220) & (freqs <= 2600)
            f3_mask = (freqs >= 2600) & (freqs <= 3500)
            
            # Energy in each formant band per time frame
            f1_energy = np.sum(mag_spec[f1_mask, :], axis=0)
            f2_energy = np.sum(mag_spec[f2_mask, :], axis=0)
            f3_energy = np.sum(mag_spec[f3_mask, :], axis=0)
            total_energy = np.sum(mag_spec, axis=0)
            
            # Formant ratios (normalize by total energy)
            f1_ratio = f1_energy / (total_energy + 1e-10)
            f2_ratio = f2_energy / (total_energy + 1e-10)
            f3_ratio = f3_energy / (total_energy + 1e-10)
            
            # Key insight: Speech formants CHANGE over time as we speak
            # Music instruments are more static
            f1_variability = np.std(f1_ratio) if len(f1_ratio) > 1 else 0
            f2_variability = np.std(f2_ratio) if len(f2_ratio) > 1 else 0
            f3_variability = np.std(f3_ratio) if len(f3_ratio) > 1 else 0
            
            # ===== Spectral centroid per frame =====
            # Calculate centroid for each time frame separately
            centroid_per_frame = []
            for t in range(mag_spec.shape[1]):
                spec_frame = mag_spec[:, t]
                total = np.sum(spec_frame)
                if total > 1e-10:
                    centroid = np.sum(freqs * spec_frame) / total
                    centroid_per_frame.append(centroid)
            
            centroid_per_frame = np.array(centroid_per_frame)
            centroid_variability = np.std(centroid_per_frame) if len(centroid_per_frame) > 1 else 0
            
            if debug:
                print(f"  [VAD] f1_var={f1_variability:.4f}, f2_var={f2_variability:.4f}, f3_var={f3_variability:.4f}, centroid_var={centroid_variability:.1f}")
            
            # ===== Decision logic - detect formant patterns of speech =====
            # PERMISSIVE: NN already has high confidence (0.99), so VAD just needs weak indicators
            # Accept any reasonable speech indicator, reject only obvious non-speech
            
            # F1 variability indicator
            if f1_variability > 0.05:
                if debug:
                    print(f"  [VAD] Decision: ACCEPT (F1 variation)")
                return True
            
            # F2 variability indicator
            if f2_variability > 0.03:
                if debug:
                    print(f"  [VAD] Decision: ACCEPT (F2 variation)")
                return True
            
            # F3 variability indicator
            if f3_variability > 0.02:
                if debug:
                    print(f"  [VAD] Decision: ACCEPT (F3 variation)")
                return True
            
            # Centroid movement indicator (lower threshold)
            if centroid_variability > 200:
                if debug:
                    print(f"  [VAD] Decision: ACCEPT (spectral movement)")
                return True
            
            # Reject borderline cases
            if debug:
                print(f"  [VAD] Decision: REJECT (insufficient speech indicators)")
            return False
            
        except Exception as e:
            if debug:
                print(f"  [VAD] Error in speech detection: {e}")
            return True  # Default to speech on error
        
    # ==================== MFCC Feature Extraction ====================
    
    def extract_mfcc(self, audio, sample_rate):
        """
        Extract MFCC features from audio signal.
        
        MFCC (Mel-Frequency Cepstral Coefficients) captures the spectral
        characteristics of audio in a way that mimics human hearing.
        
        Args:
            audio (ndarray): Audio signal (1D array of samples).
            sample_rate (int): Sample rate of the audio in Hz.
            
        Returns:
            ndarray: MFCC feature matrix of shape (n_mfcc, time_steps).
                     None if extraction fails.
        """
        try:
            mfcc = librosa.feature.mfcc(
                y=audio, 
                sr=sample_rate, 
                n_mfcc=self.n_mfcc,
                n_fft=self.n_fft,
                hop_length=self.hop_length
            )
            return mfcc
        except Exception as e:
            print(f"Error extracting MFCC: {e}")
            return None
    
    # ==================== Distance Metrics ====================
    
    def chi_squared_distance(self, hist1, hist2):
        """
        Calculate chi-squared distance between two feature distributions.
        
        Improved version that accounts for temporal structure and energy differences
        to prevent false matches with noise/silence.
        
        Formula: sum((a-b)^2 / (a+b)) with temporal and energy penalties
        
        Args:
            hist1 (ndarray): Feature matrix (feature_dim, time_steps).
            hist2 (ndarray): Feature matrix (feature_dim, time_steps).
            
        Returns:
            float: Distance score. Lower = more similar.
                   Typical ranges:
                   - 25-35: Same word instances
                   - 50-80: Different words or noisy variants
                   - 150+: Silence, noise, or completely different
        """
        # Ensure same temporal length for proper comparison
        min_len = min(hist1.shape[1], hist2.shape[1])
        h1 = hist1[:, :min_len]
        h2 = hist2[:, :min_len]
        
        # Calculate energy (sum of all MFCC coefficients over time)
        energy1 = np.sum(np.abs(h1))
        energy2 = np.sum(np.abs(h2))
        
        # Penalize large energy differences (silence vs speech)
        energy_ratio = max(energy1, energy2 + 1e-10) / (min(energy1, energy2) + 1e-10)
        energy_penalty = max(0, (energy_ratio - 2.0) * 10)  # Penalty if ratio > 2
        
        # Chi-squared on time-averaged features
        avg1 = np.mean(h1, axis=1)
        avg2 = np.mean(h2, axis=1)
        
        # Normalize by energy to remove speech level variations
        if energy1 > 1e-10:
            avg1 = avg1 / (energy1 / hist1.shape[1])
        if energy2 > 1e-10:
            avg2 = avg2 / (energy2 / hist2.shape[1])
        
        # Clip to avoid division by zero
        avg1 = np.clip(avg1, 1e-10, None)
        avg2 = np.clip(avg2, 1e-10, None)
        
        # Chi-squared distance
        chi_dist = np.sum((avg1 - avg2) ** 2 / (avg1 + avg2 + 1e-10))
        
        # Add temporal variability check - compare frame-by-frame differences
        # High variability in one but not the other suggests false match (noise)
        var1 = np.mean(np.std(h1, axis=1))
        var2 = np.mean(np.std(h2, axis=1))
        var_ratio = max(var1, var2 + 1e-10) / (min(var1, var2) + 1e-10)
        
        # Penalty for large variance mismatches
        variance_penalty = max(0, (var_ratio - 3.0) * 5) if var_ratio > 3.0 else 0
        
        # Final distance with penalties
        distance = chi_dist + energy_penalty + variance_penalty
        
        return distance
    
    # ==================== Similarity Scoring ====================
    
    def feature_similarity(self, features1, features2, method="chi_squared", debug=False):
        """
        Calculate similarity score between two MFCC feature sets.
        
        Uses improved chi-squared distance with adaptive scaling to reduce false positives.
        
        Calibration (chi-squared method):
        - distance 25-35: similarity = 0.85-1.0 (same word, strong match)
        - distance 45-55: similarity = 0.50-0.70 (different words or noisy variants)
        - distance 80+: similarity < 0.30 (poor match, likely noise/silence)
        
        Args:
            features1 (ndarray): MFCC matrix (feature_dim, time_steps).
            features2 (ndarray): MFCC matrix (feature_dim, time_steps).
            method (str): Similarity method to use:
                - "chi_squared": Recommended. Improved chi-squared with penalties.
                - "cosine": Simple cosine similarity on mean features.
                - "correlation": Pearson correlation on standardized features.
            debug (bool): If True, print distance and similarity values.
            
        Returns:
            float: Similarity score in range [0.0, 1.0].
                   1.0 = identical, 0.0 = completely different.
        """
        if method == "chi_squared":
            distance = self.chi_squared_distance(features1, features2)
            
            if debug:
                print(f"  [chi_squared] raw_distance={distance:.2f}")
            
            # Use exponential decay based on distance
            # Small distances → high similarity, but with strict thresholds
            # This naturally creates discrimination between similar distances
            
            # Exponential mapping: similarity = exp(-k * distance)
            # k controls the steepness of the curve
            # Calibrated for observed chi-squared distances: 0.06-0.24 range
            # Distance 0.06 (best match) → similarity 0.55 (passes 0.5 threshold)
            # Distance 0.15 → similarity 0.22 (fails threshold, discriminates noise)
            k = 10.0  # Steepness factor - calibrated for chi-squared distance scale
            
            similarity = np.exp(-k * distance)
            
            if debug:
                print(f"  [chi_squared] similarity={similarity:.4f}")
            
            return np.clip(similarity, 0.0, 1.0)
        
        elif method == "cosine":
            # Cosine similarity on mean feature vectors
            mean1 = np.mean(features1, axis=1)
            mean2 = np.mean(features2, axis=1)
            
            norm1 = np.linalg.norm(mean1)
            norm2 = np.linalg.norm(mean2)
            
            if norm1 == 0 or norm2 == 0:
                return 0.0
            
            similarity = np.dot(mean1, mean2) / (norm1 * norm2)
            
            if debug:
                print(f"  [cosine] similarity={similarity:.4f}")
            
            return np.clip(similarity, 0.0, 1.0)
        
        else:  # correlation
            # Pearson correlation (warning: too lenient, kept for reference)
            mean1 = np.mean(features1, axis=1)
            mean2 = np.mean(features2, axis=1)
            
            mean1_std = (mean1 - np.mean(mean1)) / (np.std(mean1) + 1e-10)
            mean2_std = (mean2 - np.mean(mean2)) / (np.std(mean2) + 1e-10)
            
            correlation = np.dot(mean1_std, mean2_std) / (len(mean1_std) + 1e-10)
            similarity = (correlation + 1.0) / 2.0
            
            if debug:
                print(f"  [correlation] similarity={similarity:.4f}")
            
            return np.clip(similarity, 0.0, 1.0)
    
    # ==================== Template Management ====================
    
    def add_template(self, audio, label="wake_word", sample_rate=None):
        """
        Add audio as a reference template for matching.
        
        Args:
            audio (ndarray): Audio signal (1D array).
            label (str): Label for this template (e.g., "wakeword_0").
            sample_rate (int): Sample rate of audio. Uses default if None.
        """
        if sample_rate is None:
            sample_rate = self.sample_rate
            
        mfcc = self.extract_mfcc(audio, sample_rate)
        if mfcc is not None:
            self.templates.append(mfcc)
            self.template_labels.append(label)
            print(f"Template added: {label} (shape: {mfcc.shape})")
    
    def load_template_from_file(self, audio_file_path, label=None):
        """
        Load audio file and add as template.
        
        Supports common audio formats: WAV, MP3, OGG, FLAC.
        
        Args:
            audio_file_path (str): Path to audio file.
            label (str): Label for template. Default: filename.
            
        Returns:
            bool: True if loaded successfully, False otherwise.
        """
        try:
            if not os.path.exists(audio_file_path):
                print(f"File not found: {audio_file_path}")
                return False
            
            # Load audio using librosa
            audio, sr = librosa.load(audio_file_path, sr=self.sample_rate)
            
            if label is None:
                label = os.path.basename(audio_file_path)
            
            self.add_template(audio, label, sample_rate=sr)
            return True
        except Exception as e:
            print(f"Error loading {audio_file_path}: {e}")
            return False
    
    def load_templates_from_directory(self, directory_path):
        """
        Load all audio files from directory as templates.
        
        Recursively loads all supported audio formats from the directory.
        Supported: WAV, MP3, OGG, FLAC.
        
        Args:
            directory_path (str): Path to directory with audio files.
            
        Returns:
            int: Number of templates successfully loaded.
        """
        if not os.path.isdir(directory_path):
            print(f"Directory not found: {directory_path}")
            return 0
        
        loaded = 0
        for filename in sorted(os.listdir(directory_path)):
            if filename.endswith(('.wav', '.mp3', '.ogg', '.flac')):
                file_path = os.path.join(directory_path, filename)
                if self.load_template_from_file(file_path):
                    loaded += 1
        
        print(f"Loaded {loaded} templates from {directory_path}")
        return loaded
    
    # ==================== Matching Functions ====================
    
    def match_direct(self, audio, match_threshold=0.85, sample_rate=22050, 
                    method="chi_squared", debug=False):
        """
        Match audio directly against all templates.
        
        Extracts MFCC features from input audio and compares to all stored
        templates using the specified similarity method.
        
        Typical usage in two-stage system:
        - Call from wake_word_detector after model confidence check
        - Pass match_threshold=0.85 for strict verification
        
        Args:
            audio (ndarray): Audio signal to match (1D array).
            match_threshold (float): Minimum similarity for positive match.
                Default 0.75 (requires distance ~45 or less).
            sample_rate (int): Sample rate of audio.
            method (str): Similarity method ("chi_squared", "cosine", "correlation").
            debug (bool): If True, print per-template match details.
            
        Returns:
            tuple: (matched, best_score, best_label)
                - matched (bool): True if best_score >= match_threshold
                - best_score (float): Highest similarity found (0-1)
                - best_label (str): Label of best-matching template
                                   or error string if no match
        """
        if not self.templates:
            return False, 0.0, "no_templates"
        
        # Extract features from input audio
        mfcc = self.extract_mfcc(audio, sample_rate)
        if mfcc is None:
            return False, 0.0, "feature_extraction_failed"
        
        best_score = 0.0
        best_label = None
        matched = False
        
        # Compare against all templates
        for template, label in zip(self.templates, self.template_labels):
            score = self.feature_similarity(mfcc, template, method=method, debug=debug)
            
            if score > best_score:
                best_score = score
                best_label = label
            
            if score >= match_threshold:
                matched = True
        
        return matched, best_score, best_label
    
    def match_audio_window(self, audio_window, sample_rate=22050, match_threshold=0.85, 
                          method="chi_squared", debug=False):
        """
        Match a pre-recorded audio window directly against all templates.
        
        Optimized for use with sliding window audio buffers from wake_word_manager.
        Does NOT perform sliding window - expects audio to already be windowed.
        
        Use this when you have a 2-second audio buffer ready to match immediately.
        
        Args:
            audio_window (ndarray): Pre-recorded audio window (already extracted).
                Should be around 2 seconds of audio at 22050 Hz (~44,100 samples).
            sample_rate (int): Sample rate of the audio window.
            match_threshold (float): Minimum similarity for positive match.
                Default 0.75 (chi_squared distance ~45 or less).
            method (str): Similarity method ("chi_squared", "cosine", "correlation").
            debug (bool): If True, print per-template match details.
            
        Returns:
            tuple: (matched, best_score, best_label, all_scores)
                - matched (bool): True if best_score >= match_threshold
                - best_score (float): Highest similarity found (0-1)
                - best_label (str): Label of best-matching template
                - all_scores (list): List of (label, score) tuples for all templates
        """
        if not self.templates:
            return False, 0.0, "no_templates", []
        
        # Extract features from the audio window
        mfcc = self.extract_mfcc(audio_window, sample_rate)
        if mfcc is None:
            return False, 0.0, "feature_extraction_failed", []
        
        best_score = 0.0
        best_label = None
        matched = False
        all_scores = []
        
        # Compare against all templates
        for template, label in zip(self.templates, self.template_labels):
            score = self.feature_similarity(mfcc, template, method=method, debug=debug)
            all_scores.append((label, score))
            
            if debug:
                print(f"  {label}: {score:.4f}")
            
            if score > best_score:
                best_score = score
                best_label = label
            
            if score >= match_threshold:
                matched = True
        
        # Sanity check: Real wake words show VARIATION in scores
        # Silence/noise shows all templates matching with nearly identical high scores
        # Calculate standard deviation of all scores
        if all_scores:
            scores_only = np.array([score for _, score in all_scores])
            score_std = np.std(scores_only)
            score_mean = np.mean(scores_only)
            
            if debug:
                print(f"  [VARIANCE] mean={score_mean:.4f}, std={score_std:.4f}")
            
            # If all scores are very similar (low std) and very high (mean > 0.90),
            # it's likely silence/noise, not a real wake word
            if score_std < 0.05 and score_mean > 0.88:
                if debug:
                    print(f"  [SANITY CHECK] Rejecting: All templates match too uniformly (std={score_std:.4f}, mean={score_mean:.4f})")
                return False, best_score, best_label, all_scores
        
        return matched, best_score, best_label, all_scores
    
    def match_with_sliding_window(self, audio, match_threshold=0.80, 
                                 window_duration=2.0, step_duration=0.2, 
                                 sample_rate=22050):
        """
        Match audio using sliding window to find best-matching portion.
        
        Useful when audio contains wake word mixed with other speech.
        Slides a window across the audio and returns the best-matching section.
        
        Args:
            audio (ndarray): Audio signal to match.
            match_threshold (float): Minimum similarity for positive match.
            window_duration (float): Window length in seconds.
            step_duration (float): How far to move window per step (seconds).
            sample_rate (int): Sample rate of audio.
            
        Returns:
            dict: Results dictionary with keys:
                - 'matched' (bool): Whether best_score >= match_threshold
                - 'best_score' (float): Highest similarity found
                - 'best_label' (str): Label of best-matching template
                - 'best_position' (float): Position of best match in seconds
                - 'all_scores' (list): All (position, label, score) tuples
        """
        if not self.templates:
            return {
                'matched': False, 
                'best_score': 0.0, 
                'best_label': 'no_templates',
                'best_position': 0.0, 
                'all_scores': []
            }
        
        window_samples = int(window_duration * sample_rate)
        step_samples = int(step_duration * sample_rate)
        
        best_score = 0.0
        best_label = None
        best_position = 0.0
        all_scores = []
        
        # Slide window across audio
        for start in range(0, len(audio) - window_samples + 1, step_samples):
            end = start + window_samples
            window_audio = audio[start:end]
            
            # Extract features from this window
            mfcc = self.extract_mfcc(window_audio, sample_rate)
            if mfcc is None:
                continue
            
            # Match against all templates
            for template, label in zip(self.templates, self.template_labels):
                # Use direct chi-squared matching for sliding window
                score = self.feature_similarity(mfcc, template, method="chi_squared")
                position = start / sample_rate
                
                if score > best_score:
                    best_score = score
                    best_label = label
                    best_position = position
                
                all_scores.append((position, label, score))
        
        matched = best_score >= match_threshold
        
        return {
            'matched': matched,
            'best_score': best_score,
            'best_label': best_label,
            'best_position': best_position,
            'all_scores': all_scores
        }
    
    # ==================== Audio Recording ====================
    
    def record_audio(self, duration=2.0, sample_rate=22050, device=None):
        """
        Record audio from microphone for specified duration.
        
        Uses sounddevice for low-latency recording. Blocks until
        recording completes.
        
        Args:
            duration (float): Recording duration in seconds.
            sample_rate (int): Sample rate for recording.
            device (int): Audio device index. None = default device.
            
        Returns:
            ndarray: Recorded audio (1D array of samples).
                     None if recording fails.
        """
        try:
            print(f"Recording {duration} seconds...")
            audio = sd.rec(
                int(duration * sample_rate), 
                samplerate=sample_rate, 
                channels=1, 
                device=device
            )
            sd.wait()  # Wait for recording to finish
            audio = audio.flatten()  # Convert to 1D array
            print("Recording complete!")
            return audio
        except Exception as e:
            print(f"Error recording audio: {e}")
            return None
    
    # ==================== Analysis & Debugging ====================
    
    def analyze_templates(self):
        """
        Analyze loaded templates to check for data quality issues.
        
        Computes chi-squared distances between all template pairs
        to assess whether templates are diverse enough.
        
        Useful for debugging if all detection scores are too high
        (indicates insufficient template diversity).
        """
        if len(self.templates) < 2:
            print("Need at least 2 templates to analyze")
            return
        
        print("\n" + "="*70)
        print("TEMPLATE QUALITY ANALYSIS")
        print("="*70)
        
        # Compute distances between all template pairs
        distances = []
        print(f"\nChi-Squared distances between templates:")
        print("-" * 70)
        print(f"{'Template 1':<25} {'Template 2':<25} {'Distance':<15}")
        print("-" * 70)
        
        for i, (t1, l1) in enumerate(zip(self.templates, self.template_labels)):
            for j, (t2, l2) in enumerate(zip(self.templates, self.template_labels)):
                if i < j:
                    dist = self.chi_squared_distance(t1, t2)
                    distances.append(dist)
                    
                    # Estimate similarity from distance
                    sim = 1.0 / (1.0 + max(0, (dist - 30.0) / 25.0))
                    sim = np.clip(sim, 0.0, 1.0)
                    
                    print(f"{l1[:24]:<25} {l2[:24]:<25} {dist:>8.2f} (sim: {sim:.4f})")
        
        if distances:
            print("-" * 70)
            print(f"\nStatistics:")
            print(f"   Min distance: {min(distances):.2f}")
            print(f"   Max distance: {max(distances):.2f}")
            print(f"   Avg distance: {np.mean(distances):.2f}")
            print(f"   Std deviation: {np.std(distances):.2f}")
            
            # Check for problematic data
            if min(distances) < 35.0:
                print("\nWARNING: Some templates are VERY similar!")
                print("   This suggests:")
                print("   - Duplicate or near-duplicate recordings")
                print("   - Templates from same speaker/environment")
                print("   Solution: Use diverse training data:")
                print("      - Different speakers")
                print("      - Different microphones")
                print("      - Different background noise levels")
            elif min(distances) < 50.0:
                print("\nTemplates show reasonable diversity")
            else:
                print("\nExcellent: Templates are well-separated")
        
        print("\n" + "="*70)
