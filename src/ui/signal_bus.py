# ruff: noqa: N815, N816
"""Signal bus for cross-component communication."""

from PySide6.QtCore import QObject, Signal


class _Bus(QObject):
    cardClicked = Signal(str)  # session_id
    requestQuit = Signal()
    requestReloadConfig = Signal()
    requestPause = Signal(bool)


signalBus = _Bus()
