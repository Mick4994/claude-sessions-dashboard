#!/usr/bin/env python3
"""Claude Sessions Dashboard — floating status bar for active Claude Code sessions.

Architecture (Phase 4):
  ProcessMonitor → SessionCollector → SessionRegistry → MainWindow (list)
  CC hooks → curl POST → HookServer → HookRouter → SessionRegistry → MainWindow (status)
  JSONL → SessionCollector (metadata only: title / context% / subtitle)
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

# Allow `python claude_dashboard.py` to find src package
sys.path.insert(0, str(Path(__file__).parent))

from PySide6.QtWidgets import QApplication, QSystemTrayIcon

from src.collector.collector import SessionCollector
from src.core.session_registry import SessionRegistry
from src.core.status import SessionStatus
from src.server.hook_server import HookServer
from src.server.router import HookRouter
from src.ui.main_window import MainWindow
from src.ui.signal_bus import signalBus
from src.ui.tray import build_tray
from src.utils.config import Config
from src.utils.paths import config_path, default_config_text
from src.utils.single_instance import try_acquire

logger = logging.getLogger(__name__)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")

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

    # -- registry (session_id-keyed, thread-safe) --
    registry = SessionRegistry()

    # -- window --
    window = MainWindow(
        expand_delay_ms=cfg.expand_delay_ms,
        collapse_delay_ms=cfg.collapse_delay_ms,
    )
    window.show()

    # -- collector (process-only, metadata from JSONL) --
    collector = SessionCollector(
        poll_interval_ms=cfg.poll_interval_ms,
        max_context_tokens=cfg.context_max_tokens,
        title_truncate_chars=cfg.title_truncate_chars,
        subtitle_truncate_chars=cfg.subtitle_truncate_chars,
    )

    # Wire collector → registry: register sessions when discovered,
    # unregister when CC process disappears.
    def _sync_registry(sessions):
        alive_sids = {s.id for s in sessions}
        existing_sids = {e.session_id for e in registry.iter_all() if e.session_id}
        for s in sessions:
            if s.id not in existing_sids:
                registry.register_by_sid(
                    session_id=s.id,
                    pid=s.pid,
                    cwd=Path(s.cwd) if s.cwd else Path("."),
                    jsonl_path=Path(s.jsonl_path) if s.jsonl_path else None,
                )
        for sid in existing_sids - alive_sids:
            registry.unregister_by_sid(sid)

    # Registry status changes → update Session object → refresh UI.
    def _on_registry_status(entry, new_status):
        # Find matching session by session_id and update its status.
        found = False
        for s in collector.current_sessions():
            if s.id == entry.session_id:
                s.status = new_status
                found = True
                break
        if found:
            # Re-emit to refresh the indicator colors without adding/removing rows.
            collector.sessionsChanged.emit(collector.current_sessions())

    registry.on_status_changed(_on_registry_status)

    def on_sessions_changed(sessions):
        _sync_registry(sessions)
        window.set_sessions(sessions)

    collector.sessionsChanged.connect(on_sessions_changed)

    # -- hook server --
    router = HookRouter(registry)
    hook_srv = HookServer("127.0.0.1", cfg.hook_port, router)

    try:
        hook_srv.start()
    except OSError as exc:
        logger.warning(
            "HookServer could not bind %s: %s — indicator colors will not update",
            hook_srv.url,
            exc,
        )

    # -- card click → activate CC terminal --
    def on_card_clicked(session_id: str):
        hwnd = None
        # Prefer PID-based window lookup (robust to title changes).
        entry = registry.get_by_sid(session_id)
        if entry and entry.pid:
            hwnd = find_terminal_for_pid(entry.pid)
        # Fallback: CWD-based title matching.
        if hwnd is None:
            sessions = collector.current_sessions()
            sess = next((s for s in sessions if s.id == session_id), None)
            if sess and sess.cwd:
                hwnd = find_terminal_for_cwd(sess.cwd)
        if hwnd:
            activate_window(hwnd)

    signalBus.cardClicked.connect(on_card_clicked)

    # -- tray --
    _tray = build_tray(app, window, collector, cfg_path)
    _tray.showMessage("Claude Sessions Dashboard", "Started", QSystemTrayIcon.Information, 3000)

    # -- config hot-reload --
    def on_reload():
        nonlocal cfg
        cfg = load_config()
        collector._poll_interval_ms = cfg.poll_interval_ms
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

    # -- start --
    collector.start()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
