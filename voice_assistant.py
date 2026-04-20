"""Voice Assistant - Main Entry Point"""

import os
import time
import threading
import json
import sounddevice as sd
import speech_recognition as sr
from dotenv import load_dotenv

from audio.audio_processor import AudioProcessors
from audio.wake_word_detector import WakeWordDetector
from speech.speech_recognizer import SpeechRecognizer
from conversation.conversation_manager import ConversationManager
from connectors.spotify_connector import SpotifyConnector
from connectors.reminder_manager import ReminderManager
from connectors.telegram_bot import TelegramBot
from handlers.wake_word_manager import WakeWordManager
from handlers.event_scheduler import EventScheduler
from gpio_setup import PixelLEDController
from handlers.strands_agent_handler import StrandsAgent
from strands.models.openai import OpenAIModel

load_dotenv()

current_dir = os.path.dirname(os.path.abspath(__file__))
model_dir = os.path.join(current_dir, 'model')

class VoiceAssistant:
    """Voice Assistant - Main Application Class"""
    
    def __init__(self):
        """Initialize all components"""
        print("[INIT] Voice Assistant Starting...\n")
        
        # Initialize LED controller
        self.pixel_led = PixelLEDController(led_count=6, brightness=1.0, simulate=False)
        self.pixel_led.off()
        
        # Initialize audio components
        self.audio_processors = AudioProcessors()
        self.audio_processors.set_pixel_led(self.pixel_led)
        
        shared_recognizer = sr.Recognizer()
        self._setup_recognizer(shared_recognizer)
        
        # Pass recognizer to audio processor so it can control dynamic calibration
        self.audio_processors.set_recognizer(shared_recognizer)
        
        self.recognizer = SpeechRecognizer(
            shared_recognizer, 
            self.audio_processors,
            device_index=0,
            pixel_led=self.pixel_led
        )
        
        # Initialize conversation and reminders
        self.conversation_manager = ConversationManager()
        self.conversation_history = self.conversation_manager.conversation_history
        
        self.reminder_manager = ReminderManager()
        self.reminder_manager.set_audio_processors(self.audio_processors)
        self.reminder_manager.start_reminder_checker()
        
        # Initialize wake word detection
        ww_model_path = self._find_wake_word_model()
        try:
            print(f"[INIT] Loading wake word model from: {ww_model_path}")
            self.wake_word_detector = WakeWordDetector(model_path=ww_model_path)
        except Exception as e:
            print(f"[INIT] Error loading wake word model: {e}")
            self.wake_word_detector = None
        
        self.wake_word_manager = WakeWordManager(
            wake_word_detector=self.wake_word_detector,
            audio_processors=self.audio_processors,
            recognizer=self.recognizer,
            pixel_led=self.pixel_led
        )
        
        # Initialize AI model and command processor
        self.spotify_connector = SpotifyConnector(None)
        self.recognizer.set_spotify_connector(self.spotify_connector)
        self.spotify_connector.set_speech_recognizer(self.recognizer)
        
        openai_api_key = os.getenv("OPENAI_API_KEY")
        model = OpenAIModel(
            model_id="gpt-5.4-nano",
            client_args={"api_key": openai_api_key},
            params={"temperature": 0.7, "max_completion_tokens": 2000}
        )
        
        self.command_processor = StrandsAgent(
            session_id="pi_01",
            model=model,
            pixel_led=self.pixel_led,
            recognizer=self.recognizer,
            audio_processors=self.audio_processors
        )
        
        # Initialize optional services
        try:
            self.telegram_bot = TelegramBot()
        except Exception as e:
            print(f"[INIT] Telegram Bot not available: {e}")
            self.telegram_bot = None
        
        self.event_scheduler = EventScheduler(check_interval=60)
        self.event_scheduler.register_callback(self._handle_scheduled_event)
        
        print("[INIT] Initialization Complete\n")


    def _find_wake_word_model(self):
        """Find wake word model file"""
        candidates = [
            f"{model_dir}/WWD_respeaker_model_v11.h5",
            f"{model_dir}/WWD_respeaker_model_v10.h5",
            f"{model_dir}/wake_word_model.h5"
        ]
        for path in candidates:
            if os.path.exists(path):
                return path
        return candidates[0]  # Return first choice if none exist
    
    def _setup_recognizer(self, recognizer):
        """Configure speech recognizer"""
        recognizer.energy_threshold = 200
        recognizer.dynamic_energy_threshold = True
        recognizer.pause_threshold = 1.2
        recognizer.phrase_threshold = 0.3
        recognizer.non_speaking_duration = 1.0

    def schedule_event(self, hour, minute, prompt, event_id=None):
        """Schedule a proactive event"""
        from datetime import time as dt_time
        event_time = dt_time(hour, minute)
        return self.event_scheduler.add_event(event_time, prompt, event_id)
    
    def unschedule_event(self, event_id):
        """Remove a scheduled event"""
        return self.event_scheduler.remove_event(event_id)
    
    def list_scheduled_events(self):
        """List all scheduled events"""
        self.event_scheduler.list_events()
    
    def load_events_from_file(self, filepath=None):
        """Load scheduled events from JSON file"""
        if filepath is None:
            filepath = os.path.join(current_dir, 'events.json')
        
        if not os.path.exists(filepath):
            print(f"[SCHEDULER] Events file not found: {filepath}")
            return 0
        
        try:
            with open(filepath, 'r') as f:
                data = json.load(f)
            
            events_count = 0
            for event in data.get('events', []):
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
            
            return events_count
        except json.JSONDecodeError as e:
            print(f"[SCHEDULER] Invalid JSON format: {e}")
            return 0

    def _handle_telegram_message(self, msg_data):
        """Handle incoming Telegram messages"""
        try:
            sender = msg_data.get('sender_name', 'Unknown')
            msg_type = msg_data.get('type', '')
            chat_id = msg_data.get('chat_id', '')
            
            if msg_type == 'text':
                content = msg_data.get('content', '')
                print(f"[TELEGRAM] Message from {sender}: {content}")
                
                result = self.command_processor.process_user_command(content)
                
                if result:
                    response = result.get('response', '')
                    if response:
                        self.telegram_bot.send_message(
                            chat_id=chat_id,
                            text=response,
                            parse_mode="HTML"
                        )
                    
                    urls = result.get('urls', [])
                    if urls:
                        urls_text = "<b>Links:</b>\n" + "\n".join(urls)
                        self.telegram_bot.send_message(
                            chat_id=chat_id,
                            text=urls_text,
                            parse_mode="HTML"
                        )
        except Exception as e:
            print(f"[TELEGRAM] Error: {e}")
    
    def _handle_scheduled_event(self, event_id, prompt):
        """Handle scheduled events"""
        try:
            print(f"[SCHEDULER] Event triggered: {event_id}")
            result = self.command_processor.process_user_command(prompt)
            
            if result:
                response = result.get('response', '')
                print(f"[SCHEDULER] Response: {response}")
                
                if self.telegram_bot:
                    chat_id = os.getenv('TELEGRAM_CHAT_ID', '')
                    if chat_id:
                        self.telegram_bot.send_message(
                            chat_id=chat_id,
                            text=f"<b>Scheduled:</b>\n{response}",
                            parse_mode="HTML"
                        )
        except Exception as e:
            print(f"[SCHEDULER] Error: {e}")
    
    def run(self):
        """Main assistant loop"""
        print("[MAIN] Listening for wake word...\n")
        
        self.wake_word_manager.setup_audio_buffer()
        self.wake_word_manager.start_detection()
        
        try:
            self.audio_processors.play_beep_sound(beep_file="beep/startup_sound.wav")
            
            # Suppress ALSA errors when opening audio stream
            import os as os_module
            from contextlib import contextmanager
            
            @contextmanager
            def suppress_alsa_errors():
                try:
                    devnull = os_module.open(os_module.devnull, os_module.O_WRONLY)
                    old_stderr = os_module.dup(2)
                    os_module.dup2(devnull, 2)
                    os_module.close(devnull)
                    yield
                finally:
                    os_module.dup2(old_stderr, 2)
                    os_module.close(old_stderr)
            
            with suppress_alsa_errors():
                stream = sd.InputStream(
                    samplerate=self.wake_word_manager.sample_rate,
                    channels=1,
                    dtype='float32',
                    callback=self.audio_processors.audio_callback
                )
            
            self.wake_word_manager.set_audio_stream(stream)
            
            with stream:
                # Start wake word detection thread
                detection_thread = threading.Thread(
                    target=self.wake_word_manager.main_detection_loop,
                    args=(self.command_processor.process_user_command,),
                    daemon=True
                )
                detection_thread.start()
                
                # Start event scheduler
                self.event_scheduler.start()
                
                # Keep running until interrupted
                while self.wake_word_manager.detection_running:
                    time.sleep(1.0)
                    
        except KeyboardInterrupt:
            print("\n[MAIN] Stopped by user")
        except Exception as e:
            print(f"[MAIN] Error: {e}")
        finally:
            print("[MAIN] Shutting down...")
            self.pixel_led.off()
            self.wake_word_manager.stop_detection()
            self.event_scheduler.stop()
          


if __name__ == "__main__":
    while True:
        try:
            assistant = VoiceAssistant()
            
            # Load scheduled events
            print("Loading scheduled events...\n")
            events_loaded = assistant.load_events_from_file()
            if events_loaded > 0:
                print(f"{events_loaded} event(s) loaded\n")
                assistant.list_scheduled_events()
            
            # Run assistant
            print("Starting Voice Assistant...")
            print("Events will trigger automatically at scheduled times\n")
            assistant.run()
            
        except KeyboardInterrupt:
            print("Program stopped by user.")
            break
        except Exception as e:
            print(f"[ERROR] {e}")
            print("Restarting in 3 seconds...")
            time.sleep(3)
