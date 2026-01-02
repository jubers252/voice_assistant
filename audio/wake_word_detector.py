
import librosa
import numpy as np
from keras.models import load_model



# Function to extract MFCC features (from test_cnn_model.py)
class WakeWordDetector:
    def __init__(self, model_path, sample_rate=22050, n_mfcc=40, n_fft=2048, hop_length=512):
        self.model = load_model(model_path)
        self.sample_rate = sample_rate
        self.n_mfcc = n_mfcc    
        self.n_fft = n_fft
        self.hop_length = hop_length
        
        # Stereo configuration
        self.desired_length = 44
        self.feature_dim = 120  # 40 MFCC + 40 delta + 40 delta2
        self.channels = 2  # Stereo
        self.optimal_threshold = 0.679  # Updated from training results - much better separation!
        
        # Warmup: Run a dummy prediction to initialize model layers
        print("Warming up wake word detector...")
        self._warmup_model()
        print("Wake word detector ready!")
    
    def _warmup_model(self):
        """Run a dummy prediction to initialize the model and avoid first-time delay"""
        try:
            # Create dummy stereo audio (2 seconds of silence)
            dummy_audio = np.zeros((2, int(self.sample_rate * 2.0)))  # Stereo: (2, samples)
            
            # Extract features from dummy audio
            features = self.extract_features(dummy_audio, self.sample_rate)
            
            if features is not None:
                # Reshape to model input: (1, time_steps, features*channels)
                features = features.reshape(1, self.desired_length, self.feature_dim * self.channels)
                _ = self.model.predict(features, verbose=0)
                print(f"Wake word detector warmed up - expecting stereo input shape: (2, samples)")
                
        except Exception as e:
            print(f"Warmup warning: {e}")
            # Continue even if warmup fails

    def extract_features(self, audio, sample_rate):
        """Extract MFCC features from stereo audio (one set per channel)"""
        try:
            # Handle stereo audio - process each channel separately
            if audio.ndim == 1:
                audio = np.array([audio, audio])  # Duplicate mono to stereo
            
            all_channel_features = []
            
            for channel_idx in range(audio.shape[0]):
                channel_audio = audio[channel_idx]
                
                # Normalize audio first (MUST match training)
                channel_audio = channel_audio / (np.max(np.abs(channel_audio)) + 1e-8)
                
                # Extract MFCC features
                mfcc = librosa.feature.mfcc(y=channel_audio, sr=sample_rate, n_mfcc=self.n_mfcc, 
                                           hop_length=self.hop_length, n_fft=self.n_fft)
                
                # Add delta features (first and second derivatives)
                delta_mfcc = librosa.feature.delta(mfcc)
                delta2_mfcc = librosa.feature.delta(mfcc, order=2)
                
                # Combine features for this channel
                channel_features = np.vstack([mfcc, delta_mfcc, delta2_mfcc])  # Shape: (120, time)
                
                # Pad or truncate to desired length
                if channel_features.shape[1] < self.desired_length:
                    pad_width = self.desired_length - channel_features.shape[1]
                    channel_features = np.pad(channel_features, ((0,0),(0,pad_width)), mode='constant')
                else:
                    channel_features = channel_features[:, :self.desired_length]
                
                all_channel_features.append(channel_features.T)  # Shape: (desired_length, 120)
            
            # Stack both channels and flatten for model input
            # Shape (desired_length, 120, 2) -> flatten to (desired_length, 240)
            stereo_features = np.stack(all_channel_features, axis=2)  # (desired_length, 120, 2)
            stereo_features = stereo_features.reshape(self.desired_length, self.feature_dim * self.channels)
            
            return stereo_features
        except Exception as e:
            print(f"Error extracting features: {e}")
            return None

    def detect_wakeword(self, audio_window, sample_rate, energy_threshold=0.001, confidence_threshold=None):
        """Return True if wake word is detected in the given audio window."""
        # Use optimal threshold from training if not specified
        if confidence_threshold is None:
            confidence_threshold = self.optimal_threshold
            
        energy = np.sqrt(np.mean(audio_window ** 2))
        if energy < energy_threshold:
            return False, energy, None
            
        features = self.extract_features(audio_window, sample_rate)
        
        if features is None:
            return False, energy, None
            
        # Reshape for model: (1, time_steps, features*channels)
        features = features.reshape(1, self.desired_length, self.feature_dim * self.channels)
        prediction = self.model.predict(features, verbose=0)[0][0]
        
        return prediction > confidence_threshold, energy, prediction
        
  