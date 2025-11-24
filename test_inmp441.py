#!/usr/bin/env python3
"""
INMP441 I2S Microphone Test Script for Raspberry Pi
This script helps identify and test the INMP441 microphone
"""

import sounddevice as sd
import numpy as np
import soundfile as sf
import time
from datetime import datetime

def list_all_devices():
    """List all available audio devices"""
    print("=" * 60)
    print("ALL AUDIO DEVICES")
    print("=" * 60)
    
    devices = sd.query_devices()
    for i, device in enumerate(devices):
        print(f"\nDevice {i}: {device['name']}")
        print(f"  Input channels:  {device['max_input_channels']}")
        print(f"  Output channels: {device['max_output_channels']}")
        print(f"  Default sample rate: {device['default_samplerate']} Hz")
        
        # Highlight potential I2S devices
        device_name_lower = device['name'].lower()
        if any(keyword in device_name_lower for keyword in ['i2s', 'inmp', 'card']):
            print("  ⭐ POTENTIAL INMP441 I2S DEVICE ⭐")
    
    print("\n" + "=" * 60)
    return devices


def test_microphone_recording(device_index=None, duration=3, sample_rate=16000):
    """Test recording from a specific microphone device"""
    print(f"\n{'=' * 60}")
    print(f"TESTING MICROPHONE")
    print(f"{'=' * 60}")
    print(f"Device index: {device_index if device_index is not None else 'Default'}")
    print(f"Duration: {duration} seconds")
    print(f"Sample rate: {sample_rate} Hz")
    print(f"Channels: 1 (mono)")
    
    try:
        # Record audio
        print("\n🎤 Recording... Speak into the microphone!")
        audio_data = sd.rec(
            int(duration * sample_rate),
            samplerate=sample_rate,
            channels=1,
            dtype='float32',
            device=device_index
        )
        sd.wait()  # Wait until recording is finished
        print("✅ Recording complete!")
        
        # Analyze audio
        audio_flat = audio_data.flatten()
        rms = np.sqrt(np.mean(audio_flat ** 2))
        peak = np.max(np.abs(audio_flat))
        
        print(f"\nAudio Analysis:")
        print(f"  RMS Level:  {rms:.6f}")
        print(f"  Peak Level: {peak:.6f}")
        print(f"  Samples:    {len(audio_flat)}")
        
        if rms < 0.001:
            print("  ⚠️  WARNING: Audio level very low - microphone may not be working!")
        elif rms < 0.01:
            print("  ⚠️  Audio level low - check microphone gain or speak louder")
        else:
            print("  ✅ Audio level good!")
        
        # Save to file
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"test_recording_{timestamp}.wav"
        sf.write(filename, audio_flat, sample_rate)
        print(f"\n💾 Recording saved to: {filename}")
        print("   You can play it back with: aplay {filename}")
        
        return True, audio_flat
        
    except Exception as e:
        print(f"❌ Error testing microphone: {e}")
        return False, None


def test_real_time_monitoring(device_index=None, sample_rate=16000, duration=10):
    """Monitor audio levels in real-time"""
    print(f"\n{'=' * 60}")
    print(f"REAL-TIME AUDIO MONITORING")
    print(f"{'=' * 60}")
    print(f"Device index: {device_index if device_index is not None else 'Default'}")
    print(f"Duration: {duration} seconds")
    print("Speak into the microphone to see audio levels...")
    print("\nAudio Level Meter:")
    
    def audio_callback(indata, frames, time_info, status):
        """Callback for real-time audio monitoring"""
        if status:
            print(f"Status: {status}")
        
        # Calculate RMS
        rms = np.sqrt(np.mean(indata ** 2))
        
        # Visual meter (0-50 chars)
        meter_length = int(rms * 1000)  # Scale for visibility
        meter = "█" * min(meter_length, 50)
        
        print(f"\r  {meter:<50} RMS: {rms:.6f}", end='', flush=True)
    
    try:
        with sd.InputStream(
            device=device_index,
            channels=1,
            samplerate=sample_rate,
            callback=audio_callback,
            dtype='float32'
        ):
            time.sleep(duration)
        
        print("\n\n✅ Monitoring complete!")
        return True
        
    except Exception as e:
        print(f"\n❌ Error during monitoring: {e}")
        return False


def find_i2s_device():
    """Try to automatically find the I2S/INMP441 device"""
    print(f"\n{'=' * 60}")
    print("SEARCHING FOR I2S/INMP441 DEVICE")
    print(f"{'=' * 60}")
    
    devices = sd.query_devices()
    candidates = []
    
    for i, device in enumerate(devices):
        # Only consider devices with input channels
        if device['max_input_channels'] > 0:
            device_name_lower = device['name'].lower()
            
            # Look for I2S-related keywords
            if any(keyword in device_name_lower for keyword in 
                   ['i2s', 'inmp', 'card', 'bcm', 'simple']):
                candidates.append((i, device))
                print(f"✓ Found candidate: Device {i} - {device['name']}")
    
    if candidates:
        print(f"\nFound {len(candidates)} potential I2S device(s)")
        return [c[0] for c in candidates]
    else:
        print("\n⚠️  No obvious I2S device found")
        print("Checking all input devices...")
        
        # Fallback: list all input devices
        input_devices = []
        for i, device in enumerate(devices):
            if device['max_input_channels'] > 0:
                input_devices.append(i)
                print(f"  Device {i}: {device['name']}")
        
        return input_devices


def main():
    """Main test function"""
    print("\n" + "=" * 60)
    print("INMP441 I2S MICROPHONE TEST UTILITY")
    print("=" * 60)
    
    # List all devices
    devices = list_all_devices()
    
    # Try to find I2S device
    candidate_devices = find_i2s_device()
    
    if not candidate_devices:
        print("\n❌ No input devices found!")
        return
    
    # Ask user which device to test
    print(f"\n{'=' * 60}")
    print("SELECT DEVICE TO TEST")
    print(f"{'=' * 60}")
    
    if len(candidate_devices) == 1:
        device_to_test = candidate_devices[0]
        print(f"Auto-selecting device {device_to_test}: {devices[device_to_test]['name']}")
    else:
        print("Available input devices:")
        for idx in candidate_devices:
            print(f"  [{idx}] {devices[idx]['name']}")
        
        try:
            device_to_test = int(input("\nEnter device index to test (or press Enter for default): ").strip() or "-1")
            if device_to_test == -1:
                device_to_test = None
                print("Using system default device")
        except (ValueError, KeyboardInterrupt):
            device_to_test = None
            print("\nUsing system default device")
    
    # Test sample rates for INMP441
    # Common rates: 16000 (recommended for speech), 22050, 44100, 48000
    print(f"\n{'=' * 60}")
    print("SAMPLE RATE SELECTION")
    print(f"{'=' * 60}")
    print("Recommended sample rates:")
    print("  [1] 16000 Hz (Good for speech recognition)")
    print("  [2] 22050 Hz (Balanced)")
    print("  [3] 44100 Hz (CD quality)")
    print("  [4] 48000 Hz (Professional)")
    
    try:
        rate_choice = int(input("\nSelect sample rate [1-4] (or press Enter for 16000 Hz): ").strip() or "1")
        sample_rates = {1: 16000, 2: 22050, 3: 44100, 4: 48000}
        sample_rate = sample_rates.get(rate_choice, 16000)
    except (ValueError, KeyboardInterrupt):
        sample_rate = 16000
        print("\nUsing default: 16000 Hz")
    
    print(f"\nSelected sample rate: {sample_rate} Hz")
    
    # Run tests
    print("\n" + "=" * 60)
    print("RUNNING TESTS")
    print("=" * 60)
    
    # Test 1: Basic recording
    print("\nTest 1: Basic Recording Test")
    success, audio = test_microphone_recording(
        device_index=device_to_test,
        duration=3,
        sample_rate=sample_rate
    )
    
    if success:
        # Test 2: Real-time monitoring
        print("\nTest 2: Real-time Monitoring")
        input("\nPress Enter to start real-time monitoring...")
        test_real_time_monitoring(
            device_index=device_to_test,
            sample_rate=sample_rate,
            duration=10
        )
    
    # Print configuration summary
    print("\n" + "=" * 60)
    print("CONFIGURATION SUMMARY")
    print("=" * 60)
    print(f"Device Index: {device_to_test if device_to_test is not None else 'None (use default)'}")
    if device_to_test is not None:
        print(f"Device Name: {devices[device_to_test]['name']}")
    print(f"Sample Rate: {sample_rate} Hz")
    print(f"Channels: 1 (mono)")
    
    print("\nTo use this configuration in your voice assistant:")
    print("1. Note the device index above")
    print("2. Update your voice_assistant.py with these settings")
    print("3. You can set the device in AudioProcessors:")
    print(f"   audio_processors.mic_device_id = {device_to_test}")
    
    print("\n" + "=" * 60)
    print("TEST COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user.")
    except Exception as e:
        print(f"\n\nError: {e}")
        import traceback
        traceback.print_exc()
