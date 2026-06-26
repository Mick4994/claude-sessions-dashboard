"""Tests for indicator widget — 3-state color mapping + WORKING-only blink."""
from PySide6.QtGui import QColor

from src.collector.models import SessionStatus
from src.ui.indicator_widget import IndicatorDot, status_blink_ms, status_color


# TC-011: 3-state color map (IDLE/WORKING/PERMISSION).
def test_color_idle_is_green():
    assert status_color(SessionStatus.IDLE) == QColor("#22C55E")


def test_color_working_is_yellow():
    assert status_color(SessionStatus.WORKING) == QColor("#EAB308")


def test_color_permission_is_red():
    assert status_color(SessionStatus.PERMISSION) == QColor("#EF4444")


# TC-019: only WORKING blinks.
def test_blink_only_for_working():
    assert status_blink_ms(SessionStatus.WORKING) == 1000


def test_no_blink_for_idle():
    assert status_blink_ms(SessionStatus.IDLE) == 0


def test_no_blink_for_permission():
    assert status_blink_ms(SessionStatus.PERMISSION) == 0


# Widget integration
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


def test_indicator_dot_switch_to_non_blinking_stops_timer(qapp):
    """Switching away from WORKING must stop the blink timer."""
    dot = IndicatorDot(SessionStatus.WORKING, size_px=12)
    qapp.processEvents()
    assert dot._timer is not None
    dot.set_status(SessionStatus.IDLE)
    qapp.processEvents()
    assert dot._timer is None
    assert dot._period_ms == 0
