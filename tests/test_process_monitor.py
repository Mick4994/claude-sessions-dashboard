"""Regression tests for process_monitor — must distinguish real CC from claude-mem observer."""
from __future__ import annotations

import pytest

from src.collector.process_monitor import _is_cc_process


@pytest.mark.parametrize(
    "name,cmdline,cwd,expected",
    [
        # Real CC running with --permission-mode
        (
            "claude.exe",
            [
                r"A:\Users\Mick4994\AppData\Local\Microsoft\WinGet\Packages\Anthropic.ClaudeCode_Microsoft.Winget.Source_8wekyb3d8bbwe\claude.exe",
                "--permission-mode",
                "auto",
                "-r",
            ],
            r"A:\Users\Mick4994",
            True,
        ),
        # claude-mem observer: must be excluded even though exe is claude.exe
        (
            "claude.exe",
            [
                r"A:\Users\Mick4994\AppData\Local\Microsoft\WinGet\Packages\Anthropic.ClaudeCode_Microsoft.Winget.Source_8wekyb3d8bbwe\claude.exe",
                "--output-format",
                "stream-json",
                "--verbose",
                "--input-format",
                "stream-json",
                "--model",
                "sonnet",
            ],
            r"A:\Users\Mick4994\.claude-mem\observer-sessions",
            False,
        ),
        # claude-mem observer mode flag alone (no cwd hint)
        (
            "claude.exe",
            ["claude.exe", "--input-format", "stream-json"],
            r"C:\Projects\app",
            False,
        ),
        # Non-CC process: must be excluded
        (
            "code.exe",
            ["C:\\Program Files\\VSCode\\code.exe"],
            r"C:\Projects\app",
            False,
        ),
        # claude-mem observer even if running in a different cwd (defensive)
        (
            "claude.exe",
            ["claude.exe", "--output-format", "stream-json"],
            r"C:\some\other\path",
            False,
        ),
        # Empty cmdline: must be excluded
        (
            "claude.exe",
            [],
            None,
            False,
        ),
    ],
)
def test_is_cc_process(name, cmdline, cwd, expected):
    assert _is_cc_process(name, cmdline, cwd) is expected