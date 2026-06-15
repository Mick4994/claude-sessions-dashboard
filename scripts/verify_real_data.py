"""Verify dashboard reads real CC session data correctly."""
from __future__ import annotations

import sys
from pathlib import Path

# Override CLAUDE_CONFIG_DIR to user's real config
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.collector.collector import SessionCollector


def main() -> int:
    collector = SessionCollector(
        poll_interval_ms=2000,
        recent_seconds=86400,    # 24h for verification (any session touched in past day)
        stale_after_minutes=1440,  # 24h
        max_context_tokens=1_000_000,
        title_truncate_chars=32,
        subtitle_truncate_chars=40,
    )
    collector.scan_once()
    sessions = collector.current_sessions()
    print(f"\n=== Dashboard would show {len(sessions)} sessions ===\n")
    for s in sessions:
        print(
            f"  ● {s.title[:40]:<40} | {s.context_pct:>5.1f}% | "
            f"sub: {s.subtitle[:30]:<30} | status: {s.status.value:<10} | "
            f"cwd: {Path(s.cwd).name}"
        )
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
