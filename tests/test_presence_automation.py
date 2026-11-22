from contextlib import redirect_stdout
from io import StringIO
import unittest
from unittest.mock import patch

from camera.presence_automation import PresenceAutomation


class _SensorReader:
    def __init__(self, samples):
        self.samples = samples

    def get_presence_samples(self):
        return self.samples


class PresenceAutomationTests(unittest.TestCase):
    def setUp(self):
        self.automation = PresenceAutomation(
            sensor_reader=_SensorReader([]),
            home=object(),
        )

    def test_fresh_in_range_sensor_sample_counts_as_presence(self):
        self.automation.sensor_reader.samples = [
            {"distance_m": 0.9, "timestamp": 100.0}
        ]

        with patch("camera.presence_automation.time.time", return_value=100.5):
            self.assertTrue(self.automation._someone_near())

    def test_old_near_sensor_sample_does_not_count_as_presence(self):
        self.automation.sensor_reader.samples = [
            {"distance_m": 0.9, "timestamp": 1.0}
        ]

        with patch("camera.presence_automation.time.time", return_value=100.0):
            self.assertFalse(self.automation._someone_near())

    def test_sample_outside_range_does_not_count_as_presence(self):
        self.automation.sensor_reader.samples = [
            {"distance_m": 3.31, "timestamp": 100.0}
        ]

        with patch("camera.presence_automation.time.time", return_value=100.5):
            self.assertFalse(self.automation._someone_near())

    def test_distance_reading_is_printed(self):
        self.automation.sensor_reader.samples = [
            {"distance_m": 2.1, "timestamp": 100.0}
        ]
        output = StringIO()

        with patch("camera.presence_automation.time.monotonic", return_value=2.0):
            with patch("camera.presence_automation.time.time", return_value=100.5):
                with redirect_stdout(output):
                    self.automation._someone_near()

        self.assertIn("Distance reading: 2.10 m", output.getvalue())

if __name__ == "__main__":
    unittest.main()
