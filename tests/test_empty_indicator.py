# ruff: noqa: N802
"""EmptyStateIndicator — 空心环 + 声呐脉冲，区别于任何 session indicator。"""

from __future__ import annotations

from PySide6.QtGui import QColor

from src.ui.empty_indicator import (
    EmptyStateIndicator,
    _EMPTY_COLOR,
    _PULSE_PERIOD_MS,
)


def test_color_matches_idle_green():
    assert _EMPTY_COLOR == QColor("#22C55E")


def test_pulse_period_is_2_5_seconds():
    assert _PULSE_PERIOD_MS == 2500


def test_widget_starts_sonar_timer(qapp):
    w = EmptyStateIndicator(size_px=12)
    qapp.processEvents()
    assert w._timer is not None
    assert w._timer.isActive()


def test_widget_paints_without_crash(qapp):
    w = EmptyStateIndicator(size_px=12)
    w.show()
    qapp.processEvents()
    # 推进 phase 到脉冲中段 — 触发 pulse draw 分支
    w._phase = 0.5
    w.update()
    qapp.processEvents()
    assert w.isVisible()