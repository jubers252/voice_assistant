#!/usr/bin/env python3
"""
Quick gain adjustment tool for MEMS INMP441 microphone
This helps you quickly test different gain settings without restarting the voice assistant
"""

import os
import sys

def update_env_gain(gain_value):
    """Update or create .env file with new gain setting"""
    env_file = ".env"
    env_example = ".env.example"
    
    # Read current .env or create from example
    env_lines = []
    if os.path.exists(env_file):
        with open(env_file, 'r') as f:
            env_lines = f.readlines()
    elif os.path.exists(env_example):
        with open(env_example, 'r') as f:
            env_lines = f.readlines()
    
    # Update or add MIC_GAIN line
    updated = False
    new_lines = []
    
    for line in env_lines:
        if line.strip().startswith('MIC_GAIN='):
            new_lines.append(f'MIC_GAIN={gain_value}\n')
            updated = True
        else:
            new_lines.append(line)
    
    # Add MIC_GAIN if not found
    if not updated:
        new_lines.append(f'MIC_GAIN={gain_value}\n')
    
    # Write back to .env
    with open(env_file, 'w') as f:
        f.writelines(new_lines)
    
    print(f"✅ Updated {env_file} with MIC_GAIN={gain_value}")

def main():
    print("🎤 MEMS INMP441 Microphone Gain Quick Adjuster")
    print("=" * 50)
    
    # Show current setting
    current_gain = os.getenv('MIC_GAIN', '1.8')
    print(f"Current gain setting: {current_gain}x")
    
    print("\nQuick presets:")
    print("1) 1.5x - Conservative (reduce false positives)")
    print("2) 1.8x - Balanced (recommended starting point)")  
    print("3) 2.0x - Standard boost")
    print("4) 2.5x - Higher sensitivity")
    print("5) 3.0x - Maximum recommended")
    print("6) Custom value")
    print("7) Run full gain test")
    
    try:
        choice = input("\nSelect option (1-7): ").strip()
        
        if choice == '1':
            gain = 1.5
        elif choice == '2':
            gain = 1.8
        elif choice == '3':
            gain = 2.0
        elif choice == '4':
            gain = 2.5
        elif choice == '5':
            gain = 3.0
        elif choice == '6':
            gain_input = input("Enter custom gain value (0.5-5.0): ").strip()
            gain = float(gain_input)
            if not (0.5 <= gain <= 5.0):
                print("⚠️  Warning: Gain outside recommended range (0.5-5.0)")
        elif choice == '7':
            print("Running full gain test...")
            os.system('python test_microphone_gain.py')
            return
        else:
            print("Invalid choice!")
            return
        
        # Update .env file
        update_env_gain(gain)
        
        # Provide guidance
        print(f"\n🎯 Set microphone gain to {gain}x")
        print("\n📋 Next steps:")
        print("1. Restart your voice assistant to apply the new gain")
        print("2. Test wake word detection")
        print("3. If still getting false positives: lower gain")
        print("4. If missing wake words: raise gain")
        
        # Suggest additional tweaks based on gain level
        if gain >= 2.5:
            print("\n⚠️  High gain detected - watch for:")
            print("   - Increased background noise amplification")
            print("   - Possible false wake word triggers")
            print("   - Consider improving model training instead")
        elif gain <= 1.5:
            print("\n📢 Low gain set - ensure:")
            print("   - You speak clearly toward the microphone")
            print("   - Microphone is positioned correctly") 
            print("   - Environment isn't too noisy")
        
    except ValueError:
        print("❌ Invalid input! Please enter a valid number.")
    except KeyboardInterrupt:
        print("\n👋 Cancelled by user.")
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    main()