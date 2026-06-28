"""SessionRegistry: pure-Python singleton mapping PID → session entry.

Callbacks (on_added / on_removed / on_status_changed) are plain lists of callables.
No Qt dependency — the UI layer wraps this with Qt Signals via an adapter.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path

from .status import SessionStatus

Callback = Callable[["SessionEntry"], None]
StatusCallback = Callable[["SessionEntry", SessionStatus], None]


@dataclass
class SessionEntry:
    pid: int
    cwd: Path
    session_id: str | None = None
    jsonl_path: Path | None = None
    status: SessionStatus = SessionStatus.IDLE


@dataclass
class _Callbacks:
    added: list[Callback] = field(default_factory=list)
    removed: list[Callback] = field(default_factory=list)
    status_changed: list[StatusCallback] = field(default_factory=list)


class SessionRegistry:
    """Thread-safe singleton mapping PID → SessionEntry with observer callbacks."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._by_pid: dict[int, SessionEntry] = {}
        self._by_sid: dict[str, SessionEntry] = {}
        self._pending: dict[str, SessionStatus] = {}      # hook 早于 register 时排队
        self._callbacks = _Callbacks()

    # -- callbacks -------------------------------------------------------

    def on_added(self, fn: Callback) -> None:
        self._callbacks.added.append(fn)

    def on_removed(self, fn: Callback) -> None:
        self._callbacks.removed.append(fn)

    def on_status_changed(self, fn: StatusCallback) -> None:
        self._callbacks.status_changed.append(fn)

    # -- mutations -------------------------------------------------------

    def register(self, pid: int, cwd: Path, jsonl_path: Path | None = None) -> SessionEntry:
        entry = SessionEntry(pid=pid, cwd=cwd, jsonl_path=jsonl_path)
        with self._lock:
            self._by_pid[pid] = entry
        for cb in self._callbacks.added:
            cb(entry)
        return entry

    def unregister(self, pid: int) -> SessionEntry | None:
        with self._lock:
            entry = self._by_pid.pop(pid, None)
            if entry is None:
                return None
            if entry.session_id:
                self._by_sid.pop(entry.session_id, None)
        for cb in self._callbacks.removed:
            cb(entry)
        return entry

    def attach_session_id(self, pid: int, session_id: str) -> None:
        with self._lock:
            entry = self._by_pid.get(pid)
            if entry is None:
                return
            entry.session_id = session_id
            self._by_sid[session_id] = entry

    def set_status(self, pid: int, status: SessionStatus) -> None:
        with self._lock:
            entry = self._by_pid.get(pid)
            if entry is None:
                return
            old = entry.status
            entry.status = status
        if old is not status:
            for cb in self._callbacks.status_changed:
                cb(entry, status)

    # -- mutations (sid-first, no PID required) -------------------------

    def register_by_sid(
        self, session_id: str, cwd: Path, *, pid: int = 0, jsonl_path: Path | None = None
    ) -> SessionEntry:
        entry = SessionEntry(pid=pid, cwd=cwd, session_id=session_id, jsonl_path=jsonl_path)
        pending: SessionStatus | None = None
        with self._lock:
            self._by_sid[session_id] = entry
            pending = self._pending.pop(session_id, None)
        if pending is not None:
            old = entry.status
            entry.status = pending
            if old is not pending:
                for cb in self._callbacks.status_changed:
                    cb(entry, pending)
        for cb in self._callbacks.added:
            cb(entry)
        return entry

    def unregister_by_sid(self, session_id: str) -> SessionEntry | None:
        with self._lock:
            entry = self._by_sid.pop(session_id, None)
        if entry:
            for cb in self._callbacks.removed:
                cb(entry)
        return entry

    def set_status_by_sid(self, session_id: str, status: SessionStatus) -> None:
        with self._lock:
            entry = self._by_sid.get(session_id)
            if entry is None:
                self._pending[session_id] = status
                return
            old = entry.status
            entry.status = status
        if old is not status:
            for cb in self._callbacks.status_changed:
                cb(entry, status)

    def unregister_by_cwd(self, cwd: str) -> list[SessionEntry]:
        removed: list[SessionEntry] = []
        normalized = str(Path(cwd))
        with self._lock:
            sids = [sid for sid, e in self._by_sid.items() if str(e.cwd) == normalized]
            for sid in sids:
                removed.append(self._by_sid.pop(sid))
        for e in removed:
            for cb in self._callbacks.removed:
                cb(e)
        return removed

    # -- queries ---------------------------------------------------------

    def get(self, pid: int) -> SessionEntry | None:
        with self._lock:
            return self._by_pid.get(pid)

    def get_by_sid(self, session_id: str) -> SessionEntry | None:
        with self._lock:
            return self._by_sid.get(session_id)

    def find_pid_by_sid(self, session_id: str) -> int | None:
        entry = self.get_by_sid(session_id)
        return entry.pid if entry else None

    def has(self, pid: int) -> bool:
        with self._lock:
            return pid in self._by_pid

    def iter_all(self) -> Iterator[SessionEntry]:
        # 一个 SessionEntry 可能同时挂在两个 index 里（register + attach_session_id
        # 会让同一对象进 _by_pid 和 _by_sid）；但 dashboard 主要走 register_by_sid
        # 只写 _by_sid。两条路径都要看到，否则 _sync_registry 会每个扫描周期重复
        # 注册并把 entry.status 重置回默认值，进而让 Stop 的 IDLE 跟 reset 后的 IDLE
        # 撞上 identity guard，callback 不触发、UI 永远卡黄。
        with self._lock:
            seen: set[int] = set()
            result: list[SessionEntry] = []
            for e in self._by_pid.values():
                if id(e) not in seen:
                    seen.add(id(e))
                    result.append(e)
            for e in self._by_sid.values():
                if id(e) not in seen:
                    seen.add(id(e))
                    result.append(e)
        yield from result

    def __len__(self) -> int:
        with self._lock:
            return len(self._by_pid)
