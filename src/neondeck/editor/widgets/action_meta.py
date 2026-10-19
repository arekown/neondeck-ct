"""Was Listen und Formulare ueber Aktionstypen wissen muessen, ohne Qt: verborgene Typen,
Anzeigenamen der Auswahlwerte, Kategorien in Anzeigereihenfolge, Kurzbeschreibung."""
from __future__ import annotations

from ...actions.base import CATEGORIES, registry
from ...actions.kde import LABELS as KDE_LABELS
from ...core.i18n import N_, tr
from ...engine.painter import action_label
from .key_names import key_display

# nur sichtbar, wenn schon belegt (Import; Mixer-Aktionen erzeugt der dynamische Ordner)
HIDDEN_TYPES = frozenset({"unsupported", "stream_volume", "stream_mute"})
CHOICE_LABELS = {
    **KDE_LABELS,
    "play_pause": N_("Wiedergabe/Pause"), "next": N_("Nächster Titel"), "previous": N_("Vorheriger Titel"),
    "stop": N_("Stopp"), "auto": N_("Automatisch"), "paste": N_("Einfügen"), "type": N_("Tippen"),
    "date": N_("Datum"), "week": N_("Kalenderwoche"),
    "windows": N_("Fenster"), "mixer": N_("Lautstärke-Mixer"),
    "loop": N_("Wiederholen umschalten"), "vertical": N_("Senkrecht"), "horizontal": N_("Waagerecht"),
    # Platz eines Fensters (run, app_focus)
    "none": N_("Nicht ändern"), "maximize": N_("Maximiert"), "left": N_("Linke Hälfte"),
    "right": N_("Rechte Hälfte"), "top": N_("Obere Hälfte"), "bottom": N_("Untere Hälfte"),
    "top_left": N_("Viertel oben links"), "top_right": N_("Viertel oben rechts"),
    "bottom_left": N_("Viertel unten links"), "bottom_right": N_("Viertel unten rechts"),
}


def ordered_categories(present) -> list[str]:
    """Kategorie-Schluessel in Anzeigereihenfolge (``CATEGORIES``); unbekannte alphabetisch
    dahinter."""
    return [c for c in CATEGORIES if c in present] + sorted(set(present) - set(CATEGORIES))


def category_name(cat: str) -> str:
    """Anzeigename eines Kategorie-Schluessels."""
    return tr(CATEGORIES.get(cat, cat))


def _param_text(kind: str, v) -> str:
    if kind == "keys":
        return key_display(v if isinstance(v, str) else "+".join(v))
    if kind == "choice":
        return tr(CHOICE_LABELS.get(v, v))
    if kind == "steps":
        return tr("{count} Schritte", count=len(v))
    if kind == "terminals":
        return tr("{count} Fenster", count=len(v))
    return v


def action_summary(action: dict) -> str:
    """Kurzbeschreibung fuer Listen: ``Tastenkürzel: Strg+C``."""
    label = action_label(action) if action.get("type") else tr("Keine Aktion")
    at = registry().get(action.get("type") or "")
    for p in at.params if at else []:
        v = action.get(p.name)
        if v not in (None, "", []):
            return f"{label}: {_param_text(p.kind, v)}"
    return label
