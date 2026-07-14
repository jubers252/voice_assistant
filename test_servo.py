import time
import math
from rpi_hardware_pwm import HardwarePWM

# --- Configuration Constants ---
MAX_ANGLE_LIMIT = 70        # Pan sweep limit
MAX_TILT_ANGLE_LIMIT = 70   # Tilt max limit
SWEEP_SPEED = 1.5           # Higher = faster oscillation, Lower = slower, smoother wave

# Tilt downward bias
# Interpreting "go down by 45 degree" as a downward shift of the commanded tilt angle.
TILT_DOWN_DELTA_DEG = 60

# --- Pan Calibration ---
# If servo goes more to RIGHT than LEFT:
# - reduce PAN_RIGHT_SCALE (<1.0), or
# - increase PAN_LEFT_SCALE (>1.0), or both.
PAN_CENTER_OFFSET_DEG = 0.0
PAN_LEFT_SCALE = 0.90
PAN_RIGHT_SCALE = 0.90

# --- Tilt Step Motion (from tilt_45.py) ---
CENTER_ANGLE = 10
DOWN_ANGLE = 90
STEP_DEG = 1
STEP_DELAY = 0.02

def angle_to_duty_cycle(angle):
    """
    Maps an angle from -MAX_ANGLE_LIMIT to +MAX_ANGLE_LIMIT to a 50Hz hardware PWM duty cycle %.
    Uses a tailored pulse range (0.6ms to 2.4ms).
    """
    angle = max(-MAX_ANGLE_LIMIT, min(MAX_ANGLE_LIMIT, angle))
    pulse_ms = 1.5 + (angle / 80.0) * 0.9
    duty_cycle = (pulse_ms / 20.0) * 100
    return duty_cycle


def move_to_angle(tilt_pwm: HardwarePWM, angle: float):
    """Move tilt servo to specified angle."""
    tilt_pwm.change_duty_cycle(angle_to_duty_cycle(angle))


try:
    print("Initializing Hardware PWM Channels...")
    pan_pwm = HardwarePWM(pwm_channel=0, hz=50, chip=0)
    tilt_pwm = HardwarePWM(pwm_channel=1, hz=50, chip=0)
    
    # Start at center position
    pan_pwm.start(angle_to_duty_cycle(0))
    tilt_pwm.start(angle_to_duty_cycle(0))
    time.sleep(1)
    
    print("\nSelect motion mode:")
    print("1 - Wave motion (synchronized pan/tilt)")
    print("2 - Tilt step motion (center <-> down)")
    mode = input("Enter mode (1 or 2): ").strip()
    
    if mode == "2":
        # --- TILT STEP MOTION (from tilt_45.py) ---
        print("Running continuous tilt motion: center (0°) <-> down (+45°). Press Ctrl+C to stop.")
        
        while True:
            # center -> down
            for a in range(CENTER_ANGLE, DOWN_ANGLE + 1, STEP_DEG):
                move_to_angle(tilt_pwm, a)
                time.sleep(STEP_DELAY)

            # down -> center
            for a in range(DOWN_ANGLE, CENTER_ANGLE - 1, -STEP_DEG):
                move_to_angle(tilt_pwm, a)
                time.sleep(STEP_DELAY)
    else:
        # --- WAVE MOTION (synchronized pan/tilt) ---
        print("Running synchronized 160-degree wave motion. Press Ctrl+C to stop.")
        
        start_time = time.time()
        
        while True:
            # 't' tracks elapsed seconds
            t = time.time() - start_time
            
            # --- The Wave Math ---
            # Base sine wave oscillates smoothly between -1.0 and +1.0
            # Multiplying 't' by SWEEP_SPEED controls how fast the wave flows
            pan_angle = math.sin(t * SWEEP_SPEED) * MAX_ANGLE_LIMIT
            
            # Adding a phase shift (e.g., math.pi / 2) creates a fluid tracking wave effect.
            # This makes the tilt motor lag slightly behind the pan motor for a circular/figure-8 dance.
            tilt_angle = math.sin((t * SWEEP_SPEED) + (math.pi / 2)) * MAX_TILT_ANGLE_LIMIT
            tilt_angle = tilt_angle + TILT_DOWN_DELTA_DEG
            tilt_angle = max(-MAX_TILT_ANGLE_LIMIT, min(MAX_TILT_ANGLE_LIMIT, tilt_angle))

            # --- Update Hardware Directly ---
            pan_pwm.change_duty_cycle(angle_to_duty_cycle(pan_angle))
            tilt_pwm.change_duty_cycle(angle_to_duty_cycle(tilt_angle))
            
            # A tiny delay keeps the loop responsive without overwhelming system resources
            time.sleep(0.01)

except KeyboardInterrupt:
    print("\nStopping safely...")
    pan_pwm.stop()
    tilt_pwm.stop()
    print("Servos stopped.")