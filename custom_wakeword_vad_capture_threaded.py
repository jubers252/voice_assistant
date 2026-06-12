import queue
import sys
import threading
import time
from collections import deque

import numpy as np
import sounddevice as sd
import speech_recognition as sr
import webrtcvad
from openwakeword.model import Model

from speech.speech_recognizer import SpeechRecognizer

# =============================
# Audio / model configuration
# =============================
SAMPLE_RATE = 16000
CHUNK_SIZE = 1280  # 80 ms @ 16 kHz
INPUT_DEVICE_INDEX = None
DEBUG_SCORES = True
CUSTOM_MODEL_PATH = "/home/jubers/Documents/voice_assistant/Sofi_20260609_092546.onnx"

# Wakeword trigger
WAKEWORD_DETECTION_THRESHOLD = 0.30
WAKEWORD_COOLDOWN_MS = 1000

# =============================
# VAD configuration
# =============================
FRAME_MS = 20  # must be 10, 20, or 30 for webrtcvad
VAD_AGGRESSIVENESS = 2
MIN_SPEECH_MS = 250
MAX_COMMAND_MS = 6000
PRE_ROLL_MS = 300

# Hybrid VAD + energy configuration
ENERGY_SILENCE_THRESHOLD = 0.010
ENERGY_END_MS = 650
VAD_RATIO_WINDOW_FRAMES = 12
VAD_END_RATIO = 0.20
HANGOVER_MS = 300

# Wakeword-trimming configuration for STT
REMOVE_WAKEWORD_FROM_STT = True
POST_WAKE_TRIM_MS = 180
MIN_TRIMMED_MS = 250

# Callback -> distributor queue
audio_queue = queue.Queue(maxsize=1200)

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
    if status and "overflow" not in str(status).lower():
        print(f"Status flag: {status}", file=sys.stderr)

    chunk = indata[:, 0].copy()
    try:
        audio_queue.put_nowait(chunk)
    except queue.Full:
        try:
            audio_queue.get_nowait()
        except queue.Empty:
            pass
        try:
            audio_queue.put_nowait(chunk)
        except queue.Full:
            pass


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


def remove_wakeword_from_segment(segment_float32, first_hit_end_sample):
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


def _recognize_and_dispatch(segment, trigger_offset_samples, speech_recognizer, process_command, recognition_lock):
    if recognition_lock and not recognition_lock.acquire(blocking=False):
        print("[INFO] Recognition busy, skipping this segment.")
        return
    try:
        stt_segment = remove_wakeword_from_segment(segment, trigger_offset_samples)
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


def _distributor_loop(stop_event, frame_size, wake_q, vad_q, shared_state):
    while not stop_event.is_set():
        try:
            raw_chunk = audio_queue.get(timeout=0.2)
        except queue.Empty:
            continue

        chunk = normalize_chunk(raw_chunk, frame_size)

        with shared_state["lock"]:
            shared_state["audio_ring"].append(chunk)
            shared_state["global_samples"] += len(chunk)
            current_global = shared_state["global_samples"]

        try:
            wake_q.put_nowait((chunk, current_global))
        except queue.Full:
            try:
                wake_q.get_nowait()
            except queue.Empty:
                pass
            try:
                wake_q.put_nowait((chunk, current_global))
            except queue.Full:
                pass

        try:
            vad_q.put_nowait((chunk, current_global))
        except queue.Full:
            try:
                vad_q.get_nowait()
            except queue.Empty:
                pass
            try:
                vad_q.put_nowait((chunk, current_global))
            except queue.Full:
                pass


def _wakeword_loop(stop_event, wake_q, shared_state):
    model = load_model()
    last_trigger_time = 0.0

    while not stop_event.is_set():
        try:
            chunk, global_samples = wake_q.get(timeout=0.2)
        except queue.Empty:
            continue

        clipped = np.clip(chunk, -1.0, 1.0)
        audio_int16 = (clipped * 32767).astype(np.int16)
        scores = model.predict(audio_int16)

        best_name = None
        best_score = 0.0
        for name, score in scores.items():
            sc = float(score)
            if sc > best_score:
                best_score = sc
                best_name = name

        now = time.time()
        cooldown_ok = (now - last_trigger_time) * 1000.0 >= WAKEWORD_COOLDOWN_MS
        if best_score >= WAKEWORD_DETECTION_THRESHOLD and cooldown_ok:
            last_trigger_time = now
            with shared_state["lock"]:
                shared_state["trigger_global_sample"] = global_samples
            shared_state["wakeword_event"].set()
            print(f"\n🔥 Wakeword trigger: model={best_name}, score={best_score:.2f}")

        if DEBUG_SCORES and int(now * 10) % 10 == 0:
            print(f"[WW] best_score={best_score:.2f}", end="\r")


def _vad_capture_loop(stop_event, vad_q, shared_state, speech_recognizer, process_command):
    frame_size = int(SAMPLE_RATE * FRAME_MS / 1000)
    vad = webrtcvad.Vad(VAD_AGGRESSIVENESS)
    chunk_ms = (frame_size / SAMPLE_RATE) * 1000.0

    recording = False
    speech_buffer = []
    speech_ms = 0.0
    silence_ms = 0.0
    hangover_ms_left = 0.0
    recent_flags = deque(maxlen=max(VAD_RATIO_WINDOW_FRAMES, 35))
    trigger_offset_samples = None
    recognition_lock = threading.Lock()

    while not stop_event.is_set():
        try:
            chunk, global_samples = vad_q.get(timeout=0.2)
        except queue.Empty:
            continue

        frame_bytes = (np.clip(chunk, -1.0, 1.0) * 32767).astype(np.int16).tobytes()
        is_speech = vad.is_speech(frame_bytes, SAMPLE_RATE)
        recent_flags.append(1 if is_speech else 0)

        peak = float(np.max(np.abs(chunk))) if len(chunk) > 0 else 0.0
        vad_ratio = _recent_vad_ratio(recent_flags)

        if is_speech:
            hangover_ms_left = HANGOVER_MS
        else:
            hangover_ms_left = max(0.0, hangover_ms_left - chunk_ms)

        if not recording:
            if shared_state["wakeword_event"].is_set():
                with shared_state["lock"]:
                    ring_chunks = list(shared_state["audio_ring"])
                    trigger_global_sample = shared_state["trigger_global_sample"]

                recording = True
                speech_buffer = ring_chunks[-max(1, int(PRE_ROLL_MS / chunk_ms)):]
                speech_buffer.append(chunk)
                speech_ms = (sum(len(ch) for ch in speech_buffer) / SAMPLE_RATE) * 1000.0
                silence_ms = 0.0
                hangover_ms_left = HANGOVER_MS

                segment_start_global = global_samples - sum(len(ch) for ch in speech_buffer)
                trigger_offset_samples = max(0, trigger_global_sample - segment_start_global)
                print(f"\n[VAD START] peak={peak:.3f} vad_ratio={vad_ratio:.2f}")
            continue

        speech_buffer.append(chunk)
        speech_ms += chunk_ms

        if peak < ENERGY_SILENCE_THRESHOLD and vad_ratio <= VAD_END_RATIO and hangover_ms_left <= 0.0:
            silence_ms += chunk_ms
        else:
            silence_ms = 0.0

        end_by_energy = silence_ms >= ENERGY_END_MS and speech_ms >= MIN_SPEECH_MS
        end_by_max = speech_ms >= MAX_COMMAND_MS

        if DEBUG_SCORES:
            print(
                f"[REC] peak={peak:.3f} vad={int(is_speech)} vad_ratio={vad_ratio:.2f} "
                f"speech_ms={speech_ms:.0f} silence_ms={silence_ms:.0f}",
                end="\r",
            )

        if end_by_energy or end_by_max:
            end_reason = "energy_silence" if end_by_energy else "max_len"
            segment = np.concatenate(speech_buffer).astype(np.float32)
            print(f"\n[VAD END] duration={len(segment)/SAMPLE_RATE:.2f}s, reason={end_reason}")

            threading.Thread(
                target=_recognize_and_dispatch,
                args=(
                    segment,
                    trigger_offset_samples,
                    speech_recognizer,
                    process_command,
                    recognition_lock,
                ),
                daemon=True,
            ).start()

            recording = False
            speech_buffer = []
            speech_ms = 0.0
            silence_ms = 0.0
            hangover_ms_left = 0.0
            trigger_offset_samples = None
            shared_state["wakeword_event"].clear()


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

    frame_size = int(SAMPLE_RATE * FRAME_MS / 1000)
    if FRAME_MS not in (10, 20, 30):
        raise ValueError("FRAME_MS must be one of: 10, 20, 30")

    list_input_devices()
    print(
        "Listening with THREADED wakeword+VAD capture... "
        f"(ww_threshold={WAKEWORD_DETECTION_THRESHOLD}, device={INPUT_DEVICE_INDEX})"
    )

    ring_chunks = max(1, int((PRE_ROLL_MS / 1000.0) * SAMPLE_RATE / frame_size))
    shared_state = {
        "lock": threading.Lock(),
        "wakeword_event": threading.Event(),
        "trigger_global_sample": 0,
        "global_samples": 0,
        "audio_ring": deque(maxlen=ring_chunks * 20),
    }

    wake_q = queue.Queue(maxsize=400)
    vad_q = queue.Queue(maxsize=400)
    stop_event = threading.Event()

    stream = create_input_stream(frame_size)

    distributor = threading.Thread(
        target=_distributor_loop,
        args=(stop_event, frame_size, wake_q, vad_q, shared_state),
        daemon=True,
    )
    wake_thread = threading.Thread(
        target=_wakeword_loop,
        args=(stop_event, wake_q, shared_state),
        daemon=True,
    )
    vad_thread = threading.Thread(
        target=_vad_capture_loop,
        args=(stop_event, vad_q, shared_state, speech_recognizer, process_command),
        daemon=True,
    )

    with stream:
        print("Ready. Speak wakeword now...")
        distributor.start()
        wake_thread.start()
        vad_thread.start()

        try:
            while True:
                time.sleep(0.5)
        except KeyboardInterrupt:
            print("\nStopping threaded wakeword+VAD capture...")
            stop_event.set()


def main():
    run_custom_wakeword_vad_capture(
        speech_recognizer=google_speech_recognizer,
        process_command=None,
        input_device_index=INPUT_DEVICE_INDEX,
    )


if __name__ == "__main__":
    main()
