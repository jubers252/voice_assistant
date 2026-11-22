"""
Person detection with YOLOv8 (ONNX Runtime).

Detects the COCO "person" class (class 0) in a camera, video file, or stream.

Examples:
    python camera/person_detector.py                      # Pi camera via rpicam-vid, headless
    python camera/person_detector.py --show               # also show a preview window (press q to quit)
    python camera/person_detector.py --source 0           # USB webcam at /dev/video0 (if available)
    python camera/person_detector.py --source video.mp4 --conf 0.5
"""

import argparse
import os
import socket
import subprocess
import threading
import time

import cv2
import numpy as np
import onnxruntime as ort

PERSON_CLASS_ID = 0
DEFAULT_MODEL = "camera/yolo_models/yolov8n.onnx"
RPICAM_SOURCE = "rpicam"
RELAY_STREAM_PORT = 8003
RELAY_STREAM_HOST = os.getenv("FRAME_RELAY_HOST", "127.0.0.1")
RELAY_PUBLISH_EVERY_N_FRAMES = 2


def letterbox(image, size):
    """Resize keeping aspect ratio, padding to a square; returns image and (scale, pad_x, pad_y)."""
    h, w = image.shape[:2]
    scale = min(size / h, size / w)
    new_w, new_h = int(round(w * scale)), int(round(h * scale))
    resized = cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
    pad_x, pad_y = (size - new_w) // 2, (size - new_h) // 2
    canvas = np.full((size, size, 3), 114, dtype=np.uint8)
    canvas[pad_y:pad_y + new_h, pad_x:pad_x + new_w] = resized
    return canvas, scale, pad_x, pad_y


class PersonDetector:
    def __init__(self, model_path, imgsz=640, conf_threshold=0.4, iou_threshold=0.45, threads=2):
        options = ort.SessionOptions()
        options.intra_op_num_threads = threads
        self.session = ort.InferenceSession(
            model_path, sess_options=options, providers=["CPUExecutionProvider"]
        )
        self.input_name = self.session.get_inputs()[0].name
        self.imgsz = imgsz
        self.conf_threshold = conf_threshold
        self.iou_threshold = iou_threshold

    def detect(self, frame_bgr):
        """Return a list of (x1, y1, x2, y2, confidence) for persons in the frame."""
        img, scale, pad_x, pad_y = letterbox(frame_bgr, self.imgsz)
        blob = img[:, :, ::-1].transpose(2, 0, 1)[None].astype(np.float32) / 255.0

        output = self.session.run(None, {self.input_name: blob})[0][0]  # (84, 8400)
        boxes_cxcywh = output[:4, :].T
        person_scores = output[4 + PERSON_CLASS_ID, :]

        keep = person_scores > self.conf_threshold
        if not np.any(keep):
            return []
        boxes_cxcywh = boxes_cxcywh[keep]
        scores = person_scores[keep]

        cx, cy, w, h = boxes_cxcywh.T
        x1 = cx - w / 2
        y1 = cy - h / 2
        boxes_xywh = np.stack([x1, y1, w, h], axis=1)

        indices = cv2.dnn.NMSBoxes(
            boxes_xywh.tolist(), scores.tolist(), self.conf_threshold, self.iou_threshold
        )
        results = []
        for i in np.array(indices).flatten():
            bx, by, bw, bh = boxes_xywh[i]
            x1 = (bx - pad_x) / scale
            y1 = (by - pad_y) / scale
            x2 = (bx + bw - pad_x) / scale
            y2 = (by + bh - pad_y) / scale
            results.append((x1, y1, x2, y2, float(scores[i])))
        return results


def rpicam_frames(width, height, fps):
    """Yield BGR frames from the Pi camera by reading MJPEG from rpicam-vid's stdout."""
    cmd = [
        "rpicam-vid", "-t", "0",
        "--width", str(width), "--height", str(height), "--framerate", str(fps),
        "--codec", "mjpeg", "--nopreview", "-o", "-",
    ]
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    buffer = b""
    try:
        while True:
            chunk = process.stdout.read(65536)
            if not chunk:
                print("rpicam-vid stopped. Is the camera already in use by voice_assistant?")
                break
            buffer += chunk
            # Keep only the newest complete JPEG so decoding never falls behind the camera.
            latest_jpg = None
            while True:
                start = buffer.find(b"\xff\xd8")
                end = buffer.find(b"\xff\xd9", start + 2) if start != -1 else -1
                if start == -1 or end == -1:
                    buffer = buffer[start:] if start > 0 else (buffer[-1:] if start == -1 else buffer)
                    break
                latest_jpg = buffer[start:end + 2]
                buffer = buffer[end + 2:]
            if latest_jpg is not None:
                frame = cv2.imdecode(np.frombuffer(latest_jpg, np.uint8), cv2.IMREAD_COLOR)
                if frame is not None:
                    yield frame
    finally:
        process.terminate()
        process.wait()


class DetectionWorker(threading.Thread):
    """Runs YOLO in the background on the newest submitted frame, so the live feed never waits for it."""

    def __init__(self, detector):
        super().__init__(daemon=True)
        self.detector = detector
        self.pending = None
        self.lock = threading.Lock()
        self.has_work = threading.Event()
        self.stop_event = threading.Event()
        self.detections = []
        self.updated_at = 0.0

    def submit(self, frame):
        with self.lock:
            self.pending = frame
        self.has_work.set()

    def latest_detections(self):
        with self.lock:
            return self.detections

    def has_recent_person(self, max_age_seconds=2.0):
        with self.lock:
            if self.updated_at <= 0:
                return None
            if not 0 <= time.time() - self.updated_at <= max_age_seconds:
                return None
            return bool(self.detections)

    def run(self):
        while not self.stop_event.is_set():
            if not self.has_work.wait(timeout=0.5):
                continue
            self.has_work.clear()
            with self.lock:
                frame, self.pending = self.pending, None
            if frame is None:
                continue
            try:
                detections = self.detector.detect(frame)
            except Exception as error:
                print(f"[PERSON] Detection failed: {error}", flush=True)
                detections = []
            with self.lock:
                self.detections = detections
                self.updated_at = time.time()
            if detections:
                summary = ", ".join(f"{score:.2f}" for *_, score in detections)
                print(f"[PERSON] count={len(detections)} confidence=[{summary}]")

    def stop(self):
        self.stop_event.set()
        self.join(timeout=2.0)


class FrameRelayServer:
    """Same TCP JPEG relay as hand_detection.py (consumed by the UI on port 8003)."""

    def __init__(self, host=RELAY_STREAM_HOST, port=RELAY_STREAM_PORT):
        self.host = host
        self.port = port
        self.server_sock = None
        self.stop_event = threading.Event()
        self.clients = []
        self.clients_lock = threading.Lock()
        self.frame_ready = threading.Event()
        self.pending_frame = None

    def start(self):
        self.server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_sock.bind((self.host, self.port))
        self.server_sock.listen()
        self.server_sock.settimeout(0.5)
        threading.Thread(target=self._accept_loop, daemon=True).start()
        threading.Thread(target=self._send_loop, daemon=True).start()
        print(f"[RELAY] Frame relay listening on tcp://{self.host}:{self.port}", flush=True)

    def _accept_loop(self):
        while not self.stop_event.is_set():
            try:
                client_sock, client_addr = self.server_sock.accept()
                client_sock.settimeout(1.0)
                with self.clients_lock:
                    self.clients.append(client_sock)
                print(f"[RELAY] Client connected from {client_addr[0]}:{client_addr[1]}", flush=True)
            except socket.timeout:
                continue
            except OSError:
                break

    def publish_frame(self, frame):
        # Encoding and socket writes happen off the capture loop; only the newest frame is kept.
        with self.clients_lock:
            if not self.clients:
                return
        self.pending_frame = frame.copy()
        self.frame_ready.set()

    def _send_loop(self):
        while not self.stop_event.is_set():
            if not self.frame_ready.wait(timeout=0.5):
                continue
            self.frame_ready.clear()
            frame, self.pending_frame = self.pending_frame, None
            if frame is None:
                continue
            ok, encoded = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 70])
            if not ok:
                continue
            payload = encoded.tobytes()
            with self.clients_lock:
                for client_sock in list(self.clients):
                    try:
                        client_sock.sendall(payload)
                    except OSError:
                        client_sock.close()
                        self.clients.remove(client_sock)

    def stop(self):
        self.stop_event.set()
        if self.server_sock is not None:
            self.server_sock.close()
            self.server_sock = None
        with self.clients_lock:
            for client_sock in self.clients:
                client_sock.close()
            self.clients.clear()


def draw_detections(frame, detections):
    for x1, y1, x2, y2, score in detections:
        cv2.rectangle(frame, (int(x1), int(y1)), (int(x2), int(y2)), (0, 255, 0), 2)
        cv2.putText(frame, f"person {score:.2f}", (int(x1), max(int(y1) - 6, 12)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)


def frame_stream(args):
    """Yield frames from the selected source: the Pi camera, a camera index, a file, or a URL."""
    if args.source == RPICAM_SOURCE:
        yield from rpicam_frames(args.width, args.height, args.fps)
        return

    cap = cv2.VideoCapture(int(args.source) if args.source.isdigit() else args.source)
    if not cap.isOpened():
        raise SystemExit(f"Could not open video source: {args.source}")
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                print("No frame received, stopping.")
                return
            yield frame
    finally:
        cap.release()


def main():
    parser = argparse.ArgumentParser(description="Detect persons with YOLOv8 (ONNX).")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Path to yolov8 .onnx model")
    parser.add_argument(
        "--source", default=RPICAM_SOURCE,
        help="'rpicam' for the Pi camera, a camera index (e.g. 0), a video file, or a stream URL",
    )
    parser.add_argument("--width", type=int, default=640, help="Pi camera capture width (rpicam source)")
    parser.add_argument("--height", type=int, default=480, help="Pi camera capture height (rpicam source)")
    parser.add_argument("--fps", type=int, default=15, help="Pi camera frame rate (rpicam source)")
    parser.add_argument("--conf", type=float, default=0.4, help="Confidence threshold")
    parser.add_argument("--iou", type=float, default=0.45, help="NMS IoU threshold")
    parser.add_argument("--imgsz", type=int, default=640, help="Model input size (must match export)")
    parser.add_argument("--threads", type=int, default=2, help="ONNX Runtime CPU threads")
    parser.add_argument("--show", action="store_true", help="Show a preview window (press q to quit)")
    parser.add_argument(
        "--detect-every", type=int, default=3,
        help="Run YOLO on every Nth frame and reuse the last result in between (1 = every frame)",
    )
    parser.add_argument("--relay-port", type=int, default=RELAY_STREAM_PORT, help="TCP relay port for the UI feed (0 = disabled)")
    args = parser.parse_args()

    relay = None
    if args.relay_port:
        relay = FrameRelayServer(port=args.relay_port)
        relay.start()

    detector = PersonDetector(
        args.model, imgsz=args.imgsz, conf_threshold=args.conf,
        iou_threshold=args.iou, threads=args.threads,
    )
    print(f"Detecting persons from {args.source} (conf >= {args.conf}, every {args.detect_every} frame(s)). Ctrl+C to stop.")
    worker = DetectionWorker(detector)
    worker.start()
    frames = 0
    fps_start = time.time()
    try:
        for frame in frame_stream(args):
            if frames % max(args.detect_every, 1) == 0:
                worker.submit(frame)
            frames += 1
            detections = worker.latest_detections()

            publish = relay is not None and frames % RELAY_PUBLISH_EVERY_N_FRAMES == 0
            if args.show or publish:
                draw_detections(frame, detections)
            if publish:
                relay.publish_frame(frame)

            if args.show:
                cv2.imshow("Person detection", frame)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break

            if frames % 100 == 0:
                fps = 100 / (time.time() - fps_start)
                print(f"[INFO] {fps:.1f} frames/s")
                fps_start = time.time()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        worker.stop()
        if relay:
            relay.stop()
        if args.show:
            cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
