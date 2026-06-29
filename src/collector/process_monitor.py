"""Enumerate running Claude Code processes on Windows."""
from __future__ import annotations

from pathlib import Path

# claude-mem worker runs inside .claude-mem/ — never a real user session.
_CLAUDE_MEM_DIR = ".claude-mem"

# cc-connect bridge processes are long-lived relays, not real user sessions.
# Their cmdline always contains "--append-system-prompt" with "cc-connect".
_CC_CONNECT_MARKER = "cc-connect"


def _is_cc_process(name: str, cmdline: list[str] | None, cwd: str | None) -> bool:
    """Return True for real Claude Code processes.

    Robust to process-name variants (claude.exe, claude-code.exe, etc):
    match any .exe whose name contains "claude". Exclude claude-mem workers
    by CWD only — do NOT filter by cmdline flags, which can false-negative
    real CC sessions in stream-json modes.
    """
    name_lower = (name or "").lower()
    if not (name_lower.endswith(".exe") and "claude" in name_lower):
        return False

    # claude-mem worker runs inside .claude-mem/ — never a real user session.
    if cwd and _CLAUDE_MEM_DIR in cwd:
        return False

    # cc-connect bridge: long-lived relay process, not a real user session.
    # Detect by scanning the joined cmdline for the "cc-connect" marker.
    if cmdline:
        cmdline_joined = " ".join(str(a) for a in cmdline)
        if _CC_CONNECT_MARKER in cmdline_joined:
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
