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
                cls = _class_name(hwnd)
                if cls in _TERMINAL_CLASSES:
                    return hwnd
        return None

    def _find_wt_window_for_pid(powershell_pid: int, cwd: str = "") -> int | None:
        """Find the visible CASCADIA_HOSTING_WINDOW_CLASS window whose process tree
        includes powershell_pid. Disambiguates by title match then by largest area.
        Uses FindWindowExW loop (no callback) — safe in pythonw."""
        cand: list[tuple[int, int, int]] = []  # (priority, -area, hwnd)
        needle = os.path.basename(cwd.rstrip("/\\")).lower() if cwd else ""
        hwnd = 0
        while True:
            hwnd = _FindWindowExW(0, hwnd, None, None)
            if not hwnd:
                break
            if not _IsWindowVisible(hwnd):
                continue
            if _class_name(hwnd) != _WT_CLASS:
                continue
            pid = wt.DWORD()
            _GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            try:
                wt_p = psutil.Process(pid.value)
                kids = {c.pid for c in wt_p.children(recursive=True)}
                if powershell_pid not in kids:
                    continue
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
            r = wt.RECT()
            area = 0
            if _GetWindowRect(hwnd, ctypes.byref(r)):
                area = (r.right - r.left) * (r.bottom - r.top)
            title = ""
            n = _GetWindowTextLengthW(hwnd)
            if n > 0:
                buf = ctypes.create_unicode_buffer(n + 1)
                _GetWindowTextW(hwnd, buf, n + 1)
                title = buf.value.lower()
            priority = 0 if (needle and needle in title) else 1
            cand.append((priority, -area, hwnd))
        if not cand:
            return None
        cand.sort(key=lambda x: (x[0], x[1]))
        return cand[0][2]

    def _is_descendant_of(pid: int, ancestor_pid: int) -> bool:
        """Return True if pid appears anywhere in the process tree rooted at ancestor_pid."""
        try:
            p = psutil.Process(pid)
            for _ in range(16):
                par = p.parent()
                if par is None:
                    return False
                if par.pid == ancestor_pid:
                    return True
                p = par
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
        return False

    def _find_terminal_window_global(cc_pid: int, cwd: str = "") -> int | None:
        """Fallback: enumerate ALL terminal-class windows and find one whose process
        tree includes cc_pid. Sort by title match then largest area."""
        cand: list[tuple[int, int, int]] = []  # (-priority, area, hwnd)
        needle = os.path.basename(cwd.rstrip("/\\")).lower() if cwd else ""
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
            pid = wt.DWORD()
            _GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            owner_pid = pid.value
            # Check if cc_pid is a descendant of this window's process
            if not _is_descendant_of(cc_pid, owner_pid):
                # Also check if any ancestor of cc_pid is a child of owner_pid
                found = False
                try:
                    owner_p = psutil.Process(owner_pid)
                    kids = {c.pid for c in owner_p.children(recursive=True)}
                    cc = psutil.Process(cc_pid)
                    cur = cc
                    for _ in range(16):
                        if cur.pid in kids:
                            found = True
                            break
                        par = cur.parent()
                        if par is None:
                            break
                        cur = par
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
                if not found:
                    continue
            # Compute priority: title match = 0, no match = 1
            r = wt.RECT()
            area = 0
            if _GetWindowRect(hwnd, ctypes.byref(r)):
                area = (r.right - r.left) * (r.bottom - r.top)
            title = ""
            n = _GetWindowTextLengthW(hwnd)
            if n > 0:
                buf = ctypes.create_unicode_buffer(n + 1)
                _GetWindowTextW(hwnd, buf, n + 1)
                title = buf.value.lower()
            priority = 0 if (needle and needle in title) else 1
            cand.append((-priority, area, hwnd))
        if not cand:
            return None
        cand.sort(key=lambda x: (x[0], -x[1]))
        return cand[0][2]

    def find_terminal_for_pid(pid: int) -> int | None:
        """Walk the parent chain of a CC process to find its terminal window.

        Special case: when the chain hits WindowsTerminal.exe, the actual visible
        window is WT's CASCADIA_HOSTING_WINDOW_CLASS (powershel.exe inside a
        WT ConPTY tab has no visible top-level window of its own)."""
        if pid <= 0:
            return None
        try:
            # 提取 CC 进程的 cwd，用于 WT 标签页标题匹配
            cc = psutil.Process(pid)
            try:
                cwd = cc.cwd() or ""
            except Exception:
                cwd = ""
            p = cc
            for _ in range(8):
                parent = p.parent()
                if parent is None:
                    break
                parent_name = parent.name().lower()
                if parent_name in _WT_NAMES:
                    return _find_wt_window_for_pid(p.pid, cwd)
                hwnd = _find_window_for_process(parent.pid)
                if hwnd:
                    return hwnd
                # 查父进程的子进程（conhost 是 powershell 的子进程）和非 WT 下的 cmd 终端
                try:
                    for child in parent.children(recursive=True):
                        hwnd = _find_window_for_process(child.pid)
                        if hwnd:
                            return hwnd
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
                p = parent
            # 父链没找到 → 全局搜索：扫所有终端 class 窗口，找包含 CC 进程树的
            return _find_terminal_window_global(pid, cwd)
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
        hwnd = 0
        while True:
            hwnd = _FindWindowExW(0, hwnd, None, None)
            if not hwnd:
                break
            if not _IsWindowVisible(hwnd):
                continue
            if not _rect_nonempty(hwnd):
                continue
            n = _GetWindowTextLengthW(hwnd)
            if n == 0:
                continue
            buf = ctypes.create_unicode_buffer(n + 1)
            _GetWindowTextW(hwnd, buf, n + 1)
            title = buf.value.lower()
            cls = _class_name(hwnd).lower()
            if cls == _WT_CLASS.lower() or any(t.lower() in title for t in _TERMINAL_TITLES):
                if needle in title:
                    return hwnd
        return None

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
