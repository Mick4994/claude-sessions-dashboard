"""Windows terminal focus — find CC terminal window by cwd and activate it."""

from __future__ import annotations

import os

if os.name == "nt":
    import ctypes
    import ctypes.wintypes as wt
    import psutil

    _user32 = ctypes.WinDLL("user32", use_last_error=True)
    _EnumWindows = _user32.EnumWindows
    _EnumWindowsProc = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    _GetWindowTextLengthW = _user32.GetWindowTextLengthW
    _GetWindowTextW = _user32.GetWindowTextW
    _IsWindowVisible = _user32.IsWindowVisible
    _SetForegroundWindow = _user32.SetForegroundWindow
    _ShowWindow = _user32.ShowWindow
    _AllowSetForegroundWindow = _user32.AllowSetForegroundWindow
    _BringWindowToTop = _user32.BringWindowToTop
    _GetForegroundWindow = _user32.GetForegroundWindow
    _SwitchToThisWindow = _user32.SwitchToThisWindow
    _SwitchToThisWindow.argtypes = (wt.HWND, wt.BOOL)
    _FindWindowExW = _user32.FindWindowExW
    _GetWindowThreadProcessId = _user32.GetWindowThreadProcessId

    _TERMINAL_TITLES = ("Claude Code", "cmd.exe", "Windows Terminal", "PowerShell", "pwsh")

    def _find_window_for_process(target_pid: int) -> int | None:
        """Walk all top-level windows via FindWindowEx (no callback — safe in pythonw).
        Return first visible HWND owned by target_pid."""
        hwnd = 0
        while True:
            hwnd = _FindWindowExW(0, hwnd, None, None)
            if not hwnd:
                break
            pid = wt.DWORD()
            _GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value == target_pid and _IsWindowVisible(hwnd):
                return hwnd
        return None

    def find_terminal_for_pid(pid: int) -> int | None:
        """Walk the parent chain of a CC process to find its terminal window."""
        if pid <= 0:
            return None
        try:
            p = psutil.Process(pid)
            for _ in range(4):
                parent = p.parent()
                if parent is None:
                    break
                hwnd = _find_window_for_process(parent.pid)
                if hwnd:
                    return hwnd
                p = parent
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
        except Exception:
            pass
        return None

    def find_terminal_for_cwd(cwd: str) -> int | None:
        if not cwd:
            return None
        needle = os.path.basename(cwd.rstrip("/\\")).lower()
        if not needle:
            return None
        found: list[int] = []

        def cb(hwnd, _lparam):
            if not _IsWindowVisible(hwnd):
                return True
            length = _GetWindowTextLengthW(hwnd)
            if length == 0:
                return True
            buf = ctypes.create_unicode_buffer(length + 1)
            _GetWindowTextW(hwnd, buf, length + 1)
            title = buf.value.lower()
            if any(t.lower() in title for t in _TERMINAL_TITLES) and needle in title:
                found.append(hwnd)
                return False
            return True

        _EnumWindows(_EnumWindowsProc(cb), 0)
        return found[0] if found else None

    def activate_window(hwnd: int) -> bool:
        """Bring a window to the foreground, even from a background (pythonw) process.

        Uses SwitchToThisWindow (bypasses the foreground lock) with a keybd_event
        ALT-sim to grant foreground activation rights to our thread."""
        if not hwnd:
            return False
        import time as _time

        # Simulate ALT key — grants foreground rights to the calling thread.
        _user32.keybd_event(0x12, 0, 0, 0)  # VK_MENU down
        _user32.keybd_event(0x12, 0, 2, 0)  # VK_MENU up (KEYEVENTF_KEYUP=2)

        _ShowWindow(hwnd, 9)  # SW_RESTORE
        _BringWindowToTop(hwnd)
        _SwitchToThisWindow(hwnd, True)
        _time.sleep(0.05)
        return _GetForegroundWindow() == hwnd

else:

    def find_terminal_for_cwd(*_args, **_kwargs):  # noqa: ARG001
        return None

    def activate_window(*_args, **_kwargs):  # noqa: ARG001
        return False
