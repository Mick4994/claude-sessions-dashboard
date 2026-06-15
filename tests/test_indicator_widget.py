"""Tests for indicator widget — color mapping + blinking dot."""

from PySide6.QtGui import QColor

from src.collector.models import SessionStatus
from src.ui.indicator_widget import IndicatorDot, status_blink_ms, status_color


def test_status_color_mapping():
    assert status_color(SessionStatus.WORKING) == QColor("#3B82F6")
    assert status_color(SessionStatus.IDLE) == QColor("#22C55E")
    assert status_color(SessionStatus.PERMISSION) == QColor("#EAB308")
    assert status_color(SessionStatus.ERROR) == QColor("#EF4444")
    assert status_color(SessionStatus.STALE) == QColor("#6B7280")


def test_status_blink_ms():
    assert status_blink_ms(SessionStatus.WORKING) == 1000
    assert status_blink_ms(SessionStatus.ERROR) == 700
    assert status_blink_ms(SessionStatus.IDLE) == 0
    assert status_blink_ms(SessionStatus.PERMISSION) == 0
    assert status_blink_ms(SessionStatus.STALE) == 0


def test_indicator_dot_creation(qapp):
    dot = IndicatorDot(SessionStatus.IDLE, size_px=12)
    dot.show()
    qapp.processEvents()
    assert dot.isVisible()


def test_indicator_dot_status_change(qapp):
    dot = IndicatorDot(SessionStatus.IDLE, size_px=12)
    dot.show()
    qapp.processEvents()
    dot.set_status(SessionStatus.WORKING)
    dot.show()
    qapp.processEvents()
    assert dot._period_ms == 1000
