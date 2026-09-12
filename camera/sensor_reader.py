"""
Sensor Reader - Read person tracking data from serial sensor
Reads X, Y coordinates from presence/motion sensor with servo tracking
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

try:
    from .face_track_servo import FaceTrackServo
    HAS_SERVO = True
except ImportError:
    try:
        # Fallback for direct script execution
        from face_track_servo import FaceTrackServo
        HAS_SERVO = True
    except ImportError:
        HAS_SERVO = False
        print("Warning: servo control not available")


class SensorReader(threading.Thread):
    """Read person position data from serial sensor (RD03D or similar)"""
    
    def __init__(self, port="/dev/ttyAMA0", baudrate=256000, daemon=False, enable_servo=True, verbose=False, servo_speed=5):
        """
        Initialize sensor reader thread.
        
        Args:
            port: Serial port device
            baudrate: Serial communication speed
            daemon: Whether to run as daemon thread
            enable_servo: Whether to enable servo tracking
            verbose: Enable debug output
            servo_speed: Servo response speed in degrees per update (default 5 for stability)
        """
        super().__init__(daemon=daemon)
        self.port = port
        self.baudrate = baudrate
        self.running = False
        self.latest_sample = None
        self.sample_queue = Queue(maxsize=5)
        self.error_count = 0
        self.max_errors = 10
        self.enable_servo = enable_servo and HAS_SERVO
        self.servo = None
        self.verbose = verbose
        self.servo_speed = servo_speed
        
        # Servo stability controls
        self.angle_smoothing_buffer = []
        self.smoothing_window_size = 5  # Number of readings to average
        self.angle_deadzone = 2.0  # Ignore movements < 2 degrees
        self.last_servo_angle = 0.0
        
    def run(self):
        """Main sensor reading loop"""
        if not HAS_SERIAL:
            print("[SENSOR] Serial module not available")
            return
        
        # Initialize servo if enabled
        if self.enable_servo:
            print("[SENSOR] Initializing servo...")
            self.servo = FaceTrackServo(verbose=self.verbose)
            if not self.servo.initialize():
                print("[SENSOR] Failed to initialize servo, tracking disabled")
                self.servo = None
            else:
                print("[SENSOR] ✓ Servo initialized successfully")
        else:
            print("[SENSOR] Servo tracking disabled")
        
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
                    
                    # Calculate pan angle (horizontal)
                    pan_angle = math.degrees(math.atan2(x, y))
                    
                    sample = {
                        "x": x,
                        "y": y,
                        "pan_angle": pan_angle,
                        "motion_detected": True,
                        "timestamp": time.time()
                    }
                    
                    self.latest_sample = sample
                    self.error_count = 0
                    
                    # Control servo if enabled
                    if self.servo:
                        self._control_servo(pan_angle)
                    
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
            if self.servo:
                self.servo = None
    
    @staticmethod
    def _decode_coord(raw):
        """Decode signed coordinate from sensor"""
        if raw >= 0x8000:
            return raw - 0x8000
        else:
            return -raw
    
    def _control_servo(self, pan_angle):
        """
        Control servo motor based on sensor pan angle with stability features.
        
        Features:
        - Angle smoothing to reduce noise
        - Deadzone to prevent micro-movements
        - Rate limiting for smooth motion
        - Hysteresis to prevent oscillation
        
        Args:
            pan_angle: Horizontal angle in degrees
        """
        if not self.servo:
            return
        
        try:
            # Clamp angle to servo limits first
            pan_angle = max(-70, min(70, pan_angle))
            
            # Apply smoothing by averaging recent readings
            self.angle_smoothing_buffer.append(pan_angle)
            if len(self.angle_smoothing_buffer) > self.smoothing_window_size:
                self.angle_smoothing_buffer.pop(0)
            
            # Use smoothed angle
            smoothed_angle = sum(self.angle_smoothing_buffer) / len(self.angle_smoothing_buffer)
            
            # Apply deadzone - only move if change exceeds threshold
            angle_delta = abs(smoothed_angle - self.last_servo_angle)
            if angle_delta < self.angle_deadzone:
                # Ignore small movements
                if self.verbose and angle_delta > 0:
                    print(f"[SERVO] Deadzone: ignored {angle_delta:.2f}° (threshold: {self.angle_deadzone}°)")
                return
            
            # Calculate movement direction and limit rate of change
            target_angle = smoothed_angle
            current_angle = self.last_servo_angle
            delta = target_angle - current_angle
            
            # Limit rate of change for smooth motion
            if abs(delta) > self.servo_speed:
                final_angle = current_angle + (self.servo_speed if delta > 0 else -self.servo_speed)
            else:
                final_angle = target_angle
            
            # Command servo directly
            self.servo.pan_pwm.change_duty_cycle(self.servo.angle_to_duty_cycle(final_angle))
            self.servo.last_pan_angle = final_angle
            self.last_servo_angle = final_angle
            self.servo.pan_angle_buffer.clear()
            self.servo.pan_angle_buffer.append(final_angle)
            
            if self.verbose:
                print(f"[SERVO] Pan: raw={pan_angle:6.2f}° -> smooth={smoothed_angle:6.2f}° -> cmd={final_angle:6.2f}°")
                
        except Exception as e:
            print(f"[SENSOR] Servo control error: {e}")
            import traceback
            traceback.print_exc()
    
    def get_latest(self):
        """Get latest sensor sample (non-blocking)"""
        return self.latest_sample
    
    def stop(self):
        """Stop the sensor reader thread"""
        self.running = False


# For testing
if __name__ == "__main__":
    """
    Servo stability parameters:
    - servo_speed: degrees per update (default 5 for smooth motion)
                   - Reduce to 2-3 for very smooth but slower response
                   - Increase to 8-10 for faster response (may jitter)
    
    Example usage:
        # Stable and smooth tracking
        reader = SensorReader(daemon=True, enable_servo=True, servo_speed=3)
        
        # More responsive (may be slightly jittery)
        reader = SensorReader(daemon=True, enable_servo=True, servo_speed=8)
    """
    reader = SensorReader(daemon=True, enable_servo=True, verbose=True, servo_speed=5)
    reader.start()
    
    try:
        print("\n[SENSOR] Starting servo tracking...\nX        Y        Pan      Motion")
        print("-" * 45)
        while True:
            sample = reader.get_latest()
            if sample:
                pan = sample.get('pan_angle', 0)
                x = sample['x']
                y = sample['y']
                motion = "✓" if sample['motion_detected'] else "✗"
                print(f"{x:6d}   {y:6d}   {pan:7.2f}°  {motion}")
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("\n\nStopping...")
        reader.stop()
        reader.join(timeout=2)
