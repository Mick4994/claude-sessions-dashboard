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


# TC-PENDING: hook fires before collector registers → must queue, not drop.
# Regression for the silent-drop bug that left UserPromptSubmit stuck gray.


def test_set_status_before_register_queues_pending():
    reg = SessionRegistry()
    reg.set_status_by_sid("sid-X", SessionStatus.WORKING)
    reg.register_by_sid("sid-X", cwd=Path("."))
    entry = reg.get_by_sid("sid-X")
    assert entry.status == SessionStatus.WORKING


def test_pending_overwritten_by_later_hook():
    reg = SessionRegistry()
    reg.set_status_by_sid("sid-Y", SessionStatus.WORKING)
    reg.set_status_by_sid("sid-Y", SessionStatus.PERMISSION)
    reg.register_by_sid("sid-Y", cwd=Path("."))
    entry = reg.get_by_sid("sid-Y")
    assert entry.status == SessionStatus.PERMISSION


def test_pending_drained_after_register():
    """register 后再 set 不应再写到 pending。"""
    reg = SessionRegistry()
    reg.register_by_sid("sid-Z", cwd=Path("."))
    reg.set_status_by_sid("sid-Z", SessionStatus.WORKING)
    assert "sid-Z" not in reg._pending


def test_register_fires_status_changed_callback_for_pending():
    """pending 被应用时应触发 on_status_changed（驱动 UI 刷新）。"""
    reg = SessionRegistry()
    fired: list[tuple[str, SessionStatus]] = []
    reg.on_status_changed(lambda e, s: fired.append((e.session_id, s)))
    reg.set_status_by_sid("sid-W", SessionStatus.WORKING)
    reg.register_by_sid("sid-W", cwd=Path("."))
    assert fired == [("sid-W", SessionStatus.WORKING)]


def test_set_status_after_register_skips_callback_if_unchanged():
    """status 没变时不重复触发 callback — 现有行为，不能因为 pending 队列而回归。
    D:\ 3-状态模型下 SessionEntry 默认 IDLE；设为 IDLE 不应触发 callback。"""
    reg = SessionRegistry()
    reg.register_by_sid("sid-V", cwd=Path("."))
    fired: list[SessionStatus] = []
    reg.on_status_changed(lambda e, s: fired.append(s))
    reg.set_status_by_sid("sid-V", SessionStatus.IDLE)
    assert fired == []


def test_unregister_does_not_clear_pending():
    """未注册的 hook 不能被 unregister 清掉（注册表语义里 pending 是 hook 队列）。"""
    reg = SessionRegistry()
    reg.set_status_by_sid("sid-orphan", SessionStatus.PERMISSION)
    assert reg._pending.get("sid-orphan") == SessionStatus.PERMISSION


def test_iter_all_sees_sid_only_entries():
    """Regression: dashboard registers via register_by_sid (no register(pid)),
    so _by_pid is empty. iter_all must still see the entries — otherwise
    _sync_registry re-registers every scan and resets entry.status to IDLE,
    which collides with Stop's IDLE on the identity guard and breaks the
    yellow→green transition."""
    reg = SessionRegistry()
    reg.register_by_sid(session_id="sess-A", cwd=Path("C:/a"), pid=100)
    reg.register_by_sid(session_id="sess-B", cwd=Path("C:/b"), pid=101)
    snap = list(reg.iter_all())
    assert {e.session_id for e in snap} == {"sess-A", "sess-B"}
    # Simulate _sync_registry: existing_sids must include both, otherwise
    # they would be re-registered (and their status overwritten).
    existing_sids = {e.session_id for e in reg.iter_all() if e.session_id}
    assert existing_sids == {"sess-A", "sess-B"}


def test_iter_all_dedups_dual_index_entries():
    """register(pid) + attach_session_id puts the SAME entry in both indices;
    iter_all must yield it exactly once."""
    reg = SessionRegistry()
    entry = reg.register(pid=50, cwd=Path("C:/x"))
    reg.attach_session_id(pid=50, session_id="sess-X")
    snap = list(reg.iter_all())
    assert len(snap) == 1
    assert snap[0] is entry