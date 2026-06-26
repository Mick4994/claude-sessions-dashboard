"""Tests for session_parser — title, context %, subtitle, and full metadata.

NOTE: _determine_status tests removed (function deleted in Phase 3 refactor).
Status is now driven by SessionRegistry updates from CC hooks.
"""

from __future__ import annotations

import json

from src.collector.models import SessionStatus
from src.collector.session_parser import (
    _parse_context_pct,
    _parse_subtitle,
    _parse_title,
    parse_session_metadata,
)


def _write_jsonl(path, entries):
    with open(path, "w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e) + "\n")


# ---- Title ----------------------------------------------------------


def test_parse_title_uses_ai_title():
    entries = [
        {"type": "last-prompt", "sessionId": "s"},
        {"type": "ai-title", "aiTitle": "Search for things", "sessionId": "s"},
        {"type": "user", "message": {"role": "user", "content": "prompt"}, "sessionId": "s"},
    ]
    assert _parse_title(entries) == "Search for things"


def test_parse_title_falls_back_to_first_user_prompt_truncated():
    long = "x" * 100
    entries = [
        {"type": "user", "message": {"role": "user", "content": long}, "sessionId": "s"},
    ]
    title = _parse_title(entries, max_chars=32)
    assert title == "x" * 32 + "…"


def test_parse_title_falls_back_to_cwd_basename():
    entries = []
    title = _parse_title(entries, cwd="C:/Users/me/my-project")
    assert title == "my-project"


def test_parse_title_priority_ai_title_over_user_prompt():
    entries = [
        {"type": "user", "message": {"role": "user", "content": "first prompt"}, "sessionId": "s"},
        {"type": "ai-title", "aiTitle": "Better Title", "sessionId": "s"},
    ]
    assert _parse_title(entries) == "Better Title"


# ---- Context % ------------------------------------------------------


def test_context_pct_basic():
    e = {
        "type": "assistant",
        "message": {
            "usage": {
                "input_tokens": 50000,
                "cache_creation_input_tokens": 0,
                "cache_read_input_tokens": 50000,
                "output_tokens": 200,
            }
        },
    }
    assert _parse_context_pct([e], max_tokens=200_000) == 50.0


def test_context_pct_uses_last_assistant_turn_only():
    entries = [
        {
            "type": "assistant",
            "message": {
                "usage": {
                    "input_tokens": 1000,
                    "cache_creation_input_tokens": 0,
                    "cache_read_input_tokens": 0,
                    "output_tokens": 10,
                }
            },
        },
        {
            "type": "assistant",
            "message": {
                "usage": {
                    "input_tokens": 80000,
                    "cache_creation_input_tokens": 0,
                    "cache_read_input_tokens": 0,
                    "output_tokens": 10,
                }
            },
        },
    ]
    assert _parse_context_pct(entries, max_tokens=200_000) == 40.0


def test_context_pct_clamps_100():
    e = {
        "type": "assistant",
        "message": {
            "usage": {
                "input_tokens": 300_000,
                "cache_creation_input_tokens": 0,
                "cache_read_input_tokens": 0,
                "output_tokens": 0,
            }
        },
    }
    assert _parse_context_pct([e], max_tokens=200_000) == 100.0


def test_context_pct_no_assistant_returns_0():
    assert _parse_context_pct([], max_tokens=200_000) == 0.0
    assert (
        _parse_context_pct(
            [{"type": "user", "message": {"role": "user", "content": "hi"}}], max_tokens=200_000
        )
        == 0.0
    )


# ---- Subtitle -------------------------------------------------------


def _assistant_tool_use(name: str, input_: dict, *, tid: str = "t1") -> dict:
    return {
        "type": "assistant",
        "message": {
            "role": "assistant",
            "content": [{"type": "tool_use", "id": tid, "name": name, "input": input_}],
        },
    }


def test_subtitle_edit_shows_filename():
    e = _assistant_tool_use("Edit", {"file_path": "/repo/src/claude_dashboard.py"})
    assert _parse_subtitle([e], max_chars=40) == "Edit: claude_dashboard.py"


def test_subtitle_bash_truncates_command():
    e = _assistant_tool_use(
        "Bash",
        {"command": "pip install pyside6 pytest pyinstaller --extra-index-url https://example.com"},
    )
    sub = _parse_subtitle([e], max_chars=40)
    assert sub.startswith("Bash: pip install pyside6")
    assert len(sub) <= 41


def test_subtitle_grep_shows_pattern():
    e = _assistant_tool_use("Grep", {"pattern": "TODO"})
    assert _parse_subtitle([e], max_chars=40) == "Grep: TODO"


def test_subtitle_agent_shows_subagent_and_desc():
    e = _assistant_tool_use("Agent", {"subagent_type": "Explore", "description": "Find auth code"})
    assert _parse_subtitle([e], max_chars=40) == "Agent: Explore: Find auth code"


def test_subtitle_uses_first_tool_use_of_last_assistant():
    entries = [
        _assistant_tool_use("Read", {"file_path": "/a.py"}, tid="t1"),
        _assistant_tool_use("Edit", {"file_path": "/b.py"}, tid="t2"),
    ]
    assert _parse_subtitle(entries, max_chars=40) == "Edit: b.py"


def test_subtitle_fallback_to_assistant_text():
    e = {
        "type": "assistant",
        "message": {
            "role": "assistant",
            "content": [{"type": "text", "text": "Let me think carefully."}],
        },
    }
    sub = _parse_subtitle([e], max_chars=40)
    assert "Let me think" in sub


def test_subtitle_fallback_idle_no_tool():
    assert _parse_subtitle([], max_chars=40, idle=True) == "Idle"


# ---- Full metadata --------------------------------------------------


def test_parse_session_metadata_status_defaults_to_idle(tmp_path):
    """TC-008: status must NOT be inferred from JSONL — always defaults to IDLE
    so the registry owns the only path to status changes. (UNKNOWN removed —
    IDLE is the natural "no hook yet" state, shown as green.)"""
    p = tmp_path / "s.jsonl"
    entries = [
        {"type": "ai-title", "aiTitle": "T", "sessionId": "s"},
        # Even with a recent permission-mode + pending tool_use, parser must NOT
        # flip status — the registry is the sole source of truth.
        {"type": "permission-mode", "permissionMode": "default"},
        _assistant_tool_use("Bash", {"command": "rm -rf /"}),
    ]
    _write_jsonl(p, entries)
    s = parse_session_metadata(
        jsonl_path=p, session_id="s", cwd="/repo", max_tokens=200_000, title_max=32, subtitle_max=40
    )
    assert s.status == SessionStatus.IDLE


def test_parse_session_metadata_no_recent_seconds_param(tmp_path):
    """TC-008: parse_session_metadata signature must not accept recent_seconds
    or stale_after_minutes (they were removed in Phase 3)."""
    p = tmp_path / "s.jsonl"
    entries = [{"type": "ai-title", "aiTitle": "X", "sessionId": "s"}]
    _write_jsonl(p, entries)
    import inspect

    sig = inspect.signature(parse_session_metadata)
    assert "recent_seconds" not in sig.parameters
    assert "stale_after_minutes" not in sig.parameters
    # Still parses successfully
    s = parse_session_metadata(
        jsonl_path=p, session_id="s", cwd="/repo", max_tokens=200_000, title_max=32, subtitle_max=40
    )
    assert s.title == "X"


def test_corrupt_jsonl_line_skipped_no_crash(tmp_path):
    """TC-022: a single bad JSONL line must not crash parsing."""
    p = tmp_path / "s.jsonl"
    # Mix good lines, blank lines, and a corrupt line.
    with open(p, "w", encoding="utf-8") as f:
        f.write(json.dumps({"type": "ai-title", "aiTitle": "Survivor", "sessionId": "s"}) + "\n")
        f.write("{not valid json\n")
        f.write("\n")
        f.write(json.dumps(_assistant_tool_use("Read", {"file_path": "/x.py"})) + "\n")
    s = parse_session_metadata(
        jsonl_path=p, session_id="s", cwd="/repo", max_tokens=200_000, title_max=32, subtitle_max=40
    )
    assert s.title == "Survivor"
    assert "Read" in s.subtitle


def test_parse_session_metadata_uses_tail_only(tmp_path):
    p = tmp_path / "s.jsonl"
    with open(p, "w", encoding="utf-8") as f:
        for i in range(200):
            f.write(json.dumps({"type": "noise", "i": i}) + "\n")
        f.write(json.dumps({"type": "ai-title", "aiTitle": "Real Title", "sessionId": "s"}) + "\n")
    s = parse_session_metadata(
        jsonl_path=p, session_id="s", cwd="x", max_tokens=200_000, title_max=32, subtitle_max=40
    )
    assert s.title == "Real Title"


# Helper for tests that build a single assistant tool_use entry.
# (kept here so existing imports work in both directions)
def _assistant_tool_use_default(*args, **kwargs):
    return _assistant_tool_use(*args, **kwargs)