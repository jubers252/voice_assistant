#!/usr/bin/env python3
"""
Test script to find optimal digital gain for MEMS INMP441 microphone
This helps you determine the best gain setting for your specific setup
"""

import numpy as np
import sounddevice as sd
import time
import matplotlib.pyplot as plt
from contextlib import contextmanager
import os

@contextmanager
def suppress_alsa_errors():
    """Context manager to suppress ALSA/JACK error output"""
    try:
        devnull = os.open(os.devnull, os.O_WRONLY)
        old_stderr = os.dup(2)
        os.dup2(devnull, 2)
        os.close(devnull)
        yield
    finally:
        os.dup2(old_stderr, 2)
        os.close(old_stderr)

def test_microphone_gain():
    """Test different gain levels to find optimal setting"""
    print("MEMS INMP441 Microphone Gain Testing")
    print("=" * 40)
    
    # Test parameters
    duration = 3.0  # seconds
    sample_rate = 22050
    gain_levels = [1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0]
    
    print("This test will record your voice at different gain levels.")
    print("Speak at a normal volume during each recording.")
    print("Press Enter when ready to start...")
    input()
    
    results = {}
    
    for gain in gain_levels:
        print(f"\n--- Testing gain level: {gain}x ---")
        print("Recording in 3 seconds... Get ready to speak!")
        time.sleep(3)
        
        try:
            with suppress_alsa_errors():
                # Record audio
                print("🎤 Recording... Speak normally!")
                audio = sd.rec(
                    int(duration * sample_rate), 
                    samplerate=sample_rate, 
                    channels=1, 
                    dtype='float32'
                )
                sd.wait()
            
            # Apply gain
            audio_gained = audio.flatten() * gain
            
            # Prevent clipping
            max_val = np.max(np.abs(audio_gained))
            if max_val > 1.0:
                audio_gained = audio_gained / max_val
                clipped = True
            else:
                clipped = False
            
            # Calculate metrics
            rms_energy = np.sqrt(np.mean(audio_gained ** 2))
            peak_amplitude = np.max(np.abs(audio_gained))
            snr_estimate = 20 * np.log10(rms_energy / 0.01) if rms_energy > 0.01 else 0
            
            results[gain] = {
                'rms_energy': rms_energy,
                'peak_amplitude': peak_amplitude,
                'snr_estimate': snr_estimate,
                'clipped': clipped,
                'audio': audio_gained
            }
            
            print(f"✓ RMS Energy: {rms_energy:.4f}")
            print(f"✓ Peak Amplitude: {peak_amplitude:.4f}")
            print(f"✓ Est. SNR: {snr_estimate:.1f} dB")
            if clipped:
                print("⚠️  Audio was clipped (normalized)")
            
            time.sleep(1)
            
        except Exception as e:
            print(f"❌ Error at gain {gain}x: {e}")
            continue
    
    # Analyze results
    print("\n" + "=" * 50)
    print("GAIN LEVEL ANALYSIS")
    print("=" * 50)
    
    best_gain = None
    best_score = 0
    
    for gain, data in results.items():
        # Score based on energy, but penalize clipping
        score = data['rms_energy'] * (0.5 if data['clipped'] else 1.0)
        
        status = "🟡 CLIPPED" if data['clipped'] else "🟢 CLEAN"
        recommendation = ""
        
        if data['rms_energy'] < 0.01:
            recommendation = "❌ Too quiet"
        elif data['rms_energy'] > 0.3:
            recommendation = "⚠️  Very loud"
        elif data['clipped']:
            recommendation = "⚠️  Clipped - reduce gain"
        elif 0.05 <= data['rms_energy'] <= 0.15:
            recommendation = "✅ GOOD RANGE"
        elif 0.02 <= data['rms_energy'] <= 0.05:
            recommendation = "🔵 Acceptable"
        
        print(f"Gain {gain:3.1f}x: Energy={data['rms_energy']:6.4f}, Peak={data['peak_amplitude']:6.4f}, {status}, {recommendation}")
        
        if score > best_score and not data['clipped'] and data['rms_energy'] >= 0.02:
            best_gain = gain
            best_score = score
    
    print("\n" + "=" * 50)
    print("RECOMMENDATIONS")
    print("=" * 50)
    
    if best_gain:
        print(f"🎯 RECOMMENDED GAIN: {best_gain}x")
        print(f"   - Good energy level: {results[best_gain]['rms_energy']:.4f}")
        print(f"   - No clipping: {results[best_gain]['peak_amplitude']:.4f} < 1.0")
        
        # Code to update
        print(f"\n📝 To use this gain, add this to your voice_assistant.py:")
        print(f"   audio_processors.set_digital_gain({best_gain})")
    else:
        print("❌ No optimal gain found. Try speaking louder or check microphone connection.")
    
    # Additional tips
    print(f"\n💡 TIPS:")
    print(f"   - For quiet environments: Use higher gain (2.0-3.0x)")
    print(f"   - For noisy environments: Use moderate gain (1.5-2.0x)")
    print(f"   - If getting false wake words: Lower gain or improve model training")
    print(f"   - If missing real wake words: Increase gain")
    
    # Offer to plot results
    try:
        plot_choice = input("\nWould you like to see a visual plot of the results? (y/n): ").lower().strip()
        if plot_choice in ['y', 'yes']:
            plot_gain_results(results)
    except KeyboardInterrupt:
        print("\nTest completed!")

def plot_gain_results(results):
    """Plot the gain test results"""
    try:
        gains = list(results.keys())
        energies = [results[g]['rms_energy'] for g in gains]
        peaks = [results[g]['peak_amplitude'] for g in gains]
        clipped = [results[g]['clipped'] for g in gains]
        
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 8))
        
        # Plot RMS Energy
        colors = ['red' if c else 'green' for c in clipped]
        ax1.bar(gains, energies, color=colors, alpha=0.7)
        ax1.set_xlabel('Gain Level (x)')
        ax1.set_ylabel('RMS Energy')
        ax1.set_title('Microphone Gain vs Audio Energy')
        ax1.grid(True, alpha=0.3)
        
        # Add good range indicator
        ax1.axhspan(0.05, 0.15, alpha=0.2, color='green', label='Good Range')
        ax1.legend()
        
        # Plot Peak Amplitude
        ax2.bar(gains, peaks, color=colors, alpha=0.7)
        ax2.set_xlabel('Gain Level (x)')
        ax2.set_ylabel('Peak Amplitude')
        ax2.set_title('Microphone Gain vs Peak Amplitude')
        ax2.axhline(y=1.0, color='red', linestyle='--', label='Clipping Threshold')
        ax2.grid(True, alpha=0.3)
        ax2.legend()
        
        plt.tight_layout()
        plt.show()
        
    except ImportError:
        print("Matplotlib not available for plotting. Install with: pip install matplotlib")
    except Exception as e:
        print(f"Plotting failed: {e}")

if __name__ == "__main__":
    try:
        test_microphone_gain()
    except KeyboardInterrupt:
        print("\nTest cancelled by user.")
    except Exception as e:
        print(f"Test failed: {e}")