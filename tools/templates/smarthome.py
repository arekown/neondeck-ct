"""Vorlagen: Smart Home (Home Assistant)."""
from __future__ import annotations

from .build import (
    VOLUME,
    enc,
    http,
    http_action,
    template,
    wheel,
)

HA = "http://homeassistant.local:8123/api/webhook/"

TEMPLATES: list[dict] = [
    template(
        "smarthome", "Smart Home (Home Assistant)",
        "Webhooks an Home Assistant für Licht an/aus, Helligkeit, Szenen und Schalter; die "
        "Adresse http://homeassistant.local:8123/api/webhook/<id> einmal je Taste an die eigenen "
        "Webhook-IDs anpassen.",
        [("Smart Home", [
            http(HA + "licht_an", "Licht an", "BrightnessUp"),
            http(HA + "licht_aus", "Licht aus", "Sleep"),
            http(HA + "licht_hell", "Hell", "BrightnessUp"),
            http(HA + "licht_gedimmt", "Gedimmt", "SleepOff"),
            http(HA + "szene_abend", "Abend", "Sparkle"),
            http(HA + "szene_film", "Film", "MediaPlayer"),
            http(HA + "szene_lesen", "Lesen", "Library"),
            http(HA + "szene_morgen", "Morgen", "EmojiSmilingFace"),
            http(HA + "gute_nacht", "Gute Nacht", "Sleep"),
            http(HA + "alles_aus", "Alles aus", "Shutdown"),
            http(HA + "steckdose_an", "Steckd. an", "Multi-toggleOn"),
            http(HA + "steckdose_aus", "Steckd.aus", "Multi-toggleOff")])],
        [enc("Licht", http_action(HA + "licht_dunkler"), http_action(HA + "licht_heller"),
             press=http_action(HA + "licht_umschalten")), VOLUME],
        wheel("Licht", http_action(HA + "licht_dunkler"), http_action(HA + "licht_heller"),
              tap=http_action(HA + "licht_umschalten")), "#00ff60"),
]
