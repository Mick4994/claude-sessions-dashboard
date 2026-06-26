# Architecture

> High-level design of `claude-sessions-dashboard` — a Windows floating
> status bar for active Claude Code sessions.
>
> Last updated: 2026-06-26.

## 1. One-paragraph description

A single Python process (`claude_dashboard.py`, run via `pythonw` for no console)
hosts a PySide6 always-on-top floating window. The window displays one colored
dot per live Claude Code (CC) session. **List management** (which dots show)
is driven by `psutil` polling for CC processes every 2s. **Dot color** is
driven by a localhost HTTP server receiving CC hook callbacks (curl POSTs from
CC itself). The two paths are completely decoupled. Session metadata
(title / context% / subtitle) is parsed from CC's `~/.claude/projects/<cwd>/
*.jsonl` files by tail-reading.

## 2. Architectural pillars

| Pillar | Choice | Why |
|---|---|---|
| List driver | Process polling (`psutil`) | Process existence is the only truth — no false positives from stale JSONL files |
| Color driver | CC hooks via HTTP POST | CC is the single source of truth for its own state; we just observe |
| Metadata | JSONL tail-read (last 128KB) | Cheap; full files can be 10MB+; we only need the most recent assistant turn |
| State machine | 3 states: IDLE / WORKING / PERMISSION | Matches the 3 visually distinct things a session can be doing |
| Default state | IDLE (green) | A session just discovered is, by definition, neither working nor waiting on permission |
| Threading | Registry thread-safe + callbacks; UI on Qt main thread | Hook HTTP server runs in daemon threads; UI never blocks |
| Autostart | `HKCU\...\Run` registry | No admin required; survives most AV scans |
| Single instance | `QLocalServer` on `claude-sessions-dashboard-singleton` | Cross-platform via Qt; second launch pings primary to show window |
| Port | `127.0.0.1:18721` | 15721 is taken by CC Switch |

## 3. Module map

```
claude_dashboard.py              ← entry point (wires everything)
├── src/
│   ├── core/                    ← framework-agnostic primitives
│   │   ├── status.py            ← SessionStatus enum + STATUS_COLORS
│   │   └── session_registry.py  ← thread-safe PID↔SID singleton + callbacks
│   ├── collector/               ← reads CC world (process + JSONL) → Session list
│   │   ├── process_monitor.py   ← psutil: enumerate alive CC processes
│   │   ├── session_scanner.py   ← discover *.jsonl under ~/.claude/projects/
│   │   ├── session_parser.py    ← tail-read one JSONL → metadata fields
│   │   ├── collector.py         ← QTimer poller: process + JSONL → Session[]
│   │   └── models.py            ← Session dataclass + re-export SessionStatus
│   ├── server/                  ← HTTP intake for CC hook callbacks
│   │   ├── hook_server.py       ← stdlib BaseHTTPRequestHandler on 127.0.0.1:18721
│   │   └── router.py            ← event-name → SessionStatus mapping (7 rules)
│   ├── ui/                      ← PySide6 widgets
│   │   ├── main_window.py       ← frameless always-on-top window + hover expand
│   │   ├── indicator_widget.py  ← colored dot + blink animation
│   │   ├── card_widget.py       ← expanded card (dot + title + progress + cwd)
│   │   ├── tray.py              ← system tray icon + menu
│   │   └── signal_bus.py        ← Qt signal hub for cross-component events
│   ├── win32/                   ← Windows-specific (graceful no-op elsewhere)
│   │   ├── autostart.py         ← HKCU Run registry read/write
│   │   └── windows_focus.py     ← ctypes: find/activate CC terminal window
│   └── utils/
│       ├── config.py            ← Config dataclass + INI load/save
│       ├── paths.py             ← %APPDATA% / config path / CC home resolution
│       └── single_instance.py   ← QLocalServer singleton lock
```

## 4. Data flow

### 4.1 List path (process → dots shown)

```
psutil.process_iter()
    ↓ every 2s
ProcessMonitor.alive_sessions()
    ↓ [{pid, cwd}]
SessionCollector.scan_once()
    ↓ for each alive CWD: find matching JSONL → parse metadata
parse_session_metadata() → Session(title, subtitle, context_pct, …, status=IDLE)
    ↓
SessionCollector.sessionsChanged.emit(sessions)
    ↓
claude_dashboard._sync_registry()           ← adds/removes from registry
MainWindow.set_sessions(sessions)           ← rebuilds dot/card list
```

**Decoupling property**: if the hook server is down, dots still appear (and
stay green = IDLE). If psutil fails, dots stay frozen but colors can still
change via hooks.

### 4.2 Color path (hook → dot color)

```
CC fires a hook (e.g. UserPromptSubmit)
    ↓
CC runs the configured command:
    curl -s -X POST 'http://127.0.0.1:18721/hook/UserPromptSubmit?sid=$CLAUDE_SESSION_ID'
    ↓
HookServer._HookHandler.do_POST()
    ↓ parse URL → event="UserPromptSubmit", sid from query
HookRouter.route(event, sid)
    ↓ _EVENT_STATUS["UserPromptSubmit"] = WORKING
SessionRegistry.set_status_by_sid(sid, WORKING)
    ↓ thread-safe; emits on_status_changed callback
claude_dashboard._on_registry_status(entry, WORKING)
    ↓ finds matching Session, mutates .status, re-emits
MainWindow._rebuild() → dot.set_status(WORKING)
    ↓ QTimer blink animation starts (yellow, 1Hz)
```

### 4.3 Click path (card click → terminal focus)

```
User clicks SessionCard
    ↓ SessionCard.clicked.emit(session_id)
signalBus.cardClicked(session_id)
    ↓
claude_dashboard.on_card_clicked(session_id)
    ↓ look up session.cwd
windows_focus.find_terminal_for_cwd(cwd)
    ↓ EnumWindows → match title containing CWD basename + terminal hint
windows_focus.activate_window(hwnd)
    ↓ SetForegroundWindow + ShowWindow(SW_RESTORE)
```

## 5. Key abstractions

### 5.1 `SessionStatus` (3 states, no UNKNOWN)

```python
class SessionStatus(Enum):
    IDLE = "idle"            # green   — CC ready for input
    WORKING = "working"      # yellow blink — CC thinking/calling tools
    PERMISSION = "permission" # red    — CC waiting on user choice/question
```

`STATUS_COLORS` is the canonical color table. Indicator and card both read
from it. **Newly-discovered sessions default to IDLE** — gray/UNKNOWN was
removed because the "I don't know yet" window is sub-millisecond and conveys
zero information.

### 5.2 `SessionRegistry` (single source of truth)

Pure-Python (no Qt dependency). Two indexes:
- `_by_pid: dict[int, SessionEntry]`
- `_by_sid: dict[str, SessionEntry]`

Callbacks (lists of callables, no Qt):
- `on_added(entry)` — fires when a session is registered
- `on_removed(entry)` — fires on unregister
- `on_status_changed(entry, new_status)` — fires when status actually changes

Thread-safe: every mutation holds a `threading.Lock`. UI side wraps these in
Qt Signals via the adapter in `claude_dashboard._sync_registry` /
`_on_registry_status`.

### 5.3 `HookRouter` (event-name → status)

```python
_EVENT_STATUS: dict[str, SessionStatus] = {
    "UserPromptSubmit":   WORKING,
    "Stop":               IDLE,    # also covers ESC interrupt
    "StopFailure":        IDLE,
    "PermissionRequest":  PERMISSION,
    "PostToolUse":        WORKING,
    "PostToolUseFailure": WORKING,
    "PermissionDenied":   WORKING, # user said no → CC continues → back to working
}
```

Unknown events return `False` (logged, 200 to CC, no state change).
Missing/unknown `sid` returns `False` (200 to CC, no state change).

### 5.4 `SessionCollector` (process-only poller)

QTimer-driven, default 2s. On every tick:
1. Enumerate alive CC processes via `ProcessMonitor`
2. Group by encoded CWD (matches `~/.claude/projects/<encoded-cwd>/`)
3. For each alive CWD: pick the Nth most-recent JSONL per Nth CC process
4. Parse metadata via `parse_session_metadata`
5. **Preserve status from previous scan** — hooks may have updated it
6. Compute removed set, emit `sessionsChanged`

JSONL parsing never touches status. Status is **only** updated by hooks.

### 5.5 `MainWindow` (presentation)

- Frameless, `Qt.Tool` (no taskbar), `WindowStaysOnTopHint`, translucent bg
- **Collapsed** (default, 40px wide): vertical stack of `IndicatorDot`s
- **Expanded** (280px wide, on hover): vertical stack of `SessionCard`s
- Hover delay: 200ms expand / 500ms collapse (anti-flicker)
- Drag from collapsed → snap to right edge if within 30px
- Click on card → `signalBus.cardClicked(session_id)`

## 6. Threading model

| Thread | Owns | Notes |
|---|---|---|
| Qt main | All UI widgets, `MainWindow`, `SessionCollector`, `MainWindow` rebuilds | Everything touches Qt here |
| HookServer daemon | `_HookHandler.do_POST`, `HookServer.serve_forever` | Calls into `SessionRegistry` (thread-safe) → callback fires on hook thread → UI work delegated by re-emitting Qt signal from main thread |
| psutil iter | Synchronous, runs on Qt main thread during `scan_once` | 2s cadence is light; ~50ms worst case |

UI mutations always happen on the Qt main thread. The hook callback path
uses `collector.sessionsChanged.emit(...)` from any thread; Qt's signal system
delivers to the main thread automatically when connected with default
`Qt.AutoConnection`.

## 7. Persistence

| Data | Where | Lifecycle |
|---|---|---|
| Config (`config.ini`) | `%APPDATA%\ClaudeSessionsDashboard\config.ini` | Created on first run, hot-reloadable via tray |
| Autostart entry | `HKCU\Software\Microsoft\Windows\CurrentVersion\Run\ClaudeSessionsDashboard` | Created by `enable()`, removed by `disable()` |
| Single-instance socket | Named pipe `claude-sessions-dashboard-singleton` | Created on primary launch, pinged by secondary |
| Session state | In-memory only (`SessionRegistry`) | Lost on exit; rebuilt from processes on restart |
| Window position | Not persisted | v2 candidate |

## 8. Failure modes & invariants

| Failure | Detection | Behavior |
|---|---|---|
| Port 18721 already taken | `OSError` on `HookServer.start()` | Logged warning; dots still work via process polling; colors stay IDLE |
| No JSONL for an alive CC | `parse_session_metadata` returns session with empty metadata | Dot still shows (IDLE); card shows `(untitled)` |
| Hook POST for unknown SID | Router returns `False`, server returns 200 + `note:"unknown sid"` | No state change; logged warning |
| Hook POST with no SID | Router returns `False`, server returns 200 + `note:"missing sid"` | No state change; logged warning |
| Corrupt JSONL line | `parse_session_metadata` skips with `try/except JSONDecodeError` | Other lines still parsed; metadata may be partial |
| psutil access denied | Caught per-process | That process skipped; rest still scanned |
| Dashboard already running | `QLocalServer` listen fails | Secondary instance sends "show" to primary and exits |
| Stale CC process (zombie) | `psutil.ZombieProcess` caught | Skipped; not added to list |

**Hard invariants**:
- `SessionRegistry` is the **only** writer of session status.
- `SessionCollector` never reads/writes status (only metadata).
- `process_monitor` never reads JSONL or hooks.
- `hook_server` never enumerates processes or reads JSONL.
- These three are completely decoupled — any one can fail without breaking the others.

## 9. Configuration

`config.ini` lives at `%APPDATA%\ClaudeSessionsDashboard\config.ini`,
created on first launch from `default_config_text()` in `src/utils/paths.py`.
Hot-reload via tray menu triggers `signalBus.requestReloadConfig`, which
re-reads the file and updates `collector._poll_interval_ms` and
`collector._max_context_tokens`.

| Section | Key | Default | Effect |
|---|---|---|---|
| general | poll_interval_ms | 2000 | SessionCollector QTimer interval |
| general | expand_delay_ms | 200 | MainWindow hover-to-expand delay |
| general | collapse_delay_ms | 500 | MainWindow leave-to-collapse delay |
| general | edge_snap_px | 30 | Drag-and-release snap distance |
| general | indicator_size_px | 12 | IndicatorDot diameter |
| display | context_max_tokens | 1000000 | 1M (MiniMax-M3 context window) |
| display | warning_threshold | 0.70 | Yellow progress at 70% |
| display | critical_threshold | 0.85 | Red progress at 85% |
| behavior | auto_start | true | HKCU Run entry on first enable |
| behavior | hook_port | 18721 | HookServer bind port |

## 10. Deployment topology

```
┌──────────────────────────── Windows host ────────────────────────────┐
│                                                                      │
│  ┌─── CC process #1 (claude.exe) ───────────────┐                    │
│  │  CWD: D:/projA                                │                    │
│  │  $CLAUDE_SESSION_ID=sess-A                    │                    │
│  │  Fires hooks → curl POST to localhost:18721   │                    │
│  └───────────────────────────────────────────────┘                    │
│                                                                      │
│  ┌─── CC process #2 (claude.exe) ───────────────┐                    │
│  │  CWD: D:/projB                                │                    │
│  │  $CLAUDE_SESSION_ID=sess-B                    │                    │
│  │  Fires hooks → curl POST to localhost:18721   │                    │
│  └───────────────────────────────────────────────┘                    │
│                          │                                           │
│                          │ HTTP POST (7 hook types)                  │
│                          ▼                                           │
│  ┌─── Dashboard process (pythonw.exe) ──────────────────────────┐    │
│  │  SessionCollector (QTimer 2s)                                │    │
│  │     → psutil: enumerate alive CC procs                        │    │
│  │     → JSONL tail: parse metadata                              │    │
│  │                                                                │    │
│  │  HookServer (daemon thread, 127.0.0.1:18721)                  │    │
│  │     → HookRouter → SessionRegistry                            │    │
│  │                                                                │    │
│  │  SessionRegistry (thread-safe singleton)                      │    │
│  │     → emits add/remove/status_changed                         │    │
│  │                                                                │    │
│  │  MainWindow (frameless, always-on-top, right edge)            │    │
│  │     → IndicatorDot (collapsed) / SessionCard (expanded)      │    │
│  │                                                                │    │
│  │  SystemTray (quit / pause / reload config)                    │    │
│  └────────────────────────────────────────────────────────────────┘    │
│                          │                                           │
│                          ▼                                           │
│  HKCU\...\Run\ClaudeSessionsDashboard = "D:\...\pythonw.exe"         │
│  → Auto-launches on user login                                       │
└──────────────────────────────────────────────────────────────────────┘
```

## 11. Why these design choices

| Choice | Rejected alternative | Reason |
|---|---|---|
| HKCU Run autostart | Task Scheduler ONLOGON | HKCU needs no admin; TS requires elevation |
| Single-instance via QLocalServer | file lock / PID file | QLocal is Qt-native, cross-platform, also used for "show" pings |
| Stdlib HTTP server | Flask / aiohttp | 7 endpoints, no routing needed; stdlib is sufficient and dependency-light |
| Tail-read JSONL (128KB) | Full read | 10MB+ files exist; only need last assistant turn |
| Process-name substring match (`"claude" in name`) | exact `claude.exe` match | Robust to variants (`claude-code.exe` etc on other machines) |
| CWD-based session→terminal mapping | PID-based | CC doesn't expose its terminal PID cleanly; CWD works in practice |
| Status default = IDLE | Status default = UNKNOWN (gray) | UNKNOWN state added zero info (sub-ms window); IDLE is the truthful "ready for input" |

## 12. Future extensions

| Feature | Where it goes | Complexity |
|---|---|---|
| Token-budget alerts (push at 90%) | new signal in `card_widget.py` | Low |
| Cross-machine monitoring | add `SessionRegistry` remote sync protocol; new `network/` module | High |
| Multi-monitor positioning | `MainWindow._move_to_right_edge` → enumerate `QApplication.screens()` | Medium |
| Session context preview | new `preview_widget.py` + `jsonl_parser` for last user msg | Medium |
| Cost estimation per session | `SessionCollector` adds token-cost calculation from model + usage | Medium |
| Per-session name (instead of just CWD basename) | read CC's `~/.claude/ide/<id>.json` | Low |
| Persistent window position | `QSettings` | Low |
| Restore on reconnect after sleep | `SessionCollector` re-scans immediately on wake signal | Low |

## 13. Cross-references

- [README](../README.md) — install + usage
- [REQUIREMENTS](../REQUIREMENTS.md) — product spec (12 sections)
- [Hook-driven refactor plan](plans/2026-06-21-hook-driven-refactor.md) —
  how we got from JSONL-driven to hook-driven status
- [Test plan](plans/2026-06-21-test-plan.md) — test coverage map
- [Session summary 2026-06-26](session_summary_2026-06-26.md) — latest
  refactor: UNKNOWN/gray removal
