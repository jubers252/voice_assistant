###### IMPORTS ################
import os
import librosa
import librosa.display
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler
import warnings
warnings.filterwarnings('ignore')

def augment_audio(audio, sr):
    """No data augmentation - return only the original audio"""
    # Ensure stereo format
    if audio.ndim == 1:
        audio = np.array([audio, audio])  # Convert mono to stereo
    return [audio]

def load_audio_file(filepath, sr=22050, duration=1.0):
    """Load audio file keeping stereo channels"""
    audio, sr_loaded = librosa.load(filepath, sr=sr, duration=duration, mono=False)
    # Ensure we have stereo (2 channels)
    if audio.ndim == 1:
        # If mono, duplicate to stereo
        audio = np.vstack([audio, audio])
    return audio, sr_loaded

def extract_features(audio, sr, n_mfcc=40, desired_length=44):
    """Extract MFCC features from stereo audio (one set per channel)"""
    # Handle stereo audio - process each channel separately
    if audio.ndim == 1:
        audio = np.array([audio, audio])  # Duplicate mono to stereo
    
    all_channel_features = []
    
    for channel_idx in range(audio.shape[0]):
        channel_audio = audio[channel_idx]
        
        # Normalize audio first
        channel_audio = channel_audio / (np.max(np.abs(channel_audio)) + 1e-8)
        
        # Extract MFCC features
        mfcc = librosa.feature.mfcc(y=channel_audio, sr=sr, n_mfcc=n_mfcc, 
                                   hop_length=512, n_fft=2048)
        
        # Add delta features (first and second derivatives)
        delta_mfcc = librosa.feature.delta(mfcc)
        delta2_mfcc = librosa.feature.delta(mfcc, order=2)
        
        # Combine features for this channel
        channel_features = np.vstack([mfcc, delta_mfcc, delta2_mfcc])  # Shape: (120, time)
        
        # Pad or truncate to desired length
        if channel_features.shape[1] < desired_length:
            pad_width = desired_length - channel_features.shape[1]
            channel_features = np.pad(channel_features, ((0,0),(0,pad_width)), mode='constant')
        else:
            channel_features = channel_features[:, :desired_length]
        
        all_channel_features.append(channel_features.T)  # Shape: (desired_length, 120)
    
    # Stack both channels: Shape (desired_length, 120, 2)
    stereo_features = np.stack(all_channel_features, axis=2)
    return stereo_features

#### LOADING THE VOICE DATA FOR VISUALIZATION ###
walley_sample = "model_training/background_sound/1.wav"
data, sample_rate = librosa.load(walley_sample)

##### VISUALIZING WAVE FORM ##
plt.title("Wave Form")
librosa.display.waveshow(data, sr=sample_rate)
plt.show()

##### VISUALIZING MFCC #######
mfccs = librosa.feature.mfcc(y=data, sr=sample_rate, n_mfcc=40)
print("Shape of mfcc:", mfccs.shape)

plt.title("MFCC")
librosa.display.specshow(mfccs, sr=sample_rate, x_axis='time')
plt.show()

##### Doing this for every sample with improved preprocessing (STEREO) ##

all_data = []
desired_length = 44  # Number of time frames for 1 second @ 22050 Hz
feature_dim = 120  # 40 MFCC + 40 delta + 40 delta2
channels = 2  # Stereo: 2 channels

data_path_dict = {
    0: ["model_training/background_sound/" + file_path for file_path in os.listdir("model_training/background_sound/") if file_path.endswith('.wav')],
    1: ["model_training/audio_data/" + file_path for file_path in os.listdir("model_training/audio_data/") if file_path.endswith('.wav')]
}

print(f"Background samples: {len(data_path_dict[0])}")
print(f"Wake word samples: {len(data_path_dict[1])}")

# the background_sound/ directory has all sounds which DOES NOT CONTAIN wake word
# the audio_data/ directory has all sound WHICH HAS Wake word

for class_label, list_of_files in data_path_dict.items():
    for single_file in list_of_files:
        try:
            # Load audio file (keeps stereo) - 1 second @ 22050 Hz
            audio, sample_rate = load_audio_file(single_file, sr=22050, duration=1.0)
            # Skip very short audio files
            num_samples = audio.shape[-1] if audio.ndim > 1 else len(audio)
            if num_samples < 1000:
                continue
                
            for aug_audio in augment_audio(audio, sample_rate):
                features = extract_features(aug_audio, sample_rate, desired_length=desired_length)
                all_data.append([features, class_label])
        except Exception as e:
            print(f"Error processing {single_file}: {e}")
            continue
    print(f"Info: Successfully Preprocessed Class Label {class_label} - {len([d for d in all_data if d[1] == class_label])} samples")

# Convert to DataFrame
df = pd.DataFrame(all_data, columns=["feature", "class_label"])

# Normalize features
print("Normalizing features...")
if len(df) == 0:
    print("ERROR: No features were extracted! Check audio files and paths.")
else:
    all_features = np.stack(df["feature"].values)  # Shape: (num_samples, desired_length, feature_dim, channels)
    print(f"Features shape: {all_features.shape}")
    scaler = StandardScaler()
    normalized_features = []

    for i in range(all_features.shape[0]):
        # Normalize each sample while preserving stereo structure
        sample_features = all_features[i]  # Shape: (44, 120, 2)
        
        # Normalize across features but keep stereo separation
        normalized_sample = scaler.fit_transform(sample_features.reshape(-1, 1)).reshape(sample_features.shape)
        normalized_features.append(normalized_sample)

    df["feature"] = normalized_features

    ###### SAVING FOR FUTURE USE ###
    print(f"Total samples: {len(df)}")
    print(f"Class distribution:\n{df['class_label'].value_counts()}")
    df.to_pickle("model_training/final_audio_data_csv/audio_data_cnn_improved.pkl")
    print("Improved preprocessing data saved!")
