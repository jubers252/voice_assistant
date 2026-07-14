# Face Tracking with Pan/Tilt Servo

This system integrates face/hand detection with real-time pan/tilt servo control to track detected faces on screen.

## Files

1. **face_track_servo.py** - Core servo control module
   - Converts bounding box coordinates to pan/tilt angles
   - Smooths servo movements to avoid jitter
   - Provides rate limiting for smooth tracking
   
2. **hand_detection_with_servo.py** - Face detection + servo tracking
   - Extended version of `hand_detection.py` with servo integration
   - Tracks faces in real-time and commands servos accordingly
   - Still detects hands and gestures as before

3. **test_servo.py** - Updated with tilt motor integration
   - Wave motion mode (synchronized pan/tilt)
   - Step motion mode (tilt up/down)

## How It Works

### Bounding Box → Servo Angle Conversion

```
Screen coordinates (0, 0) at top-left, (640, 480) at bottom-right
        ↓
Calculate offset from screen center (320, 240)
        ↓
Convert pixel offset to degrees based on calibration
        ↓
Apply smoothing filter (5-frame moving average)
        ↓
Limit angle change rate (max 3° per frame)
        ↓
Command servo with computed angle
```

### Configuration

Edit `face_track_servo.py` constants to adjust behavior:

```python
# Screen dimensions
SCREEN_WIDTH = 640
SCREEN_HEIGHT = 480

# Smoothing window (frames to average)
SMOOTHING_WINDOW = 5

# Dead zone (ignore small movements in pixels)
DEADZONE = 20

# Max angle change per update (degrees)
MAX_ANGLE_DELTA = 3

# Angle-to-screen mapping (degrees per pixel)
PAN_DEG_PER_PIXEL = 70.0 / (SCREEN_WIDTH // 2)
TILT_DEG_PER_PIXEL = 70.0 / (SCREEN_HEIGHT // 2)

# Center offset corrections
PAN_CENTER_OFFSET = 0.0
TILT_CENTER_OFFSET = 0.0
```

## Usage

### Option 1: Simple Face Tracking

```python
from face_track_servo import FaceTrackServo

tracker = FaceTrackServo(verbose=True)
tracker.initialize()

# Track a face at given screen position
bbox = {
    'x': 300,      # left edge (pixels)
    'y': 150,      # top edge (pixels)
    'width': 100,  # bounding box width
    'height': 120  # bounding box height
}

pan_angle, tilt_angle = tracker.track_face(bbox)

# Center servos when no face detected
tracker.center()

# Cleanup
tracker.stop()
```

### Option 2: Real-time Face Detection with Servo

```bash
python hand_detection_with_servo.py
```

This runs the full pipeline:
- Captures video stream
- Detects faces using MediaPipe
- Automatically tracks the first detected face with servos
- Still detects hand gestures
- Press 'q' to quit

### Option 3: Singleton Access

```python
from face_track_servo import get_tracker

# Get global tracker instance
tracker = get_tracker()
tracker.initialize()

bbox = {'x': 320, 'y': 240, 'width': 80, 'height': 80}
tracker.track_face(bbox)
```

## Calibration Tips

### If servo over-corrects:
- Reduce `MAX_ANGLE_DELTA` (slower movement)
- Increase `SMOOTHING_WINDOW` (more averaging)

### If servo under-corrects:
- Increase `MAX_ANGLE_DELTA`
- Reduce `SMOOTHING_WINDOW`

### If servo drifts from center:
- Adjust `PAN_CENTER_OFFSET` or `TILT_CENTER_OFFSET`
- Positive values rotate toward higher angles
- Negative values rotate toward lower angles

### If small movements trigger servo jitter:
- Increase `DEADZONE` (in pixels)

### For wide/narrow tracking range:
- Adjust `PAN_DEG_PER_PIXEL` and `TILT_DEG_PER_PIXEL`
- These define how many degrees per pixel of screen movement

## Hardware Setup

### PWM Channels
- Pan servo: PWM channel 0
- Tilt servo: PWM channel 1
- Both on 50Hz frequency

### Servo Angle Range
- Min: -70°
- Max: +70°
- Center: 0°

## Troubleshooting

**Servo not responding:**
- Check PWM channels and chip number
- Verify hardware PWM is available
- Test with `test_servo.py` first

**Servo moving too jerkily:**
- Increase `SMOOTHING_WINDOW`
- Reduce `MAX_ANGLE_DELTA`
- Increase `DEADZONE`

**Servo tracks behind face:**
- Reduce `SMOOTHING_WINDOW` for faster response
- Increase `MAX_ANGLE_DELTA`

**Face not being tracked:**
- Check face detection in `hand_detection_with_servo.py`
- Verify camera stream is working
- Check `min_detection_confidence` (default 0.6)

## Performance Notes

- Detection runs every N frames to save CPU (configurable)
- Servo updates run at camera FPS (~30 FPS)
- Hand detection is secondary and optional
- All operations run in main thread

## Future Enhancements

- [ ] PID controller for smoother tracking
- [ ] Support for multiple faces
- [ ] Hand tracking for secondary pan/tilt
- [ ] Gesture commands (follow hand, etc.)
- [ ] Servo position feedback
- [ ] Performance metrics logging
