from __future__ import annotations

import configparser
from dataclasses import asdict, dataclass, fields
from pathlib import Path


@dataclass
class Config:
    poll_interval_ms: int = 2000
    stale_after_minutes: int = 30
    recent_seconds: int = 60
    expand_delay_ms: int = 200
    collapse_delay_ms: int = 500
    edge_snap_px: int = 30
    indicator_size_px: int = 12
    collapsed_opacity: float = 0.8
    expanded_opacity: float = 1.0

    context_max_tokens: int = 1_000_000
    warning_threshold: float = 0.70
    critical_threshold: float = 0.85
    title_truncate_chars: int = 32
    subtitle_truncate_chars: int = 40
    max_visible_sessions: int = 20

    auto_start: bool = True
    start_minimized_to_tray: bool = False

    @classmethod
    def default(cls) -> Config:
        return cls()

    @classmethod
    def from_dict(cls, d: dict) -> Config:
        flat: dict = {}
        fmap = {f.name: f for f in fields(cls)}
        for _section, kv in d.items():
            for k, v in kv.items():
                if k in fmap:
                    target = fmap[k]
                    if target.type is bool:
                        flat[k] = str(v).lower() in ("1", "true", "yes", "on")
                    elif target.type is int:
                        flat[k] = int(v)
                    elif target.type is float:
                        flat[k] = float(v)
                    else:
                        flat[k] = v
        return cls(**flat)

    def to_dict(self) -> dict:
        d = asdict(self)
        mapping = {
            "general": [
                "poll_interval_ms",
                "stale_after_minutes",
                "recent_seconds",
                "expand_delay_ms",
                "collapse_delay_ms",
                "edge_snap_px",
                "indicator_size_px",
                "collapsed_opacity",
                "expanded_opacity",
            ],
            "display": [
                "context_max_tokens",
                "warning_threshold",
                "critical_threshold",
                "title_truncate_chars",
                "subtitle_truncate_chars",
                "max_visible_sessions",
            ],
            "behavior": ["auto_start", "start_minimized_to_tray"],
        }
        return {sec: {k: d[k] for k in keys} for sec, keys in mapping.items()}

    @classmethod
    def from_file(cls, path: Path) -> Config:
        if not path.exists():
            return cls.default()
        cp = configparser.ConfigParser()
        cp.read(path, encoding="utf-8")
        d = {s: dict(cp.items(s)) for s in cp.sections()}
        return cls.from_dict(d)

    def to_file(self, path: Path) -> None:
        d = self.to_dict()
        cp = configparser.ConfigParser()
        for sec, kv in d.items():
            cp[sec] = {k: str(v) for k, v in kv.items()}
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            cp.write(f)
