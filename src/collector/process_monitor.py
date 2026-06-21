"""Enumerate running Claude Code processes on Windows."""
from __future__ import annotations

from pathlib import Path

# Real CC uses --permission-mode; claude-mem observer / hook subprocesses use stream-json IO.
_CC_OBSERVER_FLAGS = ("--input-format stream-json", "--output-format stream-json")
_CLAUDE_MEM_DIR = ".claude-mem"


def _is_cc_process(name: str, cmdline: list[str] | None, cwd: str | None) -> bool:
    """Return True only for real Claude Code (excludes claude-mem observer and friends)."""
    if not cmdline:
        return False
    name_lower = (name or "").lower()
    cmdline_str = " ".join(cmdline).lower()

    # Must look like Claude Code: claude.exe is the only process name CC ships.
    if name_lower != "claude.exe":
        return False

    # claude-mem observer and similar hook subprocesses use stream-json IO.
    if any(flag in cmdline_str for flag in _CC_OBSERVER_FLAGS):
        return False

    # claude-mem worker runs inside .claude-mem/ — never a real user session.
    if cwd and _CLAUDE_MEM_DIR in cwd:
        return False

    return True


def alive_sessions() -> list[dict]:
    """Return list of {pid, cwd} for every real CC process."""
    try:
        import psutil
    except ImportError:
        return []

    result: list[dict] = []
    for proc in psutil.process_iter(["pid", "name", "cmdline", "cwd"]):
        try:
            info = proc.info
            if not _is_cc_process(info.get("name") or "", info.get("cmdline"), info.get("cwd")):
                continue
            cwd = info.get("cwd")
            if cwd and Path(cwd).exists():
                result.append({"pid": info["pid"], "cwd": cwd})
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
    return result


def alive_cwds() -> set[str]:
    """Backward-compatible: return unique CWDs of real CC processes."""
    return {s["cwd"] for s in alive_sessions()}