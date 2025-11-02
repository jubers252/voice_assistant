#!/usr/bin/env python3
"""
Minimal recorder: records 6 seconds from the default microphone and saves to recording.wav

Dependencies: sounddevice, soundfile (pip install sounddevice soundfile)
"""
import sounddevice as sd
import soundfile as sf
import os
import sys

OUT_FILE = 'recording.wav'
DURATION = 6.0
SAMPLE_RATE = 22050
CHANNELS = 1

def record_and_save(duration=DURATION, samplerate=SAMPLE_RATE, channels=CHANNELS, out_path=OUT_FILE):
    print(f"Recording {duration} seconds -> {out_path} (sr={samplerate}, channels={channels})")
    try:
        frames = int(duration * samplerate)
        recording = sd.rec(frames, samplerate=samplerate, channels=channels, dtype='float32')
        sd.wait()
        # soundfile expects shape (n_frames, n_channels)
        sf.write(out_path, recording, samplerate)
        print("Recording saved.")
        return out_path
    except Exception as e:
        print(f"Recording failed: {e}")
        return None

def main():
    out = record_and_save()
    if out is None:
        sys.exit(1)




if __name__ == "__main__":
    main()