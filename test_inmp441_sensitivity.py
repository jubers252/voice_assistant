#!/usr/bin/env python3
"""
Quick test to check INMP441 microphone sensitivity
This will show you real-time audio levels and help diagnose pickup issues
"""

import speech_recognition as sr
import sounddevice as sd
import numpy as np
import time
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

def test_realtime_audio_levels(duration=10, device_index=None):
    """Monitor real-time audio levels from INMP441"""
    print(f"\n{'='*60}")
    print("INMP441 Real-Time Audio Level Monitor")
    print(f"{'='*60}")
    print(f"Monitoring for {duration} seconds...")
    print("Please speak from 1 foot away from the microphone")
    print(f"{'='*60}\n")
    
    sample_rate = 16000
    chunk_size = int(sample_rate * 0.1)  # 100ms chunks
    
    start_time = time.time()
    max_rms = 0
    max_peak = 0
    samples_processed = 0
    
    try:
        with suppress_alsa_errors():
            if device_index is not None:
                stream = sd.InputStream(
                    samplerate=sample_rate,
                    channels=1,
                    dtype='float32',
                    blocksize=chunk_size,
                    device=device_index
                )
            else:
                stream = sd.InputStream(
                    samplerate=sample_rate,
                    channels=1,
                    dtype='float32',
                    blocksize=chunk_size
                )
        
        with stream:
            while (time.time() - start_time) < duration:
                audio, _ = stream.read(chunk_size)
                audio_flat = audio.flatten()
                
                # Calculate RMS and peak
                rms = np.sqrt(np.mean(audio_flat**2))
                peak = np.max(np.abs(audio_flat))
                
                # Track maximums
                max_rms = max(max_rms, rms)
                max_peak = max(max_peak, peak)
                
                # Create visual bar
                bar_length = int(rms * 1000)  # Scale for visibility
                bar = '█' * min(bar_length, 50)
                
                # Color code based on level
                if rms > 0.01:
                    status = "✓ GOOD"
                elif rms > 0.003:
                    status = "⚠ LOW"
                else:
                    status = "✗ TOO QUIET"
                
                print(f"\rRMS: {rms:6.4f} Peak: {peak:6.4f} {status} {bar}", end='', flush=True)
                samples_processed += 1
                time.sleep(0.05)  # Small delay for readability
        
        print(f"\n\n{'='*60}")
        print("Results:")
        print(f"{'='*60}")
        print(f"Max RMS:  {max_rms:.6f}")
        print(f"Max Peak: {max_peak:.6f}")
        print(f"Samples:  {samples_processed}")
        
        # Recommendations
        print(f"\n{'='*60}")
        print("Recommendations:")
        print(f"{'='*60}")
        
        if max_rms < 0.003:
            print("✗ Microphone is TOO QUIET!")
            print("  Solutions:")
            print("  1. Check INMP441 wiring (especially GND, VDD, SCK, WS, SD)")
            print("  2. Verify I2S is properly configured in /boot/config.txt")
            print("  3. Check alsamixer settings: run 'alsamixer' and increase capture volume")
            print("  4. Test with: arecord -D plughw:CARD=sndrpii2scard,DEV=0 -f S32_LE -r 16000 test.wav")
            print(f"\n  Recommended energy_threshold: 50-100")
        elif max_rms < 0.01:
            print("⚠ Microphone is quiet but working")
            print("  The levels are low but should work")
            print(f"  Recommended energy_threshold: 100-200")
        else:
            print("✓ Microphone levels are GOOD!")
            print(f"  Recommended energy_threshold: 200-300")
        
        print(f"\nEnergy threshold formula: threshold ≈ max_rms × 10000 × 0.5")
        print(f"Calculated threshold: {int(max_rms * 10000 * 0.5)}")
        
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()

def test_speech_recognition_sensitivity(device_index=None):
    """Test speech recognition with optimized settings for INMP441"""
    print(f"\n{'='*60}")
    print("Testing Speech Recognition Sensitivity")
    print(f"{'='*60}")
    print("Speak a command from 1 foot away when you see 'Listening...'")
    print(f"{'='*60}\n")
    
    try:
        recognizer = sr.Recognizer()
        
        # Ultra-sensitive settings for INMP441
        recognizer.energy_threshold = 150  # Very low for sensitive mic
        recognizer.dynamic_energy_threshold = True
        recognizer.dynamic_energy_adjustment_damping = 0.15
        recognizer.dynamic_energy_ratio = 1.5
        recognizer.pause_threshold = 0.8
        recognizer.phrase_threshold = 0.3
        recognizer.non_speaking_duration = 0.8
        
        with suppress_alsa_errors():
            if device_index is not None:
                mic = sr.Microphone(device_index=device_index)
            else:
                mic = sr.Microphone()
        
        with mic as source:
            print("Calibrating for ambient noise... (0.5 seconds)")
            recognizer.adjust_for_ambient_noise(source, duration=0.5)
            print(f"✓ Energy threshold calibrated to: {recognizer.energy_threshold}")
            print("\n🎤 Listening... (speak now)")
            
            try:
                audio = recognizer.listen(source, timeout=10, phrase_time_limit=10)
                print("Processing...")
                
                # Show audio data size
                audio_duration = len(audio.frame_data) / audio.sample_rate
                print(f"Captured {audio_duration:.2f} seconds of audio")
                
                # Try to recognize
                text = recognizer.recognize_google(audio, language='en-US')
                print(f"\n✓ SUCCESS! Recognized: '{text}'")
                return True
                
            except sr.WaitTimeoutError:
                print("✗ Timeout - no speech detected")
                print("  This means the microphone didn't detect sound above the threshold")
                return False
            except sr.UnknownValueError:
                print("⚠ Audio was detected but couldn't be understood")
                print("  The microphone IS working, but speech was unclear")
                return False
            except sr.RequestError as e:
                print(f"✗ API error: {e}")
                return False
                
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    print(f"\n{'='*60}")
    print("INMP441 Microphone Sensitivity Test")
    print(f"{'='*60}\n")
    
    # Ask for device index
    device_input = input("Enter device index (or press Enter for default): ").strip()
    device_index = int(device_input) if device_input else None
    
    # Test 1: Real-time audio levels
    print("\n[TEST 1/2] Real-time audio level monitoring")
    input("Press Enter to start 10-second monitoring...")
    test_realtime_audio_levels(duration=10, device_index=device_index)
    
    # Test 2: Speech recognition
    print("\n[TEST 2/2] Speech recognition test")
    input("Press Enter to test speech recognition...")
    test_speech_recognition_sensitivity(device_index=device_index)
    
    print(f"\n{'='*60}")
    print("Testing Complete!")
    print(f"{'='*60}\n")

if __name__ == "__main__":
    main()
