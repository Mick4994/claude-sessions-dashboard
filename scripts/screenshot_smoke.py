"""End-to-end GUI smoke test: launch dashboard, wait, screenshot, quit."""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Use real CC config
os.environ.setdefault("CLAUDE_CONFIG_DIR", str(Path.home() / ".claude"))

# Make src importable
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PIL import ImageGrab  # noqa: E402
from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from src.collector.collector import SessionCollector  # noqa: E402
from src.ui.main_window import MainWindow  # noqa: E402
from src.utils.config import Config  # noqa: E402
from src.utils.paths import config_path, default_config_text  # noqa: E402


def main() -> int:
    # Ensure config exists
    cfg_path = config_path()
    if not cfg_path.exists():
        cfg_path.parent.mkdir(parents=True, exist_ok=True)
        cfg_path.write_text(default_config_text(), encoding="utf-8")
    cfg = Config.from_file(cfg_path)

    # Loosen for visibility
    cfg.recent_seconds = 86400
    cfg.stale_after_minutes = 1440

    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("Claude Sessions Dashboard (verify)")

    window = MainWindow(expand_delay_ms=100, collapse_delay_ms=300)
    window.show()

    collector = SessionCollector(
        poll_interval_ms=500,
        recent_seconds=cfg.recent_seconds,
        stale_after_minutes=cfg.stale_after_minutes,
        max_context_tokens=cfg.context_max_tokens,
        title_truncate_chars=cfg.title_truncate_chars,
        subtitle_truncate_chars=cfg.subtitle_truncate_chars,
    )
    print(f"DEBUG: collector._recent_seconds={collector._recent_seconds}")
    print(f"DEBUG: collector._stale_after_minutes={collector._stale_after_minutes}")
    print(f"DEBUG: projects_dir={collector.projects_dir}")
    print(f"DEBUG: env CLAUDE_CONFIG_DIR={os.environ.get('CLAUDE_CONFIG_DIR')}")
    print(f"DEBUG: projects_dir exists={collector.projects_dir.exists()}")
    # Direct scan test
    collector.scan_once()
    print(f"DEBUG: after direct scan_once: {len(collector.current_sessions())} sessions")

    def on_changed(sessions):
        window.set_sessions(sessions)

    collector.sessionsChanged.connect(on_changed)
    collector.start()

    out_dir = ROOT / "docs" / "screenshots"
    out_dir.mkdir(parents=True, exist_ok=True)

    # ---- screenshot 1: collapsed ----
    def shot_collapsed():
        app.processEvents()
        # Force a scan before capture
        collector.scan_once()
        print(f"DEBUG: current_sessions count = {len(collector.current_sessions())}")
        for s in collector.current_sessions():
            print(f"  - {s.id} | {s.title[:30]} | {s.status.value}")
        # Move window to upper right for visibility
        screen = app.primaryScreen().geometry()
        window.move(screen.right() - 60, 100)
        app.processEvents()
        QTimer.singleShot(300, shot_collapsed_grab)

    def shot_collapsed_grab():
        app.processEvents()
        geom = window.frameGeometry()
        # Capture the area around the window
        x = max(0, geom.x() - 100)
        y = max(0, geom.y() - 50)
        w = min(400, geom.width() + 200)
        h = min(800, geom.height() + 200)
        img = ImageGrab.grab(bbox=(x, y, x + w, y + h))
        path = out_dir / "01-collapsed.png"
        img.save(path)
        print(f"Saved {path} | sessions={len(collector.current_sessions())}")
        # ---- screenshot 2: hover-expanded ----
        QTimer.singleShot(200, do_expand_and_shot)

    def do_expand_and_shot():
        # Force expand by calling internal
        window._do_expand()  # noqa: SLF001
        QTimer.singleShot(400, shot_expanded)

    def shot_expanded():
        app.processEvents()
        geom = window.frameGeometry()
        x = max(0, geom.x() - 50)
        y = max(0, geom.y() - 30)
        w = min(700, geom.width() + 100)
        h = min(1200, geom.height() + 100)
        img = ImageGrab.grab(bbox=(x, y, x + w, y + h))
        path = out_dir / "02-expanded.png"
        img.save(path)
        print(f"Saved {path}")
        QTimer.singleShot(200, app.quit)

    # Kick off the screenshot chain
    QTimer.singleShot(1500, shot_collapsed)

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
