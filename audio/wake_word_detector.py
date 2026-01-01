
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
        
        # Warmup: Run a dummy prediction to initialize model layers
        print("Warming up wake word detector...")
        self._warmup_model()
        print("Wake word detector ready!")
    
    def _warmup_model(self):
        """Run a dummy prediction to initialize the model and avoid first-time delay"""
        try:
            # Create dummy audio (2 seconds of silence)
            dummy_audio = np.zeros(int(self.sample_rate * 2.0))
            
            # Extract features from dummy audio
            features = self.extract_features(dummy_audio, self.sample_rate)
            
            if features is not None:
                # Pad/trim to desired length
                desired_length = 44
                if features.shape[0] < desired_length:
                    features = np.pad(features, ((0, desired_length - features.shape[0]), (0, 0)), mode='constant')
                else:
                    features = features[:desired_length]
                
                # Reshape and run prediction
                features = features.reshape(1, desired_length, 120)
                _ = self.model.predict(features, verbose=0)
                
        except Exception as e:
            print(f"Warmup warning: {e}")
            # Continue even if warmup fails

    def extract_features(self, audio, sample_rate):
        try:
            mfcc = librosa.feature.mfcc(y=audio, sr=sample_rate, n_mfcc=self.n_mfcc, n_fft=self.n_fft, hop_length=self.hop_length)
            mfcc_delta = librosa.feature.delta(mfcc)
            mfcc_delta2 = librosa.feature.delta(mfcc, order=2)
            features = np.concatenate((mfcc, mfcc_delta, mfcc_delta2), axis=0)
            features = features.T  # Transpose to (time_steps, features)
            return features
        except Exception as e:
            print(f"Error extracting features: {e}")
            return None

    def detect_wakeword(self, audio_window, sample_rate, energy_threshold=0.0001, confidence_threshold=0.95):
        """Return True if wake word is detected in the given audio window."""
        energy = np.sqrt(np.mean(audio_window ** 2))
        if energy < energy_threshold:
            return False, energy, None
        features = self.extract_features(audio_window, sample_rate)
        desired_length = 44
        if features is None:
            return False, energy, None
        if features.shape[0] < desired_length:
            features = np.pad(features, ((0, desired_length - features.shape[0]), (0, 0)), mode='constant')
        else:
            features = features[:desired_length]
        features = features.reshape(1, desired_length, 120)
        prediction = self.model.predict(features, verbose=0)[0][0]
        return prediction > confidence_threshold, energy, prediction
        
  