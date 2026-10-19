"""Sperre, Standby und Display-Schlaf: Sitzungswaechter (Ersatz-Bus), Engine, Dienst."""
import json
import threading
import time

import pytest
from PySide6.QtWidgets import QApplication

from neondeck.core.settings import Settings, settings_path
from neondeck.desktop.session import SessionWatcher
from neondeck.device.layout import ControlRef, Display
from neondeck.device.protocol import ButtonEvent, RotateEvent, TouchEvent
from neondeck.engine.leds import LED_OFF
from neondeck.profile.model import Assignment
from neondeck.service.app import App
from support.engine_rig import T0, TILE5, Rig, make_profile
from support.fake_dbus import FakeSignalBus
from support.fakes import Clock, FakeDevice, FakeKeyboard
from support.waiting import wait_until

pytestmark = pytest.mark.usefixtures("home")

LOGIN1 = ("/org/freedesktop/login1", "org.freedesktop.login1.Manager", "PrepareForSleep")
SCREENSAVER = ("/org/freedesktop/ScreenSaver", "org.freedesktop.ScreenSaver", "ActiveChanged")


def black(display) -> bytes:
    return bytes(display.width * display.height * 2)


def last_draws(draws) -> dict:
    return {d: data for d, data in draws}


# --- Sitzungswaechter ---------------------------------------------------------------------

def test_session_watcher_parses_signals():
    session, system = FakeSignalBus(), FakeSignalBus()
    w = SessionWatcher(bus=session, system_bus=system)
    seen = []
    w.about_to_sleep.connect(lambda: seen.append("sleep"))
    w.resumed.connect(lambda: seen.append("resume"))
    w.locked.connect(lambda on: seen.append(("locked", on)))
    assert w.start()
    assert [s[:4] for s in system.subscriptions] == [("org.freedesktop.login1", *LOGIN1)]
    assert [s[:4] for s in session.subscriptions] == [("org.freedesktop.ScreenSaver",
                                                       *SCREENSAVER)]
    system.emit(*LOGIN1, True)
    system.emit(*LOGIN1, False)
    session.emit(*SCREENSAVER, True)
    session.emit(*SCREENSAVER, False)
    assert seen == ["sleep", "resume", ("locked", True), ("locked", False)]
    w.stop()
    assert system.subscriptions == [] and session.subscriptions == []
    system.emit(*LOGIN1, True)
    assert seen[-1] == ("locked", False)  # nach stop kommt nichts mehr an
    w.stop()  # zweimal: harmlos


def test_session_watcher_start_reports_failed_subscription():
    w = SessionWatcher(bus=FakeSignalBus(ok=False), system_bus=FakeSignalBus())
    assert not w.start()  # logind laeuft weiter, Sperre nicht abonniert
    w.stop()


# --- Engine: Sperre --------------------------------------------------------------------------

def hold_profile():
    p = make_profile()
    p.square[15] = Assignment({"type": "hold_key", "keys": ["KEY_LEFTSHIFT"]})
    return p


def test_locked_ignores_input():
    rig = Rig(hold_profile())
    rig.engine.redraw_all()
    rig.engine.lock()
    assert rig.engine.locked
    for ev in (ButtonEvent(9, True), ButtonEvent(9, False), ButtonEvent(8, True),
               ButtonEvent(15, True), RotateEvent(1, 3), TouchEvent(1, *TILE5, True),
               TouchEvent(1, *TILE5, False)):
        rig.engine.handle(ev)
    assert rig.ex.calls == []
    assert rig.engine.workspace_id == "ws1"  # auch Navigation nicht
    # Displays schwarz, LEDs aus – und der Sekundentakt zeichnet nichts darueber
    assert last_draws(rig.draws) == {d: black(d) for d in Display}
    assert rig.leds[-1] == {c: LED_OFF for c in range(7, 15)}
    n_draws, n_leds = len(rig.draws), len(rig.leds)
    rig.engine.tick(T0 + 5)
    rig.engine.set_state(ControlRef("touch", 5), 1)
    assert len(rig.draws) == n_draws and len(rig.leds) == n_leds


def test_unlock_redraws_all():
    rig = Rig()
    rig.engine.redraw_all()
    rig.engine.lock()
    rig.draws.clear()
    rig.leds.clear()
    rig.engine.unlock()
    assert not rig.engine.locked
    assert {d for d, _ in rig.draws} == set(Display)
    assert last_draws(rig.draws)[Display.CENTER] != black(Display.CENTER)
    assert rig.leds and rig.leds[-1] != {c: LED_OFF for c in range(7, 15)}
    rig.engine.handle(ButtonEvent(9, True))  # Eingaben wirken wieder
    assert len(rig.ex.calls) == 1


def test_held_keys_released_on_lock():
    rig = Rig(hold_profile())
    rig.engine.handle(ButtonEvent(15, True))
    assert rig.ex.calls == [(ControlRef("square", 0), {"type": "hold_key",
                                                       "keys": ["KEY_LEFTSHIFT"]}, 0, True)]
    rig.engine.lock()
    assert rig.ex.calls[-1][0] == ControlRef("square", 0) and rig.ex.calls[-1][3] is False
    rig.engine.handle(ButtonEvent(15, False))  # Loslassen waehrend der Sperre: nichts doppelt
    rig.engine.unlock()
    assert len(rig.ex.calls) == 2


def test_redraw_while_locked_stays_black():
    """Wiederverbinden waehrend der Sperre: alles neu senden heisst schwarz senden."""
    rig = Rig()
    rig.engine.lock()
    rig.draws.clear()
    rig.leds.clear()
    rig.engine.redraw_all()
    assert last_draws(rig.draws) == {d: black(d) for d in Display}
    assert rig.leds == [{c: LED_OFF for c in range(7, 15)}]


# --- Engine: Display-Schlaf --------------------------------------------------------------------

def sleeping_rig(profile=None, minutes=5):
    """Engine mit eigener Monotonuhr (Schlafuhr), bereits im Display-Schlaf."""
    mono = Clock(0.0)
    rig = Rig(profile, display_sleep_min=minutes, monotonic=mono)
    rig.mono = mono
    rig.engine.redraw_all()
    mono.t = minutes * 60
    rig.engine.tick()
    assert rig.engine.display_asleep
    return rig


def test_display_sleep_first_input_only_wakes():
    mono = Clock(0.0)
    rig = Rig(display_sleep_min=5, monotonic=mono)
    rig.engine.redraw_all()
    mono.t = 4 * 60
    rig.engine.tick()
    assert not rig.engine.display_asleep
    rig.engine.tick(T0 + 24 * 3600)  # Sprung der Wanduhr zaehlt nicht
    assert not rig.engine.display_asleep
    mono.t = 5 * 60
    rig.engine.tick()
    assert rig.engine.display_asleep
    assert last_draws(rig.draws) == {d: black(d) for d in Display}
    assert rig.leds[-1] == {c: LED_OFF for c in range(7, 15)}
    mono.t = 6 * 60
    rig.draws.clear()
    rig.engine.handle(ButtonEvent(9, True))  # erste Eingabe: nur wecken
    rig.engine.handle(ButtonEvent(9, False))
    assert rig.ex.calls == []
    assert not rig.engine.display_asleep
    assert {d for d, _ in rig.draws} == set(Display)
    mono.t += 1
    rig.engine.handle(ButtonEvent(9, True))  # naechster Druck wirkt
    assert len(rig.ex.calls) == 1
    # Schlafuhr laeuft ab der letzten Eingabe neu
    mono.t += 4 * 60
    rig.engine.tick()
    assert not rig.engine.display_asleep


def test_wake_swallows_rotation_burst():
    """Ein Dreh-Schwung weckt nur; erst nach einer Pause dreht der Regler wieder."""
    rig = sleeping_rig()
    t = rig.mono.t
    for i in range(12):  # 12 Rastungen in 0,6 s (laenger als die Gnadenfrist)
        rig.mono.t = t + i * 0.05
        rig.engine.handle(RotateEvent(1, 1))
    assert not rig.engine.display_asleep
    assert rig.ex.calls == []
    rig.mono.t += 0.5  # Pause -> neuer Dreh wirkt
    rig.engine.handle(RotateEvent(1, 1))
    assert [c[:3] for c in rig.ex.calls] == [(ControlRef("knob", 0), {"type": "volume"}, 1)]


def test_wake_swallows_touch_gesture():
    """Finger, der weckt: wiederholtes „an“ und das Loslassen loesen nichts aus."""
    rig = sleeping_rig()
    t = rig.mono.t
    rig.engine.handle(TouchEvent(1, *TILE5, True))       # weckt
    rig.mono.t = t + 0.5
    rig.engine.handle(TouchEvent(1, *TILE5, True))       # Finger ruht, Geraet wiederholt
    rig.mono.t = t + 0.8
    rig.engine.handle(TouchEvent(1, *TILE5, False))
    assert rig.ex.calls == []
    # Leiste (= Regler-Druck) genauso
    rig.engine.power.sleep_display()
    t = rig.mono.t
    rig.engine.handle(TouchEvent(2, 30, 135, True))
    rig.mono.t = t + 0.6
    rig.engine.handle(TouchEvent(2, 30, 140, True))
    rig.engine.handle(TouchEvent(2, 30, 140, False))
    assert rig.ex.calls == []
    rig.mono.t += 1
    rig.tap(*TILE5)  # neue Beruehrung wirkt
    assert [c[0] for c in rig.ex.calls] == [ControlRef("touch", 5)]


def test_wake_swallows_button_until_release_and_grace():
    rig = sleeping_rig(hold_profile())
    t = rig.mono.t
    rig.engine.handle(ButtonEvent(15, True))   # hold_key: weckt nur
    rig.mono.t = t + 0.1
    rig.engine.handle(ButtonEvent(9, True))    # andere Taste in der Gnadenfrist
    rig.mono.t = t + 1.0
    rig.engine.handle(ButtonEvent(15, False))
    rig.engine.handle(ButtonEvent(9, False))
    assert rig.ex.calls == []
    rig.mono.t = t + 2.0
    rig.engine.handle(ButtonEvent(9, True))
    assert [c[0] for c in rig.ex.calls] == [ControlRef("round", 2)]


def test_display_sleep_off_by_default():
    rig = Rig(monotonic=Clock(10 ** 6))
    rig.engine.tick()
    assert not rig.engine.display_asleep


def test_unlock_wakes_sleeping_display():
    rig = sleeping_rig(minutes=1)
    rig.engine.lock()
    rig.mono.t += 60
    rig.draws.clear()
    rig.engine.unlock()
    assert not rig.engine.display_asleep and not rig.engine.locked
    assert {d for d, _ in rig.draws} == set(Display)
    rig.mono.t += 30  # Uhr ab dem Entsperren
    rig.engine.tick()
    assert not rig.engine.display_asleep


def test_dark_changes_reported_once():
    seen = []
    rig = sleeping_rig()
    rig.engine.hooks.on_dark = seen.append
    rig.engine.lock()                 # schon dunkel: keine Meldung
    rig.engine.unlock()               # hell
    rig.engine.lock()
    rig.engine.power.sleep_display()        # gesperrt bleibt gesperrt
    rig.engine.unlock()
    assert seen == [False, True, False]


# --- Dienst ------------------------------------------------------------------------------------

@pytest.fixture
def service():
    app = App(device_factory=FakeDevice, keyboard=FakeKeyboard())
    dev = app.device
    dev.on_state(True)
    assert wait_until(lambda: {d for d, _ in dev.draws} == set(Display))
    yield app, dev, app.session._system_bus, app.session._bus
    app.quit()


def test_resume_triggers_reconnect_and_full_redraw(service):
    """Review Focus 5: nach dem Aufwachen binnen 3 s Helligkeit, LEDs, alle Displays."""
    app, dev, system, _ = service
    system.emit(*LOGIN1, True)
    QApplication.processEvents()
    dev.draws.clear()
    dev.leds.clear()
    dev.brightness.clear()
    start = time.monotonic()
    system.emit(*LOGIN1, False)
    assert wait_until(lambda: {d for d, _ in dev.draws} == set(Display) and dev.leds
                      and dev.brightness)
    # Anforderung (keine Testbequemlichkeit): gemessen ~0,08 s, auch unter Volllast
    assert time.monotonic() - start < 3.0
    assert dev.reconnects == 1
    assert dev.brightness == [8]
    assert app.tray.status_text() == "verbunden"


def test_screen_lock_blanks_and_survives_reconnect(service):
    app, dev, system, session = service
    app.engine.set_profile(make_profile())  # Feld 5 „Firefox“: Mitte nicht schwarz
    session.emit(*SCREENSAVER, True)
    assert wait_until(lambda: app.engine.locked)
    assert last_draws(dev.draws) == {d: black(d) for d in Display}
    dev.draws.clear()
    # Standby waehrend der Sperre: nach dem Aufwachen bleibt alles schwarz
    system.emit(*LOGIN1, False)
    assert wait_until(lambda: set(last_draws(dev.draws)) == set(Display))
    assert last_draws(dev.draws) == {d: black(d) for d in Display}
    assert app.engine.locked
    dev.draws.clear()
    session.emit(*SCREENSAVER, False)
    assert wait_until(lambda: not app.engine.locked)
    assert {d for d, _ in dev.draws} == set(Display)
    assert last_draws(dev.draws)[Display.CENTER] != black(Display.CENTER)


def test_lock_with_session_off_keeps_device_on(service):
    app, dev, _, session = service
    app.settings_controller.apply({"lock_with_session": False})
    assert Settings.load().lock_with_session is False
    session.emit(*SCREENSAVER, True)
    QApplication.processEvents()
    assert not app.engine.locked


def test_display_sleep_menu_and_setting(service):
    app, _, _, _ = service
    menu = app.tray.menu
    sub = next(a for a in menu.actions() if a.text() == "Display-Schlaf").menu()
    assert [a.text() for a in sub.actions()] == ["Aus", "5 min", "10 min", "30 min"]
    assert [a.text() for a in sub.actions() if a.isChecked()] == ["Aus"]
    next(a for a in sub.actions() if a.text() == "10 min").trigger()
    assert app.engine.power.display_sleep_min == 10
    assert Settings.load().display_sleep_min == 10
    assert [a.text() for a in sub.actions() if a.isChecked()] == ["10 min"]


def test_settings_new_fields_defaults_and_validation():
    s = Settings.load()
    assert s.display_sleep_min == 0 and s.lock_with_session is True
    path = settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"display_sleep_min": 15, "lock_with_session": False}))
    s = Settings.load()
    assert s.display_sleep_min == 15 and s.lock_with_session is False
    for bad in (-1, True, "5", 1.5):
        path.write_text(json.dumps({"display_sleep_min": bad, "lock_with_session": "ja"}))
        s = Settings.load()
        assert s.display_sleep_min == 0 and s.lock_with_session is True


# --- Dienst: Helligkeit 0 im Dunkeln (R21), Wiederverbinden, Aufwachen --------------------------

def test_brightness_zero_while_locked_and_restored(service):
    app, dev, _, session = service
    session.emit(*SCREENSAVER, True)
    assert app.engine.locked and dev.brightness[-1] == 0
    session.emit(*SCREENSAVER, False)
    assert not app.engine.locked and dev.brightness[-1] == 8


def test_brightness_zero_while_asleep_and_restored_by_input(service):
    app, dev, _, _ = service
    app.engine.power.sleep_display()
    assert dev.brightness[-1] == 0
    dev.on_event(ButtonEvent(9, True))
    assert wait_until(lambda: not app.engine.display_asleep)
    assert dev.brightness[-1] == 8


def test_brightness_change_while_dark_only_stored(service):
    app, dev, _, session = service
    session.emit(*SCREENSAVER, True)
    sent = list(dev.brightness)
    levels = next(a for a in app.tray.menu.actions() if a.text() == "Helligkeit").menu()
    next(a for a in levels.actions() if a.text() == "4").trigger()
    assert dev.brightness == sent  # nichts gesendet, Displays bleiben aus
    assert Settings.load().brightness == 4
    assert [a.text() for a in levels.actions() if a.isChecked()] == ["4"]
    session.emit(*SCREENSAVER, False)
    assert dev.brightness[-1] == 4


def test_reconnect_while_locked_stays_dark(service):
    """Gesperrt: Wiederverbinden sendet Helligkeit 0 und schwarz (auch wenn das Display
    vorher schon schlief)."""
    app, dev, _, _ = service
    app.engine.power.sleep_display()
    app.engine.lock()
    dev.draws.clear()
    dev.leds.clear()
    dev.brightness.clear()
    in_thread(dev.on_state, False)
    in_thread(dev.on_state, True)
    assert wait_until(lambda: app.tray.status_text() == "verbunden" and dev.brightness)
    QApplication.processEvents()
    assert dev.brightness == [0]
    assert last_draws(dev.draws) == {d: black(d) for d in Display}
    assert dev.leds[-1] == {c: LED_OFF for c in range(7, 15)}
    assert app.engine.dark


def test_plug_in_while_display_asleep_wakes(service):
    """F5: Anstecken ist eine bewusste Handlung – im Display-Schlaf weckt es (Helligkeit
    und Bild), statt bis zur ersten Beruehrung schwarz zu bleiben."""
    app, dev, _, _ = service
    app.engine.set_profile(make_profile())
    app.engine.power.sleep_display()
    dev.draws.clear()
    dev.brightness.clear()
    in_thread(dev.on_state, False)
    in_thread(dev.on_state, True)
    assert wait_until(lambda: app.tray.status_text() == "verbunden" and dev.brightness)
    QApplication.processEvents()
    assert dev.brightness == [8]
    assert not app.engine.dark
    assert set(last_draws(dev.draws)) == set(Display)
    assert last_draws(dev.draws)[Display.CENTER] != black(Display.CENTER)


# --- Verbindungsmeldungen nach dem Aufwachen (I-1) -------------------------------------------

def _connection_rig(app, monkeypatch):
    """Meldungen mitschreiben; verzoegerte Rueckrufe sammeln statt per Timer ausfuehren."""
    shown, later = [], []
    app.tray.icon.showMessage = lambda title, text, *a: shown.append(text)
    monkeypatch.setattr(app.device_link, "call_later", lambda delay, fn: later.append((delay, fn)))
    return shown, later


def _run_quiet_timers(later):
    from neondeck.service.device_link import RESUME_QUIET_S
    due = [fn for delay, fn in later if delay == RESUME_QUIET_S]
    later.clear()
    for fn in due:
        fn()
    return len(due)


def test_resume_reconnect_shows_no_connection_messages(service, monkeypatch):
    """Nach dem Standby trennt ``reconnect`` absichtlich und verbindet binnen Sekunden neu:
    weder „getrennt“ noch „wieder verbunden“ – auch nicht nach Ablauf der Frist."""
    app, dev, system, _ = service
    shown, later = _connection_rig(app, monkeypatch)
    before = app.device_link.connection
    system.emit(*LOGIN1, False)
    assert wait_until(lambda: app.device_link.connection == before + 2)
    assert app.tray.status_text() == "verbunden"
    assert _run_quiet_timers(later) == 1
    assert shown == []


def test_resume_without_device_reports_lost_after_grace(service, monkeypatch):
    """Kommt das Geraet nach dem Aufwachen nicht wieder, meldet die Frist „getrennt“; das
    spaetere Anstecken dann „wieder verbunden“."""
    from neondeck.service.device_link import DEVICE_BACK, DEVICE_LOST

    app, dev, system, _ = service
    shown, later = _connection_rig(app, monkeypatch)
    monkeypatch.setattr(dev, "reconnect", lambda: in_thread(dev.on_state, False))
    system.emit(*LOGIN1, False)
    assert wait_until(lambda: app.tray.status_text() == "getrennt")
    assert shown == []
    assert _run_quiet_timers(later) == 1
    assert shown == [DEVICE_LOST]
    in_thread(dev.on_state, True)
    assert wait_until(lambda: app.tray.status_text() == "verbunden")
    assert shown == [DEVICE_LOST, DEVICE_BACK]


def test_plain_unplug_reports_at_once(service, monkeypatch):
    """Ohne Aufwachen bleibt alles wie gehabt: Abstecken meldet sofort, Anstecken danach."""
    from neondeck.service.device_link import DEVICE_BACK, DEVICE_LOST

    app, dev, _, _ = service
    shown, later = _connection_rig(app, monkeypatch)
    in_thread(dev.on_state, False)
    assert wait_until(lambda: shown == [DEVICE_LOST])
    in_thread(dev.on_state, True)
    assert wait_until(lambda: shown == [DEVICE_LOST, DEVICE_BACK])
    assert _run_quiet_timers(later) == 0


def test_resume_while_asleep_reconnects_before_drawing(service):
    app, dev, system, _ = service
    app.engine.set_profile(make_profile())
    app.engine.power.sleep_display()
    dev.draws.clear()
    dev.brightness.clear()
    system.emit(*LOGIN1, False)
    # synchron: erst neu verbinden, nichts an die (vielleicht haengende) alte Sitzung
    assert dev.reconnects == 1 and dev.at_reconnect == (0, 0)
    assert dev.draws == [] and dev.brightness == []
    assert not app.engine.display_asleep
    assert wait_until(lambda: dev.brightness == [8]
                    and last_draws(dev.draws).get(Display.CENTER, black(Display.CENTER))
                    != black(Display.CENTER))
    assert set(last_draws(dev.draws)) == set(Display)


def test_display_sleep_off_wakes(service):
    app, dev, _, _ = service
    app.settings_controller.apply({"display_sleep_min": 5})
    app.engine.power.sleep_display()
    app.settings_controller.apply({"display_sleep_min": 10})
    assert app.engine.display_asleep  # anderer Wert: schlaeft weiter
    dev.draws.clear()
    app.settings_controller.apply({"display_sleep_min": 0})
    assert not app.engine.display_asleep
    assert {d for d, _ in dev.draws} == set(Display) and dev.brightness[-1] == 8


def in_thread(fn, *args):
    t = threading.Thread(target=fn, args=args)
    t.start()
    t.join()
