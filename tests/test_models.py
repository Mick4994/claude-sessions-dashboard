from src.collector.models import Session, SessionStatus


def test_session_status_values():
    assert SessionStatus.WORKING.value == "working"
    assert SessionStatus.IDLE.value == "idle"
    assert SessionStatus.PERMISSION.value == "permission"
    assert SessionStatus.ERROR.value == "error"
    assert SessionStatus.STALE.value == "stale"


def test_session_status_count():
    assert len(SessionStatus) == 5


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
    assert s.status == SessionStatus.IDLE  # default
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
