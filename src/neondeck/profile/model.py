"""Profilmodell (JSON-Format siehe Spec, Abschnitt Profilformat).

Das Format steht nur hier: jedes Feld traegt seine Beschreibung (``schema.prop``), daraus
entstehen ``to_json``, ``from_json`` und ``validate_profile_json`` (siehe ``schema``).
"""
from __future__ import annotations

import dataclasses
import logging
from dataclasses import dataclass

from ..core.errors import ProfileFormatError
from ..core.i18n import tr
from ..device.layout import ENCODERS, ROUND_CODES, SQUARE_KEY_CODES, TOUCH_BUTTONS
from .schema import (
    PROFILE_ID_RE,
    Action,
    Color,
    Factor,
    Flag,
    Issues,
    Items,
    Keyed,
    Part,
    Record,
    Sticky,
    Strings,
    Text,
    Whole,
    check,
    prop,
    validate,
)

FORMAT_VERSION = 2
# Anzeige einer Seitenleiste (``Workspace.strip_left``/``strip_right``): Regler-Abschnitte
# wie bisher oder Live-Balken der Systemlast (CPU, RAM, GPU 1, GPU 2)
STRIP_KNOBS, STRIP_SYSTEM = "knobs", "system"
STRIP_MODES = (STRIP_KNOBS, STRIP_SYSTEM)
STRIP_LEFT, STRIP_RIGHT = "left", "right"  # Seite einer Leiste (``Workspace.strip_mode``)
# Wertemengen der Auswahlfelder (Zeichnen und Editor benutzen sie). Unbekannte Werte
# (handbearbeitet, neuere Version) laden, bleiben beim Speichern erhalten und sind gueltig;
# das Zeichnen nimmt dafuer den Standard, der Editor zeigt sie als eigenen Eintrag (P12).
LAYOUTS = ("auto", "icon", "icon_text", "text", "big_text")  # ``ButtonImage.layout``
ALIGN_H = ("left", "center", "right")
ALIGN_V = ("top", "center", "bottom")
STRIP_NAME, STRIP_NAME_VALUE, STRIP_BAR = "name", "name_value", "bar"
ENCODER_STRIPS = (STRIP_NAME, STRIP_NAME_VALUE, STRIP_BAR)  # ``Encoder.strip``
WHEEL_CLOCK, WHEEL_LABEL, WHEEL_ARC, WHEEL_IMAGE, WHEEL_BLANK = (
    "clock", "label", "arc", "image", "blank")
# ``Wheel.display``
WHEEL_DISPLAYS = (WHEEL_CLOCK, WHEEL_LABEL, WHEEL_ARC, WHEEL_IMAGE, WHEEL_BLANK)

log = logging.getLogger(__name__)


@dataclass
class ButtonImage(Record):
    bg: str = prop(Color(), "#000000")
    icon: str | None = prop(Text(nullable=True), None)
    text: str = prop(Text(), "")
    text_color: str = prop(Color(), "#ffffff")
    layout: str = prop(Text(), "auto")
    font: str | None = prop(Text(nullable=True), None)
    font_size: int | None = prop(Whole(), None)
    align_h: str = prop(Text(), "center")
    align_v: str = prop(Text(), "center")
    icon_color: str | None = prop(Color(nullable=True), None)


@dataclass
class StateDef(Record):
    image: ButtonImage = prop(Part(ButtonImage), factory=ButtonImage)
    action: dict | None = prop(Action(), None)


@dataclass
class Assignment(Record):
    action: dict = prop(Action(required=True))
    image: ButtonImage = prop(Part(ButtonImage), factory=ButtonImage)
    double: dict | None = prop(Action(), None)
    hold: dict | None = prop(Action(), None)
    states: list[StateDef] = prop(Items(StateDef), factory=list)
    # {"type": "manual"|"mute"|"mic_mute"|"media"|"app_running"|"external", ...}
    state_source: dict | None = prop(Action(), None)

    @classmethod
    def from_json(cls, d: dict | None) -> Assignment | None:
        return None if d is None else super().from_json(d)


@dataclass
class EncoderLayer(Record):
    rotate: dict | None = prop(Action(), None)
    left: dict | None = prop(Action(), None)
    right: dict | None = prop(Action(), None)
    press: dict | None = prop(Action(), None)
    label: str = prop(Text(), "")


@dataclass
class Encoder(Record):
    rotate: dict | None = prop(Action(), None)
    press: dict | None = prop(Action(), None)
    label: str = prop(Text(), "")
    left: dict | None = prop(Action(), None)
    right: dict | None = prop(Action(), None)
    invert: bool = prop(Flag(), False)
    factor: int = prop(Factor(), 1)
    layers: list[EncoderLayer] = prop(Items(EncoderLayer), factory=list)
    strip: str = prop(Text(), "name_value")
    tap: dict | None = prop(Action(), None)  # Tippen auf den Leistenabschnitt (None = wie Regler-Druck)


@dataclass
class Wheel(Record):
    rotate: dict | None = prop(Action(), None)
    display: str = prop(Text(), WHEEL_CLOCK)
    label: str = prop(Text(), "")
    left: dict | None = prop(Action(), None)
    right: dict | None = prop(Action(), None)
    invert: bool = prop(Flag(), False)
    factor: int = prop(Factor(), 1)
    tap: dict | None = prop(Action(), None)
    image: ButtonImage | None = prop(Part(ButtonImage, nullable=True), None)


@dataclass
class TouchPage(Record):
    id: str = prop(Text(empty="p1"))
    name: str = prop(Text())
    buttons: list[Assignment | None] = prop(
        Items(Assignment, size=TOUCH_BUTTONS, null_items=True),
        factory=lambda: [None] * TOUCH_BUTTONS)
    folder: bool = prop(Flag(), False)
    parent: str | None = prop(Text(nullable=True), None)


def _new_encoders() -> list[Encoder]:
    return [Encoder() for _ in range(ENCODERS)]


@dataclass
class Workspace(Record):
    id: str = prop(Text(empty="ws1"))
    name: str = prop(Text())
    touch_pages: list[TouchPage] = prop(Items(TouchPage), factory=list)
    encoders: list[Encoder] = prop(Items(Encoder, size=ENCODERS, null_items=True),
                                   factory=_new_encoders)
    wheel: Wheel = prop(Part(Wheel), factory=Wheel)
    led_color: str | None = prop(Color(nullable=True), None)
    sticky: dict[int, Assignment] = prop(Sticky(Assignment, range(TOUCH_BUTTONS)), factory=dict)
    # Anzeige der Leiste (STRIP_MODES); unbekannt/fehlend -> Reglerabschnitte (alte Profile)
    strip_left: str = prop(Text(choices=STRIP_MODES, coerce=True), STRIP_KNOBS)
    strip_right: str = prop(Text(choices=STRIP_MODES, coerce=True), STRIP_KNOBS)

    def strip_mode(self, side: str) -> str:
        """Anzeige der Leiste ``side`` (``STRIP_LEFT``/``STRIP_RIGHT``)."""
        return self.strip_left if side == STRIP_LEFT else self.strip_right


@dataclass
class Profile(Record):
    version: int = prop(Whole(), FORMAT_VERSION, kw_only=True)
    id: str = prop(Text(empty="default"))
    name: str = prop(Text())
    app: str | None = prop(Text(nullable=True), None)
    app_ids: list[str] = prop(Strings(), factory=list)
    dynamic: bool = prop(Flag(), True)
    hold_profile: bool = prop(Flag(), False)
    round: dict[int, Assignment | None] = prop(Keyed(Assignment, ROUND_CODES),
                                               factory=lambda: dict.fromkeys(ROUND_CODES))
    square: dict[int, Assignment | None] = prop(Keyed(Assignment, SQUARE_KEY_CODES),
                                                factory=lambda: dict.fromkeys(SQUARE_KEY_CODES))
    workspaces: list[Workspace] = prop(Items(Workspace), factory=list)
    home_workspace: str = prop(Text(nullable=True), "")

    @classmethod
    def empty(cls, id: str = "default", name: str | None = None) -> Profile:
        return empty_profile(id, name)

    def replace_with(self, other: Profile) -> None:
        """Inhalt von ``other`` uebernehmen; das Objekt bleibt dasselbe (Engine, Fenster und
        Rueckgaengig halten es fest). ``other`` wird danach nicht weiter benutzt (die Listen
        und Tabellen gehen ueber)."""
        for f in dataclasses.fields(other):
            setattr(self, f.name, getattr(other, f.name))

    @classmethod
    def from_json(cls, d: dict) -> Profile:
        """Profil aus JSON; ``ProfileFormatError``, wenn das Format nicht stimmt."""
        if not isinstance(d, dict):
            raise ProfileFormatError(tr("Profil muss ein JSON-Objekt sein"))
        try:
            return cls._from_dict(d)
        except (TypeError, ValueError, AttributeError, KeyError) as e:
            raise ProfileFormatError(
                tr("Profil ungültig ({kind}: {e})", kind=type(e).__name__, e=e)) from e

    @classmethod
    def _from_dict(cls, d: dict) -> Profile:
        if (d.get("version") or 0) > FORMAT_VERSION:
            log.warning("Profil '%s' hat Format-Version %s (neuer als %s); unbekannte Felder "
                        "gehen beim Speichern verloren", d.get("id"), d.get("version"),
                        FORMAT_VERSION)
        p = super().from_json(d)
        p.version = FORMAT_VERSION
        if not p.app_ids and p.app:
            p.app_ids = [p.app]
        if not p.home_workspace:
            p.home_workspace = p.workspaces[0].id if p.workspaces else ""
        return p


def empty_profile(id: str = "default", name: str | None = None) -> Profile:
    ws = Workspace("ws1", tr("Allgemein"), [TouchPage("p1", tr("Seite {n}", n=1))])
    return Profile(id=id, name=name or tr("Standard"), workspaces=[ws], home_workspace="ws1")


# --- Strukturpruefung (Profile von aussen, z. B. ueber die API) ---------------------------
#
# ``from_json`` ist nachsichtig (alte und handbearbeitete Dateien laden). Fuer Profile, die
# gespeichert und sofort angezeigt werden sollen, prueft ``validate_profile_json`` vorher jeden
# Wert, den Engine und Zeichnen benutzen: Fehlende Felder sind erlaubt (Standardwerte),
# vorhandene muessen den Typ haben. Was ``from_json`` liefert, besteht die Pruefung immer.

_PARTS = {"assignment": Assignment, "encoder": Encoder, "wheel": Wheel, "page": TouchPage}


def validate_part(kind: str, d) -> list[str]:
    """Fehler eines Profilteils (``assignment``, ``encoder``, ``wheel``, ``page``), z. B. aus
    der Zwischenablage des Editors; leer = in Ordnung."""
    return validate(_PARTS[kind], d, kind)


def validate_profile_json(d) -> list[str]:
    """Fehler in einem Profil-JSON (deutsch, mit Pfad); leer = in Ordnung."""
    if not isinstance(d, dict):
        return [tr("Profil muss ein JSON-Objekt sein")]
    c = Issues()
    check(Profile, d, "profil", c)
    _check_required(c, d)
    return c.errors


def _check_required(c: Issues, d: dict) -> None:
    """Was ``Profile.from_json`` verzeiht, ein gespeichertes Profil aber braucht."""
    if "id" not in d:
        c.fail("profil", tr("„id“ fehlt"))
    elif isinstance(d["id"], str) and not PROFILE_ID_RE.fullmatch(d["id"]):
        c.fail("profil.id", tr("Kennung {id!r} ungültig (Buchstaben, Ziffern, . _ -)", id=d["id"]))
    if "workspaces" not in d:
        c.fail("profil", tr("„workspaces“ fehlt"))
    elif d["workspaces"] is None:
        c.fail("profil.workspaces", tr("muss eine Liste sein"))
    elif isinstance(d["workspaces"], list) and not d["workspaces"]:
        c.fail("profil.workspaces", tr("mindestens ein Arbeitsbereich nötig"))
