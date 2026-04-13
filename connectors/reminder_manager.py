"""
Reminder Manager for Voice Assistant
Handles setting, checking, and managing reminders with natural language processing
"""

import json
import os
import re
import threading
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional

REMINDERS_FILE = "reminders.json"


class ReminderManager:
    """Manages voice assistant reminders with natural language processing."""
    
    def __init__(self):
        self.reminders = self.load_reminders()
        self.reminder_thread = None
        self.running = False
        self.audio_processors = None
        self._last_file_mtime = self._get_file_mtime()
        
    def _get_file_mtime(self) -> float:
        """Get the modification time of the reminders file."""
        try:
            return os.path.getmtime(REMINDERS_FILE)
        except OSError:
            return 0.0
    
    def _check_file_changes(self):
        """Check if the reminders file has been modified and reload if necessary."""
        current_mtime = self._get_file_mtime()
        if current_mtime > self._last_file_mtime:
            print("Reminders file changed, reloading...")
            self.reminders = self._load_reminders_from_file()
            self._last_file_mtime = current_mtime
    
    def _load_reminders_from_file(self) -> List[Dict]:
        """Internal method to load reminders from file."""
        try:
            with open(REMINDERS_FILE, 'r') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return []
    
    def load_reminders(self) -> List[Dict]:
        """Load reminders from file."""
        return self._load_reminders_from_file()
    
    def save_reminders(self):
        """Save reminders to file."""
        with open(REMINDERS_FILE, 'w') as f:
            json.dump(self.reminders, f, indent=2)
    
    def add_reminder(self, text: str, remind_time: str, description: str = "", recurring: str = "once") -> str:
        """Add a new reminder with natural language time parsing.
        
        Args:
            text: Reminder text
            remind_time: When to remind (e.g., '5 PM', 'in 30 minutes')
            description: Optional description
            recurring: 'once', 'daily', 'weekly' (default: 'once')
        """
        try:
            remind_datetime = self._parse_time(remind_time)
            
            if not remind_datetime:
                return "I couldn't understand the time. Please try again with a clear time like '5 PM tomorrow' or 'in 30 minutes'."
            
            reminder = {
                "id": len(self.reminders) + 1,
                "text": text,
                "description": description,
                "remind_time": remind_datetime.isoformat(),
                "created_time": datetime.now().isoformat(),
                "active": True,
                "notified": False,
                "recurring": recurring
            }
            
            self.reminders.append(reminder)
            self.save_reminders()
            
            time_str = remind_datetime.strftime("%I:%M %p on %B %d")
            return f"Reminder set for {time_str}: {text}"
            
        except Exception as e:
            return f"Sorry, I couldn't set that reminder. Error: {str(e)}"
    
    def _parse_time(self, time_str: str) -> Optional[datetime]:
        """Parse natural language time into datetime."""
        now = datetime.now()
        time_str = time_str.lower().strip()
        
        try:
            # Handle "in X minutes/hours/days"
            if "in " in time_str:
                numbers = re.findall(r'\d+', time_str)
                if numbers:
                    num = int(numbers[0])
                    if "minute" in time_str:
                        return now + timedelta(minutes=num)
                    elif "hour" in time_str:
                        return now + timedelta(hours=num)
                    elif "day" in time_str:
                        return now + timedelta(days=num)
            
            # Handle "tomorrow at X"
            if "tomorrow" in time_str and ("pm" in time_str or "am" in time_str):
                numbers = re.findall(r'\d+', time_str)
                if numbers:
                    hour = int(numbers[0])
                    if "pm" in time_str and hour != 12:
                        hour += 12
                    elif "am" in time_str and hour == 12:
                        hour = 0
                    tomorrow = now + timedelta(days=1)
                    return tomorrow.replace(hour=hour, minute=0, second=0, microsecond=0)
            
            # Handle "today at X" or just "X PM/AM"
            if "today" in time_str or any(word in time_str for word in ["pm", "am"]):
                numbers = re.findall(r'\d+', time_str)
                if numbers:
                    hour = int(numbers[0])
                    if "pm" in time_str and hour != 12:
                        hour += 12
                    elif "am" in time_str and hour == 12:
                        hour = 0
                    
                    target_time = now.replace(hour=hour, minute=0, second=0, microsecond=0)
                    if target_time <= now:
                        target_time += timedelta(days=1)
                    return target_time
            
            # Handle specific times like "5:30 PM"
            if ":" in time_str:
                time_part = time_str.split("at")[-1].strip() if "at" in time_str else time_str
                try:
                    parsed_time = datetime.strptime(time_part, "%I:%M %p")
                    target_time = now.replace(
                        hour=parsed_time.hour,
                        minute=parsed_time.minute,
                        second=0,
                        microsecond=0
                    )
                    if target_time <= now:
                        target_time += timedelta(days=1)
                    return target_time
                except:
                    pass
            
        except Exception:
            pass
        
        return None
    
    def get_active_reminders(self) -> List[Dict]:
        """Get all active reminders."""
        return [r for r in self.reminders if r["active"] and not r["notified"]]
    
    def get_due_reminders(self) -> List[Dict]:
        """Get reminders that are due now."""
        now = datetime.now()
        due_reminders = []
        
        for reminder in self.reminders:
            if (reminder["active"] and not reminder["notified"] and 
                datetime.fromisoformat(reminder["remind_time"]) <= now):
                due_reminders.append(reminder)
                
        return due_reminders
    
    def mark_reminded(self, reminder_id: int):
        """Mark a reminder as notified."""
        for reminder in self.reminders:
            if reminder["id"] == reminder_id:
                reminder["notified"] = True
                break
        self.save_reminders()
    
    def _reschedule_daily_reminder(self, reminder: Dict):
        """Reschedule a daily reminder for the next day at the same time."""
        try:
            current_time = datetime.fromisoformat(reminder["remind_time"])
            next_day = current_time + timedelta(days=1)
            
            # Update the reminder for next day
            for r in self.reminders:
                if r["id"] == reminder["id"]:
                    r["remind_time"] = next_day.isoformat()
                    r["notified"] = False
                    self.save_reminders()
                    print(f"Daily reminder rescheduled for {next_day.strftime('%I:%M %p on %B %d')}")
                    break
        except Exception as e:
            print(f"Error rescheduling daily reminder: {e}")
    
    def cancel_reminder(self, reminder_id: int) -> str:
        """Cancel a specific reminder."""
        for reminder in self.reminders:
            if reminder["id"] == reminder_id:
                reminder["active"] = False
                self.save_reminders()
                return f"Cancelled reminder: {reminder['text']}"
        return "Reminder not found."
    
    def list_reminders(self) -> str:
        """List all active reminders."""
        active_reminders = self.get_active_reminders()
        
        if not active_reminders:
            return "You have no active reminders."
        
        result = "Your active reminders:\n"
        for i, reminder in enumerate(active_reminders, 1):
            remind_time = datetime.fromisoformat(reminder["remind_time"])
            time_str = remind_time.strftime("%I:%M %p on %B %d")
            result += f"{i}. {reminder['text']} - {time_str}\n"
        
        return result.strip()
    
    def set_audio_processors(self, audio_processors):
        """Set the audio processors for TTS announcements"""
        self.audio_processors = audio_processors
    
    def start_reminder_checker(self):
        """Start the background thread that checks and announces reminders every 30 seconds."""
        if self.running and self.reminder_thread and self.reminder_thread.is_alive():
            return  # Thread is already running
        
        self.running = True
        self.reminder_thread = threading.Thread(target=self._reminder_check_loop, daemon=True)
        self.reminder_thread.start()
        print("Reminder checker started - will check every 30 seconds")
    
    def stop_reminder_checker(self):
        """Stop the reminder checker thread."""
        self.running = False
        print("Reminder checker stopped.")
    
    def _reminder_check_loop(self):
        """Background loop that checks for due reminders every 30 seconds and announces them."""
        while self.running:
            try:
                # Check if file has been modified and reload if necessary
                self._check_file_changes()
                
                # Check for due reminders
                due_reminders = self.get_due_reminders()
                
                # If there are due reminders, announce them
                if due_reminders and self.audio_processors:
                    for reminder in due_reminders:
                        print(f"REMINDER ALERT: {reminder['text']}")
                        
                        # Check if TTS is not currently speaking
                        if not getattr(self.audio_processors, 'is_speaking', False) and reminder["notified"] == False:
                           
                            time_diff = (datetime.now() - datetime.fromisoformat(reminder['remind_time'])).total_seconds()
                            if time_diff > 600 and reminder.get('recurring') != 'daily': 
                                print("Skipping reminder - more than 10 minutes late")
                                self.mark_reminded(reminder["id"])
                                continue
                            elif time_diff > 1800 and reminder.get('recurring') == 'daily':
                                print("Skipping daily reminder - more than 30 minutes late")
                                self.mark_reminded(reminder["id"])
                                continue

                            for _ in range(3):
                                self.audio_processors.play_beep_sound(beep_file ="beep/japan-eas-alarm-277877.mp3")
                                time.sleep(0.2)
                            time.sleep(0.3)
                            
                            # Speak the reminder
                            recurring_text = " (Daily Alarm)" if reminder.get('recurring') == 'daily' else ""
                            reminder_message = f"Reminder{recurring_text}: {reminder['text']}"
                            self.audio_processors.speak(reminder_message)
                            print("✓ Reminder announced successfully")
                            
                            # Handle recurring reminders
                            if reminder.get('recurring') == 'daily':
                                # Schedule for next day at the same time
                                self._reschedule_daily_reminder(reminder)
                            else:
                                # Mark one-time reminder as notified
                                self.mark_reminded(reminder["id"])
                        else:
                            print("Assistant is speaking, will retry reminder later")
                
                # Wait 30 seconds before next check
                time.sleep(30)
                
            except Exception as e:
                print(f"Error in reminder check loop: {e}")
                import traceback
                traceback.print_exc()
                time.sleep(30)  # Wait on error
    
    def get_due_reminders_for_speech(self) -> Optional[str]:
        """Get due reminders formatted for voice assistant speech."""
        due_reminders = self.get_due_reminders()
        
        if not due_reminders:
            return None
        
        if len(due_reminders) == 1:
            reminder = due_reminders[0]
            self.mark_reminded(reminder["id"])
            return f"Reminder: {reminder['text']}"
        else:
            reminder_texts = [r['text'] for r in due_reminders]
            for reminder in due_reminders:
                self.mark_reminded(reminder["id"])
            return f"You have {len(due_reminders)} reminders: " + ", ".join(reminder_texts)

    def handle_reminder_action(self, action_data: Dict) -> str:
        """Handle reminder actions from the voice assistant."""
        action = action_data.get("action", "")
        
        if action == "set": 
            text = action_data.get("text", "")
            time_str = action_data.get("time", "")
            return self.add_reminder(text, time_str)
        
        elif action == "list":
            return self.list_reminders()
        
        elif action == "cancel":
            reminder_id = action_data.get("id", 0)
            return self.cancel_reminder(reminder_id)
        
        elif action == "check":
            due_reminder = self.get_due_reminders_for_speech()
            return due_reminder or "No reminders are due right now."
        
        else:
            return "I don't understand that reminder action."