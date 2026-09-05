import json
import os
import time


CONTEXT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "camera_context.json")
WAKE_REQUEST_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "wake_request.json")
CONTEXT_MAX_AGE_SECONDS = 20
TRACKING_MAX_AGE_SECONDS = 2


def _read_json_file(path):
    try:
        with open(path, "r", encoding="utf-8") as input_file:
            return json.load(input_file)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def _write_json_file(path, payload):
    temp_path = f"{path}.tmp"
    with open(temp_path, "w", encoding="utf-8") as output_file:
        json.dump(payload, output_file)
    os.replace(temp_path, path)


def _normalized_people(visible_people):
    return [
        name
        for name in dict.fromkeys(visible_people)
        if name and name not in {"Face", "Unknown"}
    ]


def _derive_likely_speaker(people, visible_face_count, last_seen_person):
    if len(people) == 1:
        return people[0]
    if visible_face_count > 0 and last_seen_person:
        return last_seen_person
    return None


def _build_camera_context_block(visible_face_count, people, last_seen_person, likely_speaker):
    identified_people = ", ".join(people) if people else "none"
    last_seen_value = last_seen_person or (people[0] if people else "none")
    likely_speaker_value = likely_speaker or "unknown"
    return (
        "[CAMERA_CONTEXT]\n"
        f"visible_face_count: {visible_face_count}\n"
        f"identified_people: {identified_people}\n"
        f"last_seen_person: {last_seen_value}\n"
        f"likely_speaker: {likely_speaker_value}\n"
        "[/CAMERA_CONTEXT]"
    )


def write_camera_context(visible_people, visible_face_count=0, last_seen_person=None):
    people = _normalized_people(visible_people)
    payload = {
        **_read_json_file(CONTEXT_PATH),
        "visible_people": people,
        "visible_face_count": max(visible_face_count, len(people)),
        "last_seen_person": last_seen_person or (people[0] if people else None),
        "context_updated_at": time.time(),
    }
    payload["updated_at"] = payload["context_updated_at"]

    _write_json_file(CONTEXT_PATH, payload)


def write_tracking_angles(pan_angle, tilt_angle):
    payload = {
        **_read_json_file(CONTEXT_PATH),
        "pupil_pan_angle": float(pan_angle),
        "pupil_tilt_angle": float(tilt_angle),
        "tracking_updated_at": time.time(),
    }

    _write_json_file(CONTEXT_PATH, payload)


def read_camera_context(max_age_seconds=CONTEXT_MAX_AGE_SECONDS):
    payload = _read_json_file(CONTEXT_PATH)
    if not payload:
        return {}

    updated_at = payload.get("context_updated_at") or payload.get("updated_at")
    if not updated_at or time.time() - updated_at > max_age_seconds:
        return {}

    return payload


def read_tracking_angles(max_age_seconds=TRACKING_MAX_AGE_SECONDS):
    payload = _read_json_file(CONTEXT_PATH)
    if not payload:
        return {}

    updated_at = payload.get("tracking_updated_at")
    if not updated_at or time.time() - updated_at > max_age_seconds:
        return {}

    return {
        "pupil_pan_angle": float(payload.get("pupil_pan_angle", 0.0)),
        "pupil_tilt_angle": float(payload.get("pupil_tilt_angle", 0.0)),
    }


def add_camera_context_to_command(command):
    context = read_camera_context()
    people = context.get("visible_people") or []
    visible_face_count = context.get("visible_face_count") or 0
    last_seen_person = context.get("last_seen_person")

    if visible_face_count <= 0 and not people:
        return command

    likely_speaker = _derive_likely_speaker(people, visible_face_count, last_seen_person)
    context_block = _build_camera_context_block(
        visible_face_count=visible_face_count,
        people=people,
        last_seen_person=last_seen_person,
        likely_speaker=likely_speaker,
    )

    return (
        f"{context_block}\n"
        f"User command: {command}"
    )


def set_wake_request(source="hand_gesture"):
    payload = {
        "source": source,
        "updated_at": time.time(),
    }

    _write_json_file(WAKE_REQUEST_PATH, payload)


def get_wake_request(max_age_seconds=5):
    payload = _read_json_file(WAKE_REQUEST_PATH)
    if not payload:
        return {}

    updated_at = payload.get("updated_at")
    if not updated_at or time.time() - updated_at > max_age_seconds:
        return {}

    return payload


def clear_wake_request():
    try:
        os.remove(WAKE_REQUEST_PATH)
    except FileNotFoundError:
        pass
