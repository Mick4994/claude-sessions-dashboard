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

    _WT_CLASS = "CASCADIA_HOSTING_WINDOW_CLASS"
    _WT_NAMES = ("windowsterminal.exe", "wt.exe")
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
        Falls back to the largest visible terminal-class window on the system."""
        if pid <= 0:
            return None
        try:
            p = psutil.Process(pid)
            for _ in range(6):
                parent = p.parent()
                if parent is None:
                    break
                parent_name = parent.name().lower()
                # For WindowsTerminal.exe: find any visible WT window
                if parent_name in _WT_NAMES:
                    return _find_any_visible_terminal(class_filter={_WT_CLASS})
                hwnd = _find_window_for_process(parent.pid)
                if hwnd:
                    return hwnd
                p = parent
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
        # Fallback: largest visible terminal window on the system
        return _find_any_visible_terminal()

    def _find_any_visible_terminal(class_filter: set[str] | None = None) -> int | None:
        """Return the largest visible terminal-class window. No psutil — pure FindWindowExW."""
        if class_filter is None:
            class_filter = _TERMINAL_CLASSES
        best, best_area = None, 0
        hwnd = 0
        while True:
            hwnd = _FindWindowExW(0, hwnd, None, None)
            if not hwnd:
                break
            if not _IsWindowVisible(hwnd):
                continue
            if _class_name(hwnd) not in class_filter:
                continue
            rect = wt.RECT()
            if not _GetWindowRect(hwnd, ctypes.byref(rect)):
                continue
            area = (rect.right - rect.left) * (rect.bottom - rect.top)
            if area > best_area:
                best_area, best = area, hwnd
        return best

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
