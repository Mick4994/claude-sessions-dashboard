"""Background poller: scans JSONL files, parses metadata, emits session list.
Show/hide is driven by running CC processes, not file timestamps.
"""
from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal

from .models import Session
from .process_monitor import alive_cwds
from .session_parser import parse_session_metadata
from .session_scanner import discover_jsonl_files


class SessionCollector(QObject):
    """Polls ~/.claude/projects for active sessions, emits updates on a timer."""

    sessionsChanged = Signal(list)  # list[Session]  # noqa: N815

    def __init__(
        self,
        *,
        poll_interval_ms: int = 2000,
        recent_seconds: int = 60,
        hide_after_seconds: int = 86400,
        stale_after_minutes: int = 30,
        max_context_tokens: int = 1_000_000,
        title_truncate_chars: int = 32,
        subtitle_truncate_chars: int = 40,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._poll_interval_ms = poll_interval_ms
        self._recent_seconds = recent_seconds
        self._stale_after_minutes = stale_after_minutes
        self._max_context_tokens = max_context_tokens
        self._title_truncate_chars = title_truncate_chars
        self._subtitle_truncate_chars = subtitle_truncate_chars
        self._sessions: dict[str, Session] = {}
        self._timer: QTimer | None = None

    @property
    def projects_dir(self) -> Path:
        import os

        override = os.environ.get("CLAUDE_CONFIG_DIR")
        base = Path(override) if override else Path.home() / ".claude"
        return base / "projects"

    def start(self) -> None:
        if self._timer is None:
            self._timer = QTimer(self)
            self._timer.timeout.connect(self.scan_once)
        self._timer.start(self._poll_interval_ms)
        self.scan_once()

    def stop(self) -> None:
        if self._timer is not None:
            self._timer.stop()

    def current_sessions(self) -> list[Session]:
        return list(self._sessions.values())

    def scan_once(self) -> None:
        now = time.time()

        # Process-based: show sessions whose CWD has a running CC process
        running_cwds: set[str] = set()
        try:
            for c in alive_cwds():
                running_cwds.add(str(Path(c).resolve()))
        except Exception:
            pass

        # Grace period: sessions active in the last 5min that had a CC process
        grace_cutoff = now - max(300, self._recent_seconds)

        seen_ids: set[str] = set()

        for jsonl in discover_jsonl_files(self.projects_dir):
            sid = jsonl.stem
            try:
                session = parse_session_metadata(
                    jsonl_path=jsonl,
                    session_id=sid,
                    cwd=str(jsonl.parent),
                    max_tokens=self._max_context_tokens,
                    title_max=self._title_truncate_chars,
                    subtitle_max=self._subtitle_truncate_chars,
                    recent_seconds=self._recent_seconds,
                )
            except Exception:
                continue

            cwd_parts = str(Path(session.cwd).resolve())
            show = cwd_parts in running_cwds or session.last_activity_ts > grace_cutoff

            if not show:
                continue

            seen_ids.add(sid)
            self._sessions[sid] = session

        removed = [k for k in self._sessions if k not in seen_ids]
        for k in removed:
            del self._sessions[k]

        if removed or self._sessions:
            self.sessionsChanged.emit(self.current_sessions())
