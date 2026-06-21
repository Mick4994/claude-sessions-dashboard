"""Tests for SessionRegistry — TC-002, TC-012, TC-024.

Pure-Python registry mapping PID → SessionEntry. Thread-safe, observable via
callbacks. No Qt dependency.
"""

from __future__ import annotations

import threading
from pathlib import Path

from src.core.session_registry import SessionEntry, SessionRegistry
from src.core.status import SessionStatus


def _entry(pid: int = 1234, cwd: Path | None = None) -> SessionEntry:
    return SessionEntry(pid=pid, cwd=cwd or Path("C:/Users/me/proj"))


# TC-002: basic register/unregister behavior


def test_register_emits_callback():
    reg = SessionRegistry()
    seen: list[SessionEntry] = []
    reg.on_added(seen.append)
    entry = reg.register(pid=1, cwd=Path("C:/a"))
    assert entry.pid == 1
    assert len(seen) == 1
    assert seen[0] is entry


def test_unregister_emits_callback():
    reg = SessionRegistry()
    removed: list[SessionEntry] = []
    reg.on_removed(removed.append)
    entry = reg.register(pid=2, cwd=Path("C:/b"))
    reg.unregister(pid=2)
    assert len(removed) == 1
    assert removed[0] is entry
    assert not reg.has(pid=2)


def test_set_status_emits_callback_with_new_status():
    reg = SessionRegistry()
    events: list[tuple[SessionEntry, SessionStatus]] = []
    reg.on_status_changed(lambda e, s: events.append((e, s)))
    reg.register(pid=3, cwd=Path("C:/c"))
    reg.set_status(pid=3, status=SessionStatus.WORKING)
    assert len(events) == 1
    entry, new_status = events[0]
    assert entry.pid == 3
    assert new_status == SessionStatus.WORKING


def test_register_with_jsonl_path():
    reg = SessionRegistry()
    jsonl = Path("C:/Users/me/.claude/projects/x/sess.jsonl")
    entry = reg.register(pid=4, cwd=Path("C:/x"), jsonl_path=jsonl)
    assert entry.jsonl_path == jsonl
    assert reg.get(pid=4).jsonl_path == jsonl


def test_attach_session_id():
    reg = SessionRegistry()
    reg.register(pid=5, cwd=Path("C:/d"))
    reg.attach_session_id(pid=5, session_id="sess-A")
    entry = reg.get_by_sid("sess-A")
    assert entry is not None
    assert entry.pid == 5
    assert entry.session_id == "sess-A"
    assert reg.find_pid_by_sid("sess-A") == 5


def test_attach_session_id_unknown_pid():
    reg = SessionRegistry()
    # Should silently no-op (and not crash).
    reg.attach_session_id(pid=999, session_id="ghost")
    assert reg.get_by_sid("ghost") is None


def test_unregister_unknown_pid():
    reg = SessionRegistry()
    removed: list[SessionEntry] = []
    reg.on_removed(removed.append)
    result = reg.unregister(pid=9999)
    assert result is None
    assert removed == []


def test_multiple_pids_same_cwd_independent():
    """TC: same cwd, different PIDs → both independent entries with own status."""
    reg = SessionRegistry()
    cwd = Path("C:/shared")
    a = reg.register(pid=10, cwd=cwd)
    b = reg.register(pid=11, cwd=cwd)
    reg.set_status(pid=10, status=SessionStatus.WORKING)
    reg.set_status(pid=11, status=SessionStatus.IDLE)
    assert a.status == SessionStatus.WORKING
    assert b.status == SessionStatus.IDLE
    assert len(reg) == 2


def test_set_status_unknown_pid():
    reg = SessionRegistry()
    events: list[tuple[SessionEntry, SessionStatus]] = []
    reg.on_status_changed(lambda e, s: events.append((e, s)))
    # Should silently no-op.
    reg.set_status(pid=888, status=SessionStatus.PERMISSION)
    assert events == []


def test_set_status_no_change_no_event():
    """Setting the same status must NOT trigger the callback."""
    reg = SessionRegistry()
    events: list[tuple[SessionEntry, SessionStatus]] = []
    reg.on_status_changed(lambda e, s: events.append((e, s)))
    reg.register(pid=20, cwd=Path("C:/e"))
    reg.set_status(pid=20, status=SessionStatus.WORKING)
    reg.set_status(pid=20, status=SessionStatus.WORKING)
    assert len(events) == 1


# TC-012: thread-safe concurrent writes


def test_thread_safe_registry_writes():
    reg = SessionRegistry()
    pids = list(range(100))

    def writer(start: int, count: int) -> None:
        for i in range(start, start + count):
            reg.register(pid=i, cwd=Path(f"C:/p{i}"))
            reg.set_status(pid=i, status=SessionStatus.WORKING)
            reg.attach_session_id(pid=i, session_id=f"sess-{i}")

    t1 = threading.Thread(target=writer, args=(0, 50))
    t2 = threading.Thread(target=writer, args=(50, 50))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert len(reg) == 100
    for i in range(100):
        assert reg.find_pid_by_sid(f"sess-{i}") == i
        assert reg.get(pid=i).status == SessionStatus.WORKING


# TC-024: concurrent register/unregister


def test_concurrent_register_unregister():
    reg = SessionRegistry()
    pids = list(range(100))

    def writer() -> None:
        for pid in pids:
            reg.register(pid=pid, cwd=Path(f"C:/p{pid}"))

    def remover() -> None:
        for pid in pids:
            reg.unregister(pid=pid)

    t1 = threading.Thread(target=writer)
    t2 = threading.Thread(target=remover)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    # After both finish, registry may be empty or partially populated depending
    # on scheduling, but must not crash and must maintain invariants.
    for entry in reg.iter_all():
        assert entry.pid in pids
        assert reg.has(pid=entry.pid)
    for pid in pids:
        entry = reg.get(pid=pid)
        if entry is not None:
            assert entry.pid == pid


def test_iter_all_returns_snapshot():
    reg = SessionRegistry()
    for pid in range(5):
        reg.register(pid=pid, cwd=Path(f"C:/p{pid}"))
    snap = list(reg.iter_all())
    assert {e.pid for e in snap} == {0, 1, 2, 3, 4}


def test_unregister_removes_from_sid_index():
    """unregister must also drop the entry from the by_sid index."""
    reg = SessionRegistry()
    reg.register(pid=42, cwd=Path("C:/x"))
    reg.attach_session_id(pid=42, session_id="sess-Z")
    assert reg.get_by_sid("sess-Z") is not None
    reg.unregister(pid=42)
    assert reg.get_by_sid("sess-Z") is None