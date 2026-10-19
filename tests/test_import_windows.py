import base64
import json
import shutil
from pathlib import Path

import pytest

from neondeck.profile.defaults import ensure_default
from neondeck.profile.importers import windows as import_windows
from neondeck.profile.importers.windows import convert
from neondeck.profile.model import Profile
from neondeck.profile.store import ProfileStore

DATA = Path(__file__).parent / "data"
PROFILE_FILE = DATA / "synthetic-profile" / "ProfileInfo.json"
ICT_DIR = DATA / "synthetic-profile" / "ActionIcons"

DAILY = "A7ABDB9E5FC052B4824617C834BA8F2A"
APPS = "814902E62EDE5CD48B36EF8A062F6C7A"


def _info() -> dict:
    with open(PROFILE_FILE, encoding="utf-8-sig") as f:
        return json.load(f)


@pytest.fixture
def converted(tmp_path, monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda name: f"/usr/bin/{name}")
    return convert(_info(), ICT_DIR, icon_out_dir=tmp_path / "icons")


def _ws(profile: Profile, id: str):
    return next(w for w in profile.workspaces if w.id == id)


def _all_actions(profile: Profile) -> list[dict]:
    out = [a.action for a in list(profile.round.values()) + list(profile.square.values()) if a]
    for ws in profile.workspaces:
        for page in ws.touch_pages:
            out += [b.action for b in page.buttons if b]
        for e in ws.encoders:
            out += [x for x in (e.rotate, e.press) if x]
        if ws.wheel.rotate:
            out.append(ws.wheel.rotate)
    return out


def test_workspaces(converted):
    p, _ = converted
    assert [w.name for w in p.workspaces] == ["Alpha Workspace", "Beta Workspace"]
    assert [w.id for w in p.workspaces] == [DAILY, APPS]
    assert p.home_workspace == DAILY


def test_round_buttons_switch_workspace(converted):
    p, _ = converted
    assert p.round[7].action == {"type": "workspace", "id": DAILY}
    assert p.round[8].action == {"type": "workspace", "id": APPS}
    assert all(p.round[c] is None for c in range(9, 15))


def test_daily_use_first_page(converted):
    p, _ = converted
    page = _ws(p, DAILY).touch_pages[0]
    assert page.name == "Page One"
    b = [x.action if x else None for x in page.buttons]
    assert b[0] == {"type": "clock"}
    assert b[3] == {"type": "kde", "name": "lock"}
    assert b[4] == {"type": "stopwatch"}
    assert b[5] == {"type": "date", "format": "week"}
    assert b[6] == {"type": "date", "format": "date"}
    assert b[7] == {"type": "kde", "name": "desktop_add"}
    assert b[8] == {"type": "kde", "name": "files"}
    assert b[9] == {"type": "kde", "name": "search"}
    assert b[10] == {"type": "kde", "name": "emoji"}
    assert b[11] == {"type": "kde", "name": "screenshot"}


def test_encoders(converted):
    p, _ = converted
    enc = _ws(p, DAILY).encoders
    assert enc[0].rotate == {"type": "volume"}
    assert enc[0].press == {"type": "mute_toggle"}
    assert enc[1].press == {"type": "media", "key": "play_pause"}
    assert enc[1].rotate == {"type": "adjust_macro",
                             "left": [{"type": "media", "key": "previous"}],
                             "right": [{"type": "media", "key": "next"}],
                             "reset": []}
    assert enc[2].rotate == {"type": "adjust_macro",
                             "left": [{"type": "hotkey", "keys": "KEY_UP"}],
                             "right": [{"type": "hotkey", "keys": "KEY_DOWN"}],
                             "reset": []}
    assert enc[2].press == {"type": "hotkey", "keys": "KEY_PAGEDOWN"}
    assert enc[3].rotate is None and enc[3].press is None
    assert enc[4].rotate == {"type": "brightness"}
    assert enc[4].press == {"type": "brightness_reset"}
    assert enc[5].rotate == {"type": "kde_adjust", "left": "desktop_previous",
                             "right": "desktop_next"}
    assert enc[5].press == {"type": "kde", "name": "desktop_remove"}
    assert enc[1].label == "Media Track Control"


def test_urls_open(converted):
    p, _ = converted
    actions = [b.action for b in _ws(p, APPS).touch_pages[0].buttons if b]
    assert {"type": "open", "target": "https://video.example.org/"} in actions
    assert {"type": "open", "target": "https://social.example.org"} in actions


def test_applications_page(converted):
    p, _ = converted
    page = _ws(p, APPS).touch_pages[0]
    assert page.name == "Page Two"
    b = [x.action if x else None for x in page.buttons]
    assert b[0] == {"type": "command", "command": "", "terminal": True}
    assert b[1] == {"type": "command", "command": "ip -c a", "terminal": True, "hold": True}
    assert b[8] == {"type": "run", "command": "firefox"}
    assert b[9] == {"type": "run", "command": "google-chrome"}
    assert b[10] == {"type": "open_config"}
    assert b[11] is None


def test_dynamic_folders_converted(converted):
    """Mixer und Fenster-Umschalter (Windows: dynamische Ordner) sind umgesetzt (P10)."""
    p, messages = converted
    text = "\n".join(messages)
    assert "VolumeMixerOutput" not in text and "TaskSwitcher" not in text
    assert [a for a in _all_actions(p) if a["type"] == "unsupported"] == []
    b = _ws(p, DAILY).touch_pages[0].buttons
    assert b[1].action == {"type": "dynamic_folder", "kind": "mixer"}
    assert b[2].action == {"type": "dynamic_folder", "kind": "windows"}


def test_wheel_clock(converted):
    p, _ = converted
    wheel = _ws(p, DAILY).wheel
    assert wheel.display == "clock"
    assert wheel.rotate["type"] == "adjust_macro"
    assert wheel.rotate["left"] == [{"type": "hotkey", "keys": "KEY_UP"}]


def test_square_buttons(converted):
    p, messages = converted
    assert p.square[21].action == {"type": "hotkey", "keys": "KEY_UP"}
    assert p.square[22].action == {"type": "hotkey", "keys": "KEY_LEFT"}
    assert p.square[23] is None
    assert p.square[24].action == {"type": "hotkey", "keys": "KEY_DOWN"}
    assert p.square[25].action == {"type": "hotkey", "keys": "KEY_RIGHT"}
    assert p.square[26].action == {"type": "kde", "name": "overview"}
    assert all(p.square[c] is None for c in range(15, 21))
    # Fn-Ebene gibt es im eigenen Modell nicht -> gemeldet
    assert any("Fn-Belegung" in m and "CCB94EE3" in m for m in messages)


def test_missing_program_hint(tmp_path, monkeypatch):
    monkeypatch.setattr(shutil, "which",
                        lambda name: None if name == "google-chrome" else f"/usr/bin/{name}")
    _, messages = convert(_info(), ICT_DIR, icon_out_dir=tmp_path)
    hints = [m for m in messages if "google-chrome" in m]
    assert len(hints) == 1
    assert "nicht installiert" in hints[0]


def test_ict_image(converted):
    p, _ = converted
    img = _ws(p, DAILY).touch_pages[0].buttons[3].image
    assert img.bg == "#000000"
    assert img.text == "Lock Screen"
    assert img.text_color == "#ffffff"
    assert img.icon.startswith("file:")
    svg = Path(img.icon[5:])
    assert svg.suffix == ".svg" and svg.is_file()
    assert "<svg" in svg.read_text(encoding="utf-8")


def test_ict_icon_recolored_with_image_color(tmp_path):
    svg = '<svg xmlns="http://www.w3.org/2000/svg"><path fill="#222425" stroke="#111111"/>' \
          '<rect fill="none" style="fill:#222425;stroke:#010203"/></svg>'
    ict = {"backgroundColor": 0xFF102030, "items": [
        {"itemType": "Image", "isVisible": True, "imageColor": 0xFFFFFFFF,
         "imageFileName": None, "image": base64.b64encode(svg.encode()).decode()},
        {"itemType": "Text", "isVisible": False, "text": "Versteckt", "textColor": 0xFFFFFFFF},
        {"itemType": "Text", "isVisible": True, "text": "Sichtbar", "textColor": 0xFFFF0000},
    ]}
    ict_dir = tmp_path / "ict"
    ict_dir.mkdir()
    (ict_dir / "$DefaultWin___LockWorkstation.ict").write_text(json.dumps(ict), encoding="utf-8")
    info = _minimal_info("$DefaultWin___LockWorkstation")
    p, _ = convert(info, ict_dir, icon_out_dir=tmp_path / "out")
    img = p.workspaces[0].touch_pages[0].buttons[0].image
    assert img.bg == "#102030"
    assert img.text == "Sichtbar"
    assert img.text_color == "#ff0000"
    out = Path(img.icon[5:]).read_text(encoding="utf-8")
    assert "#222425" not in out and "#111111" not in out and "#010203" not in out
    assert 'fill="#ffffff"' in out and 'fill="none"' in out and "fill:#ffffff" in out


def test_action_image_png_preferred(tmp_path):
    images = tmp_path / "ActionImages"
    images.mkdir()
    png = images / "$@generic___@Macro___2BDEB3C6FC725C4C851C0450B91EED60.png"
    png.write_bytes(b"\x89PNG\r\n\x1a\n")
    p, _ = convert(_info(), ICT_DIR, icon_out_dir=tmp_path / "icons", images_dir=images)
    yt = next(b for b in _ws(p, APPS).touch_pages[0].buttons
              if b and b.action == {"type": "open", "target": "https://video.example.org/"})
    assert yt.image.icon == f"file:{png.resolve()}"


def test_fallback_text_from_macro_name(converted):
    p, _ = converted
    page = _ws(p, APPS).touch_pages[0]
    assert page.buttons[0].image.text == "Console Alpha"
    assert page.buttons[1].image.text == "Net\nInfo"


def test_no_ict_dir(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/x")
    p, _ = convert(_info(), None)
    assert p.round[7].action == {"type": "workspace", "id": DAILY}


def test_json_roundtrip(converted):
    p, _ = converted
    q = Profile.from_json(json.loads(json.dumps(p.to_json())))
    assert q == p


def test_keyboard_combo_mapping():
    m = import_windows.keyboard_combo
    assert m("ControlOrCommand+Shift+KeyZ___67830795___Ctrl+Shift+Z___win-90") == \
        "KEY_LEFTCTRL+KEY_LEFTSHIFT+KEY_Y"
    assert m("Windows+Shift+ArrowLeft___1___x___") == "KEY_LEFTMETA+KEY_LEFTSHIFT+KEY_LEFT"
    assert m("Home___67830795___Home___") == "KEY_HOME"
    assert m("Return___67830795___Return___") == "KEY_ENTER"
    assert m("Digit1___1___1___") == "KEY_1"
    assert m("Frobnicate___1___x___") is None


def _minimal_info(action: str) -> dict:
    return {"layout": {"layoutModes": [{
        "touchPages": [{"name": "P1", "displayName": "Seite", "controls": [
            {"pressAction": action}]}],
        "encoderPages": [], "wheelPages": [],
        "workspaces": [{"name": "W1", "displayName": "WS", "touchPageNames": ["P1"],
                        "encoderPageNames": [], "wheelPageNames": []}],
        "homeWorkspaceName": "W1"}]}}


def _assets(tmp_path: Path) -> Path:
    assets = tmp_path / "assets"
    src = assets / "defaults" / "DefaultProfile20"
    src.mkdir(parents=True)
    shutil.copy(PROFILE_FILE, src / "ProfileInfo.json")
    shutil.copytree(ICT_DIR, src / "ActionIcons")
    return assets


def test_ensure_default_creates(tmp_path):
    assets = _assets(tmp_path)
    store = ProfileStore(tmp_path / "profiles")
    p = ensure_default(store, assets)
    assert p.id == "default" and p.name == "Standard (CT)"
    assert (tmp_path / "profiles" / "default.json").is_file()
    assert store.load("default") == p
    icons = assets / "defaults" / "DefaultProfile20" / "linux-icons"
    assert any(icons.glob("*.svg"))
    lock = _ws(p, DAILY).touch_pages[0].buttons[3].image.icon
    assert lock.startswith(f"file:{icons.resolve()}/")


def test_ensure_default_keeps_existing(tmp_path):
    assets = _assets(tmp_path)
    store = ProfileStore(tmp_path / "profiles")
    p = ensure_default(store, assets)
    p.name = "Geändert"
    store.save(p)
    assert ensure_default(store, assets).name == "Geändert"


def test_ensure_default_without_assets(tmp_path):
    store = ProfileStore(tmp_path / "profiles")
    p = ensure_default(store, tmp_path / "leer")
    assert p.id == "default"
    assert not (tmp_path / "profiles" / "default.json").exists()


def test_foreign_plugin_action_is_unsupported():
    """Plugin-Aktionen ohne Linux-Gegenstueck werden gemeldet, nicht uebernommen."""
    action = "$SomePlugin___DoThing___x"
    p, messages = convert(_minimal_info(action), None)
    assert p.workspaces[0].touch_pages[0].buttons[0].action == {"type": "unsupported",
                                                                "original": action}
    assert any(action in m and "nicht umsetzbar" in m for m in messages)


# --- Import --------------------------------------------------------------------------

def test_import_firefox_flatpak(monkeypatch):
    monkeypatch.setattr(shutil, "which",
                        lambda name: None if name == "firefox" else f"/usr/bin/{name}")
    asked = []

    def flatpak(app_id):
        asked.append(app_id)
        return True

    p, messages = convert(_info(), ICT_DIR, flatpak_installed=flatpak)
    page = _ws(p, APPS).touch_pages[0]
    assert page.buttons[8].action == {"type": "run", "command": "flatpak run org.mozilla.firefox"}
    assert asked == ["org.mozilla.firefox"]
    assert not any("firefox" in m for m in messages)
    p, messages = convert(_info(), ICT_DIR, flatpak_installed=lambda app_id: False)
    assert _ws(p, APPS).touch_pages[0].buttons[8].action == {"type": "run", "command": "firefox"}
    assert any("firefox" in m and "nicht installiert" in m for m in messages)
