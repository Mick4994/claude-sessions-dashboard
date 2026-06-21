from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path

_SKIP_DIR_NAMES = {"tool-results"}
# Encoded names of project dirs that are plugin-internal (not user sessions).
# claude-mem observer writes JSONLs here — these must not appear as user sessions.
_SKIP_DIR_SUBSTRINGS = ("claude-mem-observer-sessions",)


def discover_jsonl_files(projects_dir: Path) -> Iterator[Path]:
    """Yield all *.jsonl files directly under projects_dir/<*>/*.jsonl.
    Skips CC's per-session tool-results/ subdirs and plugin-internal project dirs.
    """
    if not projects_dir.exists():
        return
    for project_dir in projects_dir.iterdir():
        if not project_dir.is_dir():
            continue
        if any(pat in project_dir.name for pat in _SKIP_DIR_SUBSTRINGS):
            continue
        for entry in project_dir.iterdir():
            if entry.is_file() and entry.suffix == ".jsonl":
                yield entry


def _parse_iso_timestamp(ts: str) -> float | None:
    try:
        if ts.endswith("Z"):
            ts = ts[:-1] + "+00:00"
        return datetime.fromisoformat(ts).timestamp()
    except (ValueError, AttributeError):
        return None


def last_entry_timestamp(jsonl_path: Path) -> float | None:
    """Return the `timestamp` field of the last non-empty line, parsed as ISO-8601.
    Reads only the tail (last 64KB) to stay fast on large files.
    """
    try:
        size = jsonl_path.stat().st_size
        with open(jsonl_path, "rb") as f:
            if size > 65536:
                f.seek(size - 65536)
                f.readline()  # discard partial first line
            last = None
            for line in f:
                line = line.strip()
                if line:
                    last = line
        if last is None:
            return None
        obj = json.loads(last)
        ts = obj.get("timestamp")
        if not isinstance(ts, str):
            return None
        return _parse_iso_timestamp(ts)
    except (OSError, ValueError, json.JSONDecodeError):
        return None
