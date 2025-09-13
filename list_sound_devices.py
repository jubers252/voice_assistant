"""
Script to list all available sound devices (microphones and speakers)
This helps identify the correct device indices for audio applications
"""

import speech_recognition as sr
import sounddevice as sd
import pyaudio
import sys

def list_speech_recognition_mics():
    """List microphones available to speech_recognition library"""
    print("=" * 60)
    print("SPEECH RECOGNITION MICROPHONES")
    print("=" * 60)
    
    try:
        mic_list = sr.Microphone.list_microphone_names()
        for i, name in enumerate(mic_list):
            print(f"{i:2d}: {name}")
        print(f"\nTotal microphones found: {len(mic_list)}")
        
        # Test default microphone
        print("\nTesting default microphone...")
        try:
            with sr.Microphone() as source:
                print("Default microphone is accessible ✓")
        except Exception as e:
            print(f"Default microphone error: {e}")
            
    except Exception as e:
        print(f"Error listing speech recognition microphones: {e}")

def list_sounddevice_devices():
    """List all audio devices available to sounddevice library"""
    print("\n" + "=" * 60)
    print("SOUNDDEVICE AUDIO DEVICES")
    print("=" * 60)
    
    try:
        devices = sd.query_devices()
        print(f"{'ID':<3} {'Name':<40} {'Type':<12} {'Channels':<8} {'Sample Rate'}")
        print("-" * 80)
        
        for i, device in enumerate(devices):
            device_type = []
            if device['max_input_channels'] > 0:
                device_type.append('Input')
            if device['max_output_channels'] > 0:
                device_type.append('Output')
            
            type_str = '/'.join(device_type) if device_type else 'None'
            
            print(f"{i:<3} {device['name'][:39]:<40} {type_str:<12} "
                  f"I:{device['max_input_channels']}/O:{device['max_output_channels']:<3} "
                  f"{device['default_samplerate']}")
        
        # Show default devices
        default_input = sd.default.device[0] if sd.default.device[0] is not None else 'None'
        default_output = sd.default.device[1] if sd.default.device[1] is not None else 'None'
        print(f"\nDefault input device: {default_input}")
        print(f"Default output device: {default_output}")
        
    except Exception as e:
        print(f"Error listing sounddevice devices: {e}")

def list_pyaudio_devices():
    """List all audio devices available to pyaudio library"""
    print("\n" + "=" * 60)
    print("PYAUDIO DEVICES")
    print("=" * 60)
    
    try:
        p = pyaudio.PyAudio()
        
        print(f"{'ID':<3} {'Name':<40} {'Channels':<12} {'Sample Rate'}")
        print("-" * 70)
        
        for i in range(p.get_device_count()):
            info = p.get_device_info_by_index(i)
            channels = f"I:{info['maxInputChannels']}/O:{info['maxOutputChannels']}"
            print(f"{i:<3} {info['name'][:39]:<40} {channels:<12} {info['defaultSampleRate']}")
        
        # Show default devices
        try:
            default_input_info = p.get_default_input_device_info()
            print(f"\nDefault input device: {default_input_info['index']} - {default_input_info['name']}")
        except:
            print("\nNo default input device found")
            
        try:
            default_output_info = p.get_default_output_device_info()
            print(f"Default output device: {default_output_info['index']} - {default_output_info['name']}")
        except:
            print("No default output device found")
            
        p.terminate()
        
    except Exception as e:
        print(f"Error listing pyaudio devices: {e}")

def test_microphone_access():
    """Test if we can access microphones"""
    print("\n" + "=" * 60)
    print("MICROPHONE ACCESS TEST")
    print("=" * 60)
    
    # Test speech_recognition default microphone
    print("Testing speech_recognition default microphone...")
    try:
        recognizer = sr.Recognizer()
        with sr.Microphone() as source:
            recognizer.adjust_for_ambient_noise(source, duration=0.5)
            print(f"✓ Default microphone accessible (energy threshold: {recognizer.energy_threshold})")
    except Exception as e:
        print(f"✗ Default microphone error: {e}")
    
    # Test specific microphone indices
    print("\nTesting specific microphone indices...")
    for device_index in [0, 1, 2]:
        try:
            with sr.Microphone(device_index=device_index) as source:
                print(f"✓ Microphone {device_index} accessible")
        except Exception as e:
            print(f"✗ Microphone {device_index} error: {e}")

def main():
    """Main function to run all device listing functions"""
    print("SOUND DEVICE DETECTION SCRIPT")
    print("This script will list all available audio devices on your system")
    print("Use this information to configure your voice assistant")
    
    list_speech_recognition_mics()
    list_sounddevice_devices()
    list_pyaudio_devices()
    test_microphone_access()
    
    print("\n" + "=" * 60)
    print("RECOMMENDATIONS")
    print("=" * 60)
    print("1. Use the device index from 'SPEECH RECOGNITION MICROPHONES' section")
    print("2. Look for devices with 'Input' capability and multiple input channels")
    print("3. Built-in microphones usually work best")
    print("4. If default microphone works, you can use device_index=None")
    print("5. Test different indices if you have multiple microphones")

if __name__ == "__main__":
    main()
