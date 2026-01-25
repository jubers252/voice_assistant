"""
Raspberry Pi Camera Streaming with Hand Detection + Swipe Detection
Swipe Left / Swipe Right using MediaPipe
"""

import subprocess
import time
import socket
from collections import deque
from flask import Flask, Response, render_template_string
import cv2
import numpy as np
import mediapipe as mp

app = Flask(__name__)

STREAM_PORT = 8001

# =========================
# MediaPipe setup
# =========================
mp_hands = mp.solutions.hands
mp_draw = mp.solutions.drawing_utils

hands = mp_hands.Hands(
    static_image_mode=False,
    max_num_hands=1,
    min_detection_confidence=0.6,  # Balanced for continuous detection
    min_tracking_confidence=0.6    # Balanced for continuous detection
)

# =========================
# Gray color detection setup (HSV range)
# =========================
# Gray in HSV: Strict range for true gray only (low saturation)
GRAY_LOWER = np.array([0, 0, 80])
GRAY_UPPER = np.array([180, 30, 200])

# =========================
# Swipe detection config
# =========================
hand_x_history = deque(maxlen=10)
hand_time_history = deque(maxlen=10)

SWIPE_DISTANCE = 0.20   # normalized (20% of screen width)
SWIPE_TIME = 0.6        # seconds


class CameraStreamer:
    def __init__(self, width=640, height=480, fps=30):
        self.width = width
        self.height = height
        self.fps = fps
        self.running = False
        self.camera_process = None

    def start_camera(self):
        cmd = [
            'rpicam-vid',
            '-t', '0',
            '--width', str(self.width),
            '--height', str(self.height),
            '--framerate', str(self.fps),
            '--codec', 'mjpeg',
            '--inline',
            '--listen',
            '-o', f'tcp://0.0.0.0:{STREAM_PORT}',
            '-n',
            '--gain', '4.0',  # Optimized for indoor light (not too high to avoid noise)
            '--exposure', 'normal',  # Normal exposure for typical indoor lighting
            '--brightness', '0.3',  # Moderate brightness boost
            '--contrast', '0.6',  # Slight contrast increase for better clarity
            '--saturation', '1.0',  # Normal saturation
            '--sharpness', '1.5',  # Slight sharpness for better hand detection
            '--awb', 'indoor'  # Auto white balance optimized for indoor
        ]

        self.camera_process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT
        )

        time.sleep(3)
        self.running = True
        print("📸 Camera started")
        return True

    def stop_camera(self):
        if self.camera_process:
            self.camera_process.terminate()
            self.camera_process.wait()
            self.running = False
            print("🛑 Camera stopped")

    def generate_frames(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 65536)
        sock.connect(('127.0.0.1', STREAM_PORT))
        sock.settimeout(2.0)

        buffer = b''
        frame_count = 0
        max_buffer_size = 2097152  # 2MB limit to prevent memory issues

        while self.running:
            try:
                data = sock.recv(8192)
                if not data:
                    break
                
                buffer += data
                if len(buffer) > max_buffer_size:
                    buffer = buffer[-max_buffer_size:]
            except socket.timeout:
                continue
            except Exception as e:
                print(f"Socket error: {e}")
                break

            while True:
                a = buffer.find(b'\xff\xd8')
                b = buffer.find(b'\xff\xd9')

                if a != -1 and b != -1 and b > a:
                    jpg = buffer[a:b+2]
                    buffer = buffer[b+2:]

                    frame = cv2.imdecode(
                        np.frombuffer(jpg, np.uint8),
                        cv2.IMREAD_COLOR
                    )

                    if frame is None:
                        continue

                    frame_count += 1

                    # Process every 3rd frame for continuous hand detection
                    if frame_count % 3 == 0:
                        # Light-weight enhancement (skip CLAHE in good light)
                        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                        result = hands.process(rgb)

                        if result.multi_hand_landmarks:
                            for hand_landmarks in result.multi_hand_landmarks:
                                mp_draw.draw_landmarks(
                                    frame,
                                    hand_landmarks,
                                    mp_hands.HAND_CONNECTIONS
                                )

                                # =========================
                                # Swipe detection
                                # =========================
                                wrist = hand_landmarks.landmark[
                                    mp_hands.HandLandmark.WRIST
                                ]

                                hand_x_history.append(wrist.x)
                                hand_time_history.append(time.time())

                                if len(hand_x_history) >= 6:
                                    dx = hand_x_history[-1] - hand_x_history[0]
                                    dt = hand_time_history[-1] - hand_time_history[0]

                                    if dt < SWIPE_TIME:
                                        if dx > SWIPE_DISTANCE:
                                            print("➡️ Swipe Right")
                                            hand_x_history.clear()
                                            hand_time_history.clear()

                                        elif dx < -SWIPE_DISTANCE:
                                            print("⬅️ Swipe Left")
                                            hand_x_history.clear()
                                            hand_time_history.clear()
                        
                        # =========================
                        # Gray color detection (lightweight, skip if hands found)
                        # =========================
                        if not result.multi_hand_landmarks:
                            hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
                            gray_mask = cv2.inRange(hsv, GRAY_LOWER, GRAY_UPPER)
                            
                            # Strong morphological cleanup
                            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
                            gray_mask = cv2.morphologyEx(gray_mask, cv2.MORPH_OPEN, kernel, iterations=2)
                            gray_mask = cv2.morphologyEx(gray_mask, cv2.MORPH_CLOSE, kernel, iterations=1)
                            
                            # Find contours
                            contours, _ = cv2.findContours(gray_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                            
                            gray_count = 0
                            for contour in contours:
                                area = cv2.contourArea(contour)
                                if area > 2000:  # Very high threshold to eliminate noise
                                    cv2.drawContours(frame, [contour], 0, (0, 255, 255), 2)
                                    gray_count += 1
                                    if gray_count > 3:  # Max 3 detections
                                        break
                            
                            if gray_count > 0:
                                cv2.putText(frame, f"Gray: {gray_count}", (10, 30),
                                           cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)

                    success, jpg_encoded = cv2.imencode(
                        '.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 70]
                    )

                    if not success:
                        continue

                    yield (
                        b'--frame\r\n'
                        b'Content-Type: image/jpeg\r\n\r\n' +
                        jpg_encoded.tobytes() +
                        b'\r\n'
                    )
                else:
                    break


streamer = None


@app.route('/')
def index():
    return render_template_string("""
    <html>
    <head>
        <title>Hand Swipe Detection</title>
    </head>
    <body style="background:#111;color:white;text-align:center">
        <h1>✋ Hand Swipe Detection</h1>
        <img src="/video_feed">
        <p>Swipe Left ⬅️ or Right ➡️</p>
    </body>
    </html>
    """)


@app.route('/video_feed')
def video_feed():
    return Response(
        streamer.generate_frames(),
        mimetype='multipart/x-mixed-replace; boundary=frame'
    )


def main():
    global streamer
    streamer = CameraStreamer(640, 480, 30)

    if not streamer.start_camera():
        return

    try:
        app.run(host='0.0.0.0', port=8000, threaded=True)
    except KeyboardInterrupt:
        pass
    finally:
        streamer.stop_camera()


if __name__ == "__main__":
    main()
