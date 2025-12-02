#### Wake Word Detection Model Training (Beginner Friendly)
# This script trains a simple 1D CNN to detect a wake word using MFCC features.
# You do NOT need deep learning expertise to use or modify this script.
# Just run it and check the printed accuracy and classification report!

####### IMPORTS #############
import os
import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from keras.utils import to_categorical
from keras.models import Sequential
from keras.layers import Conv1D, MaxPooling1D, Flatten, Dense, Dropout
from keras.callbacks import EarlyStopping
from sklearn.metrics import confusion_matrix, classification_report
from plot_cm import plot_confusion_matrix
import librosa
import tensorflow as tf
import tensorflow_hub as hub
import tensorflow_io as tfio
import glob
##### 1. Load Preprocessed Data (MFCC features) #####
# This file is created by your PreprocessingData.py script
# Each sample is a matrix: (time_steps, 120 features - MFCC + deltas)
df = pd.read_pickle(os.path.join("model_training", "final_audio_data_csv", "audio_data_cnn_improved.pkl"))

##### 2. Prepare Data for Training #####
X = np.stack(df["feature"].values)  # shape: (samples, time_steps, 120)
X = X.astype(np.float32)
desired_length = X.shape[1]  # Number of time steps
feature_dim = X.shape[2]     # Number of features (120)

print(f"Data shape: {X.shape}")
print(f"Feature dimension: {feature_dim}")

# Update labels to use binary format (0 or 1)
y = np.array(df["class_label"].tolist())  # Binary labels (0 or 1)
print(f"Class distribution: {np.bincount(y)}")

# Split into training and test sets (70% train, 15% validation, 15% test)
X_train, X_temp, y_train, y_temp = train_test_split(X, y, test_size=0.3, random_state=42, stratify=y)
X_val, X_test, y_val, y_test = train_test_split(X_temp, y_temp, test_size=0.5, random_state=42, stratify=y_temp)

##### 3. Build a More Conservative Model to Prevent Overfitting #####
from keras.layers import BatchNormalization, GlobalAveragePooling1D
from keras.regularizers import l2

# Smaller, more conservative model to prevent overfitting
model = Sequential([
    # First Conv Block - Reduced filters
    Conv1D(16, kernel_size=5, activation='relu', input_shape=(desired_length, feature_dim), 
           kernel_regularizer=l2(0.05)),  # Stronger L2 regularization
    BatchNormalization(),
    MaxPooling1D(3),  # Larger pooling to reduce overfitting
    Dropout(0.6),  # Higher dropout

    # Second Conv Block - Smaller
    Conv1D(32, kernel_size=3, activation='relu', kernel_regularizer=l2(0.05)),
    BatchNormalization(),
    GlobalAveragePooling1D(),  # Instead of MaxPooling + Flatten
    Dropout(0.7),  # Very high dropout

    # Smaller Dense layer
    Dense(32, activation='relu', kernel_regularizer=l2(0.05)),  # Reduced from 64 to 32
    Dropout(0.6),
    Dense(1, activation='sigmoid')  # Binary classification
])

print(model.summary())  # Shows model structure

##### 4. Compile with Conservative Settings to Prevent Overfitting #####
from keras.optimizers import Adam

model.compile(
    loss="binary_crossentropy",  # Binary classification loss
    optimizer=Adam(learning_rate=0.0005),  # Even lower learning rate
    metrics=['accuracy', 'precision', 'recall']  # Track multiple metrics
)

# More aggressive callbacks to prevent overfitting
from keras.callbacks import ReduceLROnPlateau, ModelCheckpoint

early_stop = EarlyStopping(monitor='val_loss', patience=5, restore_best_weights=True, verbose=1)  # Reduced patience
reduce_lr = ReduceLROnPlateau(monitor='val_loss', factor=0.2, patience=3, verbose=1, min_lr=1e-6)  # More aggressive LR reduction
checkpoint = ModelCheckpoint(os.path.join("model_training", "saved_model", "best_model.keras"), 
                           monitor='val_loss', save_best_only=True, verbose=1)

##### 5. Train with Strong Overfitting Prevention #####
print("Training Conservative Model to Prevent Overfitting: \n")

# Add data augmentation to prevent overfitting
from keras.utils import Sequence
import random

class AudioAugmentationGenerator(Sequence):
    def __init__(self, X, y, batch_size=32, augment=True):
        self.X, self.y = X, y
        self.batch_size = batch_size
        self.augment = augment
        self.indexes = np.arange(len(self.X))
        
    def __len__(self):
        return len(self.X) // self.batch_size
    
    def __getitem__(self, index):
        batch_indexes = self.indexes[index * self.batch_size:(index + 1) * self.batch_size]
        X_batch = self.X[batch_indexes].copy()
        y_batch = self.y[batch_indexes]
        
        if self.augment:
            # Add noise to prevent overfitting
            for i in range(len(X_batch)):
                if random.random() < 0.5:  # 50% chance of augmentation
                    noise = np.random.normal(0, 0.01, X_batch[i].shape)
                    X_batch[i] += noise
        
        return X_batch, y_batch
    
    def on_epoch_end(self):
        np.random.shuffle(self.indexes)

# Create generators
train_gen = AudioAugmentationGenerator(X_train, y_train, batch_size=32, augment=True)
val_gen = AudioAugmentationGenerator(X_val, y_val, batch_size=32, augment=False)

history = model.fit(
    train_gen,
    epochs=30,  # Reduced epochs to prevent overfitting
    validation_data=val_gen,
    callbacks=[early_stop, reduce_lr, checkpoint],
    verbose=1
)

# Load the best model
model.load_weights(os.path.join("model_training", "saved_model", "best_model.keras"))

# Save the final model
model.save(os.path.join("model_training", "saved_model", "WWD_mems_updated.h5"))

# Evaluate on test set
print("\n=== Final Model Evaluation ===")
test_scores = model.evaluate(X_test, y_test, verbose=0)
print(f"Test Loss: {test_scores[0]:.4f}")
print(f"Test Accuracy: {test_scores[1]:.4f}")
print(f"Test Precision: {test_scores[2]:.4f}")
print(f"Test Recall: {test_scores[3]:.4f}")

##### 6. Enhanced Model Analysis #####
print("\n=== Detailed Classification Report ===")
y_pred = model.predict(X_test, verbose=0)
y_pred_classes = (y_pred > 0.5).astype(int)  # Threshold at 0.5 for binary classification

# Use binary labels directly for y_true_classes
y_true_classes = y_test  # Binary labels (0 or 1)

cm = confusion_matrix(y_true_classes, y_pred_classes)
print(classification_report(y_true_classes, y_pred_classes, 
                          target_names=["Background", "Wake Word"]))

# Show prediction confidence distribution
print("\n=== Prediction Confidence Analysis ===")
wake_word_confidences = y_pred[y_true_classes == 1]  # Wake word predictions
background_confidences = y_pred[y_true_classes == 0]  # Background predictions

print(f"Wake word samples - Mean confidence: {np.mean(wake_word_confidences):.3f}, Std: {np.std(wake_word_confidences):.3f}")
print(f"Background samples - Mean confidence: {np.mean(background_confidences):.3f}, Std: {np.std(background_confidences):.3f}")

# Suggest conservative threshold to reduce false positives
from sklearn.metrics import roc_curve, auc
fpr, tpr, thresholds = roc_curve(y_true_classes, y_pred)

# Find threshold that gives 95% precision (reduces false positives)
from sklearn.metrics import precision_recall_curve
precision, recall, pr_thresholds = precision_recall_curve(y_true_classes, y_pred)
conservative_idx = np.where(precision >= 0.95)[0]
if len(conservative_idx) > 0:
    conservative_threshold = pr_thresholds[conservative_idx[0]]
else:
    conservative_threshold = 0.8  # Fallback high threshold

optimal_idx = np.argmax(tpr - fpr)
optimal_threshold = thresholds[optimal_idx]

print(f"Balanced threshold: {optimal_threshold:.3f}")
print(f"Conservative threshold (95% precision): {conservative_threshold:.3f}")
print("Recommendation: Use conservative threshold to reduce false positives")

plot_confusion_matrix(cm, classes=["Background", "Wake Word"])

print("\n=== Model Training Complete ===")
print("Improved model saved as 'WWD_improved.h5'")
print("Use this model with the suggested threshold for better performance!")

# --- End of script ---

# YAMNet Wake Word Detection Pipeline

# Load YAMNet model from TensorFlow Hub
yamnet_model = hub.load('https://tfhub.dev/google/yamnet/1')

# Function to preprocess audio
def preprocess_audio(file_path):
    audio_tensor, sample_rate = librosa.load(file_path, sr=16000)
    return audio_tensor, sample_rate

# Function to extract embeddings using YAMNet
def extract_embeddings(audio_tensor, sample_rate):
    audio_tensor = tf.constant(audio_tensor, dtype=tf.float32)
    scores, embeddings, spectrogram = yamnet_model(audio_tensor)
    # Average embeddings over time to get a single vector per audio clip
    mean_embedding = tf.reduce_mean(embeddings, axis=0)
    return mean_embedding

# Example pipeline for fine-tuning
def fine_tune_yamnet(wakeword_data, background_data):
    # Prepare dataset
    X = []
    y = []

    for audio_path in wakeword_data:
        audio_tensor, sample_rate = preprocess_audio(audio_path)
        embedding = extract_embeddings(audio_tensor, sample_rate)
        X.append(embedding.numpy())
        y.append(1)  # Label for wake word

    for audio_path in background_data:
        audio_tensor, sample_rate = preprocess_audio(audio_path)
        embedding = extract_embeddings(audio_tensor, sample_rate)
        X.append(embedding.numpy())
        y.append(0)  # Label for background noise

    X = np.array(X)
    y = np.array(y)

    # Define a simple classifier
    model = tf.keras.Sequential([
        tf.keras.layers.Input(shape=(X.shape[1],)),
        tf.keras.layers.Dense(128, activation='relu'),
        tf.keras.layers.Dropout(0.3),
        tf.keras.layers.Dense(1, activation='sigmoid')
    ])

    model.compile(optimizer='adam', loss='binary_crossentropy', metrics=['accuracy'])

    # Train the model
    model.fit(X, y, epochs=10, batch_size=32, validation_split=0.2)

    return model


# Dynamically load all wake word and background audio files
wakeword_data = glob.glob('model_training/audio_data/*.wav')  # Wake word directory
background_data = glob.glob('model_training/background_sound/*.wav')  # Background directory

# Fine-tune YAMNet
fine_tuned_model = fine_tune_yamnet(wakeword_data, background_data)

# Save the fine-tuned model
fine_tuned_model.save('model_training/saved_model/fine_tuned_yamnet_model.keras')
