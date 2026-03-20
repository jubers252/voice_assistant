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
        
        print("[CALIBRATION] Background calibration thread started (updates every {}s, pauses during active listening)".format(interval))
        
        # Start background thread for continuous calibration
        calibration_thread = threading.Thread(
            target=self._calibration_loop,
            args=(interval,),
            daemon=True
        )
        calibration_thread.start()
    
    def _calibration_loop(self, interval):
        """Monitor calibration (digital duplex systems use recognizer's built-in dynamic adjustment)"""
        # For digital duplex audio systems, don't try to open microphones separately
        # The recognizer's dynamic_energy_threshold handles adjustment automatically during listening
        print("[CALIBRATION] Using recognizer's dynamic adjustment - no active calibration for digital duplex")
        
        # Just keep thread alive as placeholder
        while True:
            try:
                time.sleep(interval)
                # Silent monitoring only - no microphone access
                if not EnergyCalibrator.enable_calibration:
                    continue
            except Exception as e:
                time.sleep(5)
    
    def _calibrate_silent(self, duration=1.0):
        """Silent calibration using recognizer's built-in ambient noise adjustment"""
        try:
            mic_kwargs = {}
            mic_kwargs['sample_rate'] = 16000
            
            # For digital duplex: don't specify device_index if it could conflict
            if self.device_index is not None:
                try:
                    mic_kwargs["device_index"] = self.device_index
                except:
                    pass
            
            old_threshold = int(self.recognizer.energy_threshold)
            
            with suppress_alsa_errors():
                microphone = sr.Microphone(**mic_kwargs)
                with suppress_alsa_errors():
                    with microphone as source:
                        # Use recognizer's built-in ambient noise calibration
                        self.recognizer.adjust_for_ambient_noise(source, duration=duration)
                        raw_threshold = int(self.recognizer.energy_threshold)
                        
                        # Apply damping: gradually adjust to avoid sudden jumps
                        damping_factor = 0.7  # Keep 70% of old value
                        final_threshold = int(old_threshold * damping_factor + raw_threshold * (1 - damping_factor))
                        
                        self.recognizer.energy_threshold = final_threshold
                        
                        print("[CALIBRATION] Updated: {} → {} (raw: {})".format(
                            old_threshold, final_threshold, raw_threshold))
        except Exception as e:
            # Re-raise to let caller handle it
            raise
      
