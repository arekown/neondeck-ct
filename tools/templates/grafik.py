"""Vorlagen: Grafik, Foto, Video, 3D."""
from __future__ import annotations

from .build import (
    VOLUME,
    app,
    enc,
    history,
    hk,
    kde,
    redo,
    save,
    template,
    undo,
    wheel,
)

TEMPLATES: list[dict] = [
    template(
        "grafik", "Grafik (GIMP, Inkscape, Blender)",
        "GIMP, Inkscape und Blender fokussieren oder starten, Bildschirmfoto, Rückgängig/Wiederholen, "
        "Kopieren/Einfügen, Speichern und Exportieren; Regler für Zoom, Verlauf und Ebenen.",
        [("Grafik", [
            app("org.gimp.GIMP", "GIMP"), app("org.inkscape.Inkscape", "Inkscape"),
            app("org.blender.Blender", "Blender", "Cube"), kde("screenshot", "Foto", "Screenshot"),
            hk("Strg+Z", "Zurück", "Undo"), hk("Strg+Umschalt+Z", "Wieder", "Redo"),
            hk("Strg+C", "Kopieren", "Copy"), hk("Strg+V", "Einfügen", "Paste"),
            hk("Strg+S", "Speichern", "OpenFile"), hk("Strg+Umschalt+E", "Export", "SendMessage"),
            hk("Strg+A", "Alles"), hk("Strg+Umschalt+A", "Nichts")])],
        [enc("Zoom", "kp-", "kp+", press="1"), enc("Verlauf", "Strg+Z", "Strg+Umschalt+Z"),
         enc("Ebene", "BildAuf", "BildAb"), VOLUME],
        wheel("Zoom", "kp-", "kp+"), "#f9f002"),
    template(
        "fotos", "Fotos (darktable, digiKam)",
        "darktable und digiKam fokussieren oder starten, Bewertung 0–5, Ablehnen und Farbmarken, "
        "Bild vor/zurück, Verlauf kopieren und einfügen, Duplikat und Export; Regler für Bilder "
        "und Verlauf.",
        [("Bewerten", [
            app("org.darktable.Darktable", "darktable"), hk("0", "0 Sterne", "StarOff"),
            *[hk(str(n), f"{n} Stern{'e' if n > 1 else ''}", "Star") for n in range(1, 6)],
            hk("R", "Ablehnen", "ThumbsDown"), hk("F1", "Rot"), hk("F2", "Gelb"), hk("F3", "Grün"),
            hk("F4", "Blau")]),
         ("Bearbeiten", [
            hk("L", "Leuchtt.", "Library"), hk("D", "Dunkelkam."),
            hk("Backspace", "Bild zur.", "ArrowLeft"), hk("Leertaste", "Bild vor", "ArrowRight"),
            hk("Strg+C", "Verl. kop.", "Copy"), hk("Strg+V", "Verl. einf", "Paste"),
            hk("Strg+D", "Duplikat"), hk("Strg+E", "Export", "SendMessage"), undo(),
            redo("Strg+Y"), hk("F11", "Vollbild", "Monitor"), hk("Tab", "Leisten")]),
         ("digiKam", [
            app("org.kde.digikam", "digiKam"), hk("Strg+0", "0 Sterne", "StarOff"),
            *[hk(f"Strg+{n}", f"{n} Stern{'e' if n > 1 else ''}", "Star") for n in range(1, 6)],
            hk("F4", "Editor")])],
        [enc("Bild", "Backspace", "Leertaste"), history("Strg+Y"), VOLUME],
        wheel("Bild", "Backspace", "Leertaste"), "#ffe4b5"),
    template(
        "videoschnitt", "Videoschnitt (Kdenlive, DaVinci Resolve)",
        "Kdenlive und DaVinci Resolve fokussieren oder starten, Wiedergabe mit J/K/L, In/Out, "
        "Schneiden, Marker/Guide und Werkzeuge je Programm; Rad bildweise, Regler für "
        "Zeitleisten-Zoom und Verlauf.",
        [("Kdenlive", [
            app("org.kde.kdenlive", "Kdenlive"), hk("Leertaste", "Play", "MediaPlayPause"),
            hk("J", "Rückwärts", "MediaPrevTrack"), hk("K", "Stopp", "MediaStop"),
            hk("L", "Vorwärts", "MediaNextTrack"), hk("I", "In-Punkt"), hk("O", "Out-Punkt"),
            hk("Umschalt+R", "Schneiden", "Cut"), hk("G", "Guide", "Bookmark"),
            hk("S", "Auswahl"), hk("X", "Rasierm."), hk("Strg+Enter", "Rendern", "SendMessage")]),
         ("Resolve", [
            app("com.blackmagicdesign.resolve", "Resolve"), hk("Leertaste", "Play", "MediaPlayPause"),
            hk("J", "Rückwärts", "MediaPrevTrack"), hk("K", "Stopp", "MediaStop"),
            hk("L", "Vorwärts", "MediaNextTrack"), hk("I", "In-Punkt"), hk("O", "Out-Punkt"),
            hk("Strg+B", "Schneiden", "Cut"), hk("M", "Marker", "Bookmark"), hk("A", "Auswahl"),
            hk("B", "Klinge"), hk("Backspace", "Löschen", "Delete")])],
        [enc("Bild", "Links", "Rechts", press="Leertaste"),
         enc("Zoom KDL", "Strg+-", "Strg++"), enc("Zoom DVR", "Strg+-", "Strg+="),
         enc("Schnitt DVR", "Hoch", "Runter"), history(), VOLUME],
        wheel("Bild", "Links", "Rechts"), "#ffb000"),
    template(
        "unreal", "Unreal Engine (Editor)",
        "Unreal Editor fokussieren oder starten, Play/Simulate/Stop, Speichern, Transformieren, "
        "Duplizieren, Live Coding, Ansichten und Ansichtsmodi; Regler für den Verlauf.",
        [("Editor", [
            app("unreal-editor", "Unreal", "Cube"), hk("Alt+P", "Play", "MediaPlayPause"),
            hk("Alt+S", "Simulate"), hk("Esc", "Stopp", "MediaStop"), save(),
            hk("Strg+Umschalt+S", "Alles sp.", "OpenFile"), hk("W", "Bewegen"),
            hk("E", "Drehen"), hk("R", "Skalieren"), hk("Strg+D", "Duplikat", "Copy"),
            hk("Ende", "Auf Boden", "ArrowDown"), hk("Strg+Alt+F11", "Live Code", "Refresh")]),
         ("Ansicht", [
            hk("F", "Fokus", "SmartZoom"), hk("G", "Game-View", "View"),
            hk("Strg+Leertaste", "Content", "Folder"), hk("Alt+G", "Perspekt.", "Cube"),
            hk("Alt+J", "Oben"), hk("Alt+H", "Vorne"), hk("Alt+K", "Seite"), hk("Alt+4", "Lit"),
            hk("Alt+3", "Unlit"), hk("Alt+2", "Drahtgit."), hk("F11", "Vollbild", "Monitor"),
            undo()])],
        [history("Strg+Y"), VOLUME],
        wheel("Verlauf", "Strg+Z", "Strg+Y"), "#b0b0b0"),
    template(
        "blender", "Blender (3D)",
        "Blender fokussieren oder starten, Ansichten über den Ziffernblock, Rendern, Modus, "
        "Greifen/Drehen/Skalieren, Hinzufügen, Duplizieren und Speichern; Regler für Zoom, "
        "Bild ±, Ansicht drehen und Verlauf.",
        [("Ansicht", [
            app("org.blender.Blender", "Blender", "Cube"), hk("kp1", "Vorne"), hk("kp3", "Rechts"),
            hk("kp7", "Oben"), hk("kp0", "Kamera", "MediaVideoOn"), hk("kp5", "Ortho/Pers"),
            hk("kp.", "Auswahl", "SmartZoom"), hk("Pos1", "Alles", "ZoomInOut"),
            hk("kp/", "Lokal", "View"), hk("Z", "Shading"), hk("Strg+Leertaste", "Vollbild", "Monitor"),
            hk("F12", "Rendern", "Screenshot")]),
         ("Bearbeiten", [
            hk("Tab", "Modus", "SwitchPages"), hk("G", "Greifen"), hk("R", "Drehen"),
            hk("S", "Skalieren"), hk("Umschalt+A", "Hinzufüg."), hk("Umschalt+D", "Duplikat", "Copy"),
            hk("X", "Löschen", "Delete"), save(), undo(), redo(),
            hk("Leertaste", "Abspielen", "MediaPlayPause"), hk("N", "Seitenl.")])],
        [enc("Zoom", "kp-", "kp+", press="kp."), enc("Bild", "Links", "Rechts", press="Leertaste"),
         enc("Drehen ↔", "kp4", "kp6"), enc("Drehen ↕", "kp2", "kp8"), history(), VOLUME],
        wheel("Zoom", "kp-", "kp+"), "#c86400"),
]
