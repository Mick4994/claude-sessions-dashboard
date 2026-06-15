# ruff: noqa: E501, N802
"""Indicator dot widget with color-coded status and blink animation."""

from __future__ import annotations

import time

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QPainter
from PySide6.QtWidgets import QWidget

from ..collector.models import SessionStatus

_COLORS: dict[SessionStatus, QColor] = {
    SessionStatus.WORKING: QColor("#3B82F6"),
    SessionStatus.IDLE: QColor("#22C55E"),
    SessionStatus.PERMISSION: QColor("#EAB308"),
    SessionStatus.ERROR: QColor("#EF4444"),
    SessionStatus.STALE: QColor("#6B7280"),
}

_BLINK_MS: dict[SessionStatus, int] = {
    SessionStatus.WORKING: 1000,
    SessionStatus.ERROR: 700,
}


def status_color(s: SessionStatus) -> QColor:
    return _COLORS[s]


def status_blink_ms(s: SessionStatus) -> int:
    return _BLINK_MS.get(s, 0)


class IndicatorDot(QWidget):
    """Circular status indicator with optional blink animation."""

    def __init__(self, status: SessionStatus, *, size_px: int = 12, parent=None) -> None:
        super().__init__(parent)
        self._size_px = size_px
        self._color = status_color(status)
        self._opacity = 1.0
        self._timer: QTimer | None = None
        self._period_ms = 0
        self.set_status(status)

    @property
    def _period_ms(self) -> int:
        return self.__period_ms

    @_period_ms.setter
    def _period_ms(self, value: int) -> None:
        self.__period_ms = value

    _period_ms = property(lambda self: self.__period_ms, _period_ms.fset)

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
        r = self._size_px / 2
        cx = self.width() / 2
        cy = self.height() / 2
        p.drawEllipse(int(cx - r), int(cy - r), int(r * 2), int(r * 2))
        hl = QColor(255, 255, 255, 60)
        p.setBrush(QBrush(hl))
        p.drawEllipse(int(cx - r * 0.55), int(cy - r * 0.7), int(r * 0.6), int(r * 0.45))
        p.end()
