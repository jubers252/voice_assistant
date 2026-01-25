import cv2
import mediapipe as mp
import sys
import os

# Suppress TensorFlow warnings
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'

# Initialize MediaPipe
mp_hands = mp.solutions.hands
mp_draw = mp.solutions.drawing_utils

hands = mp_hands.Hands(
    static_image_mode=False,     # False for video stream
    max_num_hands=2,
    min_detection_confidence=0.7,
    min_tracking_confidence=0.7
)

# For Raspberry Pi with CSI camera and libcamera backend
print("Attempting to open CSI camera...")

# Try different video devices - ISP output nodes usually work better
video_devices = ['/dev/video20', '/dev/video21', '/dev/video0', 0]

cap = None
for device in video_devices:
    print(f"  Trying {device}...")
    try:
        cap = cv2.VideoCapture(device, cv2.CAP_V4L2)
        if cap.isOpened():
            # Try to read one frame to confirm it works
            ret, _ = cap.read()
            if ret:
                print(f"✓ Camera opened successfully on {device}!")
                break
            else:
                print(f"  {device} opened but can't read frames")
                cap.release()
                cap = None
    except:
        pass

if cap is None or not cap.isOpened():
    print("\nERROR: Camera not available.")
    print("\nTo enable CSI camera:")
    print("  1. sudo raspi-config")
    print("  2. Interface Options -> Camera -> Enable")
    print("  3. Reboot")
    print("\nTo debug: v4l2-ctl --list-devices")
    sys.exit(1)

# Set camera properties for better performance
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
cap.set(cv2.CAP_PROP_FPS, 30)

frame_count = 0
error_count = 0

while True:
    success, frame = cap.read()
    frame_count += 1
    
    if not success:
        error_count += 1
        print(f"ERROR: Failed to read frame {frame_count} (Error count: {error_count})")
        if error_count > 5:
            print("Too many consecutive read errors. Exiting...")
            break
        continue
    
    error_count = 0  # Reset error count on successful read

    # Convert BGR to RGB
    rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    result = hands.process(rgb_frame)

    if result.multi_hand_landmarks:
        for hand_landmarks in result.multi_hand_landmarks:
            mp_draw.draw_landmarks(
                frame,
                hand_landmarks,
                mp_hands.HAND_CONNECTIONS
            )
        if frame_count % 30 == 0:
            print(f"Frame {frame_count}: Detected {len(result.multi_hand_landmarks)} hand(s)")

    cv2.imshow("Hand Detection", frame)

    if cv2.waitKey(1) & 0xFF == 27:  # ESC to exit
        print(f"Exiting. Total frames processed: {frame_count}")
        break

cap.release()
cv2.destroyAllWindows()
