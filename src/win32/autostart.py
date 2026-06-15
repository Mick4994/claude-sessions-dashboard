"""Windows Task Scheduler wrapper for autostart."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

TASK_NAME = "ClaudeSessionsDashboard"


def _exe_path() -> str:
    if getattr(sys, "_MEIPASS", False) or getattr(os, "frozen", False):
        return os.path.abspath(sys.executable)
    project_dir = Path(__file__).resolve().parents[2]
    script = project_dir / "claude_dashboard.py"
    return f'cmd /c "cd /D {project_dir} && uv run python {script}"'


def is_enabled() -> bool:
    if os.name != "nt":
        return False
    out = subprocess.run(
        ["schtasks", "/Query", "/TN", TASK_NAME],
        capture_output=True,
        text=True,
    )
    return out.returncode == 0


def enable() -> bool:
    if os.name != "nt":
        return False
    cmd = f'schtasks /Create /TN {TASK_NAME} /TR "{_exe_path()}" /SC ONLOGON /RL HIGHEST /F'
    out = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return out.returncode == 0


def disable() -> bool:
    if os.name != "nt":
        return False
    out = subprocess.run(
        ["schtasks", "/Delete", "/TN", TASK_NAME, "/F"],
        capture_output=True,
        text=True,
    )
    return out.returncode == 0
