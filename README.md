# Claude Sessions Dashboard

Floating always-on-top status bar for active Claude Code sessions — color-coded indicator lights driven by CC hooks.

| Status | Color | Trigger |
|--------|-------|---------|
| WORKING | 🟡 Yellow blink | `UserPromptSubmit` hook |
| IDLE | 🟢 Green | `Stop` / `StopFailure` hook (includes ESC interrupt) |
| PERMISSION | 🔴 Red | `PermissionRequest` hook |
| UNKNOWN | ⚪ Gray | Initial state (before first hook) |

## Architecture

```
CC processes (psutil) ──> ProcessPoller ──> SessionRegistry ──> UI (list add/remove)
CC hooks ──> curl POST ──> HookServer :18721 ──> HookRouter ──> SessionRegistry ──> UI (status color)
JSONL files ──> SessionCollector ──> UI (title / context% / subtitle)
```

**List management** and **indicator status** are fully decoupled.
See [docs/plans/2026-06-21-hook-driven-refactor.md](docs/plans/2026-06-21-hook-driven-refactor.md) for the full architecture.

## Quick Start

### 1. Install dependencies

```bash
cd D:/Codes/claude-sessions-dashboard
uv sync
```

### 2. Start the dashboard

```bash
uv run pythonw claude_dashboard.py
```

The dashboard listens on `localhost:18721` for hook events and polls CC processes every 2 seconds.

### 3. Configure CC hooks

> **IMPORTANT**: CC Switch periodically overwrites `~/.claude/settings.json`.
> All plugin enables, marketplaces, and hooks MUST go in `~/.claude/settings.local.json`
> to survive rewrites.

Add this to `~/.claude/settings.local.json`:

```json
{
  "hooks": {
    "UserPromptSubmit":  [{"hooks": [{"type": "command", "command": "python -c \"import re,sys,urllib.request; t=sys.stdin.read(); m=re.search(r'\\\"session_id\\\"\\s*:\\s*\\\"([^\\\"]+)\\\"',t); sid=m.group(1) if m else ''; urllib.request.urlopen(urllib.request.Request(f'http://127.0.0.1:18721/hook/UserPromptSubmit?sid={sid}',method='POST'))\""}]}],
    "Stop":              [{"hooks": [{"type": "command", "command": "python -c \"import re,sys,urllib.request; t=sys.stdin.read(); m=re.search(r'\\\"session_id\\\"\\s*:\\s*\\\"([^\\\"]+)\\\"',t); sid=m.group(1) if m else ''; urllib.request.urlopen(urllib.request.Request(f'http://127.0.0.1:18721/hook/Stop?sid={sid}',method='POST'))\""}]}],
    "StopFailure":       [{"hooks": [{"type": "command", "command": "python -c \"import re,sys,urllib.request; t=sys.stdin.read(); m=re.search(r'\\\"session_id\\\"\\s*:\\s*\\\"([^\\\"]+)\\\"',t); sid=m.group(1) if m else ''; urllib.request.urlopen(urllib.request.Request(f'http://127.0.0.1:18721/hook/StopFailure?sid={sid}',method='POST'))\""}]}],
    "PermissionRequest": [{"hooks": [{"type": "command", "command": "python -c \"import re,sys,urllib.request; t=sys.stdin.read(); m=re.search(r'\\\"session_id\\\"\\s*:\\s*\\\"([^\\\"]+)\\\"',t); sid=m.group(1) if m else ''; urllib.request.urlopen(urllib.request.Request(f'http://127.0.0.1:18721/hook/PermissionRequest?sid={sid}',method='POST'))\""}]}],
    "PostToolUse":       [{"hooks": [{"type": "command", "command": "python -c \"import re,sys,urllib.request; t=sys.stdin.read(); m=re.search(r'\\\"session_id\\\"\\s*:\\s*\\\"([^\\\"]+)\\\"',t); sid=m.group(1) if m else ''; urllib.request.urlopen(urllib.request.Request(f'http://127.0.0.1:18721/hook/PostToolUse?sid={sid}',method='POST'))\""}]}],
    "PostToolUseFailure":[{"hooks": [{"type": "command", "command": "python -c \"import re,sys,urllib.request; t=sys.stdin.read(); m=re.search(r'\\\"session_id\\\"\\s*:\\s*\\\"([^\\\"]+)\\\"',t); sid=m.group(1) if m else ''; urllib.request.urlopen(urllib.request.Request(f'http://127.0.0.1:18721/hook/PostToolUseFailure?sid={sid}',method='POST'))\""}]}],
    "PermissionDenied":  [{"hooks": [{"type": "command", "command": "python -c \"import re,sys,urllib.request; t=sys.stdin.read(); m=re.search(r'\\\"session_id\\\"\\s*:\\s*\\\"([^\\\"]+)\\\"',t); sid=m.group(1) if m else ''; urllib.request.urlopen(urllib.request.Request(f'http://127.0.0.1:18721/hook/PermissionDenied?sid={sid}',method='POST'))\""}]}]
  }
}
```

### 4. Install as CC plugin (optional)

```bash
# Add marketplace
# (already in settings.local.json extraKnownMarketplaces if you followed step 3)

/plugin install claude-sessions-dashboard@claude-sessions-dashboard
```

> After `/plugin install`, CC Switch may overwrite `settings.json` and drop the enable.
> Ensure `"claude-sessions-dashboard@claude-sessions-dashboard": true` is in
> `~/.claude/settings.local.json` under `enabledPlugins`.

## Config

Edit `%APPDATA%/ClaudeSessionsDashboard/config.ini`:

```ini
[general]
poll_interval_ms = 2000

[behavior]
hook_port = 18721
```

## Development

```bash
uv run pytest                           # 115 tests
uv run python claude_dashboard.py       # run with console output
```

## Requirements

- Windows 10+
- Python 3.12+ (uv-managed venv)
- PySide6 6.7+
- psutil 7.2+

## Repo

https://github.com/Mick4994/claude-sessions-dashboard
