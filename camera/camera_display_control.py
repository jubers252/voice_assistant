import json
import os


STATE_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "camera_display_state.json",
)


def is_camera_display_enabled(default=False):
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as state_file:
            payload = json.load(state_file)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return default

    return bool(payload.get("enabled", default))


def set_camera_display_enabled(enabled):
    payload = {"enabled": bool(enabled)}
    temp_path = f"{STATE_PATH}.tmp"
    with open(temp_path, "w", encoding="utf-8") as state_file:
        json.dump(payload, state_file)
    os.replace(temp_path, STATE_PATH)


def toggle_camera_display_enabled(default=False):
    next_state = not is_camera_display_enabled(default=default)
    set_camera_display_enabled(next_state)
    return next_state
