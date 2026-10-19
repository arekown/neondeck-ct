"""Bildschirmschoner: Varianten, Start nach Leerlauf, Beenden ohne Aktion, Dienst/API."""
from concurrent import futures

import pytest

from neondeck.api.client import ApiError
from neondeck.core.settings import SAVER_NAMES, Settings
from neondeck.device.layout import Display
from neondeck.device.protocol import ButtonEvent, TouchEvent
from neondeck.render import savers
from support.engine_rig import TILE5, Rig
from support.fakes import Clock
from support.service import call
from support.waiting import wait_until


@pytest.mark.parametrize("name", list(savers.SAVERS))
def test_saver_frames_have_device_sizes(name):
    s = savers.make(name, seed=1)
    for i in range(3):
        f = s.frame(i * 0.2)
        assert f.canvas.size == (480, 270) and f.canvas.mode == "RGB"
        assert f.wheel.size == (240, 240) and f.wheel.mode == "RGB"
        assert set(f.leds) <= set(range(7, 15))
    assert savers.resolve("auto", "neutral") == "aurora"
    assert savers.resolve("gibtsnicht", "cockpit") == "cockpit"


def test_saver_starts_when_idle_and_first_touch_only_ends_it():
    mono = Clock(0.0)
    seen = []
    rig = Rig(saver_min=2, saver_name="matrix", monotonic=mono, on_saver=seen.append)
    rig.engine.redraw_all()
    mono.t = 119
    rig.engine.tick()
    assert not rig.engine.saver_active
    mono.t = 120
    rig.engine.tick()
    assert rig.engine.saver_active and seen == [True]
    rig.draws.clear()
    assert rig.engine.saver_frame() >= 0.04
    assert {d for d, _ in rig.draws} == set(Display)
    rig.draws.clear()
    rig.engine.tick()  # waehrend des Schoners zeichnet die Engine nichts eigenes
    assert rig.draws == []
    mono.t += 1
    rig.engine.handle(TouchEvent(1, *TILE5, True))   # beendet nur
    rig.engine.handle(TouchEvent(1, *TILE5, False))
    assert not rig.engine.saver_active and seen == [True, False]
    assert rig.ex.calls == []
    assert {d for d, _ in rig.draws} == set(Display)  # normale Ansicht wieder da
    assert rig.engine.saver_frame() is None
    mono.t += 1
    rig.tap(*TILE5)
    assert len(rig.ex.calls) == 1  # danach wirkt die Taste wieder


def test_display_sleep_and_lock_beat_saver():
    mono = Clock(0.0)
    rig = Rig(saver_min=2, display_sleep_min=2, monotonic=mono)
    mono.t = 120
    rig.engine.tick()
    assert rig.engine.display_asleep and not rig.engine.saver_active
    rig.engine.handle(ButtonEvent(9, True))
    rig.engine.handle(ButtonEvent(9, False))
    assert rig.engine.start_saver("warp")
    rig.engine.lock()
    assert not rig.engine.saver_active
    assert not rig.engine.start_saver()


def test_settings_and_preview_over_api(api_service, api_client):
    app, _, _ = api_service
    s = call(api_client, "settings.put", {"screensaver_min": 7, "screensaver": "synthwave"})
    assert s["screensaver_min"] == 7 and app.engine.saver.minutes == 7
    assert app.engine.saver_name == "synthwave"
    assert Settings.load().screensaver == "synthwave"
    for bad in ({"screensaver_min": -1}, {"screensaver": "toaster"}):
        with pytest.raises(ApiError):
            call(api_client, "settings.put", bad)
    call(api_client, "settings.put", {"screensaver": "auto"})
    assert app.engine.saver_name == savers.resolve("auto", app.settings.theme)
    before = len(app.device.draws)
    assert call(api_client, "screensaver.start", {"name": "cockpit"}) == {"started": True}
    assert app.engine.saver_active
    assert wait_until(lambda: len(app.device.draws) >= before + 8)  # laeuft weiter
    app.engine.handle(ButtonEvent(9, True))
    assert not app.engine.saver_active


def test_slideshow_from_folder(tmp_path):
    from PIL import Image
    (tmp_path / "sub").mkdir()
    Image.new("RGB", (1920, 1080), (200, 30, 30)).save(tmp_path / "a.jpg")
    Image.new("RGB", (300, 900), (30, 30, 200)).save(tmp_path / "sub" / "b.png")
    (tmp_path / "kaputt.jpg").write_bytes(b"kein Bild")
    (tmp_path / "notiz.txt").write_text("x")
    files = savers.list_images(tmp_path)
    assert {f.name for f in files} == {"a.jpg", "b.png", "kaputt.jpg"}
    s = savers.make("diashow", seed=2, options={"folder": str(tmp_path), "slide_s": 3})
    try:
        seen, t = set(), 0.0
        while t < 20:
            f = s.frame(t)
            assert f.canvas.size == (480, 270) and f.wheel.size == (240, 240)
            if f.changed:
                seen.add(f.canvas.getpixel((240, 135)))
            t += 0.25
            if s._next is not None:  # Laden im Hintergrund abwarten (Test ohne Zeitdruck)
                futures.wait([s._next], timeout=2)
        assert any(r > 180 and b < 60 for r, _, b in seen)  # JPEG: rot, nicht exakt
        assert (30, 30, 200) in seen  # beide Bilder; das kaputte wird uebersprungen
    finally:
        s.close()
    empty = savers.make("diashow", options={"folder": str(tmp_path / "leer")})
    assert empty.frame(0).canvas.size == (480, 270)  # ohne Bilder: Aurora statt schwarz
    empty.close()


def test_slideshow_settings_over_api(api_service, api_client, tmp_path):
    app, _, _ = api_service
    s = call(api_client, "settings.put", {"screensaver_folder": str(tmp_path),
                                      "screensaver": "diashow", "screensaver_slide_s": 30})
    assert s["screensaver_folder"] == str(tmp_path)
    assert app.engine.saver_name == "diashow"
    assert app.engine.saver.options == {"folder": str(tmp_path), "slide_s": 30}
    for bad in ({"screensaver_folder": str(tmp_path / "gibtsnicht")},
                {"screensaver_slide_s": 1}):
        with pytest.raises(ApiError):
            call(api_client, "settings.put", bad)


def test_saver_names_match_variants():
    """``settings.SAVER_NAMES`` ist die Qt- und numpy-freie Liste der Varianten."""
    assert set(SAVER_NAMES) == {"auto", *savers.SAVERS}
