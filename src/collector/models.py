from dataclasses import dataclass
from enum import Enum


class SessionStatus(Enum):
    """Lifecycle state of a Claude Code session."""

    WORKING = "working"  # 闪烁蓝
    IDLE = "idle"  # 常亮绿
    PERMISSION = "permission"  # 常亮黄
    ERROR = "error"  # 闪烁红
    STALE = "stale"  # 不亮灰


@dataclass
class Session:
    """In-memory representation of one Claude Code session."""

    id: str
    jsonl_path: str
    cwd: str
    title: str = ""
    subtitle: str = ""
    context_pct: float = 0.0
    model: str = ""
    status: SessionStatus = SessionStatus.IDLE
    last_activity_ts: float = 0.0
