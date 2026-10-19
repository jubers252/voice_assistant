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
        self.thread_alive = True
        self.last_sample_time = 0
        self.consecutive_errors = 0
        self.reconnect_delay = 1.0
        self.max_reconnect_attempts = 5
        # The radar sends nothing while it has no target, so silence is normal.
        self.idle_reconnect_seconds = 60.0
        
        # Servo stability controls
        self.angle_smoothing_buffer = []
        self.smoothing_window_size = 5  # Number of readings to average
        self.angle_deadzone = 2.0  # Ignore movements < 2 degrees
        self.last_servo_angle = 0.0
        
    def run(self):
        """Main sensor reading loop with automatic reconnection"""
        if not HAS_SERIAL:
            print("[SENSOR] Serial module not available")
            self.thread_alive = False
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
        
        self.running = True
        reconnect_attempts = 0
        
        while self.running:
            try:
                ser = serial.Serial(self.port, self.baudrate, timeout=1)
                print(f"[SENSOR] Connected to {self.port} at {self.baudrate} baud")
                reconnect_attempts = 0
                self.consecutive_errors = 0
                
                buffer = bytearray()
                ser.reset_input_buffer()
                last_data_at = time.time()
                
                while self.running:
                    try:
                        chunk = ser.read(max(ser.in_waiting, 1))
                        if chunk:
                            buffer.extend(chunk)
                            last_data_at = time.time()
                        elif time.time() - last_data_at > self.idle_reconnect_seconds:
                            print(f"[SENSOR] No serial data for {self.idle_reconnect_seconds:.0f}s, reconnecting...")
                            break
                        
                        # Resync on the frame header so one dropped byte can't
                        # misalign every following read.
                        start = buffer.find(b"\xAA\xFF")
                        if start < 0:
                            del buffer[:-1]
                            continue
                        if start > 0:
                            del buffer[:start]
                        if len(buffer) < 8:
                            continue
                        data = bytes(buffer[:8])
                        del buffer[:2]
                        if len(buffer) > 512:
                            del buffer[:-64]
                        
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
                            # Coordinates are in mm: y is forward depth, distance is straight-line.
                            "depth_m": abs(y) / 1000.0,
                            "distance_m": math.hypot(x, y) / 1000.0,
                            "motion_detected": True,
                            "timestamp": time.time()
                        }
                        
                        self.latest_sample = sample
                        self.last_sample_time = time.time()
                        self.consecutive_errors = 0
                        
                        # Control servo if enabled
                        if self.servo:
                            self._control_servo(pan_angle)
                        
                        # Try to add to queue (non-blocking)
                        try:
                            self.sample_queue.put_nowait(sample)
                        except:
                            pass
                        
                    except serial.SerialException as e:
                        self.consecutive_errors += 1
                        if self.verbose:
                            print(f"[SENSOR] Serial error (#{self.consecutive_errors}): {e}")
                        if self.consecutive_errors > 5:
                            print(f"[SENSOR] Too many serial errors, attempting reconnection...")
                            break
                    except Exception as e:
                        self.consecutive_errors += 1
                        if self.verbose:
                            print(f"[SENSOR] Read error (#{self.consecutive_errors}): {e}")
                        if self.consecutive_errors > 10:
                            print(f"[SENSOR] Too many errors, attempting reconnection...")
                            break
                
                try:
                    ser.close()
                except:
                    pass
                
            except FileNotFoundError:
                print(f"[SENSOR] Serial port {self.port} not found")
                reconnect_attempts += 1
            except serial.SerialException as e:
                print(f"[SENSOR] Serial connection error: {e}")
                reconnect_attempts += 1
            except Exception as e:
                print(f"[SENSOR] Unexpected error: {e}")
                reconnect_attempts += 1
            
            if self.running and reconnect_attempts < self.max_reconnect_attempts:
                if self.verbose:
                    print(f"[SENSOR] Reconnecting in {self.reconnect_delay:.1f}s (attempt {reconnect_attempts}/{self.max_reconnect_attempts})...")
                time.sleep(self.reconnect_delay)
            elif reconnect_attempts >= self.max_reconnect_attempts:
                print(f"[SENSOR] Max reconnection attempts ({self.max_reconnect_attempts}) reached, stopping reader")
                break
        
        self.running = False
        self.thread_alive = False
        if self.servo:
            self.servo = None
        print("[SENSOR] Reader thread stopped")

    
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
    
    def is_healthy(self, timeout=5.0):
        """
        Check if sensor reader is still providing fresh data.
        
        Args:
            timeout: Maximum seconds since last sample (default 5.0)
        
        Returns:
            True if thread is alive and has recent data, False otherwise
        """
        now = time.time()
        
        # Check if thread has stopped
        if not self.thread_alive or not self.running:
            return False
        
        # Check if data is fresh
        if self.latest_sample is None:
            return False
        
        time_since_sample = now - self.latest_sample.get("timestamp", 0)
        if time_since_sample > timeout:
            return False
        
        return True
    
    def get_diagnostics(self):
        """Get sensor health diagnostics"""
        now = time.time()
        time_since_sample = (
            now - self.latest_sample.get("timestamp", 0)
            if self.latest_sample
            else float('inf')
        )
        
        return {
            "thread_alive": self.thread_alive,
            "running": self.running,
            "is_healthy": self.is_healthy(),
            "consecutive_errors": self.consecutive_errors,
            "latest_sample": self.latest_sample,
            "time_since_sample": time_since_sample,
            "has_latest_sample": self.latest_sample is not None,
        }
    
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
        while True:
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("\n\nStopping...")
        reader.stop()
        reader.join(timeout=2)
