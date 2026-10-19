"""Was die Displays aus einem Profil zeigen und wie es auf das Geraet kommt (ohne Qt).

* Bild-Bausteine (``button_spec``, ``strip_label``, ``strip_image``, ``wheel_picture`` …): Die
  Engine zeichnet damit das Geraet, die Geraeteansicht des Editors dieselben Bilder (R29),
  damit der Editor genau zeigt, was das Geraet zeigt.
* ``DisplayPainter``: zeichnet die aktuelle Ansicht, sendet nur Displays mit geaendertem
  Inhalt und haelt die Bild-Caches. Den Geraete-Look (klassisch/Cockpit) bekommt er als
  Strategie (``ports.Look``), Belegungen fragt er beim ``ControlResolver`` ab.
"""
from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from functools import partial
from typing import Protocol

from PIL import Image, ImageDraw

from ..actions.base import registry
from ..actions.kde import LABELS as KDE_LABELS
from ..core.i18n import N_, tr
from ..core.sysload import SystemLoad
from ..device.layout import TOUCH_BUTTONS, ControlKind, ControlRef, Display
from ..profile.model import (
    STRIP_BAR,
    STRIP_LEFT,
    STRIP_NAME,
    STRIP_RIGHT,
    STRIP_SYSTEM,
    WHEEL_ARC,
    WHEEL_BLANK,
    WHEEL_CLOCK,
    WHEEL_IMAGE,
    Assignment,
    ButtonImage,
    Encoder,
    EncoderLayer,
    TouchPage,
)
from ..render.images import (
    FLASH_WIDTH,
    TILE,
    WHEEL_TILE,
    TileSpec,
    back_arrow,
    render_strip,
    render_tile,
    render_wheel,
    to_rgb565,
    wheel_tile,
)
from ..render.live import live_image
from ..render.palette import ERROR_HEX
from .controls import ControlResolver
from .kinds import LIVE_TYPES, STOPWATCH, action_type
from .leds import LedController, device_write, round_colors
from .navigation_state import BACK_TILE, page_dots
from .ports import EnginePorts, Look, TileSpecs, default_icon_loader
from .state import EngineState

BREADCRUMB = N_("Ordner › {name}")
# Symbol der „Zurück“-Kachel, Kachel 0 jeder Ordnerseite (fest, damit laufende Gesten sie
# wiedererkennen); der Pfeil wird gezeichnet
BACK_ICON = "builtin:back"
HIGHLIGHT = "#ffffff"     # Rand eines gedrueckten Felds
STRIP_SECTIONS = 3        # Abschnitte je Leiste


def action_label(action: dict) -> str:
    """Lesbarer Name einer Aktion (Ruecktext fuer Kacheln ohne Symbol und Text)."""
    t = action.get("type") or ""
    if t == "kde" and action.get("name") in KDE_LABELS:
        return tr(KDE_LABELS[action["name"]])
    at = registry().get(t)
    return tr(at.label) if at else t


def encoder_label(enc: Encoder | EncoderLayer) -> str:
    """Name eines Reglers (oder einer Ebene) in der Leiste: Bezeichnung, sonst Name der
    Dreh-/Drueckaktion."""
    if enc.label:
        return enc.label
    for action in (enc.rotate, enc.right, enc.left, enc.press):
        if action and action.get("type"):
            return action_label(action)
    return ""


def layer_name(index: int, layer: EncoderLayer | None) -> str:
    """Name einer Ebene: Bezeichnung, sonst Name ihrer Aktion, sonst „Ebene n“."""
    return (encoder_label(layer) if layer is not None else "") or tr("Ebene {n}", n=index + 1)


# --- Tasten -------------------------------------------------------------------------

def image_spec(img: ButtonImage, icon: Image.Image | None, text: str | None = None, *,
               value: str | None = None, flash: str | None = None,
               badge: str | None = None) -> TileSpec:
    """``TileSpec`` aus einem ``ButtonImage`` (alle Gestaltungsfelder); ``text`` ersetzt
    ``img.text``."""
    return TileSpec(img.bg, icon, img.text if text is None else text, img.text_color, value,
                    flash, badge, layout=img.layout, font=img.font, font_size=img.font_size,
                    align_h=img.align_h, align_v=img.align_v, icon_color=img.icon_color)


_UNSET = object()


def button_spec(a: Assignment, img: ButtonImage, icon: Image.Image | None, dt: datetime, *,
                live_state=None, live=_UNSET, flash: str | None = None) -> TileSpec:
    """Kachel einer Belegung mit Bild ``img`` (Grundbild oder Bild des Zustands): Anzeigen
    (Uhr, Datum, Stoppuhr) live, ohne Symbol und Text der Name der Aktion, Ordner mit
    Kennzeichen. ``live``: schon berechnetes ``live_image`` (dann nicht noch einmal)."""
    action = a.action or {}
    t = action.get("type")
    if t in LIVE_TYPES:
        if live is _UNSET:
            live = live_image(action, dt, live_state)
        if live is not None:
            return image_spec(img, None, live.text, value=live.value, flash=flash)
    text = img.text
    if not text.strip() and icon is None and t:
        text = action_label(action)
    return image_spec(img, icon, text, flash=flash, badge="folder" if t == "folder" else None)


def back_spec(icon: Image.Image, flash: str | None = None) -> TileSpec:
    """„Zurück“-Kachel im Ordner (Feld 1)."""
    img = BACK_TILE.image
    return TileSpec(img.bg, icon, tr(img.text), img.text_color, None, flash)


# --- Leisten -------------------------------------------------------------------------

def strip_label(enc: Encoder, page: TouchPage | None, index: int,
                layer_index: int = 0, notice: str | None = None) -> str:
    """Name im Leistenabschnitt ``index``: im Ordner Abschnitt 0 die Brotkrume, mit Ebenen
    die Meldung bzw. der Name der aktiven Ebene, sonst der Name des Reglers."""
    if index == 0 and page is not None and page.folder:
        return tr(BREADCRUMB, name=page.name or page.id)
    if enc.layers:
        layer = enc.layers[layer_index] if 0 <= layer_index < len(enc.layers) else None
        return notice or layer_name(layer_index, layer)
    return encoder_label(enc)


def strip_section(name: str, value: str | None, mode: str, percent: float | None = None
                  ) -> tuple[str, str | None, float | None]:
    """Name, Wert und Balken (0–100) eines Leistenabschnitts je ``Encoder.strip``:
    ``name`` ohne Wert, ``bar`` als Balken, wenn es einen Prozentwert gibt, sonst wie
    ``name_value`` (Text ``value``)."""
    if mode == STRIP_NAME:
        return name, None, None
    bar = min(100.0, max(0.0, percent)) if mode == STRIP_BAR and percent is not None else None
    return name, (value if bar is None else None), bar


def strip_image(sections: list[tuple[str, str | None, float | None]],
                flashing: tuple = (), flash_color: str = ERROR_HEX) -> Image.Image:
    """Eine Leiste (drei Abschnitte aus ``strip_section``), blinkende Abschnitte mit Rand."""
    img = render_strip([(name, value) for name, value, _ in sections],
                       [bar for _, _, bar in sections])
    draw = ImageDraw.Draw(img)
    for section, on in enumerate(flashing):
        if on:
            top = section * TILE
            draw.rectangle((0, top, img.width - 1, top + TILE - 1), outline=flash_color,
                           width=FLASH_WIDTH)
    return img


# --- Rad -------------------------------------------------------------------------------

def wheel_picture(mode: str, label: str, dt: datetime | None, *,
                  value: float | None = None, spec: TileSpec | None = None,
                  muted: bool = False) -> Image.Image:
    """Raddisplay; im Modus ``image`` das Bild aus ``spec`` im Innenquadrat."""
    image = wheel_tile(spec) if spec is not None else None
    return render_wheel(mode, label, dt, value=value, image=image, muted=muted)


# --- Geraet ------------------------------------------------------------------------------

class LookSource(Protocol):
    """Aktueller Look und seine Bildnummer (``power.LookClock``)."""
    look: Look
    frame: int


class DisplayPainter:
    """Zeichnet die aktuelle Ansicht auf das Geraet: nur Displays (und LEDs), deren Inhalt sich
    geaendert hat; gesperrt, im Display-Schlaf und im Bildschirmschoner nichts.

    ``strip_pressed(i)``: liegt ein Finger auf Leistenabschnitt ``i`` (Cockpit: leuchtet)?"""

    def __init__(self, ports: EnginePorts, state: EngineState,
                 controls: ControlResolver, looks: LookSource, sysload: SystemLoad,
                 leds: LedController, strip_pressed: Callable[[int], bool]) -> None:
        self._draw = ports.draw
        self._clock = ports.clock
        self._icon_loader = ports.icon_loader or default_icon_loader
        self._state = state
        self._controls = controls
        self._looks = looks
        self._sysload = sysload
        self._leds = leds
        self._strip_pressed = strip_pressed
        self._overrides: dict[ControlRef, str] = {}  # API image.set, bis zum Neustart
        self._icons: dict[object, Image.Image | None] = {}
        self._tiles: dict[tuple, Image.Image] = {}
        self._keys: dict[Display, object] = {}

    # --- Zustand der Caches --------------------------------------------------------------

    def forget(self) -> None:
        """Beim naechsten Zeichnen alles senden, auch Unveraendertes."""
        self._keys.clear()
        self._leds.forget()

    def reset_caches(self) -> None:
        """Geladene Symbole und Tastenbilder verwerfen (anderes Profil)."""
        self._icons.clear()
        self._tiles.clear()
        self.forget()

    def set_override(self, ref: ControlRef, path: str | None) -> None:
        """Bilddatei ``path`` statt des Tastenbilds zeigen (siehe ``Engine``); die Datei wird
        jedes Mal neu geladen, auch wenn der Pfad gleich bleibt."""
        old = self._overrides.pop(ref, None)
        if old is not None:
            self._icons.pop(old, None)
        if path:
            icon_ref = f"file:{path}"
            self._icons.pop(icon_ref, None)
            self._overrides[ref] = icon_ref
        self._tiles.clear()
        self._keys.pop(Display.CENTER, None)
        self.refresh()

    def image_override(self, ref: ControlRef) -> str | None:
        """Symbol-Ref der Ueberschreibung (``file:…``) oder ``None``."""
        return self._overrides.get(ref)

    # --- Senden --------------------------------------------------------------------------

    def send(self, display: Display, img: Image.Image) -> None:
        """Ein Bild senden; bei einem Fehler wird es beim naechsten Mal neu gesendet."""
        if not device_write(self._write, display, img,
                            what=f"Zeichnen auf {display.name} fehlgeschlagen"):
            self._keys.pop(display, None)

    def _write(self, display: Display, img: Image.Image) -> None:
        self._draw(display, to_rgb565(img, display.big_endian))

    def show_leds(self, colors: dict[int, tuple]) -> None:
        """LED-Farben direkt senden (Bildschirmschoner)."""
        self._leds.show(colors)

    def blank(self) -> None:
        """Alle Displays schwarz, LEDs aus; danach zeichnet ``refresh`` wieder alles."""
        self.forget()
        for display in Display:
            device_write(self._draw, display, bytes(display.width * display.height * 2),
                         what=f"Display {display.name} nicht geleert")
        self._leds.off()

    def _changed(self, display: Display, key: object) -> bool:
        if self._keys.get(display, object()) == key:
            return False
        self._keys[display] = key
        return True

    # --- Zeichnen ------------------------------------------------------------------------

    def refresh(self, now: float | None = None) -> None:
        """Zeichnet nur die Anzeigen, deren Inhalt sich geaendert hat (dunkel oder
        Bildschirmschoner: nichts)."""
        self.update_sampling()
        if not self._state.showing:
            return
        now = self._clock() if now is None else now
        self._state.feedback.expire(now)
        dt = datetime.fromtimestamp(now)
        self._draw_strip(Display.LEFT, 0, now)
        self._draw_center(dt)
        self._draw_strip(Display.RIGHT, STRIP_SECTIONS, now)
        self._draw_wheel(dt)
        self._send_leds()

    def update_sampling(self) -> None:
        """Systemlast nur abtasten, solange eine Leiste sie zeigt und das Geraet hell,
        verbunden und ohne Bildschirmschoner ist."""
        st = self._state
        self._sysload.set_active(st.showing and st.device_connected and (
            self._strip_system(Display.LEFT) or self._strip_system(Display.RIGHT)))

    def _icon(self, ref: str, size: int = TILE) -> Image.Image | None:
        key = ref if size == TILE else (ref, size)
        if key not in self._icons:
            self._icons[key] = self._icon_loader(ref, size)
        return self._icons[key]

    def _back_icon(self) -> Image.Image:
        if BACK_ICON not in self._icons:
            self._icons[BACK_ICON] = back_arrow(TILE)
        return self._icons[BACK_ICON]

    def tile_spec(self, index: int, dt: datetime) -> tuple[TileSpec | None, str | None]:
        """Kachel von Feld ``index`` und die Ref ihres Symbols (``None``: leeres Feld)."""
        a = self._controls.tile(index)
        ref = ControlRef(ControlKind.TOUCH, index)
        override = self._overrides.get(ref)
        if a is None and override is None:
            return None, None
        fb = self._state.feedback
        flash = ERROR_HEX if ref in fb.flashes else (
            HIGHLIGHT if index in fb.highlight else None)
        if a is BACK_TILE:  # „Zurück“ ist reserviert, auch gegen image.set
            return back_spec(self._back_icon(), flash), BACK_ICON
        if override is not None:
            return TileSpec(a.image.bg if a else "#000000", self._icon(override), "",
                            flash=flash), override
        return self._assignment_spec(a, ref, dt, flash)

    def _assignment_spec(self, a: Assignment, ref: ControlRef, dt: datetime,
                         flash: str | None) -> tuple[TileSpec, str | None]:
        img, action = a.image, a.action or {}
        state_idx = self._controls.states.current(a, self._controls.state_key(ref))
        if state_idx is not None:
            img = a.states[state_idx].image
        t = action_type(action)
        if t in LIVE_TYPES:
            state = self._controls.stopwatch(ref.index) if t == STOPWATCH else None
            live = live_image(action, dt, state)  # einmal je Kachel
            if live is not None:
                return button_spec(a, img, None, dt, live=live, flash=flash), None
        icon = self._icon(img.icon) if img.icon else None
        return button_spec(a, img, icon, dt, live=None, flash=flash), (
            img.icon if icon is not None else None)

    def _render_tiles(self, specs: TileSpecs, keys: tuple) -> list[Image.Image | None]:
        """Tastenbilder; gleiche wie beim letzten Mal kommen aus dem Cache."""
        tiles: list[Image.Image | None] = []
        cache: dict[tuple, Image.Image] = {}
        for (spec, _), key in zip(specs, keys):
            if spec is None:
                tiles.append(None)
                continue
            cache[key] = self._tiles.get(key) or render_tile(spec)
            tiles.append(cache[key])
        self._tiles = cache
        return tiles

    def _draw_center(self, dt: datetime) -> None:
        dot, dots = page_dots(self._state.workspace, self._state.page_index)  # nur normale
        if self._controls.dynamic_page() is not None:
            dot, dots = 0, 0
        specs = [self.tile_spec(i, dt) for i in range(TOUCH_BUTTONS)]
        key, paint = self._looks.look.center(specs, dot, dots, self._looks.frame,
                                             self._render_tiles)
        if self._changed(Display.CENTER, key):
            self.send(Display.CENTER, paint())

    # --- Leisten -------------------------------------------------------------------------

    def strip_label(self, index: int, now: float | None = None) -> str:
        """Name im Leistenabschnitt ``index`` (siehe ``strip_label``; Mixer: keine
        Brotkrume, Ebenen: Hinweis nach dem Wechsel)."""
        c = self._controls
        page = None if c.mixer() is not None else c.page()
        enc = c.encoder(index)
        if not enc.layers:
            return strip_label(enc, page, index)
        key = c.layer_key(index)
        notice = c.layers.notice(key, self._clock() if now is None else now)
        return strip_label(enc, page, index, c.layers.index(key, enc), notice)

    def strip_section(self, index: int, now: float) -> tuple[str, str | None, float | None]:
        """Name, Wert und Balken (0–100) eines Leistenabschnitts je ``Encoder.strip``;
        im Mixer bleibt die Lautstaerke stehen, solange kein neuer Wert da ist."""
        name = self.strip_label(index, now)
        text, percent = self._state.feedback.values.get(index, (None, None))[:2]
        dyn = self._controls.dynamic_page()
        if text is None and percent is None and dyn is not None:
            text, percent = dyn.values.get(index, (None, None))
        return strip_section(name, text, self._controls.encoder(index).strip, percent)

    def _strip_system(self, display: Display) -> bool:
        """Zeigt die Leiste ``display`` die Systemlast? Ein Mixer-Ordner (eigene Regler)
        zeigt immer seine Regler."""
        ws = self._state.workspace
        if ws is None or self._controls.mixer() is not None:
            return False
        return ws.strip_mode(STRIP_LEFT if display is Display.LEFT else STRIP_RIGHT) == STRIP_SYSTEM

    def _draw_strip(self, display: Display, first: int, now: float) -> None:
        idx = range(first, first + STRIP_SECTIONS)
        flashes = self._state.feedback.flashes
        flashing = tuple(ControlRef(ControlKind.KNOB, i) in flashes for i in idx)
        edge = "right" if display is Display.LEFT else "left"  # Kante zur Mitte
        look, frame = self._looks.look, self._looks.frame
        if self._strip_system(display):
            key, paint = look.system_strip(self._sysload.values(), flashing, frame, edge)
        else:
            sections = [self.strip_section(i, now) for i in idx]
            pressed = tuple(self._strip_pressed(i) for i in idx)
            key, paint = look.strip(sections, flashing, pressed, frame, edge)
        if self._changed(display, key):
            self.send(display, paint())

    # --- Rad und LEDs --------------------------------------------------------------------

    def _draw_wheel(self, dt: datetime) -> None:
        ws = self._state.workspace
        fb = self._state.feedback
        mode, label = (ws.wheel.display, ws.wheel.label) if ws else (WHEEL_BLANK, "")
        spec = icon_ref = value = None
        if mode == WHEEL_ARC:
            value = fb.wheel_value
        elif mode == WHEEL_IMAGE and ws.wheel.image is not None:
            img = ws.wheel.image
            icon = self._icon(img.icon, WHEEL_TILE) if img.icon else None
            spec = image_spec(img, icon)
            icon_ref = img.icon if icon is not None else None
        muted = mode == WHEEL_ARC and fb.wheel_muted
        content = (mode, label, dt.replace(microsecond=0) if mode == WHEEL_CLOCK else None, value,
                   muted, None if spec is None else spec.key(icon_ref))
        base = partial(wheel_picture, mode, label, dt, value=value, spec=spec, muted=muted)
        key, paint = self._looks.look.wheel(content, base, self._looks.frame)
        if self._changed(Display.WHEEL, key):
            self.send(Display.WHEEL, paint())

    def _send_leds(self) -> None:
        colors, active = round_colors(self._state.profile, self._state.workspace_id)
        self._leds.update(self._looks.look.leds(colors, active, self._looks.frame))
