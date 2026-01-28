import sounddevice as sd
from scipy.io.wavfile import write
import numpy as np
import os

DEVICE_INDEX = 1
SAMPLE_RATE = 16000
RECORD_SECONDS = 2.0
CHANNELS = 2
DIGITAL_GAIN = 1.0
DTYPE = 'float32'

BASE_DIR = os.path.dirname(__file__)
SAVE_DIR = os.path.join(BASE_DIR, "background_sound")
os.makedirs(SAVE_DIR, exist_ok=True)

sd.default.device = (DEVICE_INDEX, None)

# Mic warm-up (important for USB mics)
sd.rec(1024, samplerate=SAMPLE_RATE, channels=CHANNELS, blocking=True)

def apply_digital_gain(audio, gain):
    audio = audio * gain
    clipped = np.any(np.abs(audio) >= 1.0)
    audio = np.clip(audio, -1.0, 1.0)
    audio = (audio * 32767).astype(np.int16)
    return audio, clipped

def record_and_save(save_dir, total_samples=2500):
    print("\n🎙 ReSpeaker Lite Stereo Wake-Word Recorder")
    input("Press Enter to start...")

    for i in range(0, total_samples):
        print(f"\nRecording {i+1}/{total_samples}")

        recording = sd.rec(
            int(RECORD_SECONDS * SAMPLE_RATE),
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype=DTYPE,
            blocking=True
        )
        print(np.max(np.abs(recording)))
        recording, clipped = apply_digital_gain(recording, DIGITAL_GAIN)
        print(np.max(np.abs(recording)))
        filename = f"background_{i:05d}.wav"
        write(os.path.join(save_dir, filename), SAMPLE_RATE, recording)

        if clipped:
            print("⚠️ Clipping detected")
        print(f"✅ Saved {filename}")

        # input("Press Enter for next (Ctrl+C to stop)")

if __name__ == "__main__":
    record_and_save(SAVE_DIR, total_samples=2500)
