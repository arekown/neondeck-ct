"""Verbindung zum Loupedeck CT: Hintergrund-Thread mit Handshake und Wiederverbinden."""
import contextlib
import logging
import struct
import threading
import time
from collections.abc import Callable

import serial

from ..core.errors import LoupedeckError
from ..core.i18n import tr
from .discovery import find_ct
from .layout import Display
from .protocol import (
    CMD_BRIGHTNESS,
    CMD_DRAW,
    CMD_FIRMWARE,
    CMD_LEDS,
    CMD_SERIAL,
    CMD_VIBRATE,
    CMD_WRITE,
    FORBIDDEN_COMMANDS,
    HANDSHAKE,
    Event,
    FrameReader,
    build_message,
    encode_frame,
    parse_event,
)

log = logging.getLogger(__name__)

RETRY_INTERVAL = 1.0
HANDSHAKE_TIMEOUT = 2.5
READ_TIMEOUT = 0.1
WRITE_TIMEOUT = 2.0
HEADER_END = b"\r\n\r\n"
STOP_TIMEOUT = HANDSHAKE_TIMEOUT + 1


class HandshakeError(LoupedeckError):
    pass


def _ignore(*_args) -> None:
    pass


class CTDevice:
    """Haelt die Verbindung im eigenen Thread; Callbacks laufen in diesem Thread."""

    def __init__(
        self,
        port_finder: Callable[[], str | None] = find_ct,
        on_event: Callable[[Event], None] = _ignore,
        on_state: Callable[[bool], None] = _ignore,
    ) -> None:
        self._port_finder = port_finder
        self._on_event = on_event
        self._on_state = on_state
        # Je Thread ein eigenes Stopp-Ereignis: ein start() nach einem haengenden stop()
        # darf den alten Thread nicht wiederbeleben.
        self._stop = threading.Event()
        self._stop.set()
        self._thread: threading.Thread | None = None
        self._reconnect = threading.Event()  # aktuelle Sitzung schliessen, sofort neu verbinden
        self._write_lock = threading.RLock()
        self._ser: serial.Serial | None = None
        self._txid = 0
        self._serial: str | None = None
        self._serial_known = threading.Event()
        self._firmware: str | None = None
        self._last_error = ""

    # --- Lebenszyklus -------------------------------------------------------

    def start(self) -> None:
        old = self._thread
        if old and old.is_alive() and not self._stop.is_set():
            return  # laeuft schon
        stop = threading.Event()
        self._stop = stop
        # Haengt ein alter Thread noch im Beenden, wartet der neue auf ihn (nie zwei Sitzungen).
        self._thread = threading.Thread(target=self._run, args=(stop, old), name="ct-device",
                                        daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread and thread is not threading.current_thread():
            thread.join(timeout=STOP_TIMEOUT)
            if thread.is_alive():
                log.warning("CT-Thread beendet sich nicht rechtzeitig")
            elif self._thread is thread:
                self._thread = None

    def reconnect(self) -> None:
        """Aktuelle Sitzung schliessen; der Thread verbindet ohne Wartezeit neu (z. B. nach
        dem Standby, wenn die alte Verbindung stumm haengen koennte). Ohne Sitzung harmlos."""
        self._reconnect.set()

    def _run(self, stop: threading.Event, previous: threading.Thread | None = None) -> None:
        if previous is not None and previous is not threading.current_thread():
            previous.join()
        while not stop.is_set():
            self._reconnect.clear()
            try:
                port = self._port_finder()
            except Exception:
                log.exception("Gerätesuche fehlgeschlagen")
                port = None
            if port and not stop.is_set():
                self._session(port, stop)
            if not self._reconnect.is_set():
                stop.wait(RETRY_INTERVAL)

    def _session(self, port: str, stop: threading.Event) -> None:
        """Eine Verbindung von Öffnen bis Trennung; Fehler werden geloggt, nie geworfen."""
        ser = None
        connected = False
        try:
            try:
                # exclusive: ein zweiter Prozess bekommt einen klaren Fehler statt Datensalat.
                ser = serial.Serial(
                    port, 9600, bytesize=serial.EIGHTBITS, parity=serial.PARITY_NONE,
                    stopbits=serial.STOPBITS_TWO, timeout=READ_TIMEOUT,
                    write_timeout=WRITE_TIMEOUT, exclusive=True,
                )
            except serial.SerialException as e:
                if "lock" in str(e).lower():
                    raise serial.SerialException(
                        tr("belegt (läuft schon eine andere Loupedeck-Software?): {e}", e=e)) from e
                raise
            rest = self._handshake(ser, stop)
            reader = FrameReader()  # pro Verbindung frisch
            with self._write_lock:
                self._ser = ser
            connected = True
            self._last_error = ""
            log.info("CT verbunden: %s", port)
            self._notify_state(True)
            self.send(CMD_SERIAL)
            self._dispatch(reader.feed(rest))
            while not stop.is_set() and not self._reconnect.is_set():
                data = ser.read(ser.in_waiting or 1)
                if data:
                    self._dispatch(reader.feed(data))
        except (serial.SerialException, OSError, HandshakeError) as e:
            # Gleicher Fehler bei jedem Versuch (z. B. keine Rechte) nur einmal laut loggen.
            msg = f"{port}: {e}"
            log.log(logging.DEBUG if msg == self._last_error else logging.INFO,
                    "CT-Verbindung %s", msg)
            self._last_error = msg
        except Exception:
            log.exception("Unerwarteter Fehler in der CT-Verbindung")
        finally:
            with self._write_lock:
                self._ser = None
            self._serial = None
            self._serial_known.clear()
            self._firmware = None
            if ser is not None:
                with contextlib.suppress(Exception):
                    ser.close()
            if connected:
                log.info("CT getrennt: %s%s", port,
                         " (neu verbinden)" if self._reconnect.is_set() else "")
                self._notify_state(False)

    def _handshake(self, ser: serial.Serial, stop: threading.Event) -> bytes:
        """Sendet BREAK + Upgrade-Anfrage; gibt die Bytes nach dem HTTP-Kopf zurück."""
        try:
            ser.send_break(0.1)
        except (serial.SerialException, OSError) as e:  # z. B. pty in Tests
            log.debug("BREAK nicht möglich: %s", e)
        ser.reset_input_buffer()
        ser.write(HANDSHAKE)
        buf = b""
        end = time.monotonic() + HANDSHAKE_TIMEOUT
        while HEADER_END not in buf:
            if stop.is_set() or time.monotonic() >= end:
                raise HandshakeError(tr("keine Handshake-Antwort"))
            buf += ser.read(ser.in_waiting or 1)
        # Vor dem Kopf können alte Ereignis-Rahmen stehen: alles bis Kopfende verwerfen.
        return buf.split(HEADER_END, 1)[1]

    # --- Empfang ------------------------------------------------------------

    def _dispatch(self, messages: list[bytes]) -> None:
        for msg in messages:
            if len(msg) < 3:
                continue
            if msg[2] == 0:
                ev = parse_event(msg)
                if ev is not None:
                    try:
                        self._on_event(ev)
                    except Exception:
                        log.exception("Fehler im Ereignis-Verbraucher (%s)", ev)
            elif msg[1] == CMD_SERIAL:
                self._serial = msg[3:].decode("ascii", "replace").strip("\0 \r\n")
                self._serial_known.set()
            elif msg[1] == CMD_FIRMWARE and len(msg) >= 6:
                self._firmware = f"{msg[3]}.{msg[4]}.{msg[5]}"

    def _notify_state(self, connected: bool) -> None:
        try:
            self._on_state(connected)
        except Exception:
            log.exception("Fehler im Zustands-Verbraucher")

    # --- Senden -------------------------------------------------------------

    def send(self, typ: int, data: bytes = b"") -> int:
        """Sendet einen Befehl, gibt die txid zurück (0 = nicht verbunden/fehlgeschlagen)."""
        if typ in FORBIDDEN_COMMANDS:
            raise ValueError(f"Befehl 0x{typ:02x} ist gesperrt (Firmware/Flash)")
        with self._write_lock:
            if self._ser is None:
                return 0
            self._txid = self._txid % 255 + 1
            try:
                self._ser.write(encode_frame(build_message(typ, self._txid, data)))
            except (serial.SerialException, OSError) as e:
                # Nach einem (Write-Timeout-)Fehler kann ein Rahmen halb geschrieben sein: der
                # Strom ist dann asynchron. Sitzung neu aufbauen, danach zeichnet der Dienst alles.
                log.info("Senden fehlgeschlagen (0x%02x): %s – verbinde neu", typ, e)
                self._reconnect.set()
                return 0
            return self._txid

    def draw(self, display: Display, rgb565: bytes, x: int = 0, y: int = 0,
             w: int | None = None, h: int | None = None) -> None:
        """Pixel (RGB565 in der Byte-Reihenfolge des Displays) schreiben und anzeigen."""
        w = display.width if w is None else w
        h = display.height if h is None else h
        if len(rgb565) != w * h * 2:
            raise ValueError(f"{len(rgb565)} Bytes passen nicht zu {w}x{h}")
        disp = ord(display.id)
        with self._write_lock:  # WRITE und DRAW nicht von anderen Befehlen trennen
            if self.send(CMD_WRITE, struct.pack(">BBHHHH", 0, disp, x, y, w, h) + rgb565):
                self.send(CMD_DRAW, bytes([0, disp]))  # nie nach fehlgeschlagenem WRITE

    def set_leds(self, colors: dict[int, tuple[int, int, int]]) -> None:
        data = b"".join(bytes([code, r, g, b]) for code, (r, g, b) in colors.items())
        self.send(CMD_LEDS, data)

    def set_brightness(self, level: int) -> None:
        self.send(CMD_BRIGHTNESS, bytes([max(0, min(10, level))]))

    def vibrate(self, pattern: int = 1) -> None:
        self.send(CMD_VIBRATE, bytes([pattern]))

    def serial_number(self, timeout: float = 0.0) -> str | None:
        """Seriennummer der aktuellen Verbindung (wartet optional bis timeout Sekunden)."""
        if timeout > 0:
            self._serial_known.wait(timeout)
        return self._serial

    def firmware_version(self, request: bool = False) -> str | None:
        """Firmware-Version der aktuellen Verbindung (``major.minor.patch``) oder ``None``.

        Mit ``request`` wird sie beim Geraet erfragt, solange sie noch unbekannt ist (nur
        lesend, Befehl 0x07); die Antwort kommt kurz danach."""
        if request and self._firmware is None:
            self.send(CMD_FIRMWARE)
        return self._firmware
