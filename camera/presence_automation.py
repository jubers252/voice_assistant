"""Turn appliances off when nobody is near and restore them when someone returns."""

import os
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from connectors.home_automation import HomeAutomation

PRESENCE_DISTANCE_M = 3.30
AWAY_DELAY_SECONDS = 5.0
SAMPLE_FRESH_SECONDS = 3.0
CHECK_PERIOD_SECONDS = 0.5
RETRY_SECONDS = 5.0


class PresenceAutomation(threading.Thread):
    """Switch off whatever is on when nobody is within range, and switch back
    on only those appliances when someone returns."""

    def __init__(self, sensor_reader, home=None):
        super().__init__(daemon=True)
        self.sensor_reader = sensor_reader
        self.home = home or HomeAutomation()
        self.stop_event = threading.Event()
        self.turned_off = None  # appliances we switched off; None while someone is present

    def _someone_near(self):
        sample = self.sensor_reader.get_latest()
        return bool(
            sample
            and time.time() - sample["timestamp"] <= SAMPLE_FRESH_SECONDS
            and sample["distance_m"] <= PRESENCE_DISTANCE_M
        )

    def _turn_off_active(self):
        status = self.home.get_status()
        if not isinstance(status, dict):
            return False
        active = [name for name, on in status.items() if on is True]
        if active and not self.home.send_cmd({name: False for name in active}):
            return False
        self.turned_off = active
        print(f"[PRESENCE] Nobody within {PRESENCE_DISTANCE_M} m, turned off: {active}", flush=True)
        return True

    def _restore(self):
        if self.turned_off and not self.home.send_cmd({name: True for name in self.turned_off}):
            return False
        print(f"[PRESENCE] Someone is back, restored: {self.turned_off}", flush=True)
        self.turned_off = None
        return True

    def run(self):
        away_since = None
        retry_at = 0.0
        while not self.stop_event.wait(CHECK_PERIOD_SECONDS):
            now = time.time()
            if now < retry_at:
                continue
            try:
                if self._someone_near():
                    away_since = None
                    done = self.turned_off is None or self._restore()
                elif self.turned_off is not None:
                    continue
                else:
                    away_since = away_since or now
                    done = now - away_since < AWAY_DELAY_SECONDS or self._turn_off_active()
            except Exception as error:
                print(f"[PRESENCE] Error: {error}", flush=True)
                done = False
            if not done:
                retry_at = now + RETRY_SECONDS

    def stop(self):
        self.stop_event.set()
