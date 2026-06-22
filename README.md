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
CC hooks ──> POST :18721 ──> HookServer ──> HookRouter ──> SessionRegistry ──> UI (status color)
JSONL files ──> SessionCollector ──> UI (title / context% / subtitle)
```

**List management** (process polling) and **indicator status** (hook events) are fully decoupled.

## Install Order (MUST follow this sequence)

> ⚠ **The order matters.** The dashboard must be running before CC fires any hook,
> and the marketplace must be added before `/plugin install` works.

1. **Add the marketplace** (before installing the plugin — otherwise `/plugin install`
   fails with `Plugin not found in marketplace`).
2. **Install dependencies** and **start the dashboard**.
3. **Set up autostart** so the dashboard runs on every login.
4. **Configure CC hooks** (sends events to the running dashboard).

---

### Step 1 — Add the marketplace

Add to `~/.claude/settings.local.json` under `extraKnownMarketplaces`:

```json
{
  "extraKnownMarketplaces": {
    "claude-sessions-dashboard": {
      "source": { "repo": "Mick4994/claude-sessions-dashboard", "source": "github" }
    }
  }
}
```

Reload CC, then verify with `/plugin marketplace list`.

> **Why this step is easy to miss**: CC Switch overwrites `~/.claude/settings.json`
> on every reload, so marketplace registrations in `settings.json` vanish. Putting
> them in `settings.local.json` makes them survive rewrites.

---

### Step 2 — Install dependencies and start the dashboard

```bash
cd D:/Codes/claude-sessions-dashboard
uv sync
uv run pythonw claude_dashboard.py      # no console window
```

The dashboard listens on `localhost:18721` for hook events and polls CC processes
every 2 seconds. A tray icon appears when it's running.

> ⚠ **Start the dashboard BEFORE configuring hooks in Step 4.** Hooks POST to
> `localhost:18721` — if the dashboard isn't running, the hooks silently fail
> (POST refused) and indicator colors never update. You'll still see sessions
> listed (process polling works independently), but all colors stay gray.

---

### Step 3 — Enable autostart on login

So the dashboard is running before any CC session starts:

```bash
uv run python -c "from src.win32.autostart import enable; print(enable())"
```

This writes an `HKCU\...\Run` registry entry (no admin required). On next login,
Windows launches `pythonw claude_dashboard.py` automatically.

Verify / disable:

```bash
uv run python -c "from src.win32.autostart import is_enabled; print(is_enabled())"
uv run python -c "from src.win32.autostart import disable; print(disable())"
```

---

### Step 4 — Configure CC hooks

> **IMPORTANT**: CC Switch periodically overwrites `~/.claude/settings.json`.
> All hooks MUST go in `~/.claude/settings.local.json` to survive rewrites.

Add this to `~/.claude/settings.local.json` (merge with the marketplace entry
from Step 1):

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

---

### Step 5 — Install as CC plugin (optional)

```bash
/plugin install claude-sessions-dashboard@claude-sessions-dashboard
```

> After `/plugin install`, CC Switch may overwrite `settings.json` and drop the enable.
> Ensure `"claude-sessions-dashboard@claude-sessions-dashboard": true` is in
> `~/.claude/settings.local.json` under `enabledPlugins`.

## Process Matching

Sessions are discovered by scanning running processes via `psutil`. A process is
treated as a Claude Code session if **its executable name contains `claude`**
(e.g. `claude.exe`, `claude-code.exe` — robust to naming variants across
machines/installations). The `.claude-mem/` worker is excluded by CWD.

If sessions don't appear on another machine:
- Confirm the CC executable name contains `claude` (check Task Manager).
- Confirm `~/.claude/projects/<encoded-cwd>/*.jsonl` exists for that session's CWD.

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
uv run pytest                           # tests
uv run python claude_dashboard.py       # run with console output
```

## Requirements

- Windows 10+
- Python 3.12+ (uv-managed venv)
- PySide6 6.7+
- psutil 7.2+

## Repo

https://github.com/Mick4994/claude-sessions-dashboard
