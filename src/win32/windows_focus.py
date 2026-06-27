"""Windows terminal focus — find CC terminal window by cwd and activate it."""

from __future__ import annotations

import os

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
            if _class_name(hwnd) in _TERMINAL_CLASSES:
                return hwnd
        return None

    def find_terminal_for_pid(pid: int) -> int | None:
        """Walk the parent chain of a CC process to find its terminal window.

        PID-strict: only returns a hwnd if some ancestor directly owns a visible
        terminal-class window. Skips WindowsTerminal.exe ancestors — multiple WT
        panes share one WT pid, so pid can't disambiguate them. Caller must use
        title/cwd matching for WT-hosted CCs.
        """
        if pid <= 0:
            return None
        try:
            p = psutil.Process(pid)
            for _ in range(6):
                parent = p.parent()
                if parent is None:
                    break
                parent_name = parent.name().lower()
                # 父进程是 WindowsTerminal.exe 时不要走 pid-strict：
                # 多个 pane 共享一个 WT 进程，_find_window_for_process(WT_pid)
                # 只会返回第一个匹配的 CASCADIA 窗口，无法按 pid 区分 pane。
                # 这种情况让调用方走 title/cwd 兜底。
                if parent_name in {"windowsterminal.exe", "wt.exe"}:
                    return None
                hwnd = _find_window_for_process(parent.pid)
                if hwnd:
                    return hwnd
                p = parent
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
        return None

    def find_terminal_for_cwd(cwd: str) -> int | None:
        if not cwd:
            return None
        needle = os.path.basename(cwd.rstrip("/\\")).lower()
        if not needle:
            return None
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
                    return hwnd
        return None

    def find_terminal_for_title(needle: str) -> int | None:
        """Find visible terminal-class window whose title contains needle.

        Used to disambiguate multiple Windows Terminal panes (all sharing one
        WT pid) by matching the pane title to the CC session title (project name
        from JSONL metadata). WT pane titles typically include the working dir
        or running task name.
        """
        if not needle:
            return None
        needle_lower = needle.strip().lower()
        if len(needle_lower) < 2:
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
                return hwnd
        return None

    def _find_largest_visible_terminal() -> int | None:
        """Return the largest visible terminal-class window. Last-resort fallback."""
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
        return out

    def is_window_valid(hwnd: int) -> bool:
        """检查 hwnd 是否仍然指向一个真实窗口（防止 WT 重启后 hwnd 被复用）。"""
        if not hwnd:
            return False
        return bool(_IsWindowVisible(hwnd) and _class_name(hwnd) in _TERMINAL_CLASSES)

    def activate_window(hwnd: int) -> bool:
        """Bring a window to the foreground, even from a background (pythonw) process."""
        if not hwnd:
            return False
        import time as _time
        # ALT key sim — grants foreground activation rights
        _user32.keybd_event(0x12, 0, 0, 0)
        _user32.keybd_event(0x12, 0, 2, 0)
        _ShowWindow(hwnd, 9)
        _BringWindowToTop(hwnd)
        _SwitchToThisWindow(hwnd, True)
        _time.sleep(0.05)
        return _GetForegroundWindow() == hwnd

else:

    def find_terminal_for_cwd(*_args, **_kwargs):
        return None

    def activate_window(*_args, **_kwargs):
        return False

    def list_visible_terminals(*_args, **_kwargs):
        return []

    def is_window_valid(*_args, **_kwargs):
        return False
