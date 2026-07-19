"""Voice Assistant - Main Entry Point"""

import os
import signal
import subprocess
import sys
import time
import json
import ctypes
import speech_recognition as sr
from concurrent.futures import ThreadPoolExecutor
from dotenv import load_dotenv

from audio.audio_processor import AudioProcessors
from speech.speech_recognizer import SpeechRecognizer
from conversation.conversation_manager import ConversationManager
from connectors.spotify_connector import SpotifyConnector
from connectors.reminder_manager import ReminderManager
from handlers.event_scheduler import EventScheduler
from gpio_setup import PixelLEDController
from handlers.strands_agent_handler import StrandsAgent
from strands.models.openai import OpenAIModel
from handlers.wake_word_manager import WakeWordManager
from camera_context import add_camera_context_to_command

load_dotenv()

current_dir = os.path.dirname(os.path.abspath(__file__))
DEFAULT_EVENTS_FILE = os.path.join(current_dir, "events.json")

class VoiceAssistant:
    """Voice Assistant - Main Application Class"""
    
    def __init__(self):
        """Initialize all components"""
        print("[INIT] Voice Assistant Starting...\n")
        self.camera_process = None
        self.current_user = "default_user"
        self.wake_manager = None

        self._initialize_hardware()
        self._initialize_audio_and_recognizer()
        self._initialize_memory_and_reminders()
        self._initialize_command_processor()
        self._initialize_scheduling()

        # Start camera process only after successful initialization to avoid orphans.
        self._start_camera_context_process()
        
        print("[INIT] Initialization Complete\n")


    def _initialize_hardware(self):
        self.pixel_led = PixelLEDController(led_count=26, brightness=1.0, simulate=False)
        self.pixel_led.off()


    def _initialize_audio_and_recognizer(self):
        self.audio_processors = AudioProcessors()
        self.audio_processors.set_pixel_led(self.pixel_led)

        shared_recognizer = sr.Recognizer()
        self._setup_recognizer(shared_recognizer)
        self.initial_energy_threshold = shared_recognizer.energy_threshold

        self.recognizer = SpeechRecognizer(
            shared_recognizer,
            self.audio_processors,
            device_index=0,
            pixel_led=self.pixel_led,
        )


    def _initialize_memory_and_reminders(self):
        self.conversation_manager = ConversationManager()
        self.conversation_history = self.conversation_manager.conversation_history

        self.reminder_manager = ReminderManager()
        self.reminder_manager.set_audio_processors(self.audio_processors)
        self.reminder_manager.start_reminder_checker()


    def _initialize_command_processor(self):
        self.spotify_connector = SpotifyConnector(None)
        self.recognizer.set_spotify_connector(self.spotify_connector)
        self.spotify_connector.set_speech_recognizer(self.recognizer)

        openai_api_key = os.getenv("OPENAI_API_KEY")
        model = OpenAIModel(
            model_id="gpt-5.4-mini",
            client_args={"api_key": openai_api_key},
            params={"temperature": 0.7, "max_completion_tokens": 2000},
        )

        self.command_processor = StrandsAgent(
            session_id=self.current_user,
            model=model,
            pixel_led=self.pixel_led,
            recognizer=self.recognizer,
            audio_processors=self.audio_processors,
        )


    def _initialize_scheduling(self):
        # Prevent scheduled tasks from blocking assistant command handling.
        self.event_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="scheduler")
        self.event_scheduler = EventScheduler(check_interval=60)
        self.event_scheduler.register_callback(self._handle_scheduled_event_async)


    def switch_user(self, user_id: str):
        """Switch to a different user session.

        Args:
            user_id: Unique identifier for the user (e.g., 'john', 'jane', 'pi_01')
        """
        self.current_user = user_id
        print(f"[USER] Switching to user session: {user_id}")
        self.command_processor.switch_session(user_id)


    def get_current_user(self) -> str:
        """Get the current active user session ID."""
        return self.current_user


    
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
        filepath = filepath or DEFAULT_EVENTS_FILE
        
        if not os.path.exists(filepath):
            print(f"[SCHEDULER] Events file not found: {filepath}")
            return 0
        
        try:
            with open(filepath, "r", encoding="utf-8") as f:
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

    def _handle_scheduled_event_async(self, event_id, prompt):
        """Queue scheduled event to run in background thread (non-blocking)"""
        self.event_executor.submit(self._handle_scheduled_event, event_id, prompt)
    
    def _handle_scheduled_event(self, event_id, prompt):
        """Handle scheduled events (runs in executor thread)"""
        try:
            print(f"[SCHEDULER] Event triggered: {event_id}")
            result = self.command_processor.process_user_command(prompt, scheduled=True)
            
            if result:
                response = result.get('response', '')
                print(f"[SCHEDULER] Response: {response}")
        except Exception as e:
            print(f"[SCHEDULER] Error: {e}")

    def _process_wake_command_with_camera_context(self, command):
        contextual_command = add_camera_context_to_command(command)
        if contextual_command != command:
            print("[CAMERA] Added visible-person context to command.")
        else:
            print("[CAMERA] No fresh camera context available for command.")
        return self.command_processor.process_user_command(contextual_command)

    def _start_camera_context_process(self):
        """Start face/hand detection in a separate process for camera context."""
        if self.camera_process and self.camera_process.poll() is None:
            return

        print("[CAMERA] Starting camera context process...", flush=True)

        def _linux_set_parent_death_signal():
            # If the parent exits unexpectedly, kernel sends SIGTERM to this child.
            libc = ctypes.CDLL("libc.so.6")
            PR_SET_PDEATHSIG = 1
            libc.prctl(PR_SET_PDEATHSIG, signal.SIGTERM)

        preexec = _linux_set_parent_death_signal if sys.platform.startswith("linux") else None

        self.camera_process = subprocess.Popen(
            [sys.executable, os.path.join(current_dir, "hand_detection.py")],
            cwd=current_dir,
            start_new_session=True,
            preexec_fn=preexec,
        )
        print(f"[CAMERA] Camera context process started with PID {self.camera_process.pid}.", flush=True)

    def _stop_camera_context_process(self):
        """Stop the background camera context process."""
        if not self.camera_process or self.camera_process.poll() is not None:
            return

        print("[CAMERA] Stopping camera context process...")
        try:
            os.killpg(os.getpgid(self.camera_process.pid), signal.SIGTERM)
            self.camera_process.wait(timeout=5)
        except Exception:
            self.camera_process.kill()
            self.camera_process.wait(timeout=2)
        finally:
            self.camera_process = None


    def _start_runtime_services(self):
        self.audio_processors.play_beep_sound(beep_file="beep/startup_sound.wav")
        self.event_scheduler.start()

        self.wake_manager = WakeWordManager(
            audio_processors=self.audio_processors,
            recognizer=self.recognizer,
            pixel_led=self.pixel_led,
            input_device_index=None,
        )
        self.wake_manager.start_detection(
            process_command_callback=self._process_wake_command_with_camera_context
        )


    def _shutdown_runtime_services(self):
        try:
            if self.wake_manager is not None:
                self.wake_manager.stop_detection()
        except Exception:
            pass

        self.pixel_led.off()
        self.event_scheduler.stop()
        self.event_executor.shutdown(wait=True)
        self._stop_camera_context_process()
    
    def run(self):
        """Main assistant loop (VAD/listen-based, no wake-word manager dependency)."""
        print("[MAIN] Listening for speech commands (VAD-based)...\n")

        try:
            self._start_runtime_services()

            while True:
                time.sleep(0.5)
                    
        except KeyboardInterrupt:
            print("\n[MAIN] Stopped by user")
        except Exception as e:
            print(f"[MAIN] Error: {e}")
        finally:
            print("[MAIN] Shutting down...")
            self._shutdown_runtime_services()
          


def _run_main_loop():
    while True:
        assistant = None
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
        finally:
            if assistant is not None:
                assistant._stop_camera_context_process()


if __name__ == "__main__":
    _run_main_loop()
