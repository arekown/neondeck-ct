"""Themes des Editors: Farben, Schriften und Effekte an einer Stelle.

``apply`` (``ThemeManager``) setzt QPalette, Schrift und Stylesheet auf die **QApplication** (nie auf einzelne
Widgets) und meldet das neue Theme ueber ``notifier.changed``; die selbstgezeichnete
Geraeteansicht liest Farben und Effekte aus ``current()``.

Stylesheets liegen in ``themes/<name>.qss``. Platzhalter: ``{schluessel}`` (Farbe aus
``palette``), ``{schluessel@20}`` (dieselbe Farbe mit 20 % ihrer Deckkraft),
``{font_ui}``, ``{font_head}``, ``{font_mono}``, ``{font_pt}`` und
``{icon:<form>:<schluessel>}`` (Pfad eines kleinen SVG-Symbols in dieser Farbe; Formen in
``ICON_SHAPES``). Farben stehen als ``#rrggbb`` bzw. ``#aarrggbb`` (Qt-Schreibweise) in
``palette``.
"""
from __future__ import annotations

import logging
import re
import tempfile
from dataclasses import dataclass, replace
from pathlib import Path

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QColor, QFont, QFontDatabase, QPalette
from PySide6.QtWidgets import QApplication

from ..core.i18n import N_
from ..core.paths import fonts_dir

log = logging.getLogger(__name__)

DEFAULT = "cockpit"
SYSTEM = "system"
QSS_DIR = Path(__file__).with_name("themes")
BASE_STYLE = "fusion"  # einheitliche Grundlage unter dem Stylesheet (Breeze zeichnet eigenwillig)


@dataclass(frozen=True)
class Theme:
    name: str
    label: str
    palette: dict[str, str]
    font_ui: str
    font_head: str
    font_mono: str
    corner: int          # Eckenmass in Geraete-Einheiten (abgeschraegt bzw. Radius)
    cut_corners: bool
    glow: bool
    grid: bool
    supports_scanlines: bool  # das Theme kann Scanlines (im Menue waehlbar)
    scanlines: bool = False   # Scanlines sind eingeschaltet (nur in current() je True)
    font_pt: float = 10.0

    def color(self, key: str, alpha: float = 1.0) -> QColor:
        """Farbe ``key``; ``alpha`` skaliert ihre Deckkraft."""
        c = QColor(self.palette[key])
        c.setAlphaF(c.alphaF() * alpha)
        return c

    def solid(self, key: str) -> QColor:
        """Farbe ``key`` deckend, auf den Hintergrund ``bg`` gerechnet."""
        return _over(self.color(key), self.color("bg"))


def _over(top: QColor, bottom: QColor) -> QColor:
    a = top.alphaF()
    return QColor.fromRgbF(top.redF() * a + bottom.redF() * (1 - a),
                           top.greenF() * a + bottom.greenF() * (1 - a),
                           top.blueF() * a + bottom.blueF() * (1 - a))


COCKPIT = Theme(
    name="cockpit", label=N_("Cyberpunk Cockpit"),
    palette={
        "bg": "#06080f", "bg2": "#0a0e1a",
        "panel": "#9e0a101c",       # rgba(10,16,28,.62)
        "line": "#4705d9e8",        # rgba(5,217,232,.28)
        "text": "#cfeef2", "text_dim": "#5f7d86",
        "accent": "#05d9e8", "accent_dim": "#0792a0",
        "accent2": "#ff2a6d", "accent2_dim": "#b81e4f",
        "ok": "#00ff9f", "warn": "#f9f002", "danger": "#ff003c",
        "bright": "#ffffff",
    },
    font_ui="Rajdhani", font_head="Orbitron", font_mono="Share Tech Mono",
    corner=12, cut_corners=True, glow=True, grid=True, supports_scanlines=True, font_pt=11.5)

NEUTRAL = Theme(
    name="neutral", label=N_("Neutral Dunkel"),
    palette={
        "bg": "#16181d", "bg2": "#1e2128", "panel": "#262a33",
        "line": "#353a46",
        "text": "#e6e8ee", "text_dim": "#9aa3b2",
        "accent": "#4f8cff", "accent_dim": "#3a68c0",
        "accent2": "#4f8cff", "accent2_dim": "#3a68c0",
        "ok": "#3ecf8e", "warn": "#e8b04a", "danger": "#f2555a",
        "bright": "#ffffff",
    },
    font_ui="Inter", font_head="Inter", font_mono="Share Tech Mono",
    corner=8, cut_corners=False, glow=False, grid=False, supports_scanlines=False,
    font_pt=10.0)

# Platzhalterwerte (Breeze Dunkel); ``apply`` liefert die echte Systempalette in current().
SYSTEM_THEME = Theme(
    name=SYSTEM, label=N_("System (KDE)"),
    palette={
        "bg": "#202326", "bg2": "#141618", "panel": "#292c30", "line": "#4d4d4d",
        "text": "#fcfcfc", "text_dim": "#a1a9b1",
        "accent": "#3daee9", "accent_dim": "#2980b9",
        "accent2": "#3daee9", "accent2_dim": "#2980b9",
        "ok": "#27ae60", "warn": "#f67400", "danger": "#da4453", "bright": "#ffffff",
    },
    font_ui="Noto Sans", font_head="Noto Sans", font_mono="Noto Sans Mono",
    corner=6, cut_corners=False, glow=False, grid=False, supports_scanlines=False)

THEMES: dict[str, Theme] = {t.name: t for t in (COCKPIT, NEUTRAL, SYSTEM_THEME)}


# --- Stylesheet und Palette -------------------------------------------------------------

_PLACEHOLDER = re.compile(r"\{(?:icon:(\w+):(\w+)|(\w+)(?:@(\d{1,3}))?)\}")
_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)


def _hex(c: QColor) -> str:
    fmt = QColor.NameFormat.HexRgb if c.alpha() == 255 else QColor.NameFormat.HexArgb
    return c.name(fmt)


# Symbole fuer Unterelemente, die Qt im Stylesheet nur als Bild kennt (viewBox 0 0 10 10)
ICON_SHAPES = {
    "arrow_down": '<path d="M1.5 3.5 L8.5 3.5 L5 7.5 Z" fill="{c}"/>',
    "arrow_up": '<path d="M1.5 6.5 L8.5 6.5 L5 2.5 Z" fill="{c}"/>',
    "check": '<path d="M1.8 5.3 L4.2 7.6 L8.4 2.6" fill="none" stroke="{c}" '
             'stroke-width="1.6" stroke-linecap="square"/>',
}


class _IconFiles:
    """SVG-Symbole fuer das Stylesheet in einem Temp-Ordner, der bis Programmende lebt."""

    def __init__(self) -> None:
        self._dir: tempfile.TemporaryDirectory | None = None

    def path(self, shape: str, color: QColor) -> Path:
        """SVG-Symbol ``shape`` in ``color`` (einmal je Form und Farbe geschrieben)."""
        if self._dir is None:
            self._dir = tempfile.TemporaryDirectory(prefix="neondeck-ct-theme-")
        name = f"{shape}-{color.name(QColor.NameFormat.HexArgb)[1:]}.svg"
        path = Path(self._dir.name) / name
        if not path.is_file():
            body = ICON_SHAPES[shape].replace("{c}", color.name()).replace(
                "/>", f' opacity="{color.alphaF():.3f}"/>')
            path.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10" '
                            f'viewBox="0 0 10 10">{body}</svg>', encoding="utf-8")
        return path


icon_path = _IconFiles().path


def render_qss(theme: Theme, template: str) -> str:
    """Platzhalter ersetzen; unbekannte Schluessel sind ein Fehler im Stylesheet."""
    values = {"font_ui": theme.font_ui, "font_head": theme.font_head,
              "font_mono": theme.font_mono, "font_pt": f"{theme.font_pt:g}"}

    def sub(m: re.Match) -> str:
        shape, icon_key, key, pct = m.groups()
        if shape is not None:
            if shape not in ICON_SHAPES or icon_key not in theme.palette:
                raise KeyError(f"Unbekanntes Symbol {m.group(0)} im Stylesheet {theme.name}")
            return icon_path(shape, theme.color(icon_key)).as_posix()
        if key in values and pct is None:
            return values[key]
        if key in theme.palette:
            return _hex(theme.color(key, 1.0 if pct is None else int(pct) / 100))
        raise KeyError(f"Unbekannter Platzhalter {{{key}}} im Stylesheet {theme.name}")

    return _PLACEHOLDER.sub(sub, _COMMENT.sub("", template))


def stylesheet(theme: Theme) -> str:
    return render_qss(theme, (QSS_DIR / f"{theme.name}.qss").read_text(encoding="utf-8"))


def qpalette(theme: Theme) -> QPalette:
    """QPalette fuer alles, was das Stylesheet nicht selbst zeichnet."""
    R = QPalette.ColorRole
    bg, bg2, panel = theme.solid("bg"), theme.solid("bg2"), theme.solid("panel")
    line, text, dim = theme.solid("line"), theme.solid("text"), theme.solid("text_dim")
    colors = {
        R.Window: bg, R.WindowText: text, R.Base: bg2, R.AlternateBase: panel,
        R.ToolTipBase: bg2, R.ToolTipText: text, R.PlaceholderText: dim, R.Text: text,
        R.Button: panel, R.ButtonText: text, R.BrightText: theme.solid("bright"),
        R.Light: panel.lighter(150), R.Midlight: panel.lighter(120), R.Mid: line,
        R.Dark: bg2.darker(130), R.Shadow: QColor(0, 0, 0),
        R.Highlight: theme.solid("accent2_dim"), R.HighlightedText: theme.solid("bright"),
        R.Link: theme.solid("accent"), R.LinkVisited: theme.solid("accent_dim"),
        R.Accent: theme.solid("accent2"),
    }
    pal = QPalette()
    for role, color in colors.items():
        pal.setColor(role, color)
    G = QPalette.ColorGroup.Disabled
    for role in (R.WindowText, R.Text, R.ButtonText):
        pal.setColor(G, role, dim)
    pal.setColor(G, R.Highlight, line)
    return pal


def _system_palette_values(pal: QPalette) -> dict[str, str]:
    R = QPalette.ColorRole

    def h(role) -> str:
        return pal.color(role).name()

    return {"bg": h(R.Window), "bg2": h(R.Base), "panel": h(R.Button), "line": h(R.Mid),
            "text": h(R.WindowText), "text_dim": h(R.PlaceholderText),
            "accent": h(R.Highlight), "accent_dim": pal.color(R.Highlight).darker(130).name(),
            "accent2": h(R.Highlight),
            "accent2_dim": pal.color(R.Highlight).darker(130).name(),
            "ok": SYSTEM_THEME.palette["ok"], "warn": SYSTEM_THEME.palette["warn"],
            "danger": SYSTEM_THEME.palette["danger"], "bright": h(R.BrightText)}


def _register_fonts() -> list[str]:
    """Mitgelieferte Schriften (``data/fonts/*/*.ttf``) anmelden; Familiennamen."""
    folder = fonts_dir()
    families: list[str] = []
    for path in sorted(folder.glob("*/*.ttf")):
        fid = QFontDatabase.addApplicationFont(str(path))
        if fid < 0:
            log.warning("Schrift %s nicht ladbar", path)
            continue
        for family in QFontDatabase.applicationFontFamilies(fid):
            if family not in families:
                families.append(family)
    if not families:
        log.warning("Keine Theme-Schriften in %s – tools/fetch_fonts.py ausführen", folder)
    return families


class ThemeManager(QObject):
    """Aktives Theme der Anwendung: ``apply`` legt es auf die QApplication und meldet es ueber
    ``changed``; merkt sich Schrift und Stil des Systems (vor dem ersten ``apply``) und die
    angemeldeten Schriften."""

    changed = Signal(object)  # Theme

    def __init__(self) -> None:
        super().__init__()
        self._current: Theme = SYSTEM_THEME
        self._system: tuple[QFont, str] | None = None
        self._families: list[str] | None = None

    def current(self) -> Theme:
        return self._current

    def load_fonts(self) -> list[str]:
        """Mitgelieferte Schriften einmalig anmelden; Familiennamen."""
        if self._families is None:
            self._families = _register_fonts()
        return list(self._families)

    def apply(self, app: QApplication, name: str, *, scanlines: bool = False) -> Theme:
        """Theme ``name`` auf die Anwendung legen (live); unbekannte Namen -> Standard-Theme."""
        base = THEMES.get(name)
        if base is None:
            log.warning("Theme %r unbekannt – %s", name, DEFAULT)
            base = THEMES[DEFAULT]
        if self._system is None:
            self._system = (QFont(app.font()), app.style().name())
        if base.name == SYSTEM:
            theme = self._apply_system(app, base)
        else:
            theme = self._apply_styled(app, base, scanlines)
        self._current = theme
        self.changed.emit(theme)
        return theme

    def _apply_system(self, app: QApplication, base: Theme) -> Theme:
        font, style = self._system
        app.setStyleSheet("")
        if app.style().name().lower() != style.lower():
            app.setStyle(style)
        app.setPalette(QPalette())  # leere Palette = wieder die des Systems
        app.setFont(font)
        return replace(base, palette=_system_palette_values(app.palette()),
                       font_ui=font.family(), font_head=font.family(), scanlines=False)

    def _apply_styled(self, app: QApplication, base: Theme, scanlines: bool) -> Theme:
        self.load_fonts()
        qss = stylesheet(base)  # vor allen Aenderungen: Fehler im Stylesheet aendern nichts
        if app.style().name().lower() != BASE_STYLE:
            app.setStyle(BASE_STYLE)
        app.setPalette(qpalette(base))
        ui = QFont(base.font_ui)
        ui.setPointSizeF(base.font_pt)
        app.setFont(ui)
        app.setStyleSheet(qss)
        return replace(base, scanlines=base.supports_scanlines and scanlines)


# Eine Instanz je Prozess; die Modulfunktionen sind ihre duenne Fassade.
manager = ThemeManager()
notifier = manager  # ``notifier.changed``: neues Theme
current = manager.current
apply = manager.apply
load_fonts = manager.load_fonts
