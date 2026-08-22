import os
import re
import socket
import time
from datetime import datetime
from urllib.parse import urlparse

import cv2
import numpy as np


def parse_tcp_stream_url(stream_url: str) -> tuple[str, int]:
    parsed = urlparse(stream_url)
    if parsed.scheme != "tcp":
        raise ValueError(f"Only tcp:// stream URLs are supported in this script. Got: {stream_url}")

    host = parsed.hostname or "127.0.0.1"
    port = parsed.port
    if not port:
        raise ValueError(f"Missing port in stream URL: {stream_url}")
    return host, port


def connect_stream_socket(host: str, port: int, attempts: int = 40, delay_s: float = 0.25) -> socket.socket:
    print(f"Connecting to camera stream at tcp://{host}:{port} ...")
    for _ in range(attempts):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 32768)
        sock.settimeout(2)
        try:
            sock.connect((host, port))
            print("Camera stream connected.")
            return sock
        except OSError:
            sock.close()
            time.sleep(delay_s)

    raise RuntimeError(f"Could not connect to camera stream at tcp://{host}:{port}")


def read_one_jpeg_frame(sock: socket.socket, buffer: bytes = b"", max_buffer_size: int = 512 * 1024):
    while True:
        data = sock.recv(32768)
        if not data:
            return None, buffer

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
                return frame, buffer


def capture_images_from_running_stream(count: int = 1, note: str = "manual_test") -> str:
    """
    Capture one or more frames from the existing running camera stream process.

    Expected stream source:
    - CAMERA_STREAM_URL env var, or
    - default tcp://127.0.0.1:8003
    """
    if count <= 0:
        return "[FAIL] Image count must be greater than 0"

    stream_url = os.getenv("CAMERA_STREAM_URL", "tcp://127.0.0.1:8003")
    output_dir = os.path.join("output", "captures")
    os.makedirs(output_dir, exist_ok=True)

    safe_note = re.sub(r"[^a-zA-Z0-9_-]+", "_", (note or "capture")).strip("_")
    if not safe_note:
        safe_note = "capture"

    base_ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    sock = None
    try:
        host, port = parse_tcp_stream_url(stream_url)
        sock = connect_stream_socket(host, port)
        buffer = b""
        saved_paths = []

        for index in range(count):
            frame, buffer = read_one_jpeg_frame(sock, buffer)
            if frame is None:
                return f"[FAIL] Connected, but failed to read/decode JPEG frame {index + 1}/{count} from stream"

            suffix = f"_{index + 1:02d}" if count > 1 else ""
            out_path = os.path.join(output_dir, f"{safe_note}_{base_ts}{suffix}.jpg")
            saved = cv2.imwrite(out_path, frame)
            if not saved:
                return f"[FAIL] Frame {index + 1}/{count} captured but failed to save image"

            if not os.path.exists(out_path) or os.path.getsize(out_path) <= 0:
                return f"[FAIL] Saved file invalid: {out_path}"

            saved_paths.append(out_path)

        return f"[OK] Captured {len(saved_paths)} image(s): " + ", ".join(saved_paths)
    except Exception as e:
        return f"[FAIL] Capture error: {e}"
    finally:
        if sock:
            sock.close()


if __name__ == "__main__":
    image_count = 5

   

    print(capture_images_from_running_stream(image_count, "assistant_running_test"))
