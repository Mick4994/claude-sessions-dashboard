from __future__ import annotations

import os
from pathlib import Path

APP_NAME = "ClaudeSessionsDashboard"


def app_data_dir() -> Path:
    """%APPDATA%/ClaudeSessionsDashboard or ~/.config/ClaudeSessionsDashboard."""
    if os.name == "nt":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / APP_NAME
    return Path.home() / ".config" / APP_NAME


def config_path() -> Path:
    return app_data_dir() / "config.ini"


def claude_home() -> Path:
    """~/.claude (or $CLAUDE_CONFIG_DIR if set)."""
    override = os.environ.get("CLAUDE_CONFIG_DIR")
    if override:
        return Path(override)
    return Path.home() / ".claude"


def claude_projects_dir() -> Path:
    return claude_home() / "projects"


def default_config_text() -> str:
    return """\
[general]
poll_interval_ms = 2000
stale_after_minutes = 30
recent_seconds = 60
expand_delay_ms = 200
collapse_delay_ms = 500
edge_snap_px = 30
indicator_size_px = 12
collapsed_opacity = 0.8
expanded_opacity = 1.0

[display]
context_max_tokens = 1000000
warning_threshold = 0.70
critical_threshold = 0.85
title_truncate_chars = 32
subtitle_truncate_chars = 40
max_visible_sessions = 20

[behavior]
auto_start = true
start_minimized_to_tray = false
"""
