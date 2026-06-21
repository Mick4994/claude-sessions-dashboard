"""Enumerate running Claude Code processes on Windows."""
from __future__ import annotations

from pathlib import Path

# Tightened: only match Claude Code specifically, not any node process with "claude" in path
_CC_SIGNATURES = ("claude-code", "@anthropic-ai/claude-code")


def _is_cc_process(name: str, cmdline: str | None) -> bool:
    if cmdline is None:
        return False
    if name.lower() == "claude.exe":
        return True
    needle = cmdline.lower()
    return any(sig in needle for sig in _CC_SIGNATURES)


def alive_cwds() -> set[str]:
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
