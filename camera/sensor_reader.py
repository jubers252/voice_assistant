"""
Sensor Reader - Read person tracking data from serial sensor
Reads X, Y coordinates from presence/motion sensor
"""

import threading
import struct
import math
import time
from queue import Queue

try:
    import serial
    HAS_SERIAL = True
except ImportError:
    HAS_SERIAL = False
    print("Warning: pyserial not available")


class SensorReader(threading.Thread):
    """Read person position data from serial sensor (RD03D or similar)"""
    
    def __init__(self, port="/dev/ttyAMA0", baudrate=256000, daemon=False):
        """
        Initialize sensor reader thread.
        
        Args:
            port: Serial port device
            baudrate: Serial communication speed
            daemon: Whether to run as daemon thread
        """
        super().__init__(daemon=daemon)
        self.port = port
        self.baudrate = baudrate
        self.running = False
        self.latest_sample = None
        self.sample_queue = Queue(maxsize=5)
        self.error_count = 0
        self.max_errors = 10
        
    def run(self):
        """Main sensor reading loop"""
        if not HAS_SERIAL:
            print("[SENSOR] Serial module not available")
            return
        
        try:
            ser = serial.Serial(self.port, self.baudrate, timeout=1)
            print(f"[SENSOR] Connected to {self.port} at {self.baudrate} baud")
            self.running = True
            
            while self.running:
                try:
                    data = ser.read(24)
                    
                    if len(data) != 24:
                        continue
                    
                    # Check frame header
                    if data[0] != 0xAA or data[1] != 0xFF:
                        continue
                    
                    # Extract coordinates
                    raw_x = struct.unpack("<H", data[4:6])[0]
                    raw_y = struct.unpack("<H", data[6:8])[0]
                    
                    x = self._decode_coord(raw_x)
                    y = self._decode_coord(raw_y)
                    
                    if y == 0:
                        continue
                    
                    # Calculate angle
                    angle = math.degrees(math.atan2(x, y))
                    
                    sample = {
                        "x": x,
                        "y": y,
                        "angle": angle,
                        "motion_detected": True,
                        "timestamp": time.time()
                    }
                    
                    self.latest_sample = sample
                    self.error_count = 0
                    
                    # Try to add to queue (non-blocking)
                    try:
                        self.sample_queue.put_nowait(sample)
                    except:
                        pass
                    
                except Exception as e:
                    self.error_count += 1
                    if self.error_count >= self.max_errors:
                        print(f"[SENSOR] Too many errors ({self.error_count}), stopping reader")
                        break
            
            ser.close()
            print("[SENSOR] Connection closed")
            
        except FileNotFoundError:
            print(f"[SENSOR] Serial port {self.port} not found")
        except Exception as e:
            print(f"[SENSOR] Error: {e}")
        finally:
            self.running = False
    
    @staticmethod
    def _decode_coord(raw):
        """Decode signed coordinate from sensor"""
        if raw >= 0x8000:
            return raw - 0x8000
        else:
            return -raw
    
    def get_latest(self):
        """Get latest sensor sample (non-blocking)"""
        return self.latest_sample
    
    def stop(self):
        """Stop the sensor reader thread"""
        self.running = False


# For testing
if __name__ == "__main__":
    reader = SensorReader(daemon=True)
    reader.start()
    
    try:
        while True:
            sample = reader.get_latest()
            if sample:
                print(f"X={sample['x']:5d} Y={sample['y']:5d} Angle={sample['angle']:6.2f}°")
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("\nStopping...")
        reader.stop()
        reader.join(timeout=2)
