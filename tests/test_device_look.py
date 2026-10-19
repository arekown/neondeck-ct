"""Geraete-Look „Cockpit“: Bilder, Takt (Look, Schoner, Sperre), Eingaben, Einstellungen/API."""
import numpy as np
import pytest
from PIL import Image

from neondeck.api.client import ApiError
from neondeck.core.settings import LOOK_NAMES, Settings
from neondeck.device.layout import ControlRef, Display
from neondeck.device.protocol import ButtonEvent
from neondeck.editor.windows.settings_page import SettingsPage
from neondeck.profile.model import Assignment, ButtonImage
from neondeck.render import look as looks
from neondeck.render.draw import mix as _mix
from neondeck.render.palette import C_BG, C_CYAN, C_MAGENTA
from support.engine_rig import TILE5, Rig, finger_down, finger_up
from support.fakes import Clock
from support.service import call
from support.waiting import wait_until


def _tile(color="#000000", text=""):
    """Tastenbild 90 × 90: Hintergrund ``color``, mittig ein weisser Block (Symbol/Text)."""
    img = Image.new("RGB", (90, 90), color)
    img.paste((255, 255, 255), (35, 35, 55, 55))
    return img


def _close(px, rgb, tol=8):
    return all(abs(int(a) - int(b)) <= tol for a, b in zip(px, rgb))


# --- Look-Modul ----------------------------------------------------------------------------

def test_sizes_and_resolve():
    look = looks.CockpitLook()
    center = look.center([None] * 12, 0, 3, frame=7)
    assert center.size == (360, 270) and center.mode == "RGB"
    strip = look.strip([("Lautstärke", "42 %", None)] * 3, (False,) * 3, 7, "right")
    assert strip.size == (60, 270) and strip.mode == "RGB"
    wheel = look.wheel(Image.new("RGB", (240, 240)), 7)
    assert wheel.size == (240, 240)
    assert set(LOOK_NAMES) == {"auto", *looks.LOOKS}
    assert looks.resolve("auto", "cockpit") == "cockpit"
    assert looks.resolve("auto", "neutral") == "classic"
    assert looks.resolve("gibtsnicht", "cockpit") == "classic"
    assert looks.make("classic") is None
    assert looks.is_black("#000000") and looks.is_black("black") and not looks.is_black("#010000")


def test_black_background_is_transparent_other_colors_opaque():
    look = looks.CockpitLook()
    bg = np.asarray(look.background(5))
    tiles = [None] * 12
    tiles[1] = looks.CenterTile(_tile("#000000"), transparent=True)
    tiles[2] = looks.CenterTile(_tile("#203060"), transparent=False)
    img = np.asarray(look.center(tiles, 0, 0, frame=5))
    # Feld 1 (x 90–179): schwarzer Hintergrund zeigt das Raster, der weisse Block bleibt
    assert (img[20:30, 100:110] == bg[20:30, 100:110]).all()
    assert _close(img[45, 135], (255, 255, 255))
    # Feld 2 (x 180–269): Farbe deckt, nur die Rahmenform (Ecken, Rand) zeigt das Raster
    assert _close(img[20, 200], (0x20, 0x30, 0x60))
    assert (img[1, 181] == bg[1, 181]).all() and (img[88, 268] == bg[88, 268]).all()


def test_pressed_is_magenta_error_red_empty_dimmed():
    look = looks.CockpitLook()
    tiles = [None] * 12
    tiles[0] = looks.CenterTile(_tile(), True, looks.PRESSED)
    tiles[1] = looks.CenterTile(_tile(), True, looks.FAILED)
    tiles[2] = looks.CenterTile(_tile(), True)
    img = np.asarray(look.center(tiles, 0, 0, frame=0))
    assert _close(img[20, 20], _mix(C_BG, C_MAGENTA, 0.45))      # Fuellung
    assert _close(img[45, 3], C_MAGENTA) and _close(img[45, 4], C_MAGENTA)  # Rahmen, 2 px
    assert _close(img[20, 110], _mix(C_BG, looks.ERROR, 0.45))
    assert _close(img[45, 93], looks.ERROR)
    frame_on = img[45, 183]
    frame_empty = img[45, 273]
    assert int(frame_on.max()) > int(frame_empty.max()) > max(C_BG)  # belegt heller als leer


def _magenta_share(px) -> float:
    """Anteil Magenta (0) bis Cyan (1) einer Rahmenfarbe ueber Gruen (Cyan hat viel Gruen)."""
    return (int(px[1]) - C_MAGENTA[1]) / (C_CYAN[1] - C_MAGENTA[1])


def test_v2_frames_mix_cyan_and_magenta_and_wander():
    look = looks.CockpitLook()
    tiles = [looks.CenterTile(_tile(), True) for _ in range(12)]
    a = np.asarray(look.center(tiles, 0, 0, frame=0))
    # obere Rahmenlinie aller Felder (y = 3): Verlauf mit cyan- und magentalastigen Stellen
    top = [a[3, x] for x in range(20, 340, 10) if x % 90 not in range(0, 16)]
    shares = [_magenta_share(px) for px in top]
    assert max(shares) > 0.75 and min(shares) < 0.25
    b = np.asarray(look.center(tiles, 0, 0, frame=60))           # 10 s spaeter: gewandert
    assert not (a[3, 20:340] == b[3, 20:340]).all()
    assert (a[40:50, 40:50] == 255).all() and (b[40:50, 40:50] == 255).all()  # Inhalt klar


def test_v2_ping_flashes_frame_not_content(monkeypatch):
    frame = 7 * looks.PING_EVERY                                 # Ping beginnt: volle Staerke
    field, k = next((i, k) for i, k in looks.ping_tiles(frame) if k == 1.0)
    tiles = [None] * 12
    tiles[field] = looks.CenterTile(_tile(), True)
    look = looks.CockpitLook()
    pinged = np.asarray(look.center(tiles, 0, 0, frame))
    monkeypatch.setattr(looks.timing, "ping_tiles", lambda f: [])
    calm = np.asarray(look.center(tiles, 0, 0, frame))
    x0, y0 = (field % 4) * 90, (field // 4) * 90
    assert (pinged[y0 + 35:y0 + 55, x0 + 35:x0 + 55] == calm[y0 + 35:y0 + 55, x0 + 35:x0 + 55]
            ).all()                                                # Inhalt unveraendert
    edge_p, edge_c = pinged[y0 + 45, x0 + 3], calm[y0 + 45, x0 + 3]
    assert int(edge_p[0]) >= int(edge_c[0]) and int(edge_p[1]) < int(edge_c[1]) + 1
    assert not (pinged[y0 + 3] == calm[y0 + 3]).all()             # Rahmen blitzt
    assert looks.ping_tiles(frame) == looks.ping_tiles(frame)     # nur von der Bildnummer


def test_v2_empty_fields_stream_and_background_scanlines():
    look = looks.CockpitLook()
    a = np.asarray(look.center([None] * 12, 0, 0, frame=3))
    b = np.asarray(look.center([None] * 12, 0, 0, frame=4))
    win = (slice(17, 73), slice(30, 60))                          # Datenstrom in Feld 0
    assert not (a[win] == b[win]).all()
    # der Strom bleibt im Feld: an den Stegen (x = 90, 180, 270) nur Raster/Rahmen/Funken
    bg = np.asarray(look.background(3))
    for x in (89, 90, 179, 180, 269, 270):
        col_a = a[20:70, x]
        assert (np.abs(col_a.astype(int) - bg[20:70, x]).max(axis=1) < 60).mean() > 0.9
    assert int(bg[4, 5].sum()) > int(bg[3, 5].sum())          # Scanline dunkler


def test_v2_strip_pressed_magenta_and_two_colour_chaser():
    look = looks.CockpitLook()
    sections = [("Lautstärke", "42 %", None)] * 3
    img = np.asarray(look.strip(sections, (False,) * 3, 0, "right", (True, False, False)))
    assert _close(img[20, 20], _mix(C_BG, C_MAGENTA, 0.3))      # Abschnitt 0 gedrueckt
    assert not _close(img[110, 20], _mix(C_BG, C_MAGENTA, 0.3))
    chaser = img[:, 58]
    assert any(_close(px, C_MAGENTA) for px in chaser)           # Kopf Magenta
    assert any(_close(px, _mix(C_BG, C_CYAN, 0.85)) for px in chaser)  # Schweif Cyan


def test_v2_wheel_ring_has_both_colours():
    look = looks.CockpitLook()
    img = np.asarray(look.wheel(Image.new("RGB", (240, 240)), 0))
    ring = [img[y, x] for y in range(240) for x in range(240)
            if 110 <= ((x - 119.5) ** 2 + (y - 119.5) ** 2) ** 0.5 <= 119]
    assert any(_close(px, C_MAGENTA, 20) for px in ring)
    assert any(_close(px, C_CYAN, 20) for px in ring)
    inner = img[30:210, 30:210]                                   # Inhalt (r < 108) bleibt
    assert int(inner[90, 90].sum()) == 0


def test_strip_text_stays_in_its_section():
    """Schrift nie ueber die Stege (y = 90, 180): die Zeilen um die Grenzen bleiben leer –
    bis auf das Lauflicht an der Kante zur Mitte."""
    look = looks.CockpitLook()
    long = "Sehr lange Bezeichnung mit vielen Woertern"
    sections = [(long, "123456789 %", None), (long, None, 55.0), (long, "stumm", None)]
    for edge in ("right", "left"):
        img = np.asarray(look.strip(sections, (False, True, False), 4, edge))
        inner = img[:, 3:57]
        for y in (90, 180):
            assert (inner[y - 3:y + 3] == C_BG).all()
        assert (inner[:2] == C_BG).all() and (inner[-2:] == C_BG).all()
    a = np.asarray(look.strip(sections, (False,) * 3, 0, "right"))
    b = np.asarray(look.strip(sections, (False,) * 3, looks.SLOW_EVERY, "right"))
    assert (a[:, :57] == b[:, :57]).all() and not (a[:, 58:] == b[:, 58:]).all()  # Lauflicht


def test_wheel_ring_turns_and_keeps_content():
    look = looks.CockpitLook()
    base = Image.new("RGB", (240, 240), (0, 0, 0))
    base.paste((255, 255, 255), (100, 100, 140, 140))
    a = np.asarray(look.wheel(base, 0))
    b = np.asarray(look.wheel(base, looks.SLOW_EVERY))
    assert (a[100:140, 100:140] == 255).all()        # Inhalt wie bisher
    assert not (a == b).all()                         # Ring dreht
    assert (np.asarray(look.wheel(base, 1)) == a).all()  # zwischen den Stufen: gleich


def test_led_breathes_between_60_and_100_percent():
    look = looks.CockpitLook()
    levels = {looks.CockpitLook.breath(f) for f in range(40)}
    assert min(levels) == pytest.approx(0.6) and max(levels) == pytest.approx(1.0)
    out = look.leds({7: (200, 100, 0), 8: (40, 40, 40)}, {7}, 0)
    assert out[8] == (40, 40, 40) and out[7] == tuple(round(c * look.breath(0))
                                                       for c in (200, 100, 0))


# --- Engine --------------------------------------------------------------------------------

def test_classic_stays_classic_and_has_no_clock():
    seen = []
    classic = Rig(on_animate=seen.append)
    classic.engine.redraw_all()
    assert seen == [] and not classic.engine.animating
    assert classic.engine.look_frame() is None
    cockpit = Rig(device_look="cockpit")
    cockpit.engine.device_look = "classic"
    cockpit.engine.redraw_all()
    for d in Display:
        assert (cockpit.last(d) == classic.last(d)).all()


def test_clock_follows_look_saver_lock_and_sleep():
    mono = Clock(0.0)
    seen = []
    rig = Rig(device_look="cockpit", monotonic=mono, on_animate=seen.append)
    e = rig.engine
    assert seen == [True] and e.animating
    rig.draws.clear()
    delay = e.look_frame()
    assert looks.FRAME_S / 2 <= delay <= 1
    assert rig.count(Display.CENTER) == 1
    for _ in range(looks.SLOW_EVERY * 2):
        e.look_frame()
    assert rig.count(Display.CENTER) == 1 + looks.SLOW_EVERY * 2
    assert 1 <= rig.count(Display.LEFT) <= 3    # Lauflicht seltener als die Mitte
    assert e.start_saver("matrix")
    assert seen == [True, False] and e.look_frame() is None
    mono.t += 1
    e.handle(ButtonEvent(9, True))              # beendet den Schoner
    assert not e.saver_active and seen[-1] is True
    e.lock()
    assert seen[-1] is False and e.look_frame() is None
    e.unlock()
    assert seen[-1] is True
    e.power.sleep_display()
    assert seen[-1] is False
    e.wake()
    assert seen[-1] is True
    e.device_connected = False
    rig.draws.clear()
    assert e.look_frame() > looks.FRAME_S and rig.draws == []  # getrennt: nichts senden
    e.device_connected = True
    e.device_look = "classic"
    assert seen[-1] is False and e.look_frame() is None


def test_input_during_animation_triggers_action_and_highlights_magenta():
    rig = Rig(device_look="cockpit")
    e = rig.engine
    for _ in range(4):
        e.look_frame()
    finger_down(rig)
    img = rig.last(Display.CENTER)
    x, y = TILE5[0] - 60, TILE5[1]  # Feld 5 in der Mitte
    assert _close(img[y - 45 + 4, x - 45 + 30], C_MAGENTA, tol=12)  # Rahmen oben: Magenta
    e.look_frame()                   # Takt waehrend der Beruehrung: Taste bleibt gedrueckt
    assert _close(rig.last(Display.CENTER)[y - 45 + 4, x - 45 + 30], C_MAGENTA, tol=12)
    finger_up(rig)
    assert len(rig.ex.calls) == 1
    assert not _close(rig.last(Display.CENTER)[y - 45 + 4, x - 45 + 30], C_MAGENTA, tol=12)


def test_same_frame_sends_nothing_again():
    """Eingabe ohne neues Bild der Animation: nur Geaendertes geht raus."""
    rig = Rig(device_look="cockpit")
    rig.engine.look_frame()
    rig.draws.clear()
    rig.engine.tick()
    assert rig.draws == []


def test_led_of_active_workspace_breathes():
    rig = Rig(device_look="cockpit")
    seen = set()
    for _ in range(20):
        rig.engine.look_frame()
        seen.add(rig.leds[-1][7])
    assert (255, 255, 255) in seen and any(c[0] < 170 for c in seen)
    assert {leds[8] for leds in rig.leds} == {(51, 51, 51)}  # andere Bereiche wie bisher


def test_error_flash_stays_red():
    rig = Rig(device_look="cockpit")
    rig.engine.state.feedback.flashes[ControlRef("touch", 5)] = rig.clock() + 10
    rig.engine.look_frame()
    img = rig.last(Display.CENTER)
    assert _close(img[90 + 45, 90 + 3], looks.ERROR)


# --- Einstellungen, API, Editor ------------------------------------------------------------

def test_device_look_over_api(api_service, api_client):
    app, _, _ = api_service
    s = call(api_client, "settings.put", {"device_look": "cockpit"})
    assert s["device_look"] == "cockpit" and app.engine.device_look == "cockpit"
    assert Settings.load().device_look == "cockpit"
    before = len(app.device.draws)
    assert wait_until(lambda: len(app.device.draws) >= before + 4)  # Takt laeuft ohne Eingabe
    call(api_client, "settings.put", {"device_look": "classic"})
    assert app.engine.device_look == "classic" and not app.engine.animating
    call(api_client, "settings.put", {"device_look": "auto", "theme": "neutral"})
    assert app.engine.device_look == "classic"
    call(api_client, "settings.put", {"theme": "cockpit"})
    assert app.engine.device_look == "cockpit"
    with pytest.raises(ApiError):
        call(api_client, "settings.put", {"device_look": "neon"})


def test_settings_page_offers_device_look():
    sent = []

    def request(method, params):
        if method == "settings.put":
            sent.append(params)
        return {"device_look": "classic"}

    page = SettingsPage(request)
    page.load({"device_look": "classic"})
    assert page.look_combo.currentData() == "classic" and sent == []
    page.look_combo.setCurrentIndex(page.look_combo.findData("cockpit"))
    assert sent == [{"device_look": "cockpit"}]
    page.deleteLater()


def test_tile_assignment_with_color_stays_opaque_in_engine():
    p = Rig().engine.profile
    p.workspaces[0].touch_pages[0].buttons[5] = Assignment(
        {"type": "run", "command": "x"}, ButtonImage(text="", bg="#203060"))
    rig = Rig(p, device_look="cockpit")
    rig.engine.look_frame()
    img = rig.last(Display.CENTER)
    assert _close(img[90 + 20, 90 + 45], (0x20, 0x30, 0x60))
