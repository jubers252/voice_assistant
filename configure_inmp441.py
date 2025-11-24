#!/usr/bin/env python3
"""
INMP441 Microphone Configuration Script for Raspberry Pi
Helps optimize settings for the INMP441 I2S microphone
"""

import speech_recognition as sr
import sounddevice as sd
import numpy as np
import os
from contextlib import contextmanager

@contextmanager
def suppress_alsa_errors():
    """Suppress ALSA/JACK error messages"""
    try:
        devnull = os.open(os.devnull, os.O_WRONLY)
        old_stderr = os.dup(2)
        os.dup2(devnull, 2)
        os.close(devnull)
        yield
    finally:
        os.dup2(old_stderr, 2)
        os.close(old_stderr)

def list_audio_devices():
    """List all available audio devices"""
    print("\n=== Available Audio Devices ===")
    with suppress_alsa_errors():
        devices = sd.query_devices()
        for i, device in enumerate(devices):
            print(f"\nDevice {i}: {device['name']}")
            print(f"  Input channels: {device['max_input_channels']}")
            print(f"  Output channels: {device['max_output_channels']}")
            print(f"  Default sample rate: {device['default_samplerate']}")
    
    print("\n=== Speech Recognition Microphones ===")
    mic_names = sr.Microphone.list_microphone_names()
    for i, name in enumerate(mic_names):
        print(f"{i}: {name}")
    
    return devices

def test_microphone(device_index=None, duration=3):
    """Test microphone and measure audio levels"""
    print(f"\n=== Testing Microphone (device_index={device_index}) ===")
    print(f"Recording for {duration} seconds...")
    print("Please speak into the microphone...")
    
    try:
        with suppress_alsa_errors():
            if device_index is not None:
                audio = sd.rec(
                    int(duration * 16000),
                    samplerate=16000,
                    channels=1,
                    dtype='float32',
                    device=device_index
                )
            else:
                audio = sd.rec(
                    int(duration * 16000),
                    samplerate=16000,
                    channels=1,
                    dtype='float32'
                )
            sd.wait()
        
        audio_flat = audio.flatten()
        
        # Calculate audio statistics
        rms = np.sqrt(np.mean(audio_flat**2))
        peak = np.max(np.abs(audio_flat))
        
        print(f"\n✓ Recording successful!")
        print(f"  RMS level: {rms:.6f}")
        print(f"  Peak level: {peak:.6f}")
        print(f"  Recommended energy threshold: {int(rms * 10000)}-{int(rms * 15000)}")
        
        # Check if audio is too quiet or too loud
        if rms < 0.001:
            print("  ⚠️  WARNING: Audio is very quiet! Check microphone connection.")
        elif rms > 0.1:
            print("  ⚠️  WARNING: Audio is very loud! May cause distortion.")
        else:
            print("  ✓ Audio levels look good!")
        
        return True, rms, peak
        
    except Exception as e:
        print(f"✗ Error testing microphone: {e}")
        return False, 0, 0

def test_speech_recognition(device_index=None):
    """Test speech recognition with the microphone"""
    print(f"\n=== Testing Speech Recognition ===")
    print("Speak a command when you see 'Listening...'")
    
    try:
        recognizer = sr.Recognizer()
        # Adjust settings for INMP441
        recognizer.energy_threshold = 300  # Lower for sensitive mic
        recognizer.dynamic_energy_threshold = True
        recognizer.pause_threshold = 0.8
        
        with suppress_alsa_errors():
            if device_index is not None:
                mic = sr.Microphone(device_index=device_index)
            else:
                mic = sr.Microphone()
        
        with mic as source:
            print("Adjusting for ambient noise... (1 second)")
            recognizer.adjust_for_ambient_noise(source, duration=1)
            print(f"Energy threshold set to: {recognizer.energy_threshold}")
            print("\nListening...")
            audio = recognizer.listen(source, timeout=10, phrase_time_limit=5)
            print("Processing...")
        
        # Try to recognize
        try:
            text = recognizer.recognize_google(audio, language='en-US')
            print(f"\n✓ Recognized: '{text}'")
            return True
        except sr.UnknownValueError:
            print("✗ Could not understand audio")
            return False
        except sr.RequestError as e:
            print(f"✗ API error: {e}")
            return False
            
    except Exception as e:
        print(f"✗ Error: {e}")
        return False

def generate_config():
    """Generate recommended configuration"""
    print("\n=== Recommended Configuration ===")
    print("""
Add these settings to your voice_assistant.py:

# For AudioProcessors.__init__():
self.sample_rate = 16000  # INMP441 works well at 16kHz
self.mic_device_id = None  # Use system default or specify index
self.audio_channels = 1

# For SpeechRecognizer._setup_recognizer():
self.recognizer.energy_threshold = 300  # Lower for sensitive INMP441
self.recognizer.dynamic_energy_threshold = True
self.recognizer.pause_threshold = 0.8
self.recognizer.phrase_threshold = 0.3
self.recognizer.non_speaking_duration = 0.8

# Optional: To suppress ALSA errors, the code has already been updated.
    """)

def main():
    """Main configuration wizard"""
    print("=" * 60)
    print("INMP441 Microphone Configuration for Voice Assistant")
    print("=" * 60)
    
    # List devices
    devices = list_audio_devices()
    
    # Ask user which device to test
    print("\n" + "=" * 60)
    device_input = input("\nEnter device index to test (or press Enter for default): ").strip()
    
    if device_input:
        try:
            device_index = int(device_input)
        except ValueError:
            print("Invalid input, using default device")
            device_index = None
    else:
        device_index = None
    
    # Test microphone
    success, rms, peak = test_microphone(device_index=device_index, duration=3)
    
    if success:
        # Test speech recognition
        print("\n" + "=" * 60)
        if input("Test speech recognition? (y/n): ").lower().startswith('y'):
            test_speech_recognition(device_index=device_index)
    
    # Generate config
    generate_config()
    
    print("\n" + "=" * 60)
    print("Configuration complete!")
    print("=" * 60)

if __name__ == "__main__":
    main()
