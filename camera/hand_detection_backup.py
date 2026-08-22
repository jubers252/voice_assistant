import os
import socket
import subprocess
import threading
import time

import cv2
import mediapipe as mp
import numpy as np

from .camera_context import set_wake_request, write_camera_context
from camera.face_track_servo import FaceTrackServo
from read_serial_simple import SensorReader

try:
    import face_recognition
except ImportError:
    face_recognition = None


os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"
os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")

STREAM_PORT = 8002
CAMERA_INDEX = "0"
WIDTH = 640
HEIGHT = 480
FPS = 30
DETECT_EVERY_N_FRAMES = 4     # Face and hand detect every 4 frames for stable tracking
FACE_RECOGNITION_EVERY_N_FRAMES = 30  # Recognize every 30 frames (reduce CPU)
PROCESS_SCALE = 0.35             # Much smaller = faster (was 0.5)
FACE_DB_PATH = "my_db"
FACE_MATCH_TOLERANCE = 0.5
CONTEXT_LOG_EVERY_N_FRAMES = 30
CAMERA_CONTEXT_UPDATE_SECONDS = 2
FACE_LOST_CENTER_DELAY = 1.5
FACE_MOVE_THRESHOLD = 6

# Hand gesture constants
FINGER_THRESHOLD = 0.05  # Distance threshold for finger detection
WAKE_GESTURE_PATTERN = ("fist", "open_hand", "fist", "open_hand")
WAKE_GESTURE_MAX_STEP_SECONDS = 1.2
WAKE_GESTURE_TRIGGER_COOLDOWN_SECONDS = 2.0

# Sensor-assisted tracking
TRACKING_MODE_FACE = "face"
TRACKING_MODE_SENSOR = "sensor"


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
    try:
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        print(f"Camera process started with PID {process.pid}")
        return process
    except FileNotFoundError:
        print("ERROR: rpicam-vid not found. Install libcamera: sudo apt install -y libcamera-apps")
        raise
    except Exception as e:
        print(f"ERROR: Failed to start camera: {e}")
        raise


def print_stream_logs(process):
    for line in iter(process.stdout.readline, b""):
        print(f"camera: {line.decode(errors='replace').rstrip()}")


def connect_stream(process):
    print("Connecting to camera stream...")

    for attempt in range(40):
        if process.poll() is not None:
            # Process died, get stderr for diagnosis
            print(f"ERROR: Camera process died with exit code {process.returncode}")
            print("Camera process output:")
            try:
                output = process.stdout.read()
                if output:
                    print(output.decode(errors='replace'))
            except:
                pass
            raise RuntimeError(f"Camera stream stopped with code {process.returncode}")

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 32768)
        sock.settimeout(2)

        try:
            sock.connect(("127.0.0.1", STREAM_PORT))
            print(f"Camera stream connected on attempt {attempt + 1}.")
            return sock
        except OSError as e:
            sock.close()
            if attempt == 0:
                print(f"[Attempt {attempt + 1}/40] Waiting for camera stream...")
            time.sleep(0.25)

    raise RuntimeError(f"Could not connect to camera stream on port {STREAM_PORT} after 40 attempts.")


def read_frames(sock):
    buffer = b""
    max_buffer_size = 512 * 1024

    while True:
        data = sock.recv(32768)
        if not data:
            break

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
                yield frame


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
    
    # Count 4 main fingers: Index, Middle, Ring, Pinky
    # Compare tip to PIP (middle joint)
    finger_tips = [8, 12, 16, 20]
    finger_pips = [6, 10, 14, 18]
    
    fingers_extended = 0
    
    for tip_idx, pip_idx in zip(finger_tips, finger_pips):
        tip = hand_landmarks.landmark[tip_idx]
        pip = hand_landmarks.landmark[pip_idx]
        
        # When extended: tip is higher on screen (lower y value)
        if tip.y < pip.y:
            fingers_extended += 1
    
    # Thumb: compare tip (4) with CMC joint (2) using x-coordinate
    thumb_tip = hand_landmarks.landmark[4]
    thumb_cmc = hand_landmarks.landmark[2]
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
    elif fingers >= 4:
        gesture = "open_hand"
    elif fingers == 2:
        gesture = "peace"
    
    return {
        "gesture": gesture,
        "fingers": fingers
    }


def get_hand_center(hand_landmarks):
    """Return a stable normalized palm center for motion tracking."""
    palm_indices = (0, 5, 9, 13, 17)
    xs = [hand_landmarks.landmark[idx].x for idx in palm_indices]
    ys = [hand_landmarks.landmark[idx].y for idx in palm_indices]
    return sum(xs) / len(xs), sum(ys) / len(ys)


def reset_wake_gesture_state(wake_gesture_state, clear_center=False):
    wake_gesture_state["sequence"] = []
    wake_gesture_state["last_gesture"] = None
    wake_gesture_state["last_step_at"] = 0.0
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

    if not hand_result or not hand_result.multi_hand_landmarks:
        if now - wake_gesture_state.get("last_step_at", 0.0) > WAKE_GESTURE_MAX_STEP_SECONDS:
            reset_wake_gesture_state(wake_gesture_state, clear_center=True)
        result["progress"] = len(wake_gesture_state["sequence"])
        result["matched"] = list(wake_gesture_state["sequence"])
        return result

    primary_hand = hand_result.multi_hand_landmarks[0]
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


def process_detection_frame(frame, face_detector, hands):
    rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    return face_detector.process(rgb_frame), hands.process(rgb_frame)


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


def draw_hand_overlays(frame, hand_result, mp_draw, mp_hands, frame_count):
    if not hand_result or not hand_result.multi_hand_landmarks:
        return

    for hand_idx, hand_landmarks in enumerate(hand_result.multi_hand_landmarks):
        mp_draw.draw_landmarks(frame, hand_landmarks, mp_hands.HAND_CONNECTIONS)
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


def draw_wake_gesture_overlay(frame, wake_gesture_status, now):
    if not wake_gesture_status:
        return

    center = wake_gesture_status.get("center")
    if center:
        frame_height, frame_width = frame.shape[:2]
        x = int(center[0] * frame_width)
        y = int(center[1] * frame_height)
        cv2.circle(frame, (x, y), 14, (255, 200, 0), 2)

    if wake_gesture_status.get("detected"):
        cv2.putText(
            frame,
            "Wake gesture detected",
            (10, HEIGHT - 60),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (255, 200, 0),
            2,
        )
    elif now - wake_gesture_status.get("last_seen_at", 0.0) < 0.75:
        matched = " -> ".join(wake_gesture_status.get("matched", [])) or "waiting"
        cv2.putText(
            frame,
            f"Wake watch: {matched}",
            (10, HEIGHT - 60),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (255, 200, 0),
            1,
        )


def initialize_sensor_reader():
    try:
        reader = SensorReader(daemon=True)
        reader.start()
        return reader
    except Exception as exc:
        print(f"[SENSOR] Warning: Could not initialize sensor reader - {exc}")
        return None


def update_servo_tracking(
    face_result,
    sensor_sample,
    sensor_tracking_enabled,
    servo_tracker,
    frame_shape,
    now,
    last_face_seen_at,
    last_tracked_center,
    current_mode,
):
    sensor_motion_active = bool(sensor_sample and sensor_sample.get("motion_detected"))

    if face_result and face_result.detections:
        primary_face = face_result.detections[0]
        face_bbox = get_face_bbox(primary_face, frame_shape[1], frame_shape[0])
        center_x = face_bbox['x'] + face_bbox['width'] // 2
        center_y = face_bbox['y'] + face_bbox['height'] // 2

        moved_enough = (
            last_tracked_center is None or
            abs(center_x - last_tracked_center[0]) > FACE_MOVE_THRESHOLD or
            abs(center_y - last_tracked_center[1]) > FACE_MOVE_THRESHOLD
        )

        if moved_enough:
            servo_tracker.track_face(face_bbox)
            last_tracked_center = (center_x, center_y)

        return now, last_tracked_center, TRACKING_MODE_FACE

    if sensor_motion_active:
        servo_tracker.move_pan_from_sensor(sensor_sample["x"], sensor_sample["y"])
        return last_face_seen_at, None, TRACKING_MODE_SENSOR

    if not sensor_tracking_enabled and now - last_face_seen_at > FACE_LOST_CENTER_DELAY:
        servo_tracker.center()

    return last_face_seen_at, None, current_mode


def detect_face_and_hands(sock, servo_tracker, sensor_reader=None):
    """Main detection loop for face and hand tracking.
    
    Args:
        sock: Camera stream socket
        servo_tracker: FaceTrackServo instance for face tracking
        sensor_reader: Optional sensor reader for motion-based pan fallback
    """
    mp_face_detection = mp.solutions.face_detection
    mp_hands = mp.solutions.hands
    mp_draw = mp.solutions.drawing_utils
    known_encodings, known_names = load_known_faces(FACE_DB_PATH)

    face_detector = mp_face_detection.FaceDetection(
        model_selection=0, min_detection_confidence=0.6
    )
    hands = mp_hands.Hands(
        static_image_mode=False,
        model_complexity=0,
        max_num_hands=2,
        min_detection_confidence=0.7,
        min_tracking_confidence=0.5,
    )

    # State tracking
    frame_count = 0
    latest_face_result, latest_face_labels = None, []
    latest_hand_result = None
    last_context_face_count = 0
    last_context_update_at = 0

    # Servo: track when face was last seen to avoid centering on brief drops
    last_face_seen_at = 0.0
    last_tracked_center = None
    tracking_mode = TRACKING_MODE_SENSOR if sensor_reader else TRACKING_MODE_FACE
    wake_gesture_state = {
        "sequence": [],
        "last_gesture": None,
        "last_step_at": 0.0,
        "last_trigger_at": 0.0,
        "center": None,
    }
    wake_gesture_status = None

    setup_display_window()

    try:
        for frame in read_frames(sock):
            frame_count += 1
            now = time.time()

            # Downscale for faster processing
            processing_frame = frame
            if PROCESS_SCALE < 1.0:
                processing_frame = cv2.resize(
                    frame, None, fx=PROCESS_SCALE, fy=PROCESS_SCALE,
                    interpolation=cv2.INTER_LINEAR
                )

            # Run face and hand detection on the same cadence to keep CPU usage stable.
            if frame_count % DETECT_EVERY_N_FRAMES == 0:
                latest_face_result, latest_hand_result = process_detection_frame(
                    processing_frame,
                    face_detector,
                    hands,
                )
                latest_face_labels = update_face_labels(
                    frame,
                    latest_face_result,
                    frame_count,
                    known_encodings,
                    known_names,
                    latest_face_labels,
                )
                wake_gesture_status = detect_wake_gesture(latest_hand_result, wake_gesture_state, now)
                wake_gesture_status["last_seen_at"] = now
                if wake_gesture_status.get("detected"):
                    set_wake_request()
                    print("[HAND] Wake gesture detected")

            # Update camera context from the latest detections and labels.
            latest_face_labels, last_context_face_count, last_context_update_at = update_camera_context(
                latest_face_result,
                latest_face_labels,
                frame_count,
                now,
                last_context_face_count,
                last_context_update_at,
            )

            sensor_sample = sensor_reader.get_latest() if sensor_reader else None

            # Draw detections and detect gestures
            if latest_face_result:
                draw_faces(frame, latest_face_result.detections, latest_face_labels)
            draw_hand_overlays(frame, latest_hand_result, mp_draw, mp_hands, frame_count)
            draw_wake_gesture_overlay(frame, wake_gesture_status, now)

            # Face updates run on the detection cadence; sensor fallback can run every frame.
            should_update_tracking = (
                frame_count % DETECT_EVERY_N_FRAMES == 0
                or bool(sensor_sample and sensor_sample.get("motion_detected"))
            )
            if should_update_tracking:
                last_face_seen_at, last_tracked_center, next_mode = update_servo_tracking(
                    latest_face_result,
                    sensor_sample,
                    sensor_reader is not None,
                    servo_tracker,
                    frame.shape,
                    now,
                    last_face_seen_at,
                    last_tracked_center,
                    tracking_mode,
                )
                if next_mode != tracking_mode:
                    print(f"[TRACKING] Mode -> {next_mode}")
                tracking_mode = next_mode
            
            # Upscale frame to fill the 720x1280 vertical display
            display_frame = cv2.resize(frame, (720, 1280), interpolation=cv2.INTER_LINEAR)
            cv2.imshow("Face and Hand Detection", display_frame)

            if (cv2.waitKey(1) & 0xFF) in (27, ord("q")):
                print(f"Exiting. Total frames: {frame_count}")
                break
    finally:
        servo_tracker.stop()
        if sensor_reader:
            sensor_reader.stop()
            sensor_reader.join(timeout=1.0)
        hands.close()
        face_detector.close()


def main():
    process = None
    sock = None
    servo_tracker = FaceTrackServo(verbose=False)
    sensor_reader = None

    try:
        # Start camera stream
        process = start_stream()
        threading.Thread(target=print_stream_logs, args=(process,), daemon=True).start()
        time.sleep(0.5)  # Give process time to start
        
        # Connect to camera stream
        try:
            sock = connect_stream(process)
        except RuntimeError as e:
            print(f"\n[ERROR] Camera connection failed: {e}")
            print("\nTroubleshooting:")
            print("  1. Check if camera is connected: vcgencmd get_camera")
            print("  2. Enable camera: sudo raspi-config -> Interface Options -> Camera")
            print("  3. Check permissions: v4l2-ctl --list-devices")
            print("  4. Try direct test: rpicam-still -o test.jpg")
            raise
        
        # Initialize servo tracking (optional - will skip if hardware not available)
        if not servo_tracker.initialize():
            print("[WARNING] Could not initialize servo hardware - face tracking disabled")

        sensor_reader = initialize_sensor_reader()
        detect_face_and_hands(sock, servo_tracker, sensor_reader)
    
    except Exception as e:
        print(f"\n[CRITICAL ERROR] {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        print("\nCleaning up...")
        servo_tracker.stop()
        if sensor_reader:
            sensor_reader.stop()
            sensor_reader.join(timeout=1.0)
        if sock:
            sock.close()
        if process:
            process.terminate()
            process.wait(timeout=5)
        cv2.destroyAllWindows()
        print("Cleanup complete.")


if __name__ == "__main__":
    main()
