"""Single-instance lock via QLocalServer."""

from __future__ import annotations

from PySide6.QtNetwork import QLocalServer, QLocalSocket

SOCKET_NAME = "claude-sessions-dashboard-singleton"


def try_acquire() -> tuple[QLocalServer | None, bool]:
    """Try to become the singleton. Returns (server, is_primary).
    If another instance is already running, sends 'show' to it and returns (None, False).
    """
    sock = QLocalSocket()
    sock.connectToServer(SOCKET_NAME)
    if sock.waitForConnected(300):
        sock.write(b"show")
        sock.flush()
        sock.disconnectFromServer()
        return None, False

    server = QLocalServer()
    QLocalServer.removeServer(SOCKET_NAME)
    if not server.listen(SOCKET_NAME):
        return None, True
    return server, True
