# ruff: noqa: N802
"""Hollow ring + sonar pulse — empty-state marker, visually distinct from any session indicator."""

from __future__ import annotations

import time

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QWidget

_EMPTY_COLOR = QColor("#22C55E")     # 同 IDLE 绿 — 用形状而非颜色区分
_PULSE_PERIOD_MS = 2500
_PULSE_TICK_MS = 33
_RING_ALPHA = 0.85                  # 空心环基础透明度
_PULSE_PEAK_ALPHA = 0.55            # 声呐环峰值透明度


class EmptyStateIndicator(QWidget):
    """居中空心绿环 + 向外扩散渐隐的同心脉冲。"""

    def __init__(self, *, size_px: int = 12, parent=None) -> None:
        super().__init__(parent)
        # 给脉冲留出扩散空间（size_px * 3 不会撞到 layout 边界）
        self.setFixedSize(size_px * 3, size_px * 3)
        self._size_px = size_px
        self._phase = 0.0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(_PULSE_TICK_MS)

    def _tick(self) -> None:
        self._phase = ((time.time() * 1000) % _PULSE_PERIOD_MS) / _PULSE_PERIOD_MS
        self.update()

    def paintEvent(self, _ev) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        cx, cy = self.width() / 2, self.height() / 2
        half = self._size_px / 2
        # 1) 声呐脉冲: 从 half 扩散到边缘, alpha 渐隐
        max_r = (self.width() / 2) - 1
        pulse_r = half + self._phase * (max_r - half)
        pulse_a = _PULSE_PEAK_ALPHA * (1.0 - self._phase)
        pulse = QColor(_EMPTY_COLOR)
        pulse.setAlphaF(max(0.0, pulse_a))
        p.setPen(pulse)
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(int(cx - pulse_r), int(cy - pulse_r), int(pulse_r * 2), int(pulse_r * 2))
        # 2) 中心空心环（marker）
        ring = QColor(_EMPTY_COLOR)
        ring.setAlphaF(_RING_ALPHA)
        p.setPen(ring)
        p.drawEllipse(int(cx - half), int(cy - half), self._size_px, self._size_px)
        p.end()