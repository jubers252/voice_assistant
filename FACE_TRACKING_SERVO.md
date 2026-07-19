# Face Tracking with Pan/Tilt Servo

This setup uses MediaPipe face detection plus hardware PWM pan/tilt control to keep the first detected face near the center of a 640x480 frame.

## Relevant Files

1. **face_track_servo.py**
   - Converts a detected face bounding box into pan and tilt corrections
   - Applies smoothing, rate limiting, and small-angle hysteresis
   - Exposes `initialize()`, `track_face()`, `center()`, and `stop()`

2. **hand_detection_with_servo.py**
   - Starts the camera stream and runs the MediaPipe detection loop
   - Tracks the first detected face when servo tracking is enabled
   - Re-centers the servos when no face is detected
   - Keeps hand detection optional and disabled by default

3. **test_servo.py**
   - Simple pan/tilt hardware motion test
   - Useful for confirming PWM wiring and basic servo movement before using tracking

## Current Tracking Behavior

The active control flow in `face_track_servo.py` is:

```text
bounding box
  -> compute face center
  -> compare against frame center (320, 240)
  -> apply separate deadzones for pan and tilt
  -> convert pixel offset to angle delta
  -> add delta to the last commanded servo angle
  -> smooth using a 7-sample moving average
  -> clamp per-update movement to 5 degrees
  -> ignore changes smaller than 1.5 degrees
  -> send PWM duty cycle update
```

Important detail: when the face is already within the deadzone, the tracker holds the current angle. It does not slowly drift back to neutral unless `center()` is called explicitly.

## Servo Configuration

These are the current values in `face_track_servo.py`:

```python
MAX_ANGLE_LIMIT = 70
PAN_SERVO_CHANNEL = 0
TILT_SERVO_CHANNEL = 1
PWM_FREQUENCY = 50
CHIP = 0

PAN_NEUTRAL_ANGLE = 0
TILT_NEUTRAL_ANGLE = 50

SCREEN_WIDTH = 640
SCREEN_HEIGHT = 480

SMOOTHING_WINDOW = 7
DEADZONE_PAN = 50
DEADZONE_TILT = 70
MAX_ANGLE_DELTA = 5

PAN_DEG_PER_PIXEL = 70.0 / (SCREEN_WIDTH // 2)
TILT_DEG_PER_PIXEL = 70.0 / (SCREEN_HEIGHT // 2)
```

Notes:

- Tilt neutral is intentionally offset to `50`, so the mounted camera points correctly at rest.
- Pan and tilt use separate deadzones because vertical jitter is usually worse than horizontal jitter.
- Angle commands are clamped to `-70` to `+70` before converting to PWM duty cycle.

## Basic Usage

```python
from face_track_servo import FaceTrackServo

tracker = FaceTrackServo(verbose=True)

if tracker.initialize():
        bbox = {
                'x': 300,
                'y': 150,
                'width': 100,
                'height': 120,
        }

        pan_angle, tilt_angle = tracker.track_face(bbox)

        # Explicitly return to neutral mount position when needed.
        tracker.center()
        tracker.stop()
```

`track_face()` expects a dictionary with `x`, `y`, `width`, and `height` in pixels. If the tracker is not initialized, it returns `(None, None)`.

## Integrated Detection Mode

Run the full detector plus servo pipeline with:

```bash
python hand_detection_with_servo.py
```

Current runtime behavior:

- The camera stream is started with `rpicam-vid` at 640x480 and 30 FPS.
- Face detection runs every 2 frames.
- MediaPipe face detection uses `min_detection_confidence=0.6`.
- The first detected face is passed to `FaceTrackServo.track_face()`.
- If no face is detected on a detection cycle, `servo_tracker.center()` is called.
- Hand detection support exists, but `DETECT_HANDS` is currently `False` by default.

## Singleton Access

```python
from face_track_servo import get_tracker

tracker = get_tracker()

if tracker.initialize():
        tracker.track_face({'x': 320, 'y': 240, 'width': 80, 'height': 80})
```

## Calibration Guidance

If tracking is too aggressive:

- Reduce `MAX_ANGLE_DELTA`
- Increase `SMOOTHING_WINDOW`
- Increase `DEADZONE_PAN` or `DEADZONE_TILT`

If tracking reacts too slowly:

- Increase `MAX_ANGLE_DELTA`
- Reduce `SMOOTHING_WINDOW`
- Reduce the deadzone values carefully

If the camera points too high or too low at rest:

- Adjust `TILT_NEUTRAL_ANGLE`

If left/right centering is off at rest:

- Adjust `PAN_NEUTRAL_ANGLE`

If the tracker moves in the wrong direction:

- Re-check servo mounting orientation
- If needed, invert the sign in `pan_delta` or `tilt_delta`

## Hardware Notes

- Pan servo uses PWM channel `0`
- Tilt servo uses PWM channel `1`
- PWM runs at `50 Hz`
- PWM chip is `0`
- The module depends on `rpi_hardware_pwm`

The current duty cycle mapping is based on:

```python
pulse_ms = 1.5 + (angle / 80.0) * 0.9
duty_cycle = (pulse_ms / 20.0) * 100
```

## Troubleshooting

**Servo does not move**

- Check that hardware PWM is available on the Raspberry Pi
- Verify the configured PWM channels match your wiring
- Run `python test_servo.py` first to validate the hardware path

**Servo jitters while the face is almost centered**

- Increase `DEADZONE_PAN` or `DEADZONE_TILT`
- Increase `SMOOTHING_WINDOW`
- Increase the 1.5 degree hysteresis threshold in `track_face()` if needed

**Tracker keeps lagging behind the face**

- Reduce `SMOOTHING_WINDOW`
- Increase `MAX_ANGLE_DELTA`
- Lower `DETECT_EVERY_N_FRAMES` in `hand_detection_with_servo.py`

**Tracker always returns to center**

- That is expected in `hand_detection_with_servo.py` when no face is detected
- If you want the last angle to be held instead, remove or change the `servo_tracker.center()` call in the no-face branch

**Face boxes appear but the servo does nothing**

- Confirm `ENABLE_SERVO_TRACKING = True`
- Check whether `FaceTrackServo.initialize()` prints a hardware PWM error
- Verify the bounding boxes are reaching `track_face()`
