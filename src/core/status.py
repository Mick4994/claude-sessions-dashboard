"""Status enum and color constants for Claude Code session indicators."""

from __future__ import annotations

from enum import Enum


class SessionStatus(Enum):
    IDLE = "idle"
    WORKING = "working"
    PERMISSION = "permission"


# RGB hex strings for each status. 3 states: IDLE/WORKING/PERMISSION.
# A freshly-discovered session defaults to IDLE (green) until a hook flips it.
STATUS_COLORS: dict[SessionStatus, str] = {
    SessionStatus.IDLE: "#22C55E",  # green-500
    SessionStatus.WORKING: "#EAB308",  # yellow-500
    SessionStatus.PERMISSION: "#EF4444",  # red-500
}
