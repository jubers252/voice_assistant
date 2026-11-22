"""On-request room sweep: pan the camera and look for a person with the YOLO worker.

check() is called from the presence thread and blocks; step() is called once per
frame from the camera loop, which owns the servos and the frames.
"""

import threading
from typing import Optional

from face_track_servo import PAN_NEUTRAL_ANGLE, TILT_NEUTRAL_ANGLE

SCAN_PAN_ANGLES = (90, 70, 50, 20, 0, -20, -50, -70, -90)
SETTLE_SECONDS = 0.8
DETECT_TIMEOUT_SECONDS = 10.0
CHECK_TIMEOUT_SECONDS = (
    len(SCAN_PAN_ANGLES) * (SETTLE_SECONDS + DETECT_TIMEOUT_SECONDS) + 10.0
)


class RoomScanner:
    def __init__(self):
        self._lock = threading.Lock()
        self._requested = threading.Event()
        self._done = threading.Event()
        self._found = None
        self._state = None

    def check(self, timeout=CHECK_TIMEOUT_SECONDS) -> Optional[bool]:
        """Return True if found, False if clear, or None if the scan failed."""
        with self._lock:
            self._found = None
            self._done.clear()
            self._requested.set()
            if not self._done.wait(timeout):
                self._requested.clear()
                return None
            return self._found

    def _finish(self, servo, found):
        if not found:
            servo.move_pan_to_angle(PAN_NEUTRAL_ANGLE)
            servo.move_tilt_to_angle(TILT_NEUTRAL_ANGLE)
        self._state = None
        self._found = found
        self._requested.clear()
        self._done.set()

    def _advance(self, servo):
        state = self._state
        if state["index"] + 1 < len(SCAN_PAN_ANGLES):
            state["index"] += 1
            state["phase"] = "move"
            return

        result = (
            True if state["person_found"]
            else None if state["scan_failed"]
            else False
        )
        self._finish(servo, result)

    def step(self, servo, worker, frame, face_visible, now):
        """Advance the sweep by one frame; returns True while the camera is busy scanning."""
        if self._state is None:
            if not self._requested.is_set():
                return False
            self._state = {
                "index": 0,
                "phase": "move",
                "since": now,
                "person_found": False,
                "scan_failed": False,
            }
            servo.move_tilt_to_angle(TILT_NEUTRAL_ANGLE)

        state = self._state
        if face_visible:
            state["person_found"] = True
        if worker is None:
            state["scan_failed"] = True

        if state["phase"] == "move":
            servo.move_pan_to_angle(SCAN_PAN_ANGLES[state["index"]])
            state["phase"], state["since"] = "settle", now
        elif state["phase"] == "settle":
            if now - state["since"] >= SETTLE_SECONDS:
                if worker is None:
                    self._advance(servo)
                else:
                    worker.submit(frame.copy())
                    state["phase"], state["since"] = "wait", now
        elif worker.updated_at > state["since"]:
            if worker.latest_detections():
                state["person_found"] = True
            self._advance(servo)
        elif now - state["since"] > DETECT_TIMEOUT_SECONDS:
            state["scan_failed"] = True
            self._advance(servo)
        return True
