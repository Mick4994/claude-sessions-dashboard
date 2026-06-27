"""诊断：枚举所有 terminal-class 窗口，打印 pid / class / title / rect。

帮助理解当前激活回退能看到什么、为什么匹配失败。
"""
import ctypes
import ctypes.wintypes as wt

user32 = ctypes.WinDLL("user32", use_last_error=True)
GetClassNameW = user32.GetClassNameW
GetWindowRect = user32.GetWindowRect
GetWindowTextLengthW = user32.GetWindowTextLengthW
GetWindowTextW = user32.GetWindowTextW
IsWindowVisible = user32.IsWindowVisible
FindWindowExW = user32.FindWindowExW
GetWindowThreadProcessId = user32.GetWindowThreadProcessId


def class_name(hwnd: int) -> str:
    buf = ctypes.create_unicode_buffer(256)
    n = GetClassNameW(hwnd, buf, 256)
    return buf.value[:n]


def title(hwnd: int) -> str:
    n = GetWindowTextLengthW(hwnd)
    if n == 0:
        return ""
    buf = ctypes.create_unicode_buffer(n + 1)
    GetWindowTextW(hwnd, buf, n + 1)
    return buf.value


def is_terminal_class(cls: str) -> bool:
    return cls in {"ConsoleWindowClass", "CASCADIA_HOSTING_WINDOW_CLASS"}


hwnd = 0
print(f"{'hwnd':>10} {'pid':>8} {'visible':>7} {'class':<30} {'title':<60}")
print("-" * 120)
while True:
    hwnd = FindWindowExW(0, hwnd, None, None)
    if not hwnd:
        break
    cls = class_name(hwnd)
    if not is_terminal_class(cls):
        continue
    pid = wt.DWORD()
    GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    rect = wt.RECT()
    GetWindowRect(hwnd, ctypes.byref(rect))
    width = rect.right - rect.left
    height = rect.bottom - rect.top
    vis = IsWindowVisible(hwnd)
    t = title(hwnd)
    print(f"{hwnd:>10} {pid.value:>8} {str(vis):>7} {cls:<30} {t[:60]:<60}  {width}x{height}")