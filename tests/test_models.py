from src.collector.models import SessionStatus


def test_session_status_values():
    assert SessionStatus.WORKING.value == "working"
    assert SessionStatus.IDLE.value == "idle"
    assert SessionStatus.PERMISSION.value == "permission"
    assert SessionStatus.ERROR.value == "error"
    assert SessionStatus.STALE.value == "stale"


def test_session_status_count():
    assert len(SessionStatus) == 5
