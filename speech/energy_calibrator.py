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
    
    # Global flag to enable/disable background calibration modifications
    enable_calibration = True  # Enabled by default, paused during listening
    
    def __init__(self, recognizer, device_index=None):
        """
        Args:
            recognizer: speech_recognition.Recognizer instance
            device_index: Microphone device index (None for default)
        """
        self.recognizer = recognizer
        self.device_index = device_index
    
    def start_continuous_calibration(self, interval=5):
        """Start background thread for continuous energy calibration
        
        Args:
            interval: Calibration interval in seconds (default 5s)
        """
        import threading
        
        # Do immediate calibration BEFORE starting background thread to ensure first listen has correct threshold
        try:
            initial_threshold = int(self.recognizer.energy_threshold)
            self._calibrate_silent(duration=1.0)
            new_threshold = int(self.recognizer.energy_threshold)
            
            # Keep threshold within safe bounds to ensure speech quality
            # Min: 1000 (avoid too-sensitive picks up everything)
            # Max: 3000 (avoid too-strict misses quiet speech)
            if new_threshold < 1000:
                self.recognizer.energy_threshold = 1000
                new_threshold = 1000
            elif new_threshold > 3000:
                self.recognizer.energy_threshold = 3000
                new_threshold = 3000
            
            print("[CALIBRATION] Initial calibration: {} → {} (range: 1000-3000)".format(initial_threshold, new_threshold))
        except Exception as e:
            print("[CALIBRATION] Initial calibration failed (non-critical): {}".format(e))
        
        # Now start background thread for continuous updates
        calibration_thread = threading.Thread(
            target=self._calibration_loop,
            args=(interval,),
            daemon=True
        )
        calibration_thread.start()
        print("[CALIBRATION] Background calibration thread started (updates every {}s, pauses during active listening)".format(interval))
    
    def _calibration_loop(self, interval):
        """Continuously calibrate ambient energy at specified interval"""
        # Initial calibration already done in start_continuous_calibration(), so start with sleep
        first_run = True
        while True:
            try:
                if first_run:
                    first_run = False
                    time.sleep(interval)  # Wait before second calibration
                else:
                    time.sleep(interval)
                
                # Skip if calibration is disabled globally
                if EnergyCalibrator.enable_calibration:
                    # Calibrate ambient noise to adjust energy threshold
                    self._calibrate_silent(duration=1.0)
            except Exception as e:
                print("[CALIBRATION] Calibration loop error: {}".format(e))
                time.sleep(5)  # Wait before retrying
    
    def _calibrate_silent(self, duration=1.0):
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
                        # This automatically adjusts energy_threshold based on current ambient noise
                        self.recognizer.adjust_for_ambient_noise(source, duration=duration)
                        
                        raw_threshold = int(self.recognizer.energy_threshold)
                        
                        # Apply damping/smoothing: don't let threshold jump too much between calibrations
                        # 70% old threshold + 30% new threshold = gradual adjustment
                        damping_factor = 0.7  # How much to keep old threshold (higher = less change)
                        smoothed_threshold = int(old_threshold * damping_factor + raw_threshold * (1 - damping_factor))
                        
                        # Keep threshold within safe bounds to ensure speech quality
                        # Min: 1000 (avoid too-sensitive picks up everything)
                        # Max: 3000 (avoid too-strict misses quiet speech)
                        if smoothed_threshold < 1000:
                            final_threshold = 1000
                        elif smoothed_threshold > 3000:
                            final_threshold = 3000
                        else:
                            final_threshold = smoothed_threshold
                        
                        self.recognizer.energy_threshold = final_threshold
                        
                        print("[CALIBRATION] Updated: {} → {} (raw: {}, smoothed: {}, range: 1000-3000)".format(
                            old_threshold, final_threshold, raw_threshold, smoothed_threshold))
        except Exception as e:
            print("[CALIBRATION] Error: {}".format(e))
      
