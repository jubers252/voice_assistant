#!/usr/bin/env python3
"""
Test speech recognition accuracy at different distances.
Helps you find the optimal range for voice recognition.
"""

import speech_recognition as sr
import time
import pyaudio
import struct
import math
import warnings
import os
import sys

# Suppress ALSA/JACK warnings
warnings.filterwarnings("ignore")

# Redirect stderr to suppress ALSA/JACK messages at C library level
from contextlib import contextmanager

@contextmanager
def suppress_alsa_errors():
    """Suppress ALSA error messages from C libraries."""
    # Save the actual stderr file descriptor
    stderr_fd = sys.stderr.fileno()
    old_stderr = os.dup(stderr_fd)
    
    # Redirect stderr to /dev/null
    devnull = os.open(os.devnull, os.O_WRONLY)
    os.dup2(devnull, stderr_fd)
    os.close(devnull)
    
    try:
        yield
    finally:
        # Restore stderr
        os.dup2(old_stderr, stderr_fd)
        os.close(old_stderr)

def calculate_rms(data):
    """Calculate RMS for audio data."""
    count = len(data) / 2
    format_str = f"{int(count)}h"
    shorts = struct.unpack(format_str, data)
    sum_squares = sum(s ** 2 for s in shorts)
    rms = math.sqrt(sum_squares / count)
    return rms

def test_recognition():
    recognizer = sr.Recognizer()
    
    # Adjust for ambient noise
    print("=" * 70)
    print("Speech Recognition Range Test")
    print("=" * 70)
    print("\nCalibrating for ambient noise... Please wait (5 seconds)")
    
    with suppress_alsa_errors():
        with sr.Microphone() as source:
            recognizer.adjust_for_ambient_noise(source, duration=5)
            print(f"✓ Calibration complete")
            print(f"  Energy threshold: {recognizer.energy_threshold}")
            print(f"  Dynamic threshold: {recognizer.dynamic_energy_threshold}")
    
    print("\n" + "=" * 70)
    print("Test Instructions:")
    print("=" * 70)
    print("1. Say test phrases like:")
    print("   • 'Hello, how are you?'")
    print("   • 'What is the weather today?'")
    print("   • 'Play some music'")
    print("2. Try speaking from different distances")
    print("3. Watch recognition accuracy")
    print("4. Press Ctrl+C to quit")
    print("=" * 70 + "\n")
    
    test_count = 0
    successful = 0
    
    while True:
        try:
            test_count += 1
            print(f"\n[Test #{test_count}] Listening... (speak now)")
            
            with suppress_alsa_errors():
                with sr.Microphone() as source:
                    # Get audio level while listening
                    audio_data = recognizer.listen(source, timeout=10, phrase_time_limit=10)
                    
                    # Calculate audio level
                    raw_data = audio_data.get_raw_data()
                    rms = calculate_rms(raw_data)
                
                print(f"🎤 Audio captured | RMS Level: {int(rms)}")
            
            # Try to recognize
            print("🔄 Processing...")
            start_time = time.time()
            
            try:
                # Try Google Speech Recognition
                text = recognizer.recognize_google(audio_data)
                recognition_time = time.time() - start_time
                successful += 1
                
                print(f"✓ RECOGNIZED ({recognition_time:.2f}s):")
                print(f"  └─> \"{text}\"")
                print(f"  └─> Audio Level: {int(rms)}")
                
                # Quality assessment
                if rms < 500:
                    quality = "⚠️  Low volume - try moving closer"
                elif rms < 3000:
                    quality = "✓ Good volume level"
                elif rms < 8000:
                    quality = "⚠️  High volume - may cause distortion"
                else:
                    quality = "❌ Too loud - move further away"
                
                print(f"  └─> {quality}")
                
            except sr.UnknownValueError:
                print("❌ Could not understand audio")
                print(f"  └─> Audio Level: {int(rms)}")
                if rms < 500:
                    print("  └─> Tip: Audio too quiet, move closer or speak louder")
                elif rms > 8000:
                    print("  └─> Tip: Audio too loud, move further away")
                else:
                    print("  └─> Tip: Try speaking more clearly")
            
            except sr.RequestError as e:
                print(f"❌ API Error: {e}")
                print("  └─> Check internet connection")
            
            # Statistics
            if test_count > 0:
                success_rate = (successful / test_count) * 100
                print(f"\n📊 Stats: {successful}/{test_count} successful ({success_rate:.1f}%)")
            
            print("\n" + "-" * 70)
            
        except sr.WaitTimeoutError:
            print("⏱️  Timeout - no speech detected")
            print("  └─> Tip: Speak louder or move closer")
            print("\n" + "-" * 70)
            
        except KeyboardInterrupt:
            print("\n\n" + "=" * 70)
            print("Test Summary")
            print("=" * 70)
            print(f"Total tests: {test_count}")
            print(f"Successful: {successful}")
            print(f"Failed: {test_count - successful}")
            if test_count > 0:
                print(f"Success rate: {(successful / test_count) * 100:.1f}%")
            print("\nRecommendations:")
            print("  • Aim for 80%+ success rate")
            print("  • Maintain RMS levels between 500-3000")
            print("  • Speak clearly and at normal pace")
            print("  • Minimize background noise")
            print("=" * 70)
            break
        
        except Exception as e:
            print(f"❌ Error: {e}")
            print("\n" + "-" * 70)

if __name__ == "__main__":
    try:
        test_recognition()
    except KeyboardInterrupt:
        print("\n\nTest stopped by user.")
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        print("\nTroubleshooting:")
        print("  • Check microphone connection")
        print("  • Verify internet connection (for Google API)")
        print("  • Check microphone permissions")
        print("  • Install: pip install SpeechRecognition pyaudio")
