"""Status enum and color constants for Claude Code session indicators."""

from __future__ import annotations

from enum import Enum


class SessionStatus(Enum):
    UNKNOWN = "unknown"
    IDLE = "idle"
    WORKING = "working"
    PERMISSION = "permission"


# RGB hex strings for each status.
STATUS_COLORS: dict[SessionStatus, str] = {
    SessionStatus.UNKNOWN: "#9CA3AF",  # gray-400
    SessionStatus.IDLE: "#22C55E",  # green-500
    SessionStatus.WORKING: "#EAB308",  # yellow-500
    SessionStatus.PERMISSION: "#EF4444",  # red-500
}
