"""Camera and hand detection module for voice assistant."""

from .camera_context import (
    add_camera_context_to_command,
    clear_wake_request,
    get_wake_request,
    read_tracking_angles,
    set_wake_request,
    write_camera_context,
    write_tracking_angles,
)
from .camera_display_control import is_camera_display_enabled, toggle_camera_display_enabled

__all__ = [
    "add_camera_context_to_command",
    "clear_wake_request",
    "get_wake_request",
    "read_tracking_angles",
    "set_wake_request",
    "write_camera_context",
    "write_tracking_angles",
    "is_camera_display_enabled",
    "toggle_camera_display_enabled",
]
