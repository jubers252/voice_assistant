"""
Simple Energy Calibration Module
Uses the recognizer's built-in dynamic energy threshold adjustment
"""

import speech_recognition as sr


class EnergyCalibrator:
    """Uses recognizer's built-in dynamic energy threshold"""
    
    enable_calibration = True  # Global flag (for compatibility)
    
    def __init__(self, recognizer, device_index=None):
        """
        Args:
            recognizer: speech_recognition.Recognizer instance
            device_index: Microphone device index (None for default)
        """
        self.recognizer = recognizer
        self.device_index = device_index
    
    def start_continuous_calibration(self, interval=10):
        """Start continuous calibration (uses recognizer's built-in dynamic adjustment)
        
        Args:
            interval: Ignored - uses recognizer's built-in adjustment during listening
        """
        # Enable the recognizer's built-in dynamic energy threshold
        self.recognizer.dynamic_energy_threshold = True
        print("[CALIBRATION] Using recognizer's dynamic energy threshold (auto-adjusts during listening)")
      
