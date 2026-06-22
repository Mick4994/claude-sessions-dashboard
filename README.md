<p align="center">
  <strong><a href="#english">English</a></strong> | <strong><a href="#中文">中文</a></strong>
</p>

---

<h1 id="english">Claude Sessions Dashboard</h1>

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

---

<h1 id="中文">Claude Sessions Dashboard</h1>

针对活跃 Claude Code 会话的浮窗状态栏 —— 由 CC 钩子驱动的彩色指示灯。

| 状态 | 颜色 | 触发钩子 |
|--------|-------|---------|
| WORKING | 🟡 黄色闪烁 | `UserPromptSubmit` |
| IDLE | 🟢 绿色 | `Stop` / `StopFailure`（含 ESC 中断） |
| PERMISSION | 🔴 红色 | `PermissionRequest` |
| UNKNOWN | ⚪ 灰色 | 初始状态（首次钩子前） |

## 架构

```
CC 进程 (psutil) ──> ProcessPoller ──> SessionRegistry ──> UI（列表增删）
CC 钩子 ──> POST :18721 ──> HookServer ──> HookRouter ──> SessionRegistry ──> UI（状态颜色）
JSONL 文件 ──> SessionCollector ──> UI（标题 / 上下文% / 副标题）
```

**列表管理**（进程轮询）和**指示灯状态**（钩子事件）完全解耦。

## 安装顺序（必须按此顺序）

> ⚠ **顺序很重要。** 仪表盘必须在 CC 触发任何钩子之前启动，
> marketplace 必须在 `/plugin install` 之前添加。

1. **添加 marketplace**（装插件之前，否则 `/plugin install` 报"未找到"）
2. **安装依赖**并**启动仪表盘**
3. **设置开机自启**
4. **配置 CC 钩子**（向正在运行的仪表盘发送事件）

---

### 第 1 步 — 添加 marketplace

在 `~/.claude/settings.local.json` 的 `extraKnownMarketplaces` 下添加：

```json
{
  "extraKnownMarketplaces": {
    "claude-sessions-dashboard": {
      "source": { "repo": "Mick4994/claude-sessions-dashboard", "source": "github" }
    }
  }
}
```

重载 CC，然后用 `/plugin marketplace list` 验证。

> **为什么容易漏这一步**：CC Switch 每次重载都会覆写 `~/.claude/settings.json`，
> 写在 `settings.json` 里的 marketplace 注册会消失。放在 `settings.local.json`
> 才能避免被覆写。

---

### 第 2 步 — 安装依赖并启动仪表盘

```bash
cd D:/Codes/claude-sessions-dashboard
uv sync
uv run pythonw claude_dashboard.py      # 无控制台窗口
```

仪表盘监听 `localhost:18721` 接收钩子事件，每 2 秒轮询 CC 进程。运行后会在系统托盘显示图标。

> ⚠ **先启动仪表盘，再在第 4 步配置钩子。** 钩子 POST 到 `localhost:18721` ——
> 如果仪表盘没运行，POST 会被拒绝，指示灯颜色永远不变。会话列表仍会显示（进程轮询独立工作），
> 但所有颜色都是灰色。

---

### 第 3 步 — 设置开机自启

开机自动运行，确保在任何 CC 会话之前仪表盘已就绪：

```bash
uv run python -c "from src.win32.autostart import enable; print(enable())"
```

这会在 `HKCU\...\Run` 注册表写入开机启动项（**不需要管理员权限**）。下次登录时 Windows 自动启动仪表盘。

验证 / 关闭：

```bash
uv run python -c "from src.win32.autostart import is_enabled; print(is_enabled())"
uv run python -c "from src.win32.autostart import disable; print(disable())"
```

---

### 第 4 步 — 配置 CC 钩子

> **重要**：CC Switch 会定期覆写 `~/.claude/settings.json`。
> 所有钩子**必须**放在 `~/.claude/settings.local.json` 才能避免被覆写。

把以下内容合并到 `~/.claude/settings.local.json`（和第一步的 marketplace 一起）：

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

### 第 5 步 — 安装为 CC 插件（可选）

```bash
/plugin install claude-sessions-dashboard@claude-sessions-dashboard
```

> `/plugin install` 后，CC Switch 可能会覆写 `settings.json` 导致插件被禁用。
> 确保 `~/.claude/settings.local.json` 的 `enabledPlugins` 中包含：
> `"claude-sessions-dashboard@claude-sessions-dashboard": true`

## 进程匹配

通过 `psutil` 扫描运行中的进程来发现会话。如果进程的**可执行文件名包含 `claude`**，
就视为一个 Claude Code 会话（例如 `claude.exe`、`claude-code.exe` —— 在不同机器和
安装方式下都兼容）。`.claude-mem/` 工作进程按 CWD 排除。

如果在另一台机器上会话未显示：
- 确认 CC 可执行文件名包含 `claude`（查看任务管理器）。
- 确认 `~/.claude/projects/<编码后的CWD>/*.jsonl` 存在。

## 配置

编辑 `%APPDATA%/ClaudeSessionsDashboard/config.ini`：

```ini
[general]
poll_interval_ms = 2000

[behavior]
hook_port = 18721
```

## 开发

```bash
uv run pytest                           # 测试
uv run python claude_dashboard.py       # 带控制台输出运行
```

## 系统要求

- Windows 10+
- Python 3.12+（uv 管理虚拟环境）
- PySide6 6.7+
- psutil 7.2+

## 仓库

https://github.com/Mick4994/claude-sessions-dashboard
