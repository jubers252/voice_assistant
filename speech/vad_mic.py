#!/usr/bin/env python3
"""
Optimized Single-Pass Microphone VAD & Command Extraction Script.
Listens continuously, groups wake-word + command into a single sentence,
and processes it locally using faster-whisper.
"""

import os
import queue
import signal
import sys
import time
import string
from collections import deque

# Reduce noisy ALSA/JACK diagnostics in stderr on Raspberry Pi/Linux audio stacks
os.environ.setdefault("PYTHONWARNINGS", "ignore")
os.environ.setdefault("ALSA_LOG_LEVEL", "0")

import numpy as np
import sounddevice as sd
import webrtcvad
from faster_whisper import WhisperModel
import speech_recognition as sr
from speech.speech_recognizer import SpeechRecognizer

# Global flag for clean exit
RUNNING = True

def _signal_handler(sig, frame):
    global RUNNING
    RUNNING = False
    print("\nStopping VAD system smoothly...")

def list_input_devices():
    devices = sd.query_devices()
    print("Available input devices:")
    for i, dev in enumerate(devices):
        if dev.get("max_input_channels", 0) > 0:
            print(
                f"  {i}: {dev['name']} "
                f"(inputs={dev['max_input_channels']}, default_sr={dev['default_samplerate']})"
            )

def pcm16_bytes_from_float32(audio_float: np.ndarray) -> bytes:
    audio_clipped = np.clip(audio_float, -1.0, 1.0)
    audio_int16 = (audio_clipped * 32767).astype(np.int16)
    return audio_int16.tobytes()

def rms_dbfs(audio_float: np.ndarray) -> float:
    rms = np.sqrt(np.mean(np.square(audio_float)) + 1e-12)
    return 20.0 * np.log10(rms + 1e-12)

def process_extracted_text(
    raw_text,
    segment=None,
    sample_rate=16000,
    process_command=None,
    speech_recognizer=None,
):
    """
    Cleans the transcript and separates the wake word from the rest of the command.
    """
    cleaned = raw_text.lower().strip().translate(str.maketrans("", "", string.punctuation))
    words = cleaned.split()
    
    if not words:
        return

    # Broad vocabulary matching to handle common local whisper variations of 'Sofi'
    wake_words = {"sofi", "sophie", "sophia", "sofee", "softly", "sobe", "surface"}
    
    found_wake_index = -1
    matched_wake = None
    
    # Search the first 3 words of the sentence for the wake word trigger
    for i, word in enumerate(words[:3]): 
        if word in wake_words:
            found_wake_index = i
            matched_wake = word
            break
            
    if found_wake_index != -1:
        # Extract everything following the matched wake word as your actual intent
        command = " ".join(words[found_wake_index + 1:]).strip()
        
        if command:
            print(f" 🔥 [MATCH SUCCESS] Wake Word: '{matched_wake}' | Command Isolated: '{command}'")

            final_command = command

            if segment is not None and speech_recognizer is not None:
                try:
                    audio_data = sr.AudioData(
                        frame_data=pcm16_bytes_from_float32(segment),
                        sample_rate=sample_rate,
                        sample_width=2,
                    )
                    recognized_command = speech_recognizer._recognize_audio(audio_data)
                    if recognized_command:
                        final_command = recognized_command.strip()
                        print(f" ✅ [GOOGLE RESULT] {final_command}")
                    else:
                        print(" ⚠️ [GOOGLE RESULT] Empty result, using local extracted command.")
                except Exception as e:
                    print(f" ⚠️ [GOOGLE ERROR] Failed to recognize segment via Google: {e}")

            if callable(process_command):
                try:
                    process_command(final_command)
                except Exception as callback_error:
                    print(f" ⚠️ [PROCESS COMMAND ERROR] {callback_error}")
        else:
            print(f" ⚠️ [MATCH] Heard wake word '{matched_wake}', but no command followed.")
    else:
        print(f" 💤 [IGNORED] No wake word detected at start. Dropping phrase: '{cleaned}'")

def run_vad(
    device=None,
    sample_rate=16000,
    frame_ms=30,
    aggressiveness=3,
    debug=False,
    start_trigger_frames=3,
    end_trigger_frames=35, # Hardcoded default to ~1.05s hang-time
    transcribe=True,
    whisper_model_name="tiny.en",
    language="en",
    task="transcribe",
    beam_size=1,
    best_of=1,
    initial_prompt=None,
    process_command=None,
):
    vad = webrtcvad.Vad(aggressiveness)

    frame_size = int(sample_rate * frame_ms / 1000)
    if frame_size <= 0:
        raise ValueError("Invalid frame size. Check sample_rate/frame_ms.")

    if frame_ms not in (10, 20, 30):
        raise ValueError("frame-ms must be one of: 10, 20, 30")

    audio_queue = queue.Queue()
    speech_state = False
    
    # We use the max of start or a solid safety window to maintain clean sizing
    max_history = max(start_trigger_frames, end_trigger_frames, 35)
    recent_flags = deque(maxlen=max_history)
    
    # Pre-roll ring buffer holds audio frames captured right BEFORE validation triggers
    pre_roll_buffer = deque(maxlen=start_trigger_frames)

    model = None
    speech_buffer = []
    shared_recognizer = sr.Recognizer()
    google_speech_recognizer = SpeechRecognizer(
        recognizer=shared_recognizer,
        audio_processor=None,
        device_index=None,
        pixel_led=None,
    )
    if transcribe:
        print(f"Loading faster-whisper model '{whisper_model_name}'...")
        # Running local int8 optimized parameters for CPU execution speed
        model = WhisperModel(whisper_model_name, device="cpu", compute_type="int8")
        print("faster-whisper model loaded and ready.")

    def callback(indata, frames, time_info, status):
        if status:
            print(f"[audio status] {status}")
        mono = indata[:, 0] if indata.ndim > 1 else indata
        audio_queue.put(mono.copy())

    print("\n[System] Microphone stream active. Speak naturally: 'Sofi, [your command]'...")

    # Normalize device selection:
    # - None => default device
    # - int index => use index
    # - invalid index => fallback to default
    selected_device = device
    try:
        if selected_device is not None:
            devices = sd.query_devices()
            if not isinstance(selected_device, int) or selected_device < 0 or selected_device >= len(devices):
                print(f"[AUDIO] Invalid device '{selected_device}', falling back to system default input.")
                selected_device = None
    except Exception as e:
        print(f"[AUDIO] Could not validate device index ({e}). Falling back to system default input.")
        selected_device = None

    try:
        input_stream = sd.InputStream(
            samplerate=sample_rate,
            channels=1,
            dtype="float32",
            blocksize=frame_size,
            device=selected_device,
            callback=callback,
        )
    except Exception as e:
        raise RuntimeError(
            f"Failed to open microphone input stream (device={selected_device}, sample_rate={sample_rate}). "
            f"Underlying error: {e}. "
            f"Try running list_input_devices() and set a valid input device index."
        )

    with input_stream:
        while RUNNING:
            try:
                chunk = audio_queue.get(timeout=0.2)
            except queue.Empty:
                continue

            if len(chunk) != frame_size:
                if len(chunk) < frame_size:
                    padded = np.zeros(frame_size, dtype=np.float32)
                    padded[: len(chunk)] = chunk
                    chunk = padded
                else:
                    chunk = chunk[:frame_size]

            # Constantly log incoming history to prevent clipping the first word
            pre_roll_buffer.append(chunk.copy())

            frame_bytes = pcm16_bytes_from_float32(chunk)
            is_speech = vad.is_speech(frame_bytes, sample_rate)

            recent_flags.append(1 if is_speech else 0)
            now = time.strftime("%H:%M:%S")

            if not speech_state:
                # Transition to SPEECH_START
                if len(recent_flags) >= start_trigger_frames and sum(
                    list(recent_flags)[-start_trigger_frames:]
                ) >= start_trigger_frames:
                    speech_state = True
                    print(f"\n[{now}] 🎙️ SPEECH_START")
                    if transcribe:
                        # Pre-populate buffer with the trailing pre-roll audio chunks
                        speech_buffer = list(pre_roll_buffer)
            else:
                # Accumulate the continuous speech array data chunks
                if transcribe:
                    speech_buffer.append(chunk.copy())

                # CRITICAL FIX: Set a high frame threshold (35 frames = 1.05 seconds) 
                # to prevent mid-sentence silence cutting off the command text
                required_silence_frames = end_trigger_frames

                if len(recent_flags) >= required_silence_frames and sum(
                    list(recent_flags)[-required_silence_frames:]
                ) == 0:
                    speech_state = False
                    print(f"[{now}] 🛑 SPEECH_END")

                    if transcribe and model is not None and len(speech_buffer) > 0:
                        segment = np.concatenate(speech_buffer).astype(np.float32)

                        # Guard against very short/noisy segments that can stall slower STT paths
                        min_samples = int(sample_rate * 0.35)
                        if segment.size < min_samples:
                            print(f"[{now}] TRANSCRIPT: skipped short segment ({segment.size} samples)")
                            speech_buffer = []
                            continue
                        
                        # Highly optimized local inference transcription flags
                        segments, info = model.transcribe(
                            segment,
                            language=language,
                           
                      
                        )
                        text = " ".join(seg.text.strip() for seg in segments).strip()
                        
                        if text:
                            print(f"[{now}] FULL TRANSCRIPT: \"{text}\"")
                            process_extracted_text(
                                text,
                                segment,
                                sample_rate=sample_rate,
                                process_command=process_command,
                                speech_recognizer=google_speech_recognizer,
                            )
                        else:
                            print(f"[{now}] TRANSCRIPT: (empty or unrecognized sound)")

                        # Reset per-utterance buffer to avoid growing memory and repeated stale transcribes
                        speech_buffer = []

            if debug:
                level = rms_dbfs(chunk)
                print(f"[{now}] vad={int(is_speech)} rms_dbfs={level:.1f}")

    print("Microphone stream closed cleanly.")

DEFAULT_CONFIG = {
    "list_devices": False,
    "device": None,
    "aggressiveness": 3,
    "frame_ms": 35,
    "sample_rate": 16000,
    "debug": False,
    "start_trigger_frames": 3,
    "end_trigger_frames": 35,
    "whisper_model": "small.en",
}

def main():
    global RUNNING
    cfg = DEFAULT_CONFIG

    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    if cfg["list_devices"]:
        list_input_devices()
        return

    try:
        run_vad(
            device=cfg["device"],
            sample_rate=cfg["sample_rate"],
            frame_ms=cfg["frame_ms"],
            aggressiveness=cfg["aggressiveness"],
            debug=cfg["debug"],
            start_trigger_frames=cfg["start_trigger_frames"],
            end_trigger_frames=cfg["end_trigger_frames"],
            whisper_model_name=cfg["whisper_model"],
        )
    except KeyboardInterrupt:
        RUNNING = False
        print("\nInterrupted by user execution.")
    except Exception as e:
        print(f"System Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()