import queue
import re
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


class WakeWordManager:
    """Class-based threaded wakeword + VAD manager."""

    # Audio / model configuration
    SAMPLE_RATE = 16000
    CHUNK_SIZE = 1280  # 80 ms @ 16 kHz
    DEBUG_SCORES = True
    CUSTOM_MODEL_PATH = "/home/jubers/Documents/voice_assistant/Sofi_20260609_092546.onnx"

    # Wakeword triggers
    WAKEWORD_DETECTION_THRESHOLD = 0.40
    WAKEWORD_COOLDOWN_MS = 500

    # VAD configuration
    FRAME_MS = 20  # must be 10, 20, or 30 for webrtcvad
    VAD_AGGRESSIVENESS = 2
    MIN_SPEECH_MS = 250
    MAX_COMMAND_MS = 6000
    PRE_ROLL_MS = 300
    MAX_SILENCE_MS = 1500
    ENERGY_SILENCE_THRESHOLD = 0.008
    NOISE_MULTIPLIER = 3.0
    NOISE_CALIBRATION_SEC = 2
    ENERGY_END_MS = 700
    VAD_RATIO_WINDOW_FRAMES = 12
    VAD_END_RATIO = 0.10
    HANGOVER_MS = 80

    # Wakeword-trimming configuration for STT
    REMOVE_WAKEWORD_FROM_STT = True
    POST_WAKE_TRIM_MS = 180
    MIN_TRIMMED_MS = 250

    def __init__(
        self,
        audio_processors=None,
        recognizer=None,
        pixel_led=None,
        sample_rate=16000,
        energy_threshold=0.0001,
        confidence_threshold=0.75,
        templates_dir=None,
        input_device_index=None,
    ):
        self.audio_processors = audio_processors
        self.recognizer = recognizer
        self.pixel_led = pixel_led
        self.sample_rate = sample_rate
        self.energy_threshold = energy_threshold
        self.confidence_threshold = confidence_threshold
        self.templates_dir = templates_dir
        self.ambient_noise_floor = 0.003
        self.input_device_index = input_device_index

        self.audio_queue = queue.Queue(maxsize=1200)
        self.wake_q = queue.Queue(maxsize=400)
        self.vad_q = queue.Queue(maxsize=400)

        self.stop_event = threading.Event()
        self.detection_running = False

        self.stream = None
        self.threads = []

        self.shared_recognizer = sr.Recognizer()
        self.google_speech_recognizer = SpeechRecognizer(
            recognizer=self.shared_recognizer,
            audio_processor=None,
            device_index=None,
            pixel_led=None,
        )

        self.speech_recognizer = recognizer if recognizer is not None else self.google_speech_recognizer
        self.process_command_callback = None

        self.shared_state = None
        self.recognition_lock = threading.Lock()
        self.is_recording = False

    def list_input_devices(self):
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

    def _audio_callback(self, indata, frames, time_info, status):
        if status and "overflow" not in str(status).lower():
            print(f"Status flag: {status}", file=sys.stderr)

        chunk = indata[:, 0].copy()
        try:
            self.audio_queue.put_nowait(chunk)
        except queue.Full:
            try:
                self.audio_queue.get_nowait()
            except queue.Empty:
                pass
            try:
                self.audio_queue.put_nowait(chunk)
            except queue.Full:
                pass

    def _load_model(self):
        print("Loading openWakeWord model...")
        try:
            return Model(wakeword_models=[self.CUSTOM_MODEL_PATH], inference_framework="onnx")
        except Exception as e:
            print(f"Failed to initialize openWakeWord model: {e}")
            raise

    def _create_input_stream(self, frame_size):
        try:
            return sd.InputStream(
                samplerate=self.SAMPLE_RATE,
                channels=1,
                dtype="float32",
                blocksize=frame_size,
                device=self.input_device_index,
                callback=self._audio_callback,
            )
        except Exception as e:
            print(f"Failed to open input stream: {e}")
            print("Tip: set input_device_index to a valid microphone index from the list above.")
            raise

    @staticmethod
    def _normalize_chunk(raw_chunk, frame_size):
        if len(raw_chunk) == frame_size:
            return raw_chunk
        if len(raw_chunk) < frame_size:
            padded = np.zeros(frame_size, dtype=np.float32)
            padded[: len(raw_chunk)] = raw_chunk
            return padded
        return raw_chunk[:frame_size]

    @staticmethod
    def _recent_vad_ratio(recent_flags):
        if not recent_flags:
            return 0.0
        return float(sum(recent_flags)) / float(len(recent_flags))

    def _calibrate_noise_floor(self):
        """
        Measure ambient room noise before starting detection.
        """
        samples = []

        print("[CAL] Measuring ambient noise... stay quiet")

        start = time.time()

        while time.time() - start < self.NOISE_CALIBRATION_SEC:
            try:
                chunk = self.audio_queue.get(timeout=0.1)

                rms = float(
                    np.sqrt(
                        np.mean(chunk.astype(np.float32) ** 2)
                    )
                )

                samples.append(rms)

            except queue.Empty:
                pass

        if samples:
            self.ambient_noise_floor = float(np.percentile(samples, 20))

        print(
            f"[CAL] Ambient floor={self.ambient_noise_floor:.6f}",
            f"Current={rms:.5f}"
        )

    def _remove_wakeword_from_segment(self, segment_float32, first_hit_end_sample):
        if (
            not self.REMOVE_WAKEWORD_FROM_STT
            or first_hit_end_sample is None
            or first_hit_end_sample <= 0
        ):
            return segment_float32

        trim_extra_samples = int((self.POST_WAKE_TRIM_MS / 1000.0) * self.SAMPLE_RATE)
        trim_start = max(0, int(first_hit_end_sample) + trim_extra_samples)

        if trim_start >= len(segment_float32):
            return segment_float32

        trimmed = segment_float32[trim_start:]
        min_trimmed_samples = int((self.MIN_TRIMMED_MS / 1000.0) * self.SAMPLE_RATE)
        if len(trimmed) < min_trimmed_samples:
            return segment_float32
        return trimmed

    def _recognize_and_dispatch(self, segment, trigger_offset_samples):
        if not self.recognition_lock.acquire(blocking=False):
            print("[INFO] Recognition busy, skipping this segment.")
            return
        try:
            stt_segment = self._remove_wakeword_from_segment(segment, trigger_offset_samples)
            clipped = np.clip(stt_segment, -1.0, 1.0)
            audio_int16 = (clipped * 32767).astype(np.int16)
            audio_data = sr.AudioData(audio_int16.tobytes(), self.SAMPLE_RATE, 2)
            recognized_command = self.speech_recognizer._recognize_audio(audio_data)
            print(f"🎙️ Recognized command: {recognized_command}")
            if recognized_command and self.process_command_callback:
                self.process_command_callback(recognized_command)
        finally:
            if self.recognition_lock.locked():
                self.recognition_lock.release()
                if self.pixel_led:
                    self.pixel_led.off()

    def _distributor_loop(self, frame_size):
        while not self.stop_event.is_set():
            try:
                raw_chunk = self.audio_queue.get(timeout=0.2)
            except queue.Empty:
                continue

            chunk = self._normalize_chunk(raw_chunk, frame_size)

            with self.shared_state["lock"]:
                self.shared_state["audio_ring"].append(chunk)
                self.shared_state["global_samples"] += len(chunk)
                current_global = self.shared_state["global_samples"]

            try:
                self.wake_q.put_nowait((chunk, current_global))
            except queue.Full:
                try:
                    self.wake_q.get_nowait()
                except queue.Empty:
                    pass
                try:
                    self.wake_q.put_nowait((chunk, current_global))
                except queue.Full:
                    pass

            try:
                self.vad_q.put_nowait((chunk, current_global))
            except queue.Full:
                try:
                    self.vad_q.get_nowait()
                except queue.Empty:
                    pass
                try:
                    self.vad_q.put_nowait((chunk, current_global))
                except queue.Full:
                    pass

    def _wakeword_loop(self):
        model = self._load_model()
        last_trigger_time = 0.0

        while not self.stop_event.is_set():
            try:
                chunk, global_samples = self.wake_q.get(timeout=0.2)
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
            cooldown_ok = (now - last_trigger_time) * 1000.0 >= self.WAKEWORD_COOLDOWN_MS
            if best_score >= self.WAKEWORD_DETECTION_THRESHOLD and cooldown_ok:
                last_trigger_time = now
                self.pixel_led.set_listening()
                with self.shared_state["lock"]:
                    self.shared_state["trigger_global_sample"] = global_samples
                self.shared_state["wakeword_event"].set()
                print(f"\n🔥 Wakeword trigger: model={best_name}, score={best_score:.2f}")

            if self.DEBUG_SCORES and int(now * 10) % 10 == 0:
                print(f"[WW] best_score={best_score:.2f}", end="\r")

    def _vad_capture_loop(self):
        frame_size = int(self.SAMPLE_RATE * self.FRAME_MS / 1000)
        vad = webrtcvad.Vad(self.VAD_AGGRESSIVENESS)
        chunk_ms = (frame_size / self.SAMPLE_RATE) * 1000.0

        recording = False
        speech_buffer = []
        speech_ms = 0.0
        silence_ms = 0.0
        hangover_ms_left = 0.0
        recent_flags = deque(maxlen=max(self.VAD_RATIO_WINDOW_FRAMES, 35))
        trigger_offset_samples = None
        recording_elapsed_ms = 0.0

        while not self.stop_event.is_set():
            try:
                chunk, global_samples = self.vad_q.get(timeout=0.2)
            except queue.Empty:
                continue

            frame_bytes = (np.clip(chunk, -1.0, 1.0) * 32767).astype(np.int16).tobytes()
            is_speech = vad.is_speech(frame_bytes, self.SAMPLE_RATE)
            recent_flags.append(1 if is_speech else 0)

            rms = float(
            np.sqrt(
                np.mean(chunk.astype(np.float32) ** 2)
                )
            )
            vad_ratio = self._recent_vad_ratio(recent_flags)

            if is_speech:
                hangover_ms_left = self.HANGOVER_MS
            else:
                hangover_ms_left = max(0.0, hangover_ms_left - chunk_ms)

            if not recording:
                if self.shared_state["wakeword_event"].is_set():
                    with self.shared_state["lock"]:
                        ring_chunks = list(self.shared_state["audio_ring"])
                        trigger_global_sample = self.shared_state["trigger_global_sample"]

                    recording = True
                    self.is_recording = True
                    speech_buffer = ring_chunks[-max(1, int(self.PRE_ROLL_MS / chunk_ms)):]
                    speech_buffer.append(chunk)
                    speech_ms = (sum(len(ch) for ch in speech_buffer) / self.SAMPLE_RATE) * 1000.0
                    recording_elapsed_ms = 0.0
                    silence_ms = 0.0
                    hangover_ms_left = self.HANGOVER_MS

                    segment_start_global = global_samples - sum(len(ch) for ch in speech_buffer)
                    trigger_offset_samples = max(0, trigger_global_sample - segment_start_global)
                    print(f"\n[VAD START] peak={rms:.3f} vad_ratio={vad_ratio:.2f}")
                continue

            speech_buffer.append(chunk)
            speech_ms += chunk_ms

            silence_threshold = max(
                self.ambient_noise_floor * self.NOISE_MULTIPLIER,
                self.ENERGY_SILENCE_THRESHOLD
            )

            is_energy_silent = rms < silence_threshold

            if (
                is_energy_silent
                and vad_ratio <= self.VAD_END_RATIO
                and hangover_ms_left <= 0.0
            ):
                silence_ms += chunk_ms
            else:
                silence_ms = 0.0

            end_by_energy = silence_ms >= self.ENERGY_END_MS and speech_ms >= self.MIN_SPEECH_MS
            end_by_max = speech_ms >= self.MAX_COMMAND_MS
            end_by_long_silence = silence_ms >= self.MAX_SILENCE_MS
            if self.DEBUG_SCORES:
                print(
                f"[REC] rms={rms:.5f} "
                f"noise={self.ambient_noise_floor:.5f} "
                f"thr={silence_threshold:.5f} "
                )

            if end_by_energy or end_by_max or end_by_long_silence:
                end_reason = "energy_silence" if end_by_energy else "max_len"
                segment = np.concatenate(speech_buffer).astype(np.float32)
                print(f"\n[VAD END] duration={len(segment)/self.SAMPLE_RATE:.2f}s, reason={end_reason}")

                threading.Thread(
                    target=self._recognize_and_dispatch,
                    args=(segment, trigger_offset_samples),
                    daemon=True,
                ).start()

                recording = False
                speech_buffer = []
                speech_ms = 0.0
                silence_ms = 0.0
                hangover_ms_left = 0.0
                trigger_offset_samples = None
                recording_elapsed_ms = 0.0
                self.is_recording = False
                self.shared_state["wakeword_event"].clear()
                recent_flags.clear()
    def start_detection(self, process_command_callback=None):
        if self.detection_running:
            print("[WWD] Detection already running")
            return

        if self.FRAME_MS not in (10, 20, 30):
            raise ValueError("FRAME_MS must be one of: 10, 20, 30")

        self.process_command_callback = process_command_callback
        self.stop_event.clear()
        self.detection_running = True

        frame_size = int(self.SAMPLE_RATE * self.FRAME_MS / 1000)
        ring_chunks = max(1, int((self.PRE_ROLL_MS / 1000.0) * self.SAMPLE_RATE / frame_size))
        self.shared_state = {
            "lock": threading.Lock(),
            "wakeword_event": threading.Event(),
            "trigger_global_sample": 0,
            "global_samples": 0,
            "audio_ring": deque(maxlen=ring_chunks * 20),
        }

        self.list_input_devices()
        print(
            "Listening with class-based THREADED wakeword+VAD capture... "
            f"(ww_threshold={self.WAKEWORD_DETECTION_THRESHOLD}, device={self.input_device_index})"
        )

        self.stream = self._create_input_stream(frame_size)
        self.stream.start()
        self._calibrate_noise_floor()
        distributor = threading.Thread(target=self._distributor_loop, args=(frame_size,), daemon=True)
        wake_thread = threading.Thread(target=self._wakeword_loop, daemon=True)
        vad_thread = threading.Thread(target=self._vad_capture_loop, daemon=True)

        self.threads = [distributor, wake_thread, vad_thread]
        for t in self.threads:
            t.start()

        print("[WWD] Ready. Speak wakeword now...")

    def stop_detection(self):
        if not self.detection_running:
            return

        self.stop_event.set()
        self.detection_running = False

        if self.stream is not None:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception:
                pass
            self.stream = None

        for t in self.threads:
            if t.is_alive():
                t.join(timeout=1.0)
        self.threads = []

        print("[WWD] Threaded detection stopped")

