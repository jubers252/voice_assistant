import queue
import sys
import threading
from collections import deque

import numpy as np
import sounddevice as sd
import webrtcvad
from openwakeword.model import Model
import speech_recognition as sr

from speech.speech_recognizer import SpeechRecognizer

# =============================
# Audio / model configuration
# =============================
SAMPLE_RATE = 16000
CHUNK_SIZE = 1280  # 80 ms @ 16 kHz
DETECTION_THRESHOLD = 0.30
INPUT_DEVICE_INDEX = None
DEBUG_SCORES = True
CUSTOM_MODEL_PATH = "/home/jubers/Documents/voice_assistant/Sofi_20260609_092546.onnx"

# =============================
# VAD configuration (WebRTC frame-based)
# =============================
FRAME_MS = 20                    # must be 10, 20, or 30 for webrtcvad
VAD_AGGRESSIVENESS = 2           # 0 (lenient) -> 3 (strict)
START_TRIGGER_FRAMES = 3         # start when recent speech frames reach this
END_TRIGGER_FRAMES = 25          # end when recent frames are all non-speech (~500ms @20ms)
MIN_SPEECH_MS = 350              # ignore too-short captures
MAX_SPEECH_MS = 7000             # lower cap for command-oriented capture
PRE_ROLL_MS = 300                # prepend context before VAD start

# Hybrid VAD + energy configuration
ENERGY_START_THRESHOLD = 0.020    # start assist in noisy VAD misses
ENERGY_SILENCE_THRESHOLD = 0.010  # end assist; tune per mic/noise floor
ENERGY_END_MS = 650               # end when low energy persists this long

# VAD smoothing / hangover
VAD_RATIO_WINDOW_FRAMES = 12
VAD_START_RATIO = 0.35
VAD_END_RATIO = 0.20
HANGOVER_MS = 300

# Wakeword-trimming configuration for STT
REMOVE_WAKEWORD_FROM_STT = True
POST_WAKE_TRIM_MS = 180
MIN_TRIMMED_MS = 250

# Thread-safe queue for callback -> main loop (larger headroom for continuity)
audio_queue = queue.Queue(maxsize=800)

shared_recognizer = sr.Recognizer()
google_speech_recognizer = SpeechRecognizer(
    recognizer=shared_recognizer,
    audio_processor=None,
    device_index=None,
    pixel_led=None,
)

def list_input_devices():
    print("Available input devices:")
    try:
        devices = sd.query_devices()
        for i, dev in enumerate(devices):
            if dev.get("max_input_channels", 0) > 0:
                print(
                    f"  {i}: {dev['name']} "
                    f"(inputs={dev['max_input_channels']}, default_sr={dev['default_samplerate']})"
                )
    except Exception as e:
        print(f"Failed to list devices: {e}")


def audio_callback(indata, frames, time_info, status):
    """Capture mic frames quickly; no heavy processing here."""
    # input_overflow is non-fatal; avoid noisy logs in tight callback loop.
    if status and "overflow" not in str(status).lower():
        print(f"Status flag: {status}", file=sys.stderr)

    chunk = indata[:, 0].copy()  # mono float32 chunk
    try:
        audio_queue.put_nowait(chunk)
    except queue.Full:
        # Drop oldest chunk to keep real-time behavior.
        try:
            audio_queue.get_nowait()
        except queue.Empty:
            pass
        try:
            audio_queue.put_nowait(chunk)
        except queue.Full:
            pass


def detect_wakeword_in_segment(oww_model, segment_float32):
    """
    Run wakeword detection over a full captured segment by scanning
    with CHUNK_SIZE windows.

    Returns:
      (detected, best_model, best_score, first_hit_end_sample)
    where first_hit_end_sample is the sample index right after the first
    threshold-crossing wakeword chunk (or None if not detected).
    """
    if len(segment_float32) < CHUNK_SIZE:
        return False, None, 0.0, None

    # Float32 [-1..1] -> int16
    clipped = np.clip(segment_float32, -1.0, 1.0)
    audio_int16 = (clipped * 32767).astype(np.int16)
    best_model = None
    best_score = 0.0
    detected = False
    first_hit_end_sample = None

    # Process full segment in model-sized windows
    for i in range(0, len(audio_int16) - CHUNK_SIZE + 1, CHUNK_SIZE):
        frame = audio_int16[i : i + CHUNK_SIZE]
        scores = oww_model.predict(frame)

        for model_name, score in scores.items():
            if score > best_score:
                best_score = float(score)
                best_model = model_name
            if score >= DETECTION_THRESHOLD:
                detected = True
                if first_hit_end_sample is None:
                    first_hit_end_sample = i + CHUNK_SIZE

    return detected, best_model, best_score, first_hit_end_sample


def load_model():
    print("Loading openWakeWord model...")
    try:
        return Model(wakeword_models=[CUSTOM_MODEL_PATH], inference_framework="onnx")
    except Exception as e:
        print(f"Failed to initialize openWakeWord model: {e}")
        raise


def create_input_stream(frame_size):
    try:
        return sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype="float32",
            blocksize=frame_size,
            device=INPUT_DEVICE_INDEX,
            callback=audio_callback,
        )
    except Exception as e:
        print(f"Failed to open input stream: {e}")
        print("Tip: set INPUT_DEVICE_INDEX to a valid microphone index from the list above.")
        raise


def normalize_chunk(raw_chunk, frame_size):
    if len(raw_chunk) == frame_size:
        return raw_chunk
    if len(raw_chunk) < frame_size:
        padded = np.zeros(frame_size, dtype=np.float32)
        padded[: len(raw_chunk)] = raw_chunk
        return padded
    return raw_chunk[:frame_size]


def _recent_vad_ratio(recent_flags):
    if not recent_flags:
        return 0.0
    return float(sum(recent_flags)) / float(len(recent_flags))


def should_start_recording(recent_flags, peak):
    strong_consecutive_vad = len(recent_flags) >= START_TRIGGER_FRAMES and sum(
        list(recent_flags)[-START_TRIGGER_FRAMES:]
    ) >= START_TRIGGER_FRAMES
    vad_ratio = _recent_vad_ratio(recent_flags)
    energy_start = peak >= ENERGY_START_THRESHOLD
    return strong_consecutive_vad or vad_ratio >= VAD_START_RATIO or energy_start


def should_end_recording(recent_flags, speech_ms, silence_ms, hangover_ms_left):
    vad_ratio = _recent_vad_ratio(recent_flags)
    end_by_vad_silence = (
        len(recent_flags) >= END_TRIGGER_FRAMES
        and sum(list(recent_flags)[-END_TRIGGER_FRAMES:]) == 0
    ) or (len(recent_flags) >= 4 and vad_ratio <= VAD_END_RATIO and hangover_ms_left <= 0.0)
    end_by_energy_silence = silence_ms >= ENERGY_END_MS and hangover_ms_left <= 0.0
    end_by_max_len = speech_ms >= MAX_SPEECH_MS
    return end_by_vad_silence, end_by_energy_silence, end_by_max_len, vad_ratio


def remove_wakeword_from_segment(segment_float32, first_hit_end_sample):
    """
    Remove wakeword portion from the beginning of a captured segment before STT.
    Trims up to: first_hit_end_sample + POST_WAKE_TRIM_MS.
    Falls back to original segment if trimmed result is too short.
    """
    if (
        not REMOVE_WAKEWORD_FROM_STT
        or first_hit_end_sample is None
        or first_hit_end_sample <= 0
    ):
        return segment_float32

    trim_extra_samples = int((POST_WAKE_TRIM_MS / 1000.0) * SAMPLE_RATE)
    trim_start = max(0, int(first_hit_end_sample) + trim_extra_samples)

    if trim_start >= len(segment_float32):
        return segment_float32

    trimmed = segment_float32[trim_start:]
    min_trimmed_samples = int((MIN_TRIMMED_MS / 1000.0) * SAMPLE_RATE)
    if len(trimmed) < min_trimmed_samples:
        return segment_float32

    return trimmed


def process_recording_end(
    oww_model,
    speech_buffer,
    speech_ms,
    end_reason,
    speech_recognizer=None,
    process_command=None,
    recognition_lock=None,
):
    segment = np.concatenate(speech_buffer).astype(np.float32)
    duration_sec = len(segment) / SAMPLE_RATE
    print(
        f"[VAD END] duration={duration_sec:.2f}s, reason={end_reason}"
    )

    if speech_ms >= MIN_SPEECH_MS:
        detected, best_model, best_score, first_hit_end_sample = detect_wakeword_in_segment(
            oww_model, segment
        )
        if detected:
            print(
                f"🔥 Wakeword detected in captured audio: "
                f"model={best_model}, best_score={best_score:.2f}"
            )
            def _recognize_and_process():
                if recognition_lock and not recognition_lock.acquire(blocking=False):
                    print("[INFO] Recognition busy, skipping this segment.")
                    return
                try:
                    stt_segment = remove_wakeword_from_segment(
                        segment, first_hit_end_sample
                    )
                    clipped = np.clip(stt_segment, -1.0, 1.0)
                    audio_int16 = (clipped * 32767).astype(np.int16)
                    audio_data = sr.AudioData(audio_int16.tobytes(), SAMPLE_RATE, 2)
                    recognized_command = speech_recognizer._recognize_audio(audio_data)
                    print(f"🎙️ Recognized command: {recognized_command}")
                    if recognized_command and process_command:
                        process_command(recognized_command)
                finally:
                    if recognition_lock and recognition_lock.locked():
                        recognition_lock.release()

            threading.Thread(target=_recognize_and_process, daemon=True).start()
            return True
        else:
            print(
                f"[NO WAKEWORD] best_model={best_model}, "
                f"best_score={best_score:.2f}"
            )
            return None
    else:
        print(
            f"[SKIP] Captured speech too short: {speech_ms:.0f}ms "
            f"(min={MIN_SPEECH_MS}ms)"
        )
        return None

def run_custom_wakeword_vad_capture(
    speech_recognizer=None,
    process_command=None,
    input_device_index=None,
):
    global INPUT_DEVICE_INDEX
    if input_device_index is not None:
        INPUT_DEVICE_INDEX = input_device_index
    if speech_recognizer is None:
        speech_recognizer = google_speech_recognizer

    oww_model = load_model()

    list_input_devices()
    print(
        "Listening with VAD capture... "
        f"(threshold={DETECTION_THRESHOLD}, device={INPUT_DEVICE_INDEX})"
    )

    frame_size = int(SAMPLE_RATE * FRAME_MS / 1000)
    if FRAME_MS not in (10, 20, 30):
        raise ValueError("FRAME_MS must be one of: 10, 20, 30")

    vad = webrtcvad.Vad(VAD_AGGRESSIVENESS)
    stream = create_input_stream(frame_size)

    recording = False
    speech_buffer = []
    speech_ms = 0.0
    silence_ms = 0.0
    hangover_ms_left = 0.0
    debug_counter = 0

    preroll_chunks = max(1, int(PRE_ROLL_MS / (CHUNK_SIZE / SAMPLE_RATE * 1000.0)))
    pre_roll = deque(maxlen=preroll_chunks)
    recent_flags = deque(maxlen=max(START_TRIGGER_FRAMES, END_TRIGGER_FRAMES, VAD_RATIO_WINDOW_FRAMES, 35))

    recognition_lock = threading.Lock()
    with stream:
        print("Ready. Speak now...")
        while True:
            try:
                raw_chunk = audio_queue.get(timeout=1.0)
            except queue.Empty:
                continue

            chunk = normalize_chunk(raw_chunk, frame_size)
            chunk_ms = (len(chunk) / SAMPLE_RATE) * 1000.0
            peak = float(np.max(np.abs(chunk))) if len(chunk) > 0 else 0.0

            pre_roll.append(chunk)

            frame_bytes = (np.clip(chunk, -1.0, 1.0) * 32767).astype(np.int16).tobytes()
            is_speech = vad.is_speech(frame_bytes, SAMPLE_RATE)
            recent_flags.append(1 if is_speech else 0)

            if is_speech:
                hangover_ms_left = HANGOVER_MS
            else:
                hangover_ms_left = max(0.0, hangover_ms_left - chunk_ms)

            debug_counter += 1
            if recording:
                vad_ratio = _recent_vad_ratio(recent_flags)
                if peak < ENERGY_SILENCE_THRESHOLD and vad_ratio <= VAD_END_RATIO and hangover_ms_left <= 0.0:
                    silence_ms += chunk_ms
                else:
                    silence_ms = 0.0

            if DEBUG_SCORES and debug_counter % 10 == 0:
                state = "REC" if recording else "IDLE"
                print(
                    f"[{state}] peak={peak:.3f} vad={int(is_speech)} "
                    f"vad_ratio={_recent_vad_ratio(recent_flags):.2f} "
                    f"speech_ms={speech_ms:.0f} silence_ms={silence_ms:.0f} "
                    f"hang={hangover_ms_left:.0f}",
                    end="\r",
                )

            if not recording:
                if should_start_recording(recent_flags, peak):
                    recording = True
                    speech_buffer = list(pre_roll)
                    speech_buffer.append(chunk)
                    speech_ms = (sum(len(ch) for ch in speech_buffer) / SAMPLE_RATE) * 1000.0
                    silence_ms = 0.0
                    hangover_ms_left = HANGOVER_MS
                    print(f"\n[VAD START] peak={peak:.3f} vad_ratio={_recent_vad_ratio(recent_flags):.2f}")
                continue

            speech_buffer.append(chunk)
            speech_ms += chunk_ms

            (
                end_by_vad_silence,
                end_by_energy_silence,
                end_by_max_len,
                vad_ratio,
            ) = should_end_recording(
                recent_flags, speech_ms, silence_ms, hangover_ms_left
            )
            if end_by_vad_silence or end_by_energy_silence or end_by_max_len:
                if end_by_max_len:
                    end_reason = "max_len"
                elif end_by_energy_silence:
                    end_reason = "energy_silence"
                else:
                    end_reason = "vad_silence"

                if DEBUG_SCORES:
                    print(
                        f"\n[VAD STOP] reason={end_reason} vad_ratio={vad_ratio:.2f} "
                        f"silence_ms={silence_ms:.0f} speech_ms={speech_ms:.0f}"
                    )

                process_recording_end(
                    oww_model,
                    speech_buffer,
                    speech_ms,
                    end_reason,
                    speech_recognizer=speech_recognizer,
                    process_command=process_command,
                    recognition_lock=recognition_lock,
                )
                recording = False
                speech_buffer = []
                speech_ms = 0.0
                silence_ms = 0.0
                hangover_ms_left = 0.0


def main():
    run_custom_wakeword_vad_capture(
        speech_recognizer=google_speech_recognizer,
        process_command=None,
        input_device_index=INPUT_DEVICE_INDEX,
    )


if __name__ == "__main__":
    main()
