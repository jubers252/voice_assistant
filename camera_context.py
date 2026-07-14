import json
import os
import time


CONTEXT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "camera_context.json")
CONTEXT_MAX_AGE_SECONDS = 20


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
        "visible_people": people,
        "visible_face_count": max(visible_face_count, len(people)),
        "last_seen_person": last_seen_person or (people[0] if people else None),
        "updated_at": time.time(),
    }

    temp_path = f"{CONTEXT_PATH}.tmp"
    with open(temp_path, "w", encoding="utf-8") as context_file:
        json.dump(payload, context_file)
    os.replace(temp_path, CONTEXT_PATH)


def read_camera_context(max_age_seconds=CONTEXT_MAX_AGE_SECONDS):
    try:
        with open(CONTEXT_PATH, "r", encoding="utf-8") as context_file:
            payload = json.load(context_file)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}

    updated_at = payload.get("updated_at")
    if not updated_at or time.time() - updated_at > max_age_seconds:
        return {}

    return payload


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
