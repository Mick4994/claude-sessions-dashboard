"""Regression tests for process_monitor — must distinguish real CC from claude-mem observer."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from src.collector import process_monitor
from src.collector.process_monitor import _is_cc_process, alive_cwds


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


# --- alive_cwds() with mocked psutil.process_iter ------------------------------


class _FakeProc:
    """Minimal stand-in for psutil.Process namedtuple from process_iter()."""

    def __init__(self, info: dict[str, Any]) -> None:
        self._info = info

    @property
    def info(self) -> dict[str, Any]:
        return self._info


class _FakeProcessIter:
    def __init__(self, attrs: list[str], procs: list[_FakeProc]) -> None:
        self._attrs = attrs
        self._procs = procs

    def __iter__(self):
        return iter(self._procs)


def _patch_process_iter(monkeypatch, procs: list[_FakeProc]) -> None:
    """Inject a fake psutil.process_iter via monkeypatch."""
    import psutil  # imported inside the module under test as well

    def _iter(attrs):
        return _FakeProcessIter(attrs, procs)

    monkeypatch.setattr(psutil, "process_iter", _iter)


def test_alive_cwds_returns_real_cc(monkeypatch, tmp_path):
    """TC: alive_cwds() returns cwd of a real CC process."""
    real_cwd = str(tmp_path)
    _patch_process_iter(
        monkeypatch,
        [
            _FakeProc(
                {
                    "name": "claude.exe",
                    "cmdline": ["claude.exe", "--permission-mode", "auto"],
                    "cwd": real_cwd,
                }
            ),
        ],
    )
    result = alive_cwds()
    assert real_cwd in result


def test_alive_cwds_excludes_claude_mem(monkeypatch, tmp_path):
    """TC-009: claude-mem observer is excluded from alive_cwds()."""
    cm_dir = tmp_path / ".claude-mem" / "observer-sessions"
    cm_dir.mkdir(parents=True)
    _patch_process_iter(
        monkeypatch,
        [
            _FakeProc(
                {
                    "name": "claude.exe",
                    "cmdline": [
                        "claude.exe",
                        "--input-format",
                        "stream-json",
                        "--output-format",
                        "stream-json",
                    ],
                    "cwd": str(cm_dir),
                }
            ),
        ],
    )
    result = alive_cwds()
    # Must NOT include the claude-mem cwd
    assert str(cm_dir) not in result


def test_alive_cwds_skips_nonexistent_cwd(monkeypatch):
    """Cwd that doesn't exist on disk should not appear in result."""
    fake_cwd = r"A:\does\not\exist\here\zzz123"
    _patch_process_iter(
        monkeypatch,
        [
            _FakeProc(
                {
                    "name": "claude.exe",
                    "cmdline": ["claude.exe", "--permission-mode", "auto"],
                    "cwd": fake_cwd,
                }
            ),
        ],
    )
    result = alive_cwds()
    assert fake_cwd not in result


def test_alive_cwds_handles_no_processes(monkeypatch):
    """No processes → empty set."""
    _patch_process_iter(monkeypatch, [])
    result = alive_cwds()
    assert result == set()


def test_alive_cwds_skips_process_that_raises(monkeypatch):
    """A process whose .info access raises must be skipped, not crash."""
    import psutil

    class _RaisingProc:
        @property
        def info(self) -> dict:
            raise psutil.AccessDenied(4242)

    def _iter(attrs):
        return iter([_RaisingProc()])

    import psutil as _psutil

    monkeypatch.setattr(_psutil, "process_iter", _iter)
    result = alive_cwds()
    assert result == set()


def test_alive_cwds_collects_multiple_distinct_real_ccs(monkeypatch, tmp_path):
    """Multiple distinct real CCs → multiple cwds."""
    cwd_a = tmp_path / "a"
    cwd_b = tmp_path / "b"
    cwd_a.mkdir()
    cwd_b.mkdir()
    _patch_process_iter(
        monkeypatch,
        [
            _FakeProc(
                {
                    "name": "claude.exe",
                    "cmdline": ["claude.exe", "--permission-mode", "auto"],
                    "cwd": str(cwd_a),
                }
            ),
            _FakeProc(
                {
                    "name": "claude.exe",
                    "cmdline": ["claude.exe", "--permission-mode", "auto"],
                    "cwd": str(cwd_b),
                }
            ),
        ],
    )
    result = alive_cwds()
    assert str(cwd_a) in result
    assert str(cwd_b) in result
    assert len(result) == 2