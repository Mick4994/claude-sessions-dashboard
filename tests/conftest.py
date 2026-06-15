import pytest
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="session")
def qapp():
    """Session-scoped QApplication for all tests that need a Qt event loop."""
    app = QApplication.instance() or QApplication([])
    yield app
    app.quit()
