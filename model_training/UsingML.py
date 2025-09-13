####### IMPORTS #############
import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import confusion_matrix, classification_report
import pickle

##### Loading saved pickle file ##############
df = pd.read_pickle(r"model_training\final_audio_data_csv\audio_data_cnn_no_augmentation.pkl")

####### Making our data training-ready
# Extract features - they're already in the right format from preprocessing
X = np.stack(df["feature"].values)  # Shape: (samples, time_steps, features)

# For Logistic Regression, we need to flatten the features
X_flattened = X.reshape(X.shape[0], -1)  # Shape: (samples, time_steps * features)

print(f"Original shape: {X.shape}")
print(f"Flattened shape: {X_flattened.shape}")

y = np.array(df["class_label"].tolist())
print(f"Class distribution: {np.bincount(y)}")

####### train test split ############
X_train, X_test, y_train, y_test = train_test_split(X_flattened, y, test_size=0.2, random_state=42, stratify=y)

print(f"Training samples: {len(X_train)}")
print(f"Test samples: {len(X_test)}")

##### Training with regularization to prevent overfitting ############

# Use L2 regularization to prevent overfitting
logit_reg = LogisticRegression(max_iter=10000, C=1.0, random_state=42)
logit_reg.fit(X_train, y_train)
score = logit_reg.score(X_test, y_test)
print(f"\nModel Test Accuracy: {score:.4f}")

# Check prediction probabilities for better analysis
y_pred_proba = logit_reg.predict_proba(X_test)
print(f"\nPrediction Probability Analysis:")
print(f"Wake word samples - Mean confidence: {np.mean(y_pred_proba[y_test == 1, 1]):.3f}")
print(f"Background samples - Mean confidence: {np.mean(y_pred_proba[y_test == 0, 1]):.3f}")

#### Evaluating our model ###########
print("\n=== Model Classification Report ===")

y_pred = logit_reg.predict(X_test)
cm = confusion_matrix(y_test, y_pred)
print(classification_report(y_test, y_pred, target_names=["Background", "Wake Word"]))

#### Save the model with better naming
model_path = 'model/WWD_LogisticRegression.pkl'
pickle.dump(logit_reg, open(model_path, 'wb'))
print(f"\nModel saved to: {model_path}")

print("\n=== Model Training Complete ===")
print("Logistic Regression model should have more realistic confidence scores!")

'''
To load the model again run this:

>>> import pickle
>>> model = pickle.load(open('saved_model/WWD_LogisticRegression.pkl', 'rb'))
>>> model.predict_proba(<-- your flattened feature matrix -->) # to get probabilities
>>> model.predict(<-- your flattened feature matrix -->) # to get class predictions
'''
