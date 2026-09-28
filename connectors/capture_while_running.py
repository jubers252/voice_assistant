import os
import socket
import time
from pathlib import Path
from urllib.parse import urlparse

import cv2
import numpy as np

MAX_CAPTURE_IMAGES = 5


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


def capture_images_from_running_stream(
    count: int = MAX_CAPTURE_IMAGES, note: str = "manual_test"
) -> list[tuple[bytes, str]]:
    """
    Capture frames and overwrite the stable output/captures/latest_NN.jpg files.

    Returns a list of (JPEG bytes, saved path) pairs. At most five images are
    retained; requesting fewer removes stale slots from the previous capture.

    Expected stream source:
    - CAMERA_STREAM_URL env var, or
    - default tcp://127.0.0.1:8003
    """
    if not isinstance(count, int) or isinstance(count, bool) or not 1 <= count <= MAX_CAPTURE_IMAGES:
        raise ValueError(f"Image count must be between 1 and {MAX_CAPTURE_IMAGES}")

    stream_url = os.getenv("CAMERA_STREAM_URL", "tcp://127.0.0.1:8003")
    output_dir = Path(__file__).resolve().parent.parent / "output" / "captures"
    output_dir.mkdir(parents=True, exist_ok=True)
    sock = None
    try:
        host, port = parse_tcp_stream_url(stream_url)
        sock = connect_stream_socket(host, port)
        buffer = b""
        captured_jpegs = []

        for index in range(count):
            frame, buffer = read_one_jpeg_frame(sock, buffer)
            if frame is None:
                raise RuntimeError(
                    f"Connected, but failed to read/decode JPEG frame {index + 1}/{count} from stream"
                )

            ok, encoded = cv2.imencode(".jpg", frame)
            if not ok:
                raise RuntimeError(f"Frame {index + 1}/{count} could not be encoded as JPEG")
            captured_jpegs.append(encoded.tobytes())

        saved_images = []
        for index, jpeg_bytes in enumerate(captured_jpegs, start=1):
            out_path = output_dir / f"latest_{index:02d}.jpg"
            temp_path = output_dir / f".latest_{index:02d}.jpg.tmp"
            temp_path.write_bytes(jpeg_bytes)
            os.replace(temp_path, out_path)
            saved_images.append((jpeg_bytes, str(out_path)))

        # Keep the output set limited to the most recently requested count.
        for index in range(count + 1, MAX_CAPTURE_IMAGES + 1):
            (output_dir / f"latest_{index:02d}.jpg").unlink(missing_ok=True)
        # Remove the single-image filename used by the previous implementation.
        (output_dir / "latest.jpg").unlink(missing_ok=True)
        return saved_images

    except Exception as e:
        raise RuntimeError(f"Capture error: {e}") from e
    finally:
        if sock:
            sock.close()


if __name__ == "__main__":
    image_count = 5

    images = capture_images_from_running_stream(image_count)
    print(f"[OK] Captured {len(images)} image(s): " + ", ".join(path for _, path in images))
