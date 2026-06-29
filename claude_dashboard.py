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

from PySide6.QtCore import QProcess
from PySide6.QtWidgets import QApplication, QSystemTrayIcon

from src.collector.collector import SessionCollector
from src.core.pairing_store import PairingStore
from src.core.session_registry import SessionRegistry
from src.core.status import SessionStatus
from src.server.hook_server import HookServer
from src.server.router import HookRouter
from src.ui.main_window import MainWindow
from src.ui.signal_bus import signalBus
from src.ui.tray import build_tray
from src.utils.config import Config
from src.utils.paths import app_data_dir, config_path, default_config_text
from src.utils.single_instance import try_acquire
from src.win32.windows_focus import (
    _find_largest_visible_terminal,
    activate_window,
    find_terminal_for_cwd,
    find_terminal_for_pid,
    find_terminal_for_title,
    is_window_valid,
    list_visible_terminals,
)

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

    # Version stamp — written on every startup so we know which code is running.
    import datetime as _dt, subprocess as _sp
    _ver = Path(os.environ.get("TEMP", ".")) / "csd_click_debug.log"
    try:
        _commit = _sp.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(Path(__file__).parent),
            stderr=_sp.DEVNULL,
            text=True,
        ).strip()
    except Exception:
        _commit = "unknown"
    with open(_ver, "a") as _vf:
        _vf.write(f"\n=== DASHBOARD STARTUP {_dt.datetime.now():%Y-%m-%d %H:%M:%S} commit={_commit} ===\n")

    # -- registry (session_id-keyed, thread-safe) --
    registry = SessionRegistry()

    # -- 手动配对持久化（卡片右键 → 选终端 → 写文件） --
    pairing_store = PairingStore(app_data_dir() / "pairings.json")

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
        # 刷新卡片的配对状态指示器
        _refresh_paired_indicators()

    collector.sessionsChanged.connect(on_sessions_changed)

    def _refresh_paired_indicators() -> None:
        """读持久化配对表 → 更新每张卡片的"已配对"小圆点 + 内存缓存。"""
        _pairs = pairing_store.all()
        _ids = set(_pairs.keys())
        _titles = {sid: p.get("title", "") for sid, p in _pairs.items()}
        window.set_paired_sessions(_ids, _titles)
        window.set_paired_cache(_pairs)

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
        # 防御性 try/except：pythonw 启动时没有 stderr，任何异常都会被静默吞掉。
        # 把所有异常 dump 到 csd_click_debug.log，确保未来类似 bug 不会再次无声丢失。
        import datetime as _dt
        import traceback as _tb

        _log = Path(os.environ.get("TEMP", ".")) / "csd_click_debug.log"
        _sid8 = session_id[:8]

        def _w(msg: str) -> None:
            # 每行带 [_sid8] 前缀，方便 grep 单 session 的全链路
            with open(_log, "a", encoding="utf-8") as _f:
                _f.write(f"{_dt.datetime.now():%H:%M:%S.%f} [{_sid8}] {msg}\n")

        hwnd_source: str = "none"  # 标注最终 hwnd 来自哪条路径
        try:
            _w(f"cardClicked sid={session_id}")
            hwnd: int | None = None
            entry = registry.get_by_sid(session_id)
            _w(f"  entry={entry!r}")
            # 1. 先看手动配对缓存（最高优先级）
            pair = pairing_store.get(session_id)
            if pair is not None:
                _w(
                    f"  pair cache HIT: hwnd={pair['hwnd']} "
                    f"title={pair['title']!r} class={pair['class']!r}"
                )
                if is_window_valid(pair["hwnd"]):
                    hwnd = pair["hwnd"]
                    hwnd_source = "pair_cache"
                    _w(f"  pair cache hwnd still valid -> {hwnd}")
                else:
                    # hwnd 失效（WT 重启等），按 title 重新找
                    _w(f"  pair cache hwnd STALE, try title re-resolution")
                    _rescued = False
                    for t in list_visible_terminals():
                        if t["title"] == pair["title"] and t["class"] == pair["class"]:
                            hwnd = t["hwnd"]
                            pairing_store.set(session_id, hwnd, t["title"], t["class"])
                            hwnd_source = "pair_cache_rescued_by_title"
                            _w(
                                f"  pair cache rescued by title match -> hwnd={hwnd} "
                                f"(cache updated)"
                            )
                            _rescued = True
                            break
                    if not _rescued:
                        _w(f"  pair cache stale + title miss -> fall through to auto-detect")
            else:
                _w(f"  pair cache MISS (no entry in store)")
            if hwnd is None and entry and entry.pid:
                _w(f"  try pid-based: entry.pid={entry.pid}")
                hwnd = find_terminal_for_pid(entry.pid)
                if hwnd is not None:
                    hwnd_source = "pid"
                _w(f"  find_terminal_for_pid({entry.pid}) -> hwnd={hwnd}")
            if hwnd is None:
                sessions = collector.current_sessions()
                sess = next((s for s in sessions if s.id == session_id), None)
                if sess:
                    _w(
                        f"  fallback chain: title={sess.title!r} "
                        f"subtitle={sess.subtitle!r} cwd={sess.cwd!r}"
                    )
                    if sess.title:
                        hwnd = find_terminal_for_title(sess.title)
                        if hwnd is not None:
                            hwnd_source = "title"
                        _w(f"  find_terminal_for_title(title) -> hwnd={hwnd}")
                    if hwnd is None and sess.subtitle:
                        hwnd = find_terminal_for_title(sess.subtitle)
                        if hwnd is not None:
                            hwnd_source = "subtitle"
                        _w(f"  find_terminal_for_title(subtitle) -> hwnd={hwnd}")
                    if hwnd is None and sess.cwd:
                        hwnd = find_terminal_for_cwd(sess.cwd)
                        if hwnd is not None:
                            hwnd_source = "cwd"
                        _w(f"  find_terminal_for_cwd -> hwnd={hwnd}")
                    if hwnd is None:
                        hwnd = _find_largest_visible_terminal()
                        hwnd_source = "largest_fallback"
                        _w(f"  _find_largest_visible_terminal -> hwnd={hwnd}")
                else:
                    _w(f"  no session object found in collector")
            if hwnd:
                _w(f"  FINAL hwnd={hwnd} (source={hwnd_source}) → activate")
                ok = activate_window(hwnd)
                _w(f"  activate_window({hwnd}) -> {ok}")
            else:
                _w(f"  NO hwnd for sid={session_id} (source={hwnd_source})")
        except Exception:
            # 任何异常（NameError / psutil.NoSuchProcess / ctypes.ArgumentError / OSError ...）
            # 都要落盘，不能再让"异常被吞"成为隐藏 bug 的根源。
            _w("  EXCEPTION caught:")
            with open(_log, "a", encoding="utf-8") as _f:
                _f.write(_tb.format_exc())

    signalBus.cardClicked.connect(on_card_clicked)

    # -- 手动配对：卡片右键 → 选终端 / 取消配对 --
    def _on_card_paired(session_id: str, hwnd: int, title: str, class_name: str) -> None:
        pairing_store.set(session_id, hwnd, title, class_name)
        _refresh_paired_indicators()
        logger.info("paired sid=%s -> hwnd=%d title=%r", session_id, hwnd, title)

    def _on_card_unpaired(session_id: str) -> None:
        pairing_store.delete(session_id)
        _refresh_paired_indicators()
        logger.info("unpaired sid=%s", session_id)

    window.cardPairRequested.connect(_on_card_paired)
    window.cardUnpairRequested.connect(_on_card_unpaired)

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

    # -- restart: spawn a new instance then quit --
    def on_restart():
        # Resolve the venv pythonw executable — prefer pythonw over python
        # so the restarted process stays window-less on Windows.
        _venv_dir = Path(sys.executable).parent
        _pythonw = _venv_dir / "pythonw.exe"
        if not _pythonw.exists():
            _pythonw = _venv_dir / "pythonw"
        _exe = str(_pythonw) if _pythonw.exists() else sys.executable
        QProcess.startDetached(
            _exe,
            [str(Path(__file__).resolve())],
            str(Path(__file__).resolve().parent),
        )
        app.quit()

    signalBus.requestRestart.connect(on_restart)

    # -- handle "show" ping from secondary instance --
    if server is not None:

        def _on_new_conn():
            client = server.nextPendingConnection()
            if client:
                client.readyRead.connect(lambda: _handle_ping(client))

        def _handle_ping(client):
            msg = bytes(client.readAll()).decode("utf-8", "ignore").strip()
            # 外部注入点击事件：socket 收到 "click <session_id>" 后转发到 signalBus
            if msg.startswith("click "):
                sid = msg[len("click "):].strip()
                if sid:
                    signalBus.cardClicked.emit(sid)
            elif window.isHidden():
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
