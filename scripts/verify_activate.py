"""直接验证 find_terminal_for_pid + activate_window。

找 claude.exe → 找父链中第一个可见窗口 → 激活 → 检查前台。
"""
import sys, time
import psutil, ctypes, ctypes.wintypes as wt
sys.path.insert(0, r"D:\Codes\claude-sessions-dashboard")
from src.win32 import windows_focus as wf

user32 = ctypes.WinDLL("user32", use_last_error=True)

def asc(s): return s.encode("ascii", "replace").decode("ascii")

# 找真用户 claude.exe（排除 claude-mem observer），优先父链含 WindowsTerminal
_WT_NAMES = {"windowsterminal.exe", "wt.exe"}
_best = []
for p in psutil.process_iter(["pid", "name", "cwd"]):
    if (p.info.get("name") or "").lower() != "claude.exe": continue
    if ".claude-mem" in (p.info.get("cwd") or "").lower(): continue
    cc = psutil.Process(p.info["pid"])
    anc = set()
    try:
        cur = cc
        for _ in range(6):
            pp = cur.parent()
            if not pp: break
            anc.add(pp.name().lower());
            cur = pp
    except: pass
    in_wt = bool(anc & _WT_NAMES)
    _best.append((in_wt, p.info["pid"]))
    _best.sort(key=lambda x: (not x[0], x[1]))  # WT first
cc_pid = _best[0][1] if _best else None
print(f"cc_pid={cc_pid}")
if not cc_pid:
    print("no claude.exe found"); sys.exit(1)

# 打印父链
p = psutil.Process(cc_pid)
for d in range(6):
    try: name = p.name()
    except: name = "?"
    par = p.parent()
    print(f"  d{d}: pid={p.pid} name={name}")
    if not par: break
    p = par

# 直接调用 dashboard 用的 find_terminal_for_pid + activate_window
hwnd = wf.find_terminal_for_pid(cc_pid)
print(f"find_terminal_for_pid -> hwnd={hwnd}")

if hwnd:
    ok = wf.activate_window(hwnd)
    time.sleep(0.3)
    fg = user32.GetForegroundWindow()
    ln = user32.GetWindowTextLengthW(fg)
    title = ""
    if ln > 0:
        buf = ctypes.create_unicode_buffer(ln+1)
        user32.GetWindowTextW(fg, buf, ln+1)
        title = asc(buf.value)
    print(f"activate_window -> {ok}")
    print(f"FG now: hwnd={fg} title={title!r}")
    print(f"match: {fg == hwnd}")
else:
    print("no hwnd found — FAIL")
    sys.exit(1)
