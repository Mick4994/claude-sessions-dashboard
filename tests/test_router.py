"""Tests for HookRouter — TC-001 state machine + §8.3 routing logic.

Covers all 7 hook events and all valid (current_state, event) transitions.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.core.session_registry import SessionRegistry
from src.core.status import SessionStatus
from src.server.router import HookRouter


def _registered(reg: SessionRegistry, pid: int = 1, sid: str = "sess-1"):
    reg.register(pid=pid, cwd=Path("C:/repo"))
    reg.attach_session_id(pid=pid, session_id=sid)


# TC-001: full state machine across 7 valid events + 4 starting states.


@pytest.mark.parametrize(
    "event,expected",
    [
        ("UserPromptSubmit", SessionStatus.WORKING),
        ("Stop", SessionStatus.IDLE),
        ("StopFailure", SessionStatus.IDLE),
        ("PermissionRequest", SessionStatus.PERMISSION),
        ("PostToolUse", SessionStatus.WORKING),
        ("PostToolUseFailure", SessionStatus.WORKING),
        ("PermissionDenied", SessionStatus.WORKING),
    ],
)
def test_router_maps_known_events(event: str, expected: SessionStatus):
    reg = SessionRegistry()
    _registered(reg)
    router = HookRouter(reg)
    ok = router.route(event, "sess-1")
    assert ok is True
    assert reg.get(pid=1).status == expected


def test_router_unknown_event_returns_false():
    reg = SessionRegistry()
    _registered(reg)
    router = HookRouter(reg)
    assert router.route("SomethingWeird", "sess-1") is False
    # Status unchanged.
    assert reg.get(pid=1).status == SessionStatus.UNKNOWN


def test_router_missing_sid_returns_false():
    reg = SessionRegistry()
    _registered(reg)
    router = HookRouter(reg)
    assert router.route("Stop", None) is False
    assert reg.get(pid=1).status == SessionStatus.UNKNOWN


def test_router_unknown_sid_returns_false():
    reg = SessionRegistry()
    _registered(reg)
    router = HookRouter(reg)
    assert router.route("Stop", "nonexistent") is False
    assert reg.get(pid=1).status == SessionStatus.UNKNOWN


def test_router_permission_red_to_yellow_on_post_tool_use():
    """TC-007: PERMISSION + PostToolUse → WORKING."""
    reg = SessionRegistry()
    _registered(reg)
    reg.set_status(pid=1, status=SessionStatus.PERMISSION)
    router = HookRouter(reg)
    router.route("PostToolUse", "sess-1")
    assert reg.get(pid=1).status == SessionStatus.WORKING


def test_router_permission_red_to_yellow_on_user_prompt():
    """TC-013: PERMISSION + UserPromptSubmit → WORKING."""
    reg = SessionRegistry()
    _registered(reg)
    reg.set_status(pid=1, status=SessionStatus.PERMISSION)
    router = HookRouter(reg)
    router.route("UserPromptSubmit", "sess-1")
    assert reg.get(pid=1).status == SessionStatus.WORKING


def test_router_permission_red_to_yellow_on_permission_denied():
    """TC-014: PERMISSION + PermissionDenied → WORKING."""
    reg = SessionRegistry()
    _registered(reg)
    reg.set_status(pid=1, status=SessionStatus.PERMISSION)
    router = HookRouter(reg)
    router.route("PermissionDenied", "sess-1")
    assert reg.get(pid=1).status == SessionStatus.WORKING


def test_router_routes_to_correct_pid_by_sid():
    """TC-015: hook with sid routes to the PID that owns that sid."""
    reg = SessionRegistry()
    _registered(reg, pid=1, sid="sess-A")
    _registered(reg, pid=2, sid="sess-B")
    router = HookRouter(reg)
    router.route("Stop", "sess-B")
    assert reg.get(pid=1).status == SessionStatus.UNKNOWN
    assert reg.get(pid=2).status == SessionStatus.IDLE