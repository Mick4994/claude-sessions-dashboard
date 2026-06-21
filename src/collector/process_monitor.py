"""Enumerate running Claude Code processes by scanning node.exe (and claude) on Windows."""
from __future__ import annotations

from pathlib import Path

_CC_SIGNATURES = ("claude-code", "@anthropic-ai/claude-code", "/claude", "\\claude")


def _is_cc_process(name: str, cmdline: str | None) -> bool:
    """Heuristic: process name or command line suggests Claude Code."""
    if cmdline is None:
        return False
    needle = cmdline.lower()
    for sig in _CC_SIGNATURES:
        if sig in needle:
            return True
    if name.lower() in ("claude.exe", "claude"):
        return True
    return False


def alive_cwds() -> set[str]:
    """Return the set of working directories for currently running CC processes.
    Uses psutil on all platforms; falls back to an empty set on import failure.
    """
    try:
        import psutil
    except ImportError:
        return set()

    result: set[str] = set()
    for proc in psutil.process_iter(["name", "cmdline", "cwd"]):
        try:
            info = proc.info
            if not _is_cc_process(info["name"] or "", (info["cmdline"] or [""])[0]):
                continue
            cwd = info["cwd"]
            if cwd and Path(cwd).exists():
                result.add(cwd)
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
    return result
