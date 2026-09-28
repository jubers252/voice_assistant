"""Share the detection process's JPEG relay with browser viewers."""
import socket
import threading
import time


class CameraFeed:
    def __init__(self, host='127.0.0.1', port=8003):
        self.host, self.port = host, port
        self.condition = threading.Condition()
        self.frame = None
        self.updated_at = 0
        self.sequence = 0
        self.thread = None

    def start(self):
        with self.condition:
            if self.thread is None:
                self.thread = threading.Thread(target=self._receive, daemon=True)
                self.thread.start()

    def available(self):
        with self.condition:
            return self.frame is not None and time.monotonic() - self.updated_at < 5

    def _receive(self):
        while True:
            try:
                with socket.create_connection((self.host, self.port), timeout=3) as connection:
                    connection.settimeout(3)
                    buffer = bytearray()
                    while True:
                        chunk = connection.recv(65536)
                        if not chunk:
                            raise ConnectionError('Camera relay closed')
                        buffer.extend(chunk)
                        while True:
                            start = buffer.find(b'\xff\xd8')
                            if start < 0:
                                buffer[:] = buffer[-1:]
                                break
                            if start:
                                del buffer[:start]
                            end = buffer.find(b'\xff\xd9', 2)
                            if end < 0:
                                break
                            frame = bytes(buffer[:end + 2])
                            del buffer[:end + 2]
                            with self.condition:
                                self.frame = frame
                                self.updated_at = time.monotonic()
                                self.sequence += 1
                                self.condition.notify_all()
                        if len(buffer) > 8 * 1024 * 1024:
                            raise ValueError('Camera frame exceeds size limit')
            except (OSError, ValueError):
                with self.condition:
                    self.frame = None
                    self.condition.notify_all()
                time.sleep(1)

    def stream(self):
        sequence = -1
        while True:
            with self.condition:
                self.condition.wait_for(
                    lambda: self.sequence != sequence and self.frame is not None,
                    timeout=5,
                )
                if self.frame is None or time.monotonic() - self.updated_at >= 5:
                    return
                sequence, frame = self.sequence, self.frame
            yield (b'--frame\r\nContent-Type: image/jpeg\r\nContent-Length: '
                   + str(len(frame)).encode() + b'\r\n\r\n' + frame + b'\r\n')
