"""
Dual Sensor 230° Coverage - Two sensors at ±55° with combined servo tracking
Combines output from left and right sensors to achieve 230-degree coverage
"""

import threading
import struct
import math
import time
from queue import Queue, Full
from typing import Optional, Dict

try:
    import serial
    HAS_SERIAL = True
except ImportError:
    HAS_SERIAL = False
    print("Warning: pyserial not available")


from face_track_servo import FaceTrackServo
HAS_SERVO = True

class DualSensorReader(threading.Thread):
    """Read person tracking data from serial sensor"""
    
    def __init__(self, port="/dev/ttyAMA0", baudrate=256000, daemon=False, 
                 verbose=False, angle_offset=0, sensor_label=""):
        """
        Initialize sensor reader thread.
        
        Args:
            port: Serial port device
            baudrate: Serial communication speed
            daemon: Whether to run as daemon thread
            verbose: Enable debug output
            angle_offset: Mounting angle offset from center (-55 or +55 degrees)
            sensor_label: Label for this sensor (e.g., "LEFT", "RIGHT")
        """
        super().__init__(daemon=daemon)
        self.port = port
        self.baudrate = baudrate
        self.running = False
        self.latest_sample = None
        self.sample_queue = Queue(maxsize=5)
        self.verbose = verbose
        self.angle_offset = angle_offset
        self.sensor_label = sensor_label
        self.thread_alive = True
        self.consecutive_errors = 0
        self.reconnect_delay = 1.0
        self.max_reconnect_attempts = 5
        
    def run(self):
        """Main sensor reading loop with automatic reconnection"""
        if not HAS_SERIAL:
            print(f"[{self.sensor_label}] Serial module not available")
            self.thread_alive = False
            return
        
        self.running = True
        reconnect_attempts = 0
        
        while self.running:
            try:
                ser = serial.Serial(self.port, self.baudrate, timeout=1)
                print(f"[{self.sensor_label}] Connected to {self.port} at {self.baudrate} baud")
                reconnect_attempts = 0
                self.consecutive_errors = 0
                
                buffer = bytearray()
                ser.reset_input_buffer()
                
                while self.running:
                    try:
                        chunk = ser.read(max(ser.in_waiting, 1))
                        if chunk:
                            buffer.extend(chunk)
                        
                        # Resync on frame header
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
                        
                        # Calculate pan angle in sensor's local frame (-70° to +70°)
                        pan_angle = math.degrees(math.atan2(x, y))
                        
                        sample = {
                            "x": x,
                            "y": y,
                            "pan_angle": pan_angle,  # Local angle in sensor frame
                            "depth_m": abs(y) / 1000.0,
                            "distance_m": math.hypot(x, y) / 1000.0,
                            "motion_detected": True,
                            "timestamp": time.time()
                        }
                        
                        self.latest_sample = sample
                        self.consecutive_errors = 0
                        
                        try:
                            self.sample_queue.put_nowait(sample)
                        except Full:
                            pass
                        
                    except serial.SerialException as e:
                        self.consecutive_errors += 1
                        if self.verbose:
                            print(f"[{self.sensor_label}] Serial error: {e}")
                        if self.consecutive_errors > 5:
                            break
                    except Exception as e:
                        self.consecutive_errors += 1
                        if self.verbose:
                            print(f"[{self.sensor_label}] Read error: {e}")
                        if self.consecutive_errors > 10:
                            break
                
                try:
                    ser.close()
                except:
                    pass
                
            except FileNotFoundError:
                print(f"[{self.sensor_label}] Port {self.port} not found")
                reconnect_attempts += 1
            except serial.SerialException as e:
                print(f"[{self.sensor_label}] Connection error: {e}")
                reconnect_attempts += 1
            except Exception as e:
                print(f"[{self.sensor_label}] Unexpected error: {e}")
                reconnect_attempts += 1
            
            if self.running and reconnect_attempts < self.max_reconnect_attempts:
                if self.verbose:
                    print(f"[{self.sensor_label}] Reconnecting in {self.reconnect_delay}s...")
                time.sleep(self.reconnect_delay)
            elif reconnect_attempts >= self.max_reconnect_attempts:
                print(f"[{self.sensor_label}] Max reconnection attempts reached")
                break
        
        self.running = False
        self.thread_alive = False
        print(f"[{self.sensor_label}] Reader stopped")
    
    @staticmethod
    def _decode_coord(raw):
        """Decode signed coordinate from sensor"""
        return raw - 0x8000 if raw >= 0x8000 else -raw
    
    def get_latest(self):
        """Get latest sensor sample"""
        return self.latest_sample
    
    def is_healthy(self, timeout=5.0):
        """Check if sensor is providing fresh data"""
        now = time.time()
        
        if not self.thread_alive or not self.running:
            return False
        
        if self.latest_sample is None:
            return False
        
        time_since_sample = now - self.latest_sample.get("timestamp", 0)
        return time_since_sample <= timeout
    
    def stop(self):
        """Stop the sensor reader"""
        self.running = False


class DualSensor230Degree:
    """
    Combines two sensors at ±55° to achieve 230° coverage
    
    Sensor Layout (top-down):
    
           -70°           0°          +70°
            |             |            |
            ↓             ↓            ↓
    
    LEFT SENSOR (-55°)    CENTER    RIGHT SENSOR (+55°)
    at -125° to +15°      SERVO     at -15° to +125°
            \\             |            //
             \\            |           //
              \\           |          //
               \\          ↓         //     <- Servo rotates to track
                \\        SERVO      //
                 \\______(  )_______//
                        / \
                       /   \
                      /TARGET\
                     /__AREA__\
    
    Coverage: -125° to +125° = 250° (some overlap in center)
    Effective tracking: ±115° with servo assistance
    """
    
    def __init__(self, left_port="/dev/ttyAMA0", right_port="/dev/ttyAMA1", 
                 enable_servo=True, verbose=False):
        """
        Initialize dual sensor fusion.
        
        Args:
            left_port: Serial port for left sensor (at -55°)
            right_port: Serial port for right sensor (at +55°)
            enable_servo: Enable servo tracking
            verbose: Debug output
        """
        self.enable_servo = enable_servo and HAS_SERVO
        self.verbose = verbose
        if enable_servo and not HAS_SERVO:
            print("[DUAL-SENSOR] Servo tracking requested but FaceTrackServo "
                  "could not be imported")
        
        # Create two sensor readers
        self.left_sensor = DualSensorReader(
            port=left_port,
            baudrate=256000,
            daemon=True,
            verbose=verbose,
            angle_offset=+55,
            sensor_label="LEFT+60°"
        )
        
        self.right_sensor = DualSensorReader(
            port=right_port,
            baudrate=256000,
            daemon=True,
            verbose=verbose,
            angle_offset=-55,
            sensor_label="RIGHT-60°"
        )
        
        self.servo = None
        self.combined_sample = None
        self.sample_queue = Queue(maxsize=10)
        self.running = False
        self.fusion_thread = None
        self._primary_sensor = None
        
        print(f"[DUAL-SENSOR] Initializing dual sensor 230° coverage")
        print(f"  Left sensor ({self.left_sensor.angle_offset:+.0f}°):  {left_port}")
        print(f"  Right sensor ({self.right_sensor.angle_offset:+.0f}°): {right_port}")
    
    def start(self):
        """Start both sensor readers and fusion"""
        if self.running:
            print("[DUAL-SENSOR] Already running")
            return
        
        self.running = True
        
        # Initialize servo if enabled
        if self.enable_servo:
            print("[DUAL-SENSOR] Initializing servo...")
            self.servo = FaceTrackServo(verbose=self.verbose)
            if not self.servo.initialize():
                print("[DUAL-SENSOR] Failed to initialize servo, continuing without servo")
                self.servo = None
            else:
                print("[DUAL-SENSOR] ✓ Servo initialized")
        
        # Start sensor readers
        self.left_sensor.start()
        self.right_sensor.start()
        print("[DUAL-SENSOR] ✓ Sensors started")
        
        # Start fusion thread
        self.fusion_thread = threading.Thread(target=self._fusion_loop, daemon=True)
        self.fusion_thread.start()
        print("[DUAL-SENSOR] ✓ Sensor fusion started")
    
    def _fusion_loop(self):
        """Main loop that combines data from both sensors"""
        last_left_timestamp = 0
        last_right_timestamp = 0
        
        while self.running:
            try:
                # Get latest samples
                left_sample = self.left_sensor.get_latest()
                right_sample = self.right_sensor.get_latest()
                
                # Check if data is ACTUALLY UPDATING (not stale cache)
                left_updated = (left_sample and 
                               left_sample.get('timestamp', 0) > last_left_timestamp)
                right_updated = (right_sample and 
                                right_sample.get('timestamp', 0) > last_right_timestamp)
                
                # Update timestamps only if data changed
                if left_updated:
                    last_left_timestamp = left_sample['timestamp']
                if right_updated:
                    last_right_timestamp = right_sample['timestamp']
                
                # Compare both recent detections whenever either sensor updates.
                # Passing only the just-updated sensor made the chosen target
                # alternate between sensors on successive serial frames.
                now = time.time()
                left_fresh = bool(left_sample and now - left_sample.get('timestamp', 0) <= 0.75)
                right_fresh = bool(right_sample and now - right_sample.get('timestamp', 0) <= 0.75)
                if not left_updated and not right_updated:
                    time.sleep(0.1)
                    continue
                
                # Fuse the samples (only freshly updated data)
                fused = self._fuse_samples(
                    left_sample if left_fresh else None,
                    right_sample if right_fresh else None
                )
                
                if fused:
                    # Convert the selected/fused polar detection into one room
                    # coordinate. Angles use atan2(x, y): 0° is straight ahead,
                    # positive x is to the right. This assumes both sensors
                    # share an origin; add sensor mounting translations if they
                    # are physically separated by a meaningful distance.
                    angle_rad = math.radians(fused['absolute_pan_angle'])
                    fused['x_m'] = fused['distance_m'] * math.sin(angle_rad)
                    fused['y_m'] = fused['distance_m'] * math.cos(angle_rad)
                    fused['coordinate_m'] = {
                        'x': fused['x_m'],
                        'y': fused['y_m'],
                    }
                    self.combined_sample = fused
                    
                    abs_angle = fused['absolute_pan_angle']
                    
                    # Control servo with fused angle
                    if self.servo:
                        self._control_servo(abs_angle)
                    
                    try:
                        self.sample_queue.put_nowait(fused)
                    except Full:
                        pass
                
                time.sleep(0.05)  # 20Hz fusion rate
                
            except Exception as e:
                print(f"[DUAL-SENSOR] Fusion error: {e}")
                if self.verbose:
                    import traceback
                    traceback.print_exc()
                time.sleep(0.1)
    
    def _fuse_samples(self, left_sample: Optional[Dict],
                      right_sample: Optional[Dict]) -> Optional[Dict]:
        """Select one radar at a time and hand off near the local ±50° edge."""
        # Use each radar's central 120° field and calibrated camera offset.
        if left_sample and abs(left_sample.get('pan_angle', 999)) > 60:
            left_sample = None
        if right_sample and abs(right_sample.get('pan_angle', 999)) > 60:
            right_sample = None

        candidates = {}
        if left_sample:
            candidates['LEFT'] = left_sample
        if right_sample:
            candidates['RIGHT'] = right_sample
        if not candidates:
            return None

        # Start with the sensor whose target is nearer its local center. This
        # makes RIGHT (+10°) win over LEFT (-55°) in the example from the user.
        if self._primary_sensor not in candidates:
            self._primary_sensor = min(
                candidates, key=lambda name: abs(candidates[name]['pan_angle'])
            )
        else:
            other_name = 'RIGHT' if self._primary_sensor == 'LEFT' else 'LEFT'
            active_sample = candidates[self._primary_sensor]
            other_sample = candidates.get(other_name)

            # Hand off only when the active sensor approaches its ±50° edge
            # and the other sensor has a fresh reading back inside that edge.
            if (other_sample
                    and abs(active_sample['pan_angle']) >= 50
                    and abs(other_sample['pan_angle']) < 50):
                self._primary_sensor = other_name

        selected = candidates.get(self._primary_sensor)
        if selected is None:
            # Active sensor lost its target; use the remaining live sensor.
            self._primary_sensor = next(iter(candidates))
            selected = candidates[self._primary_sensor]

        if self._primary_sensor == 'LEFT':
            absolute_angle = self.left_sensor.angle_offset + selected['pan_angle']
        else:
            absolute_angle = self.right_sensor.angle_offset + selected['pan_angle']

        return {
            'distance_m': selected['distance_m'],
            'depth_m': selected['depth_m'],
            'absolute_pan_angle': absolute_angle,
            'left_angle': (
                self.left_sensor.angle_offset + left_sample['pan_angle']
                if left_sample else None
            ),
            'right_angle': (
                self.right_sensor.angle_offset + right_sample['pan_angle']
                if right_sample else None
            ),
            'source': f'TRACKING: {self._primary_sensor} sensor',
            'confidence': 90.0,
            'motion_detected': True,
            'timestamp': selected['timestamp'],
        }
    
    def _control_servo(self, absolute_pan_angle):
        """Track the fused radar bearing in the installed servo's frame."""
        if not self.servo:
            return
        
        try:
            # The installed camera/servo uses the same sign as the calibrated
            # radar frame: negative bearings are left, positive are right.
            servo_target = absolute_pan_angle
            commanded_angle = self.servo.move_pan_to_angle(servo_target)
            if self.verbose:
                print(f"[SERVO] Radar bearing {absolute_pan_angle:+.1f}° -> "
                      f"servo target {servo_target:+.1f}° -> "
                      f"pan {commanded_angle:+.1f}° (limit ±90°)")
                
        except Exception as e:
            print(f"[DUAL-SENSOR] Servo error: {e}")
    
    def get_latest(self) -> Optional[Dict]:
        """Get latest fused sample"""
        return self.combined_sample

    def get_presence_samples(self):
        """Return each sensor's latest reading for independent presence checks."""
        return [
            sample
            for sample in (
                self.left_sensor.get_latest(),
                self.right_sensor.get_latest(),
            )
            if sample is not None
        ]
    
    def get_sensor_status(self) -> Dict:
        """Get health status of both sensors"""
        return {
            'running': self.running,
            'coverage_degrees': 230,
            'left_sensor': {
                'label': 'LEFT+60°',
                'port': self.left_sensor.port,
                'angle_offset': self.left_sensor.angle_offset,
                'healthy': self.left_sensor.is_healthy(),
                'distance': self.left_sensor.latest_sample.get('distance_m') 
                           if self.left_sensor.latest_sample else None,
            },
            'right_sensor': {
                'label': 'RIGHT-60°',
                'port': self.right_sensor.port,
                'angle_offset': self.right_sensor.angle_offset,
                'healthy': self.right_sensor.is_healthy(),
                'distance': self.right_sensor.latest_sample.get('distance_m')
                           if self.right_sensor.latest_sample else None,
            },
            'servo_enabled': self.servo is not None,
        }
    
    def stop(self):
        """Stop all readers and fusion"""
        self.running = False
        self.left_sensor.stop()
        self.right_sensor.stop()
        if self.fusion_thread:
            self.fusion_thread.join(timeout=2)
        if self.servo:
            self.servo = None
        print("[DUAL-SENSOR] All stopped")


# Example usage
if __name__ == "__main__":
    """
    230° Coverage with Two Sensors at ±55°
    
    Each sensor: ±70° FOV = 140° total per sensor
    
    Configuration:
    - Left sensor at -55°: sees from -125° to +15°
    - Right sensor at +55°: sees from -15° to +125°
    - Combined: 250° coverage with center overlap
    - With servo assist: can track ±115° continuously
    """
    
    fusion = DualSensor230Degree(
        left_port='/dev/ttyAMA0',     # Change to your left sensor port
        right_port='/dev/ttyAMA1',    # Change to your right sensor port
        enable_servo=True,
        verbose=True
    )
    
    try:
        fusion.start()
        
        while True:
            time.sleep(1)
            
            # Print status
            status = fusion.get_sensor_status()
            print(f"\n[STATUS] 230° Coverage Tracking")
            print(f"  Left ({status['left_sensor']['angle_offset']:+.0f}°):  "
                  f"{'✓' if status['left_sensor']['healthy'] else '✗'} "
                  f"{status['left_sensor']['distance']:.2f}m" 
                  if status['left_sensor']['distance'] else f"{'✗'} no data")
            print(f"  Right ({status['right_sensor']['angle_offset']:+.0f}°): "
                  f"{'✓' if status['right_sensor']['healthy'] else '✗'} "
                  f"{status['right_sensor']['distance']:.2f}m"
                  if status['right_sensor']['distance'] else f"{'✗'} no data")
            print(f"  Servo: {'✓ Enabled' if status['servo_enabled'] else '✗ Disabled'}")
            
            # Print fused result
            fused = fusion.get_latest()
            if fused:
                print(f"\n[TARGET] Angle: {fused['absolute_pan_angle']:+7.1f}° | "
                      f"Distance: {fused['distance_m']:.2f}m | "
                      f"Confidence: {fused['confidence']:.0f}%")
    
    except KeyboardInterrupt:
        print("\n\nStopping...")
        fusion.stop()
