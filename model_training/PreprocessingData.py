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
    # No data augmentation - return only the original audio
    return [audio]

def extract_features(audio, sr, n_mfcc=40, desired_length=44):
    """Extract MFCC features with better preprocessing"""
    # Normalize audio first
    audio = audio / np.max(np.abs(audio) + 1e-8)
    
    # Extract MFCC features
    mfcc = librosa.feature.mfcc(y=audio, sr=sr, n_mfcc=n_mfcc, 
                               hop_length=512, n_fft=2048)
    
    # Add delta features (first and second derivatives)
    delta_mfcc = librosa.feature.delta(mfcc)
    delta2_mfcc = librosa.feature.delta(mfcc, order=2)
    
    # Combine features
    features = np.vstack([mfcc, delta_mfcc, delta2_mfcc])  # Shape: (120, time)
    
    # Pad or truncate to desired length
    if features.shape[1] < desired_length:
        pad_width = desired_length - features.shape[1]
        features = np.pad(features, ((0,0),(0,pad_width)), mode='constant')
    else:
        features = features[:, :desired_length]
    
    return features.T  # Shape: (desired_length, 120)

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

##### Doing this for every sample with improved preprocessing ##

all_data = []
desired_length = 44  # Number of time frames for each sample
feature_dim = 120  # 40 MFCC + 40 delta + 40 delta2

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
            audio, sample_rate = librosa.load(single_file, duration=1.0, sr=22050)
            # Skip very short audio files
            if len(audio) < 1000:
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
all_features = np.stack(df["feature"].values)
scaler = StandardScaler()
normalized_features = []

for i in range(all_features.shape[0]):
    # Flatten, normalize, then reshape
    flat_features = all_features[i].flatten()
    normalized_flat = scaler.fit_transform(flat_features.reshape(-1, 1)).flatten()
    normalized_features.append(normalized_flat.reshape(desired_length, feature_dim))

df["feature"] = normalized_features

###### SAVING FOR FUTURE USE ###
print(f"Total samples: {len(df)}")
print(f"Class distribution:\n{df['class_label'].value_counts()}")

# Create directory if it doesn't exist
output_dir = "model_training/final_audio_data_csv"
os.makedirs(output_dir, exist_ok=True)

df.to_pickle(os.path.join(output_dir, "audio_data_cnn_improved.pkl"))
print("Improved preprocessing data saved!")
