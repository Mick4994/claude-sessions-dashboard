"""用当前可见的 WT pane 标题测试 find_terminal_for_title 匹配逻辑。

预期：3 个 pane 中只有项目名能匹配对应 pane。
"""
import sys
sys.path.insert(0, r"D:\Codes\claude-sessions-dashboard")
from src.win32 import windows_focus as wf

# 当前可见的 pane 标题（diag 输出）
PANE_TITLES = [
    "⠐ 排查仪表盘卡片唤起窗口问题",
    "✳ 臂力器健身辅助程序",
    "Windows PowerShell",
]

# 三个 CC 的 session title（来自 JSONL）—— 凭直觉推测：
# 用户说有两个不同的 CC（sid=3e261ef1 和 sid=729d5809）。
# 仪表盘项目自身 = claude-sessions-dashboard（"排查仪表盘卡片唤起窗口问题"）
# 其他项目 = chest-expander-tracker（"臂力器健身辅助程序"）
test_titles = [
    "排查仪表盘卡片唤起窗口问题",  # 期望匹配 pane 1
    "臂力器健身辅助程序",  # 期望匹配 pane 2
    "PowerShell",  # 期望匹配 pane 3
    "claude-sessions-dashboard",  # 期望无匹配（pane 标题没这个）
]

for t in test_titles:
    hwnd = wf.find_terminal_for_title(t)
    print(f"find_terminal_for_title({t!r}) -> hwnd={hwnd}")