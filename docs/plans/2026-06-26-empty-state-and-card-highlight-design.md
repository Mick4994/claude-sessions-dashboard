# 空态提示 + 悬停高亮 + PID 激活窗口 (2026-06-26)

> 方案 C — PID 重构。9 个文件，~150 行。

## 1. 需求

1. **空态提示**：列表中无会话时，收起态显示呼吸动画 dot，展开态显示 "无活跃 Claude Code 会话" 文字
2. **悬停高亮**：SessionCard 和 IndicatorDot 悬停时视觉反馈
3. **点击激活（bug 修复）**：点击卡片/指示灯可激活对应 CC 终端窗口。现有 `find_terminal_for_cwd` 用标题匹配 cwd basename，但 CC 窗口标题是 `? Claude Code <任务>` 不含目录名，永远匹配不上

## 2. 架构变更

**核心改动**：CC 进程 PID 从 `ProcessMonitor.alive_sessions()` 一路透传到 `windows_focus.find_terminal_for_pid()`，用 PID → 父进程链 → 窗口 HWND 替代标题匹配。

```
ProcessMonitor.alive_sessions()  →  [{pid, cwd}]  (已有)
    ↓ pid
SessionCollector → parse_session_metadata(pid=pid)
    ↓ pid in Session dataclass
SessionRegistry.register_by_sid(pid=pid)
    ↓ pid in SessionEntry
on_card_clicked → registry.get_by_sid(sid).pid
    ↓
windows_focus.find_terminal_for_pid(pid)   ← NEW
    ↓ psutil.Process(pid).parent() chain
EnumWindows → GetWindowThreadProcessId → match
    ↓ hwnd
activate_window(hwnd)
```

## 3. 文件改动

| # | 文件 | 改动 | 行数 |
|---|------|------|------|
| 1 | `src/collector/models.py` | `Session.pid: int = 0` | +1 |
| 2 | `src/collector/collector.py` | `scan_once()` 传 `pid=sess_info["pid"]` | +1 |
| 3 | `src/collector/session_parser.py` | 参数加 `pid: int = 0`，透传到 `Session(...)` | +1 |
| 4 | `src/core/session_registry.py` | `register_by_sid` 收 `pid: int = 0` | +1 |
| 5 | `claude_dashboard.py` | `_sync_registry` 传 pid；`on_card_clicked` 优先用 `find_terminal_for_pid` | +15 |
| 6 | `src/win32/windows_focus.py` | 新增 `find_terminal_for_pid()` + `_find_window_for_process()` | +50 |
| 7 | `src/ui/card_widget.py` | `enterEvent`/`leaveEvent` 切换 hover 背景 | +12 |
| 8 | `src/ui/indicator_widget.py` | dot hover 放大 + click emit + 空态 pulse 模式 | +25 |
| 9 | `src/ui/main_window.py` | 空态文字提示（展开态）+ empty dot（收起态） | +15 |
| 10 | `tests/` | 5 个新测试 | +40 |

## 4. 错误处理

| 场景 | 处理 |
|---|---|
| CC 进程退出（pid 过时） | `psutil.NoSuchProcess` caught → fallback `find_terminal_for_cwd` |
| 权限不足查父进程 | `psutil.AccessDenied` caught → fallback |
| 父进程链无窗口 | `None` → fallback |
| registry 中 sid 不存在 | `entry = None`，静默不激活 |
| 非 Windows 环境 | pid 路径返回 `None`，fallback 到 cwd 路径（现有） |

## 5. 测试清单

| ID | 测试 | 验证 |
|---|---|---|
| TC-030 | `test_find_terminal_for_pid_valid` | mock Process → 返回有效 HWND |
| TC-031 | `test_find_terminal_for_pid_no_parent` | parent()=None → 返回 None |
| TC-032 | `test_find_terminal_for_pid_no_such_process` | NoSuchProcess → 返回 None |
| TC-033 | `test_session_pid_default_zero` | Session 默认 pid=0 |
| TC-034 | `test_register_by_sid_stores_pid` | registry 存/取 pid |
| TC-035 | `test_dot_hover_enlarges` | hover 直径 +2px |
| TC-036 | `test_dot_click_emits_session_id` | click → signalBus 收到 |
| TC-037 | `test_card_hover_style_applied` | hover → stylesheet 变化 |
| TC-038 | `test_empty_state_label` | sessions=[] → QLabel 显示提示 |
| TC-039 | `test_empty_state_pulse_dot` | sessions=[] → breathing dot |
