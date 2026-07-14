import os
import socket
import subprocess
import threading
import time

import cv2
import mediapipe as mp
import numpy as np

from camera_context import write_camera_context
from face_track_servo import FaceTrackServo

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
DETECT_EVERY_N_FRAMES = 4     # Detect every 4 frames for stable tracking
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
    return subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)


def print_stream_logs(process):
    for line in iter(process.stdout.readline, b""):
        print(f"camera: {line.decode(errors='replace').rstrip()}")


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
    elif fingers == 5:
        gesture = "open_hand"
    elif fingers == 2:
        gesture = "peace"
    
    return {
        "gesture": gesture,
        "fingers": fingers
    }


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


def update_servo_tracking(face_result, servo_tracker, frame_shape, now, last_face_seen_at, last_tracked_center):
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

        return now, last_tracked_center

    if now - last_face_seen_at > FACE_LOST_CENTER_DELAY:
        servo_tracker.center()

    return last_face_seen_at, None


def detect_face_and_hands(sock, servo_tracker):
    """Main detection loop for face and hand tracking.
    
    Args:
        sock: Camera stream socket
        servo_tracker: FaceTrackServo instance for face tracking
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

            # Run detection every N frames
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
            draw_hand_overlays(frame, latest_hand_result, mp_draw, mp_hands, frame_count)

            # Track face with servo ONLY when face actually moves
            if frame_count % DETECT_EVERY_N_FRAMES == 0:
                last_face_seen_at, last_tracked_center = update_servo_tracking(
                    latest_face_result,
                    servo_tracker,
                    frame.shape,
                    now,
                    last_face_seen_at,
                    last_tracked_center,
                )
            
            # Upscale frame to fill the 720x1280 vertical display
            display_frame = cv2.resize(frame, (720, 1280), interpolation=cv2.INTER_LINEAR)
            cv2.imshow("Face and Hand Detection", display_frame)

            if (cv2.waitKey(1) & 0xFF) in (27, ord("q")):
                print(f"Exiting. Total frames: {frame_count}")
                break
    finally:
        servo_tracker.stop()
        hands.close()
        face_detector.close()


def main():
    process = start_stream()
    threading.Thread(target=print_stream_logs, args=(process,), daemon=True).start()
    sock = None
    servo_tracker = FaceTrackServo(verbose=False)

    try:
        sock = connect_stream(process)
        
        # Initialize servo tracking (optional - will skip if hardware not available)
        if not servo_tracker.initialize():
            print("[WARNING] Could not initialize servo hardware - face tracking disabled")
        
        detect_face_and_hands(sock, servo_tracker)
    finally:
        servo_tracker.stop()
        if sock:
            sock.close()
        process.terminate()
        process.wait()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
