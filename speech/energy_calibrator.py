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
        self.is_calibrating = False
    
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
        print("[ENERGY_CALIBRATOR] Background calibration thread started (updates every {}s)".format(interval))
    
    def _calibration_loop(self, interval):
        """Continuously calibrate ambient energy at specified interval"""
        while True:
            try:
                time.sleep(interval)
                self._calibrate_silent(duration=0.5, multiplier=1.5)
            except Exception as e:
                print("[ENERGY_CALIBRATOR] Calibration loop error: {}".format(e))
                time.sleep(5)  # Wait before retrying
    
    def _calibrate_silent(self, duration=0.5, multiplier=1.5):
        """Silent calibration - updates threshold without printing (for background loop)"""
        try:
            mic_kwargs = {"device_index": self.device_index} if self.device_index is not None else {}
            mic_kwargs['sample_rate'] = 16000
            
            with suppress_alsa_errors():
                microphone = sr.Microphone(**mic_kwargs)
                with suppress_alsa_errors():
                    with microphone as source:
                        try:
                            # Quick ambient measurement
                            audio = self.recognizer.listen(
                                source, 
                                timeout=duration, 
                                phrase_time_limit=duration
                            )
                            
                            frame_data = audio.frame_data
                            audio_data = np.frombuffer(frame_data, dtype=np.int16)
                            rms_energy = np.sqrt(np.mean(np.square(audio_data.astype(float))))
                            new_threshold = int(rms_energy * multiplier)
                            new_threshold = max(new_threshold, 100)  # Minimum 100
                            old_threshold = int(self.recognizer.energy_threshold)
                            self.recognizer.energy_threshold = new_threshold
                            print("[ENERGY_CALIBRATOR] Background calibration: Energy {:.0f} | Threshold updated: {} → {}".format(rms_energy, old_threshold, new_threshold))
                            
                        except sr.WaitTimeoutError:
                            # Quiet environment
                            self.recognizer.energy_threshold = 200
                            print("[ENERGY_CALIBRATOR] Quiet environment - threshold set to 200")
        except Exception as e:
            print("[ENERGY_CALIBRATOR] Background calibration error: {}".format(e))
    
    def calibrate_on_demand(self, duration=1.0, multiplier=1.5):
        """Manual calibration on demand (with feedback)
        
        Args:
            duration: How long to listen for ambient noise (in seconds)
            multiplier: Multiplier to apply to ambient energy
        
        Returns:
            The new energy threshold value set
        """
        try:
            mic_kwargs = {"device_index": self.device_index} if self.device_index is not None else {}
            mic_kwargs['sample_rate'] = 16000
            
            print("[ENERGY_CALIBRATOR] Calibrating ambient energy...")
         
         
            with suppress_alsa_errors():
                microphone = sr.Microphone(**mic_kwargs)
                
                with suppress_alsa_errors():
                    with microphone as source:
                        try:
                            # Measure ambient energy for the specified duration
                            audio = self.recognizer.listen(
                                source, 
                                timeout=duration, 
                                phrase_time_limit=duration
                            )
                            
                            # Calculate energy from the audio frame data
                            frame_data = audio.frame_data
                            audio_data = np.frombuffer(frame_data, dtype=np.int16)
                            
                            # RMS (Root Mean Square) energy calculation
                            rms_energy = np.sqrt(np.mean(np.square(audio_data.astype(float))))
                            
                            # Set new threshold with multiplier for safety margin
                            new_threshold = max(int(rms_energy * multiplier), 100)  # Minimum 100
                            self.recognizer.energy_threshold = new_threshold
                            
                            print("[ENERGY_CALIBRATOR] Ambient energy: {:.0f} | New threshold: {}".format(rms_energy, new_threshold))
                            return new_threshold
                            
                        except sr.WaitTimeoutError:
                            # No sound detected, use lower threshold
                            self.recognizer.energy_threshold = 200
                            print("[ENERGY_CALIBRATOR] Quiet environment detected | Threshold set to: 200")
                            return 200
        
        except Exception as e:
            print("[ENERGY_CALIBRATOR] Calibration failed: {}".format(e))
            self.recognizer.energy_threshold = 300  # Fall back to default
            return 300
      
