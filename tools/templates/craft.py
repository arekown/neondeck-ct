"""Vorlagen: Craft-Apps (ArtCraft, github.com/storytold): Kuerzel nur aus notes/research_notes/craft-apps-shortcuts.md
(aus dem Quellcode belegt). ``Cmd`` im Craft-Quellcode ist unter Linux Strg."""
from __future__ import annotations

from .build import (
    VOLUME,
    app,
    cad,
    copy,
    craft_id,
    cut,
    enc,
    history,
    hk,
    paste,
    redo,
    save,
    save_as,
    template,
    undo,
    wheel,
    zoom,
)

TEMPLATES: list[dict] = [
    template(
        "photocraft", "PhotoCraft (ArtCraft)",
        "PhotoCraft fokussieren oder starten, Werkzeuge im Photoshop-Layout, Auswahl und Ebenen, "
        "Ansicht und Export; Regler für Zoom, Pinselgröße, Härte und Ebenenreihenfolge.",
        [("Werkzeuge", [
            app("ai.storyteller.photocraft", "PhotoCraft"), hk("V", "Bewegen"), hk("M", "Auswahl"),
            hk("L", "Lasso"), hk("W", "Zauberst."), hk("C", "Zuschn."), hk("I", "Pipette"),
            hk("B", "Pinsel"), hk("E", "Radierer"), hk("S", "Stempel"), hk("J", "Reparatur"),
            hk("T", "Text")]),
         ("Bearbeiten", [
            undo(), redo(), copy(), paste(), hk("Strg+T", "Transform."), hk("Strg+A", "Alles"),
            hk("Strg+D", "Abwählen"), hk("Strg+Umschalt+I", "Umkehren"),
            hk("Strg+Umschalt+N", "Neue Ebene"), hk("Strg+J", "Ebene kop."), hk("Strg+G", "Gruppe"),
            hk("Strg+E", "Vereinen")]),
         ("Ansicht", [
            save(), save_as(), hk("Strg+Alt+Umschalt+W", "Export", "SendMessage"),
            hk("Strg+0", "Einpassen", "SmartZoom"), hk("Strg+1", "100 %"), hk("Tab", "Paletten"),
            hk("F7", "Ebenen"), hk("Strg+R", "Lineale"), hk("X", "Farbtausch"),
            hk("D", "Standard"), hk("Strg+L", "Tonwert"), hk("Strg+M", "Kurven")])],
        [zoom(), enc("Pinsel", "ö", "#"), enc("Härte", "Umschalt+ö", "Umschalt+#"),
         enc("Ebene", "Strg+[", "Strg+]"), history(), VOLUME],
        wheel("Zoom", "Strg+-", "Strg+="), "#1e6fff"),
    template(
        "lightcraft", "LightCraft (ArtCraft)",
        "LightCraft fokussieren oder starten, Bewertung 0–5, Farbmarken und Flaggen, Entwickeln "
        "und Export, Ansichten; Regler für Zoom, Pinselgröße und Miniaturgröße.",
        [("Bewerten", [
            app("lightcraft", "LightCraft"), hk("0", "0 Sterne", "StarOff"),
            *[hk(str(n), f"{n} Stern{'e' if n > 1 else ''}", "Star") for n in range(1, 6)],
            hk("6", "Rot"), hk("7", "Gelb"), hk("8", "Grün"), hk("9", "Blau"),
            hk("Umschalt+Z", "Auswählen", "ThumbsUp")]),
         ("Entwickeln", [
            hk("Umschalt+X", "Ablehnen", "ThumbsDown"), hk("Umschalt+U", "Ohne Flag."),
            hk("D", "Detail", "View"), hk("Umschalt+C", "Vergleich"), hk("Y", "Vorher"),
            hk("E", "Bearbeiten"), hk("C", "Zuschn."), hk("M", "Masken"), hk("B", "Pinsel"),
            hk("Umschalt+E", "Export", "SendMessage"), hk("Strg+E", "Wie zuvor"),
            hk("Strg+Umschalt+E", "PhotoCraft", "OpenApp")]),
         ("Ansicht", [
            hk("Strg+0", "Einpassen", "SmartZoom"), hk("Strg+Alt+0", "100 %"),
            hk("F", "Vollbild", "Monitor"), hk("Umschalt+L", "Licht aus"),
            hk("Strg+Umschalt+H", "Histogramm", "BarGraph"), hk("J", "Beschnitt"),
            hk("S", "Softproof"), hk("Strg+Umschalt+C", "Einst.kop.", "Copy"),
            hk("Strg+Umschalt+V", "Einst.einf", "Paste"), hk("Strg+S", "Metadaten", "OpenFile"),
            hk("Pos1", "Erstes", "ArrowLeft"), hk("Ende", "Letztes", "ArrowRight")])],
        [zoom(press="Z"), enc("Pinsel", "[", "]"), enc("Miniatur", "-", "="), VOLUME],
        wheel("Zoom", "Strg+-", "Strg+="), "#66ccff"),
    template(
        "filmcraft", "FilmCraft (ArtCraft)",
        "FilmCraft fokussieren oder starten, Wiedergabe mit J/K/L, In/Out, Marker und Schnitt, "
        "Schnittwerkzeuge, Bearbeiten; Regler für Bild ±1/±5, Schnittpunkte, Zeitleisten-Zoom "
        "und Clip-Lautstärke.",
        [("Schnitt", [
            app(craft_id("filmcraft"), "FilmCraft"), hk("Leertaste", "Play", "MediaPlayPause"),
            hk("J", "Rückwärts", "MediaPrevTrack"), hk("K", "Stopp", "MediaStop"),
            hk("L", "Vorwärts", "MediaNextTrack"), hk("I", "In-Punkt"), hk("O", "Out-Punkt"),
            hk("M", "Marker", "Bookmark"), hk("Strg+K", "Schnitt", "Cut"), undo(), redo(),
            save()]),
         ("Werkzeuge", [
            hk("V", "Auswahl"), hk("C", "Rasierm.", "Cut"), hk("B", "Ripple"), hk("N", "Rolling"),
            hk("R", "Dehnen"), hk("Y", "Slip"), hk("U", "Slide"), hk("P", "Stift"),
            hk("H", "Hand"), hk("Z", "Zoom", "ZoomIn"), hk("T", "Text"), hk("S", "Einrasten")]),
         ("Bearbeiten", [
            hk("Umschalt+I", "Zu In"), hk("Umschalt+O", "Zu Out"), hk(";", "Heben"),
            hk("'", "Extrah."), hk("Entf", "Löschen", "Delete"),
            hk("Umschalt+Entf", "Ripple-Lö."), copy(), paste(), cut(),
            hk("Strg+I", "Import", "OpenFolder"), hk("Strg+M", "Export", "SendMessage"),
            hk("\\", "Sequenz", "SmartZoom")])],
        [enc("Bild", "Links", "Rechts", press="Leertaste"),
         enc("5 Bilder", "Umschalt+Links", "Umschalt+Rechts"),
         enc("Schnittpkt", "Hoch", "Runter"), enc("Zeitleiste", "-", "=", press="\\"),
         enc("Clip-dB", "[", "]"), VOLUME],
        wheel("Bild", "Links", "Rechts"), "#7a3cff"),
    template(
        "effectcraft", "EffectCraft (ArtCraft)",
        "EffectCraft fokussieren oder starten, Vorschau, Keyframes, Arbeitsbereich und Marker, "
        "Werkzeuge und Eigenschaften im After-Effects-Layout, Ebenen; Regler für Zeit- und "
        "Viewer-Zoom, Keyframes und Ebenen-Verschiebung.",
        [("Zeit", [
            app(craft_id("effectcraft"), "EffectCrft"), hk("Leertaste", "Vorschau", "MediaPlayPause"),
            hk("I", "Ebene In"), hk("O", "Ebene Out"), hk("J", "Keyfr. ←", "ArrowLeft"),
            hk("K", "Keyfr. →", "ArrowRight"), hk("B", "Bereich A"), hk("N", "Bereich E"),
            hk("kp*", "Marker", "Bookmark"), hk("F9", "Easy Ease"), hk("Umschalt+F3", "Graph", "Graph"),
            hk("Strg+Umschalt+D", "Teilen", "Cut")]),
         ("Werkzeuge", [
            hk("V", "Auswahl"), hk("H", "Hand"), hk("Z", "Zoom", "ZoomIn"), hk("Strg+T", "Text"),
            hk("G", "Stift"), hk("Q", "Form"), hk("W", "Drehwerkz."), hk("Y", "Pan hinten"),
            hk("P", "Position"), hk("S", "Skalierung"), hk("R", "Rotation"),
            hk("T", "Deckkraft")]),
         ("Ebene", [
            undo(), redo(), save(), hk("Strg+N", "Neue Komp."), hk("Strg+Y", "Farbfläche"),
            hk("Strg+Alt+Y", "Einst.-Eb."), hk("Strg+Umschalt+C", "Vorkomp."),
            hk("Strg+D", "Duplikat", "Copy"), hk("A", "Anker"), hk("E", "Effekte"),
            hk("M", "Masken"), hk("Alt+Umschalt+P", "Key Pos.")])],
        [enc("Zeit-Zoom", "-", "="), enc("Viewer", ",", ".", press="/"),
         enc("Keyframe", "J", "K"), enc("Ebene ±1", "Alt+BildAuf", "Alt+BildAb"),
         enc("Schieben", "Links", "Rechts"), VOLUME],
        wheel("Keyframe", "J", "K"), "#d080ff"),
    template(
        "vectorcraft", "VectorCraft (ArtCraft)",
        "VectorCraft fokussieren oder starten, Werkzeuge im Illustrator-Layout, Objekte anordnen "
        "und gruppieren, Datei und Ansicht; Regler für Zoom und Schriftgröße.",
        [("Werkzeuge", [
            app(craft_id("vectorcraft"), "VectorCrft"), hk("V", "Auswahl"), hk("A", "Direkt"),
            hk("P", "Stift"), hk("T", "Text"), hk("M", "Rechteck"), hk("L", "Ellipse", "Ellipse"),
            hk("B", "Pinsel"), hk("Umschalt+E", "Radierer"), hk("R", "Drehen"),
            hk("S", "Skalieren"), hk("I", "Pipette")]),
         ("Objekt", [
            undo(), redo(), hk("Strg+G", "Gruppe"), hk("Strg+Umschalt+G", "Aufheben"),
            hk("Strg+]", "Nach vorn", "ArrowUp"), hk("Strg+[", "Nach hint.", "ArrowDown"),
            hk("Strg+Umschalt+]", "Ganz vorn", "DoubleArrowsUp"),
            hk("Strg+Umschalt+[", "Ganz hint.", "DoubleArrowsDown"), hk("Strg+A", "Alles"),
            hk("Strg+Umschalt+A", "Abwählen"), hk("Strg+J", "Verbinden"),
            hk("Strg+Umschalt+O", "Konturen")]),
         ("Datei", [
            save(), save_as(), hk("Strg+O", "Öffnen", "OpenFolder"), hk("Strg+N", "Neu"),
            copy(), paste(), hk("Strg+F", "Einf.vorn"), hk("Strg+B", "Einf.hint."),
            hk("Strg+0", "Einpassen", "SmartZoom"), hk("Strg+1", "100 %"),
            hk("Umschalt+X", "Farbtausch"), hk("H", "Hand")])],
        [zoom(), enc("Schrift", "Strg+Umschalt+,", "Strg+Umschalt+."), history(), VOLUME],
        wheel("Zoom", "Strg+-", "Strg+="), "#ff8c00"),
    template(
        "soundcraft", "SoundCraft (ArtCraft)",
        "SoundCraft fokussieren oder starten, Transport und Aufnahme, Clips bearbeiten, Spuren "
        "und Edit-Werkzeuge im Pro-Tools-Layout; Regler für Zeitleisten-Zoom, Spurhöhe, "
        "Clip-Gain und Nudge.",
        [("Transport", [
            app(craft_id("soundcraft"), "SoundCraft"), hk("Leertaste", "Play", "MediaPlayPause"),
            hk("F12", "Aufnahme", "Dictation"), hk("Pos1", "Anfang", "MediaPrevTrack"),
            hk("Ende", "Ende", "MediaNextTrack"), hk("Enter", "Marker", "Bookmark"),
            hk("Strg+Umschalt+L", "Loop", "Loop"), hk("Umschalt+Leertaste", "Halb"),
            undo(), redo(), save(), hk("Strg+=", "Mix/Edit", "SwitchPages")]),
         ("Bearbeiten", [
            copy(), cut(), paste(), hk("Strg+D", "Duplikat"), hk("Strg+E", "Trennen", "Cut"),
            hk("Strg+H", "Heilen"), hk("Strg+T", "Zuschn."), hk("Strg+U", "Stille weg"),
            hk("Strg+M", "Clip stumm", "MediaVolumeMute"), hk("Strg+F", "Blenden"),
            hk("Strg+Umschalt+N", "Neue Spur"), hk("Strg+Alt+B", "Bounce", "SendMessage")]),
         ("Spur & Wkz", [
            hk("Umschalt+M", "Stumm", "MediaVolumeMute"), hk("Umschalt+S", "Solo", "MediaHeadphones"),
            hk("Umschalt+R", "Aufn.-ber."), hk("Umschalt+I", "Monitor", "MediaHeadphones"),
            hk("F1", "Shuffle"), hk("F2", "Slip"), hk("F3", "Spot"), hk("F4", "Grid"),
            hk("F5", "Zoom-Wkz.", "ZoomIn"), hk("F6", "Trim"), hk("F7", "Selector"),
            hk("F8", "Grabber")])],
        [enc("Zoom", "Strg+[", "Strg+]", press="Alt+A"), enc("Spurhöhe", "Strg+Runter", "Strg+Hoch"),
         enc("Clip-Gain", "Strg+Umschalt+Runter", "Strg+Umschalt+Hoch"), enc("Nudge", "-", "+"),
         history(), VOLUME],
        wheel("Zoom", "Strg+[", "Strg+]"), "#00e5c0"),
    template(
        "cadcraft", "CADCraft (ArtCraft)",
        "CADCraft fokussieren oder starten, Zeichen- und Änderungsbefehle über die Befehlszeile "
        "(Alias plus Enter), Fang, Raster und Ortho auf den F-Tasten, Datei; Regler für den Verlauf.",
        [("Zeichnen", [
            app("cadcraft", "CADCraft"), cad("L", "Linie"), cad("PL", "Polylinie"),
            cad("C", "Kreis", "Ellipse"), cad("A", "Bogen"), cad("REC", "Rechteck"),
            cad("H", "Schraffur"), cad("T", "Text"), cad("DLI", "Bemaßung"), cad("O", "Versatz"),
            cad("TR", "Stutzen"), cad("EX", "Dehnen")]),
         ("Ändern", [
            cad("M", "Schieben"), cad("CO", "Kopieren", "Copy"), cad("RO", "Drehen"),
            cad("SC", "Skalieren"), cad("MI", "Spiegeln"), cad("S", "Strecken"),
            cad("F", "Abrunden"), cad("X", "Zerlegen"), cad("E", "Löschen", "Delete"),
            cad("AR", "Reihe"), cad("Z", "Zoom", "ZoomIn"), cad("LA", "Layer")]),
         ("Fang & Datei", [
            hk("F3", "Objektfang"), hk("F7", "Raster"), hk("F8", "Ortho"), hk("F9", "Fangraster"),
            hk("F10", "Polar"), hk("F11", "Verfolgung"), hk("F12", "Dyn. Eing."), undo(),
            redo("Strg+Y"), save(), hk("Strg+P", "Plotten", "Print"),
            hk("Esc", "Abbrechen", "Close")])],
        [history("Strg+Y"), VOLUME],
        wheel("Verlauf", "Strg+Z", "Strg+Y"), "#ffffff"),
    template(
        "gridcraft", "GridCraft (ArtCraft)",
        "GridCraft fokussieren oder starten, Zellformat, Summe, Ausfüllen, Filter und Blätter, "
        "Bearbeiten, Suchen und Drucken; Regler für Blattwechsel und Schriftgröße.",
        [("Tabelle", [
            app("gridcraft", "GridCraft"), hk("Strg+B", "Fett"), hk("Strg+I", "Kursiv"),
            hk("Strg+U", "Unterstr."), hk("Strg+1", "Formatier."), hk("Strg+Umschalt+T", "Summe"),
            hk("F2", "Bearbeiten"), hk("Strg+D", "Ausf. ↓", "ArrowDown"),
            hk("Strg+R", "Ausf. →", "ArrowRight"), hk("Strg+Umschalt+L", "Filter"),
            hk("F9", "Berechnen", "Refresh"), hk("Umschalt+F11", "Neu. Blatt")]),
         ("Bearbeiten", [
            undo(), redo("Strg+Y"), copy(), cut(), paste(),
            hk("Strg+F", "Suchen", "SearchComputer"), hk("Strg+H", "Ersetzen"),
            hk("Strg+G", "Gehe zu"), save(), hk("Strg+P", "Drucken", "Print"),
            hk("Umschalt+Leertaste", "Zeile"), hk("Strg+Leertaste", "Spalte")])],
        [enc("Blatt", "Strg+BildAuf", "Strg+BildAb"),
         enc("Schrift", "Strg+Umschalt+<", "Strg+Umschalt+>"), history("Strg+Y"), VOLUME],
        wheel("Blatt", "Strg+BildAuf", "Strg+BildAb"), "#22c55e"),
    template(
        "deckcraft", "DeckCraft (ArtCraft)",
        "DeckCraft fokussieren oder starten, Folien anlegen und vorführen, Bearbeiten, "
        "Textformat, Ausrichtung und Gruppieren; Regler für Folienwechsel, Schriftgröße, Zoom "
        "und Ebenenreihenfolge.",
        [("Folien", [
            app(craft_id("deckcraft"), "DeckCraft"), hk("Strg+Umschalt+N", "Neue Folie"),
            hk("Strg+Umschalt+Enter", "Schau Anf.", "MediaPlayPause"),
            hk("Strg+Enter", "Schau hier", "MediaPlayer"), hk("Pos1", "Erste", "ArrowLeft"),
            hk("Ende", "Letzte", "ArrowRight"), hk("Strg+D", "Duplikat", "Copy"),
            hk("Entf", "Löschen", "Delete"), undo(), redo("Strg+Y"), save(),
            hk("Strg+Umschalt+P", "Befehle")]),
         ("Format", [
            hk("Strg+B", "Fett"), hk("Strg+I", "Kursiv"), hk("Strg+U", "Unterstr."),
            hk("Strg+L", "Links"), hk("Strg+E", "Zentriert"), hk("Strg+R", "Rechts"),
            hk("Strg+J", "Blocksatz"), hk("Strg+Umschalt+C", "Format kop", "Copy"),
            hk("Strg+Umschalt+V", "Format ein", "Paste"), hk("Strg+Alt+G", "Gruppe"),
            hk("Strg+Alt+Umschalt+G", "Aufheben"), hk("Alt+P", "Medien", "MediaPlayer")])],
        [enc("Folie", "BildAuf", "BildAb"), enc("Schrift", "Strg+Umschalt+,", "Strg+Umschalt+."),
         zoom(press=None), enc("Ebene", "Strg+[", "Strg+]"), history("Strg+Y"), VOLUME],
        wheel("Folie", "BildAuf", "BildAb"), "#ff9e80"),
    template(
        "pdfcraft", "PdfCraft (ArtCraft)",
        "PdfCraft fokussieren oder starten, Öffnen, Speichern, Drucken, Suchen, Befehlspalette, "
        "Seite und Vollbild; Regler für Verlauf, Ansicht zurück/vor und Tabs.",
        [("PDF", [
            app(craft_id("pdfcraft"), "PdfCraft"), hk("Strg+O", "Öffnen", "OpenFolder"), save(),
            save_as(), hk("Strg+P", "Drucken", "Print"), hk("Strg+F", "Suchen", "SearchComputer"),
            hk("Strg+Umschalt+F", "Erweitert"), hk("Strg+K", "Befehle"),
            hk("Strg+Umschalt+N", "Gehe Seite"), hk("Strg+L", "Vollbild", "Monitor"),
            hk("Strg+3", "Einpassen", "SmartZoom"), hk("Strg+B", "Lesezeich.", "Bookmark")])],
        [history(), enc("Ansicht", "Strg+[", "Strg+]"),
         enc("Tab", "Strg+Umschalt+Tab", "Strg+Tab"), VOLUME],
        wheel("Ansicht", "Strg+[", "Strg+]"), "#d4142a"),
    template(
        "designcraft", "DesignCraft (ArtCraft)",
        "DesignCraft fokussieren oder starten, Werkzeuge im InDesign-Layout, Objekte und "
        "Textformat, Ansicht, Export und Paletten; Regler für Zoom, Seite, Druckbogen, "
        "Punktgröße und Ebenenreihenfolge.",
        [("Werkzeuge", [
            app(craft_id("designcraft"), "DesignCrft"), hk("V", "Auswahl"), hk("A", "Direkt"),
            hk("T", "Text"), hk("\\", "Linie"), hk("P", "Stift"), hk("F", "Rahmen"),
            hk("M", "Rechteck"), hk("L", "Ellipse", "Ellipse"), hk("R", "Drehen"),
            hk("S", "Skalieren"), hk("H", "Hand")]),
         ("Objekt & Text", [
            undo(), redo(), hk("Strg+G", "Gruppe"), hk("Strg+Umschalt+G", "Aufheben"),
            hk("Strg+L", "Sperren", "Lock"), hk("Strg+Umschalt+B", "Fett"),
            hk("Strg+Umschalt+I", "Kursiv"), hk("Strg+Umschalt+U", "Unterstr."),
            hk("Strg+Umschalt+L", "Links"), hk("Strg+Umschalt+C", "Mitte"),
            hk("Strg+Umschalt+R", "Rechts"), hk("Strg+D", "Platzieren", "OpenFolder")]),
         ("Ansicht", [
            save(), hk("Strg+E", "PNG-Export", "SendMessage"), hk("Strg+P", "Drucken", "Print"),
            hk("W", "Vorschau", "View"), hk("Strg+0", "Einpassen", "SmartZoom"),
            hk("Strg+1", "100 %"), hk("Strg+Alt+0", "Druckbog."), hk("Strg+J", "Gehe Seite"),
            hk("Tab", "Paletten"), hk("Strg+T", "Zeichen"), hk("Strg+Alt+T", "Absatz"),
            hk("I", "Pipette")])],
        [zoom(), enc("Seite", "Umschalt+BildAuf", "Umschalt+BildAb"),
         enc("Druckbog.", "Alt+BildAuf", "Alt+BildAb"),
         enc("Punktgr.", "Strg+Umschalt+,", "Strg+Umschalt+."), enc("Ebene", "Strg+[", "Strg+]"),
         VOLUME],
        wheel("Zoom", "Strg+-", "Strg+="), "#ff40b0"),
    template(
        "figcraft", "FigCraft (ArtCraft)",
        "FigCraft fokussieren oder starten, Werkzeuge im Figma-Layout, Objekte, Komponenten und "
        "Boolesche Operationen, Ausrichten, Export und Präsentation; Regler für Zoom, Frames und "
        "Typografie.",
        [("Werkzeuge", [
            app(craft_id("figcraft"), "FigCraft"), hk("V", "Bewegen"), hk("K", "Skalieren"),
            hk("H", "Hand"), hk("F", "Frame"), hk("R", "Rechteck"), hk("L", "Linie"),
            hk("Umschalt+L", "Pfeil", "ArrowRight"), hk("O", "Ellipse", "Ellipse"),
            hk("P", "Stift"), hk("T", "Text"), hk("C", "Kommentar", "ChatMessage")]),
         ("Objekt", [
            undo(), redo(), hk("Strg+D", "Duplikat", "Copy"), hk("Strg+G", "Gruppe"),
            hk("Strg+Umschalt+G", "Aufheben"), hk("Strg+Alt+G", "Frame um"),
            hk("Strg+Alt+K", "Komponente"), hk("Strg+Alt+B", "Lösen"),
            hk("Alt+Umschalt+U", "Vereinig."), hk("Alt+Umschalt+S", "Abziehen"),
            hk("Umschalt+H", "Spiegel H"), hk("Umschalt+V", "Spiegel V")]),
         ("Ausrichten", [
            hk("Alt+A", "Links"), hk("Alt+H", "Mitte H"), hk("Alt+D", "Rechts"),
            hk("Alt+W", "Oben"), hk("Alt+V", "Mitte V"), hk("Alt+S", "Unten"), save(),
            hk("Strg+Umschalt+E", "Export", "SendMessage"),
            hk("Strg+Umschalt+I", "Import", "OpenFolder"),
            hk("Strg+Alt+Enter", "Präsent.", "MediaPlayPause"),
            hk("Umschalt+Leertaste", "Vorschau", "View"), hk("Strg+K", "Aktionen")])],
        [zoom(press="Umschalt+1"), enc("Frame", "Umschalt+N", "N"),
         enc("Schrift", "Strg+Umschalt+,", "Strg+Umschalt+."),
         enc("Schnitt", "Strg+Alt+,", "Strg+Alt+."),
         enc("Zeilenhöhe", "Alt+Umschalt+,", "Alt+Umschalt+."), enc("Laufweite", "Alt+,", "Alt+.")],
        wheel("Zoom", "Strg+-", "Strg+="), "#b8ff3d"),
    template(
        "wordcraft", "WordCraft (ArtCraft)",
        "WordCraft fokussieren oder starten, Zeichen- und Absatzformat, Überschriften, Bearbeiten "
        "und Suchen, Dokument-Werkzeuge; Regler für Schriftgröße, Absatz verschieben und "
        "wortweises Springen.",
        [("Format", [
            app("wordcraft", "WordCraft"), hk("Strg+B", "Fett"), hk("Strg+I", "Kursiv"),
            hk("Strg+U", "Unterstr."), hk("Strg+Umschalt+X", "Durchgestr"),
            hk("Strg+Alt+1", "Übersch. 1"), hk("Strg+Alt+2", "Übersch. 2"),
            hk("Strg+Alt+3", "Übersch. 3"), hk("Strg+Umschalt+N", "Standard"),
            hk("Strg+Umschalt+L", "Aufzählung"), hk("Strg+L", "Links"), hk("Strg+E", "Mitte")]),
         ("Bearbeiten", [
            undo(), redo("Strg+Y"), copy(), cut(), paste(), hk("Strg+Umschalt+Alt+V", "Nur Text"),
            hk("Strg+F", "Suchen", "SearchComputer"), hk("Strg+H", "Ersetzen"), save(),
            save_as("F12"), hk("Strg+P", "Drucken", "Print"), hk("Strg+K", "Link")]),
         ("Dokument", [
            hk("Strg+R", "Rechts"), hk("Strg+J", "Blocksatz"), hk("Strg+M", "Einzug +"),
            hk("Strg+Umschalt+M", "Einzug −"), hk("Strg+Enter", "Umbruch"),
            hk("Strg+Alt+M", "Kommentar", "ChatMessage"), hk("Strg+Alt+F", "Fußnote"),
            hk("Strg+Umschalt+E", "Änderungen"), hk("F7", "Rechtschr."), hk("Strg+8", "Absatzm."),
            hk("F11", "Vollbild", "Monitor"), hk("F9", "Felder", "Refresh")])],
        [enc("Schrift", "Strg+Umschalt+,", "Strg+Umschalt+."), enc("Schrift ±1", "Strg+[", "Strg+]"),
         enc("Absatz", "Alt+Umschalt+Hoch", "Alt+Umschalt+Runter"),
         enc("Wort", "Strg+Links", "Strg+Rechts"), history("Strg+Y"), VOLUME],
        wheel("Schrift", "Strg+Umschalt+,", "Strg+Umschalt+."), "#2b3fbf"),
]
