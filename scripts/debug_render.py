"""Debug why indicators aren't showing."""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("CLAUDE_CONFIG_DIR", str(Path.home() / ".claude"))
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PIL import ImageGrab  # noqa: E402
from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from src.collector.collector import SessionCollector  # noqa: E402
from src.ui.indicator_widget import IndicatorDot  # noqa: E402
from src.ui.main_window import MainWindow  # noqa: E402


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)

    # 1. screen info
    screen = QApplication.primaryScreen()
    print(f"[screen] size={screen.size().width()}x{screen.size().height()}")
    print(f"[screen] avail={screen.availableGeometry().width()}x{screen.availableGeometry().height()}")
    print(f"[screen] DPI={screen.logicalDotsPerInch()}")

    # 2. window
    w = MainWindow()
    w.show()
    app.processEvents()
    print(f"\n[window] pos=({w.x()},{w.y()}) size=({w.width()}x{w.height()})")
    print(f"[window] visible={w.isVisible()} frameGeom={w.frameGeometry()}")
    print(f"[window] windowOpacity={w.windowOpacity()}")

    # 3. container
    c = w._container
    print(f"\n[container] pos=({c.x()},{c.y()}) size=({c.width()}x{c.height()})")
    print(f"[container] visible={c.isVisible()} styleSheet={c.styleSheet()!r}")

    # 4. collector
    collector = SessionCollector(
        poll_interval_ms=500,
        recent_seconds=86400,
        stale_after_minutes=1440,
        max_context_tokens=1_000_000,
    )
    collector.scan_once()
    sessions = collector.current_sessions()
    print(f"\n[collector] sessions={len(sessions)}")
    for s in sessions:
        print(f"  - {s.id[:8]} | {s.title[:30]}")
    w.set_sessions(sessions)
    app.processEvents()

    # 5. inspect dots after set_sessions
    print(f"\n[layout] _inner.count()={w._inner.count()}")
    for i in range(w._inner.count()):
        item = w._inner.itemAt(i)
        wdg = item.widget()
        if wdg is not None:
            print(f"  [{i}] widget={type(wdg).__name__} visible={wdg.isVisible()} size={wdg.size().width()}x{wdg.size().height()} pos=({wdg.x()},{wdg.y()})")
            # look for IndicatorDot children
            for child in wdg.findChildren(IndicatorDot):
                print(f"      dot color={child._color.name()} visible={child.isVisible()} size={child.size().width()}x{child.size().height()} pos=({child.x()},{child.y()}) period={child._period_ms}")

    # 6. screenshot
    QTimer.singleShot(500, lambda: _shot(w))
    QTimer.singleShot(2000, app.quit)
    return app.exec()


def _shot(w):
    app = QApplication.instance()
    geom = w.frameGeometry()
    # capture a generous area around the window
    x = max(0, geom.x() - 200)
    y = max(0, geom.y() - 100)
    wpx = min(800, geom.width() + 400)
    hpx = min(1000, geom.height() + 200)
    print(f"\n[screenshot] bbox=({x},{y},{x+wpx},{y+hpx})  size={wpx}x{hpx}")
    img = ImageGrab.grab(bbox=(x, y, x + wpx, y + hpx))
    path = ROOT / "docs" / "screenshots" / "debug-collapsed.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path)
    print(f"[screenshot] saved {path} ({path.stat().st_size} bytes)")


if __name__ == "__main__":
    sys.exit(main())
