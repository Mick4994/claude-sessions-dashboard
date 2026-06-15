from pathlib import Path

from src.utils.paths import (
    app_data_dir,
    claude_projects_dir,
    config_path,
    default_config_text,
)


def test_app_data_dir_under_roaming(monkeypatch):
    monkeypatch.setenv("APPDATA", r"C:\Users\me\AppData\Roaming")
    p = app_data_dir()
    assert p == Path(r"C:\Users\me\AppData\Roaming\ClaudeSessionsDashboard")


def test_config_path():
    p = config_path()
    assert p.name == "config.ini"
    assert "ClaudeSessionsDashboard" in str(p)


def test_claude_projects_dir_uses_userprofile(monkeypatch):
    monkeypatch.setenv("USERPROFILE", r"C:\Users\me")
    p = claude_projects_dir()
    assert p == Path(r"C:\Users\me/.claude/projects")


def test_default_config_text_is_valid_ini():
    text = default_config_text()
    assert "[general]" in text
    assert "poll_interval_ms = 2000" in text
    assert "context_max_tokens = 1000000" in text
