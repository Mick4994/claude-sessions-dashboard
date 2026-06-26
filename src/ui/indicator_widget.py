# ruff: noqa: E501, N802
"""Indicator dot widget with color-coded status and blink animation."""
from __future__ import annotations

import time

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QPainter
from PySide6.QtWidgets import QWidget

from ..collector.models import SessionStatus

# 3-state map: IDLE 🟢 / WORKING 🟡 (blink) / PERMISSION 🔴
_COLORS: dict[SessionStatus, QColor] = {
    SessionStatus.WORKING: QColor("#EAB308"),       # yellow
    SessionStatus.IDLE: QColor("#22C55E"),           # green
    SessionStatus.PERMISSION: QColor("#EF4444"),     # red
}

_BLINK_MS: dict[SessionStatus, int] = {
    SessionStatus.WORKING: 1000,   # yellow blink 1Hz
}


def status_color(s: SessionStatus) -> QColor:
    return _COLORS[s]


def status_blink_ms(s: SessionStatus) -> int:
    return _BLINK_MS.get(s, 0)


class IndicatorDot(QWidget):
    """Circular status indicator with optional blink animation."""

    def __init__(
        self,
        status: SessionStatus,
        *,
        size_px: int = 12,
        session_id: str | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        e = max(4, size_px + 6)
        self.setFixedSize(e, e)
        self._size_px = size_px
        self._session_id = session_id
        self._color = status_color(status)
        self._opacity = 1.0
        self._timer: QTimer | None = None
        self._period_ms = 0
        self._hover = False
        self.setMouseTracking(True)
        self.set_status(status)

    @property
    def _period_ms(self) -> int:
        return self.__period_ms

    @_period_ms.setter
    def _period_ms(self, value: int) -> None:
        self.__period_ms = value

    _period_ms = property(lambda self: self.__period_ms, _period_ms.fset)

    def enterEvent(self, ev) -> None:
        self._hover = True
        self.update()
        super().enterEvent(ev)

    def leaveEvent(self, ev) -> None:
        self._hover = False
        self.update()
        super().leaveEvent(ev)

    def mousePressEvent(self, ev) -> None:
        if ev.button() == Qt.LeftButton and self._session_id:
            from .signal_bus import signalBus

            signalBus.cardClicked.emit(self._session_id)
        super().mousePressEvent(ev)

    def set_status(self, s: SessionStatus) -> None:
        self._color = status_color(s)
        period = status_blink_ms(s)
        self.__period_ms = period
        if self._timer is not None:
            self._timer.stop()
            self._timer = None
        if period > 0:
            self._timer = QTimer(self)
            self._timer.timeout.connect(self._tick)
            self._timer.start(33)
        self._opacity = 1.0
        self.update()

    def _tick(self) -> None:
        t = (time.time() * 1000) % self.__period_ms
        phase = t / self.__period_ms
        self._opacity = 0.55 + 0.45 * (1 - abs(2 * phase - 1))
        self.update()

    def paintEvent(self, _ev) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        c = QColor(self._color)
        c.setAlphaF(max(0.2, min(1.0, self._opacity)))
        p.setBrush(QBrush(c))
        p.setPen(Qt.NoPen)
        eff = self._size_px + 2 if self._hover else self._size_px
        rr = eff / 2
        cx = self.width() / 2
        cy = self.height() / 2
        p.drawEllipse(int(cx - rr), int(cy - rr), int(rr * 2), int(rr * 2))
        # inner highlight
        hl = QColor(255, 255, 255, 60)
        p.setBrush(QBrush(hl))
        p.drawEllipse(int(cx - rr * 0.55), int(cy - rr * 0.7), int(rr * 0.6), int(rr * 0.45))
        p.end()
