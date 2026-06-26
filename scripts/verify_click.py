"""验证仪表盘点击激活：极简版。

1. Win+D 让前台变成桌面（基线）
2. 通过单例 socket 注入 click <session_id> API 调用
3. 读前台窗口名并打印
"""
import time
import win32api
import win32gui
from PySide6.QtNetwork import QLocalSocket

# 从仪表盘的 click 日志里抄一个真实存在的 session_id
SID = "87f76def-6119-485c-9614-1cee7d310976"

# 1. Win+D 切到桌面
win32api.keybd_event(0x5B, 0, 0, 0)
win32api.keybd_event(0x44, 0, 0, 0)
win32api.keybd_event(0x44, 0, 2, 0)
win32api.keybd_event(0x5B, 0, 2, 0)
time.sleep(0.5)

# 2. 注入点击事件（1 行 socket 写入）
QLocalSocket().connectToServer("claude-sessions-dashboard-singleton")
s = QLocalSocket()
s.connectToServer("claude-sessions-dashboard-singleton")
s.waitForConnected(500)
s.write(f"click {SID}".encode())
s.flush()
s.disconnectFromServer()
time.sleep(0.7)

# 3. 读前台窗口名
print(win32gui.GetWindowText(win32gui.GetForegroundWindow()))
