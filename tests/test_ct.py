import threading
import time

import pytest

from neondeck.device.ct import CTDevice
from neondeck.device.discovery import find_ct
from neondeck.device.layout import Display
from neondeck.device.protocol import ButtonEvent
from support.fake_ct import SERIAL, FakeCT
from support.waiting import wait_until

TIMEOUT = 15.0  # Obergrenze nur fuer den Fehlerfall (Rechner unter Last)


class Recorder:
    def __init__(self) -> None:
        self.events: list = []
        self.states: list[bool] = []
        self.got_event = threading.Event()
        self.up = threading.Event()
        self.down = threading.Event()

    def on_event(self, ev) -> None:
        self.events.append(ev)
        self.got_event.set()

    def on_state(self, connected: bool) -> None:
        self.states.append(connected)
        (self.up if connected else self.down).set()


@pytest.fixture
def fake():
    f = FakeCT()
    yield f
    f.close()


@pytest.fixture
def connected(fake):
    rec = Recorder()
    dev = CTDevice(port_finder=lambda: fake.path, on_event=rec.on_event, on_state=rec.on_state)
    dev.start()
    assert rec.up.wait(TIMEOUT)
    yield fake, dev, rec
    dev.stop()


def test_connects_and_reports_state(connected):
    _, _, rec = connected
    assert rec.states == [True]


def test_events_delivered(connected):
    fake, _, rec = connected
    fake.emit("0500000700")
    assert rec.got_event.wait(TIMEOUT)
    assert rec.events == [ButtonEvent(7, True)]


def test_stale_frames_before_header_ignored(connected):
    fake, _, rec = connected
    # FakeCT schickt vor dem 101-Kopf einen alten Tastenrahmen (Code 9); der darf nicht ankommen.
    fake.emit("0500000800")
    assert rec.got_event.wait(TIMEOUT)
    assert rec.events == [ButtonEvent(8, True)]


def test_serial_number_after_connect(connected):
    _, dev, _ = connected
    assert dev.serial_number(timeout=TIMEOUT) == SERIAL


def test_draw_sends_write_and_draw(connected):
    fake, dev, _ = connected
    dev.draw(Display.CENTER, bytes(360 * 270 * 2))
    assert fake.wait_received(lambda r: any(m[1] == 0x0F for m in r))
    msgs = [m for m in fake.received if m[1] in (0x10, 0x0F)]
    write, draw = msgs
    assert write[1] == 0x10
    assert write[3:13] == bytes.fromhex("0041000000000168010e")
    assert len(write) == 3 + 10 + 360 * 270 * 2
    assert draw[1] == 0x0F and draw[3:] == bytes.fromhex("0041")


def test_draw_rejects_wrong_pixel_count(connected):
    _, dev, _ = connected
    with pytest.raises(ValueError):
        dev.draw(Display.LEFT, bytes(10))


def test_leds_brightness_vibrate(connected):
    fake, dev, _ = connected
    dev.set_leds({7: (255, 0, 0), 8: (0, 255, 0)})
    dev.set_brightness(42)
    dev.vibrate()
    assert fake.wait_received(lambda r: any(m[1] == 0x1B for m in r))
    by_type = {m[1]: m for m in fake.received}
    assert by_type[0x02][3:] == bytes([7, 255, 0, 0, 8, 0, 255, 0])
    assert by_type[0x09][3:] == bytes([10])
    assert by_type[0x1B][3:] == bytes([1])


def test_txids_increment_and_skip_zero(connected):
    _, dev, _ = connected
    ids = [dev.send(0x09, b"\x05") for _ in range(300)]
    assert 0 not in ids
    assert all(1 <= i <= 255 for i in ids)
    assert ids[1] == ids[0] % 255 + 1


def test_forbidden_command_raises(connected):
    _, dev, _ = connected
    for cmd in (0x06, 0x17, 0x18):
        with pytest.raises(ValueError):
            dev.send(cmd)


def test_event_callback_exception_does_not_kill_connection(fake):
    rec = Recorder()

    def bad(ev):
        if ev == ButtonEvent(7, True):
            raise RuntimeError("kaputter Verbraucher")
        rec.on_event(ev)

    dev = CTDevice(port_finder=lambda: fake.path, on_event=bad, on_state=rec.on_state)
    dev.start()
    try:
        assert rec.up.wait(TIMEOUT)
        fake.emit("0500000700")
        fake.emit("0500000701")
        assert rec.got_event.wait(TIMEOUT)
        assert rec.events == [ButtonEvent(7, False)]
        assert rec.states == [True]
    finally:
        dev.stop()


def test_reconnect_after_unplug():
    first = FakeCT()
    current = {"path": first.path}
    rec = Recorder()
    dev = CTDevice(port_finder=lambda: current["path"], on_event=rec.on_event, on_state=rec.on_state)
    dev.start()
    second = None
    try:
        assert rec.up.wait(TIMEOUT)
        rec.up.clear()
        first.close()
        assert rec.down.wait(TIMEOUT)
        assert dev.send(0x09, b"\x05") == 0
        second = FakeCT()
        current["path"] = second.path
        t0 = time.monotonic()
        assert rec.up.wait(TIMEOUT)
        assert time.monotonic() - t0 < TIMEOUT
        assert rec.states == [True, False, True]
        second.emit("0500000700")
        assert rec.got_event.wait(TIMEOUT)
        assert rec.events == [ButtonEvent(7, True)]
    finally:
        dev.stop()
        if second:
            second.close()


def test_no_device_no_crash():
    rec = Recorder()
    searches = []
    dev = CTDevice(port_finder=lambda: searches.append(1), on_event=rec.on_event,
                   on_state=rec.on_state)
    dev.start()
    assert wait_until(lambda: len(searches) >= 2)  # mindestens ein erneuter Versuch lief
    assert dev.send(0x09, b"\x05") == 0
    assert dev.serial_number() is None
    dev.stop()
    assert rec.states == []


def test_stop_reports_disconnect(connected):
    _, dev, rec = connected
    dev.stop()
    assert rec.states == [True, False]


def _fake_tty(root, name, vendor, product):
    d = root / name
    (d / "device").mkdir(parents=True)
    (d / "idVendor").write_text(vendor + "\n")
    (d / "idProduct").write_text(product + "\n")


def test_find_ct_matches_vendor_and_product(tmp_path):
    _fake_tty(tmp_path, "ttyACM0", "1234", "0003")
    _fake_tty(tmp_path, "ttyACM1", "2ec2", "0004")
    _fake_tty(tmp_path, "ttyACM2", "2ec2", "0003")
    assert find_ct(sys_root=str(tmp_path)) == "/dev/ttyACM2"


def test_find_ct_none_when_absent(tmp_path):
    _fake_tty(tmp_path, "ttyACM0", "1234", "0003")
    assert find_ct(sys_root=str(tmp_path)) is None
    assert find_ct(sys_root=str(tmp_path / "fehlt")) is None


def test_port_in_use_is_not_shared(fake, caplog):
    """Ein zweiter Prozess (hier: fremde exklusive Sperre) bekommt das Geraet nicht."""
    import serial

    from neondeck.device import ct

    rec = Recorder()
    holder = serial.Serial(fake.path, exclusive=True)
    dev = CTDevice(port_finder=lambda: fake.path, on_event=rec.on_event, on_state=rec.on_state)
    try:
        with caplog.at_level("INFO", logger=ct.__name__):
            dev.start()
            assert wait_until(lambda: any("belegt" in r.getMessage() for r in caplog.records))
        assert not rec.up.is_set()
        holder.close()  # andere Instanz beendet -> Verbindung kommt von selbst
        assert rec.up.wait(TIMEOUT)
    finally:
        holder.close()
        dev.stop()


def _alive_device_threads() -> list[threading.Thread]:
    return [t for t in threading.enumerate() if t.name == "ct-device" and t.is_alive()]


def test_restart_does_not_revive_hanging_thread(monkeypatch):
    from neondeck.device import ct

    stop_timeout = ct.STOP_TIMEOUT
    monkeypatch.setattr(ct, "STOP_TIMEOUT", 0.2, raising=False)
    gate = threading.Event()
    callers: list[threading.Thread] = []
    called = threading.Event()

    def finder():
        callers.append(threading.current_thread())
        called.set()
        gate.wait(60)  # haengt, bis der Test freigibt (auch unter Last laenger als stop())
        return None

    dev = CTDevice(port_finder=finder)
    dev.start()
    try:
        assert called.wait(TIMEOUT)
        old = callers[0]
        dev.stop()  # Join laeuft ab, der alte Thread lebt noch
        assert old.is_alive()
        assert dev._thread is old
        dev.start()
        gate.set()
        old.join(TIMEOUT)
        assert not old.is_alive(), "alter Thread wurde durch start() wiederbelebt"
        assert wait_until(lambda: any(c is not old for c in callers)), "neuer Thread laeuft nicht"
        assert len(_alive_device_threads()) == 1
    finally:
        gate.set()
        # Zum Aufraeumen wieder die echte Join-Grenze: 0,2 s reichen unter Last nicht immer.
        monkeypatch.setattr(ct, "STOP_TIMEOUT", stop_timeout)
        dev.stop()
    assert _alive_device_threads() == []


def test_reconnect_closes_session_and_connects_again(connected, monkeypatch):
    """Nach dem Standby: Sitzung schliessen, der Thread verbindet sofort neu."""
    from neondeck.device import ct

    fake, dev, rec = connected
    # Wartete der Thread zwischen den Versuchen, kaeme die neue Sitzung erst nach einer
    # Stunde – also nie binnen TIMEOUT (statt einer Wanduhr-Grenze, die unter Last kippt).
    monkeypatch.setattr(ct, "RETRY_INTERVAL", 3600.0)
    rec.up.clear()
    dev.reconnect()
    assert rec.down.wait(TIMEOUT)
    assert rec.up.wait(TIMEOUT)  # ohne die Wartezeit zwischen Versuchen
    assert rec.states == [True, False, True]
    fake.emit("0500000700")  # neue Sitzung empfaengt
    assert rec.got_event.wait(TIMEOUT)
    assert dev.serial_number(timeout=TIMEOUT) == SERIAL


def test_reconnect_without_session_is_harmless(fake):
    rec = Recorder()
    dev = CTDevice(port_finder=lambda: None, on_event=rec.on_event, on_state=rec.on_state)
    dev.reconnect()  # nicht gestartet
    dev.start()
    dev.reconnect()  # kein Geraet da
    dev.stop()
    assert rec.states == []


class _TimeoutSerial:
    """Schreiben laeuft in den Write-Timeout (nur ``write`` wird gebraucht)."""

    def __init__(self):
        self.writes = 0

    def write(self, data):
        import serial
        self.writes += 1
        raise serial.SerialTimeoutException("Write timeout")


def test_write_timeout_forces_reconnect_and_skips_draw():
    """F2: nach einem Write-Timeout ist der Strom evtl. halb geschrieben – die Sitzung wird
    neu aufgebaut (dann zeichnet der Dienst alles neu), und DRAW folgt keinem
    fehlgeschlagenen WRITE."""
    rec = Recorder()
    dev = CTDevice(port_finder=lambda: None, on_event=rec.on_event, on_state=rec.on_state)
    ser = _TimeoutSerial()
    dev._ser = ser
    d = Display.LEFT
    dev.draw(d, bytes(d.width * d.height * 2))
    assert ser.writes == 1  # nur WRITE versucht, kein DRAW hinterher
    assert dev._reconnect.is_set()
