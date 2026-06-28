# ruff: noqa: N802
"""Frameless always-on-top window with hover expand/collapse, edge snap, and drag."""

from __future__ import annotations

import os
import time
from pathlib import Path

from PySide6.QtCore import QPoint, QPropertyAnimation, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QMainWindow,
    QVBoxLayout,
    QWidget,
)

from ..collector.models import Session, SessionStatus
from .card_widget import SessionCard
from .indicator_widget import IndicatorDot
from .signal_bus import signalBus
from ..win32 import windows_focus as wf


class MainWindow(QMainWindow):
    COLLAPSED_WIDTH = 40
    EXPANDED_WIDTH = 280
    CARD_HEIGHT = 78
    CARD_SPACING = 6
    PADDING = 8
    INDICATOR_ROW = 22

    # 卡片请求配对/取消配对时，主窗口把它们再转出去给主程序处理
    cardPairRequested = Signal(str, int, str, str)  # session_id, hwnd, title, class_name
    cardUnpairRequested = Signal(str)

    def __init__(self, *, expand_delay_ms: int = 200, collapse_delay_ms: int = 500) -> None:
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground, True)

        self._sessions: list[Session] = []
        self._expanded = False
        self._current_width = self.COLLAPSED_WIDTH
        self._dragging = False
        self._drag_offset = QPoint()

        self._container = QWidget(self)
        self._container.setObjectName("container")
        self._container.setStyleSheet(
            "#container { background: rgba(20, 20, 24, 0.80); border-radius: 8px; }"
        )
        self._inner = QVBoxLayout(self._container)
        self._inner.setContentsMargins(self.PADDING, self.PADDING, self.PADDING, self.PADDING)
        self._inner.setSpacing(self.CARD_SPACING)

        self.setCentralWidget(self._container)
        self.resize(self.COLLAPSED_WIDTH, 200)
        self._move_to_right_edge()

        self._expand_timer = QTimer(self)
        self._expand_timer.setSingleShot(True)
        self._expand_timer.timeout.connect(self._do_expand)
        self._collapse_timer = QTimer(self)
        self._collapse_timer.setSingleShot(True)
        self._collapse_timer.timeout.connect(self._do_collapse)
        self._expand_delay_ms = expand_delay_ms
        self._collapse_delay_ms = collapse_delay_ms

        self.setMouseTracking(True)
        self._container.setMouseTracking(True)

    # ---- positioning ----
    def _move_to_right_edge(self) -> None:
        screen = QApplication.primaryScreen()
        if screen is None:
            return
        geo = screen.availableGeometry()
        x = geo.right() - self._current_width
        y = geo.center().y() - self.height() // 2
        self.move(x, y)

    # ---- session updates ----
    def set_sessions(self, sessions: list[Session]) -> None:
        if len(sessions) > 20:
            sessions = sessions[:20]
        self._sessions = sessions
        self._rebuild()
        self._fit_height()

    def set_paired_sessions(self, paired_ids: set[str], titles: dict[str, str]) -> None:
        """根据持久化的配对表，刷新每张卡片右上角的"已配对"小圆点。"""
        self._paired_ids_cache = set(paired_ids)
        for i in range(self._inner.count()):
            _item = self._inner.itemAt(i)
            _w = _item.widget() if _item else None
            if isinstance(_w, SessionCard):
                _sid = _w.session.id
                _w.set_paired(_sid in paired_ids, titles.get(_sid, ""))

    def _find_card(self, sid: str):
        """按 session_id 在当前 expanded 卡片里找。"""
        from .card_widget import SessionCard as _SC

        for i in range(self._inner.count()):
            _item = self._inner.itemAt(i)
            _w = _item.widget() if _item else None
            if isinstance(_w, _SC) and _w.session.id == sid:
                return _w
        return None

    def _on_card_list_terminals(self, session) -> None:
        """卡片右键请求列出终端窗口——按 session.title/subtitle 过滤、配对项置顶。

        完整数据流：卡片发 listTerminalsRequested(session) -> 本方法
        查 pairing_store 取 paired_hwnd -> wf.list_terminals_for_session 过滤
        -> 回填到对应卡片（_card.set_terminals）
        """
        _card = self._find_card(session.id)
        if _card is None:
            return
        _pair = self._paired_pairs_cache.get(session.id) if hasattr(self, "_paired_pairs_cache") else None
        _paired_hwnd = _pair.get("hwnd") if _pair else None
        _terms, _fallback = wf.list_terminals_for_session(
            session.title or None,
            session.subtitle or None,
            _paired_hwnd,
        )
        _is_paired = session.id in (self._paired_ids_cache or set())
        _card.set_terminals(_terms, _fallback, _paired_hwnd, _is_paired)

    def set_paired_cache(self, paired_pairs: dict[str, dict]) -> None:
        """刷新内存缓存（sid → {hwnd, title, class, paired_at}），
        用于右键菜单判断当前卡片是否已配对 + 拿到 paired_hwnd。
        """
        self._paired_pairs_cache = dict(paired_pairs)
        self._paired_ids_cache = set(paired_pairs.keys())

    def set_menu_open(self, is_open: bool) -> None:
        """卡片右键菜单显示/关闭时调用，抑制 leaveEvent 触发的自动收起。

        关键：开菜单时要把已经挂起的 expand / collapse timer 都 stop 掉——
        否则菜单显示期间旧 timer fire 触发收起，Qt 会 dismiss 掉弹出的菜单。
        """
        self._menu_open = bool(is_open)
        if is_open:
            self._collapse_timer.stop()
            self._expand_timer.stop()

    def collapse_after_menu(self) -> None:
        """菜单关闭后，如果鼠标还在 dashboard 外，启动一次收起计时。"""
        if not getattr(self, "_menu_open", False):
            # 如果期间菜单又关了但鼠标也回来了，就别收——leaveEvent 早晚会触发
            # 这里只在鼠标仍在外部时主动收一次（防止菜单关闭后卡在展开态）
            under_mouse = self.underMouse()
            if not under_mouse:
                self._expand_timer.stop()
                self._collapse_timer.start(self._collapse_delay_ms)

    def _fit_height(self) -> None:
        n = max(1, len(self._sessions))
        if self._expanded:
            if not self._sessions:
                h = 80
            else:
                h = (
                    self.PADDING * 2
                    + len(self._sessions) * self.CARD_HEIGHT
                    + max(0, len(self._sessions) - 1) * self.CARD_SPACING
                )
        else:
            h = self.PADDING * 2 + n * self.INDICATOR_ROW + (n - 1) * 4
        h = max(60, h)
        self.resize(self._current_width, h)
        self._move_to_right_edge()

    # ---- rebuild contents ----
    def _clear_inner(self) -> None:
        while self._inner.count():
            item = self._inner.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()

    def _rebuild(self) -> None:
        self._clear_inner()
        if not self._sessions:
            if self._expanded:
                label = QLabel(
                    "无活跃 Claude Code 会话\n启动 CC 后可在此查看会话状态"
                )
                label.setAlignment(Qt.AlignCenter)
                label.setStyleSheet(
                    "color: rgba(180,180,190,0.7);"
                    "padding: 12px 0;"
                )
                label.setWordWrap(True)
                self._inner.addWidget(label, 0, Qt.AlignCenter)
            else:
                # ponytail: 空心环 + 声呐脉冲 — 几何上区别于实心 IDLE 点
                from .empty_indicator import EmptyStateIndicator

                placeholder = EmptyStateIndicator(size_px=12)
                placeholder.setToolTip("暂无活跃 Claude Code 会话")
                self._inner.addWidget(placeholder, 0, Qt.AlignCenter)
            self._inner.addStretch(0)
            return

        if self._expanded:
            for s in self._sessions:
                card = SessionCard(s)
                card.clicked.connect(signalBus.cardClicked.emit)
                # 把卡片的配对相关信号转发出去
                card.pairRequested.connect(self.cardPairRequested)
                card.unpairRequested.connect(self.cardUnpairRequested)
                # 列出终端的请求由主窗口自己处理（需要回填到具体卡片）
                card.listTerminalsRequested.connect(self._on_card_list_terminals)
                self._inner.addWidget(card)
        else:
            for s in self._sessions:
                dot = IndicatorDot(s.status, size_px=12, session_id=s.id)
                dot.setToolTip(
                    f"{s.title or '(untitled)'}\n{s.subtitle or ''}\n{int(s.context_pct)}%"
                )
                self._inner.addWidget(dot, 0, Qt.AlignCenter)
        self._inner.addStretch(0)

    # ---- hover expand/collapse ----
    def enterEvent(self, _ev) -> None:
        self._collapse_timer.stop()
        self._expand_timer.start(self._expand_delay_ms)

    def leaveEvent(self, _ev) -> None:
        if getattr(self, "_menu_open", False):
            # 右键菜单显示期间不要收起，否则菜单会跑到收起后的窄条下面点不到
            return
        self._expand_timer.stop()
        self._collapse_timer.start(self._collapse_delay_ms)

    def _do_expand(self) -> None:
        if self._expanded:
            return
        self._expanded = True
        self._rebuild()
        # ponytail: 回退到 HEAD 的 width-only + 50ms 后 _fit_height snap —
        # 两轴同时 tween 在 QMainWindow 里被 layout 抢，4 次迭代未能稳定。
        # 动画平滑性让位给稳定性（30+ commit 验证过）。
        self._animate_width(self.COLLAPSED_WIDTH, self.EXPANDED_WIDTH, 180)

    def _do_collapse(self) -> None:
        if not self._expanded:
            return
        self._expanded = False
        self._rebuild()
        self._animate_width(self.EXPANDED_WIDTH, self.COLLAPSED_WIDTH, 180)

    def _animate_width(self, _from: int, to: int, duration_ms: int) -> None:
        rect = self.geometry()
        dx = to - self._current_width
        # 右对齐 — tween width 时 x 也同步滑动
        start_x = rect.x() - dx if dx != 0 else rect.x()
        self._current_width = to
        self._anim_t0 = time.perf_counter()
        self._anim_dur = duration_ms / 1000.0
        self._anim_start_g = rect
        self._anim_end_x = start_x
        self._anim_end_w = to
        # ponytail: QPropertyAnimation 在部分 Qt platform 下不产生 ticks（offscreen/
        # bash-QPA），用 QTimer 手动 tween — 每 16ms (~60fps) 一帧保证所有环境有帧
        timer = QTimer(self)
        timer.setInterval(16)
        timer.timeout.connect(lambda: self._anim_tick(timer, duration_ms))
        timer.start()

    def _anim_tick(self, timer: QTimer, duration_ms: int) -> None:
        t = (time.perf_counter() - self._anim_t0) / self._anim_dur
        t = min(1.0, max(0.0, t))
        # OutCubic easing: 1 - (1-t)³
        eased = 1.0 - (1.0 - t) ** 3
        cur_w = self._anim_start_g.width() + int((self._anim_end_w - self._anim_start_g.width()) * eased)
        cur_x = self._anim_start_g.x() - int((self._anim_end_w - self._anim_start_g.width()) * eased)
        self.setGeometry(cur_x, self._anim_start_g.y(), cur_w, self._anim_start_g.height())
        # 帧级日志 — 设 CSD_DEBUG=1 后写 %TEMP%/csd_anim_debug.log
        if os.environ.get("CSD_DEBUG"):
            import datetime as _dt
            _log_path = Path(os.environ.get("TEMP", ".")) / "csd_anim_debug.log"
            with open(_log_path, "a", encoding="utf-8") as _f:
                _f.write(f"{_dt.datetime.now():%H:%M:%S.%f} [anim:frame] t={t:.3f} eased={eased:.3f} g={cur_x},{self._anim_start_g.y()},{cur_w},{self._anim_start_g.height()}\n")
        if t >= 1.0:
            timer.stop()
            timer.deleteLater()
            QTimer.singleShot(50, self._fit_height)

    # ---- drag + edge snap ----
    def mousePressEvent(self, ev) -> None:
        if ev.button() == Qt.LeftButton:
            self._dragging = True
            self._drag_offset = ev.globalPosition().toPoint() - self.frameGeometry().topLeft()
            ev.accept()

    def mouseMoveEvent(self, ev) -> None:
        if self._dragging and (ev.buttons() & Qt.LeftButton):
            new_pos = ev.globalPosition().toPoint() - self._drag_offset
            self.move(new_pos)
            ev.accept()

    def mouseReleaseEvent(self, ev) -> None:
        if ev.button() == Qt.LeftButton and self._dragging:
            self._dragging = False
            self._maybe_snap()
            ev.accept()

    def _maybe_snap(self) -> None:
        screen = QApplication.primaryScreen()
        if screen is None:
            return
        geo = screen.availableGeometry()
        snap = 30
        x = self.x()
        if abs(geo.right() - (x + self.width())) < snap:
            self.move(geo.right() - self.width(), self.y())
        elif abs(geo.left() - x) < snap:
            self.move(geo.left(), self.y())
