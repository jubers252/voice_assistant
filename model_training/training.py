#### Wake Word Detection Model Training (Beginner Friendly)
# This script trains a simple 1D CNN to detect a wake word using MFCC features.
# You do NOT need deep learning expertise to use or modify this script.
# Just run it and check the printed accuracy and classification report!

####### IMPORTS #############
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
df = pd.read_pickle(r"model_training\final_audio_data_csv\audio_data_cnn_improved.pkl")

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

##### 3. Build an Improved 1D CNN Model with Better Regularization #####
from keras.layers import BatchNormalization
from keras.regularizers import l2

# This model learns patterns in the MFCC features over time with better generalization
model = Sequential([
    # First Conv Block
    Conv1D(32, kernel_size=3, activation='relu', input_shape=(desired_length, feature_dim), 
           kernel_regularizer=l2(0.01)),
    BatchNormalization(),
    MaxPooling1D(2),
    Dropout(0.4),  # Increased dropout

    # Second Conv Block
    Conv1D(64, kernel_size=3, activation='relu', kernel_regularizer=l2(0.01)),
    BatchNormalization(),
    MaxPooling1D(2),
    Dropout(0.5),  # Increased dropout

    # Dense layers
    Flatten(),
    Dense(64, activation='relu', kernel_regularizer=l2(0.01)),
    Dropout(0.5),
    Dense(1, activation='sigmoid')  # Binary classification
])

print(model.summary())  # Shows model structure

##### 4. Compile the Model with Better Settings #####
from keras.optimizers import Adam

model.compile(
    loss="binary_crossentropy",  # Binary classification loss
    optimizer=Adam(learning_rate=0.001),  # Lower learning rate for better convergence
    metrics=['accuracy', 'precision', 'recall']  # Track multiple metrics
)

# Enhanced callbacks for better training control
from keras.callbacks import ReduceLROnPlateau, ModelCheckpoint

early_stop = EarlyStopping(monitor='val_loss', patience=10, restore_best_weights=True, verbose=1)
reduce_lr = ReduceLROnPlateau(monitor='val_loss', factor=0.5, patience=5, verbose=1, min_lr=1e-5)
checkpoint = ModelCheckpoint(r"model_training\saved_model\best_model.h5", 
                           monitor='val_loss', save_best_only=True, verbose=1)

##### 5. Train the Model with Better Validation #####
print("Training Model with Enhanced Regularization: \n")
history = model.fit(
    X_train, y_train,
    epochs=50,  # Reduced epochs
    batch_size=16,                 # Smaller batch size for better generalization
    validation_data=(X_val, y_val), # Use separate validation set
    callbacks=[early_stop, reduce_lr, checkpoint],  # Multiple callbacks
    verbose=1
)

# Load the best model
model.load_weights(r"model_training\saved_model\best_model.h5")

# Save the final model
model.save(r"model_training\saved_model\WWD_improved.h5")

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

# Suggest optimal threshold
from sklearn.metrics import roc_curve, auc
fpr, tpr, thresholds = roc_curve(y_true_classes, y_pred)
optimal_idx = np.argmax(tpr - fpr)
optimal_threshold = thresholds[optimal_idx]
print(f"Suggested optimal threshold: {optimal_threshold:.3f}")

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
wakeword_data = glob.glob('model_training/wake_word/*.wav')  # Replace with your wake word directory
background_data = glob.glob('model_training/background_sound/*.wav')  # Replace with your background directory

# Fine-tune YAMNet
fine_tuned_model = fine_tune_yamnet(wakeword_data, background_data)

# Save the fine-tuned model
fine_tuned_model.save('model_training/saved_model/fine_tuned_yamnet_model.keras')
