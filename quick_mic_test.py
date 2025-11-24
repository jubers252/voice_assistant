#!/usr/bin/env python3
"""
Quick microphone test - simplified version for fast testing
"""

import sounddevice as sd
import numpy as np
import time

def quick_test():
    """Quick test to check if microphone is working"""
    print("=== Quick INMP441 Microphone Test ===\n")
    
    # List devices
    print("Available audio devices:")
    devices = sd.query_devices()
    i2s_device = None
    
    for i, device in enumerate(devices):
        if device['max_input_channels'] > 0:
            print(f"  [{i}] {device['name']}")
            # Auto-detect I2S
            if any(kw in device['name'].lower() for kw in ['i2s', 'inmp', 'simple-card']):
                i2s_device = i
                print(f"      ⭐ I2S device detected!")
    
    # Select device
    if i2s_device is not None:
        device_id = i2s_device
        print(f"\nUsing auto-detected I2S device: {device_id}")
    else:
        try:
            device_id = int(input("\nEnter device number to test (or press Enter for default): ").strip() or "-1")
            if device_id == -1:
                device_id = None
        except:
            device_id = None
    
    # Quick recording test
    print(f"\n🎤 Recording 3 seconds... Speak now!")
    
    try:
        sample_rate = 16000
        audio = sd.rec(
            int(3 * sample_rate),
            samplerate=sample_rate,
            channels=1,
            dtype='float32',
            device=device_id
        )
        sd.wait()
        
        # Analyze
        audio_flat = audio.flatten()
        rms = np.sqrt(np.mean(audio_flat ** 2))
        peak = np.max(np.abs(audio_flat))
        
        print(f"\n✅ Recording complete!")
        print(f"   RMS Level:  {rms:.6f}")
        print(f"   Peak Level: {peak:.6f}")
        
        if rms < 0.001:
            print("   ⚠️  WARNING: Very low audio - microphone might not be working!")
            print("   Check connections and ALSA configuration")
        elif rms < 0.01:
            print("   ⚠️  Low audio - try speaking louder or adjust gain")
        else:
            print("   ✅ Microphone is working well!")
        
        # Save
        import soundfile as sf
        sf.write("quick_test.wav", audio_flat, sample_rate)
        print(f"   💾 Saved to: quick_test.wav")
        
        print(f"\n📝 Configuration for voice assistant:")
        print(f"   Device ID: {device_id if device_id is not None else 'None (default)'}")
        print(f"   Sample Rate: {sample_rate} Hz")
        
        return True
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        print("\nTroubleshooting tips:")
        print("1. Check if I2S is enabled: lsmod | grep snd")
        print("2. List ALSA devices: arecord -l")
        print("3. Test with ALSA: arecord -D hw:1,0 -f S32_LE -r 16000 -d 3 test.wav")
        return False

if __name__ == "__main__":
    try:
        quick_test()
    except KeyboardInterrupt:
        print("\n\nTest cancelled.")
