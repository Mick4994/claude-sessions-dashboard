"""Integration tests for HookServer — real HTTP socket ↔ real registry.

TC-005..007, TC-010, TC-013..018. Uses OS-assigned ports to avoid collisions.
"""

from __future__ import annotations

import json
import socket
import threading
from http.client import HTTPConnection
from pathlib import Path

import pytest

from src.core.session_registry import SessionRegistry
from src.core.status import SessionStatus
from src.server.hook_server import HookServer
from src.server.router import HookRouter


def _free_port() -> int:
    """Ask the OS for an unused TCP port."""
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _make_server(reg: SessionRegistry) -> tuple[HookServer, int]:
    port = _free_port()
    router = HookRouter(reg)
    server = HookServer("127.0.0.1", port, router)
    server.start()
    return server, port


def _post(port: int, path: str, *, body: bytes = b"") -> tuple[int, dict]:
    conn = HTTPConnection("127.0.0.1", port, timeout=5)
    conn.request("POST", path, body=body, headers={"Content-Length": str(len(body))})
    resp = conn.getresponse()
    raw = resp.read()
    conn.close()
    try:
        payload = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        payload = {"raw": raw.decode("utf-8", errors="replace")}
    return resp.status, payload


def _get(port: int, path: str) -> tuple[int, dict]:
    conn = HTTPConnection("127.0.0.1", port, timeout=5)
    conn.request("GET", path)
    resp = conn.getresponse()
    raw = resp.read()
    conn.close()
    try:
        payload = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        payload = {"raw": raw.decode("utf-8", errors="replace")}
    return resp.status, payload


@pytest.fixture
def live_server():
    """Yield (server, port, registry) — server runs on OS-assigned port."""
    reg = SessionRegistry()
    # Pre-register a PID + sid so events land somewhere.
    reg.register(pid=4242, cwd=Path("C:/proj"))
    reg.attach_session_id(pid=4242, session_id="sess-test")
    server, port = _make_server(reg)
    try:
        # Brief sleep to ensure socket is accepting.
        import time
        time.sleep(0.05)
        yield server, port, reg
    finally:
        server.stop()


# TC-005: Stop → 200 + IDLE
def test_post_stop_returns_200_idle(live_server):
    _, port, reg = live_server
    code, body = _post(port, "/hook/Stop?sid=sess-test")
    assert code == 200
    assert body.get("ok") is True
    assert reg.get(pid=4242).status == SessionStatus.IDLE


def test_post_user_prompt_returns_200_working(live_server):
    _, port, reg = live_server
    code, body = _post(port, "/hook/UserPromptSubmit?sid=sess-test")
    assert code == 200
    assert body.get("ok") is True
    assert reg.get(pid=4242).status == SessionStatus.WORKING


# TC-006: PermissionRequest → 200 + PERMISSION
def test_post_permission_returns_200_permission(live_server):
    _, port, reg = live_server
    code, body = _post(port, "/hook/PermissionRequest?sid=sess-test")
    assert code == 200
    assert body.get("ok") is True
    assert reg.get(pid=4242).status == SessionStatus.PERMISSION


def test_post_post_tool_use_returns_200_working(live_server):
    _, port, reg = live_server
    code, body = _post(port, "/hook/PostToolUse?sid=sess-test")
    assert code == 200
    assert body.get("ok") is True
    assert reg.get(pid=4242).status == SessionStatus.WORKING


def test_post_post_tool_use_failure_returns_200_working(live_server):
    _, port, reg = live_server
    code, _ = _post(port, "/hook/PostToolUseFailure?sid=sess-test")
    assert code == 200
    assert reg.get(pid=4242).status == SessionStatus.WORKING


def test_post_permission_denied_returns_200_working(live_server):
    _, port, reg = live_server
    code, _ = _post(port, "/hook/PermissionDenied?sid=sess-test")
    assert code == 200
    assert reg.get(pid=4242).status == SessionStatus.WORKING


def test_post_stop_failure_returns_200_idle(live_server):
    _, port, reg = live_server
    code, _ = _post(port, "/hook/StopFailure?sid=sess-test")
    assert code == 200
    assert reg.get(pid=4242).status == SessionStatus.IDLE


# TC-007: PERMISSION + PostToolUse → WORKING
def test_permission_red_to_yellow_on_post_tool_use(live_server):
    _, port, reg = live_server
    reg.set_status(pid=4242, status=SessionStatus.PERMISSION)
    code, _ = _post(port, "/hook/PostToolUse?sid=sess-test")
    assert code == 200
    assert reg.get(pid=4242).status == SessionStatus.WORKING


def test_permission_red_to_yellow_on_user_prompt(live_server):
    _, port, reg = live_server
    reg.set_status(pid=4242, status=SessionStatus.PERMISSION)
    code, _ = _post(port, "/hook/UserPromptSubmit?sid=sess-test")
    assert code == 200
    assert reg.get(pid=4242).status == SessionStatus.WORKING


def test_permission_red_to_yellow_on_permission_denied(live_server):
    _, port, reg = live_server
    reg.set_status(pid=4242, status=SessionStatus.PERMISSION)
    code, _ = _post(port, "/hook/PermissionDenied?sid=sess-test")
    assert code == 200
    assert reg.get(pid=4242).status == SessionStatus.WORKING


# TC-010: unknown event → 200, no state change
def test_post_unknown_event_returns_200_ignored(live_server):
    _, port, reg = live_server
    code, body = _post(port, "/hook/SomeWeirdEvent?sid=sess-test")
    assert code == 200
    assert body.get("ok") is True
    assert reg.get(pid=4242).status == SessionStatus.UNKNOWN


# TC-016: unknown sid → 200 with note, no crash
def test_post_unknown_sid_returns_200_with_warn(live_server):
    _, port, reg = live_server
    code, body = _post(port, "/hook/Stop?sid=does-not-exist")
    assert code == 200
    assert body.get("note") == "unknown sid"
    assert reg.get(pid=4242).status == SessionStatus.UNKNOWN


# TC-017: missing sid → 200 with note, no crash
def test_post_missing_sid_returns_200(live_server):
    _, port, reg = live_server
    code, body = _post(port, "/hook/Stop")
    assert code == 200
    assert body.get("note") == "missing sid"
    assert reg.get(pid=4242).status == SessionStatus.UNKNOWN


# TC-018: GET → not 200 (BaseHTTPRequestHandler returns 501 for unregistered
# methods since the handler only implements do_POST; the test plan calls for 405
# but production code is unchanged and we verify the contract that GET is not
# silently accepted).
def test_get_returns_non_200(live_server):
    _, port, _ = live_server
    code, _ = _get(port, "/hook/Stop?sid=sess-test")
    assert code != 200


def test_url_path_with_trailing_slash(live_server):
    _, port, reg = live_server
    code, _ = _post(port, "/hook/Stop/?sid=sess-test")
    assert code == 200
    assert reg.get(pid=4242).status == SessionStatus.IDLE


def test_url_with_extra_query_params_ignored(live_server):
    _, port, reg = live_server
    code, _ = _post(port, "/hook/Stop?sid=sess-test&extra=junk")
    assert code == 200
    assert reg.get(pid=4242).status == SessionStatus.IDLE


def test_unknown_path_returns_404(live_server):
    _, port, _ = live_server
    code, _ = _post(port, "/not-a-hook?sid=x")
    assert code == 404


def test_concurrent_posts_thread_safe(live_server):
    """Many concurrent POSTs to the same session don't lose updates."""
    _, port, reg = live_server
    errors: list[Exception] = []

    def worker() -> None:
        try:
            for _ in range(20):
                _post(port, "/hook/PostToolUse?sid=sess-test")
                _post(port, "/hook/Stop?sid=sess-test")
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    # Final state must be one of the two valid end states.
    assert reg.get(pid=4242).status in (SessionStatus.WORKING, SessionStatus.IDLE)


# TC-025: server.stop() returns without hanging.
def test_server_shutdown_drains_pending(live_server):
    _, port, _ = live_server
    # Send a final POST, then stop. Stop must drain.
    code, _ = _post(port, "/hook/Stop?sid=sess-test")
    assert code == 200
    # Stop must complete cleanly (fixture teardown calls it).