"""System tray icon with menu."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from .signal_bus import signalBus


def _build_icon(color: QColor | None = None) -> QIcon:
    if color is None:
        color = QColor("#3B82F6")
    pm = QPixmap(64, 64)
    pm.fill(QColor(0, 0, 0, 0))
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(color)
    p.setPen(0)
    p.drawEllipse(8, 8, 48, 48)
    p.end()
    return QIcon(pm)


def build_tray(app: QApplication, window, collector, cfg_path: Path) -> QSystemTrayIcon:
    tray = QSystemTrayIcon(_build_icon(), app)
    tray.setToolTip("Claude Sessions Dashboard")
    menu = QMenu()
    a_show = QAction("Show / Hide", menu)
    a_show.triggered.connect(lambda: window.show() if window.isHidden() else window.hide())
    a_reload = QAction("Reload config", menu)
    a_reload.triggered.connect(lambda: signalBus.requestReloadConfig.emit())
    a_pause = QAction("Pause polling", menu, checkable=True)
    a_pause.toggled.connect(lambda on: signalBus.requestPause.emit(on))
    a_restart = QAction("Restart", menu)
    a_restart.triggered.connect(lambda: signalBus.requestRestart.emit())
    menu.addAction(a_show)
    menu.addAction(a_reload)
    menu.addAction(a_pause)
    menu.addAction(a_restart)
    menu.addSeparator()
    a_quit = QAction("Quit", menu)
    a_quit.triggered.connect(app.quit)
    menu.addAction(a_quit)
    tray.setContextMenu(menu)
    tray.activated.connect(
        lambda reason: (
            (window.show(), window.raise_(), window.activateWindow())
            if reason == QSystemTrayIcon.Trigger
            else None
        )
    )
    tray.show()
    return tray
