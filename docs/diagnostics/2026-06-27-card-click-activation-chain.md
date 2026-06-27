# 卡片点击 → 窗口唤起：全链路诊断

**日期：** 2026-06-27
**项目：** claude-sessions-dashboard
**症状：** 在仪表盘里点击会话卡片，并不会把对应的 Claude Code 终端窗口带到前台。无任何可见反馈、无错误。
**诊断时的代码版本：** HEAD `ef206f1`（工作区干净），但**正在运行的仪表盘至少落后 6 个 commit**（见 N6 与下方的日志证据）。

---

## 一句话结论 — 决定性证据

**`claude_dashboard.py` 调用了 `find_terminal_for_pid`、`find_terminal_for_cwd`、`activate_window`，但从未从 `src.win32.windows_focus` 导入它们。**

结果就是：每次卡片点击都会在 Qt 信号处理函数里抛 `NameError`，而仪表盘以 `pythonw.exe` 启动（无 stderr 终端），这个异常被无声吞掉。

验证脚本 `scripts/verify_activate.py` 自己正确做了 import（`from src.win32 import windows_focus as wf`），所以它一直 PASS——而仪表盘点击永远没反应。

---

## 全链路节点表

| # | 节点 | 文件:行 | 状态 | 证据 / 观察 | 我的假设 |
|---|------|---------|------|------------|---------|
| **N1** | 鼠标命中卡片 | `src/ui/card_widget.py:141`（`mousePressEvent`） | ✅ 已验证 | 点击日志出现 `cardClicked sid=...` | OK |
| **N2** | 卡片发出 `clicked(sid)` | `src/ui/card_widget.py:143` | ✅ 已验证 | 同上日志条目 | OK |
| **N3** | MainWindow 把 `card.clicked` 接到 `signalBus.cardClicked.emit` | `src/ui/main_window.py:134` | ✅ 已验证 | 同上日志条目 | OK |
| **N4** | `signalBus.cardClicked` 信号分发 | `src/ui/signal_bus.py:8` | ✅ 已验证 | 同上日志条目 | OK |
| **N5** | `claude_dashboard.py` 把 `cardClicked` 接到 `on_card_clicked` | `claude_dashboard.py:165` | ✅ 已验证 | `on_card_clicked` 被调用，日志出现 `entry.pid=...` | OK |
| **N6** | **`on_card_clicked` 调用 `find_terminal_for_pid` / `find_terminal_for_cwd` / `activate_window`** | `claude_dashboard.py:147, 156, 158` | 🔴 **缺 import，必坏** | 全项目只有 `scripts/verify_activate.py` 导入了 `windows_focus`，`claude_dashboard.py` 从未导入。`grep -rn "from src.win32" .` 只匹配到 1 处，且不在仪表盘入口。 | **决定性证据**——每次点击抛 `NameError`，被 Qt 信号分发在 `pythonw.exe` 下静默吞掉 |
| **N7** | `registry.get_by_sid(session_id)` 返回 pid | `claude_dashboard.py:143` | ✅ 已验证 | 日志 `entry.pid=25768` / `23252` 等一直非零且合法 | OK |
| **N8** | `find_terminal_for_pid(pid)` 走父链（最多 6 跳，发现 `WindowsTerminal.exe` / `wt.exe` 父进程则用 class 过滤；否则 `_find_window_for_process`） | `src/win32/windows_focus.py:60-82` | ⚠️ 仅在独立脚本验证过（N6 拦截了仪表盘路径） | `verify_activate.py` 通过 | 隔离环境 OK |
| **N9** | `_find_window_for_process` FindWindowExW 循环（找 `parent.pid` 拥有的第一个可见 terminal-class 窗口） | `src/win32/windows_focus.py:41-58` | ✅ 已验证 | 独立脚本通过 | OK |
| **N10** | `_find_any_visible_terminal` 兜底（全系统最大的可见 terminal-class 窗口） | `src/win32/windows_focus.py:84-104` | ✅ 已验证 | 独立脚本通过 | OK |
| **N11** | `find_terminal_for_cwd(cwd)` CWD 标题兜底 | `src/win32/windows_focus.py:106-129` | ⚠️ 仅在独立脚本验证过（N6 拦截了仪表盘路径） | 独立脚本通过 | 隔离环境 OK |
| **N12** | `activate_window(hwnd)`——ALT `keybd_event` 模拟 + `ShowWindow(SW_RESTORE)` + `BringWindowToTop` + `SwitchToThisWindow`；通过 `GetForegroundWindow == hwnd` 校验 | `src/win32/windows_focus.py:131-143` | ✅ 已验证 | 独立 `verify_activate.py` 报 `match: True` | OK |

---

## 证据链

### 1. 缺 import —— `grep` 实证

```bash
$ grep -rn "from src.win32" D:\Codes\claude-sessions-dashboard --include="*.py"
D:\Codes\claude-sessions-dashboard\scripts\verify_activate.py:8:from src.win32 import windows_focus as wf
```

整个仓库里只有这一处 import focus 模块。`claude_dashboard.py` 的 import 列表里包含 `collector`、`registry`、`hook_server`、`router`、`main_window`、`signal_bus`、`tray`、`config`、`paths`、`single_instance`——**唯独没有 `windows_focus`**。

### 2. 点击日志停在 `entry.pid=` —— `NameError` 的典型签名

最新点击日志尾部（`%TEMP%\csd_click_debug.log`）：

```
11:31:50.730422 cardClicked sid=fd7b4484-8c0f-4959-9f52-20620bc78c33
11:31:50.732421   entry.pid=25768
11:31:51.091520 cardClicked sid=1e07e596-7cb4-4828-a016-010df800b6ea
11:31:51.093497   entry.pid=23252
11:31:51.531902 cardClicked sid=fd7b4484-8c0f-4959-9f52-20620bc78c33
11:31:51.531902   entry.pid=25768
```

模式：每次点击精确写出 2 行（位于函数调用之前的日志），然后**什么都没有**。源码 `claude_dashboard.py:149` 应该有 `find_terminal_for_pid(...) → hwnd=...` 这一行，但日志里没有；`activate_window(...) → ...` 也没有；`NO hwnd for sid=...` 也没有。日志写到 `entry.pid` 后紧接着 `find_terminal_for_pid(entry.pid)` 触发 `NameError`，异常从 `on_card_clicked` 向上抛出，被 Qt `Signal.emit` 内部捕获（信号处理器抛异常会被转换为 `QtWarningMsg` 写到 `qDebug`，无人可见）。

### 3. 为什么之前 7+ 次都没抓到

- 仪表盘通过 `pythonw.exe`（无窗口）启动 → `stderr` 没有出口 → `NameError` traceback 用户看不到。
- 之前所有验证都走 `scripts/verify_activate.py`，它**显式做了 import**（`from src.win32 import windows_focus as wf`）→ 独立验证一直通过。
- 后续重构（commit `37906b6`、`0127f99`、`e23798e`、`ef206f1`）都在改 `src/win32/windows_focus.py` 的算法细节——**没有任何一次碰过 `claude_dashboard.py` 的 import 段**，因为它们被看成"focus 模块内部的事"。调用方从来没被重新接线。
- 这正是用户假设的失败形态：**"改动的两段代码没接通"**——N1–N5（UI 点击侧）和 N7–N12（win32 focus 侧）各自都 OK，唯独 N6 这个调用点没接通。

---

## 修复方案（已提交用户审阅，待选项）

### 方案 1 — 最小修复（一行 import）

加一行 import：

```python
# claude_dashboard.py，紧挨现有 src.* import
from src.win32.windows_focus import (
    find_terminal_for_pid,
    find_terminal_for_cwd,
    activate_window,
)
```

然后重启仪表盘复测。**只有在我们相信点击日志能可靠捕获下一次失败时才推荐**——但它对 N7 之后的非 import 错误并不可靠（任何 N7 之后抛的异常又会再次无声丢失）。

### 方案 2 — 最小修复 + 防御性日志（推荐）

import 同方案 1，**另外**把 `on_card_clicked` 整体包 `try/except`，把任何异常 dump 到 `csd_click_debug.log`：

```python
def on_card_clicked(session_id: str):
    import os as _os, datetime as _dt, traceback as _tb
    _log = Path(_os.environ.get("TEMP", ".")) / "csd_click_debug.log"
    def _w(msg: str) -> None:
        with open(_log, "a") as _f:
            _f.write(f"{_dt.datetime.now():%H:%M:%S.%f} {msg}\n")
    try:
        _w(f"cardClicked sid={session_id}")
        hwnd = None
        entry = registry.get_by_sid(session_id)
        if entry and entry.pid:
            _w(f"  entry.pid={entry.pid}")
            hwnd = find_terminal_for_pid(entry.pid)
            _w(f"  find_terminal_for_pid({entry.pid}) -> hwnd={hwnd}")
        if hwnd is None:
            sessions = collector.current_sessions()
            sess = next((s for s in sessions if s.id == session_id), None)
            if sess and sess.cwd:
                _w(f"  fallback cwd={sess.cwd}")
                hwnd = find_terminal_for_cwd(sess.cwd)
                _w(f"  find_terminal_for_cwd -> hwnd={hwnd}")
        if hwnd:
            ok = activate_window(hwnd)
            _w(f"  activate_window({hwnd}) -> {ok}")
        else:
            _w(f"  NO hwnd for sid={session_id}")
    except Exception:
        _w(f"  EXCEPTION: {_tb.format_exc().splitlines()[-1]}")
        with open(_log, "a") as _f:
            _f.write(_tb.format_exc())
```

这样**未来点击路径里任何异常都不会再静默丢失**——无论是当前的 `NameError`，还是将来的 `psutil.NoSuchProcess`、`ctypes.ArgumentError`、`OSError`，全捕获。

---

## 修复后验证计划

1. 停掉正在跑的仪表盘（很可能跑的是旧代码；日志里的 commit 戳写的是 `37906b6`——硬编码字符串，不代表真实运行 commit）。
2. 通过标准启动脚本（`launch_dashboard.ps1` 或等价物）重启仪表盘。
3. 打开 `%TEMP%\csd_click_debug.log`，确认新启动戳出现。
4. 点击一个会话卡片。
5. **预期日志签名（方案 2 修复后）：**
   ```
   cardClicked sid=...
     entry.pid=...
     find_terminal_for_pid(...) -> hwnd=<某个 int>
     activate_window(...) -> True
   ```
6. **预期行为：** 对应 CC 终端窗口（Windows Terminal 或 conhost）跳到前台。
7. 如果 `find_terminal_for_pid -> hwnd=None`，说明 N8–N10 真的失败——回退到 N11（cwd 路径）再测。
8. 如果 `activate_window -> False`，说明 N12 失败——可能是 Windows 前台权限提升问题，独立根因。

---

## 待用户决策

等用户在方案 1（最小 import）和方案 2（import + try/except 日志）之间二选一。推荐方案 2，因为它能防止"异常被吞"这个导致本次 bug 藏了 7+ 轮的失败模式再次发生。