"""Tests for Session dataclass + SessionStatus enum (3-state after simplification)."""

from src.collector.models import Session, SessionStatus


def test_session_status_values():
    """SessionStatus has exactly 3 members — gray/UNKNOWN removed."""
    assert SessionStatus.IDLE.value == "idle"
    assert SessionStatus.WORKING.value == "working"
    assert SessionStatus.PERMISSION.value == "permission"
    # Removed in simplification:
    assert not hasattr(SessionStatus, "UNKNOWN")


def test_session_status_count():
    assert len(SessionStatus) == 3


def test_session_minimal():
    s = Session(
        id="abc-123",
        jsonl_path="C:/Users/me/.claude/projects/x/abc-123.jsonl",
        cwd="C:/Users/me",
    )
    assert s.id == "abc-123"
    assert s.cwd == "C:/Users/me"
    assert s.title == ""  # default
    assert s.subtitle == ""  # default
    assert s.context_pct == 0.0  # default
    assert s.model == ""  # default
    assert s.status == SessionStatus.IDLE  # default (newly-discovered sessions start green)
    assert s.last_activity_ts == 0.0  # default


def test_session_full():
    from datetime import datetime

    s = Session(
        id="x",
        jsonl_path="p",
        cwd="c",
        title="Search for things",
        subtitle="Edit: foo.py",
        context_pct=42.5,
        model="claude-sonnet-4-6",
        status=SessionStatus.WORKING,
        last_activity_ts=datetime(2026, 6, 15, 12, 0, 0).timestamp(),
    )
    assert s.title == "Search for things"
    assert s.context_pct == 42.5
    assert s.status == SessionStatus.WORKING
