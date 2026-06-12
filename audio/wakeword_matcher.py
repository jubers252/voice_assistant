"""
Wake Word Matcher using Faster Whisper tiny.en model for 2nd stage verification.
Simple transcription and wake word detection.
"""


import os
import numpy as np
from collections import deque
from faster_whisper import WhisperModel


class WakeWordMatcher:
    """Matches wake words using Faster Whisper tiny.en model."""
    
    def __init__(self, wake_word="Sophie", device="cpu", buffer_duration=2, sample_rate=16000):
        self.wake_word = wake_word.lower()
        self.device = device
        self.sample_rate = sample_rate
        self.buffer_duration = buffer_duration
        
        # Initialize deque for 2-second audio buffer
        self.buffer_size = buffer_duration * sample_rate
        self.audio_buffer = deque(maxlen=self.buffer_size)
        
        print(f"Loading Faster Whisper tiny.en model...")
        self.model = WhisperModel("tiny.en", device=device, cpu_threads=4, num_workers=4, compute_type="int8")
        print("Model loaded!")
    

    def transcribe(self, audio_file):
        """Transcribe audio file."""
        if not os.path.exists(audio_file):
            raise FileNotFoundError(f"Audio file not found: {audio_file}")
        
        segments, _ = self.model.transcribe(audio_file, language="en")
        text = "".join([seg.text for seg in segments]).strip()
        return text
    
    def transcribe_chunk(self, audio_data, sample_rate=16000):
        """
        Transcribe audio chunk (bytes or numpy array).
        
        Args:
            audio_data: Audio chunk as bytes or numpy array
            sample_rate: Sample rate of the audio (default: 16000 Hz)
        
        Returns:
            Transcribed text from the audio chunk
        """
        try:
            # Convert bytes to numpy array if needed
            if isinstance(audio_data, bytes):
                audio_data = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32) / 32768.0
            elif isinstance(audio_data, np.ndarray):
                # Ensure it's float32 in [-1, 1] range
                if audio_data.dtype == np.int16:
                    audio_data = audio_data.astype(np.float32) / 32768.0
                elif audio_data.dtype != np.float32:
                    audio_data = audio_data.astype(np.float32)
            
            # Transcribe the audio chunk
            segments, _ = self.model.transcribe(
                audio_data,
                language="en",
                vad_filter=True,
                vad_parameters={"min_speech_duration_ms": 250}
            )
            text = "".join([seg.text for seg in segments]).strip()
            return text
        except Exception as e:
            print(f"Error transcribing audio chunk: {e}")
            return ""

    
    def record_and_transcribe(self, duration=2, sample_rate=16000):
        """
        Record audio from microphone and transcribe it.
        
        Args:
            duration: Duration to record in seconds (default: 2)
            sample_rate: Sample rate in Hz (default: 16000)
        
        Returns:
            Transcribed text
        """
        audio_data = self.record_from_mic(duration=duration, sample_rate=sample_rate)
        
        if len(audio_data) > 0:
            print("Transcribing...")
            text = self.transcribe_chunk(audio_data, sample_rate=sample_rate)
            print(f"Result: {text}")
            return text
        else:
            print("No audio recorded")
            return ""
    

obj = WakeWordMatcher()

text = obj.transcribe("model_training/audio_data/wakeword_367.wav")
print(f"Transcribed text: {text}")