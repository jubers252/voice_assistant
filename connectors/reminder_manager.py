"""
Reminder Manager for Voice Assistant
Handles setting, checking, and managing reminders using Gemini AI
"""

import json
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import threading
import time


REMINDERS_FILE = "reminders.json"


class ReminderManager:
    """Manages voice assistant reminders with natural language processing."""
    
    def __init__(self):
        self.reminders = self.load_reminders()
        self.reminder_thread = None
        self.running = False
        
    def load_reminders(self) -> List[Dict]:
        """Load reminders from file."""
        try:
            with open(REMINDERS_FILE, 'r') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return []
    
    def save_reminders(self):
        """Save reminders to file."""
        with open(REMINDERS_FILE, 'w') as f:
            json.dump(self.reminders, f, indent=2)
    
    def add_reminder(self, text: str, remind_time: str, description: str = "") -> str:
        """
        Add a new reminder.
        
        Args:
            text: The reminder message
            remind_time: When to remind (parsed by Gemini)
            description: Optional additional description
            
        Returns:
            Confirmation message
        """
        try:
            # Parse the time (you can enhance this with more sophisticated parsing)
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
                "notified": False
            }
            
            self.reminders.append(reminder)
            self.save_reminders()
            
            # Only start reminder checking thread if not running and this is not during initialization
            # The voice assistant will start it separately when needed
            
            time_str = remind_datetime.strftime("%I:%M %p on %B %d")
            return f"Reminder set for {time_str}: {text}"
            
        except Exception as e:
            return f"Sorry, I couldn't set that reminder. Error: {str(e)}"
    
    def _parse_time(self, time_str: str) -> Optional[datetime]:
        """Parse natural language time into datetime."""
        now = datetime.now()
        time_str = time_str.lower().strip()
        
        try:
            # Handle "in X minutes/hours"
            if "in " in time_str:
                # Extract number more carefully
                import re
                numbers = re.findall(r'\d+', time_str)
                if numbers:
                    num = int(numbers[0])  # Take the first number found
                    if "minute" in time_str:
                        return now + timedelta(minutes=num)
                    elif "hour" in time_str:
                        return now + timedelta(hours=num)
                    elif "day" in time_str:
                        return now + timedelta(days=num)
            
            # Handle "tomorrow at X"
            if "tomorrow" in time_str:
                tomorrow = now + timedelta(days=1)
                if "pm" in time_str or "am" in time_str:
                    import re
                    numbers = re.findall(r'\d+', time_str)
                    if numbers:
                        hour = int(numbers[0])
                        if "pm" in time_str and hour != 12:
                            hour += 12
                        elif "am" in time_str and hour == 12:
                            hour = 0
                        return tomorrow.replace(hour=hour, minute=0, second=0, microsecond=0)
            
            # Handle "today at X"
            if "today" in time_str or any(word in time_str for word in ["pm", "am"]):
                if "pm" in time_str or "am" in time_str:
                    import re
                    numbers = re.findall(r'\d+', time_str)
                    if numbers:
                        hour = int(numbers[0])
                        if "pm" in time_str and hour != 12:
                            hour += 12
                        elif "am" in time_str and hour == 12:
                            hour = 0
                        
                        target_time = now.replace(hour=hour, minute=0, second=0, microsecond=0)
                        
                        # If the time has passed today, set it for tomorrow
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
                    
                    # If the time has passed today, set it for tomorrow
                    if target_time <= now:
                        target_time += timedelta(days=1)
                    
                    return target_time
                except:
                    pass
            
        except Exception as e:
            print(f"Debug: Error parsing time '{time_str}': {e}")
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
    
    def start_reminder_checker(self):
        """Start the background thread that checks for due reminders."""
        if self.running and self.reminder_thread and self.reminder_thread.is_alive():
            return  # Thread is already running
        
        self.running = True
        self.reminder_thread = threading.Thread(target=self._check_reminders_loop, daemon=True)
        self.reminder_thread.start()
        print("Reminder checker started.")
    
    def stop_reminder_checker(self):
        """Stop the reminder checker thread."""
        self.running = False
        print("Reminder checker stopped.")
    
    def _check_reminders_loop(self):
        """Background loop to check for due reminders."""
        while self.running:
            try:
                due_reminders = self.get_due_reminders()
                for reminder in due_reminders:
                    # This would be handled by the main voice assistant
                    print(f" REMINDER: {reminder['text']}")
                    self.mark_reminded(reminder["id"])
                
                time.sleep(60)  # Check every 60 seconds (1 minute)
                
            except Exception as e:
                print(f"Error in reminder checker: {e}")
                time.sleep(60)  # Wait longer if there's an error
    
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


    # Example usage functions for integration
    def handle_reminder_action(self, action_data: Dict) -> str:
        """Handle reminder actions from the voice assistant."""
        rm = ReminderManager()
        
        action = action_data.get("action", "")
        
        if action == "set": 
            text = action_data.get("text", "")
            time_str = action_data.get("time", "")
            return rm.add_reminder(text, time_str)
        
        elif action == "list":
            return rm.list_reminders()
        
        elif action == "cancel":
            reminder_id = action_data.get("id", 0)
            return rm.cancel_reminder(reminder_id)
        
        elif action == "check":
            due_reminder = rm.get_due_reminders_for_speech()
            return due_reminder or "No reminders are due right now."
        
        else:
            return "I don't understand that reminder action."


def test_reminder_system():
    """
    Simple test function that:
    1. Sets a reminder for 1 minute from now
    2. Starts a thread that checks every 10 seconds
    3. Shows when the reminder triggers
    """
    print("🧪 Testing Reminder System...")
    
    rm = ReminderManager()
    
    # Clear any existing reminders for clean test
    rm.reminders = []
    rm.save_reminders()
    
    # Set a test reminder for 1 minute from now
    test_message = "Test reminder - this is a 1 minute test!"
    result = rm.add_reminder(test_message, "in 1 minute")
    print(f"✅ {result}")
    
    # Start the reminder checker with faster check interval for testing
    print("🔄 Starting reminder checker (checking every 10 seconds)...")
    
    def test_check_loop():
        """Test loop that checks every 10 seconds instead of 60."""
        check_count = 0
        while check_count < 12:  # Run for up to 2 minutes (12 * 10 seconds)
            try:
                check_count += 1
                print(f"⏰ Check #{check_count} - {datetime.now().strftime('%H:%M:%S')}")
                
                due_reminders = rm.get_due_reminders()
                if due_reminders:
                    for reminder in due_reminders:
                        print(f"🔔 REMINDER TRIGGERED: {reminder['text']}")
                        rm.mark_reminded(reminder["id"])
                    print("✅ Test completed - reminder was triggered!")
                    return
                else:
                    print("   No reminders due yet...")
                
                time.sleep(10)  # Check every 10 seconds
                
            except Exception as e:
                print(f"❌ Error in test checker: {e}")
                time.sleep(10)
        
        print("⏰ Test timeout reached (2 minutes)")
    
    # Start the test thread (don't use daemon so script waits for it)
    test_thread = threading.Thread(target=test_check_loop, daemon=False)
    test_thread.start()
    
    print(f"📱 Test started at {datetime.now().strftime('%H:%M:%S')}")
    print("💡 The reminder should trigger in about 1 minute...")
    print("🛑 Press Ctrl+C to stop the test")
    
    try:
        # Keep the main thread alive and wait for test to complete
        test_thread.join()
        print("✅ Test completed successfully!")
    except KeyboardInterrupt:
        print("\n🛑 Test stopped by user")


if __name__ == "__main__":
    # Test the reminder manager
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        # Run the test function
        test_reminder_system()
    else:
        # When run directly, run the full test by default
        print("🚀 Running reminder system test...")
        test_reminder_system()
