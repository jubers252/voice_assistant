"""
Event Scheduler for proactive agent interactions
Schedules events at specific times to ask user if they need something
"""

import threading
import time
from datetime import datetime, time as dt_time
from typing import Callable, List, Dict, Optional


class ScheduledEvent:
    """Represents a scheduled event"""
    
    def __init__(self, event_time: dt_time, prompt: str, event_id: str = None):
        """
        Args:
            event_time: datetime.time object (e.g., time(14, 30) for 2:30 PM)
            prompt: Message to send to agent (e.g., "Do you need anything?")
            event_id: Unique identifier for the event
        """
        self.event_time = event_time
        self.prompt = prompt
        self.event_id = event_id or str(event_time)
        self.last_triggered = None
    
    def should_trigger(self, current_time: dt_time) -> bool:
        """Check if event should trigger at current time"""
        # Trigger if current time matches scheduled time (within 1 minute window)
        if self.event_time.hour == current_time.hour and self.event_time.minute == current_time.minute:
            # Avoid triggering multiple times in the same minute
            if self.last_triggered != current_time:
                self.last_triggered = current_time
                return True
        return False


class EventScheduler:
    """Manages scheduled events and triggers callbacks"""
    
    def __init__(self, check_interval: int = 60):
        """
        Args:
            check_interval: How often to check for scheduled events (seconds)
        """
        self.events: List[ScheduledEvent] = []
        self.check_interval = check_interval
        self.running = False
        self.scheduler_thread = None
        self.callbacks: List[Callable] = []
    
    def add_event(self, event_time: dt_time, prompt: str, event_id: str = None) -> str:
        """
        Add a scheduled event
        
        Args:
            event_time: Time to trigger (datetime.time object)
            prompt: Message for agent
            event_id: Optional unique ID
        
        Returns:
            event_id
        """
        event = ScheduledEvent(event_time, prompt, event_id)
        self.events.append(event)
        print(f"[SCHEDULER] Event added: {event.event_id} at {event_time.strftime('%H:%M')}")
        return event.event_id
    
    def remove_event(self, event_id: str) -> bool:
        """Remove a scheduled event"""
        for i, event in enumerate(self.events):
            if event.event_id == event_id:
                self.events.pop(i)
                print(f"[SCHEDULER] Event removed: {event_id}")
                return True
        return False
    
    def register_callback(self, callback: Callable):
        """
        Register a callback to be called when event triggers
        
        Callback signature: callback(event_id, prompt)
        """
        self.callbacks.append(callback)
    
    def _scheduler_loop(self):
        """Main scheduler loop"""
        print("[SCHEDULER] Scheduler loop started")
        
        while self.running:
            try:
                current_time = datetime.now().time()
                
                # Check each event
                for event in self.events:
                    if event.should_trigger(current_time):
                        print(f"[SCHEDULER] Event triggered: {event.event_id} - '{event.prompt}'")
                        
                        # Call all registered callbacks
                        for callback in self.callbacks:
                            try:
                                callback(event.event_id, event.prompt)
                            except Exception as e:
                                print(f"[SCHEDULER] Callback error: {e}")
                
                # Sleep before next check
                time.sleep(self.check_interval)
                
            except Exception as e:
                print(f"[SCHEDULER] Error in scheduler loop: {e}")
                time.sleep(self.check_interval)
    
    def start(self):
        """Start the scheduler"""
        if self.running:
            print("[SCHEDULER] Scheduler already running")
            return
        
        self.running = True
        self.scheduler_thread = threading.Thread(
            target=self._scheduler_loop,
            daemon=True,
            name="EventScheduler"
        )
        self.scheduler_thread.start()
        print("[SCHEDULER] Scheduler started")
    
    def stop(self):
        """Stop the scheduler"""
        self.running = False
        if self.scheduler_thread:
            self.scheduler_thread.join(timeout=5)
        print("[SCHEDULER] Scheduler stopped")
    
    def get_events(self) -> List[Dict]:
        """Get all scheduled events"""
        return [
            {
                "id": event.event_id,
                "time": event.event_time.strftime("%H:%M"),
                "prompt": event.prompt
            }
            for event in self.events
        ]
    
    def list_events(self):
        """Print all scheduled events"""
        if not self.events:
            print("[SCHEDULER] No events scheduled")
            return
        
        print("[SCHEDULER] Scheduled Events:")
        for event in self.events:
            print(f"  - {event.event_id}: {event.event_time.strftime('%H:%M')} - '{event.prompt}'")
