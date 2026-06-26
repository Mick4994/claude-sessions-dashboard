from dataclasses import dataclass

from src.core.status import STATUS_COLORS, SessionStatus  # noqa: F401 — re-export

__all__ = ["Session", "SessionStatus", "STATUS_COLORS"]


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
