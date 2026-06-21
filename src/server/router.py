"""HookRouter: maps incoming hook event names to registry status updates."""

from __future__ import annotations

from src.core.session_registry import SessionRegistry
from src.core.status import SessionStatus

# Event name → target status.
# No mapping means the event is ignored (200, no state change).
_EVENT_STATUS: dict[str, SessionStatus] = {
    "UserPromptSubmit": SessionStatus.WORKING,
    "Stop": SessionStatus.IDLE,
    "StopFailure": SessionStatus.IDLE,
    "PermissionRequest": SessionStatus.PERMISSION,
    "PostToolUse": SessionStatus.WORKING,
    "PostToolUseFailure": SessionStatus.WORKING,
    "PermissionDenied": SessionStatus.WORKING,
}


class HookRouter:
    """Routes POST /hook/{event}?sid={session_id} to registry status updates."""

    def __init__(self, registry: SessionRegistry) -> None:
        self._registry = registry

    def route(self, event: str, session_id: str | None) -> bool:
        """Apply the event's status mapping if known.  Returns True on success."""
        status = _EVENT_STATUS.get(event)
        if status is None:
            return False
        if session_id is None:
            return False
        self._registry.set_status_by_sid(session_id, status)
        return True
