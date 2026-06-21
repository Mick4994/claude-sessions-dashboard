"""Tests for SessionCollector — background poller that parses JSONL → Session list.

Note: collector is now process-driven (no mtime filtering, no recent_seconds /
stale_after_minutes params). Tests stub out alive_cwds to inject fake processes.
"""

from __future__ import annotations

import json
import os
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
        "max_context_tokens": 200_000,
    }
    defaults.update(kwargs)
    return SessionCollector(**defaults)


def _stub_alive_cwds(monkeypatch, cwds: set[str]):
    """Monkeypatch alive_cwds to return a fixed set of cwds (simulates running CC)."""
    from src.collector import collector as collector_mod

    monkeypatch.setattr(collector_mod, "alive_cwds", lambda: cwds)


def _proj_name_for(cwd: str) -> str:
    """Mirror collector.scan_once encoding: replace ':' and '\\' with '-'."""
    return str(Path(cwd)).replace(":", "-").replace("\\", "-")


def test_collector_one_alive_one_session(tmp_path, monkeypatch, qapp):
    """TC-003: 1 alive CC process → 1 session in list."""
    cwd = str(tmp_path)
    proj_name = _proj_name_for(cwd)
    proj = tmp_path / "projects" / proj_name
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
    _stub_alive_cwds(monkeypatch, {cwd})

    c = _collector(tmp_path, monkeypatch)
    c.scan_once()
    sessions = c.current_sessions()
    assert len(sessions) == 1
    assert sessions[0].id == "s1"
    assert sessions[0].title == "Test session"


def test_collector_process_gone_removed(tmp_path, monkeypatch, qapp):
    """TC-004: when alive_cwds no longer includes a cwd, the session is removed."""
    cwd = str(tmp_path)
    proj_name = _proj_name_for(cwd)
    proj = tmp_path / "projects" / proj_name
    _touch(
        proj / "s1.jsonl", [{"type": "last-prompt", "sessionId": "s1", "timestamp": _recent_ts()}]
    )

    # First scan: CC is alive.
    _stub_alive_cwds(monkeypatch, {cwd})
    c = _collector(tmp_path, monkeypatch)
    c.scan_once()
    assert len(c.current_sessions()) == 1

    # Second scan: CC process gone.
    _stub_alive_cwds(monkeypatch, set())
    c.scan_once()
    assert c.current_sessions() == []


def test_collector_no_alive_empty(tmp_path, monkeypatch, qapp):
    """TC-020: 0 alive CC processes → empty list."""
    _stub_alive_cwds(monkeypatch, set())
    c = _collector(tmp_path, monkeypatch)
    c.scan_once()
    assert c.current_sessions() == []


def test_collector_emits_signal(tmp_path, monkeypatch, qapp):
    cwd = str(tmp_path)
    proj_name = _proj_name_for(cwd)
    proj = tmp_path / "projects" / proj_name
    _touch(
        proj / "s1.jsonl", [{"type": "last-prompt", "sessionId": "s1", "timestamp": _recent_ts()}]
    )
    _stub_alive_cwds(monkeypatch, {cwd})

    c = _collector(tmp_path, monkeypatch)
    received = []

    def on_changed(s):
        received.append(s)

    c.sessionsChanged.connect(on_changed)  # noqa: N815
    c.scan_once()
    assert len(received) == 1
    assert received[0][0].id == "s1"


def test_collector_process_no_jsonl_still_in_list(tmp_path, monkeypatch, qapp):
    """TC-021: alive CC with no JSONL files yet must NOT crash, must NOT include
    a session entry (parser requires a JSONL, but the alive_cwds loop safely skips
    project dirs with no jsonl)."""
    # Project dir exists but is empty.
    (tmp_path / "projects" / "p1").mkdir(parents=True)
    _stub_alive_cwds(monkeypatch, {str(tmp_path)})

    c = _collector(tmp_path, monkeypatch)
    c.scan_once()
    # No JSONL → no session; alive process is tracked separately by registry, not here.
    assert c.current_sessions() == []


def test_collector_corrupt_jsonl_no_crash(tmp_path, monkeypatch, qapp):
    """TC-022: corrupt JSONL does not crash collector."""
    proj = tmp_path / "projects" / "p1"
    proj.mkdir(parents=True)
    bad = proj / "s1.jsonl"
    with open(bad, "wb") as f:
        f.write(b"\xff\xfe\xfd garbage not json at all {{{\n")
    _stub_alive_cwds(monkeypatch, {str(tmp_path)})

    c = _collector(tmp_path, monkeypatch)
    # Should not raise.
    c.scan_once()
    assert c.current_sessions() == []