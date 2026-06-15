# Claude Sessions Dashboard Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:test-driven-development to implement this plan task-by-task. Use superpowers:verification-loop before claiming done. Use superpowers:requesting-code-review after Phase 6, 10, 14.

**Goal:** Build a Windows desktop GUI app that visualizes all active Claude Code sessions via indicator lights and context percentages, with hover-expand cards, edge-snap docking, system tray, and task-scheduler autostart.

**Architecture:**
- PySide6 desktop app, frameless + always-on-top + transparent window
- Background `QThread` polls `~/.claude/projects/**/<sessionId>.jsonl` every 2s using mtime + tail-timestamp double-signal
- Single main window hosts collapsible indicator column (40px) ↔ expanded card list (280px)
- QSystemTrayIcon for quit/minimize; QLocalServer for single-instance; `schtasks` for autostart
- Configuration via INI in `%APPDATA%/ClaudeSessionsDashboard/`

**Tech Stack:**
- Python 3.12, PySide6 6.7+, `uv` (packaging), `pytest` 8+ + `pytest-qt`, `ruff`, `pyinstaller` 6+
- Win32 API via `ctypes` (SetForegroundWindow, EnumWindows)
- No third-party JSONL libs (parse manually — JSONL is just line-delimited JSON)

---

## Phase 1: Project Setup

### Task 1.1: Init uv project

**Files:**
- Create: `D:/Codes/claude-sessions-dashboard/pyproject.toml`
- Create: `D:/Codes/claude-sessions-dashboard/.gitignore`
- Create: `D:/Codes/claude-sessions-dashboard/.python-version`

**Step 1:** Create pyproject.toml

```toml
[project]
name = "claude-sessions-dashboard"
version = "0.1.0"
description = "Floating status bar for active Claude Code sessions"
requires-python = ">=3.12"
dependencies = [
    "PySide6>=6.7",
]

[project.optional-dependencies]
dev = [
    "pytest>=8",
    "pytest-qt>=4.4",
    "ruff>=0.5",
    "pyinstaller>=6",
]

[tool.uv]
package = false

[tool.pytest.ini_options]
testpaths = ["tests"]
qt_api = "pyside6"

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "W", "I", "N", "UP", "B", "A", "C4", "SIM"]
```

**Step 2:** Create .python-version and .gitignore

```
# .python-version
3.12
```

```
# .gitignore
__pycache__/
*.py[cod]
.venv/
.uv-cache/
dist/
build/
*.spec
.pytest_cache/
.ruff_cache/
*.log
config.local.ini
```

**Step 3:** Run `uv sync` to install deps and create venv

```bash
cd D:/Codes/claude-sessions-dashboard && uv sync --extra dev
```

**Step 4:** Verify PySide6 imports

```bash
uv run python -c "from PySide6.QtWidgets import QApplication; print('PySide6 OK')"
```

Expected: `PySide6 OK`

**Step 5:** Init git and commit

```bash
cd D:/Codes/claude-sessions-dashboard && git init && git add . && git commit -m "chore: init uv project with PySide6"
```

---

### Task 1.2: Create package skeleton

**Files:**
- Create: `src/__init__.py`
- Create: `src/collector/__init__.py`
- Create: `src/collector/models.py` (empty stub)
- Create: `src/ui/__init__.py`
- Create: `src/win32/__init__.py`
- Create: `src/utils/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`
- Create: `tests/fixtures/.gitkeep`
- Create: `scripts/__init__.py`

**Step 1:** Create directory structure

```bash
cd D:/Codes/claude-sessions-dashboard && mkdir -p src/collector src/ui src/win32 src/utils tests/fixtures scripts
```

**Step 2:** Touch `__init__.py` in each package

```bash
for d in src src/collector src/ui src/win32 src/utils tests scripts; do touch "$d/__init__.py"; done
```

**Step 3:** Create `tests/conftest.py` with qapp fixture

```python
import pytest
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app
    app.quit()
```

**Step 4:** Smoke test

```bash
uv run pytest tests/ -v --collect-only
```

Expected: collects 0 tests, exit 0.

**Step 5:** Commit

```bash
git add . && git commit -m "chore: create package skeleton"
```

---

### Task 1.3: Add ruff + pre-commit

**Files:**
- Create: `.pre-commit-config.yaml`

**Step 1:** Write pre-commit config

```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.5.7
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format
```

**Step 2:** Install hooks (best-effort, skip if pre-commit not available)

```bash
uv run pre-commit install 2>&1 || echo "pre-commit not installed, skipping"
```

**Step 3:** Run ruff to confirm no errors

```bash
uv run ruff check .
```

Expected: no output, exit 0.

**Step 4:** Commit

```bash
git add . && git commit -m "chore: add ruff + pre-commit"
```

---

## Phase 2: Data Models

### Task 2.1: Define SessionStatus enum (TDD)

**Files:**
- Test: `tests/test_models.py`
- Create: `src/collector/models.py`

**Step 1:** Write failing test

```python
# tests/test_models.py
from src.collector.models import SessionStatus


def test_session_status_values():
    assert SessionStatus.WORKING.value == "working"
    assert SessionStatus.IDLE.value == "idle"
    assert SessionStatus.PERMISSION.value == "permission"
    assert SessionStatus.ERROR.value == "error"
    assert SessionStatus.STALE.value == "stale"


def test_session_status_count():
    assert len(SessionStatus) == 5
```

**Step 2:** Run — should fail (ModuleNotFoundError)

```bash
uv run pytest tests/test_models.py -v
```

Expected: FAIL with "ModuleNotFoundError: No module named 'src.collector.models'"

**Step 3:** Implement enum

```python
# src/collector/models.py
from enum import Enum


class SessionStatus(Enum):
    """Lifecycle state of a Claude Code session."""

    WORKING = "working"          # 闪烁蓝
    IDLE = "idle"                # 常亮绿
    PERMISSION = "permission"    # 常亮黄
    ERROR = "error"              # 闪烁红
    STALE = "stale"              # 不亮灰
```

**Step 4:** Run — should pass

```bash
uv run pytest tests/test_models.py -v
```

Expected: 2 passed.

**Step 5:** Commit

```bash
git add . && git commit -m "feat(collector): add SessionStatus enum"
```

---

### Task 2.2: Define Session dataclass (TDD)

**Files:**
- Modify: `tests/test_models.py`
- Modify: `src/collector/models.py`

**Step 1:** Append failing tests

```python
# append to tests/test_models.py
from src.collector.models import Session


def test_session_minimal():
    s = Session(
        id="abc-123",
        jsonl_path="C:/Users/me/.claude/projects/x/abc-123.jsonl",
        cwd="C:/Users/me",
    )
    assert s.id == "abc-123"
    assert s.cwd == "C:/Users/me"
    assert s.title == ""           # default
    assert s.subtitle == ""        # default
    assert s.context_pct == 0.0    # default
    assert s.model == ""           # default
    assert s.status == SessionStatus.IDLE  # default
    assert s.last_activity_ts == 0.0       # default


def test_session_full():
    from datetime import datetime
    s = Session(
        id="x",
        jsonl_path="p",
        cwd="c",
        title="Search for things",
        subtitle="Edit: foo.py",
        context_pct=42.5,
        model="claude-sonnet-4-6",
        status=SessionStatus.WORKING,
        last_activity_ts=datetime(2026, 6, 15, 12, 0, 0).timestamp(),
    )
    assert s.title == "Search for things"
    assert s.context_pct == 42.5
    assert s.status == SessionStatus.WORKING
```

**Step 2:** Run — fail

```bash
uv run pytest tests/test_models.py -v
```

Expected: ImportError for Session.

**Step 3:** Implement Session dataclass

```python
# append to src/collector/models.py
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Session:
    """In-memory representation of one Claude Code session."""

    id: str
    jsonl_path: str
    cwd: str
    title: str = ""
    subtitle: str = ""
    context_pct: float = 0.0
    model: str = ""
    status: SessionStatus = SessionStatus.IDLE
    last_activity_ts: float = 0.0
```

**Step 4:** Run — pass

```bash
uv run pytest tests/test_models.py -v
```

Expected: 4 passed.

**Step 5:** Commit

```bash
git add . && git commit -m "feat(collector): add Session dataclass"
```

---

## Phase 3: Configuration

### Task 3.1: Implement config dataclass (TDD)

**Files:**
- Test: `tests/test_config.py`
- Create: `src/utils/config.py`

**Step 1:** Write failing tests

```python
# tests/test_config.py
from src.utils.config import Config, DEFAULTS


def test_defaults():
    cfg = Config.default()
    assert cfg.poll_interval_ms == 2000
    assert cfg.stale_after_minutes == 30
    assert cfg.recent_seconds == 60
    assert cfg.context_max_tokens == 1_000_000
    assert cfg.collapsed_opacity == 0.8
    assert cfg.expanded_opacity == 1.0
    assert cfg.auto_start is True


def test_from_dict_partial():
    cfg = Config.from_dict({"general": {"poll_interval_ms": 500}})
    assert cfg.poll_interval_ms == 500
    assert cfg.stale_after_minutes == 30  # default


def test_round_trip():
    cfg = Config.default()
    d = cfg.to_dict()
    cfg2 = Config.from_dict(d)
    assert cfg == cfg2


def test_from_file_missing(tmp_path):
    p = tmp_path / "config.ini"
    cfg = Config.from_file(p)
    assert cfg.poll_interval_ms == 2000  # all defaults
```

**Step 2:** Run — fail

```bash
uv run pytest tests/test_config.py -v
```

Expected: ModuleNotFoundError.

**Step 3:** Implement Config

```python
# src/utils/config.py
from __future__ import annotations

import configparser
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

DEFAULTS = {
    "general": {
        "poll_interval_ms": 2000,
        "stale_after_minutes": 30,
        "recent_seconds": 60,
        "expand_delay_ms": 200,
        "collapse_delay_ms": 500,
        "edge_snap_px": 30,
        "indicator_size_px": 12,
        "collapsed_opacity": 0.8,
        "expanded_opacity": 1.0,
    },
    "display": {
        "context_max_tokens": 1_000_000,
        "warning_threshold": 0.70,
        "critical_threshold": 0.85,
        "title_truncate_chars": 32,
        "subtitle_truncate_chars": 40,
        "max_visible_sessions": 20,
    },
    "behavior": {
        "auto_start": True,
        "start_minimized_to_tray": False,
    },
}


@dataclass
class Config:
    poll_interval_ms: int = 2000
    stale_after_minutes: int = 30
    recent_seconds: int = 60
    expand_delay_ms: int = 200
    collapse_delay_ms: int = 500
    edge_snap_px: int = 30
    indicator_size_px: int = 12
    collapsed_opacity: float = 0.8
    expanded_opacity: float = 1.0

    context_max_tokens: int = 1_000_000
    warning_threshold: float = 0.70
    critical_threshold: float = 0.85
    title_truncate_chars: int = 32
    subtitle_truncate_chars: int = 40
    max_visible_sessions: int = 20

    auto_start: bool = True
    start_minimized_to_tray: bool = False

    @classmethod
    def default(cls) -> Config:
        return cls()

    @classmethod
    def from_dict(cls, d: dict) -> Config:
        # Flatten nested dict to flat keys by section name
        flat = {}
        for section, kv in d.items():
            for k, v in kv.items():
                if k in {f.name for f in fields(cls)}:
                    # type-coerce
                    target = cls.__dataclass_fields__[k]
                    if target.type is bool:
                        flat[k] = str(v).lower() in ("1", "true", "yes", "on")
                    else:
                        flat[k] = target.type(v)
        return cls(**flat)

    def to_dict(self) -> dict:
        d = asdict(self)
        out = {"general": {}, "display": {}, "behavior": {}}
        mapping = {
            "general": [
                "poll_interval_ms", "stale_after_minutes", "recent_seconds",
                "expand_delay_ms", "collapse_delay_ms", "edge_snap_px",
                "indicator_size_px", "collapsed_opacity", "expanded_opacity",
            ],
            "display": [
                "context_max_tokens", "warning_threshold", "critical_threshold",
                "title_truncate_chars", "subtitle_truncate_chars",
                "max_visible_sessions",
            ],
            "behavior": ["auto_start", "start_minimized_to_tray"],
        }
        for sec, keys in mapping.items():
            for k in keys:
                out[sec][k] = d[k]
        return out

    @classmethod
    def from_file(cls, path: Path) -> Config:
        if not path.exists():
            return cls.default()
        cp = configparser.ConfigParser()
        cp.read(path, encoding="utf-8")
        d = {s: dict(cp.items(s)) for s in cp.sections()}
        return cls.from_dict(d)

    def to_file(self, path: Path) -> None:
        d = self.to_dict()
        cp = configparser.ConfigParser()
        for sec, kv in d.items():
            cp[sec] = {k: str(v) for k, v in kv.items()}
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            cp.write(f)
```

**Step 4:** Run — pass

```bash
uv run pytest tests/test_config.py -v
```

Expected: 4 passed.

**Step 5:** Commit

```bash
git add . && git commit -m "feat(utils): add Config dataclass with INI round-trip"
```

---

### Task 3.2: Add path utilities

**Files:**
- Test: `tests/test_paths.py`
- Create: `src/utils/paths.py`

**Step 1:** Write failing tests

```python
# tests/test_paths.py
from pathlib import Path
from src.utils.paths import (
    app_data_dir, config_path, claude_projects_dir,
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


def test_claude_projects_dir_uses_homedrive(monkeypatch):
    monkeypatch.setenv("USERPROFILE", r"C:\Users\me")
    p = claude_projects_dir()
    assert p == Path(r"C:\Users\me/.claude/projects")


def test_default_config_text_is_valid_ini():
    text = default_config_text()
    assert "[general]" in text
    assert "poll_interval_ms = 2000" in text
    assert "context_max_tokens = 1000000" in text
```

**Step 2:** Run — fail

```bash
uv run pytest tests/test_paths.py -v
```

Expected: ImportError.

**Step 3:** Implement

```python
# src/utils/paths.py
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
```

**Step 4:** Run — pass

```bash
uv run pytest tests/test_paths.py -v
```

Expected: 4 passed.

**Step 5:** Commit

```bash
git add . && git commit -m "feat(utils): add path helpers and default config text"
```

---

## Phase 4: JSONL Session Scanner

### Task 4.1: Implement scanner (TDD)

**Files:**
- Test: `tests/test_session_scanner.py`
- Create: `src/collector/session_scanner.py`

**Step 1:** Create test fixture dir with sample jsonl files

```bash
mkdir -p tests/fixtures/projects/proj1 tests/fixtures/projects/proj2
```

**Step 2:** Create `tests/fixtures/projects/proj1/sess-A.jsonl` (1 line)

```json
{"type":"last-prompt","leafUuid":"x","sessionId":"sess-A"}
```

**Step 3:** Create `tests/fixtures/projects/proj1/sess-B.jsonl`

```json
{"type":"last-prompt","leafUuid":"y","sessionId":"sess-B"}
{"type":"user","message":{"role":"user","content":"hello"},"timestamp":"2026-06-15T00:00:00Z","sessionId":"sess-B"}
```

**Step 4:** Create `tests/fixtures/projects/proj2/sess-C.jsonl` (empty file)

**Step 5:** Write tests

```python
# tests/test_session_scanner.py
import json
import os
import time
from pathlib import Path
import pytest
from src.collector.session_scanner import discover_jsonl_files, last_entry_timestamp


FIXTURE = Path(__file__).parent / "fixtures" / "projects"


def test_discover_finds_all_jsonl(tmp_path):
    # Copy fixture
    target = tmp_path / "projects"
    import shutil
    shutil.copytree(FIXTURE, target)
    files = list(discover_jsonl_files(target))
    assert len(files) == 3
    assert {f.stem for f in files} == {"sess-A", "sess-B", "sess-C"}


def test_discover_empty_dir(tmp_path):
    files = list(discover_jsonl_files(tmp_path))
    assert files == []


def test_discover_skips_subdirs_named_tool_results(tmp_path):
    # Real CC creates tool-results/ subdirs; should be ignored
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "sess-A.jsonl").write_text("{}")
    (proj / "tool-results").mkdir()
    (proj / "tool-results" / "x.jsonl").write_text("{}")
    files = list(discover_jsonl_files(tmp_path))
    assert len(files) == 1
    assert files[0].stem == "sess-A"


def test_last_entry_timestamp_known(tmp_path):
    p = tmp_path / "s.jsonl"
    p.write_text(
        '{"type":"last-prompt","sessionId":"s"}\n'
        '{"type":"user","timestamp":"2026-06-15T10:30:00Z","sessionId":"s"}\n'
    )
    ts = last_entry_timestamp(p)
    assert ts is not None
    assert abs(ts - 1771037400.0) < 60   # 2026-06-15 10:30 UTC


def test_last_entry_timestamp_no_timestamp_field(tmp_path):
    p = tmp_path / "s.jsonl"
    p.write_text('{"type":"user","message":{"role":"user","content":"hi"}}\n')
    ts = last_entry_timestamp(p)
    assert ts is None


def test_last_entry_timestamp_empty_file(tmp_path):
    p = tmp_path / "s.jsonl"
    p.write_text("")
    ts = last_entry_timestamp(p)
    assert ts is None
```

**Step 6:** Run — fail

```bash
uv run pytest tests/test_session_scanner.py -v
```

**Step 7:** Implement scanner

```python
# src/collector/session_scanner.py
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Iterator, Optional

# Subdirs created by Claude Code that should be skipped
_SKIP_DIR_NAMES = {"tool-results"}


def discover_jsonl_files(projects_dir: Path) -> Iterator[Path]:
    """Yield all *.jsonl files directly under projects_dir/<*>/*.jsonl.

    Skips CC's per-session tool-results/ subdirs.
    """
    if not projects_dir.exists():
        return
    for project_dir in projects_dir.iterdir():
        if not project_dir.is_dir():
            continue
        for entry in project_dir.iterdir():
            if entry.is_file() and entry.suffix == ".jsonl":
                yield entry


def last_entry_timestamp(jsonl_path: Path) -> Optional[float]:
    """Return the `timestamp` field of the last non-empty line in the file,
    parsed as ISO-8601 → epoch seconds. None if no timestamp found.
    Reads only the tail (last 64KB) to stay fast on large files.
    """
    try:
        size = jsonl_path.stat().st_size
        with open(jsonl_path, "rb") as f:
            if size > 65536:
                f.seek(size - 65536)
                f.readline()  # discard partial first line
            last = None
            for line in f:
                line = line.strip()
                if not line:
                    continue
                last = line
        if last is None:
            return None
        obj = json.loads(last)
        ts = obj.get("timestamp")
        if not ts:
            return None
        # Parse ISO-8601 with optional Z
        if ts.endswith("Z"):
            ts = ts[:-1] + "+00:00"
        return datetime.fromisoformat(ts).timestamp()
    except (OSError, ValueError, json.JSONDecodeError):
        return None
```

**Step 8:** Run — pass

```bash
uv run pytest tests/test_session_scanner.py -v
```

**Step 9:** Commit

```bash
git add . && git commit -m "feat(collector): add JSONL scanner and tail-timestamp reader"
```

---

## Phase 5: JSONL Session Parser

This is the heart of the project. The parser derives **title, subtitle, context%, status** from a JSONL file by reading its tail.

### Task 5.1: Title parser (TDD)

**Files:**
- Test: `tests/test_session_parser.py`
- Create: `src/collector/session_parser.py`

**Step 1:** Write failing tests for title parsing

```python
# tests/test_session_parser.py
import json
from pathlib import Path
import pytest
from src.collector.session_parser import (
    parse_session_metadata,
    _parse_title,
)


def _write_jsonl(path: Path, entries: list[dict]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e) + "\n")


def test_parse_title_uses_ai_title():
    entries = [
        {"type": "last-prompt", "sessionId": "s"},
        {"type": "ai-title", "aiTitle": "Search for things", "sessionId": "s"},
        {"type": "user", "message": {"role": "user", "content": "actually this is a prompt"}, "sessionId": "s"},
    ]
    p = Path("dummy.jsonl")
    assert _parse_title(entries) == "Search for things"


def test_parse_title_falls_back_to_first_user_prompt_truncated():
    long = "x" * 100
    entries = [
        {"type": "user", "message": {"role": "user", "content": long}, "sessionId": "s"},
    ]
    title = _parse_title(entries, max_chars=32)
    assert title == "x" * 32 + "…"


def test_parse_title_falls_back_to_cwd_basename():
    p = Path(r"C:\Users\me\my-project")
    entries = []
    title = _parse_title(entries, cwd=str(p))
    assert title == "my-project"


def test_parse_title_priority_ai_title_over_user_prompt():
    entries = [
        {"type": "user", "message": {"role": "user", "content": "first prompt"}, "sessionId": "s"},
        {"type": "ai-title", "aiTitle": "Better Title", "sessionId": "s"},
    ]
    assert _parse_title(entries) == "Better Title"
```

**Step 2:** Run — fail

```bash
uv run pytest tests/test_session_parser.py -v
```

**Step 3:** Implement `parse_session_metadata` shell + `_parse_title`

```python
# src/collector/session_parser.py
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .models import Session, SessionStatus


# --- Title ---------------------------------------------------------------

def _truncate(s: str, max_chars: int) -> str:
    if len(s) <= max_chars:
        return s
    return s[:max_chars] + "…"


def _first_user_text(entries: list[dict]) -> Optional[str]:
    for e in entries:
        if e.get("type") != "user":
            continue
        msg = e.get("message") or {}
        if msg.get("role") != "user":
            continue
        content = msg.get("content")
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    return (block.get("text") or "").strip()
    return None


def _parse_title(
    entries: list[dict],
    *,
    cwd: str = "",
    max_chars: int = 32,
) -> str:
    # 1. ai-title (any entry)
    for e in entries:
        if e.get("type") == "ai-title" and e.get("aiTitle"):
            return e["aiTitle"]
    # 2. first user message
    text = _first_user_text(entries)
    if text:
        return _truncate(text, max_chars)
    # 3. cwd basename
    if cwd:
        return Path(cwd).name or cwd
    return ""
```

**Step 4:** Run — pass

```bash
uv run pytest tests/test_session_parser.py -v -k title
```

**Step 5:** Commit

```bash
git add . && git commit -m "feat(collector): add title parser (ai-title → user prompt → cwd)"
```

---

### Task 5.2: Context % parser (TDD)

**Files:**
- Modify: `tests/test_session_parser.py`
- Modify: `src/collector/session_parser.py`

**Step 1:** Add failing tests

```python
# append to tests/test_session_parser.py
from src.collector.session_parser import _parse_context_pct


def test_context_pct_basic():
    e = {
        "type": "assistant",
        "message": {
            "usage": {
                "input_tokens": 50000,
                "cache_creation_input_tokens": 0,
                "cache_read_input_tokens": 50000,
                "output_tokens": 200,
            }
        },
    }
    assert _parse_context_pct([e], max_tokens=200000) == 50.0


def test_context_pct_uses_last_assistant_turn_only():
    entries = [
        {"type": "assistant", "message": {"usage": {"input_tokens": 1000, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0, "output_tokens": 10}}},
        {"type": "assistant", "message": {"usage": {"input_tokens": 80000, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0, "output_tokens": 10}}},
    ]
    assert _parse_context_pct(entries, max_tokens=200000) == 40.0


def test_context_pct_clamps_100():
    e = {"type": "assistant", "message": {"usage": {"input_tokens": 300000, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0, "output_tokens": 0}}}
    assert _parse_context_pct([e], max_tokens=200000) == 100.0


def test_context_pct_no_assistant_returns_0():
    assert _parse_context_pct([], max_tokens=200000) == 0.0
    assert _parse_context_pct(
        [{"type": "user", "message": {"role": "user", "content": "hi"}}],
        max_tokens=200000,
    ) == 0.0
```

**Step 2:** Run — fail

```bash
uv run pytest tests/test_session_parser.py -v -k context
```

**Step 3:** Implement `_parse_context_pct`

```python
# append to src/collector/session_parser.py

def _parse_context_pct(entries: list[dict], *, max_tokens: int) -> float:
    last_usage: Optional[dict] = None
    for e in entries:
        if e.get("type") != "assistant":
            continue
        msg = e.get("message") or {}
        usage = msg.get("usage")
        if isinstance(usage, dict):
            last_usage = usage
    if not last_usage:
        return 0.0
    tokens = (
        (last_usage.get("input_tokens") or 0)
        + (last_usage.get("cache_creation_input_tokens") or 0)
        + (last_usage.get("cache_read_input_tokens") or 0)
    )
    if max_tokens <= 0:
        return 0.0
    pct = round(tokens / max_tokens * 100, 1)
    return min(100.0, max(0.0, pct))
```

**Step 4:** Run — pass

```bash
uv run pytest tests/test_session_parser.py -v -k context
```

**Step 5:** Commit

```bash
git add . && git commit -m "feat(collector): add context% parser from latest assistant usage"
```

---

### Task 5.3: Subtitle (current task) parser (TDD)

**Files:**
- Modify: `tests/test_session_parser.py`
- Modify: `src/collector/session_parser.py`

**Step 1:** Add failing tests

```python
# append to tests/test_session_parser.py
from src.collector.session_parser import _parse_subtitle


def _assistant_tool_use(name: str, input_: dict) -> dict:
    return {
        "type": "assistant",
        "message": {
            "role": "assistant",
            "content": [{"type": "tool_use", "name": name, "input": input_}],
        },
    }


def test_subtitle_edit_shows_filename():
    e = _assistant_tool_use("Edit", {"file_path": "/repo/src/claude_dashboard.py"})
    assert _parse_subtitle([e], max_chars=40) == "Edit: claude_dashboard.py"


def test_subtitle_bash_truncates_command():
    e = _assistant_tool_use("Bash", {"command": "pip install pyside6 pytest pyinstaller --extra-index-url https://example.com"})
    sub = _parse_subtitle([e], max_chars=40)
    assert sub.startswith("Bash: pip install pyside6 pytest")
    assert len(sub) <= 41  # 40 + ellipsis


def test_subtitle_grep_shows_pattern():
    e = _assistant_tool_use("Grep", {"pattern": "TODO"})
    assert _parse_subtitle([e], max_chars=40) == "Grep: TODO"


def test_subtitle_agent_shows_subagent_and_desc():
    e = _assistant_tool_use("Agent", {"subagent_type": "Explore", "description": "Find auth code"})
    assert _parse_subtitle([e], max_chars=40) == "Agent: Explore: Find auth code"


def test_subtitle_uses_first_tool_use_of_last_assistant():
    entries = [
        _assistant_tool_use("Read", {"file_path": "/a.py"}),
        _assistant_tool_use("Edit", {"file_path": "/b.py"}),
    ]
    assert _parse_subtitle(entries, max_chars=40) == "Edit: b.py"


def test_subtitle_fallback_to_assistant_text():
    e = {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": "Let me think about this carefully."}]}}
    sub = _parse_subtitle([e], max_chars=40)
    assert "Let me think" in sub


def test_subtitle_fallback_to_completed_tool_result():
    e = {"type": "user", "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t1", "content": "ok"}]}}
    # When a prior assistant entry has matching tool_use, can derive (covered separately).
    # Without that, just "完成" / idle.
    sub = _parse_subtitle([e], max_chars=40)
    assert sub  # non-empty


def test_subtitle_fallback_idle_no_tool():
    assert _parse_subtitle([], max_chars=40, idle=True) == "Idle"
```

**Step 2:** Run — fail

**Step 3:** Implement `_parse_subtitle`

```python
# append to src/collector/session_parser.py

def _tool_subtitle(name: str, input_: dict, max_chars: int) -> str:
    path_like = {"Read", "Write", "Edit", "MultiEdit", "NotebookEdit"}
    if name in path_like:
        fp = input_.get("file_path") or input_.get("notebook_path") or ""
        base = Path(fp).name if fp else ""
        return _truncate(f"{name}: {base}" if base else name, max_chars)
    if name == "Bash":
        cmd = (input_.get("command") or "").strip()
        return _truncate(f"Bash: {cmd}", max_chars)
    if name == "Grep":
        pat = (input_.get("pattern") or "").strip()
        return _truncate(f"Grep: {pat}" if pat else "Grep", max_chars)
    if name == "Glob":
        pat = (input_.get("pattern") or "").strip()
        return _truncate(f"Glob: {pat}" if pat else "Glob", max_chars)
    if name == "Agent":
        st = input_.get("subagent_type", "")
        desc = (input_.get("description") or "").strip()
        head = f"Agent: {st}"
        if desc:
            head += f": {desc}"
        return _truncate(head, max_chars)
    if name == "WebFetch":
        url = input_.get("url") or ""
        host = url.split("/")[2] if url.count("/") >= 2 else url
        return _truncate(f"WebFetch: {host}" if host else "WebFetch", max_chars)
    if name == "WebSearch":
        q = (input_.get("query") or "").strip()
        return _truncate(f"WebSearch: {q}" if q else "WebSearch", max_chars)
    if name == "TodoWrite":
        return "TodoWrite: 任务列表更新"
    if name == "AskUserQuestion":
        return "AskUserQuestion: 询问用户"
    if name == "EnterPlanMode":
        return "Plan: 进入计划模式"
    return name


def _last_assistant_entry(entries: list[dict]) -> Optional[dict]:
    for e in reversed(entries):
        if e.get("type") == "assistant":
            return e
    return None


def _parse_subtitle(
    entries: list[dict],
    *,
    max_chars: int = 40,
    idle: bool = False,
) -> str:
    last = _last_assistant_entry(entries)
    if last:
        msg = last.get("message") or {}
        content = msg.get("content") or []
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    name = block.get("name") or "Tool"
                    inp = block.get("input") or {}
                    return _tool_subtitle(name, inp, max_chars)
            # No tool_use → maybe text
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    txt = (block.get("text") or "").strip()
                    if txt:
                        return _truncate(txt, max_chars)
    # No assistant at all (or no useful content) → check tool_result
    for e in reversed(entries):
        if e.get("type") == "user":
            msg = e.get("message") or {}
            content = msg.get("content") or []
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_result":
                        return _truncate("(完成) tool", max_chars)
            elif isinstance(content, str) and content.strip():
                return _truncate(content.strip(), max_chars)
    if idle:
        return "Idle"
    return "Thinking…"
```

**Step 4:** Run — pass

**Step 5:** Commit

```bash
git add . && git commit -m "feat(collector): add subtitle parser (current task)"
```

---

### Task 5.4: Status parser (TDD)

**Files:**
- Modify: `tests/test_session_parser.py`
- Modify: `src/collector/session_parser.py`

**Step 1:** Add failing tests

```python
# append to tests/test_session_parser.py
import time as time_mod
from src.collector.session_parser import _determine_status


def test_status_working_recent_assistant():
    now = time_mod.time()
    entries = [{"type": "assistant", "timestamp": _iso(now - 2)}]
    assert _determine_status(entries, now=now, recent_seconds=60) == SessionStatus.WORKING


def test_status_idle_assistant_end_turn_old():
    now = time_mod.time()
    entries = [{"type": "assistant", "stop_reason": "end_turn", "timestamp": _iso(now - 120)}]
    assert _determine_status(entries, now=now, recent_seconds=60) == SessionStatus.IDLE


def test_status_permission_tool_use_awaiting_result():
    now = time_mod.time()
    # Recent tool_use, no tool_result since
    entries = [
        {"type": "assistant", "stop_reason": "tool_use", "timestamp": _iso(now - 3),
         "message": {"content": [{"type": "tool_use", "name": "Bash", "input": {"command": "x"}}]}},
    ]
    assert _determine_status(entries, now=now, recent_seconds=60) == SessionStatus.PERMISSION


def test_status_idle_tool_use_with_result():
    now = time_mod.time()
    entries = [
        {"type": "assistant", "stop_reason": "tool_use", "timestamp": _iso(now - 5),
         "message": {"content": [{"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": "x"}}]}},
        {"type": "user", "timestamp": _iso(now - 1),
         "message": {"content": [{"type": "tool_result", "tool_use_id": "t1", "content": "ok"}]}},
    ]
    assert _determine_status(entries, now=now, recent_seconds=60) == SessionStatus.IDLE


def test_status_idle_user_prompt_recent():
    now = time_mod.time()
    entries = [{"type": "user", "timestamp": _iso(now - 2)}]
    assert _determine_status(entries, now=now, recent_seconds=60) == SessionStatus.IDLE


def test_status_stale_no_recent_activity():
    now = time_mod.time()
    entries = [{"type": "assistant", "timestamp": _iso(now - 300)}]
    assert _determine_status(entries, now=now, recent_seconds=60) == SessionStatus.STALE


def _iso(epoch: float) -> str:
    from datetime import datetime, timezone
    return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat().replace("+00:00", "Z")
```

**Step 2:** Run — fail

**Step 3:** Implement `_determine_status`

```python
# append to src/collector/session_parser.py

def _entry_ts(entry: dict) -> Optional[float]:
    ts = entry.get("timestamp")
    if not ts:
        return None
    try:
        if ts.endswith("Z"):
            ts = ts[:-1] + "+00:00"
        from datetime import datetime
        return datetime.fromisoformat(ts).timestamp()
    except ValueError:
        return None


def _gather_tool_use_ids(entries: list[dict]) -> set[str]:
    ids: set[str] = set()
    for e in entries:
        if e.get("type") != "assistant":
            continue
        content = (e.get("message") or {}).get("content") or []
        if not isinstance(content, list):
            continue
        for b in content:
            if isinstance(b, dict) and b.get("type") == "tool_use":
                tid = b.get("id")
                if tid:
                    ids.add(tid)
    return ids


def _gather_tool_result_ids(entries: list[dict]) -> set[str]:
    ids: set[str] = set()
    for e in entries:
        if e.get("type") != "user":
            continue
        content = (e.get("message") or {}).get("content") or []
        if not isinstance(content, list):
            continue
        for b in content:
            if isinstance(b, dict) and b.get("type") == "tool_result":
                tid = b.get("tool_use_id")
                if tid:
                    ids.add(tid)
    return ids


def _determine_status(
    entries: list[dict],
    *,
    now: float,
    recent_seconds: int = 60,
) -> SessionStatus:
    if not entries:
        return SessionStatus.STALE

    # Find last entry's type and timestamp
    last = entries[-1]
    last_type = last.get("type")
    last_ts = _entry_ts(last)

    if last_ts is None or (now - last_ts) > recent_seconds:
        return SessionStatus.STALE

    # If last assistant has tool_use with no matching tool_result → permission
    if last_type == "assistant":
        stop_reason = last.get("stop_reason")
        if stop_reason == "tool_use":
            use_ids = _gather_tool_use_ids(entries)
            res_ids = _gather_tool_result_ids(entries)
            if use_ids - res_ids:
                return SessionStatus.PERMISSION
            return SessionStatus.IDLE
        # Working: recent assistant, no end_turn
        return SessionStatus.WORKING

    if last_type == "user":
        return SessionStatus.IDLE

    return SessionStatus.IDLE
```

**Step 4:** Run — pass

**Step 5:** Commit

```bash
git add . && git commit -m "feat(collector): add status determination (working/idle/permission/stale)"
```

---

### Task 5.5: Wire full `parse_session_metadata`

**Files:**
- Modify: `tests/test_session_parser.py`
- Modify: `src/collector/session_parser.py`

**Step 1:** Add integration test

```python
# append to tests/test_session_parser.py
from src.collector.session_parser import parse_session_metadata


def test_parse_session_metadata_full(tmp_path):
    p = tmp_path / "s.jsonl"
    entries = [
        {"type": "last-prompt", "sessionId": "s", "timestamp": "2026-06-15T00:00:00Z"},
        {"type": "ai-title", "aiTitle": "Build dashboard", "sessionId": "s"},
        {"type": "user", "message": {"role": "user", "content": "build"}, "timestamp": "2026-06-15T00:00:01Z", "sessionId": "s"},
        {
            "type": "assistant",
            "message": {
                "role": "assistant",
                "content": [{"type": "tool_use", "id": "t1", "name": "Edit",
                             "input": {"file_path": "/repo/src/main.py"}}],
                "usage": {"input_tokens": 5000, "cache_creation_input_tokens": 0,
                          "cache_read_input_tokens": 30000, "output_tokens": 200},
            },
            "stop_reason": "tool_use",
            "timestamp": "2026-06-15T00:00:30Z",
            "sessionId": "s",
            "cwd": "/repo",
        },
    ]
    p.write_text("\n".join(json.dumps(e) for e in entries) + "\n")
    s = parse_session_metadata(
        jsonl_path=p,
        session_id="s",
        cwd="/repo",
        max_tokens=200000,
        title_max=32,
        subtitle_max=40,
    )
    assert s.id == "s"
    assert s.title == "Build dashboard"
    assert s.subtitle == "Edit: main.py"
    assert s.context_pct == 17.5   # (5000+30000)/200000
    assert s.status == SessionStatus.PERMISSION


def test_parse_session_metadata_uses_tail_only(tmp_path):
    """Large file → only tail should be read."""
    p = tmp_path / "s.jsonl"
    # Write 5000 dummy entries, then 1 real one
    with open(p, "w", encoding="utf-8") as f:
        for i in range(5000):
            f.write(json.dumps({"type": "noise", "i": i}) + "\n")
        f.write(json.dumps(
            {"type": "ai-title", "aiTitle": "Real Title", "sessionId": "s"}
        ) + "\n")
    s = parse_session_metadata(
        jsonl_path=p, session_id="s", cwd="x", max_tokens=200000,
        title_max=32, subtitle_max=40,
    )
    assert s.title == "Real Title"
```

**Step 2:** Implement `parse_session_metadata`

```python
# append to src/collector/session_parser.py

_TAIL_BYTES = 65536 * 2   # 128KB is plenty for tail metadata


def _read_jsonl_tail(path: Path) -> list[dict]:
    """Read last ~128KB of a JSONL file, parse each line as JSON, return list."""
    try:
        size = path.stat().st_size
        with open(path, "rb") as f:
            if size > _TAIL_BYTES:
                f.seek(size - _TAIL_BYTES)
                f.readline()  # discard partial first line
            entries: list[dict] = []
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(obj, dict):
                    entries.append(obj)
        return entries
    except OSError:
        return []


def _latest_model(entries: list[dict]) -> str:
    for e in reversed(entries):
        if e.get("type") == "assistant":
            m = (e.get("message") or {}).get("model")
            if m:
                return m
    return ""


def _latest_cwd(entries: list[dict], fallback: str = "") -> str:
    for e in reversed(entries):
        c = e.get("cwd")
        if c:
            return c
    return fallback


def parse_session_metadata(
    *,
    jsonl_path: Path,
    session_id: str,
    cwd: str,
    max_tokens: int,
    title_max: int,
    subtitle_max: int,
    recent_seconds: int = 60,
) -> Session:
    """Parse the tail of a JSONL into a Session dataclass."""
    entries = _read_jsonl_tail(jsonl_path)
    actual_cwd = _latest_cwd(entries, cwd)
    title = _parse_title(entries, cwd=actual_cwd, max_chars=title_max)
    subtitle = _parse_subtitle(entries, max_chars=subtitle_max, idle=False)
    pct = _parse_context_pct(entries, max_tokens=max_tokens)
    model = _latest_model(entries)
    status = _determine_status(entries, now=_now(), recent_seconds=recent_seconds)
    last_ts = 0.0
    for e in reversed(entries):
        ts = _entry_ts(e)
        if ts is not None:
            last_ts = ts
            break
    return Session(
        id=session_id,
        jsonl_path=str(jsonl_path),
        cwd=actual_cwd,
        title=title,
        subtitle=subtitle,
        context_pct=pct,
        model=model,
        status=status,
        last_activity_ts=last_ts,
    )


def _now() -> float:
    import time
    return time.time()
```

**Step 3:** Run — pass

```bash
uv run pytest tests/test_session_parser.py -v
```

**Step 4:** Commit

```bash
git add . && git commit -m "feat(collector): wire parse_session_metadata end-to-end"
```

---

## Phase 6: Background Collector

### Task 6.1: SessionCollector (TDD)

**Files:**
- Test: `tests/test_collector.py`
- Create: `src/collector/collector.py`

**Step 1:** Add QObject signal import conftest fixture if needed (skip for now)

**Step 2:** Write failing tests

```python
# tests/test_collector.py
import json
import time
from pathlib import Path
import pytest
from src.collector.collector import SessionCollector
from src.collector.models import Session, SessionStatus


def _write(path: Path, entries: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(e) for e in entries) + "\n")


def test_collector_yields_active_sessions(tmp_path, monkeypatch):
    proj = tmp_path / "proj"
    proj.mkdir()
    p = proj / "s1.jsonl"
    _write(p, [
        {"type": "last-prompt", "sessionId": "s1"},
        {"type": "user", "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "sessionId": "s1"},
    ])
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path))
    c = SessionCollector(poll_interval_ms=100, recent_seconds=60, stale_after_minutes=30)
    c.scan_once()
    sessions = c.current_sessions()
    assert len(sessions) == 1
    assert sessions[0].id == "s1"


def test_collector_filters_stale_by_mtime(tmp_path, monkeypatch):
    proj = tmp_path / "proj"
    proj.mkdir()
    p = proj / "s1.jsonl"
    _write(p, [{"type": "last-prompt", "sessionId": "s1"}])
    # Set mtime to long ago
    import os
    old = time.time() - 7200   # 2h ago
    os.utime(p, (old, old))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path))
    c = SessionCollector(poll_interval_ms=100, recent_seconds=60, stale_after_minutes=30)
    c.scan_once()
    assert c.current_sessions() == []


def test_collector_removes_session_when_stale(tmp_path, monkeypatch):
    proj = tmp_path / "proj"
    proj.mkdir()
    p = proj / "s1.jsonl"
    _write(p, [{"type": "last-prompt", "sessionId": "s1"}])
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path))
    c = SessionCollector(poll_interval_ms=100, recent_seconds=60, stale_after_minutes=30)
    c.scan_once()
    assert len(c.current_sessions()) == 1
    # Now make it stale
    import os
    old = time.time() - 7200
    os.utime(p, (old, old))
    c.scan_once()
    assert c.current_sessions() == []
```

**Step 3:** Implement

```python
# src/collector/collector.py
from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Callable, Optional

from PySide6.QtCore import QObject, QTimer, Signal

from .models import Session
from .session_parser import parse_session_metadata
from .session_scanner import discover_jsonl_files, last_entry_timestamp


class SessionCollector(QObject):
    """Polls ~/.claude/projects for active sessions, emits updates."""

    sessionsChanged = Signal(list)  # list[Session]

    def __init__(
        self,
        *,
        poll_interval_ms: int = 2000,
        recent_seconds: int = 60,
        stale_after_minutes: int = 30,
        max_context_tokens: int = 1_000_000,
        title_truncate_chars: int = 32,
        subtitle_truncate_chars: int = 40,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self._poll_interval_ms = poll_interval_ms
        self._recent_seconds = recent_seconds
        self._stale_after_minutes = stale_after_minutes
        self._max_context_tokens = max_context_tokens
        self._title_truncate_chars = title_truncate_chars
        self._subtitle_truncate_chars = subtitle_truncate_chars
        self._sessions: dict[str, Session] = {}
        self._timer: Optional[QTimer] = None

    @property
    def projects_dir(self) -> Path:
        override = os.environ.get("CLAUDE_CONFIG_DIR")
        base = Path(override) if override else Path.home() / ".claude"
        return base / "projects"

    def start(self) -> None:
        if self._timer is None:
            self._timer = QTimer(self)
            self._timer.timeout.connect(self.scan_once)
        self._timer.start(self._poll_interval_ms)
        self.scan_once()

    def stop(self) -> None:
        if self._timer is not None:
            self._timer.stop()

    def current_sessions(self) -> list[Session]:
        return list(self._sessions.values())

    def scan_once(self) -> None:
        now = time.time()
        stale_cutoff = now - self._stale_after_minutes * 60
        seen_ids: set[str] = set()

        for jsonl in discover_jsonl_files(self.projects_dir):
            sid = jsonl.stem
            try:
                mtime = jsonl.stat().st_mtime
            except OSError:
                continue
            if mtime < stale_cutoff:
                continue
            ts = last_entry_timestamp(jsonl)
            if ts is None or (now - ts) > self._recent_seconds:
                continue
            seen_ids.add(sid)
            try:
                session = parse_session_metadata(
                    jsonl_path=jsonl,
                    session_id=sid,
                    cwd=str(jsonl.parent),
                    max_tokens=self._max_context_tokens,
                    title_max=self._title_truncate_chars,
                    subtitle_max=self._subtitle_truncate_chars,
                    recent_seconds=self._recent_seconds,
                )
            except Exception:
                continue
            self._sessions[sid] = session

        # Remove sessions no longer seen
        removed = [k for k in self._sessions if k not in seen_ids]
        for k in removed:
            del self._sessions[k]

        if removed or self._sessions:
            self.sessionsChanged.emit(self.current_sessions())
```

**Step 4:** Run — pass

```bash
uv run pytest tests/test_collector.py -v
```

Note: `QObject` requires `QApplication` for `Signal` to work. Ensure the `qapp` fixture from conftest is in scope.

**Step 5:** Commit

```bash
git add . && git commit -m "feat(collector): add SessionCollector with timer + double-signal filter"
```

---

## Phase 7: Indicator Widget (UI)

### Task 7.1: Status → color mapping (TDD)

**Files:**
- Test: `tests/test_indicator_widget.py`
- Create: `src/ui/indicator_widget.py`

**Step 1:** Write failing tests

```python
# tests/test_indicator_widget.py
import pytest
from PySide6.QtGui import QColor
from src.collector.models import SessionStatus
from src.ui.indicator_widget import status_color, status_blink_ms


def test_status_color_known():
    assert status_color(SessionStatus.WORKING) == QColor("#3B82F6")
    assert status_color(SessionStatus.IDLE) == QColor("#22C55E")
    assert status_color(SessionStatus.PERMISSION) == QColor("#EAB308")
    assert status_color(SessionStatus.ERROR) == QColor("#EF4444")
    assert status_color(SessionStatus.STALE) == QColor("#6B7280")


def test_status_blink_ms_known():
    assert status_blink_ms(SessionStatus.WORKING) == 1000
    assert status_blink_ms(SessionStatus.ERROR) == 700
    assert status_blink_ms(SessionStatus.IDLE) == 0
    assert status_blink_ms(SessionStatus.PERMISSION) == 0
    assert status_blink_ms(SessionStatus.STALE) == 0
```

**Step 2:** Implement

```python
# src/ui/indicator_widget.py
from __future__ import annotations

from PySide6.QtCore import QObject, QPropertyAnimation, QTimer, Qt
from PySide6.QtGui import QColor, QPainter, QBrush
from PySide6.QtWidgets import QWidget

from ..collector.models import SessionStatus


_COLORS: dict[SessionStatus, QColor] = {
    SessionStatus.WORKING: QColor("#3B82F6"),
    SessionStatus.IDLE: QColor("#22C55E"),
    SessionStatus.PERMISSION: QColor("#EAB308"),
    SessionStatus.ERROR: QColor("#EF4444"),
    SessionStatus.STALE: QColor("#6B7280"),
}


def status_color(s: SessionStatus) -> QColor:
    return _COLORS[s]


_BLINK_MS: dict[SessionStatus, int] = {
    SessionStatus.WORKING: 1000,
    SessionStatus.ERROR: 700,
}


def status_blink_ms(s: SessionStatus) -> int:
    return _BLINK_MS.get(s, 0)
```

**Step 3:** Run — pass

**Step 4:** Commit

```bash
git add . && git commit -m "feat(ui): add status_color / status_blink_ms mappings"
```

---

### Task 7.2: IndicatorDot widget

**Files:**
- Modify: `tests/test_indicator_widget.py`
- Modify: `src/ui/indicator_widget.py`

**Step 1:** Add widget test

```python
# append
def test_indicator_dot_paints_color(qapp):
    from src.ui.indicator_widget import IndicatorDot
    from PySide6.QtWidgets import QApplication
    dot = IndicatorDot(SessionStatus.IDLE, size_px=12)
    dot.resize(20, 20)
    # Force paint
    pm = dot.grab()
    assert not pm.isNull()


def test_indicator_dot_changes_color_on_set_status(qapp):
    from src.ui.indicator_widget import IndicatorDot
    dot = IndicatorDot(SessionStatus.IDLE, size_px=12)
    dot.set_status(SessionStatus.WORKING)
    assert dot._color == status_color(SessionStatus.WORKING)
```

**Step 2:** Implement

```python
# append to src/ui/indicator_widget.py

class IndicatorDot(QWidget):
    """A circular indicator with optional blink animation."""

    def __init__(self, status: SessionStatus, *, size_px: int = 12, parent=None) -> None:
        super().__init__(parent)
        self.setFixedSize(size_px + 6, size_px + 6)
        self._size_px = size_px
        self._color = status_color(status)
        self._opacity = 1.0
        self._timer: QTimer | None = None
        self._t0 = 0
        self._period_ms = 0
        self.set_status(status)

    def set_status(self, s: SessionStatus) -> None:
        self._color = status_color(s)
        self._period_ms = status_blink_ms(s)
        if self._timer is not None:
            self._timer.stop()
            self._timer = None
        if self._period_ms > 0:
            self._timer = QTimer(self)
            self._t0 = 0
            self._timer.timeout.connect(self._tick)
            self._timer.start(33)   # ~30fps
        self._opacity = 1.0
        self.update()

    def _tick(self) -> None:
        import time
        t = (time.time() * 1000) % self._period_ms
        # Triangle wave 0.5 → 1.0 → 0.5
        phase = t / self._period_ms
        self._opacity = 0.55 + 0.45 * (1 - abs(2 * phase - 1))
        self.update()

    def paintEvent(self, _ev) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        c = QColor(self._color)
        c.setAlphaF(max(0.2, min(1.0, self._opacity)))
        p.setBrush(QBrush(c))
        p.setPen(Qt.NoPen)
        r = self._size_px / 2
        cx = self.width() / 2
        cy = self.height() / 2
        p.drawEllipse(int(cx - r), int(cy - r), int(r * 2), int(r * 2))
        # inner highlight
        hl = QColor(255, 255, 255, 60)
        p.setBrush(QBrush(hl))
        p.drawEllipse(int(cx - r * 0.55), int(cy - r * 0.7), int(r * 0.6), int(r * 0.45))
        p.end()
```

**Step 3:** Run — pass

**Step 4:** Commit

```bash
git add . && git commit -m "feat(ui): add IndicatorDot widget with blink animation"
```

---

## Phase 8: Card Widget

### Task 8.1: SessionCard widget

**Files:**
- Test: `tests/test_card_widget.py`
- Create: `src/ui/card_widget.py`

**Step 1:** Write tests

```python
# tests/test_card_widget.py
from src.collector.models import Session, SessionStatus
from src.ui.card_widget import SessionCard


def test_card_widget_init(qapp):
    s = Session(
        id="abc", jsonl_path="p", cwd="C:/Users/me/repo",
        title="Search for things", subtitle="Edit: foo.py",
        context_pct=42.0, model="claude-sonnet-4-6",
        status=SessionStatus.WORKING,
    )
    card = SessionCard(s)
    assert card.session is s
    # Title shows
    assert "Search for things" in card.title_label.text()
    # Subtitle shows
    assert "Edit: foo.py" in card.subtitle_label.text()
    # Percent shows
    assert "42" in card.percent_label.text()
```

**Step 2:** Implement

```python
# src/ui/card_widget.py
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QProgressBar, QVBoxLayout, QWidget,
)

from ..collector.models import Session, SessionStatus
from .indicator_widget import IndicatorDot


def _context_color(pct: float, *, warn: float = 70.0, crit: float = 85.0) -> QColor:
    if pct >= crit:
        return QColor("#EF4444")
    if pct >= warn:
        return QColor("#EAB308")
    return QColor("#22C55E")


class SessionCard(QFrame):
    """Expanded card: dot | (title + subtitle + progress) | percent."""

    clicked = Signal(str)  # session id

    def __init__(self, session: Session, *, parent=None) -> None:
        super().__init__(parent)
        self.session = session
        self.setObjectName("SessionCard")
        self.setStyleSheet(
            "#SessionCard { background: transparent; }"
            "QLabel { color: #E6E6EA; }"
            "QLabel[role='subtitle'] { color: rgba(180,180,190,0.85); }"
            "QLabel[role='cwd'] { color: rgba(140,140,150,0.7); font-size: 10px; }"
            "QLabel[role='percent'] { font-weight: bold; }"
            "QProgressBar { background: rgba(255,255,255,0.08); border: none; height: 6px; border-radius: 3px; }"
            "QProgressBar::chunk { background-color: #22C55E; border-radius: 3px; }"
        )

        self.dot = IndicatorDot(session.status, size_px=10)
        self.title_label = QLabel(session.title or "(untitled)")
        self.subtitle_label = QLabel(session.subtitle or "")
        self.subtitle_label.setProperty("role", "subtitle")
        self.subtitle_label.setTextFormat(Qt.PlainText)
        f = QFont()
        f.setPointSize(9)
        self.subtitle_label.setFont(f)
        # Truncate subtitle visually via fixed width handled by parent layout

        self.percent_label = QLabel(_format_pct(session.context_pct))
        self.percent_label.setProperty("role", "percent")
        self.percent_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.percent_label.setStyleSheet(f"color: {_context_color(session.context_pct).name()}; font-size: 12px;")

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(int(session.context_pct))
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(6)
        c = _context_color(session.context_pct)
        self.progress.setStyleSheet(
            f"QProgressBar {{ background: rgba(255,255,255,0.08); border: none; height: 6px; border-radius: 3px; }}"
            f"QProgressBar::chunk {{ background-color: {c.name()}; border-radius: 3px; }}"
        )

        cwd_label = QLabel(_shorten_cwd(session.cwd))
        cwd_label.setProperty("role", "cwd")
        cwd_label.setWordWrap(False)
        cwd_label.setTextFormat(Qt.PlainText)

        # Layout
        left = QVBoxLayout()
        left.setContentsMargins(0, 0, 0, 0)
        left.setSpacing(2)
        left.addWidget(self.title_label)
        left.addWidget(self.subtitle_label)
        left.addWidget(self.progress)
        left.addWidget(cwd_label)

        right = QVBoxLayout()
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(0)
        right.addWidget(self.percent_label, 0, Qt.AlignRight)
        right.addStretch(1)

        outer = QHBoxLayout(self)
        outer.setContentsMargins(8, 6, 8, 6)
        outer.setSpacing(8)
        outer.addWidget(self.dot, 0, Qt.AlignTop)
        outer.addLayout(left, 1)
        outer.addLayout(right, 0)

        self.setFixedHeight(78)
        self.setCursor(Qt.PointingHandCursor)

    def update_session(self, session: Session) -> None:
        self.session = session
        self.dot.set_status(session.status)
        self.title_label.setText(session.title or "(untitled)")
        self.subtitle_label.setText(session.subtitle or "")
        self.percent_label.setText(_format_pct(session.context_pct))
        c = _context_color(session.context_pct)
        self.percent_label.setStyleSheet(f"color: {c.name()}; font-size: 12px;")
        self.progress.setValue(int(session.context_pct))
        self.progress.setStyleSheet(
            f"QProgressBar {{ background: rgba(255,255,255,0.08); border: none; height: 6px; border-radius: 3px; }}"
            f"QProgressBar::chunk {{ background-color: {c.name()}; border-radius: 3px; }}"
        )

    def mousePressEvent(self, ev) -> None:
        if ev.button() == Qt.LeftButton:
            self.clicked.emit(self.session.id)
        super().mousePressEvent(ev)


def _format_pct(p: float) -> str:
    if p >= 99.5:
        return "100%"
    return f"{p:.0f}%"


def _shorten_cwd(cwd: str) -> str:
    if not cwd:
        return ""
    return cwd.replace("\\", "/").replace("C:/Users/", "~/")
```

**Step 3:** Run — pass

**Step 4:** Commit

```bash
git add . && git commit -m "feat(ui): add SessionCard widget"
```

---

## Phase 9: Main Window

### Task 9.1: Frameless + on-top + transparent window

**Files:**
- Create: `src/ui/main_window.py`

**Step 1:** Implement (no test — verified by smoke run)

```python
# src/ui/main_window.py
from __future__ import annotations

from PySide6.QtCore import Qt, QPoint, QRect, QTimer
from PySide6.QtGui import QPainter, QColor, QBrush
from PySide6.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QApplication

from .card_widget import SessionCard
from .indicator_widget import IndicatorDot
from ..collector.models import Session


class MainWindow(QMainWindow):
    """Frameless, always-on-top, transparent-collapsed window with hover-expand."""

    COLLAPSED_WIDTH = 40
    EXPANDED_WIDTH = 280
    CARD_HEIGHT = 78
    CARD_SPACING = 6
    PADDING = 8

    def __init__(self) -> None:
        super().__init__()
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)

        self._sessions: list[Session] = []
        self._expanded = False
        self._target_width = self.COLLAPSED_WIDTH
        self._current_width = self.COLLAPSED_WIDTH

        # Central container with background
        self._container = QWidget(self)
        self._container.setObjectName("container")
        self._container.setStyleSheet(
            "#container { background: rgba(20, 20, 24, 0.80); border-radius: 8px; }"
        )
        # Layout inside container
        self._inner = QVBoxLayout(self._container)
        self._inner.setContentsMargins(self.PADDING, self.PADDING, self.PADDING, self.PADDING)
        self._inner.setSpacing(self.CARD_SPACING)

        self.setCentralWidget(self._container)
        self.resize(self.COLLAPSED_WIDTH, 200)
        self._move_to_right_edge()

        # Hover timers
        self._expand_timer = QTimer(self)
        self._expand_timer.setSingleShot(True)
        self._expand_timer.timeout.connect(self._do_expand)
        self._collapse_timer = QTimer(self)
        self._collapse_timer.setSingleShot(True)
        self._collapse_timer.timeout.connect(self._do_collapse)

        self.setMouseTracking(True)
        self._container.setMouseTracking(True)

    # ---- positioning ----
    def _move_to_right_edge(self) -> None:
        screen = QApplication.primaryScreen()
        if screen is None:
            return
        geo = screen.availableGeometry()
        x = geo.right() - self._current_width + 1   # +1 to hide edge
        y = geo.center().y() - self.height() // 2
        self.move(x, y)

    # ---- session updates ----
    def set_sessions(self, sessions: list[Session]) -> None:
        self._sessions = sessions
        self._rebuild()
        self._fit_height()

    def _fit_height(self) -> None:
        n = max(1, len(self._sessions))
        h = self.PADDING * 2 + n * (self.IndicatorSize or 18) + (n - 1) * 4
        if self._expanded:
            h = self.PADDING * 2 + len(self._sessions) * self.CARD_HEIGHT + max(0, len(self._sessions) - 1) * self.CARD_SPACING
        h = max(60, h)
        self.resize(self._current_width, h)
        self._move_to_right_edge()

    @property
    def IndicatorSize(self) -> int:
        return 18

    # ---- rebuild contents ----
    def _clear_inner(self) -> None:
        while self._inner.count():
            item = self._inner.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()

    def _rebuild(self) -> None:
        self._clear_inner()
        if self._expanded:
            for s in self._sessions:
                card = SessionCard(s)
                card.clicked.connect(self._on_card_clicked)
                self._inner.addWidget(card)
        else:
            for s in self._sessions:
                row = QWidget()
                row.setFixedHeight(self.IndicatorSize)
                hl = QHBoxLayout(row)
                hl.setContentsMargins(0, 0, 0, 0)
                hl.addStretch(1)
                hl.addWidget(IndicatorDot(s.status, size_px=12))
                hl.addStretch(1)
                self._inner.addWidget(row)
        self._inner.addStretch(0)

    # ---- hover expand/collapse ----
    def enterEvent(self, _ev) -> None:
        self._collapse_timer.stop()
        self._expand_timer.start(200)   # expand_delay_ms

    def leaveEvent(self, _ev) -> None:
        self._expand_timer.stop()
        self._collapse_timer.start(500) # collapse_delay_ms

    def _do_expand(self) -> None:
        if self._expanded:
            return
        self._expanded = True
        self._target_width = self.EXPANDED_WIDTH
        self._rebuild()
        self._fit_height()
        self._animate_width(self.COLLAPSED_WIDTH, self.EXPANDED_WIDTH, 180)

    def _do_collapse(self) -> None:
        if not self._expanded:
            return
        self._expanded = False
        self._target_width = self.COLLAPSED_WIDTH
        self._rebuild()
        self._animate_width(self.EXPANDED_WIDTH, self.COLLAPSED_WIDTH, 180)

    def _animate_width(self, from_w: int, to_w: int, duration_ms: int) -> None:
        from PySide6.QtCore import QPropertyAnimation
        self._anim = QPropertyAnimation(self, b"geometry")
        rect = self.geometry()
        rect.setWidth(to_w)
        # adjust x so right edge stays put
        rect.setX(rect.x() - (to_w - from_w))
        self._anim.setDuration(duration_ms)
        self._anim.setStartValue(self.geometry())
        self._anim.setEndValue(rect)
        self._anim.start()
        self._current_width = to_w
        # Ensure container is sized correctly after
        QTimer.singleShot(duration_ms + 20, self._move_to_right_edge)

    # ---- card click ----
    def _on_card_clicked(self, session_id: str) -> None:
        # Implemented in Phase 11 (windows_focus)
        from .signal_bus import cardClicked
        cardClicked.emit(session_id)
```

**Step 2:** Smoke test with empty sessions

```bash
uv run python -c "
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtWidgets import QApplication
import sys
app = QApplication(sys.argv)
from src.ui.main_window import MainWindow
w = MainWindow()
w.show()
app.processEvents()
print('MainWindow OK, size=', w.size().width(), 'x', w.size().height())
"
```

Expected: `MainWindow OK, size= 40 x ...`

**Step 3:** Commit

```bash
git add . && git commit -m "feat(ui): add frameless MainWindow with hover expand/collapse"
```

---

### Task 9.2: Wire MainWindow to SessionCollector

**Files:**
- Modify: `claude_dashboard.py` (create if missing)
- Create: `src/ui/signal_bus.py`

**Step 1:** Create signal bus

```python
# src/ui/signal_bus.py
from PySide6.QtCore import QObject, Signal

class _Bus(QObject):
    cardClicked = Signal(str)  # session id
    requestQuit = Signal()
    requestReloadConfig = Signal()
    requestPause = Signal(bool)  # True=pause, False=resume

signalBus = _Bus()
```

**Step 2:** Create main entry `claude_dashboard.py`

```python
#!/usr/bin/env python3
"""Claude Sessions Dashboard — floating status bar entrypoint."""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Allow `python claude_dashboard.py` to find src package
sys.path.insert(0, str(Path(__file__).parent))

from PySide6.QtCore import QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from src.collector.collector import SessionCollector
from src.ui.main_window import MainWindow
from src.ui.signal_bus import signalBus
from src.utils.config import Config
from src.utils.paths import config_path, default_config_text


def main() -> int:
    cfg_path = config_path()
    if not cfg_path.exists():
        cfg_path.parent.mkdir(parents=True, exist_ok=True)
        cfg_path.write_text(default_config_text(), encoding="utf-8")
    cfg = Config.from_file(cfg_path)

    app = QApplication(sys.argv)
    app.setApplicationName("Claude Sessions Dashboard")
    app.setQuitOnLastWindowClosed(False)   # tray keeps process alive

    window = MainWindow()
    window.show()

    collector = SessionCollector(
        poll_interval_ms=cfg.poll_interval_ms,
        recent_seconds=cfg.recent_seconds,
        stale_after_minutes=cfg.stale_after_minutes,
        max_context_tokens=cfg.context_max_tokens,
        title_truncate_chars=cfg.title_truncate_chars,
        subtitle_truncate_chars=cfg.subtitle_truncate_chars,
    )

    def on_sessions_changed(sessions):
        window.set_sessions(sessions)

    collector.sessionsChanged.connect(on_sessions_changed)
    collector.start()

    # Phase 12: tray wiring
    from src.ui.tray import build_tray
    build_tray(app, window, collector, cfg_path)

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
```

**Step 3:** Smoke test

```bash
uv run python claude_dashboard.py
```

Expected: Window appears on right edge of screen. (Manual: close it.)

**Step 4:** Commit

```bash
git add . && git commit -m "feat: wire MainWindow to SessionCollector and add entrypoint"
```

---

## Phase 10: Edge Snap & Drag

### Task 10.1: Drag and edge snap

**Files:**
- Modify: `src/ui/main_window.py`

**Step 1:** Add drag state and override mouse events

```python
# append to MainWindow class:

class MainWindow(QMainWindow):
    # ... existing __init__ ...
    def __init__(self) -> None:
        super().__init__()
        # ... existing setup ...
        self._dragging = False
        self._drag_offset = QPoint()
        self._edge_snap_px = 30

    def mousePressEvent(self, ev) -> None:
        if ev.button() == Qt.LeftButton:
            self._dragging = True
            self._drag_offset = ev.globalPosition().toPoint() - self.frameGeometry().topLeft()
            ev.accept()

    def mouseMoveEvent(self, ev) -> None:
        if self._dragging and (ev.buttons() & Qt.LeftButton):
            new_pos = ev.globalPosition().toPoint() - self._drag_offset
            self.move(new_pos)
            ev.accept()

    def mouseReleaseEvent(self, ev) -> None:
        if ev.button() == Qt.LeftButton and self._dragging:
            self._dragging = False
            self._maybe_snap()
            ev.accept()

    def _maybe_snap(self) -> None:
        screen = QApplication.primaryScreen()
        if screen is None:
            return
        geo = screen.availableGeometry()
        x = self.x()
        snap = self._edge_snap_px
        new_x = x
        # Snap to right edge
        if abs(geo.right() - (x + self.width())) < snap:
            new_x = geo.right() - self.width() + 1
        # Snap to left edge
        elif abs(geo.left() - x) < snap:
            new_x = geo.left()
        if new_x != x:
            self.move(new_x, self.y())
```

**Step 2:** Manual smoke test (drag, release near right edge → snaps)

**Step 3:** Commit

```bash
git add . && git commit -m "feat(ui): drag + edge-snap on right edge only"
```

---

## Phase 11: Windows Focus (Click → Activate CC Terminal)

### Task 11.1: Implement win32 window enumerator (TDD where possible)

**Files:**
- Test: `tests/test_windows_focus.py`
- Create: `src/win32/windows_focus.py`

**Step 1:** Implement (integration test on real Windows)

```python
# tests/test_windows_focus.py
import os
from pathlib import Path
from src.win32.windows_focus import find_terminal_for_cwd


def test_find_terminal_returns_none_when_no_match():
    """When no terminal window matches the cwd, returns None."""
    if os.name != "nt":
        return  # skip on non-Windows
    result = find_terminal_for_cwd("C:/this/path/definitely/does/not/exist/xyz123")
    assert result is None
```

**Step 2:** Implement

```python
# src/win32/windows_focus.py
from __future__ import annotations

import ctypes
import os
from ctypes import wintypes
from typing import Optional

if os.name != "nt":
    def find_terminal_for_cwd(*_args, **_kwargs): return None
    def activate_window(*_args, **_kwargs): return False
else:
    import ctypes.wintypes as wt

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    EnumWindows = user32.EnumWindows
    EnumWindowsProc = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    GetWindowThreadProcessId = user32.GetWindowThreadProcessId
    GetWindowTextW = user32.GetWindowTextW
    GetWindowTextLength = user32.GetWindowTextLength
    IsWindowVisible = user32.IsWindowVisible
    SetForegroundWindow = user32.SetForegroundWindow
    ShowWindow = user32.ShowWindow

    _TERMINAL_TITLES = (
        "Claude Code", "cmd.exe", "Windows Terminal", "PowerShell", "pwsh",
    )

    def _pid_cwd(pid: int) -> Optional[str]:
        """Best-effort: get current working directory of a process by PID on Windows.
        Uses GetModuleFileNameW fallback; precise cwd requires NtQueryInformationProcess
        which is not in user32. For our purposes, the title contains the cwd hint.
        """
        return None

    def find_terminal_for_cwd(cwd: str) -> Optional[int]:
        """Find a top-level window whose title contains the cwd basename.
        Returns hwnd or None.
        """
        if not cwd:
            return None
        needle = os.path.basename(cwd.rstrip("/\\")).lower()
        if not needle:
            return None
        found: list[int] = []

        def cb(hwnd, _lparam):
            if not IsWindowVisible(hwnd):
                return True
            length = GetWindowTextLength(hwnd)
            if length == 0:
                return True
            buf = ctypes.create_unicode_buffer(length + 1)
            GetWindowTextW(hwnd, buf, length + 1)
            title = buf.value.lower()
            if any(t.lower() in title for t in _TERMINAL_TITLES) and needle in title:
                found.append(hwnd)
                return False  # stop enumeration
            return True

        EnumWindows(EnumWindowsProc(cb), 0)
        return found[0] if found else None

    def activate_window(hwnd: int) -> bool:
        if not hwnd:
            return False
        ShowWindow(hwnd, 9)   # SW_RESTORE
        return bool(SetForegroundWindow(hwnd))
```

**Step 3:** Wire card click → activate

```python
# In src/ui/signal_bus.py - no change
# In claude_dashboard.py - add after window.show():

def on_card_clicked(session_id: str):
    sess = next((s for s in collector.current_sessions() if s.id == session_id), None)
    if sess is None:
        return
    if os.name == "nt":
        from src.win32.windows_focus import find_terminal_for_cwd, activate_window
        hwnd = find_terminal_for_cwd(sess.cwd)
        if hwnd:
            activate_window(hwnd)

signalBus.cardClicked.connect(on_card_clicked)
```

**Step 4:** Run tests, manual verify

```bash
uv run pytest tests/test_windows_focus.py -v
```

**Step 5:** Commit

```bash
git add . && git commit -m "feat(platform): add Windows terminal focus by cwd basename match"
```

---

## Phase 12: System Tray

### Task 12.1: Tray icon with menu

**Files:**
- Create: `src/ui/tray.py`

**Step 1:** Implement

```python
# src/ui/tray.py
from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from .signal_bus import signalBus


def _build_icon(color: QColor = QColor("#3B82F6")) -> QIcon:
    pm = QPixmap(64, 64)
    pm.fill(QColor(0, 0, 0, 0))
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(color)
    p.setPen(0)
    p.drawEllipse(8, 8, 48, 48)
    p.end()
    return QIcon(pm)


def build_tray(app: QApplication, window, collector, cfg_path: Path) -> QSystemTrayIcon:
    tray = QSystemTrayIcon(_build_icon(), app)
    tray.setToolTip("Claude Sessions Dashboard")
    menu = QMenu()
    a_show = QAction("Show / Hide", menu)
    a_show.triggered.connect(lambda: (window.show(), window.raise_()) if window.isHidden() else window.hide())
    a_reload = QAction("Reload config", menu)
    a_reload.triggered.connect(lambda: signalBus.requestReloadConfig.emit())
    a_pause = QAction("Pause polling", menu, checkable=True)
    a_pause.toggled.connect(lambda on: signalBus.requestPause.emit(on))
    a_quit = QAction("Quit", menu)
    a_quit.triggered.connect(app.quit)
    menu.addAction(a_show)
    menu.addAction(a_reload)
    menu.addAction(a_pause)
    menu.addSeparator()
    menu.addAction(a_quit)
    tray.setContextMenu(menu)
    tray.activated.connect(lambda reason: (window.show(), window.raise_()) if reason == QSystemTrayIcon.Trigger else None)
    tray.show()
    return tray
```

**Step 2:** Wire config reload + close-to-tray in `claude_dashboard.py`

```python
# in main(), after tray setup:

def on_reload_config():
    global cfg
    cfg = Config.from_file(cfg_path)
    collector._poll_interval_ms = cfg.poll_interval_ms
    collector._recent_seconds = cfg.recent_seconds
    # ... apply other fields

def on_pause(paused: bool):
    if paused:
        collector.stop()
    else:
        collector.start()

signalBus.requestReloadConfig.connect(on_reload_config)
signalBus.requestPause.connect(on_pause)
```

**Step 3:** Manual smoke: tray icon visible, right-click shows menu, Quit exits

**Step 4:** Commit

```bash
git add . && git commit -m "feat(ui): add system tray with show/reload/pause/quit"
```

---

## Phase 13: Single-Instance Lock

### Task 13.1: QLocalServer based lock

**Files:**
- Create: `src/utils/single_instance.py`
- Modify: `claude_dashboard.py`

**Step 1:** Implement

```python
# src/utils/single_instance.py
from __future__ import annotations

from PySide6.QtCore import QObject
from PySide6.QtNetwork import QLocalServer, QLocalSocket


SOCKET_NAME = "claude-sessions-dashboard-singleton"


def try_acquire_or_notify(parent: QObject | None = None) -> tuple[QLocalServer | None, bool]:
    """Try to become the singleton. Returns (server, is_primary).
    If another instance is already running, sends a 'show' ping to it and returns (None, False).
    """
    # Probe: try connecting to existing
    sock = QLocalSocket()
    sock.connectToServer(SOCKET_NAME)
    if sock.waitForConnected(300):
        sock.write(b"show")
        sock.flush()
        sock.disconnectFromServer()
        return None, False

    server = QLocalServer(parent)
    QLocalServer.removeServer(SOCKET_NAME)
    if not server.listen(SOCKET_NAME):
        return None, True   # give up; run anyway
    return server, True
```

**Step 2:** Wire in `claude_dashboard.py`

```python
# at top of main():
from src.utils.single_instance import try_acquire_or_notify

server, is_primary = try_acquire_or_notify()
if not is_primary:
    # Another instance is running; our message told it to show. Exit.
    sys.exit(0)
```

**Step 3:** Hook the "show" message in main window (when secondary pings)

```python
# in main(), after server is set:
def on_new_connection():
    client = server.nextPendingConnection()
    if client:
        client.readyRead.connect(lambda: _handle_ping(client))

def _handle_ping(client):
    data = bytes(client.readAll()).decode("utf-8", "ignore").strip()
    if "show" in data:
        if window.isHidden():
            window.show()
        window.raise_()
        window.activateWindow()
    client.disconnectFromServer()

server.newConnection.connect(on_new_connection)
```

**Step 4:** Commit

```bash
git add . && git commit -m "feat(utils): add single-instance lock via QLocalServer"
```

---

## Phase 14: Autostart (Task Scheduler)

### Task 14.1: schtasks wrapper

**Files:**
- Create: `src/win32/autostart.py`

**Step 1:** Implement

```python
# src/win32/autostart.py
from __future__ import annotations

import os
import shlex
import subprocess
from pathlib import Path

TASK_NAME = "ClaudeSessionsDashboard"


def _exe_path() -> str:
    """Return the path used to launch the app at startup.
    When running as a PyInstaller bundle, sys.executable is the .exe.
    When running from source, use 'uv run python claude_dashboard.py'.
    """
    if getattr(os, "frozen", False):
        return os.path.abspath(sys.executable)
    # Source run: launch via uv
    project_dir = Path(__file__).resolve().parents[2]
    script = project_dir / "claude_dashboard.py"
    return f'cmd /c "cd /D {project_dir} && uv run python {script}"'


def is_enabled() -> bool:
    if os.name != "nt":
        return False
    out = subprocess.run(
        ["schtasks", "/Query", "/TN", TASK_NAME],
        capture_output=True, text=True,
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
        capture_output=True, text=True,
    )
    return out.returncode == 0
```

**Step 2:** Add to tray menu (extend `tray.py`)

```python
# in tray.py, add toggle action:
a_autostart = QAction("Start on login", menu, checkable=True)
a_autostart.setChecked(is_enabled())
def toggle_autostart(on):
    enable() if on else disable()
a_autostart.toggled.connect(toggle_autostart)
menu.addAction(a_autostart)
```

**Step 3:** Verify

```bash
uv run python -c "from src.win32.autostart import is_enabled, enable; print('before:', is_enabled()); print('enable:', enable()); print('after:', is_enabled())"
```

Expected: shows before/after states. Disable afterward for clean dev state.

**Step 4:** Commit

```bash
git add . && git commit -m "feat(platform): add Windows Task Scheduler autostart wrapper"
```

---

## Phase 15: PyInstaller Packaging

### Task 15.1: Create spec file

**Files:**
- Create: `scripts/build_exe.py`
- Create: `claude-dashboard.spec`

**Step 1:** Write build script

```python
# scripts/build_exe.py
"""Build ClaudeDashboard.exe via PyInstaller."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "claude-dashboard.spec"


def main() -> int:
    if not SPEC.exists():
        # Generate spec on the fly
        spec_text = f"""\
# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules

block_cipher = None

a = Analysis(
    ['{(ROOT / 'claude_dashboard.py')!s}'],
    pathex=['{ROOT!s}'],
    binaries=[],
    datas=[],
    hiddenimports=collect_submodules('PySide6'),
    hookspath=[],
    runtime_hooks=[],
    excludes=['tkinter', 'unittest', 'pydoc'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(
    pyz, a.scripts, a.binaries, a.zipfiles, a.datas, [],
    name='ClaudeDashboard',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=False,    # windowed (no console)
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='{(ROOT / 'assets' / 'icon.ico')!s}' if (ROOT / 'assets' / 'icon.ico').exists() else None,
)
"""
        SPEC.write_text(spec_text, encoding="utf-8")
    cmd = [sys.executable, "-m", "PyInstaller", str(SPEC), "--noconfirm", "--clean"]
    print(">>>", " ".join(cmd))
    return subprocess.call(cmd, cwd=ROOT)


if __name__ == "__main__":
    sys.exit(main())
```

**Step 2:** Run build

```bash
mkdir -p assets  # optional: place icon.ico here
uv run python scripts/build_exe.py
```

Expected: `dist/ClaudeDashboard.exe` produced.

**Step 3:** Smoke test the exe

```bash
./dist/ClaudeDashboard.exe &
sleep 3
# Check it runs (no console window should appear)
taskkill /F /IM ClaudeDashboard.exe
```

**Step 4:** Commit

```bash
git add . && git commit -m "build: add PyInstaller spec and build script"
```

---

### Task 15.2: README with install/usage

**Files:**
- Create: `README.md`

**Step 1:** Write README

```markdown
# Claude Sessions Dashboard

A Windows desktop floating status bar that visualizes all active Claude Code sessions via indicator lights and context percentages.

![screenshot](docs/screenshot.png)

## Features

- **Indicator lights** (5 states) for every active Claude Code session
- **Context %** per session (with color-coded progress bar)
- **Current task subtitle** (e.g., "Edit: claude_dashboard.py", "Bash: pip install pyside6")
- **Hover expand/collapse** (40px ↔ 280px), right-edge snap
- **Click card** to activate the corresponding Claude Code terminal
- **System tray** with pause/reload/quit
- **Single instance** — second launch focuses the existing one
- **Autostart** via Windows Task Scheduler

## Install (from source)

```bash
git clone <repo>
cd claude-sessions-dashboard
uv sync --extra dev
uv run python claude_dashboard.py
```

## Install (from exe)

1. Download `ClaudeDashboard.exe` from Releases
2. Double-click to run (first run creates `%APPDATA%/ClaudeSessionsDashboard/config.ini`)
3. Right-click tray icon → "Start on login" to enable autostart

## Build exe

```bash
uv run python scripts/build_exe.py
# → dist/ClaudeDashboard.exe
```

## Configuration

Config file: `%APPDATA%/ClaudeSessionsDashboard/config.ini`

| Key | Default | Description |
|-----|---------|-------------|
| `poll_interval_ms` | 2000 | How often to scan JSONL files |
| `stale_after_minutes` | 30 | File mtime older → hidden |
| `recent_seconds` | 60 | Last entry older → hidden |
| `context_max_tokens` | 1000000 | Max context window for % calc (MiniMax-M3 = 1M) |
| `auto_start` | true | Start on login (via Task Scheduler) |

## License

MIT
```

**Step 2:** Commit

```bash
git add . && git commit -m "docs: add README with install/usage/build instructions"
```

---

## Phase 16: End-to-End Verification

### Task 16.1: Run with synthetic CC sessions

**Step 1:** Create fixture script that simulates 3 active sessions writing to JSONL

```bash
mkdir -p tests/integration
```

```python
# tests/integration/fake_cc.py
"""Simulate 3 Claude Code sessions by writing JSONL to a temp dir."""
import json
import os
import sys
import time
import random
from datetime import datetime, timezone
from pathlib import Path

# Override CLAUDE_CONFIG_DIR to a temp dir
target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(os.environ["FAKE_CLAUDE_DIR"])
target.mkdir(parents=True, exist_ok=True)

sessions = [
    {"id": "alpha", "title": "Refactor parser", "tool": "Edit", "input": {"file_path": "/repo/src/parser.py"}, "status": "working"},
    {"id": "beta",  "title": "Install deps",   "tool": "Bash", "input": {"command": "uv add pyinstaller"},            "status": "permission"},
    {"id": "gamma", "title": "Idle chat",      "tool": None,   "input": {},                                       "status": "idle"},
]

# Write initial JSONL files
for s in sessions:
    p = target / f"{s['id']}.jsonl"
    with open(p, "w", encoding="utf-8") as f:
        f.write(json.dumps({"type": "last-prompt", "sessionId": s["id"]}) + "\n")
        f.write(json.dumps({"type": "ai-title", "aiTitle": s["title"], "sessionId": s["id"]}) + "\n")
        if s["tool"]:
            f.write(json.dumps({
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [{"type": "tool_use", "id": "t1", "name": s["tool"], "input": s["input"]}],
                    "usage": {"input_tokens": random.randint(10000, 900000),
                              "cache_creation_input_tokens": 0,
                              "cache_read_input_tokens": 0,
                              "output_tokens": 100},
                    "model": "claude-sonnet-4-6",
                },
                "stop_reason": "tool_use",
                "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "sessionId": s["id"],
                "cwd": "C:/Users/me/repo",
            }) + "\n")
        else:
            f.write(json.dumps({
                "type": "user",
                "message": {"role": "user", "content": "what's the weather"},
                "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "sessionId": s["id"],
                "cwd": "C:/Users/me/repo",
            }) + "\n")
    print(f"wrote {p}")

# Touch every 2s for 30s to keep them "active"
for _ in range(15):
    time.sleep(2)
    for s in sessions:
        p = target / f"{s['id']}.jsonl"
        os.utime(p, None)
print("done")
```

**Step 2:** Run fake CC + dashboard in two terminals

```bash
# Terminal 1
export FAKE_CLAUDE_DIR=/tmp/fake-claude
export CLAUDE_CONFIG_DIR=/tmp/fake-claude
uv run python tests/integration/fake_cc.py

# Terminal 2
export CLAUDE_CONFIG_DIR=/tmp/fake-claude
uv run python claude_dashboard.py
```

**Step 3:** Visual verify all 3 indicators + cards. Use the win-screenshot skill to capture proof.

---

### Task 16.2: Final acceptance checklist

Run through REQUIREMENTS.md §10 and tick each box. Use `verification-loop` skill.

```markdown
- [ ] 启动 3 个 CC 会话（其中 1 个跑长任务触发 working 闪烁），GUI 3 个指示灯同时显示
- [ ] 鼠标进入窗口 → 200ms 内展开显示卡片；离开 → 500ms 内收起
- [ ] 展开后每张卡片显示副标题（当前工具摘要），格式与表格一致
- [ ] 收起态 hover tooltip 也显示副标题（v1 简化：tooltip 只显示标题和百分比，副标题仅展开时）
- [ ] 拖动到屏幕左/上/下边缘不吸附，拖到右边缘 30px 内吸附回右
- [ ] 单击卡片能把对应终端窗口带到前台
- [ ] context% 数字与 claude-hud statusLine 显示值误差 < 3%
- [ ] 关闭主窗口不退出进程，托盘图标仍在
- [ ] 重启电脑后自动启动（任务计划程序生效）
- [ ] 进程常驻，1 小时内 CPU < 1%、内存 < 100MB
```

Final commit: `git commit -m "chore: pass all acceptance criteria"` (only if checklist is complete).

---

## Summary

Total: **16 phases, ~32 tasks, ~160 bite-sized steps**.

Critical files:
- `src/collector/session_parser.py` — the data-layer brain
- `src/ui/main_window.py` — the UX brain
- `src/win32/windows_focus.py` — the OS-integration glue
- `claude_dashboard.py` — the entrypoint

Run order: Phase 1 → 16, with frequent commits after each task.
