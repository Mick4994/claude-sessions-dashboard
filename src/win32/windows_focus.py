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
    _SetForegroundWindow = _user32.SetForegroundWindow
    _ShowWindow = _user32.ShowWindow
    _AllowSetForegroundWindow = _user32.AllowSetForegroundWindow
    _BringWindowToTop = _user32.BringWindowToTop
    _GetForegroundWindow = _user32.GetForegroundWindow
    _SwitchToThisWindow = _user32.SwitchToThisWindow
    _SwitchToThisWindow.argtypes = (wt.HWND, wt.BOOL)
    _FindWindowExW = _user32.FindWindowExW
    _GetWindowThreadProcessId = _user32.GetWindowThreadProcessId
    _EnumWindows = _user32.EnumWindows
    _EnumWindowsProc = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)

    # Windows Terminal hosting window class — used as a special case when
    # walking the parent chain hits WindowsTerminal.exe (the WT GUI hosts
    # powershell/cmd in ConPTY tabs; the powershell process itself has no
    # visible top-level window).
    _WT_CLASS = "CASCADIA_HOSTING_WINDOW_CLASS"
    _WT_NAMES = ("windowsterminal.exe", "wt.exe")
    _TERMINAL_TITLES = ("Claude Code", "cmd.exe", "Windows Terminal", "PowerShell", "pwsh")

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
        """Return first visible top-level HWND owned by target_pid with non-empty rect.
        Skips hidden stub windows like PseudoConsoleWindow."""
        hwnd = 0
        while True:
            hwnd = _FindWindowExW(0, hwnd, None, None)
            if not hwnd:
                break
            pid = wt.DWORD()
            _GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value == target_pid and _IsWindowVisible(hwnd) and _rect_nonempty(hwnd):
                return hwnd
        return None

    def _find_wt_window_for_pid(target_pid: int) -> int | None:
        """Find a visible CASCADIA_HOSTING_WINDOW_CLASS window. We can't directly
        map a powershell PID to a WT tab, so return the first visible WT window
        whose tree includes target_pid (parents or children)."""
        # First try: WT window owned by a process that's a parent of target_pid.
        try:
            target_p = psutil.Process(target_pid)
            ancestor_pids: set[int] = set()
            cur = target_p
            for _ in range(8):
                ancestor_pids.add(cur.pid)
                par = cur.parent()
                if par is None:
                    break
                cur = par
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            ancestor_pids = set()

        found: list[int] = []

        def cb(hwnd, _):
            if not _IsWindowVisible(hwnd):
                return True
            if _class_name(hwnd) != _WT_CLASS:
                return True
            pid = wt.DWORD()
            _GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            # Either WT directly owns target, or a descendant of WT owns target.
            if pid.value in ancestor_pids:
                found.append(hwnd)
                return False
            # Or target is a descendant of the WT process.
            try:
                p = psutil.Process(pid.value)
                kids = {c.pid for c in p.children(recursive=True)}
                if target_pid in kids:
                    found.append(hwnd)
                    return False
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
            return True

        _EnumWindows(_EnumWindowsProc(cb), 0)
        return found[0] if found else None

    def find_terminal_for_pid(pid: int) -> int | None:
        """Walk the parent chain of a CC process to find its terminal window.

        Special case: when the chain hits WindowsTerminal.exe, the actual visible
        window is WT's CASCADIA_HOSTING_WINDOW_CLASS (powershel.exe inside a
        WT ConPTY tab has no visible top-level window of its own)."""
        if pid <= 0:
            return None
        try:
            p = psutil.Process(pid)
            for _ in range(8):
                parent = p.parent()
                if parent is None:
                    break
                parent_name = parent.name().lower()
                if parent_name in _WT_NAMES:
                    # WT host — find the right WT window.
                    return _find_wt_window_for_pid(parent.pid)
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
            if not _rect_nonempty(hwnd):
                return True
            length = _GetWindowTextLengthW(hwnd)
            if length == 0:
                return True
            buf = ctypes.create_unicode_buffer(length + 1)
            _GetWindowTextW(hwnd, buf, length + 1)
            title = buf.value.lower()
            cls = _class_name(hwnd).lower()
            # Match by title substring or by known terminal class.
            if cls == _WT_CLASS.lower() or any(t.lower() in title for t in _TERMINAL_TITLES):
                if needle in title:
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
