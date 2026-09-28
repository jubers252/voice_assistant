"""Pan/tilt servo control for face tracking."""

import math
import time
from collections import deque

from rpi_hardware_pwm import HardwarePWM


PAN_MIN_ANGLE = -90
PAN_MAX_ANGLE = 90
TILT_MIN_ANGLE = 0
TILT_MAX_ANGLE = 90
# Kept as an alias for the older backup tracker.
MAX_ANGLE_LIMIT = PAN_MAX_ANGLE
PAN_SERVO_CHANNEL = 0
TILT_SERVO_CHANNEL = 1
PWM_FREQUENCY = 50
CHIP = 0
PAN_NEUTRAL_ANGLE = 0
TILT_NEUTRAL_ANGLE = 50

SCREEN_WIDTH = 640
SCREEN_HEIGHT = 480
SMOOTHING_WINDOW = 3
DEADZONE_PAN = 60
DEADZONE_TILT = 80
MAX_ANGLE_DELTA = 2
MIN_ANGLE_CHANGE = 0.6
TRACKING_GAIN = 0.20
PAN_DEG_PER_PIXEL = PAN_MAX_ANGLE / (SCREEN_WIDTH // 2)
TILT_DEG_PER_PIXEL = TILT_MAX_ANGLE / (SCREEN_HEIGHT // 2)


def _clamp(angle, minimum, maximum):
    return max(minimum, min(maximum, float(angle)))


class FaceTrackServo:
    """Convert face positions or sensor readings into smoothed servo motion."""

    def __init__(self, verbose=False):
        self.verbose = verbose
        self.pan_pwm = None
        self.tilt_pwm = None
        self.pan_angle_buffer = deque(maxlen=SMOOTHING_WINDOW)
        self.tilt_angle_buffer = deque(maxlen=SMOOTHING_WINDOW)
        self.last_pan_angle = PAN_NEUTRAL_ANGLE
        self.last_tilt_angle = TILT_NEUTRAL_ANGLE
        self.initialized = False

    @staticmethod
    def angle_to_duty_cycle(angle):
        # A 180-degree pan servo maps -90..90 onto its 0.6..2.4 ms pulse range.
        angle = _clamp(angle, PAN_MIN_ANGLE, PAN_MAX_ANGLE)
        pulse_ms = 1.5 + (angle / 90.0) * 0.9
        return pulse_ms / 20.0 * 100

    def initialize(self):
        try:
            print("Initializing hardware PWM for face tracking...")
            self.pan_pwm = HardwarePWM(
                pwm_channel=PAN_SERVO_CHANNEL, hz=PWM_FREQUENCY, chip=CHIP
            )
            self.tilt_pwm = HardwarePWM(
                pwm_channel=TILT_SERVO_CHANNEL, hz=PWM_FREQUENCY, chip=CHIP
            )
            self.pan_pwm.start(self.angle_to_duty_cycle(PAN_NEUTRAL_ANGLE))
            self.tilt_pwm.start(self.angle_to_duty_cycle(TILT_NEUTRAL_ANGLE))
            time.sleep(0.5)
            self.initialized = True
            print("Face tracking servos initialized.")
            return True
        except Exception as error:
            print(f"Error initializing servos: {error}")
            self.initialized = False
            return False

    @staticmethod
    def bbox_to_angles(bbox):
        """Return pan and tilt corrections for a pixel bounding box."""
        if not bbox:
            return None, None

        center_x = bbox["x"] + bbox["width"] // 2
        center_y = bbox["y"] + bbox["height"] // 2
        offset_x = center_x - SCREEN_WIDTH // 2
        offset_y = center_y - SCREEN_HEIGHT // 2
        if abs(offset_x) < DEADZONE_PAN:
            offset_x = 0
        if abs(offset_y) < DEADZONE_TILT:
            offset_y = 0
        return -offset_x * PAN_DEG_PER_PIXEL, offset_y * TILT_DEG_PER_PIXEL

    @staticmethod
    def _step_toward(target, current):
        difference = target - current
        if abs(difference) < MIN_ANGLE_CHANGE:
            return current
        return current + max(-MAX_ANGLE_DELTA, min(MAX_ANGLE_DELTA, difference))

    def _move_axis(self, axis, angle, smooth=False):
        if not self.initialized:
            return None

        is_pan = axis == "pan"
        attr = "last_pan_angle" if is_pan else "last_tilt_angle"
        buffer = self.pan_angle_buffer if is_pan else self.tilt_angle_buffer
        pwm = self.pan_pwm if is_pan else self.tilt_pwm
        current = getattr(self, attr)
        minimum, maximum = (
            (PAN_MIN_ANGLE, PAN_MAX_ANGLE)
            if is_pan else (TILT_MIN_ANGLE, TILT_MAX_ANGLE)
        )
        target = _clamp(angle, minimum, maximum)

        if smooth:
            buffer.append(target)
            target = sum(buffer) / len(buffer)
            target = _clamp(
                self._step_toward(target, current), minimum, maximum
            )
        else:
            buffer.clear()
            buffer.append(target)

        if target != current:
            pwm.change_duty_cycle(self.angle_to_duty_cycle(target))
            setattr(self, attr, target)
            if self.verbose:
                print(f"{axis.title()}: {target:6.2f}°")
        return getattr(self, attr)

    def track_face(self, bbox, track_pan=True):
        """Track a face; callers can disable pan when another sensor owns it."""
        if not self.initialized:
            return None, None
        pan_delta, tilt_delta = self.bbox_to_angles(bbox)
        if pan_delta is None:
            return None, None

        pan = self.last_pan_angle
        if track_pan:
            pan = self._move_axis(
                "pan", self.last_pan_angle + pan_delta * TRACKING_GAIN, smooth=True
            )
        tilt = self._move_axis(
            "tilt", self.last_tilt_angle + tilt_delta * TRACKING_GAIN, smooth=True
        )
        return pan, tilt

    def move_pan_to_angle(self, angle):
        return self._move_axis("pan", angle)

    def move_tilt_to_angle(self, angle):
        return self._move_axis("tilt", angle)

    def move_pan_from_sensor(self, x, y, scale=1.0):
        if y == 0:
            return None
        return self.move_pan_to_angle(math.degrees(math.atan2(x, y)) * scale)

    def center(self):
        if not self.initialized:
            return
        self.move_pan_to_angle(PAN_NEUTRAL_ANGLE)
        self.move_tilt_to_angle(TILT_NEUTRAL_ANGLE)
        print(f"Servos centered at pan={PAN_NEUTRAL_ANGLE}°, tilt={TILT_NEUTRAL_ANGLE}°.")

    def stop(self):
        if not self.initialized:
            return
        try:
            self.pan_pwm.stop()
            self.tilt_pwm.stop()
            print("Face tracking servos stopped.")
        except Exception as error:
            print(f"Error stopping servos: {error}")
        finally:
            self.initialized = False


_tracker = None


def get_tracker():
    """Return the module's shared tracker instance."""
    global _tracker
    if _tracker is None:
        _tracker = FaceTrackServo()
    return _tracker


if __name__ == "__main__":
    tracker = FaceTrackServo(verbose=True)
    if not tracker.initialize():
        raise SystemExit(1)
    try:
        tracker.move_pan_to_angle(30)
        time.sleep(0.1)
        tracker.center()
    except KeyboardInterrupt:
        pass
    finally:
        tracker.stop()
