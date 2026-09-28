import os
import socket
import select
import subprocess
import threading
import time
import math

import cv2
import mediapipe as mp
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision as mp_vision
import numpy as np

from camera_display_control import is_camera_display_enabled, toggle_camera_display_enabled
from camera_context import (
    get_servo_adjustment,
    write_camera_context,
    write_tracking_angles,
    set_wake_request,
)
from face_track_servo import (
    FaceTrackServo,
    MAX_ANGLE_LIMIT,
    PAN_MIN_ANGLE,
    PAN_MAX_ANGLE,
    PAN_NEUTRAL_ANGLE,
    TILT_MIN_ANGLE,
    TILT_MAX_ANGLE,
    TILT_NEUTRAL_ANGLE,
)
from sensor_reader import SensorReader

try:
    import face_recognition
except ImportError:
    face_recognition = None


os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"
os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")

MP_MODELS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mp_models")
FACE_DETECTOR_MODEL_PATH = os.path.join(MP_MODELS_DIR, "blaze_face_short_range.tflite")
HAND_LANDMARKER_MODEL_PATH = os.path.join(MP_MODELS_DIR, "hand_landmarker.task")

STREAM_PORT = 8002
RELAY_STREAM_PORT = 8003
RELAY_STREAM_HOST = os.getenv("FRAME_RELAY_HOST", "127.0.0.1")
RELAY_PUBLISH_EVERY_N_FRAMES = 4
CAMERA_INDEX = "0"
WIDTH = 640
HEIGHT = 480
FPS = 30
FACE_DETECT_EVERY_N_FRAMES = 2  # Update face tracking up to 15 times per second at 30 FPS.
DETECT_EVERY_N_FRAMES = 3      # Keep hand/gesture detection at 7.5 times per second.
FACE_RECOGNITION_EVERY_N_FRAMES = 30  # Recognize every 30 frames (reduce CPU)
PROCESS_SCALE = 0.35             # Much smaller = faster (was 0.5)
FACE_DB_PATH = "my_db"
FACE_MATCH_TOLERANCE = 0.5
CONTEXT_LOG_EVERY_N_FRAMES = 30
CAMERA_CONTEXT_UPDATE_SECONDS = 2
FACE_LOST_CENTER_DELAY = 1.5
TILT_SEARCH_RANGE_DEGREES = 20
TILT_SEARCH_STEP_DEGREES = 1
TILT_SEARCH_INTERVAL_SECONDS = 0.25
WAKE_GESTURE_PATTERN = ("fist", "open_hand", "fist", "open_hand")
WAKE_GESTURE_MAX_STEP_SECONDS = 1.2
WAKE_GESTURE_TRIGGER_COOLDOWN_SECONDS = 2.0
# Hand gesture constants
FINGER_THRESHOLD = 0.05  # Distance threshold for finger detection

# Sensor-based tracking fallback
SENSOR_PORT = os.getenv("SENSOR_PORT", "/dev/ttyAMA0")
SENSOR_BAUDRATE = 256000
SENSOR_TRACKING_TIMEOUT = 3.0  # Hold the last pan target after radar data goes stale.
SENSOR_FALLBACK_ENABLE = True  # Enable radar pan tracking.

DISPLAY_STATE_CHECK_SECONDS = 0.2
DISPLAY_BUTTON_BOUNDS = (510, 40, 680, 105)
MAX_PUPIL_ANGLE = math.pi / 2


class _RelativeBoundingBox:
    """Normalized bounding box, mirroring the legacy mp.solutions API shape."""
    __slots__ = ("xmin", "ymin", "width", "height")

    def __init__(self, xmin, ymin, width, height):
        self.xmin = xmin
        self.ymin = ymin
        self.width = width
        self.height = height


class _LocationData:
    __slots__ = ("relative_bounding_box",)

    def __init__(self, relative_bounding_box):
        self.relative_bounding_box = relative_bounding_box


class _CompatDetection:
    """Wraps a Tasks-API Detection to look like the legacy detection object."""
    __slots__ = ("location_data",)

    def __init__(self, location_data):
        self.location_data = location_data


class _FaceDetectionResult:
    __slots__ = ("detections",)

    def __init__(self, detections):
        self.detections = detections


def _to_compat_face_result(detection_result, image_width, image_height):
    """Convert a mediapipe.tasks FaceDetectorResult (pixel bboxes) into the
    legacy-shaped result with normalized relative_bounding_box coordinates."""
    if not detection_result or not detection_result.detections:
        return _FaceDetectionResult([])

    compat_detections = []
    for detection in detection_result.detections:
        bbox = detection.bounding_box
        relative_bbox = _RelativeBoundingBox(
            xmin=bbox.origin_x / image_width,
            ymin=bbox.origin_y / image_height,
            width=bbox.width / image_width,
            height=bbox.height / image_height,
        )
        compat_detections.append(_CompatDetection(_LocationData(relative_bbox)))

    return _FaceDetectionResult(compat_detections)


def servo_angles_to_pupil_angles(pan_angle, tilt_angle):
    pan_ratio = (pan_angle - PAN_NEUTRAL_ANGLE) / PAN_MAX_ANGLE
    tilt_span = max(TILT_NEUTRAL_ANGLE - TILT_MIN_ANGLE, TILT_MAX_ANGLE - TILT_NEUTRAL_ANGLE)
    tilt_ratio = (tilt_angle - TILT_NEUTRAL_ANGLE) / tilt_span

    pan_ratio = max(-1.0, min(1.0, pan_ratio))
    tilt_ratio = max(-1.0, min(1.0, tilt_ratio))

    pupil_pan_angle = pan_ratio * MAX_PUPIL_ANGLE
    pupil_tilt_angle = tilt_ratio * MAX_PUPIL_ANGLE
    return pupil_pan_angle, pupil_tilt_angle


def publish_tracking_angles(servo_tracker):
    pan_angle = getattr(servo_tracker, "last_pan_angle", None)
    tilt_angle = getattr(servo_tracker, "last_tilt_angle", None)
    if pan_angle is None or tilt_angle is None:
        return

    pupil_pan_angle, pupil_tilt_angle = servo_angles_to_pupil_angles(pan_angle, tilt_angle)
    write_tracking_angles(pupil_pan_angle, pupil_tilt_angle)


def start_stream():
    cmd = [
        "rpicam-vid",
        "--camera",
        CAMERA_INDEX,
        "-t",
        "0",
        "--width",
        str(WIDTH),
        "--height",
        str(HEIGHT),
        "--framerate",
        str(FPS),
        # Focus once at startup, then hold to avoid continuous focus hunting.
        "--autofocus-mode",
        "auto",
        "--codec",
        "mjpeg",
        "--quality",
        "55",
        "--listen",
        "-o",
        f"tcp://0.0.0.0:{STREAM_PORT}",
        "-n",
    ]

    print("Starting camera stream with rpicam-vid...")
    return subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)


def print_stream_logs(process):
    for line in iter(process.stdout.readline, b""):
        print(f"camera: {line.decode(errors='replace').rstrip()}")


class FrameRelayServer:
    def __init__(self, host=RELAY_STREAM_HOST, port=RELAY_STREAM_PORT):
        self.host = host
        self.port = port
        self.server_sock = None
        self.accept_thread = None
        self.stop_event = threading.Event()
        self.clients = []
        self.clients_lock = threading.Lock()

    def start(self):
        self.server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_sock.bind((self.host, self.port))
        self.server_sock.listen()
        self.server_sock.settimeout(0.5)
        self.accept_thread = threading.Thread(target=self._accept_loop, daemon=True)
        self.accept_thread.start()
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
                if not self.stop_event.is_set():
                    print("[RELAY] Accept loop stopped unexpectedly", flush=True)
                break

    def publish_frame(self, frame):
        with self.clients_lock:
            if not self.clients:
                return

        ok, encoded = cv2.imencode(
            ".jpg",
            frame,
            [int(cv2.IMWRITE_JPEG_QUALITY), 80],
        )
        if not ok:
            return

        payload = encoded.tobytes()
        dead_clients = []
        with self.clients_lock:
            for client_sock in self.clients:
                try:
                    client_sock.sendall(payload)
                except OSError:
                    dead_clients.append(client_sock)

            for client_sock in dead_clients:
                try:
                    client_sock.close()
                except OSError:
                    pass
                self.clients.remove(client_sock)

    def stop(self):
        self.stop_event.set()
        if self.server_sock is not None:
            try:
                self.server_sock.close()
            except OSError:
                pass
            self.server_sock = None

        if self.accept_thread and self.accept_thread.is_alive():
            self.accept_thread.join(timeout=1.0)
        self.accept_thread = None

        with self.clients_lock:
            for client_sock in self.clients:
                try:
                    client_sock.close()
                except OSError:
                    pass
            self.clients = []


def connect_stream(process):
    print("Connecting to camera stream...")

    for _ in range(40):
        if process.poll() is not None:
            raise RuntimeError(f"Camera stream stopped with code {process.returncode}")

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 32768)
        sock.settimeout(2)

        try:
            sock.connect(("127.0.0.1", STREAM_PORT))
            print("Camera stream connected.")
            return sock
        except OSError:
            sock.close()
            time.sleep(0.25)

    raise RuntimeError("Could not connect to camera stream.")


def read_frames(sock):
    buffer = b""
    max_buffer_size = 512 * 1024

    while True:
        data = sock.recv(32768)
        if not data:
            break

        latest_frame = None
        while True:
            buffer += data
            if len(buffer) > max_buffer_size:
                buffer = buffer[-max_buffer_size:]

            while True:
                start = buffer.find(b"\xff\xd8")
                end = buffer.find(b"\xff\xd9")
                if start == -1 or end == -1 or end <= start:
                    break

                jpg = buffer[start:end + 2]
                buffer = buffer[end + 2:]
                frame = cv2.imdecode(np.frombuffer(jpg, np.uint8), cv2.IMREAD_COLOR)
                if frame is not None:
                    latest_frame = frame

            # Discard queued old frames and track the newest complete frame.
            readable, _, _ = select.select([sock], [], [], 0)
            if not readable:
                break
            data = sock.recv(32768)
            if not data:
                return

        if latest_frame is not None:
            yield latest_frame


def load_known_faces(db_path):
    if face_recognition is None:
        print("face_recognition is not installed. Face labels will show as 'Face'.")
        print("Install it with: pip install face-recognition")
        return [], []

    known_encodings = []
    known_names = []
    valid_extensions = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}

    if not os.path.isdir(db_path):
        print(f"Face database folder not found: {db_path}")
        return known_encodings, known_names

    for root, _, files in os.walk(db_path):
        for filename in files:
            _, ext = os.path.splitext(filename.lower())
            if ext not in valid_extensions:
                continue

            image_path = os.path.join(root, filename)
            image = face_recognition.load_image_file(image_path)
            encodings = face_recognition.face_encodings(image)

            if not encodings:
                print(f"No face found in {image_path}")
                continue

            name = os.path.basename(root)
            known_encodings.append(encodings[0])
            known_names.append(name)

    print(f"Loaded {len(known_encodings)} known face image(s).")
    return known_encodings, known_names


def detection_to_face_location(detection, frame_width, frame_height):
    bbox = detection.location_data.relative_bounding_box
    left = max(0, int(bbox.xmin * frame_width))
    top = max(0, int(bbox.ymin * frame_height))
    right = min(frame_width, left + int(bbox.width * frame_width))
    bottom = min(frame_height, top + int(bbox.height * frame_height))
    return top, right, bottom, left


def recognize_faces(frame, detections, known_encodings, known_names):
    if not detections or not known_encodings or face_recognition is None:
        return []

    frame_height, frame_width = frame.shape[:2]
    rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    face_locations = [
        detection_to_face_location(detection, frame_width, frame_height)
        for detection in detections
    ]
    face_encodings = face_recognition.face_encodings(rgb_frame, face_locations)
    labels = []

    for encoding in face_encodings:
        distances = face_recognition.face_distance(known_encodings, encoding)

        if len(distances) == 0:
            labels.append("Unknown")
            continue

        best_index = int(np.argmin(distances))
        if distances[best_index] <= FACE_MATCH_TOLERANCE:
            labels.append(known_names[best_index])
        else:
            labels.append("Unknown")

    return labels


def draw_faces(frame, detections, labels=None):
    """Draw face bounding boxes and labels on frame."""
    if not detections:
        return

    frame_height, frame_width = frame.shape[:2]
    labels = labels or []

    for idx, detection in enumerate(detections):
        bbox = detection.location_data.relative_bounding_box
        x = max(0, int(bbox.xmin * frame_width))
        y = max(0, int(bbox.ymin * frame_height))
        x2 = min(frame_width, x + int(bbox.width * frame_width))
        y2 = min(frame_height, y + int(bbox.height * frame_height))

        cv2.rectangle(frame, (x, y), (x2, y2), (0, 255, 0), 2)
        label = labels[idx] if idx < len(labels) else "Face"
        cv2.putText(frame, label, (x, max(20, y - 8)),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)


def count_fingers(hand_landmarks):
    """Count extended fingers in hand. Returns 0-5."""
    if not hand_landmarks:
        return 0
    
    # Handle both NormalizedLandmarkList and direct list formats
    landmarks = hand_landmarks.landmark if hasattr(hand_landmarks, 'landmark') else hand_landmarks
    
    # Count 4 main fingers: Index, Middle, Ring, Pinky
    # Compare tip to PIP (middle joint)
    finger_tips = [8, 12, 16, 20]
    finger_pips = [6, 10, 14, 18]
    
    fingers_extended = 0
    
    for tip_idx, pip_idx in zip(finger_tips, finger_pips):
        tip = landmarks[tip_idx]
        pip = landmarks[pip_idx]
        
        # When extended: tip is higher on screen (lower y value)
        if tip.y < pip.y:
            fingers_extended += 1
    
    # Thumb: compare tip (4) with CMC joint (2) using x-coordinate
    thumb_tip = landmarks[4]
    thumb_cmc = landmarks[2]
    # Thumb is extended if tip is away from palm (larger x difference)
    if abs(thumb_tip.x - thumb_cmc.x) > 0.05:
        fingers_extended += 1
    
    return fingers_extended


def is_fist(hand_landmarks):
    """Detect if hand is in fist position."""
    if not hand_landmarks:
        return False
    
    # If very few fingers extended, it's likely a fist
    fingers_extended = count_fingers(hand_landmarks)
    return fingers_extended <= 1



def get_hand_gesture(hand_landmarks):
    """Get current hand gesture and features.
    
    Returns: {
        'gesture': 'fist' | 'open_hand' | 'peace' | None,
        'fingers': 0-5
    }
    """
    if not hand_landmarks:
        return None
    
    fingers = count_fingers(hand_landmarks)
    is_closed = is_fist(hand_landmarks)
    
    # Detect static gestures (fist, open, peace)
    gesture = None
    if is_closed:
        gesture = "fist"
    elif fingers == 5:
        gesture = "open_hand"
    elif fingers == 2:
        gesture = "peace"
    
    return {
        "gesture": gesture,
        "fingers": fingers
    }


def get_hand_center(hand_landmarks):
    """Return a stable normalized palm center for motion tracking."""
    # Handle both NormalizedLandmarkList and direct list formats
    landmarks = hand_landmarks.landmark if hasattr(hand_landmarks, 'landmark') else hand_landmarks
    
    palm_indices = (0, 5, 9, 13, 17)
    xs = [landmarks[idx].x for idx in palm_indices]
    ys = [landmarks[idx].y for idx in palm_indices]
    return sum(xs) / len(xs), sum(ys) / len(ys)


def reset_wake_gesture_state(wake_gesture_state, clear_center=False):
    wake_gesture_state["sequence"] = []
    wake_gesture_state["last_gesture"] = None
    wake_gesture_state["last_step_at"] = 0.0
    wake_gesture_state["last_trigger_at"] = 0.0
    if clear_center:
        wake_gesture_state["center"] = None


def detect_wake_gesture(hand_result, wake_gesture_state, now):
    """Detect the sequence fist -> open_hand -> fist -> open_hand within a timeout."""
    result = {
        "detected": False,
        "center": wake_gesture_state.get("center"),
        "progress": 0,
        "matched": [],
    }

    if not hand_result or not hand_result.hand_landmarks:
        if now - wake_gesture_state.get("last_step_at", 0.0) > WAKE_GESTURE_MAX_STEP_SECONDS:
            reset_wake_gesture_state(wake_gesture_state, clear_center=True)
        result["progress"] = len(wake_gesture_state["sequence"])
        result["matched"] = list(wake_gesture_state["sequence"])
        return result

    primary_hand = hand_result.hand_landmarks[0]
    gesture_info = get_hand_gesture(primary_hand)
    gesture = gesture_info.get("gesture") if gesture_info else None
    if gesture not in {"fist", "open_hand"}:
        if now - wake_gesture_state.get("last_step_at", 0.0) > WAKE_GESTURE_MAX_STEP_SECONDS:
            reset_wake_gesture_state(wake_gesture_state, clear_center=True)
        result["progress"] = len(wake_gesture_state["sequence"])
        result["matched"] = list(wake_gesture_state["sequence"])
        return result

    center_x, center_y = get_hand_center(primary_hand)
    wake_gesture_state["center"] = (center_x, center_y)
    result["center"] = wake_gesture_state["center"]

    if (
        wake_gesture_state["sequence"]
        and now - wake_gesture_state.get("last_step_at", 0.0) > WAKE_GESTURE_MAX_STEP_SECONDS
    ):
        reset_wake_gesture_state(wake_gesture_state)
        wake_gesture_state["center"] = (center_x, center_y)

    if wake_gesture_state["last_gesture"] == gesture:
        result["progress"] = len(wake_gesture_state["sequence"])
        result["matched"] = list(wake_gesture_state["sequence"])
        return result

    wake_gesture_state["last_gesture"] = gesture

    if not wake_gesture_state["sequence"]:
        if gesture == WAKE_GESTURE_PATTERN[0]:
            wake_gesture_state["sequence"] = [gesture]
            wake_gesture_state["last_step_at"] = now
    else:
        next_index = len(wake_gesture_state["sequence"])
        if next_index >= len(WAKE_GESTURE_PATTERN):
            cooldown_elapsed = (
                now - wake_gesture_state["last_trigger_at"]
            ) >= WAKE_GESTURE_TRIGGER_COOLDOWN_SECONDS
            if cooldown_elapsed:
                wake_gesture_state["last_trigger_at"] = now
                result["detected"] = True
            reset_wake_gesture_state(wake_gesture_state)
            wake_gesture_state["center"] = (center_x, center_y)
            result["center"] = (center_x, center_y)
            return result

        expected_gesture = WAKE_GESTURE_PATTERN[next_index]
        if gesture == expected_gesture:
            wake_gesture_state["sequence"].append(gesture)
            wake_gesture_state["last_step_at"] = now
        elif gesture == WAKE_GESTURE_PATTERN[0]:
            wake_gesture_state["sequence"] = [gesture]
            wake_gesture_state["last_step_at"] = now
        else:
            reset_wake_gesture_state(wake_gesture_state)
            wake_gesture_state["center"] = (center_x, center_y)

    result["progress"] = len(wake_gesture_state["sequence"])
    result["matched"] = list(wake_gesture_state["sequence"])

    cooldown_elapsed = (
        now - wake_gesture_state["last_trigger_at"]
    ) >= WAKE_GESTURE_TRIGGER_COOLDOWN_SECONDS
    if len(wake_gesture_state["sequence"]) == len(WAKE_GESTURE_PATTERN) and cooldown_elapsed:
        wake_gesture_state["last_trigger_at"] = now
        result["detected"] = True
        reset_wake_gesture_state(wake_gesture_state)
        wake_gesture_state["center"] = (center_x, center_y)
        result["center"] = (center_x, center_y)

    return result

def get_face_bbox(detection, frame_width, frame_height):
    """Convert face detection to bounding box.
    
    Args:
        detection: MediaPipe face detection
        frame_width: Frame width in pixels
        frame_height: Frame height in pixels
    
    Returns: dict with 'x', 'y', 'width', 'height' in pixels
    """
    bbox = detection.location_data.relative_bounding_box
    x = max(0, int(bbox.xmin * frame_width))
    y = max(0, int(bbox.ymin * frame_height))
    width = int(bbox.width * frame_width)
    height = int(bbox.height * frame_height)
    
    return {
        'x': x,
        'y': y,
        'width': width,
        'height': height
    }


def setup_display_window():
    cv2.namedWindow("Face and Hand Detection", cv2.WINDOW_NORMAL)
    cv2.resizeWindow("Face and Hand Detection", 720, 1280)
    cv2.moveWindow("Face and Hand Detection", 0, 0)
    cv2.setWindowProperty(
        "Face and Hand Detection",
        cv2.WND_PROP_FULLSCREEN,
        cv2.WINDOW_FULLSCREEN,
    )


def set_display_visibility(should_show, display_visible):
    if should_show and not display_visible:
        setup_display_window()
        return True

    if not should_show and display_visible:
        try:
            cv2.destroyWindow("Face and Hand Detection")
        except cv2.error:
            pass
        return False

    return display_visible


def draw_display_toggle_button(frame, label):
    x1, y1, x2, y2 = DISPLAY_BUTTON_BOUNDS
    cv2.rectangle(frame, (x1, y1), (x2, y2), (60, 60, 60), -1)
    cv2.rectangle(frame, (x1, y1), (x2, y2), (220, 220, 220), 2)
    cv2.putText(frame, label, (x1 + 14, y1 + 42),
               cv2.FONT_HERSHEY_SIMPLEX, 0.72, (245, 245, 245), 2, cv2.LINE_AA)


def point_in_display_button(x, y):
    x1, y1, x2, y2 = DISPLAY_BUTTON_BOUNDS
    return x1 <= x <= x2 and y1 <= y <= y2


def process_detection_frame(frame, face_detector, hands, run_face=True, run_hands=True):
    rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)
    frame_height, frame_width = rgb_frame.shape[:2]

    face_result = face_detector.detect(mp_image) if run_face else None
    hand_result = hands.detect(mp_image) if run_hands else None

    compat_face_result = (
        _to_compat_face_result(face_result, frame_width, frame_height)
        if run_face else None
    )
    return compat_face_result, hand_result


def update_face_labels(frame, face_result, frame_count, known_encodings, known_names, last_labels):
    if not face_result or not face_result.detections:
        return []

    should_recognize = frame_count % FACE_RECOGNITION_EVERY_N_FRAMES == 0
    if should_recognize:
        return recognize_faces(frame, face_result.detections, known_encodings, known_names)

    return last_labels


def update_camera_context(face_result, face_labels, frame_count, now, last_face_count, last_update_at):
    if face_result and face_result.detections:
        face_count = len(face_result.detections)
        visible_people = [label for label in face_labels if label not in {"Face", "Unknown"}]
        last_seen_person = visible_people[0] if visible_people else None
        context_changed = face_count != last_face_count
        should_update = (
            context_changed or
            now - last_update_at >= CAMERA_CONTEXT_UPDATE_SECONDS
        )

        if should_update:
            write_camera_context(
                visible_people,
                visible_face_count=face_count,
                last_seen_person=last_seen_person,
            )
            last_update_at = now
            if context_changed or frame_count % CONTEXT_LOG_EVERY_N_FRAMES == 0:
                people_text = ", ".join(visible_people) if visible_people else "none"
                print(f"[CAMERA] faces={face_count} identified={people_text}", flush=True)

        return face_labels, face_count, last_update_at

    if face_result and not face_result.detections:
        if last_face_count > 0 or now - last_update_at >= CAMERA_CONTEXT_UPDATE_SECONDS:
            write_camera_context([], visible_face_count=0)
            last_update_at = now
            if last_face_count > 0:
                print("[CAMERA] Context cleared: no faces visible", flush=True)

        return [], 0, last_update_at

    return [], last_face_count, last_update_at


def draw_hand_overlays(frame, hand_result, mp_draw, hand_connections, frame_count):
    if not hand_result or not hand_result.hand_landmarks:
        return

    for hand_idx, hand_landmarks in enumerate(hand_result.hand_landmarks):
        mp_draw.draw_landmarks(frame, hand_landmarks, hand_connections)
        gesture_info = get_hand_gesture(hand_landmarks)

        if not gesture_info:
            continue

        y_offset = 30 + (hand_idx * 50)
        cv2.putText(frame, f"Hand {hand_idx + 1}:", (10, y_offset),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2)
        cv2.putText(frame, f"  Fingers: {gesture_info['fingers']}", (10, y_offset + 25),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 1)
        if gesture_info['gesture']:
            cv2.putText(frame, f"  Gesture: {gesture_info['gesture']}", (10, y_offset + 45),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 1)

        if frame_count % 30 == 0:
            print(f"[HAND{hand_idx + 1}] fingers={gesture_info['fingers']}, "
                  f"gesture={gesture_info['gesture']}")


def detect_face_and_hands(sock, servo_tracker, relay_server=None, sensor_reader=None):
    """Main detection loop for face and hand tracking.
    
    Args:
        sock: Camera stream socket
        servo_tracker: FaceTrackServo instance for face tracking
        relay_server: Optional frame relay for downstream consumers
        sensor_reader: Optional SensorReader instance for fallback tracking when face not detected
    """
    mp_draw = mp_vision.drawing_utils
    hand_connections = mp_vision.HandLandmarksConnections.HAND_CONNECTIONS
    known_encodings, known_names = load_known_faces(FACE_DB_PATH)

    face_detector = mp_vision.FaceDetector.create_from_options(
        mp_vision.FaceDetectorOptions(
            base_options=mp_python.BaseOptions(model_asset_path=FACE_DETECTOR_MODEL_PATH),
            running_mode=mp_vision.RunningMode.IMAGE,
            min_detection_confidence=0.6,
        )
    )
    hands = mp_vision.HandLandmarker.create_from_options(
        mp_vision.HandLandmarkerOptions(
            base_options=mp_python.BaseOptions(model_asset_path=HAND_LANDMARKER_MODEL_PATH),
            running_mode=mp_vision.RunningMode.IMAGE,
            num_hands=2,
            min_hand_detection_confidence=0.7,
            min_tracking_confidence=0.5,
        )
    )

    # State tracking
    frame_count = 0
    latest_face_result, latest_face_labels = None, []
    latest_hand_result = None
    last_context_face_count = 0
    last_context_update_at = 0

    # Face detections own both pan and tilt; radar is only a fallback when no
    # face is visible.
    last_face_seen_at = 0.0
    tilt_search_direction = 1
    next_tilt_search_at = 0.0
    last_servo_command_id = 0
    manual_servo_until = 0.0

    # Wake gesture detection state
    wake_gesture_state = {
        "sequence": [],
        "last_gesture": None,
        "last_step_at": 0.0,
        "last_trigger_at": 0.0,
        "center": None,
    }

    using_radar_pan = False

    display_enabled = is_camera_display_enabled(default=False)
    display_visible = set_display_visibility(display_enabled, False)
    last_display_state_check_at = 0.0
    toggle_requested = False

    def _mouse_callback(event, x, y, _flags, _param):
        nonlocal toggle_requested
        if event == cv2.EVENT_LBUTTONUP and point_in_display_button(x, y):
            toggle_requested = True

    if display_visible:
        cv2.setMouseCallback("Face and Hand Detection", _mouse_callback)

    try:
        for frame in read_frames(sock):
            frame_count += 1
            now = time.time()

            if now - last_display_state_check_at >= DISPLAY_STATE_CHECK_SECONDS:
                display_enabled = is_camera_display_enabled(default=False)
                display_visible = set_display_visibility(display_enabled, display_visible)
                if display_visible:
                    cv2.setMouseCallback("Face and Hand Detection", _mouse_callback)
                last_display_state_check_at = now

            # Downscale for faster processing
            processing_frame = frame
            if PROCESS_SCALE < 1.0:
                processing_frame = cv2.resize(
                    frame, None, fx=PROCESS_SCALE, fy=PROCESS_SCALE,
                    interpolation=cv2.INTER_LINEAR
                )

            # Run face detection more often than hand detection so tracking
            # stays responsive without doubling the gesture model workload.
            run_face_detection = frame_count % FACE_DETECT_EVERY_N_FRAMES == 0
            run_hand_detection = frame_count % DETECT_EVERY_N_FRAMES == 0
            if run_face_detection or run_hand_detection:
                face_result, hand_result = process_detection_frame(
                    processing_frame,
                    face_detector,
                    hands,
                    run_face=run_face_detection,
                    run_hands=run_hand_detection,
                )
                if run_face_detection:
                    latest_face_result = face_result
                    latest_face_labels = update_face_labels(
                        frame,
                        latest_face_result,
                        frame_count,
                        known_encodings,
                        known_names,
                        latest_face_labels,
                    )
                if run_hand_detection:
                    latest_hand_result = hand_result

            # Update camera context from the latest detections and labels.
            latest_face_labels, last_context_face_count, last_context_update_at = update_camera_context(
                latest_face_result,
                latest_face_labels,
                frame_count,
                now,
                last_context_face_count,
                last_context_update_at,
            )

            # Draw detections and detect gestures
            if latest_face_result:
                draw_faces(frame, latest_face_result.detections, latest_face_labels)
            draw_hand_overlays(frame, latest_hand_result, mp_draw, hand_connections, frame_count)

            # Detect wake gesture (fist -> open_hand -> fist -> open_hand sequence)
            wake_result = detect_wake_gesture(latest_hand_result, wake_gesture_state, now)
            if wake_result["detected"]:
                print("[WAKE] Wake gesture detected! Waking up assistant...", flush=True)
                set_wake_request(source="hand_gesture")
            
            # Draw wake gesture progress on screen
            if wake_result["progress"] > 0:
                progress_text = f"Wake Gesture: {'/'.join(wake_result['matched'])} ({wake_result['progress']}/{len(WAKE_GESTURE_PATTERN)})"
                cv2.putText(frame, progress_text, (10, frame.shape[0] - 20),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2)
            
            face_visible = bool(
                latest_face_result and latest_face_result.detections
            )
            adjustment = get_servo_adjustment(after_command_id=last_servo_command_id)
            if adjustment:
                last_servo_command_id = adjustment["command_id"]
                if adjustment.get("pan_angle") is not None:
                    servo_tracker.move_pan_to_angle(adjustment["pan_angle"])
                if adjustment.get("tilt_angle") is not None:
                    servo_tracker.move_tilt_to_angle(adjustment["tilt_angle"])
                manual_servo_until = now + adjustment["hold_seconds"]
                publish_tracking_angles(servo_tracker)
                print(
                    "[CAMERA] Agent servo adjustment: "
                    f"pan {servo_tracker.last_pan_angle:.1f}°, "
                    f"tilt {servo_tracker.last_tilt_angle:.1f}°; "
                    f"holding face tracking for {adjustment['hold_seconds']:.1f}s",
                    flush=True,
                )

            if run_face_detection and now >= manual_servo_until:
                if face_visible:
                    primary_face = latest_face_result.detections[0]
                    face_bbox = get_face_bbox(primary_face, frame.shape[1], frame.shape[0])
                    _, tilt_correction = servo_tracker.bbox_to_angles(face_bbox)
                    if tilt_correction:
                        tilt_search_direction = 1 if tilt_correction > 0 else -1
                    servo_tracker.track_face(face_bbox)
                    publish_tracking_angles(servo_tracker)
                    last_face_seen_at = now
                    using_radar_pan = False
                else:
                    # Radar may help reacquire a face after it leaves view,
                    # but cannot override face-based tracking while visible.
                    sensor_sample = (
                        sensor_reader.get_latest()
                        if sensor_reader and SENSOR_FALLBACK_ENABLE
                        else None
                    )
                    using_radar_pan = bool(
                        sensor_sample
                        and now - sensor_sample.get("timestamp", 0) <= SENSOR_TRACKING_TIMEOUT
                    )
                    if using_radar_pan:
                        previous_pan = servo_tracker.last_pan_angle
                        servo_tracker.move_pan_to_angle(sensor_sample.get("pan_angle", 0))
                        if servo_tracker.last_pan_angle != previous_pan:
                            publish_tracking_angles(servo_tracker)
                        cv2.putText(frame, "● RADAR REACQUIRE", (10, 50),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 165, 255), 2)

                if not face_visible and now - last_face_seen_at >= FACE_LOST_CENTER_DELAY:
                    # Search only around the configured default tilt position.
                    # The endpoints are hard limits for this recovery motion.
                    if now >= next_tilt_search_at:
                        lower = max(
                            TILT_MIN_ANGLE,
                            TILT_NEUTRAL_ANGLE - TILT_SEARCH_RANGE_DEGREES,
                        )
                        upper = min(
                            TILT_MAX_ANGLE,
                            TILT_NEUTRAL_ANGLE + TILT_SEARCH_RANGE_DEGREES,
                        )
                        target_tilt = (
                            servo_tracker.last_tilt_angle
                            + tilt_search_direction * TILT_SEARCH_STEP_DEGREES
                        )
                        if target_tilt >= upper:
                            target_tilt = upper
                            tilt_search_direction = -1
                        elif target_tilt <= lower:
                            target_tilt = lower
                            tilt_search_direction = 1

                        previous_tilt = servo_tracker.last_tilt_angle
                        servo_tracker.move_tilt_to_angle(target_tilt)
                        if servo_tracker.last_tilt_angle != previous_tilt:
                            publish_tracking_angles(servo_tracker)
                        next_tilt_search_at = now + TILT_SEARCH_INTERVAL_SECONDS
            
            # Dashboard frames are published independently of the desktop window.
            if relay_server and frame_count % RELAY_PUBLISH_EVERY_N_FRAMES == 0:
                relay_server.publish_frame(frame)
            if display_visible:
                display_frame = cv2.resize(frame, (720, 1280), interpolation=cv2.INTER_LINEAR)
                draw_display_toggle_button(display_frame, "Hide Camera")
                cv2.imshow("Face and Hand Detection", display_frame)

                key = cv2.waitKey(1) & 0xFF
                if key == ord("c") or toggle_requested:
                    toggle_requested = False
                    toggle_camera_display_enabled(default=False)
                    display_enabled = False
                    display_visible = set_display_visibility(False, display_visible)
                    continue

                if key in (27, ord("q")):
                    print(f"Exiting. Total frames: {frame_count}")
                    break
    finally:
        servo_tracker.stop()
        hands.close()
        face_detector.close()
        if display_visible:
            try:
                cv2.destroyWindow("Face and Hand Detection")
            except cv2.error:
                pass


def main():
    process = start_stream()
    threading.Thread(target=print_stream_logs, args=(process,), daemon=True).start()
    sock = None
    servo_tracker = FaceTrackServo(verbose=False)
    sensor_reader = None
    relay_server = None

    try:
        sock = connect_stream(process)
        relay_server = FrameRelayServer()
        relay_server.start()
        
        # Initialize servo tracking (optional - will skip if hardware not available)
        if not servo_tracker.initialize():
            print("[WARNING] Could not initialize servo hardware - face tracking disabled")
        
        # Initialize sensor-based fallback tracking (optional)
        if SENSOR_FALLBACK_ENABLE:
            try:
                sensor_reader = SensorReader(
                    port=SENSOR_PORT,
                    baudrate=SENSOR_BAUDRATE,
                    daemon=True,
                    enable_servo=False,  # Servo controlled by face detector, not sensor
                    verbose=False
                )
                sensor_reader.start()
                print("[SENSOR] Sensor reader started for fallback tracking", flush=True)
            except Exception as e:
                print(f"[WARNING] Could not initialize sensor reader: {e}")
                sensor_reader = None
        
        detect_face_and_hands(sock, servo_tracker, relay_server=relay_server, sensor_reader=sensor_reader)
    
    finally:
        servo_tracker.stop()
        if sensor_reader and sensor_reader.running:
            sensor_reader.stop()
            sensor_reader.join(timeout=2.0)
        if relay_server:
            relay_server.stop()
        if sock:
            sock.close()
        process.terminate()
        process.wait()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
