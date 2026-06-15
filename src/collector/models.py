from enum import Enum


class SessionStatus(Enum):
    """Lifecycle state of a Claude Code session."""

    WORKING = "working"          # 闪烁蓝
    IDLE = "idle"                # 常亮绿
    PERMISSION = "permission"    # 常亮黄
    ERROR = "error"              # 闪烁红
    STALE = "stale"              # 不亮灰
