"""Windows terminal focus — find CC terminal window by cwd and activate it.

所有"经常出错"的查找函数都按 [[feedback_buggy-modules-need-full-logs]] 写全日志：
- 进入/退出都记
- 每个分支记返回值
- 异常落 traceback
- 日志写 %TEMP%/csd_click_debug.log（pythonw 黑洞安全）
"""

from __future__ import annotations

import datetime as _dt
import os
import traceback as _tb


def _wf_log(tag: str, msg: str) -> None:
    """windows_focus.py 专用日志，落 %TEMP%/csd_click_debug.log。

    前缀 [wf:<tag>] 方便区分日志来源模块。
    """
    try:
        _p = os.environ.get("TEMP", ".") + os.sep + "csd_click_debug.log"
        with open(_p, "a", encoding="utf-8") as _f:
            _f.write(f"{_dt.datetime.now():%H:%M:%S.%f} [wf:{tag}] {msg}\n")
    except Exception:
        # 日志本身不能崩——吞掉异常避免递归
        pass


if os.name == "nt":
    import ctypes
    import ctypes.wintypes as wt
    import psutil

    _user32 = ctypes.WinDLL("user32", use_last_error=True)
    _GetClassNameW = _user32.GetClassNameW
    _GetWindowRect = _user32.GetWindowRect
    _GetWindowTextLengthW = _user32.GetWindowTextLengthW
    _GetWindowTextW = _user32.GetWindowTextW
    _IsWindowVisible = _user32.IsWindowVisible
    _ShowWindow = _user32.ShowWindow
    _BringWindowToTop = _user32.BringWindowToTop
    _GetForegroundWindow = _user32.GetForegroundWindow
    _SwitchToThisWindow = _user32.SwitchToThisWindow
    _SwitchToThisWindow.argtypes = (wt.HWND, wt.BOOL)
    _FindWindowExW = _user32.FindWindowExW
    _GetWindowThreadProcessId = _user32.GetWindowThreadProcessId

    _TERMINAL_CLASSES = {"ConsoleWindowClass", "CASCADIA_HOSTING_WINDOW_CLASS"}

    def _rect_nonempty(hwnd: int) -> bool:
        rect = wt.RECT()
        if not _GetWindowRect(hwnd, ctypes.byref(rect)):
            return False
        return (rect.right - rect.left) > 0 and (rect.bottom - rect.top) > 0

    def _class_name(hwnd: int) -> str:
        buf = ctypes.create_unicode_buffer(256)
        n = _GetClassNameW(hwnd, buf, 256)
        return buf.value[:n]

    def _find_window_for_process(target_pid: int) -> int | None:
        """FindWindowExW loop: first visible terminal-class window owned by target_pid."""
        _wf_log("fwp", f"enter pid={target_pid}")
        hwnd = 0
        while True:
            hwnd = _FindWindowExW(0, hwnd, None, None)
            if not hwnd:
                break
            pid = wt.DWORD()
            _GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value != target_pid:
                continue
            if not _IsWindowVisible(hwnd):
                continue
            if not _rect_nonempty(hwnd):
                continue
            cls = _class_name(hwnd)
            if cls in _TERMINAL_CLASSES:
                _wf_log("fwp", f"exit -> hwnd={hwnd} class={cls}")
                return hwnd
        _wf_log("fwp", f"exit -> None (no terminal-class window owned by pid={target_pid})")
        return None

    def find_terminal_for_pid(pid: int) -> int | None:
        """Walk the parent chain of a CC process to find its terminal window.

        PID-strict: only returns a hwnd if some ancestor directly owns a visible
        terminal-class window. Skips WindowsTerminal.exe ancestors — multiple WT
        panes share one WT pid, so pid can't disambiguate them. Caller must use
        title/cwd matching for WT-hosted CCs.
        """
        _wf_log("ftp", f"enter pid={pid}")
        if pid <= 0:
            _wf_log("ftp", f"exit -> None (pid<=0)")
            return None
        try:
            p = psutil.Process(pid)
            _wf_log("ftp", f"start walk from pid={pid} name={p.name()}")
            for depth in range(6):
                parent = p.parent()
                if parent is None:
                    _wf_log("ftp", f"  d{depth}: parent=None, stop walk")
                    break
                parent_name = parent.name().lower()
                _wf_log("ftp", f"  d{depth}: parent={parent_name} pid={parent.pid}")
                # 父进程是 WindowsTerminal.exe 时不要走 pid-strict：
                # 多个 pane 共享一个 WT 进程，_find_window_for_process(WT_pid)
                # 只会返回第一个匹配的 CASCADIA 窗口，无法按 pid 区分 pane。
                # 这种情况让调用方走 title/cwd 兜底。
                if parent_name in {"windowsterminal.exe", "wt.exe"}:
                    _wf_log("ftp", f"  d{depth}: parent is WT, return None (caller uses title match)")
                    return None
                hwnd = _find_window_for_process(parent.pid)
                if hwnd:
                    _wf_log("ftp", f"  d{depth}: matched hwnd={hwnd} via pid={parent.pid}")
                    return hwnd
                p = parent
            _wf_log("ftp", f"exit -> None (no ancestor owned a terminal window)")
            return None
        except (psutil.NoSuchProcess, psutil.AccessDenied) as _e:
            _wf_log("ftp", f"exit -> None (psutil {type(_e).__name__}: {_e})")
            return None
        except Exception as _e:
            _wf_log("ftp", f"exit -> None (UNEXPECTED {type(_e).__name__}: {_e})")
            _wf_log("ftp", _tb.format_exc())
            return None

    def find_terminal_for_cwd(cwd: str) -> int | None:
        _wf_log("fcwd", f"enter cwd={cwd!r}")
        if not cwd:
            _wf_log("fcwd", f"exit -> None (empty cwd)")
            return None
        needle = os.path.basename(cwd.rstrip("/\\")).lower()
        if not needle:
            _wf_log("fcwd", f"exit -> None (empty needle)")
            return None
        _wf_log("fcwd", f"needle={needle!r}")
        match_count = 0
        hwnd = 0
        while True:
            hwnd = _FindWindowExW(0, hwnd, None, None)
            if not hwnd:
                break
            if not _IsWindowVisible(hwnd):
                continue
            n = _GetWindowTextLengthW(hwnd)
            if n == 0:
                continue
            buf = ctypes.create_unicode_buffer(n + 1)
            _GetWindowTextW(hwnd, buf, n + 1)
            title = buf.value.lower()
            if needle in title:
                cls = _class_name(hwnd)
                if cls in _TERMINAL_CLASSES or "powershell" in title or "cmd" in title:
                    match_count += 1
                    _wf_log("fcwd", f"  match #{match_count} hwnd={hwnd} cls={cls} title={title[:40]!r}")
                    _wf_log("fcwd", f"exit -> hwnd={hwnd}")
                    return hwnd
        _wf_log("fcwd", f"exit -> None (0 matches)")
        return None

    def find_terminal_for_title(needle: str) -> int | None:
        """Find visible terminal-class window whose title contains needle.

        Used to disambiguate multiple Windows Terminal panes (all sharing one
        WT pid) by matching the pane title to the CC session title (project name
        from JSONL metadata). WT pane titles typically include the working dir
        or running task name.
        """
        _wf_log("ftit", f"enter needle={needle!r}")
        if not needle:
            _wf_log("ftit", f"exit -> None (empty needle)")
            return None
        needle_lower = needle.strip().lower()
        if len(needle_lower) < 2:
            _wf_log("ftit", f"exit -> None (needle too short)")
            return None
        hwnd = 0
        while True:
            hwnd = _FindWindowExW(0, hwnd, None, None)
            if not hwnd:
                break
            if not _IsWindowVisible(hwnd):
                continue
            cls = _class_name(hwnd)
            if cls not in _TERMINAL_CLASSES:
                continue
            n = _GetWindowTextLengthW(hwnd)
            if n == 0:
                continue
            buf = ctypes.create_unicode_buffer(n + 1)
            _GetWindowTextW(hwnd, buf, n + 1)
            title_lower = buf.value.lower()
            if needle_lower in title_lower:
                _wf_log("ftit", f"  match hwnd={hwnd} cls={cls} title={buf.value[:50]!r}")
                _wf_log("ftit", f"exit -> hwnd={hwnd}")
                return hwnd
        _wf_log("ftit", f"exit -> None (no title contains {needle!r})")
        return None

    def _find_largest_visible_terminal() -> int | None:
        """Return the largest visible terminal-class window. Last-resort fallback."""
        _wf_log("flvt", f"enter")
        best, best_area = None, 0
        hwnd = 0
        while True:
            hwnd = _FindWindowExW(0, hwnd, None, None)
            if not hwnd:
                break
            if not _IsWindowVisible(hwnd):
                continue
            if _class_name(hwnd) not in _TERMINAL_CLASSES:
                continue
            rect = wt.RECT()
            if not _GetWindowRect(hwnd, ctypes.byref(rect)):
                continue
            area = (rect.right - rect.left) * (rect.bottom - rect.top)
            if area > best_area:
                best_area, best = area, hwnd
        _wf_log("flvt", f"exit -> hwnd={best} area={best_area}")
        return best

    def list_visible_terminals() -> list[dict]:
        """枚举所有可见 terminal-class 窗口，给右键手动配对菜单用。

        返回 [{hwnd, pid, class, title, width, height}, ...]。
        按面积从大到小排序。
        """
        out: list[dict] = []
        hwnd = 0
        while True:
            hwnd = _FindWindowExW(0, hwnd, None, None)
            if not hwnd:
                break
            if not _IsWindowVisible(hwnd):
                continue
            cls = _class_name(hwnd)
            if cls not in _TERMINAL_CLASSES:
                continue
            if not _rect_nonempty(hwnd):
                continue
            pid = wt.DWORD()
            _GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            rect = wt.RECT()
            _GetWindowRect(hwnd, ctypes.byref(rect))
            n = _GetWindowTextLengthW(hwnd)
            title = ""
            if n > 0:
                buf = ctypes.create_unicode_buffer(n + 1)
                _GetWindowTextW(hwnd, buf, n + 1)
                title = buf.value
            out.append(
                {
                    "hwnd": int(hwnd),
                    "pid": int(pid.value),
                    "class": cls,
                    "title": title,
                    "width": rect.right - rect.left,
                    "height": rect.bottom - rect.top,
                }
            )
        out.sort(key=lambda d: d["width"] * d["height"], reverse=True)
        _wf_log("lvt", f"found {len(out)} visible terminal(s)")
        for _t in out:
            _wf_log(
                "lvt",
                f"  hwnd={_t['hwnd']} pid={_t['pid']} cls={_t['class']} "
                f"title={_t['title'][:30]!r} {_t['width']}x{_t['height']}",
            )
        return out

    def is_window_valid(hwnd: int) -> bool:
        """检查 hwnd 是否仍然指向一个真实窗口（防止 WT 重启后 hwnd 被复用）。"""
        if not hwnd:
            _wf_log("iwv", f"hwnd=0 -> False")
            return False
        vis = _IsWindowVisible(hwnd)
        cls = _class_name(hwnd)
        rect_ok = _rect_nonempty(hwnd)
        result = bool(vis and cls in _TERMINAL_CLASSES and rect_ok)
        _wf_log(
            "iwv",
            f"hwnd={hwnd} visible={vis} cls={cls} rect_ok={rect_ok} class_match={cls in _TERMINAL_CLASSES} -> {result}",
        )
        return result

    def list_terminals_for_session(
        session_title: str | None,
        session_subtitle: str | None = None,
        paired_hwnd: int | None = None,
    ) -> tuple[list[dict], bool]:
        """按 session 过滤终端列表，给右键菜单用。

        返回 (candidates, fallback_to_all)：
        - candidates: 列表，配对的在最前（若仍 valid），其余按 title 匹配 + 面积排序
        - fallback_to_all: True 表示 session 没有任何匹配项、菜单要显示全部终端

        匹配规则（不区分大小写子串）：
        - title 含 session_title 或 session_subtitle

        排序：
        1. paired_hwnd 有效且在候选里 → 最前
        2. 标题匹配的按面积降序
        3. 其它按面积降序
        """
        all_terms = list_visible_terminals()
        _wf_log(
            "lts",
            f"enter title={session_title!r} subtitle={session_subtitle!r} paired_hwnd={paired_hwnd} all_count={len(all_terms)}",
        )
        needles: list[str] = []
        if session_title:
            needles.append(session_title.strip().lower())
        if session_subtitle:
            needles.append(session_subtitle.strip().lower())
        needles = [n for n in needles if len(n) >= 2]
        _wf_log("lts", f"needles={needles}")

        matched: list[dict] = []
        others: list[dict] = []
        for t in all_terms:
            tl = t["title"].lower()
            if any(n in tl for n in needles):
                matched.append(t)
            else:
                others.append(t)
        _wf_log("lts", f"matched={len(matched)} others={len(others)}")

        # 配对项插到最前（若 valid）
        paired_item: dict | None = None
        if paired_hwnd and is_window_valid(paired_hwnd):
            for t in all_terms:
                if t["hwnd"] == paired_hwnd:
                    paired_item = t
                    break
        if paired_item is not None:
            # 从 matched/others 移除再加到最前
            matched = [t for t in matched if t["hwnd"] != paired_hwnd]
            others = [t for t in others if t["hwnd"] != paired_hwnd]
            result = [paired_item] + matched + others
        else:
            result = matched + others

        # 排序：除配对外按面积降序
        if paired_item is not None:
            tail = result[1:]
            tail.sort(key=lambda d: d["width"] * d["height"], reverse=True)
            result = [paired_item] + tail
        else:
            result.sort(key=lambda d: d["width"] * d["height"], reverse=True)

        fallback = len(matched) == 0 and paired_item is None
        _wf_log(
            "lts",
            f"exit -> {len(result)} item(s) paired_first={paired_item is not None} fallback_to_all={fallback}",
        )
        return result, fallback

    def activate_window(hwnd: int) -> bool:
        """Bring a window to the foreground, even from a background (pythonw) process."""
        _wf_log("act", f"enter hwnd={hwnd}")
        if not hwnd:
            _wf_log("act", f"exit -> False (empty hwnd)")
            return False
        import time as _time
        # ALT key sim — grants foreground activation rights
        _wf_log("act", f"  ALT down")
        _user32.keybd_event(0x12, 0, 0, 0)
        _wf_log("act", f"  ALT up")
        _user32.keybd_event(0x12, 0, 2, 0)
        _wf_log("act", f"  ShowWindow(SW_RESTORE)")
        _ShowWindow(hwnd, 9)
        _wf_log("act", f"  BringWindowToTop")
        _BringWindowToTop(hwnd)
        _wf_log("act", f"  SwitchToThisWindow")
        _SwitchToThisWindow(hwnd, True)
        _time.sleep(0.05)
        fg = _GetForegroundWindow()
        match = fg == hwnd
        _wf_log("act", f"  foreground_after={fg} expected={hwnd} match={match}")
        _wf_log("act", f"exit -> {match}")
        return match

else:

    def find_terminal_for_cwd(*_args, **_kwargs):
        return None

    def activate_window(*_args, **_kwargs):
        return False

    def list_visible_terminals(*_args, **_kwargs):
        return []

    def is_window_valid(*_args, **_kwargs):
        return False

    def list_terminals_for_session(*_args, **_kwargs):
        return [], True