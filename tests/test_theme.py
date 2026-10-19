"""Themes (offscreen): Werte, QPalette/QSS auf der QApplication, Schriften, Umschalten."""
import json
import re

import pytest
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QFont, QFontDatabase, QFontMetricsF
from PySide6.QtWidgets import QApplication, QWidget

from neondeck.core.settings import DEFAULT_THEME, THEME_NAMES, Settings, settings_path
from neondeck.editor.widgets.action_form import ActionForm
from neondeck.editor.widgets.device_geometry import (
    button_label_area,
    round_rect,
    square_rect,
)
from neondeck.editor.widgets.device_paint import fonts
from neondeck.editor.widgets.device_view import DeviceView
from neondeck.editor.widgets.label_fit import MIN_LABEL_PX, fit_label
from neondeck.editor.windows.config_window import ConfigWindow
from neondeck.profile.model import Profile
from neondeck.profile.store import ProfileStore
from neondeck.ui import theme
from support.engine_rig import make_engine

pytestmark = pytest.mark.usefixtures("home")

KEYS = {"bg", "bg2", "panel", "line", "text", "text_dim", "accent", "accent2", "ok", "warn",
        "danger"}
HEX = re.compile(r"^#(?:[0-9a-f]{6}|[0-9a-f]{8})$")


def app():
    return QApplication.instance()


def test_themes_complete():
    assert set(theme.THEMES) == {"cockpit", "neutral", "system"}
    for name, t in theme.THEMES.items():
        assert t.name == name
        assert t.label
        assert set(t.palette) >= KEYS, name
        for key, value in t.palette.items():
            assert HEX.match(value), (name, key, value)
        for family in (t.font_ui, t.font_head, t.font_mono):
            assert isinstance(family, str) and family
        assert t.corner >= 0


def test_theme_names_match_settings():
    """Dienst und Einstellungen pruefen Qt-frei gegen ``settings.THEME_NAMES``."""
    assert tuple(theme.THEMES) == THEME_NAMES
    assert theme.DEFAULT == DEFAULT_THEME


def test_cockpit_values():
    c = theme.THEMES["cockpit"]
    assert c.palette["bg"] == "#06080f"
    assert c.palette["bg2"] == "#0a0e1a"
    assert c.palette["accent"] == "#05d9e8"
    assert c.palette["accent2"] == "#ff2a6d"
    assert c.palette["ok"] == "#00ff9f"
    assert c.palette["warn"] == "#f9f002"
    assert c.palette["danger"] == "#ff003c"
    assert c.palette["text"] == "#cfeef2"
    assert c.palette["text_dim"] == "#5f7d86"
    assert c.palette["panel"] == "#9e0a101c"  # rgba(10,16,28,.62)
    assert c.palette["line"] == "#4705d9e8"   # rgba(5,217,232,.28)
    assert (c.font_head, c.font_ui, c.font_mono) == ("Orbitron", "Rajdhani", "Share Tech Mono")
    assert c.cut_corners and c.glow and c.grid and c.supports_scanlines
    assert not c.scanlines  # eingeschaltet wird erst ueber apply(..., scanlines=True)
    assert 8 <= c.corner <= 16


def test_neutral_values():
    n = theme.THEMES["neutral"]
    assert (n.palette["bg"], n.palette["bg2"], n.palette["panel"]) == (
        "#16181d", "#1e2128", "#262a33")
    assert n.palette["accent"] == "#4f8cff"
    assert (n.palette["text"], n.palette["text_dim"]) == ("#e6e8ee", "#9aa3b2")
    assert (n.palette["ok"], n.palette["danger"]) == ("#3ecf8e", "#f2555a")
    assert n.font_ui == n.font_head == "Inter"
    assert n.corner == 8
    assert not (n.cut_corners or n.glow or n.grid or n.supports_scanlines or n.scanlines)


def test_apply_sets_palette_and_qss():
    t = theme.apply(app(), "cockpit")
    assert t is theme.current()
    assert t.name == "cockpit"
    assert app().palette().window().color().name() == "#06080f"
    qss = app().styleSheet()
    assert qss
    assert not re.search(r"\{\s*[\w@]+\s*\}", qss), "unersetzte Platzhalter"
    assert "#ff2a6d" in qss.lower() or "255, 42, 109" in qss
    theme.apply(app(), "neutral")
    assert app().palette().window().color().name() == "#16181d"
    assert "Inter" in app().styleSheet()


def test_system_theme_no_stylesheet():
    before = app().palette().window().color().name()
    font = app().font().family()
    theme.apply(app(), "cockpit")
    t = theme.apply(app(), "system")
    assert t.name == "system"
    assert app().styleSheet() == ""
    assert app().palette().window().color().name() == before
    assert app().font().family() == font


def test_unknown_theme_falls_back_to_cockpit():
    assert theme.apply(app(), "gibtsnicht").name == "cockpit"


def test_scanlines_only_when_switched_on():
    assert not theme.apply(app(), "cockpit").scanlines
    on = theme.apply(app(), "cockpit", scanlines=True)
    assert on.scanlines and on.supports_scanlines
    assert not theme.apply(app(), "neutral", scanlines=True).scanlines  # kann es nicht


def test_fonts_load():
    families = theme.load_fonts()
    for family in ("Orbitron", "Rajdhani", "Share Tech Mono", "Inter"):
        assert family in families
        assert family in QFontDatabase.families()
    assert theme.load_fonts() == families  # einmalig, zweiter Aufruf aendert nichts


def test_font_files_have_license():
    for folder in theme.fonts_dir().iterdir():
        assert (folder / "OFL.txt").is_file(), folder
        assert list(folder.glob("*.ttf")), folder


def test_theme_switch_repaints_device_view(monkeypatch):
    view = DeviceView(icon_loader=lambda ref: None)
    calls = []
    monkeypatch.setattr(view, "update", lambda *a: calls.append(a))
    theme.apply(app(), "neutral")
    assert calls
    calls.clear()
    theme.notifier.changed.emit(theme.THEMES["cockpit"])
    assert calls
    view.deleteLater()


@pytest.mark.parametrize("name", ["cockpit", "neutral", "system"])
def test_device_view_paints_each_theme(name):
    theme.apply(app(), name, scanlines=True)
    view = DeviceView(icon_loader=lambda ref: None)
    view.resize(740, 650)
    img = view.grab().toImage()
    assert not img.isNull()
    if name == "cockpit":  # Rasterhintergrund: Ecke ist Theme-Hintergrund, nicht leer
        assert img.pixelColor(2, 2).alpha() == 255
    view.deleteLater()


# --- Einstellungen und Menue ----------------------------------------------------------

def test_settings_theme_defaults_and_roundtrip():
    s = Settings.load()
    assert s.theme == "cockpit"
    assert s.theme_scanlines is False
    s.theme, s.theme_scanlines = "neutral", True
    s.save()
    loaded = Settings.load()
    assert (loaded.theme, loaded.theme_scanlines) == ("neutral", True)


def test_settings_theme_bad_values_use_defaults():
    settings_path().parent.mkdir(parents=True, exist_ok=True)
    settings_path().write_text(json.dumps({"theme": 3, "theme_scanlines": "ja"}),
                               encoding="utf-8")
    s = Settings.load()
    assert (s.theme, s.theme_scanlines) == ("cockpit", False)


@pytest.fixture
def win(home):
    store = ProfileStore(home / "config" / "profiles")
    profile = Profile.empty()
    store.save(profile)
    engine = make_engine(profile)
    chosen = []
    w = ConfigWindow(store, engine, lambda pid: None,
                     on_theme=lambda name, scan: chosen.append((name, scan)))
    w.chosen = chosen
    yield w
    w.close()
    w.deleteLater()


def test_theme_menu_switches_live_and_reports(win):
    theme.apply(app(), "cockpit")
    actions = {a.data(): a for a in win.theme_menu.theme_actions.actions()}
    assert set(actions) == {"cockpit", "neutral", "system"}
    actions["neutral"].trigger()
    assert theme.current().name == "neutral"
    assert app().palette().window().color().name() == "#16181d"
    assert win.chosen[-1] == ("neutral", False)
    assert not win.theme_menu.scanlines_action.isEnabled()  # Neutral hat keine Scanlines
    actions["cockpit"].trigger()
    assert win.theme_menu.scanlines_action.isEnabled()
    win.theme_menu.scanlines_action.trigger()
    assert theme.current().scanlines
    assert win.chosen[-1] == ("cockpit", True)
    # Fenster und Kinder bekommen nie ein eigenes Stylesheet
    assert win.styleSheet() == ""
    assert [w for w in win.findChildren(QWidget) if w.styleSheet()] == []


def test_theme_menu_shows_current_theme(win):
    theme.apply(app(), "neutral")
    checked = [a.data() for a in win.theme_menu.theme_actions.actions() if a.isChecked()]
    assert checked == ["neutral"]


# --- Beschriftungen am Geraetebild passen in ihre Felder --------------------------------

def _fits(font: QFont, area: QRectF, shown: str) -> bool:
    fm = QFontMetricsF(font)
    lines = shown.split("\n")
    height = fm.height() + (len(lines) - 1) * fm.lineSpacing()
    return (all(fm.horizontalAdvance(line) <= area.width() for line in lines)
            and height <= area.height())


@pytest.mark.parametrize("name", ["cockpit", "neutral", "system"])
def test_device_labels_fit_their_boxes(name):
    theme.apply(app(), name)
    view = DeviceView(icon_loader=lambda ref: None)
    label_font, _ = fonts(theme.current(), view.font())
    square = button_label_area(square_rect(0), False)
    under_round = button_label_area(round_rect(0), True)
    for text, area, wrap in (("Übersicht", square, True), ("Key: (Arrow Down)", square, True),
                             ("Arbeitsbereich", under_round, False)):
        font, shown = fit_label(label_font, area, text, wrap)
        assert "…" not in shown, (name, text, shown)
        assert shown.split() == text.split(), (name, text, shown)  # nichts verloren
        assert _fits(font, area, shown), (name, text, shown, font.pixelSize())
        assert font.pixelSize() >= MIN_LABEL_PX
    view.deleteLater()


def test_fit_label_keeps_theme_size_when_room():
    font = QFont("Rajdhani")
    font.setPixelSize(13)
    fitted, shown = fit_label(font, QRectF(0, 0, 200, 40), "Kurz", True)
    assert (fitted.pixelSize(), shown) == (13, "Kurz")


def test_fit_label_elides_at_minimum_size_inside_box():
    font = QFont("Inter")
    font.setPixelSize(12)
    area = QRectF(0, 0, 50, 50)
    text = "Ein sehr langer Beschriftungstext mit Donaudampfschifffahrtsgesellschaft und mehr"
    fitted, shown = fit_label(font, area, text, True)
    assert fitted.pixelSize() == MIN_LABEL_PX
    assert "…" in shown
    assert _fits(fitted, area, shown)
    fitted, shown = fit_label(font, QRectF(0, 0, 80, 16), "Arbeitsbereich mit Überlänge", False)
    assert "\n" not in shown and _fits(fitted, QRectF(0, 0, 80, 16), shown)


# --- Kategorie-Ueberschriften im Aktionsfeld folgen dem Theme ---------------------------

def _headers(form: ActionForm) -> list:
    model = form.type_combo.model()
    items = [model.item(i) for i in range(form.type_combo.count())]
    return [it for it in items if it.flags() == Qt.ItemFlag.NoItemFlags]


def test_action_combo_headers_follow_theme():
    theme.apply(app(), "cockpit")
    form = ActionForm()
    form.show()
    QApplication.processEvents()
    theme.apply(app(), "neutral")
    QApplication.processEvents()
    combo_font = form.type_combo.font()
    headers = _headers(form)
    assert headers
    for item in headers:
        font = item.font()
        assert font.bold()
        assert font.family() == combo_font.family() == "Inter"
        assert font.pointSizeF() == combo_font.pointSizeF()
    form.close()
    form.deleteLater()
