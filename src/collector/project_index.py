"""CWD → project-directory-name reverse index built from JSONL file contents.

Instead of guessing Claude Code's opaque encoding of CWD → project directory
names (which replaces : \\ . _ and non-ASCII codepoints with hyphens), we read
the *actual* CWD from the ``cwd`` field inside each project's JSONL files and
build a reverse mapping.  This is robust against any future encoding changes.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

_TAIL_READ_BYTES = 8192  # scan last 8 KB of the most recent JSONL


class ProjectDirIndex:
    """Maps real CWDs to ``~/.claude/projects/<name>`` directory names.

    The index is lazily refreshed so we don't re-scan the filesystem on every
    poll tick.  Call ``refresh()`` periodically (every 30 s by default) and
    ``find_dir(cwd)`` to resolve a CWD to its project directory name.
    """

    def __init__(self, projects_dir: Path, refresh_interval_ms: int = 30_000) -> None:
        self._projects_dir = projects_dir
        self._refresh_interval_s = refresh_interval_ms / 1000.0
        self._cwd_to_dir: dict[str, str] = {}  # normalised cwd → dir name
        self._last_refresh = 0.0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def find_dir(self, cwd: str) -> str | None:
        """Return the project directory name for *cwd*, or *None*."""
        # 1. exact match
        if cwd in self._cwd_to_dir:
            return self._cwd_to_dir[cwd]

        # 2. case-insensitive match (Windows drive letters)
        cwd_lower = cwd.lower()
        for stored_cwd, proj_name in self._cwd_to_dir.items():
            if stored_cwd.lower() == cwd_lower:
                return proj_name

        return None

    def refresh(self) -> None:
        """Re-scan the projects directory (throttled by *refresh_interval_ms*)."""
        now = time.monotonic()
        if now - self._last_refresh < self._refresh_interval_s:
            return
        self._last_refresh = now

        if not self._projects_dir.is_dir():
            return

        for entry in self._projects_dir.iterdir():
            if not entry.is_dir():
                continue
            cwd = self._extract_cwd(entry)
            if cwd:
                self._cwd_to_dir[cwd] = entry.name

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_cwd(proj_dir: Path) -> str | None:
        """Read the ``cwd`` field from the tail of the most recent JSONL."""
        candidates = sorted(
            proj_dir.glob("*.jsonl"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if not candidates:
            return None

        try:
            with open(candidates[0], "r", encoding="utf-8", errors="replace") as fh:
                fh.seek(max(0, candidates[0].stat().st_size - _TAIL_READ_BYTES))
                tail = fh.read()
        except OSError:
            return None

        for line in reversed(tail.strip().split("\n")):
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            cwd = entry.get("cwd")
            if cwd and isinstance(cwd, str):
                return cwd

        return None