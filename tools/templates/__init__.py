"""Die mitgelieferten Vorlagen (``data/templates/*.json``), aus Daten nach Kategorie erzeugt."""
from __future__ import annotations

from . import arbeit, craft, gaming, grafik, smarthome

TEMPLATES: list[dict] = [*grafik.TEMPLATES, *gaming.TEMPLATES, *craft.TEMPLATES,
                         *arbeit.TEMPLATES, *smarthome.TEMPLATES]
