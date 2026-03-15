"""
Energy Calibration Module
Handles continuous ambient energy measurement and adaptive threshold adjustment
for speech recognition, running in background without blocking listening
"""

import numpy as np
import speech_recognition as sr
import time
from contextlib import contextmanager
import os


@contextmanager
def suppress_alsa_errors():
    """Context manager to suppress ALSA/JACK error output"""
    try:
        devnull = os.open(os.devnull, os.O_WRONLY)
        old_stderr = os.dup(2)
        os.dup2(devnull, 2)
        os.close(devnull)
        yield
    finally:
        os.dup2(old_stderr, 2)
        os.close(old_stderr)


class EnergyCalibrator:
    """Handles continuous ambient energy calibration for speech recognizer"""
    
    def __init__(self, recognizer, device_index=None):
        """
        Args:
            recognizer: speech_recognition.Recognizer instance
            device_index: Microphone device index (None for default)
        """
        self.recognizer = recognizer
        self.device_index = device_index
        self.pause_calibration = False  # Flag to pause calibration during active listening
    
    def start_continuous_calibration(self, interval=30):
        """Start background thread for continuous energy calibration
        
        Args:
            interval: Calibration interval in seconds (default 30s)
        """
        import threading
        calibration_thread = threading.Thread(
            target=self._calibration_loop,
            args=(interval,),
            daemon=True
        )
        calibration_thread.start()
        print("[ENERGY_CALIBRATOR] Background calibration thread started (updates every {}s, pauses during active listening)".format(interval))
    
    def _calibration_loop(self, interval):
        """Continuously calibrate ambient energy at specified interval"""
        # Run calibration immediately on startup (don't wait 30 seconds)
        first_run = True
        while True:
            try:
                if not first_run:
                    time.sleep(interval)
                else:
                    first_run = False
                
                # Skip if calibration is paused (during active listening)
                if not self.pause_calibration:
                    # Use longer duration (2 seconds) to better capture ambient noise
                    # Use lower multiplier (1.3 instead of 1.5) to be conservative and not filter distant speech
                    self._calibrate_silent(duration=2.0, multiplier=1.3)
            except Exception as e:
                print("[ENERGY_CALIBRATOR] Calibration loop error: {}".format(e))
                time.sleep(5)  # Wait before retrying
    
    def _calibrate_silent(self, duration=2.0, multiplier=1.3):
        """Silent calibration using recognizer's built-in ambient noise adjustment"""
        try:
            mic_kwargs = {"device_index": self.device_index} if self.device_index is not None else {}
            mic_kwargs['sample_rate'] = 16000
            
            old_threshold = int(self.recognizer.energy_threshold)
            
            with suppress_alsa_errors():
                microphone = sr.Microphone(**mic_kwargs)
                with suppress_alsa_errors():
                    with microphone as source:
                        # Use recognizer's built-in ambient noise calibration
                        # This uses the library's own energy calculation method for consistency
                        self.recognizer.adjust_for_ambient_noise(source, duration=duration)
                        
                        new_threshold = int(self.recognizer.energy_threshold)
                        
                        # Prevent drastic threshold jumps that break detection at night
                        # If new threshold is more than 50% different from old, cap the change
                        max_increase_ratio = 1.5  # Allow up to 50% increase
                        max_decrease_ratio = 0.7  # Allow threshold to drop to 70% of old value (better for night)
                        
                        if new_threshold > old_threshold * max_increase_ratio:
                            new_threshold = int(old_threshold * max_increase_ratio)
                            self.recognizer.energy_threshold = new_threshold
                            print("[ENERGY_CALIBRATOR] Background calibration: Threshold capped at increase limit")
                        elif new_threshold < old_threshold * max_decrease_ratio and old_threshold > 100:
                            new_threshold = int(old_threshold * max_decrease_ratio)
                            self.recognizer.energy_threshold = new_threshold
                            print("[ENERGY_CALIBRATOR] Background calibration: Threshold restored for night sensitivity")
                        
                        print("[ENERGY_CALIBRATOR] Background calibration: Threshold updated: {} → {} (multiplier: {})".format(
                            old_threshold, new_threshold, multiplier))
        except Exception as e:
            print("[ENERGY_CALIBRATOR] Background calibration error: {}".format(e))
      
