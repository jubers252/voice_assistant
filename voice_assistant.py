"""Voice Assistant - Main Entry Point"""

import os
import signal
import subprocess
import sys
import threading
import time
import json
import ctypes
import speech_recognition as sr
from concurrent.futures import ThreadPoolExecutor
from dotenv import load_dotenv

from audio.audio_processor import AudioProcessors
from camera.camera_display_control import is_camera_display_enabled, set_camera_display_enabled
from speech.speech_recognizer import SpeechRecognizer
from conversation.conversation_manager import ConversationManager
from connectors.spotify_connector import SpotifyConnector
from connectors.reminder_manager import ReminderManager
from connectors.telegram_bot import TelegramBot
from handlers.event_scheduler import EventScheduler
from gpio_setup import PixelLEDController
from handlers.strands_agent_handler import StrandsAgent
from strands.models.openai import OpenAIModel
from handlers.wake_word_manager import WakeWordManager
from camera.camera_context import add_camera_context_to_command, clear_wake_request, get_wake_request, read_tracking_angles
from anime_face_display import FaceDisplayController

load_dotenv()

current_dir = os.path.dirname(os.path.abspath(__file__))
DEFAULT_EVENTS_FILE = os.path.join(current_dir, "events.json")
DISPLAY_SYNC_INTERVAL = 0.2

class VoiceAssistant:
    """Voice Assistant - Main Application Class"""
    
    def __init__(self):
        """Initialize all components"""
        print("[INIT] Voice Assistant Starting...\n")
        self.camera_process = None
        self.face_display = None
        self.camera_display_enabled = False
        self.display_sync_stop_event = threading.Event()
        self.display_sync_thread = None
        self.current_user = "default_user"
        self.wake_manager = None
        self.wake_request_stop_event = threading.Event()
        self.wake_request_thread = None
        self.last_wake_request_at = 0.0
        self.telegram_bot = None
        self.telegram_stop_event = threading.Event()
        self.telegram_thread = None
        self.telegram_last_update_id = 0

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
        set_camera_display_enabled(False)
        self.face_display = FaceDisplayController(mode="neutral")
        self.face_display.start()
        self._start_display_sync()

    def _set_face_mode(self, mode: str):
        if self.camera_display_enabled:
            return
        if self.face_display is None:
            return
        try:
            self.face_display.set_mode(mode)
        except Exception as e:
            print(f"[FACE] Failed to set mode '{mode}': {e}")

    def set_camera_display(self, enabled: bool):
        enabled = bool(enabled)
        set_camera_display_enabled(enabled)
        self.camera_display_enabled = enabled

        if enabled:
            if self.face_display is not None:
                self.face_display.hide()
            print("[DISPLAY] Camera tracking window enabled.")
            return

        if self.face_display is not None:
            self.face_display.show()
        print("[DISPLAY] Anime face window enabled.")

    def toggle_camera_display(self):
        self.set_camera_display(not self.camera_display_enabled)

    def _display_sync_loop(self):
        while not self.display_sync_stop_event.is_set():
            enabled = is_camera_display_enabled(default=False)
            self.camera_display_enabled = enabled

            if self.face_display is not None:
                tracking_angles = read_tracking_angles()
                self.face_display.set_pupil_angles(
                    tracking_angles.get("pupil_pan_angle", 0.0),
                    tracking_angles.get("pupil_tilt_angle", 0.0),
                )
                if enabled:
                    self.face_display.hide()
                else:
                    if not self.face_display.is_running():
                        self.face_display.start()
                    self.face_display.show()
            self.display_sync_stop_event.wait(DISPLAY_SYNC_INTERVAL)

    def _start_display_sync(self):
        if self.display_sync_thread and self.display_sync_thread.is_alive():
            return

        self.display_sync_stop_event.clear()
        self.display_sync_thread = threading.Thread(
            target=self._display_sync_loop,
            name="display-sync",
            daemon=True,
        )
        self.display_sync_thread.start()

    def _stop_display_sync(self):
        self.display_sync_stop_event.set()
        if self.display_sync_thread and self.display_sync_thread.is_alive():
            self.display_sync_thread.join(timeout=1.0)
        self.display_sync_thread = None


    def _initialize_audio_and_recognizer(self):
        self.audio_processors = AudioProcessors()
        self.audio_processors.set_pixel_led(self.pixel_led)
        self.audio_processors.set_state_callback(self._set_face_mode)

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

        print(f"[INIT] Face Display Controller: {self.face_display}")
        print(f"[INIT] Face Display Running: {self.face_display.is_running() if self.face_display else 'N/A'}")
        
        self.command_processor = StrandsAgent(
            session_id=self.current_user,
            model=model,
            pixel_led=self.pixel_led,
            recognizer=self.recognizer,
            audio_processors=self.audio_processors,
            state_callback=self._set_face_mode,
            face_display=self.face_display,
        )
        
        print(f"[INIT] Agent Created with face_display: {self.command_processor.face_display}")


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
            [sys.executable, os.path.join(current_dir, "camera", "hand_detection.py")],
            cwd=current_dir,
            start_new_session=True,
            preexec_fn=preexec,
        )
        print(f"[CAMERA] Camera context process started with PID {self.camera_process.pid}.", flush=True)

    def _wake_request_loop(self):
        while not self.wake_request_stop_event.is_set():
            wake_request = get_wake_request()
            updated_at = wake_request.get("updated_at") if wake_request else None
            if updated_at and updated_at > self.last_wake_request_at:
                self.last_wake_request_at = updated_at
                triggered = bool(self.wake_manager and self.wake_manager.trigger_listening())
                clear_wake_request()
                if triggered:
                    print("[HAND] Wake request forwarded to assistant listening.")
            self.wake_request_stop_event.wait(0.2)

    def _start_wake_request_listener(self):
        if self.wake_request_thread and self.wake_request_thread.is_alive():
            return

        clear_wake_request()
        self.wake_request_stop_event.clear()
        self.wake_request_thread = threading.Thread(
            target=self._wake_request_loop,
            name="wake-request-listener",
            daemon=True,
        )
        self.wake_request_thread.start()

    def _stop_wake_request_listener(self):
        self.wake_request_stop_event.set()
        if self.wake_request_thread and self.wake_request_thread.is_alive():
            self.wake_request_thread.join(timeout=1.0)
        self.wake_request_thread = None
        clear_wake_request()

    def _handle_telegram_message(self, message_data):
        try:
            msg_type = message_data.get("type")
            sender = message_data.get("sender_name", "").strip() or "Unknown"
            content = message_data.get("content", "")
            chat_id = message_data.get("chat_id")

            print(f"[TELEGRAM] Message from {sender} ({msg_type}): {content}")

            if msg_type == "text" and content:
                result = self.command_processor.process_user_command(content)
                response_text = ""
                if isinstance(result, dict):
                    response_text = result.get("response", "") or ""
                if response_text and self.telegram_bot and chat_id is not None:
                    self.telegram_bot.send_message(chat_id=chat_id, text=response_text)
        except Exception as e:
            print(f"[TELEGRAM] Error handling message: {e}")

    def _telegram_loop(self):
        while not self.telegram_stop_event.is_set():
            try:
                updates = self.telegram_bot.get_updates(
                    offset=self.telegram_last_update_id + 1,
                    timeout=10,
                    allowed_updates=["message"],
                )
                if updates:
                    for update in updates:
                        update_id = update.get("update_id", 0)
                        if update_id > self.telegram_last_update_id:
                            self.telegram_last_update_id = update_id

                        message_data = self.telegram_bot.extract_message_data(update)
                        if message_data:
                            self._handle_telegram_message(message_data)
            except Exception as e:
                print(f"[TELEGRAM] Polling error: {e}")

            self.telegram_stop_event.wait(0.2)

    def _start_telegram_listener(self):
        if self.telegram_thread and self.telegram_thread.is_alive():
            return

        try:
            self.telegram_bot = TelegramBot()
            self.telegram_stop_event.clear()
            self.telegram_thread = threading.Thread(
                target=self._telegram_loop,
                name="telegram-listener",
                daemon=True,
            )
            self.telegram_thread.start()
            print("[TELEGRAM] Telegram listener started.")
        except Exception as e:
            print(f"[TELEGRAM] Telegram listener disabled: {e}")
            self.telegram_bot = None

    def _stop_telegram_listener(self):
        self.telegram_stop_event.set()
        if self.telegram_thread and self.telegram_thread.is_alive():
            self.telegram_thread.join(timeout=1.0)
        self.telegram_thread = None

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
            state_callback=self._set_face_mode,
            input_device_index=None,
        )
        self.wake_manager.start_detection(
            process_command_callback=self._process_wake_command_with_camera_context
        )
        self._start_wake_request_listener()
        self._start_telegram_listener()


    def _shutdown_runtime_services(self):
        try:
            if self.wake_manager is not None:
                self.wake_manager.stop_detection()
        except Exception:
            pass

        self._stop_wake_request_listener()
        self._stop_telegram_listener()

        self.pixel_led.off()
        set_camera_display_enabled(False)
        self._stop_display_sync()
        if self.face_display is not None:
            self.face_display.stop()
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
