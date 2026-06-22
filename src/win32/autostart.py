"""Windows autostart via HKCU Run registry key (no admin required)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

_RUN_KEY = r"HKCU\Software\Microsoft\Windows\CurrentVersion\Run"
_VALUE_NAME = "ClaudeSessionsDashboard"


def _command() -> str:
    """Return the autostart command string."""
    if getattr(sys, "_MEIPASS", False) or getattr(os, "frozen", False):
        return f'"{os.path.abspath(sys.executable)}"'
    project_dir = Path(__file__).resolve().parents[2]
    exe = project_dir / ".venv" / "Scripts" / "pythonw.exe"
    script = project_dir / "claude_dashboard.py"
    return f'"{exe}" "{script}"'


def is_enabled() -> bool:
    if os.name != "nt":
        return False
    out = subprocess.run(
        ["reg", "query", _RUN_KEY, "/v", _VALUE_NAME],
        capture_output=True,
        text=True,
    )
    return out.returncode == 0


def enable() -> bool:
    if os.name != "nt":
        return False
    out = subprocess.run(
        ["reg", "add", _RUN_KEY, "/v", _VALUE_NAME, "/t", "REG_SZ", "/d", _command(), "/f"],
        capture_output=True,
        text=True,
    )
    return out.returncode == 0


def disable() -> bool:
    if os.name != "nt":
        return False
    out = subprocess.run(
        ["reg", "delete", _RUN_KEY, "/v", _VALUE_NAME, "/f"],
        capture_output=True,
        text=True,
    )
    return out.returncode == 0 or "not found" in (out.stderr + out.stdout).lower()
