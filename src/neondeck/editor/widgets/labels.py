"""Deutsche Namen der Bedienelemente und kurze Beschriftungen von Belegungen (ohne Qt)."""
from __future__ import annotations

from ...core.i18n import N_, tr
from ...device.layout import ControlKind, ControlRef
from ...engine.navigation_state import BACK_TILE
from ...engine.painter import action_label
from ...profile.model import Assignment

KNOB_NAMES = (N_("links oben"), N_("links Mitte"), N_("links unten"),
              N_("rechts oben"), N_("rechts Mitte"), N_("rechts unten"))
_KIND_NAMES = {ControlKind.TOUCH: N_("Touch-Taste"), ControlKind.ROUND: N_("Runde Taste"),
               ControlKind.SQUARE: N_("Eckige Taste")}


def ref_name(ref: ControlRef) -> str:
    """Deutscher Name eines Bedienelements (Titel im Editor, Tooltip)."""
    if ref.kind in _KIND_NAMES:
        return tr("{kind} {n}", kind=tr(_KIND_NAMES[ref.kind]), n=ref.index + 1)
    if ref.kind in (ControlKind.KNOB, ControlKind.STRIP):
        return tr("Regler {name}", name=tr(KNOB_NAMES[ref.index]))
    return tr("Rad")


def assignment_label(a: Assignment | None) -> str:
    """Text einer Taste ohne Display: eigene Bezeichnung, sonst Name der Aktion."""
    if a is None:
        return ""
    if a.image.text.strip():
        text = a.image.text.strip()
        return tr(text) if a is BACK_TILE else text  # „Zurück“ ist N_-Text
    return action_label(a.action) if (a.action or {}).get("type") else ""
