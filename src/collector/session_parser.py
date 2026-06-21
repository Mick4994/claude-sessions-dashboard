"""Parse Claude Code session JSONL files into Session dataclass."""

from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path

from .models import Session, SessionStatus

_TAIL_BYTES = 65536 * 2  # 128KB


def _truncate(s: str, max_chars: int) -> str:
    if len(s) <= max_chars:
        return s
    return s[:max_chars] + "…"


def _entry_ts(entry: dict) -> float | None:
    ts = entry.get("timestamp")
    if not isinstance(ts, str):
        return None
    try:
        if ts.endswith("Z"):
            ts = ts[:-1] + "+00:00"
        return datetime.fromisoformat(ts).timestamp()
    except ValueError:
        return None


def _read_jsonl_tail(path: Path) -> list[dict]:
    """Read last ~128KB of a JSONL file, parse each line as JSON."""
    try:
        size = path.stat().st_size
        with open(path, "rb") as f:
            if size > _TAIL_BYTES:
                f.seek(size - _TAIL_BYTES)
                f.readline()
            entries: list[dict] = []
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(obj, dict):
                    entries.append(obj)
        return entries
    except OSError:
        return []


def _first_user_text(entries: list[dict]) -> str | None:
    for e in entries:
        if e.get("type") != "user":
            continue
        msg = e.get("message") or {}
        if msg.get("role") != "user":
            continue
        content = msg.get("content")
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    return (block.get("text") or "").strip()
    return None


# ---- Title ----------------------------------------------------------------


def _parse_title(
    entries: list[dict],
    *,
    cwd: str = "",
    max_chars: int = 32,
) -> str:
    for e in entries:
        if e.get("type") == "ai-title" and e.get("aiTitle"):
            return e["aiTitle"]
    text = _first_user_text(entries)
    if text:
        return _truncate(text, max_chars)
    if cwd:
        return Path(cwd).name or cwd
    return ""


# ---- Context % -------------------------------------------------------------


def _parse_context_pct(entries: list[dict], *, max_tokens: int) -> float:
    last_usage: dict | None = None
    for e in entries:
        if e.get("type") != "assistant":
            continue
        msg = e.get("message") or {}
        usage = msg.get("usage")
        if isinstance(usage, dict):
            last_usage = usage
    if not last_usage:
        return 0.0
    tokens = (
        (last_usage.get("input_tokens") or 0)
        + (last_usage.get("cache_creation_input_tokens") or 0)
        + (last_usage.get("cache_read_input_tokens") or 0)
    )
    if max_tokens <= 0:
        return 0.0
    pct = round(tokens / max_tokens * 100, 1)
    return min(100.0, max(0.0, pct))


# ---- Subtitle --------------------------------------------------------------


def _tool_subtitle(name: str, input_: dict, max_chars: int) -> str:
    path_like = {"Read", "Write", "Edit", "MultiEdit", "NotebookEdit"}
    if name in path_like:
        fp = input_.get("file_path") or input_.get("notebook_path") or ""
        base = Path(fp).name if fp else ""
        return _truncate(f"{name}: {base}" if base else name, max_chars)
    if name == "Bash":
        cmd = (input_.get("command") or "").strip()
        return _truncate(f"Bash: {cmd}", max_chars)
    if name == "Grep":
        pat = (input_.get("pattern") or "").strip()
        return _truncate(f"Grep: {pat}" if pat else "Grep", max_chars)
    if name == "Glob":
        pat = (input_.get("pattern") or "").strip()
        return _truncate(f"Glob: {pat}" if pat else "Glob", max_chars)
    if name == "Agent":
        st = input_.get("subagent_type", "")
        desc = (input_.get("description") or "").strip()
        head = f"Agent: {st}"
        if desc:
            head += f": {desc}"
        return _truncate(head, max_chars)
    if name == "WebFetch":
        url = input_.get("url") or ""
        host = url.split("/")[2] if url.count("/") >= 2 else url
        return _truncate(f"WebFetch: {host}" if host else "WebFetch", max_chars)
    if name == "WebSearch":
        q = (input_.get("query") or "").strip()
        return _truncate(f"WebSearch: {q}" if q else "WebSearch", max_chars)
    if name == "TodoWrite":
        return "TodoWrite: task list update"
    if name == "AskUserQuestion":
        return "AskUserQuestion"
    if name == "EnterPlanMode":
        return "Plan: entering plan mode"
    return name


def _parse_subtitle(
    entries: list[dict],
    *,
    max_chars: int = 40,
    idle: bool = False,
) -> str:
    for e in reversed(entries):
        if e.get("type") != "assistant":
            continue
        msg = e.get("message") or {}
        content = msg.get("content") or []
        if not isinstance(content, list):
            continue
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                name = block.get("name") or "Tool"
                inp = block.get("input") or {}
                return _tool_subtitle(name, inp, max_chars)
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                txt = (block.get("text") or "").strip()
                if txt:
                    return _truncate(txt, max_chars)
        break
    for e in reversed(entries):
        if e.get("type") != "user":
            continue
        msg = e.get("message") or {}
        content = msg.get("content") or []
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "tool_result":
                    return _truncate("(done) tool", max_chars)
        elif isinstance(content, str) and content.strip():
            return _truncate(content.strip(), max_chars)
    if idle:
        return "Idle"
    return "Thinking…"


# ---- Status -----------------------------------------------------------------

# Tools that require user approval in default (non-auto) permission mode.
# Auto mode runs these without prompting, so they only count as WORKING there.
_PERMISSION_TOOLS = {"Bash", "Write", "Edit", "MultiEdit", "NotebookEdit", "WebFetch"}


def _gather_tool_use_ids(entries: list[dict]) -> set[str]:
    ids: set[str] = set()
    for e in entries:
        if e.get("type") != "assistant":
            continue
        content = (e.get("message") or {}).get("content") or []
        if not isinstance(content, list):
            continue
        for b in content:
            if isinstance(b, dict) and b.get("type") == "tool_use":
                tid = b.get("id")
                if tid:
                    ids.add(tid)
    return ids


def _gather_tool_result_ids(entries: list[dict]) -> set[str]:
    ids: set[str] = set()
    for e in entries:
        if e.get("type") != "user":
            continue
        content = (e.get("message") or {}).get("content") or []
        if not isinstance(content, list):
            continue
        for b in content:
            if isinstance(b, dict) and b.get("type") == "tool_result":
                tid = b.get("tool_use_id")
                if tid:
                    ids.add(tid)
    return ids


def _gather_pending_tool_names(entries: list[dict]) -> set[str]:
    """Names of tool_uses that don't yet have a tool_result."""
    use_ids = _gather_tool_use_ids(entries)
    res_ids = _gather_tool_result_ids(entries)
    pending_ids = use_ids - res_ids
    names: set[str] = set()
    for e in entries:
        if e.get("type") != "assistant":
            continue
        content = (e.get("message") or {}).get("content") or []
        if not isinstance(content, list):
            continue
        for b in content:
            if isinstance(b, dict) and b.get("type") == "tool_use":
                if b.get("id") in pending_ids:
                    name = b.get("name")
                    if isinstance(name, str):
                        names.add(name)
    return names


def _permission_mode(entries: list[dict]) -> str:
    """Return the session's permission mode ('auto' | 'default' | 'plan' | ...).
    Defaults to 'default' if the header entry is not in the read window — safer
    to assume permission may be needed than to silently drop PERMISSION."""
    for e in entries:
        if e.get("type") == "permission-mode":
            mode = e.get("permissionMode")
            if isinstance(mode, str):
                return mode
    return "default"


def _has_tool_result_recent(entries: list[dict]) -> bool:
    """True if the most recent user entry contains a tool_result block."""
    for e in reversed(entries):
        if e.get("type") == "user":
            content = (e.get("message") or {}).get("content") or []
            if isinstance(content, list):
                return any(
                    isinstance(b, dict) and b.get("type") == "tool_result"
                    for b in content
                )
            return False
    return False


def _determine_status(
    entries: list[dict],
    *,
    now: float,
    recent_seconds: int = 60,
) -> SessionStatus:
    if not entries:
        return SessionStatus.STALE

    last = entries[-1]
    last_ts = _entry_ts(last)
    if last_ts is None or (now - last_ts) > recent_seconds:
        return SessionStatus.STALE

    last_type = last.get("type")

    if last_type == "assistant":
        stop_reason = last.get("stop_reason")
        if stop_reason == "tool_use":
            pending = _gather_pending_tool_names(entries)
            if pending:
                # Auto mode auto-executes risky tools — never PERMISSION there.
                # Default (or unknown) mode: risky tool pending = permission requested.
                perm_mode = _permission_mode(entries)
                if perm_mode != "auto" and pending & _PERMISSION_TOOLS:
                    return SessionStatus.PERMISSION
                return SessionStatus.WORKING
            # Tool use + result already in tail → agent waiting for next prompt.
            return SessionStatus.IDLE
        if stop_reason == "end_turn":
            return SessionStatus.IDLE
        # No stop_reason yet → assistant is still streaming.
        return SessionStatus.WORKING

    if last_type == "user":
        # tool_result = a tool just completed; agent is processing the output → WORKING.
        # Plain user text = waiting for agent to pick it up → IDLE.
        if _has_tool_result_recent(entries):
            return SessionStatus.WORKING
        return SessionStatus.IDLE

    return SessionStatus.IDLE


# ---- Full metadata ----------------------------------------------------------


def _latest_model(entries: list[dict]) -> str:
    for e in reversed(entries):
        if e.get("type") == "assistant":
            m = (e.get("message") or {}).get("model")
            if m:
                return m
    return ""


def _latest_cwd(entries: list[dict], fallback: str = "") -> str:
    for e in reversed(entries):
        c = e.get("cwd")
        if c:
            return c
    return fallback


def parse_session_metadata(
    *,
    jsonl_path: Path,
    session_id: str,
    cwd: str,
    max_tokens: int,
    title_max: int,
    subtitle_max: int,
    recent_seconds: int = 60,
) -> Session:
    """Parse tail of a JSONL file into a Session dataclass."""
    entries = _read_jsonl_tail(jsonl_path)
    actual_cwd = _latest_cwd(entries, cwd)
    title = _parse_title(entries, cwd=actual_cwd, max_chars=title_max)
    subtitle = _parse_subtitle(entries, max_chars=subtitle_max, idle=False)
    pct = _parse_context_pct(entries, max_tokens=max_tokens)
    model = _latest_model(entries)
    status = _determine_status(entries, now=time.time(), recent_seconds=recent_seconds)
    last_ts = 0.0
    for e in reversed(entries):
        ts = _entry_ts(e)
        if ts is not None:
            last_ts = ts
            break
    return Session(
        id=session_id,
        jsonl_path=str(jsonl_path),
        cwd=actual_cwd,
        title=title,
        subtitle=subtitle,
        context_pct=pct,
        model=model,
        status=status,
        last_activity_ts=last_ts,
    )
