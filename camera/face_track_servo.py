"""
Face/Hand tracking with Pan/Tilt Servo control.

Takes bounding boxes from screen and converts them to pan/tilt angles.
Smooths movements to avoid jittery servo motion.
"""

import time
import math
from collections import deque
from rpi_hardware_pwm import HardwarePWM


# --- Servo Configuration ---
MAX_ANGLE_LIMIT = 70
PAN_SERVO_CHANNEL = 0
TILT_SERVO_CHANNEL = 1
PWM_FREQUENCY = 50
CHIP = 0
PAN_NEUTRAL_ANGLE = 0
TILT_NEUTRAL_ANGLE = 50

# --- Tracking Configuration ---
SCREEN_WIDTH = 640
SCREEN_HEIGHT = 480
CENTER_X = SCREEN_WIDTH // 2
CENTER_Y = SCREEN_HEIGHT // 2

# Smoothing: number of detection updates to average (not frames)
SMOOTHING_WINDOW = 7

# Tracking deadzone: ignore small movements (pixels)
# Face must be this many pixels off-center before servo moves at all
DEADZONE_PAN = 50
DEADZONE_TILT = 70

# Max angle change per detection update (degrees)
MAX_ANGLE_DELTA = 5

# --- Calibration: Angle-to-Screen mapping ---
# How many degrees per pixel of screen movement
# Adjust these based on your servo FOV and camera
PAN_DEG_PER_PIXEL = 70.0 / (SCREEN_WIDTH // 2)    # degrees per pixel
TILT_DEG_PER_PIXEL = 70.0 / (SCREEN_HEIGHT // 2)   # degrees per pixel

# Center offset corrections
PAN_CENTER_OFFSET = PAN_NEUTRAL_ANGLE
TILT_CENTER_OFFSET = TILT_NEUTRAL_ANGLE


class FaceTrackServo:
    def __init__(self, verbose=False):
        """Initialize servo control for face tracking."""
        self.verbose = verbose
        self.pan_pwm = None
        self.tilt_pwm = None
        
        # Smoothing buffers
        self.pan_angle_buffer = deque(maxlen=SMOOTHING_WINDOW)
        self.tilt_angle_buffer = deque(maxlen=SMOOTHING_WINDOW)
        
        # Last command for delta limiting
        self.last_pan_angle = PAN_NEUTRAL_ANGLE
        self.last_tilt_angle = TILT_NEUTRAL_ANGLE
        
        self.initialized = False
    
    def initialize(self):
        """Initialize PWM hardware."""
        try:
            print("Initializing Hardware PWM for face tracking...")
            self.pan_pwm = HardwarePWM(pwm_channel=PAN_SERVO_CHANNEL, hz=PWM_FREQUENCY, chip=CHIP)
            self.tilt_pwm = HardwarePWM(pwm_channel=TILT_SERVO_CHANNEL, hz=PWM_FREQUENCY, chip=CHIP)
            
            # Start at the calibrated neutral position.
            self.pan_pwm.start(self.angle_to_duty_cycle(PAN_NEUTRAL_ANGLE))
            self.tilt_pwm.start(self.angle_to_duty_cycle(TILT_NEUTRAL_ANGLE))
            
            time.sleep(0.5)
            self.initialized = True
            print("Face tracking servos initialized.")
            return True
        except Exception as e:
            print(f"Error initializing servos: {e}")
            self.initialized = False
            return False
    
    def angle_to_duty_cycle(self, angle):
        """Convert angle (-MAX_ANGLE_LIMIT to +MAX_ANGLE_LIMIT) to PWM duty cycle %."""
        angle = max(-MAX_ANGLE_LIMIT, min(MAX_ANGLE_LIMIT, angle))
        pulse_ms = 1.5 + (angle / 80.0) * 0.9
        duty_cycle = (pulse_ms / 20.0) * 100
        return duty_cycle
    
    def bbox_to_angles(self, bbox):
        """
        Convert bounding box to pan/tilt correction angles.
        
        bbox: dict with keys:
            'x': left edge (pixels)
            'y': top edge (pixels)
            'width': bbox width (pixels)
            'height': bbox height (pixels)
        
        Returns: (pan_delta, tilt_delta) in degrees
        """
        if not bbox:
            return None, None
        
        # Get bounding box center
        bbox_center_x = bbox['x'] + bbox['width'] // 2
        bbox_center_y = bbox['y'] + bbox['height'] // 2
        
        # Calculate offset from screen center
        offset_x = bbox_center_x - CENTER_X
        offset_y = bbox_center_y - CENTER_Y
        
        # Apply separate deadzones for pan and tilt
        if abs(offset_x) < DEADZONE_PAN:
            offset_x = 0
        if abs(offset_y) < DEADZONE_TILT:
            offset_y = 0
        
        # Convert screen offset into servo corrections.
        # When the face is centered, both corrections become 0 and the
        # tracker holds the current pan/tilt angles instead of drifting
        # back toward the neutral mount position.
        pan_delta = -(offset_x * PAN_DEG_PER_PIXEL)
        tilt_delta = offset_y * TILT_DEG_PER_PIXEL

        return pan_delta, tilt_delta
    
    def smooth_angle(self, target_angle, buffer):
        """Apply exponential smoothing to servo angle."""
        if target_angle is None:
            return None
        
        buffer.append(target_angle)
        # Average the buffered values for smoothing
        smoothed = sum(buffer) / len(buffer)
        return smoothed
    
    def limit_angle_delta(self, target_angle, last_angle, max_delta):
        """Limit rate of angle change to prevent jitter."""
        if target_angle is None:
            return last_angle
        
        delta = target_angle - last_angle
        
        # Clamp delta to max allowed change
        if abs(delta) > max_delta:
            delta = max_delta if delta > 0 else -max_delta
        
        return last_angle + delta
    
    def track_face(self, bbox):
        """
        Update servo position to track face/object at given bounding box.
        
        Args:\n            bbox: dict with 'x', 'y', 'width', 'height' in pixels, or None to center
        
        Returns:
            (pan_angle, tilt_angle) actually commanded
        """
        if not self.initialized:
            return None, None
        
        # Get incremental corrections from the current face offset.
        pan_delta, tilt_delta = self.bbox_to_angles(bbox)

        if pan_delta is None:
            return None, None

        # When the face is already centered, stale smoothing history can keep
        # pushing the servo. Reset the buffers so the current angle is held.
        if pan_delta == 0:
            self.pan_angle_buffer.clear()
            self.pan_angle_buffer.append(self.last_pan_angle)
        if tilt_delta == 0:
            self.tilt_angle_buffer.clear()
            self.tilt_angle_buffer.append(self.last_tilt_angle)

        pan_target = self.last_pan_angle + pan_delta
        tilt_target = self.last_tilt_angle + tilt_delta

        pan_target = max(-MAX_ANGLE_LIMIT, min(MAX_ANGLE_LIMIT, pan_target))
        tilt_target = max(-MAX_ANGLE_LIMIT, min(MAX_ANGLE_LIMIT, tilt_target))
        
        # Smooth the angles
        pan_smooth = self.smooth_angle(pan_target, self.pan_angle_buffer)
        tilt_smooth = self.smooth_angle(tilt_target, self.tilt_angle_buffer)
        
        # Limit rate of change
        pan_cmd = self.limit_angle_delta(pan_smooth, self.last_pan_angle, MAX_ANGLE_DELTA)
        tilt_cmd = self.limit_angle_delta(tilt_smooth, self.last_tilt_angle, MAX_ANGLE_DELTA)
        
        # Hysteresis: only move servo if angle change exceeds threshold
        # 1.5° threshold prevents bbox jitter (2-4px noise) from driving the servo
        pan_change = abs(pan_cmd - self.last_pan_angle)
        tilt_change = abs(tilt_cmd - self.last_tilt_angle)
        
        if pan_change < 1.5:
            pan_cmd = self.last_pan_angle
        if tilt_change < 1.5:
            tilt_cmd = self.last_tilt_angle
        
        # Command servos
        self.pan_pwm.change_duty_cycle(self.angle_to_duty_cycle(pan_cmd))
        self.tilt_pwm.change_duty_cycle(self.angle_to_duty_cycle(tilt_cmd))
        
        # Update last commanded angles
        self.last_pan_angle = pan_cmd
        self.last_tilt_angle = tilt_cmd
        
        if self.verbose:
            print(f"Pan: {pan_cmd:6.2f}° | Tilt: {tilt_cmd:6.2f}°")
        
        return pan_cmd, tilt_cmd
    
    def move_pan_to_angle(self, angle):
        """
        Move pan motor to a specific angle.
        
        Args:
            angle: Target pan angle in degrees (-MAX_ANGLE_LIMIT to +MAX_ANGLE_LIMIT)
        
        Returns:
            The actual angle commanded to the servo
        """
        if not self.initialized:
            return None
        
        # Clamp angle to limits
        pan_cmd = max(-MAX_ANGLE_LIMIT, min(MAX_ANGLE_LIMIT, angle))
        
        # Command servo
        self.pan_pwm.change_duty_cycle(self.angle_to_duty_cycle(pan_cmd))
        
        # Update last commanded angle
        self.last_pan_angle = pan_cmd
        
        # Clear smoothing buffer to avoid stale history
        self.pan_angle_buffer.clear()
        self.pan_angle_buffer.append(pan_cmd)
        
        if self.verbose:
            print(f"Pan moved to: {pan_cmd:6.2f}°")
        
        return pan_cmd
    
    def move_pan_from_sensor(self, x, y, scale=1.0):
        """
        Move pan motor based on sensor X, Y coordinates.
        
        Calculates angle from atan2(x, y) and applies optional scaling.
        Useful for RD03D or similar presence sensors that output XY coords.
        
        Args:
            x: Sensor X coordinate (in sensor units)
            y: Sensor Y coordinate (in sensor units)
            scale: Scale factor to apply to the calculated angle (default: 1.0)
                   Use scale < 1.0 to reduce sensitivity, > 1.0 to increase
        
        Returns:
            The actual angle commanded to the servo
        """
        if not self.initialized or y == 0:
            return None
        
        # Calculate angle from sensor coordinates (same as RD03D sensor logic)
        angle = math.degrees(math.atan2(x, y)) * scale
        
        # Use the standard move method
        return self.move_pan_to_angle(angle)
    
    def center(self):
        """Return servos to the calibrated neutral position."""
        if self.initialized:
            self.pan_pwm.change_duty_cycle(self.angle_to_duty_cycle(PAN_NEUTRAL_ANGLE))
            self.tilt_pwm.change_duty_cycle(self.angle_to_duty_cycle(TILT_NEUTRAL_ANGLE))
            self.last_pan_angle = PAN_NEUTRAL_ANGLE
            self.last_tilt_angle = TILT_NEUTRAL_ANGLE
            self.pan_angle_buffer.clear()
            self.tilt_angle_buffer.clear()
            print(
                f"Servos centered at pan={PAN_NEUTRAL_ANGLE}°, "
                f"tilt={TILT_NEUTRAL_ANGLE}°."
            )
    
    def stop(self):
        """Stop and cleanup servos."""
        if self.initialized:
            try:
                self.pan_pwm.stop()
                self.tilt_pwm.stop()
                print("Face tracking servos stopped.")
            except Exception as e:
                print(f"Error stopping servos: {e}")
            self.initialized = False


# Singleton instance for easy access
_tracker = None

def get_tracker():
    """Get or create the singleton tracker instance."""
    global _tracker
    if _tracker is None:
        _tracker = FaceTrackServo()
    return _tracker


# Simple test function
if __name__ == "__main__":
    tracker = FaceTrackServo(verbose=True)
    
    if not tracker.initialize():
        print("Failed to initialize servos!")
        exit(1)
    
    try:
        print("\nTest 1: Face at screen center")
        # bbox = {'x': 280, 'y': 200, 'width': 80, 'height': 80}
        # tracker.track_face(bbox)
        # time.sleep(1)
        
        # print("\nTest 2: Face at top-right")
        # bbox = {'x': 450, 'y': 100, 'width': 80, 'height': 80}
        # for _ in range(5):
        #     tracker.track_face(bbox)
        #     time.sleep(0.1)
        
        # print("\nTest 3: Face at bottom-left")
        # bbox = {'x': 100, 'y': 350, 'width': 80, 'height': 80}
        # for _ in range(5):
        #     tracker.track_face(bbox)
        tracker.move_pan_to_angle(30)
        time.sleep(0.1)
        
        print("\nTest 4: Return to center")
        tracker.center()
        
    except KeyboardInterrupt:
        print("\nInterrupted.")
    finally:
        tracker.stop()
