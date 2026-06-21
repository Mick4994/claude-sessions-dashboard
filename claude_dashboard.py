#!/usr/bin/env python3
"""Claude Sessions Dashboard — floating status bar for active Claude Code sessions."""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Allow `python claude_dashboard.py` to find src package
sys.path.insert(0, str(Path(__file__).parent))

from PySide6.QtWidgets import QApplication

from src.collector.collector import SessionCollector
from src.ui.main_window import MainWindow
from src.ui.signal_bus import signalBus
from src.ui.tray import build_tray
from src.utils.config import Config
from src.utils.paths import config_path, default_config_text
from src.utils.single_instance import try_acquire


def main() -> int:
    # -- single-instance --
    server, is_primary = try_acquire()
    if not is_primary:
        sys.exit(0)

    # -- config --
    cfg_path = config_path()
    if not cfg_path.exists():
        cfg_path.parent.mkdir(parents=True, exist_ok=True)
        cfg_path.write_text(default_config_text(), encoding="utf-8")

    def load_config() -> Config:
        return Config.from_file(cfg_path)

    cfg = load_config()

    # -- app --
    app = QApplication(sys.argv)
    app.setApplicationName("Claude Sessions Dashboard")
    app.setQuitOnLastWindowClosed(False)

    # -- window --
    window = MainWindow(
        expand_delay_ms=cfg.expand_delay_ms,
        collapse_delay_ms=cfg.collapse_delay_ms,
    )
    window.show()

    # -- collector --
    collector = SessionCollector(
        poll_interval_ms=cfg.poll_interval_ms,
        recent_seconds=cfg.recent_seconds,
        hide_after_seconds=cfg.hide_after_seconds,
        stale_after_minutes=cfg.stale_after_minutes,
        max_context_tokens=cfg.context_max_tokens,
        title_truncate_chars=cfg.title_truncate_chars,
        subtitle_truncate_chars=cfg.subtitle_truncate_chars,
    )

    def on_sessions_changed(sessions):
        window.set_sessions(sessions)

    collector.sessionsChanged.connect(on_sessions_changed)

    # -- card click → activate CC terminal --
    def on_card_clicked(session_id: str):
        sessions = collector.current_sessions()
        sess = next((s for s in sessions if s.id == session_id), None)
        if sess is None:
            return
        if os.name == "nt":
            from src.win32.windows_focus import activate_window, find_terminal_for_cwd

            hwnd = find_terminal_for_cwd(sess.cwd)
            if hwnd:
                activate_window(hwnd)

    signalBus.cardClicked.connect(on_card_clicked)

    # -- tray --
    _tray = build_tray(app, window, collector, cfg_path)

    # -- config reload / pause --
    def on_reload():
        nonlocal cfg
        cfg = load_config()
        collector._poll_interval_ms = cfg.poll_interval_ms
        collector._recent_seconds = cfg.recent_seconds
        collector._stale_after_minutes = cfg.stale_after_minutes
        collector._max_context_tokens = cfg.context_max_tokens

    def on_pause(paused: bool):
        if paused:
            collector.stop()
        else:
            collector.start()

    signalBus.requestReloadConfig.connect(on_reload)
    signalBus.requestPause.connect(on_pause)

    # -- handle "show" ping from secondary instance --
    if server is not None:

        def _on_new_conn():
            client = server.nextPendingConnection()
            if client:
                client.readyRead.connect(lambda: _handle_ping(client))

        def _handle_ping(client):
            _ = bytes(client.readAll()).decode("utf-8", "ignore").strip()
            if window.isHidden():
                window.show()
            window.raise_()
            window.activateWindow()
            client.disconnectFromServer()

        server.newConnection.connect(_on_new_conn)

    # -- start polling --
    collector.start()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
