"""
Face and hand detection with integrated pan/tilt servo tracking.

This module combines face detection, hand gesture recognition,
and real-time servo control to track detected faces/hands.
"""

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
DETECT_EVERY_N_FRAMES = 2        # Detect every 2 frames (~15 FPS) for balance
FACE_RECOGNITION_EVERY_N_FRAMES = 30  # Recognize every 30 frames (reduce CPU)
PROCESS_SCALE = 0.35             # Much smaller = faster (was 0.5)
FACE_DB_PATH = "my_db"
FACE_MATCH_TOLERANCE = 0.5
CONTEXT_LOG_EVERY_N_FRAMES = 30
CAMERA_CONTEXT_UPDATE_SECONDS = 2
RECENT_KNOWN_PERSON_TTL_SECONDS = 10
FACE_RECOGNITION_STARTUP_GRACE_SECONDS = 2.5

# Hand gesture constants
FINGER_THRESHOLD = 0.05

# Face tracking servo constants
ENABLE_SERVO_TRACKING = True      # Set to False to disable servo control
DETECT_HANDS = False              # Set to True for hand detection (adds ~30% CPU load)


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


def detection_to_bbox_dict(detection, frame_width, frame_height):
    """Convert MediaPipe detection to bbox dict for servo tracking."""
    bbox = detection.location_data.relative_bounding_box
    x = max(0, int(bbox.xmin * frame_width))
    y = max(0, int(bbox.ymin * frame_height))
    width = int(bbox.width * frame_width)
    height = int(bbox.height * frame_height)
    return {'x': x, 'y': y, 'width': width, 'height': height}


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
    finger_tips = [8, 12, 16, 20]
    finger_pips = [6, 10, 14, 18]
    
    fingers_extended = 0
    
    for tip_idx, pip_idx in zip(finger_tips, finger_pips):
        tip = hand_landmarks.landmark[tip_idx]
        pip = hand_landmarks.landmark[pip_idx]
        
        if tip.y < pip.y:
            fingers_extended += 1
    
    # Thumb
    thumb_tip = hand_landmarks.landmark[4]
    thumb_cmc = hand_landmarks.landmark[2]
    if abs(thumb_tip.x - thumb_cmc.x) > 0.05:
        fingers_extended += 1
    
    return fingers_extended


def is_fist(hand_landmarks):
    """Detect if hand is in fist position."""
    if not hand_landmarks:
        return False
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


def detect_face_and_hands(sock, use_servo=ENABLE_SERVO_TRACKING):
    """Main detection loop for face and hand tracking with optional servo control."""
    mp_face_detection = mp.solutions.face_detection
    mp_hands = mp.solutions.hands
    mp_draw = mp.solutions.drawing_utils
    known_encodings, known_names = load_known_faces(FACE_DB_PATH)

    face_detector = mp_face_detection.FaceDetection(
        model_selection=0, min_detection_confidence=0.6
    )
    hands = mp_hands.Hands(
        static_image_mode=False,
        max_num_hands=2,
        min_detection_confidence=0.5,
        min_tracking_confidence=0.5,
    )
    
    # Initialize servo tracker if enabled
    servo_tracker = None
    if use_servo:
        servo_tracker = FaceTrackServo(verbose=False)
        if not servo_tracker.initialize():
            print("Warning: Could not initialize servo tracking. Continuing without servo.")
            servo_tracker = None

    frame_count = 0
    recent_known_person = None
    recent_known_person_time = 0
    last_context_log = time.time()

    try:
        for frame in read_frames(sock):
            frame_count += 1
            frame_height, frame_width = frame.shape[:2]

            # --- Face Detection ---
            detections = []
            labels = []
            try:
                if frame_count % DETECT_EVERY_N_FRAMES == 0:
                    results = face_detector.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
                    detections = list(results.detections) if results and results.detections else []

                    # Face Recognition
                    if frame_count % FACE_RECOGNITION_EVERY_N_FRAMES == 0:
                        labels = recognize_faces(frame, detections, known_encodings, known_names)

                    # Servo tracking: track the first detected face
                    if servo_tracker and detections:
                        try:
                            first_detection = detections[0]
                            bbox_dict = detection_to_bbox_dict(first_detection, frame_width, frame_height)
                            servo_tracker.track_face(bbox_dict)
                        except Exception as e:
                            print(f"Servo tracking error: {e}")
                    elif servo_tracker:
                        # No face detected, center servos
                        servo_tracker.center()
            except Exception as e:
                print(f"Face detection error: {e}")

            draw_faces(frame, detections, labels)

            # --- Hand Detection ---
            hand_results = None
            if DETECT_HANDS:
                try:
                    hand_results = hands.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
                except Exception as e:
                    print(f"Hand detection process error: {e}")
                    hand_results = None
            
            if hand_results and hand_results.multi_hand_landmarks:
                try:
                    for hand_landmarks in hand_results.multi_hand_landmarks:
                        mp_draw.draw_landmarks(
                            frame,
                            hand_landmarks,
                            mp_hands.HAND_CONNECTIONS,
                            mp_draw.DrawingSpec(color=(0, 0, 255), thickness=2, circle_radius=2),
                            mp_draw.DrawingSpec(color=(255, 0, 0), thickness=2),
                        )

                        gesture_info = get_hand_gesture(hand_results.multi_hand_landmarks[0])
                        if gesture_info:
                            cv2.putText(
                                frame,
                                f"Gesture: {gesture_info['gesture']} ({gesture_info['fingers']} fingers)",
                                (10, 30),
                                cv2.FONT_HERSHEY_SIMPLEX,
                                0.7,
                                (255, 255, 255),
                                2,
                            )
                except Exception as e:
                    print(f"Hand processing error: {e}")

            # --- Display Info ---
            cv2.putText(
                frame,
                f"Frame: {frame_count}",
                (10, frame_height - 20),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (200, 200, 200),
                1,
            )
            
            if servo_tracker and servo_tracker.initialized:
                cv2.putText(
                    frame,
                    "SERVO TRACKING: ON",
                    (10, 60),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.6,
                    (0, 255, 0),
                    2,
                )

            # --- Update Context ---
            if time.time() - last_context_log > CAMERA_CONTEXT_UPDATE_SECONDS:
                if frame_count % CONTEXT_LOG_EVERY_N_FRAMES == 0:
                    try:
                        num_faces = len(detections) if isinstance(detections, (list, tuple)) else 0
                        num_hands = 0
                        if hand_results and hand_results.multi_hand_landmarks:
                            if isinstance(hand_results.multi_hand_landmarks, (list, tuple)):
                                num_hands = len(hand_results.multi_hand_landmarks)
                        write_camera_context(num_faces, num_hands)
                        last_context_log = time.time()
                    except Exception as e:
                        print(f"Context logging error: {e}")

            cv2.imshow("Face & Hand Detection with Servo Tracking", frame)

            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

    except KeyboardInterrupt:
        print("\nInterrupted.")
    except Exception as e:
        print(f"Main loop error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if servo_tracker:
            servo_tracker.stop()
        face_detector.close()
        hands.close()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    process = None
    sock = None

    try:
        process = start_stream()
        stream_thread = threading.Thread(target=print_stream_logs, args=(process,), daemon=True)
        stream_thread.start()

        sock = connect_stream(process)
        detect_face_and_hands(sock)

    except Exception as e:
        print(f"Error: {e}")
    finally:
        if sock:
            sock.close()
        if process:
            process.terminate()
            process.wait()
