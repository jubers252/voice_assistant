"""
Simple Camera Streaming for Raspberry Pi
Uses rpicam-vid with TCP streaming
"""

import subprocess
import time
import socket
import threading
from flask import Flask, Response, render_template_string

app = Flask(__name__)

# Global variables
camera_process = None
stream_socket = None
STREAM_PORT = 8001


class CameraStreamer:
    def __init__(self, width=640, height=480, fps=30):
        self.width = width
        self.height = height
        self.fps = fps
        self.camera_process = None
        self.running = False
        
    def start_camera(self):
        """Start camera with TCP streaming"""
        print(f"Starting camera stream {self.width}x{self.height}...")
        
        # Use rpicam-vid with inline MJPEG output
        cmd = [
            'rpicam-vid',
            '-t', '0',  # Run indefinitely
            '--width', str(self.width),
            '--height', str(self.height),
            '--framerate', str(self.fps),
            '--codec', 'mjpeg',
            '--inline',
            '--listen',  # TCP listen mode
            '-o', f'tcp://0.0.0.0:{STREAM_PORT}',
            '-n'  # No preview window
        ]
        
        try:
            self.camera_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT
            )
            self.running = True
            print(f"Camera process started (PID: {self.camera_process.pid})")
            time.sleep(3)  # Give camera time to initialize
            
            # Check if process is still running
            if self.camera_process.poll() is not None:
                output, _ = self.camera_process.communicate()
                print(f"Camera process failed: {output.decode()}")
                return False
            
            print(f"Camera is streaming on TCP port {STREAM_PORT}")
            return True
        except Exception as e:
            print(f"Error starting camera: {e}")
            return False
    
    def stop_camera(self):
        """Stop the camera process"""
        if self.camera_process:
            self.camera_process.terminate()
            try:
                self.camera_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.camera_process.kill()
            self.running = False
            print("Camera stopped")
    
    def generate_frames(self):
        """Connect to camera TCP stream and yield frames"""
        retry_count = 0
        max_retries = 15
        
        print("Attempting to connect to camera stream...")
        
        while retry_count < max_retries:
            try:
                # Connect to the TCP stream
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(15)
                print(f"Connecting to 127.0.0.1:{STREAM_PORT}...")
                sock.connect(('127.0.0.1', STREAM_PORT))
                print("✓ Connected to camera stream successfully")
                
                buffer = b''
                frame_count = 0
                
                while self.running:
                    try:
                        # Read data from socket
                        data = sock.recv(8192)
                        if not data:
                            print("No more data from camera")
                            break
                        
                        buffer += data
                        
                        # Look for JPEG boundaries
                        while True:
                            a = buffer.find(b'\xff\xd8')  # JPEG start
                            b = buffer.find(b'\xff\xd9')  # JPEG end
                            
                            if a != -1 and b != -1 and b > a:
                                jpg = buffer[a:b+2]
                                buffer = buffer[b+2:]
                                
                                frame_count += 1
                                if frame_count % 30 == 0:
                                    print(f"Streamed {frame_count} frames")
                                
                                # Yield the frame
                                yield (b'--frame\r\n'
                                       b'Content-Type: image/jpeg\r\n\r\n' + jpg + b'\r\n')
                            else:
                                break
                    
                    except socket.timeout:
                        print("Socket timeout, continuing...")
                        continue
                    except Exception as e:
                        print(f"Error reading frame: {e}")
                        break
                
                sock.close()
                break
                
            except ConnectionRefusedError:
                retry_count += 1
                print(f"Connection refused, attempt {retry_count}/{max_retries}")
                time.sleep(1)
            except socket.timeout as e:
                retry_count += 1
                print(f"Connection timeout, attempt {retry_count}/{max_retries}: {e}")
                time.sleep(1)
            except Exception as e:
                print(f"Streaming error: {e}")
                import traceback
                traceback.print_exc()
                break
        
        if retry_count >= max_retries:
            print("Failed to connect to camera stream after all retries")


# Global streamer instance
streamer = None


@app.route('/')
def index():
    """Video streaming home page"""
    return render_template_string('''
        <!DOCTYPE html>
        <html>
        <head>
            <title>Raspberry Pi Camera Stream</title>
            <style>
                body {
                    font-family: Arial, sans-serif;
                    text-align: center;
                    background-color: #1a1a1a;
                    color: #fff;
                    margin: 0;
                    padding: 20px;
                }
                h1 {
                    color: #4CAF50;
                    margin-bottom: 10px;
                }
                .video-container {
                    display: inline-block;
                    background-color: #000;
                    padding: 10px;
                    border-radius: 8px;
                    box-shadow: 0 4px 12px rgba(76, 175, 80, 0.3);
                    margin: 20px auto;
                }
                img {
                    display: block;
                    max-width: 100%;
                    height: auto;
                    border-radius: 4px;
                }
                .info {
                    margin-top: 20px;
                    color: #999;
                    font-size: 14px;
                }
                .status {
                    display: inline-block;
                    background: #4CAF50;
                    color: white;
                    padding: 5px 15px;
                    border-radius: 20px;
                    font-size: 12px;
                    margin: 10px 0;
                }
            </style>
        </head>
        <body>
            <h1>📷 Raspberry Pi Camera Stream</h1>
            <div class="status">🟢 LIVE</div>
            <div class="video-container">
                <img src="{{ url_for('video_feed') }}" alt="Camera Stream" />
            </div>
            <div class="info">
                <p>Resolution: ''' + f'{streamer.width}x{streamer.height}' + ''' @ ''' + f'{streamer.fps} fps' + '''</p>
                <p>Codec: MJPEG | Protocol: TCP</p>
            </div>
        </body>
        </html>
    ''')


@app.route('/video_feed')
def video_feed():
    """Video streaming route"""
    return Response(
        streamer.generate_frames(),
        mimetype='multipart/x-mixed-replace; boundary=frame'
    )


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Raspberry Pi Camera HTTP Streaming')
    parser.add_argument('--width', type=int, default=640, help='Video width')
    parser.add_argument('--height', type=int, default=480, help='Video height')
    parser.add_argument('--fps', type=int, default=30, help='Frames per second')
    parser.add_argument('--port', type=int, default=8000, help='HTTP server port')
    
    args = parser.parse_args()
    
    global streamer
    streamer = CameraStreamer(width=args.width, height=args.height, fps=args.fps)
    
    try:
        if not streamer.start_camera():
            print("Failed to start camera")
            return
        
        print(f"\n🎥 Camera stream available at:")
        print(f"   http://localhost:{args.port}")
        print(f"   http://<raspberry-pi-ip>:{args.port}")
        print(f"\n📡 Streaming at {args.width}x{args.height} @ {args.fps}fps")
        print("\nPress Ctrl+C to stop\n")
        
        app.run(host='0.0.0.0', port=args.port, threaded=True, debug=False)
        
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        streamer.stop_camera()


if __name__ == '__main__':
    main()
