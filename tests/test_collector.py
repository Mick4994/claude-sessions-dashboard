"""Tests for SessionCollector — background poller that parses JSONL → Session list."""

from __future__ import annotations

import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path

from src.collector.collector import SessionCollector


def _touch(path: Path, entries: list[dict], *, mtime: float | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e) + "\n")
    if mtime is not None:
        os.utime(path, (mtime, mtime))


def _recent_ts() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _collector(tmp_path, monkeypatch, **kwargs) -> SessionCollector:
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path))
    defaults = {
        "poll_interval_ms": 100,
        "recent_seconds": 600,
        "stale_after_minutes": 30,
        "max_context_tokens": 200_000,
    }
    defaults.update(kwargs)
    return SessionCollector(**defaults)


def test_collector_scans_and_yields_active_sessions(tmp_path, monkeypatch, qapp):
    proj = tmp_path / "projects" / "p1"
    _touch(
        proj / "s1.jsonl",
        [
            {"type": "last-prompt", "sessionId": "s1"},
            {"type": "ai-title", "aiTitle": "Test session", "sessionId": "s1"},
            {
                "type": "user",
                "message": {"role": "user", "content": "hi"},
                "timestamp": _recent_ts(),
                "sessionId": "s1",
            },
        ],
    )
    c = _collector(tmp_path, monkeypatch, recent_seconds=600)
    c.scan_once()
    sessions = c.current_sessions()
    assert len(sessions) == 1
    assert sessions[0].id == "s1"
    assert sessions[0].title == "Test session"


def test_collector_filters_stale_by_mtime(tmp_path, monkeypatch, qapp):
    proj = tmp_path / "projects" / "p1"
    old = time.time() - 7200
    _touch(proj / "s1.jsonl", [{"type": "last-prompt", "sessionId": "s1"}], mtime=old)
    c = _collector(tmp_path, monkeypatch, stale_after_minutes=30)
    c.scan_once()
    assert c.current_sessions() == []


def test_collector_removes_disappeared_session(tmp_path, monkeypatch, qapp):
    proj = tmp_path / "projects" / "p1"
    _touch(
        proj / "s1.jsonl", [{"type": "last-prompt", "sessionId": "s1", "timestamp": _recent_ts()}]
    )
    c = _collector(tmp_path, monkeypatch, recent_seconds=600)
    c.scan_once()
    assert len(c.current_sessions()) == 1
    (proj / "s1.jsonl").unlink()
    c.scan_once()
    assert c.current_sessions() == []


def test_collector_emits_signal(tmp_path, monkeypatch, qapp):
    proj = tmp_path / "projects" / "p1"
    _touch(
        proj / "s1.jsonl", [{"type": "last-prompt", "sessionId": "s1", "timestamp": _recent_ts()}]
    )
    c = _collector(tmp_path, monkeypatch, recent_seconds=600)
    received = []

    def on_changed(s):
        received.append(s)

    c.sessionsChanged.connect(on_changed)  # noqa: N815
    c.scan_once()
    assert len(received) == 1
    assert received[0][0].id == "s1"
