"""
Simplified Voice Assistant using modular handlers
This shows how the main file would look after separation
"""

import os
import time
import threading
import json
import asyncio
import sounddevice as sd
import speech_recognition as sr
from dotenv import load_dotenv
# Component imports
from audio.audio_processor import AudioProcessors
from audio.wake_word_detector import WakeWordDetector
from speech.speech_recognizer import SpeechRecognizer
from speech.energy_calibrator import EnergyCalibrator
from conversation.conversation_manager import ConversationManager
from connectors.spotify_connector import SpotifyConnector
from connectors.reminder_manager import ReminderManager
from connectors.telegram_bot import TelegramBot
from handlers.wake_word_manager import WakeWordManager
from handlers.event_scheduler import EventScheduler
# from handlers.command_processor import CommandProcessor  # Replaced by LangChain processor
from handlers.langchain_command_processor import LangChainAgentProcessor
from gpio_setup import PixelLEDController


load_dotenv()

current_dir = os.path.dirname(os.path.abspath(__file__))
model_dir = os.path.join(current_dir, 'model')
yamnet_model_path = os.getenv('YAMNET_MODEL_PATH')

class VoiceAssistantRefactored:
    """Refactored Voice Assistant with modular handlers"""
    
    def __init__(self):
        """Initialize the voice assistant components"""
        print("Initializing Voice Assistant...")
        
        # Core components
        self.pixel_led = PixelLEDController(led_count=6, brightness=1.0, simulate=False)
        self.audio_processors = AudioProcessors()
        self.audio_processors.set_pixel_led(self.pixel_led)  # Connect LED to audio processor
        
        # Create single recognizer instance to be shared across all components
        shared_recognizer = sr.Recognizer()
        self._setup_recognizer(shared_recognizer)
        
        # Check speech recognition service to use
        use_azure = os.getenv('USE_AZURE', 'false').lower() == 'true'
        
        if use_azure:
            print("[ASSISTANT] Azure speech recognition enabled")
        else:
            print("[ASSISTANT] Using default Google Speech Recognition")
            
        self.recognizer = SpeechRecognizer(
            shared_recognizer,  # Pass the shared recognizer
            self.audio_processors, 
            device_index=0,  # ReSpeaker Lite (from diagnostic)
            pixel_led=self.pixel_led, 
        )
        
        self.conversation_manager = ConversationManager()
        self.conversation_history = self.conversation_manager.conversation_history

        self.reminder_manager = ReminderManager()
        self.reminder_manager.set_audio_processors(self.audio_processors)
        self.reminder_manager.start_reminder_checker()
        
        # Start continuous energy calibration (runs in background, pauses during listening)
        energy_calibrator = EnergyCalibrator(shared_recognizer, device_index=0)
        energy_calibrator.start_continuous_calibration(interval=10)
        

        ww_model_path = f"{model_dir}/WWD_respeaker_model_v11.h5"
       
        if not os.path.exists(ww_model_path):
            ww_model_path = f"{model_dir}/wake_word_model.h5"
        
        try:
            print(f"Loading wake word model from: {ww_model_path}")
            self.wake_word_detector = WakeWordDetector(model_path=ww_model_path)
        except Exception as e:
            print(f"Warning: wake word model not loaded during init: {e}")
            self.wake_word_detector = None
        
        
        # Wake word manager
        self.wake_word_manager = WakeWordManager(
            wake_word_detector=self.wake_word_detector,
            audio_processors=self.audio_processors,
            recognizer=self.recognizer,
            pixel_led=self.pixel_led
        )
        
        # Try to initialize Spotify connector for music detection

        
        self.spotify_connector = SpotifyConnector(None)
        
        # Connect Spotify to speech recognizer for dynamic timeout and music flag updates
        self.recognizer.set_spotify_connector(self.spotify_connector)
        self.spotify_connector.set_speech_recognizer(self.recognizer)
           
    
      
        self.command_processor = LangChainAgentProcessor(
            conversation_history=self.conversation_history,
            audio_processors=self.audio_processors,
            conversation_manager=self.conversation_manager,
            pixel_led=self.pixel_led,
            recognizer=self.recognizer  # Pass recognizer for follow-up questions
        )
        
        # Initialize Telegram Bot for receiving messages
        try:
            self.telegram_bot = TelegramBot()
            print("[TELEGRAM] Telegram Bot initialized - message receiving ready")
        except Exception as e:
            print(f"[TELEGRAM] Warning: Telegram Bot not initialized: {e}")
            self.telegram_bot = None
        
        # Initialize Event Scheduler for proactive interactions
        self.event_scheduler = EventScheduler(check_interval=60)
        self.event_scheduler.register_callback(self._handle_scheduled_event)
        print("[SCHEDULER] Event scheduler initialized - ready for scheduled commands")

    def _setup_recognizer(self, recognizer):
        """Configure the shared recognizer instance"""
        # Lower threshold for noisy environments + dynamic adjustment
        recognizer.energy_threshold = 100  # Lower sensitivity baseline for background noise
        recognizer.dynamic_energy_threshold = True  # Auto-adjust based on ambient noise
        recognizer.dynamic_energy_adjustment_damping = 0.10  # More aggressive adjustment (lower = faster response)
        recognizer.dynamic_energy_ratio = 1.5
        recognizer.pause_threshold = 1.3  # 1.3 seconds of silence before stopping
        recognizer.phrase_threshold = 0.3  # Minimum 300ms to catch speech start
        recognizer.non_speaking_duration = 1.0  # Allow up to 1.0 seconds pause mid-phrase
        print(f"[RECOGNIZER] Recognizer configured - Energy: {recognizer.energy_threshold}, Dynamic: {recognizer.dynamic_energy_threshold} (Damping: {recognizer.dynamic_energy_adjustment_damping})")

    def schedule_event(self, hour: int, minute: int, prompt: str, event_id: str = None) -> str:
        """
        Schedule a proactive event at a specific time
        
        Args:
            hour: Hour (0-23)
            minute: Minute (0-59)
            prompt: Message to send to agent (e.g., "Do you need help with anything?")
            event_id: Optional ID for the event
        
        Returns:
            event_id
        
        Example:
            assistant.schedule_event(14, 30, "Do you need help with anything?", "check_in_afternoon")
            assistant.schedule_event(9, 0, "Good morning! What can I help with?", "morning_greeting")
        """
        from datetime import time as dt_time
        event_time = dt_time(hour, minute)
        return self.event_scheduler.add_event(event_time, prompt, event_id)
    
    def unschedule_event(self, event_id: str) -> bool:
        """Remove a scheduled event"""
        return self.event_scheduler.remove_event(event_id)
    
    def list_scheduled_events(self):
        """List all scheduled events"""
        self.event_scheduler.list_events()
    
    def load_events_from_file(self, filepath: str = None) -> int:
        """
        Load scheduled events from JSON file
        
        Args:
            filepath: Path to events.json file. If None, uses default location.
        
        Returns:
            Number of events loaded
        
        Example:
            assistant.load_events_from_file()  # Loads from events.json
            assistant.load_events_from_file("custom_events.json")
        """

        if filepath is None:
            filepath = os.path.join(current_dir, 'events.json')
        
        try:
            # Check if file exists
            if not os.path.exists(filepath):
                print(f"[SCHEDULER] Events file not found: {filepath}")
                return 0
            
            # Read JSON file
            with open(filepath, 'r') as f:
                data = json.load(f)
            
            # Load each event
            events_count = 0
            if 'events' in data:
                for event in data['events']:
                    try:
                        self.schedule_event(
                            hour=event.get('hour'),
                            minute=event.get('minute'),
                            prompt=event.get('prompt'),
                            event_id=event.get('event_id')
                        )
                        events_count += 1
                    except Exception as e:
                        print(f"[SCHEDULER] Error loading event {event.get('event_id')}: {e}")
            
            print(f"[SCHEDULER] Loaded {events_count} event(s) from {filepath}")
            return events_count
            
        except json.JSONDecodeError as e:
            print(f"[SCHEDULER] Invalid JSON format in {filepath}: {e}")
            return 0
        except Exception as e:
            print(f"[SCHEDULER] Error loading events file: {e}")
            return 0

    def _handle_telegram_message(self, msg_data):
        """Handle incoming Telegram messages and return responses"""
        try:
            sender = msg_data['sender_name']
            msg_type = msg_data['type']
            chat_id = msg_data['chat_id']
            
            if msg_type == 'text':
                content = msg_data.get('content', '')
                print(f"\n[TELEGRAM] Message from {sender}: {content}")
                
                # Pass to agent for processing and get response
                result = self.command_processor.process_user_command(content)
                
                if result:
                    # Send response back to Telegram
                    response = result.get('response', '')
                    urls = result.get('urls', [])
                    
                    print(f"[TELEGRAM] Sending response to {sender}")
                    if response:
                        self.telegram_bot.send_message(
                            chat_id=chat_id,
                            text=response,
                            parse_mode="HTML"
                        )
                    
                    # Send URLs if available
                    if urls:
                        urls_text = "\n\n<b>Links:</b>\n" + "\n".join(urls)
                        self.telegram_bot.send_message(
                            chat_id=chat_id,
                            text=urls_text,
                            parse_mode="HTML"
                        )
                
            else:
                print(f"[TELEGRAM] Received {msg_type} from {sender} (not text message)")
                
        except Exception as e:
            print(f"[TELEGRAM] Error handling message: {e}")
    
    def _handle_scheduled_event(self, event_id: str, prompt: str):
        """Handle scheduled events - passively ask user if they need something"""
        try:
            print(f"\n[SCHEDULER] Handling scheduled event: {event_id}")
            
            # Process the prompt through the agent
            result = self.command_processor.process_user_command(prompt)
            
            if result:
                response = result.get('response', '')
                
                # Speak the response to user
                print(f"[SCHEDULER] Agent response: {response}")
                
                # Send to Telegram if bot is available
                if self.telegram_bot:
                    chat_id = os.getenv('TELEGRAM_CHAT_ID', '')
                    if chat_id:
                        try:
                            self.telegram_bot.send_message(
                                chat_id=chat_id,
                                text=f"<b>Scheduled Check-in:</b>\n{response}",
                                parse_mode="HTML"
                            )
                            print(f"[SCHEDULER] Message sent to Telegram")
                        except Exception as e:
                            print(f"[SCHEDULER] Could not send to Telegram: {e}")
                
        except Exception as e:
            print(f"[SCHEDULER] Error handling scheduled event: {e}")
    
    async def _async_telegram_receiver(self):
        """Async wrapper for Telegram message receiver"""
        try:
            if not self.telegram_bot:
                print("[TELEGRAM] Bot not initialized, skipping message receiver")
                return
            
            print("[TELEGRAM] Starting async message receiver...")
            loop = asyncio.get_event_loop()
            
            # Run blocking receive_messages in thread pool executor
            await loop.run_in_executor(
                None,
                self.telegram_bot.receive_messages,
                self._handle_telegram_message,
                ['message']
            )
        except asyncio.CancelledError:
            print("[TELEGRAM] Message receiver cancelled")
        except Exception as e:
            print(f"[TELEGRAM] Error in async receiver: {e}")
    
    async def _async_main_loop(self, detection_running_check):
        """Async main loop that handles both voice detection and Telegram"""
        # Create telegram receiver task
        telegram_task = asyncio.create_task(self._async_telegram_receiver())
        
        try:
            # Keep the main loop running
            while detection_running_check():
                await asyncio.sleep(1.0)
        except KeyboardInterrupt:
            print("\nProgram stopped by user")
        except Exception as e:
            print(f"Error in async main loop: {e}")
        finally:
            # Cancel telegram task
            telegram_task.cancel()
            try:
                await telegram_task
            except asyncio.CancelledError:
                pass
    
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
            
            # Pass the stream reference to wake word manager so it can stop/start it
            self.wake_word_manager.set_audio_stream(stream)
            
            with stream:
                # Start wake word detection in separate thread
                detection_thread = threading.Thread(
                    target=self.wake_word_manager.main_detection_loop,
                    args=(self.command_processor.process_user_command,),
                    daemon=True
                )
                detection_thread.start()
                
                # Start event scheduler for proactive interactions
                self.event_scheduler.start()
                
                # Create and run async main loop with Telegram receiver
                try:
                    asyncio.run(self._async_main_loop(
                        lambda: self.wake_word_manager.detection_running
                    ))
                except KeyboardInterrupt:
                    print("\nProgram stopped by user")
                except Exception as e:
                    print(f"Error in async loop: {e}") 
                    
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
            self.event_scheduler.stop()  # Stop scheduler on shutdown
          


if __name__ == "__main__":
    import time
    while True:
        try:
            assistant = VoiceAssistantRefactored()
            
            # Load events from JSON file
            print("\nLoading scheduled events from events.json...")
            events_loaded = assistant.load_events_from_file()
            
            if events_loaded > 0:
                print(f"{events_loaded} event(s) loaded successfully\n")
                # Show loaded events
                assistant.list_scheduled_events()
            else:
                print("No events loaded. Check events.json file.\n")
            
            print("Starting Voice Assistant...")
            print("Events will trigger automatically at scheduled times")
        
            
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
