"""Loupedeck-CT-Protokoll: Rahmen, Nachrichten, Ereignisse (ohne I/O)."""
from dataclasses import dataclass

CMD_LEDS = 0x02
CMD_SERIAL = 0x03
CMD_FIRMWARE = 0x07
CMD_BRIGHTNESS = 0x09
CMD_DRAW = 0x0F
CMD_WRITE = 0x10
CMD_VIBRATE = 0x1B
FORBIDDEN_COMMANDS = frozenset({0x06, 0x17, 0x18})

HANDSHAKE = (
    b"GET /index.html HTTP/1.1\r\n"
    b"Connection: Upgrade\r\n"
    b"Upgrade: websocket\r\n"
    b"Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\n\r\n"
)

# Groesster plausibler Rahmen (ein volles Display ist ~190 KB); groessere Laengen = Muell.
MAX_FRAME_LENGTH = 1_048_576

EVT_BUTTON = 0x00
EVT_ROTATE = 0x01
EVT_TOUCH_DOWN = 0x4D
EVT_TOUCH_UP = 0x6D
EVT_WHEEL_DOWN = 0x52
EVT_WHEEL_UP = 0x72


def encode_frame(payload: bytes) -> bytes:
    """Host->Geraet: 0x82, Laenge|0x80, 4 Null-Maskenbytes, Nutzdaten."""
    n = len(payload)
    if n < 126:
        head = bytes([0x82, 0x80 | n])
    elif n < 65536:
        head = bytes([0x82, 0x80 | 126]) + n.to_bytes(2, "big")
    else:
        head = bytes([0x82, 0x80 | 127]) + n.to_bytes(8, "big")
    return head + b"\0\0\0\0" + payload


# Laengenangabe im zweiten Byte: 126 = 2 Bytes folgen, 127 = 8 Bytes folgen
_EXTENDED_LENGTH = {126: 2, 127: 8}


def _frame_header(buf: bytearray) -> tuple[int, int] | None:
    """(Laenge der Nutzdaten, Beginn der Nutzdaten) eines Rahmens am Anfang von ``buf``;
    ``None``, solange der Kopf noch nicht vollstaendig da ist."""
    if len(buf) < 2:
        return None
    n = buf[1] & 0x7F
    extra = _EXTENDED_LENGTH.get(n, 0)
    if len(buf) < 2 + extra:
        return None
    if extra:
        n = int.from_bytes(buf[2:2 + extra], "big")
    return n, 2 + extra


class FrameReader:
    """Gerät->Host: setzt Rahmen aus beliebig zerstückelten Bytes zusammen."""

    def __init__(self) -> None:
        self._buf = bytearray()

    def feed(self, data: bytes) -> list[bytes]:
        self._buf += data
        out: list[bytes] = []
        while True:
            i = self._buf.find(0x82)
            if i < 0:
                self._buf.clear()
                break
            if i:
                del self._buf[:i]
            header = _frame_header(self._buf)
            if header is None:
                break
            n, pos = header
            if n > MAX_FRAME_LENGTH:
                del self._buf[:1]  # kein echter Rahmenanfang: neu synchronisieren
                continue
            if len(self._buf) < pos + n:
                break
            out.append(bytes(self._buf[pos:pos + n]))
            del self._buf[:pos + n]
        return out


def build_message(typ: int, txid: int, data: bytes = b"") -> bytes:
    return bytes([min(3 + len(data), 255), typ, txid]) + data


@dataclass(frozen=True)
class ButtonEvent:
    code: int
    pressed: bool


@dataclass(frozen=True)
class RotateEvent:
    code: int
    delta: int


@dataclass(frozen=True)
class TouchEvent:
    finger: int
    x: int
    y: int
    down: bool


@dataclass(frozen=True)
class WheelTouchEvent:
    finger: int
    x: int
    y: int
    down: bool


Event = ButtonEvent | RotateEvent | TouchEvent | WheelTouchEvent


def parse_event(msg: bytes) -> Event | None:
    if len(msg) < 5 or msg[2] != 0:
        return None
    typ = msg[1]
    if typ == EVT_BUTTON:
        return ButtonEvent(msg[3], msg[4] == 0)
    if typ == EVT_ROTATE:
        return RotateEvent(msg[3], 1 if msg[4] == 1 else -1)
    if typ in (EVT_TOUCH_DOWN, EVT_TOUCH_UP, EVT_WHEEL_DOWN, EVT_WHEEL_UP):
        if len(msg) < 8:
            return None
        x = int.from_bytes(msg[4:6], "big")
        y = int.from_bytes(msg[6:8], "big")
        if typ in (EVT_TOUCH_DOWN, EVT_TOUCH_UP):
            return TouchEvent(msg[3], x, y, typ == EVT_TOUCH_DOWN)
        return WheelTouchEvent(msg[3], x, y, typ == EVT_WHEEL_DOWN)
    return None
