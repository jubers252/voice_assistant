"""
Diagnostic script to test wake word detection in night/quiet conditions
Run this to verify the fixes are working
"""

import numpy as np
import sys
import os
from pathlib import Path

# Add parent dir to path
sys.path.insert(0, str(Path(__file__).parent))

from audio.wake_word_detector import WakeWordDetector
from speech.speech_recognizer import SpeechRecognizer
from audio.audio_processor import AudioProcessors
import speech_recognition as sr

def test_night_detection():
    """Test wake word detection with simulated night conditions"""
    
    print("\n" + "="*70)
    print("NIGHTTIME WAKE WORD DETECTION TEST")
    print("="*70)
    
    # Initialize components
    print("\n[1/5] Loading wake word detector...")
    try:
        ww_model = "model/WWD_respeaker_model_v10.h5"
        detector = WakeWordDetector(model_path=ww_model)
        print("✓ Wake word detector loaded")
    except Exception as e:
        print(f"✗ Failed to load detector: {e}")
        return
    
    # Initialize audio processors
    print("[2/5] Setting up audio processors...")
    audio_processors = AudioProcessors()
    print("✓ Audio processors ready")
    
    # Initialize recognizer
    print("[3/5] Initializing speech recognizer...")
    recognizer = SpeechRecognizer(audio_processors, device_index=0)
    print(f"✓ Recognizer ready")
    print(f"  - Device: {recognizer.device_index}")
    print(f"  - Initial energy threshold: {int(recognizer.recognizer.energy_threshold)}")
    
    # Test with quiet audio simulation
    print("\n[4/5] Testing with quiet audio (simulating night)...")
    sr_recognizer = sr.Recognizer()
    
    # Simulate very quiet ambient noise (night conditions)
    quiet_audio = np.random.normal(0, 100, 16000 * 2).astype(np.float32)  # Convert to float32
    # Normalize to -1.0 to 1.0 range (librosa expects float audio)
    quiet_audio = quiet_audio / np.max(np.abs(quiet_audio))
    
    try:
        # Convert to audio_data format
        features = detector.extract_features(quiet_audio, 16000)
        if features is None:
            print("✗ Failed to extract features")
            return
            
        # Pad to model size
        if features.shape[0] < 44:
            features = np.pad(features, ((0, 44 - features.shape[0]), (0, 0)), mode='constant')
        else:
            features = features[:44]
        
        features = features.reshape(1, 44, 120)
        
        # Test detection with different thresholds
        print("\n  Testing with various confidence thresholds:")
        for conf_thresh in [0.25, 0.30, 0.35, 0.40]:
            prediction = detector.model.predict(features, verbose=0)[0][0]
            detected = prediction > conf_thresh
            print(f"    Confidence={prediction:.4f} | Threshold={conf_thresh:.2f} | Result: {'✓ DETECTED' if detected else '✗ rejected'}")
        
        print("\n✓ Feature extraction and model inference working")
        
    except Exception as e:
        print(f"✗ Error during testing: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # Check energy thresholds
    print("[5/5] Analyzing energy threshold settings...")
    print(f"\n  Current recognizer energy threshold: {int(sr_recognizer.energy_threshold)}")
    print(f"\n  Wake word detection will use:")
    print(f"    - Min energy threshold: 0.00005")
    print(f"    - Max energy threshold: 0.0005")
    print(f"    - Formula: (recognizer_threshold / 4000) * 0.05, clipped to bounds")
    
    # Simulate what threshold would be calculated
    rec_threshold = sr_recognizer.energy_threshold
    normalized = (rec_threshold / 4000.0) * 0.05
    final = np.clip(normalized, 0.00005, 0.0005)
    print(f"\n  If recognizer threshold is {int(rec_threshold)}:")
    print(f"    Normalized calculation: {normalized:.6f}")
    print(f"    Final (clipped): {final:.6f}")
    
    print("\n" + "="*70)
    print("TEST COMPLETE")
    print("="*70)
    print("\nIf you're still not detecting wake words at night:")
    print("1. Check console for [WWD_NIGHT_DEBUG] messages during operation")
    print("2. If Energy is detected but Confidence is low, the model itself needs retraining")
    print("3. If Energy is NOT detected, microphone may have issues at low volumes")
    print("4. Set debug_mode=True in WakeWordManager for verbose output")
    print("\n")

if __name__ == "__main__":
    test_night_detection()
