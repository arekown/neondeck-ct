"""HTTP-Aktion: Methoden, Kopfzeilen, Statuscodes, Zeitlimit."""
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from neondeck.actions import execute, registry
from neondeck.actions import http as http_action
from neondeck.actions.base import Result
from support.fakes import make_ctx

# --- HTTP ------------------------------------------------------------------------------

class _Handler(BaseHTTPRequestHandler):
    seen: list = []

    def _answer(self, code):
        n = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(n).decode() if n else ""
        self.seen.append((self.command, self.path, self.headers.get("X-Token"), body))
        self.send_response(code)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):  # noqa: N802 - Name von BaseHTTPRequestHandler vorgegeben
        self._answer(404 if self.path == "/fehlt" else 200)

    def do_POST(self):  # noqa: N802 - Name von BaseHTTPRequestHandler vorgegeben
        self._answer(201)

    def log_message(self, *args):
        pass


@pytest.fixture
def http_server():
    _Handler.seen = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{server.server_address[1]}", _Handler.seen
    server.shutdown()
    server.server_close()


def test_http_get_status(http_server):
    base, seen = http_server
    assert http_action.TIMEOUT_S == 5
    r = execute({"type": "http", "method": "GET", "url": base + "/hallo"}, make_ctx())
    assert r == Result(True, "200")
    r = execute({"type": "http", "method": "POST", "url": base + "/hook",
                 "headers": "X-Token: geheim\nContent-Type: text/plain\n\nkaputt-ohne-doppelpunkt",
                 "body": "Grüße"}, make_ctx())
    assert r == Result(True, "201")
    assert seen == [("GET", "/hallo", None, ""), ("POST", "/hook", "geheim", "Grüße")]
    r = execute({"type": "http", "url": base + "/fehlt"}, make_ctx())  # GET ist Standard
    assert not r.ok and "404" in r.message
    for bad in ("file:///etc/passwd", "ftp://x/y", "", "localhost:80"):
        r = execute({"type": "http", "url": bad}, make_ctx())
        assert not r.ok and "http" in r.message.lower()
    r = execute({"type": "http", "method": "PATCH", "url": base}, make_ctx())
    assert not r.ok
    assert registry()["http"].params[0].choices == ["GET", "POST", "PUT", "DELETE"]


def test_http_timeout_false(monkeypatch):
    """Server nimmt die Verbindung an, antwortet aber nie: nach dem Zeitlimit False."""
    default = http_action.TIMEOUT_S
    monkeypatch.setattr(http_action, "TIMEOUT_S", 0.3)
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    sock.listen(1)
    try:
        t0 = time.monotonic()
        r = execute({"type": "http", "url": f"http://127.0.0.1:{sock.getsockname()[1]}/"},
                    make_ctx())
        assert time.monotonic() - t0 < default  # das eingestellte Limit gilt, nicht 5 s
        assert not r.ok and "Zeit" in r.message
        closed = socket.socket()
        closed.bind(("127.0.0.1", 0))
        port = closed.getsockname()[1]
        closed.close()  # niemand lauscht: Verbindung abgelehnt
        r = execute({"type": "http", "url": f"http://127.0.0.1:{port}/"}, make_ctx())
        assert not r.ok
    finally:
        sock.close()
