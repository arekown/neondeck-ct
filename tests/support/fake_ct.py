"""Pty-basiertes Ersatzgeraet fuer Tests der CT-Verbindung (kein echtes Geraet)."""
import contextlib
import os
import select
import threading
import tty

HANDSHAKE_REPLY = (
    b"HTTP/1.1 101 Switching Protocols\r\n"
    b"Upgrade: websocket\r\n"
    b"Connection: Upgrade\r\n"
    b"Sec-WebSocket-Accept: s3pPLMBiTxaQ9kYGzzhZRbK+xOo=\r\n\r\n"
)
# Alter Tastenrahmen, der am echten Geraet vor dem 101-Kopf auftauchen kann.
STALE_FRAME = bytes.fromhex("82050500000900")
SERIAL = "CTTEST00000000000000000001"
CMD_SERIAL = 0x03


def device_frame(msg: bytes) -> bytes:
    """Geraet->Host: 0x82, Laenge ohne Maske."""
    n = len(msg)
    if n < 126:
        head = bytes([0x82, n])
    elif n < 65536:
        head = bytes([0x82, 126]) + n.to_bytes(2, "big")
    else:
        head = bytes([0x82, 127]) + n.to_bytes(8, "big")
    return head + msg


class _HostFrameParser:
    """Host->Geraet: 0x82, Laenge|0x80, 4 Maskenbytes (Null), Nutzdaten."""

    def __init__(self) -> None:
        self._buf = bytearray()

    def feed(self, data: bytes) -> list[bytes]:
        """Ganze Rahmen; bleibt an einer Rahmengrenze vor einem neuen Handshake (``GET ``)
        stehen, der Rest steht dann in ``handshake_rest``."""
        self._buf += data
        out = []
        while len(self._buf) >= 2:
            if b"GET ".startswith(bytes(self._buf[:4])):
                break  # Host hat neu geoeffnet (Anfang evtl. erst teilweise da)
            if self._buf[0] != 0x82:
                del self._buf[:1]
                continue
            n = self._buf[1] & 0x7F
            pos = 2
            if n == 126:
                if len(self._buf) < 4:
                    break
                n = int.from_bytes(self._buf[2:4], "big")
                pos = 4
            elif n == 127:
                if len(self._buf) < 10:
                    break
                n = int.from_bytes(self._buf[2:10], "big")
                pos = 10
            pos += 4  # Maske
            if len(self._buf) < pos + n:
                break
            out.append(bytes(self._buf[pos:pos + n]))
            del self._buf[:pos + n]
        return out

    def handshake_rest(self) -> bytes | None:
        return bytes(self._buf) if self._buf.startswith(b"GET ") else None


class FakeCT:
    """Antwortet auf den Handshake, sammelt Nachrichten, sendet Ereignisse."""

    def __init__(self, stale_before_header: bool = True) -> None:
        self._master, self._slave = os.openpty()
        tty.setraw(self._slave)
        self.path = os.ttyname(self._slave)
        self.received: list[bytes] = []
        self._stale = stale_before_header
        self._cond = threading.Condition()
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _write(self, data: bytes) -> None:
        with self._lock:
            view = memoryview(data)
            while view:
                n = os.write(self._master, view)
                view = view[n:]

    def _run(self) -> None:
        pending = b""
        parser: _HostFrameParser | None = None
        while not self._stop.is_set():
            try:
                r, _, _ = select.select([self._master], [], [], 0.05)
                if not r:
                    continue
                data = os.read(self._master, 65536)
            except OSError:
                return
            if not data:
                return
            while data:
                if parser is not None:
                    # Rahmen der alten Sitzung abarbeiten; ein neuer Handshake kann unter Last
                    # im selben Lesestueck direkt dahinter stehen (nicht nur am Anfang).
                    for msg in parser.feed(data):
                        self._handle(msg)
                    data = parser.handshake_rest()
                    if data is None:
                        break
                    parser, pending = None, b""  # Host hat neu geoeffnet: neuer Handshake
                pending += data
                data = b""
                if b"\r\n\r\n" not in pending:
                    break
                data = pending.split(b"\r\n\r\n", 1)[1]
                self._write((STALE_FRAME if self._stale else b"") + HANDSHAKE_REPLY)
                parser = _HostFrameParser()

    def _handle(self, msg: bytes) -> None:
        if len(msg) >= 3 and msg[1] == CMD_SERIAL:
            reply = SERIAL.encode() + b" "
            self._write(device_frame(bytes([3 + len(reply), CMD_SERIAL, msg[2]]) + reply))
        with self._cond:
            self.received.append(msg)
            self._cond.notify_all()

    def wait_received(self, predicate, timeout: float = 15.0) -> bool:
        """Wartet, bis predicate(self.received) wahr ist."""
        with self._cond:
            return self._cond.wait_for(lambda: predicate(self.received), timeout)

    def emit(self, msg_hex: str) -> None:
        self._write(device_frame(bytes.fromhex(msg_hex)))

    def close(self) -> None:
        """Simuliert Abstecken: Master schliessen -> Hangup auf der Host-Seite."""
        self._stop.set()
        self._thread.join(timeout=2)
        for fd in (self._slave, self._master):
            with contextlib.suppress(OSError):
                os.close(fd)
