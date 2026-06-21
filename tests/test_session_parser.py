"""Tests for session_parser — title, context %, subtitle, status, and full metadata."""

from __future__ import annotations

import json
import time
from datetime import UTC

from src.collector.models import SessionStatus
from src.collector.session_parser import (
    _determine_status,
    _parse_context_pct,
    _parse_subtitle,
    _parse_title,
    parse_session_metadata,
)


def _write_jsonl(path, entries):
    with open(path, "w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e) + "\n")


def _assistant_tool_use(name, input_, *, tid="t1"):
    return {
        "type": "assistant",
        "message": {
            "role": "assistant",
            "content": [{"type": "tool_use", "id": tid, "name": name, "input": input_}],
        },
    }


def _iso(epoch):
    from datetime import datetime

    return datetime.fromtimestamp(epoch, tz=UTC).isoformat().replace("+00:00", "Z")


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
    assert title == "x" * 32 + "\u2026"


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


# ---- Status ---------------------------------------------------------


def test_status_working_recent_assistant():
    now = time.time()
    entries = [{"type": "assistant", "timestamp": _iso(now - 2)}]
    assert _determine_status(entries, now=now, recent_seconds=60) == SessionStatus.WORKING


def test_status_idle_assistant_end_turn_recent():
    now = time.time()
    entries = [{"type": "assistant", "stop_reason": "end_turn", "timestamp": _iso(now - 10)}]
    assert _determine_status(entries, now=now, recent_seconds=60) == SessionStatus.IDLE


def test_status_permission_tool_use_awaiting_result():
    now = time.time()
    entries = [
        {
            "type": "assistant",
            "stop_reason": "tool_use",
            "timestamp": _iso(now - 3),
            "message": {
                "content": [
                    {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": "x"}}
                ]
            },
        }
    ]
    assert _determine_status(entries, now=now, recent_seconds=60) == SessionStatus.PERMISSION


def test_status_idle_tool_use_with_result_then_stale_assistant():
    """Once all tools have results and the next assistant message is older than recency,
    the session is IDLE — but only if the assistant hasn't continued within the window."""
    now = time.time()
    entries = [
        {
            "type": "assistant",
            "stop_reason": "tool_use",
            "timestamp": _iso(now - 120),
            "message": {
                "content": [
                    {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": "x"}}
                ]
            },
        },
        {
            "type": "user",
            "timestamp": _iso(now - 30),
            "message": {"content": [{"type": "tool_result", "tool_use_id": "t1", "content": "ok"}]},
        },
    ]
    # The latest entry is a tool_result within recency → agent is processing it → WORKING
    assert _determine_status(entries, now=now, recent_seconds=60) == SessionStatus.WORKING


def test_status_working_recent_tool_result_with_old_assistant():
    """When the most recent entry is a tool_result (even if assistant is older),
    the agent is currently processing the tool output → WORKING."""
    now = time.time()
    entries = [
        {
            "type": "assistant",
            "stop_reason": "tool_use",
            "timestamp": _iso(now - 90),
            "message": {
                "content": [
                    {"type": "tool_use", "id": "t1", "name": "Read", "input": {"path": "x"}}
                ]
            },
        },
        {
            "type": "user",
            "timestamp": _iso(now - 5),
            "message": {"content": [{"type": "tool_result", "tool_use_id": "t1", "content": "ok"}]},
        },
    ]
    assert _determine_status(entries, now=now, recent_seconds=60) == SessionStatus.WORKING


def test_status_stale_old_tool_result():
    """Old tool_result (180s ago, > recent_seconds 60s) → STALE.
    The collector converts STALE → IDLE inside its visible window, but the
    parser's job is to flag STALE truthfully based on recency alone."""
    now = time.time()
    entries = [
        {
            "type": "assistant",
            "stop_reason": "tool_use",
            "timestamp": _iso(now - 200),
            "message": {
                "content": [
                    {"type": "tool_use", "id": "t1", "name": "Read", "input": {"path": "x"}}
                ]
            },
        },
        {
            "type": "user",
            "timestamp": _iso(now - 180),
            "message": {"content": [{"type": "tool_result", "tool_use_id": "t1", "content": "ok"}]},
        },
    ]
    assert _determine_status(entries, now=now, recent_seconds=60) == SessionStatus.STALE


def test_status_idle_user_prompt_recent():
    now = time.time()
    entries = [{"type": "user", "timestamp": _iso(now - 2)}]
    assert _determine_status(entries, now=now, recent_seconds=60) == SessionStatus.IDLE


def test_status_permission_risky_tool_in_default_mode():
    """Pending Bash in default mode without result → PERMISSION."""
    now = time.time()
    entries = [
        {"type": "permission-mode", "permissionMode": "default"},
        {
            "type": "assistant",
            "stop_reason": "tool_use",
            "timestamp": _iso(now - 3),
            "message": {
                "content": [
                    {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": "rm"}}
                ]
            },
        },
    ]
    assert _determine_status(entries, now=now, recent_seconds=60) == SessionStatus.PERMISSION


def test_status_working_risky_tool_in_auto_mode():
    """Pending Bash in auto mode without result → WORKING (auto-executes)."""
    now = time.time()
    entries = [
        {"type": "permission-mode", "permissionMode": "auto"},
        {
            "type": "assistant",
            "stop_reason": "tool_use",
            "timestamp": _iso(now - 3),
            "message": {
                "content": [
                    {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": "ls"}}
                ]
            },
        },
    ]
    assert _determine_status(entries, now=now, recent_seconds=60) == SessionStatus.WORKING


def test_status_working_safe_tool_in_default_mode():
    """Pending Read in default mode without result → WORKING (safe tool, no permission needed)."""
    now = time.time()
    entries = [
        {"type": "permission-mode", "permissionMode": "default"},
        {
            "type": "assistant",
            "stop_reason": "tool_use",
            "timestamp": _iso(now - 3),
            "message": {
                "content": [
                    {"type": "tool_use", "id": "t1", "name": "Read", "input": {"path": "x"}}
                ]
            },
        },
    ]
    assert _determine_status(entries, now=now, recent_seconds=60) == SessionStatus.WORKING


def test_status_stale_no_recent_activity():
    now = time.time()
    entries = [{"type": "assistant", "timestamp": _iso(now - 300)}]
    assert _determine_status(entries, now=now, recent_seconds=60) == SessionStatus.STALE


# ---- Full metadata --------------------------------------------------


def test_parse_session_metadata_full(tmp_path):
    p = tmp_path / "s.jsonl"
    now = time.time()
    ts0 = _iso(now - 5)
    ts1 = _iso(now - 4)
    ts2 = _iso(now - 3)
    entries = [
        {"type": "last-prompt", "sessionId": "s", "timestamp": ts0},
        {"type": "ai-title", "aiTitle": "Build dashboard", "sessionId": "s"},
        {
            "type": "user",
            "message": {"role": "user", "content": "build"},
            "timestamp": ts1,
            "sessionId": "s",
        },
        {
            "type": "assistant",
            "message": {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "t1",
                        "name": "Edit",
                        "input": {"file_path": "/repo/src/main.py"},
                    }
                ],
                "usage": {
                    "input_tokens": 5000,
                    "cache_creation_input_tokens": 0,
                    "cache_read_input_tokens": 30000,
                    "output_tokens": 200,
                },
            },
            "stop_reason": "tool_use",
            "timestamp": ts2,
            "sessionId": "s",
            "cwd": "/repo",
        },
    ]
    p.write_text("\n".join(json.dumps(e) for e in entries) + "\n")
    s = parse_session_metadata(
        jsonl_path=p, session_id="s", cwd="/repo", max_tokens=200_000, title_max=32, subtitle_max=40
    )
    assert s.title == "Build dashboard"
    assert s.subtitle == "Edit: main.py"
    assert s.context_pct == 17.5
    assert s.status == SessionStatus.PERMISSION


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
