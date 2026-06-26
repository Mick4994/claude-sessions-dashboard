"""Background poller: scans running CC processes, parses JSONL metadata.

Show/hide is driven entirely by running CC processes, not file timestamps.
JSONL is read ONLY for display metadata (title / context% / subtitle).
Status (color) is driven by SessionRegistry updates from the hook server.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal

from .process_monitor import alive_sessions
from .session_parser import parse_session_metadata


class SessionCollector(QObject):
    """Polls alive CC processes, parses JSONL metadata, emits session list updates."""

    sessionsChanged = Signal(list)  # list[Session]  # noqa: N815

    def __init__(
        self,
        *,
        poll_interval_ms: int = 2000,
        max_context_tokens: int = 1_000_000,
        title_truncate_chars: int = 32,
        subtitle_truncate_chars: int = 40,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._poll_interval_ms = poll_interval_ms
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
        seen_ids: set[str] = set()

        # Group alive sessions by encoded CWD to share JSONL candidates.
        by_cwd: dict[str, list[dict]] = {}
        for s in alive_sessions():
            encoded = str(Path(s["cwd"])).replace(":", "-").replace("\\", "-")
            by_cwd.setdefault(encoded, []).append(s)

        for proj_name, entries in by_cwd.items():
            proj_dir = self.projects_dir / proj_name
            if not proj_dir.is_dir():
                continue

            # Collect all JSONLs sorted by mtime descending.
            candidates: list[Path] = []
            for entry in proj_dir.iterdir():
                if entry.is_file() and entry.suffix == ".jsonl":
                    candidates.append(entry)
            candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)

            # Assign the Nth most-recent JSONL to the Nth CC in this CWD.
            for idx, sess_info in enumerate(entries):
                if idx >= len(candidates):
                    break
                jsonl = candidates[idx]

                try:
                    session = parse_session_metadata(
                        jsonl_path=jsonl,
                        session_id=jsonl.stem,
                        cwd=sess_info["cwd"],
                        pid=sess_info["pid"],
                        max_tokens=self._max_context_tokens,
                        title_max=self._title_truncate_chars,
                        subtitle_max=self._subtitle_truncate_chars,
                    )
                except Exception:
                    continue

                # Preserve status from previous scan — hooks may have updated it.
                if session.id in self._sessions:
                    session.status = self._sessions[session.id].status

                seen_ids.add(session.id)
                self._sessions[session.id] = session

        removed = [k for k in self._sessions if k not in seen_ids]
        for k in removed:
            del self._sessions[k]

        if removed or self._sessions:
            self.sessionsChanged.emit(self.current_sessions())


# Re-export so UI imports still work.
from .models import Session  # noqa: E402,F401
