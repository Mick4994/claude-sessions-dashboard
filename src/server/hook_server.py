"""HookServer: lightweight HTTP server that receives CC hook events via curl."""

from __future__ import annotations

import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

from .router import HookRouter

logger = logging.getLogger(__name__)


class _HookHandler(BaseHTTPRequestHandler):
    router: HookRouter

    def log_message(self, fmt: str, *args: object) -> None:
        logger.debug(fmt, *args)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")
        qs = parse_qs(parsed.query)
        sid = qs.get("sid", [None])[0]

        # /hook/Stop?sid=xxx  →  event = "Stop"
        if not path.startswith("/hook/"):
            self._respond(404, {"error": "not found"})
            return

        event = path[len("/hook/") :]
        if not event:
            self._respond(400, {"error": "missing event name"})
            return

        # Read body (hook payload) — we don't parse it, just drain to avoid RST.
        content_len = int(self.headers.get("Content-Length", 0))
        if content_len > 0:
            self.rfile.read(content_len)

        ok = self.router.route(event, sid)
        if ok:
            self._respond(200, {"ok": True})
        elif sid is None:
            logger.warning("Hook %s received without session_id", event)
            self._respond(200, {"ok": True, "note": "missing sid"})
        else:
            logger.warning("Hook %s for unknown sid=%s", event, sid)
            self._respond(200, {"ok": True, "note": "unknown sid"})

    def _respond(self, code: int, body: dict) -> None:
        data = json.dumps(body).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


class HookServer:
    """Runs an HTTP server on localhost for CC hook callbacks.
    Runs in a daemon thread — start() returns immediately."""

    def __init__(self, host: str, port: int, router: HookRouter) -> None:
        self._host = host
        self._port = port
        self._router = router
        self._httpd: HTTPServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def url(self) -> str:
        return f"http://{self._host}:{self._port}"

    def start(self) -> None:
        handler = type(
            "_BoundHandler",
            (_HookHandler,),
            {"router": self._router},
        )
        self._httpd = HTTPServer((self._host, self._port), handler)
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()
        logger.info("HookServer listening on %s", self.url)

    def stop(self) -> None:
        if self._httpd is not None:
            self._httpd.shutdown()
            self._httpd.server_close()
            self._httpd = None
        if self._thread is not None:
            self._thread.join(timeout=2)
            self._thread = None

    def __enter__(self) -> HookServer:
        self.start()
        return self

    def __exit__(self, *_: object) -> None:
        self.stop()
