"""
Simplified Voice Assistant using modular handlers
This shows how the main file would look after separation
"""

import os
import time
import threading
import sounddevice as sd
from dotenv import load_dotenv


# Component imports
from audio.audio_processor import AudioProcessors
from audio.wake_word_detector import WakeWordDetector
from speech.speech_recognizer import SpeechRecognizer
from conversation.conversation_manager import ConversationManager

from connectors.reminder_manager import ReminderManager
from handlers.wake_word_manager import WakeWordManager
# from handlers.command_processor import CommandProcessor  # Replaced by LangChain processor
from handlers.langchain_command_processor import LangChainAgentProcessor
from gpio_setup import PixelLEDController


load_dotenv()

# Configuration from environment variables
MIC_GAIN = float(os.environ.get('MIC_GAIN', '2.5'))  # Default 2.5x gain for better sensitivity to normal speech

current_dir = os.path.dirname(os.path.abspath(__file__))
model_dir = os.path.join(current_dir, 'model')


class VoiceAssistantRefactored:
    """Refactored Voice Assistant with modular handlers"""
    
    def __init__(self):
        """Initialize the voice assistant components"""
        print("Initializing Voice Assistant...")
        
        # Core components
        self.pixel_led = PixelLEDController(led_count=6, brightness=1.0, simulate=False)
        self.audio_processors = AudioProcessors()
        self.audio_processors.set_pixel_led(self.pixel_led)  # Connect LED to audio processor
        
        # Set digital gain for MEMS INMP441 microphone (adjust as needed)
        # Recommended values: 1.5-3.0x for MEMS mics, test with test_microphone_gain.py
        # Higher gain (2.5x) for better sensitivity to normal speech volumes
        self.audio_processors.set_digital_gain(MIC_GAIN)
        print(f"🎤 Microphone digital gain set to {MIC_GAIN}x")
        self.recognizer = SpeechRecognizer(self.audio_processors, pixel_led = self.pixel_led)
        self.conversation_manager = ConversationManager()
        self.conversation_history = self.conversation_manager.conversation_history

        self.reminder_manager = ReminderManager()
        self.reminder_manager.set_audio_processors(self.audio_processors)
        self.reminder_manager.start_reminder_checker()
        
        # Wake word detector
        ww_model_path = f"{model_dir}/WWD_improved_mems_v2.h5"
        if not os.path.exists(ww_model_path):
            ww_model_path = f"{model_dir}/wake_word_model.h5"
        
        try:
            self.wake_word_detector = WakeWordDetector(model_path=ww_model_path)
        except Exception as e:
            print(f"Warning: wake word model not loaded during init: {e}")
            self.wake_word_detector = None
        
        
        # Note: These handlers are no longer needed with LangChain implementation  
        # self.tool_action_handler = ToolActionHandler(self.conversation_history)
        # self.ai_response_handler = AIResponseHandler(
        #     conversation_manager=self.conversation_manager,
        #     audio_processors=self.audio_processors,
        #     recognizer=self.recognizer
        # )
        
        # Wake word manager
        self.wake_word_manager = WakeWordManager(
            wake_word_detector=self.wake_word_detector,
            audio_processors=self.audio_processors,
            recognizer=self.recognizer,
            pixel_led=self.pixel_led
        )
        
        # Command processor
        # self.command_processor = CommandProcessor(
        #     tool_action_handler=self.tool_action_handler,
        #     ai_response_handler=self.ai_response_handler,
        #     feedback_handler=self.feedback_handler,
        #     conversation_manager=self.conversation_manager,
        #     conversation_history=self.conversation_history,
        #     audio_processors=self.audio_processors,
        #     reminder_manager=self.reminder_manager
        # )
        self.command_processor = LangChainAgentProcessor(
            conversation_history=self.conversation_history,
            audio_processors=self.audio_processors,
            conversation_manager=self.conversation_manager,
            pixel_led=self.pixel_led
        )


    
    def run(self):
        """Main loop to run the voice assistant"""
        print("Listening for wake word...")
        
        # Set LED to off during idle/listening for wake word
        self.pixel_led.off()
        
        # Setup audio buffer through wake word manager
        audio_buffer, buffer_lock = self.wake_word_manager.setup_audio_buffer()
        
        # Start detection
        self.wake_word_manager.start_detection()
        
        try:
            self.audio_processors.play_beep_sound(beep_file="beep/startup_sound.wav")
            
            # Suppress ALSA errors when opening audio stream
            import sys
            from contextlib import contextmanager
            
            @contextmanager
            def suppress_alsa_errors():
                try:
                    devnull = os.open(os.devnull, os.O_WRONLY)
                    old_stderr = os.dup(2)
                    os.dup2(devnull, 2)
                    os.close(devnull)
                    yield
                finally:
                    os.dup2(old_stderr, 2)
                    os.close(old_stderr)
            
            with suppress_alsa_errors():
                stream = sd.InputStream(
                    samplerate=self.wake_word_manager.sample_rate,
                    channels=1,
                    dtype='float32',
                    callback=self.audio_processors.audio_callback
                )
            
            with stream:
                # Start wake word detection in separate thread
                detection_thread = threading.Thread(
                    target=self.wake_word_manager.main_detection_loop,
                    args=(self.command_processor.process_user_command,),
                    daemon=True
                )
                detection_thread.start()
                
                # Main loop - just keep running while detection is active
                while self.wake_word_manager.detection_running:
                    time.sleep(1.0)  # Reduced frequency since reminders run in background
                    
        except KeyboardInterrupt:
            print("\nProgram stopped by user")
            self.pixel_led.off()
            self.wake_word_manager.stop_detection()
        except Exception as e:
            print(f"Error in main loop: {e}")
            self.pixel_led.off()
            self.wake_word_manager.stop_detection()
        finally:
            print("Voice assistant shutting down...")
            self.pixel_led.off()
          


if __name__ == "__main__":
    import time
    while True:
        try:
            assistant = VoiceAssistantRefactored()
            assistant.run()
        except KeyboardInterrupt:
            print("Program stopped by user.")
            break
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"Fatal error: {e}")
            print("Restarting assistant in 3 seconds...")
            time.sleep(3)