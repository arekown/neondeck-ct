"""Vorlagen: Arbeit am Rechner: Browser, Buero, Konsole, KDE, Ziffernblock."""
from __future__ import annotations

from .build import (
    VOLUME,
    app,
    btn,
    enc,
    history,
    hk,
    kde,
    ks,
    redo,
    save,
    template,
    term,
    typed,
    undo,
    wheel,
)

TEMPLATES: list[dict] = [
    template(
        "browser", "Browser (Brave, Firefox)",
        "Brave und Firefox fokussieren oder starten, Tabs öffnen, schließen und wiederherstellen, "
        "Zurück/Vor, Neu laden, Lesezeichen, privates Fenster, Downloads und Seitenwerkzeuge; "
        "Regler für Tabs, Zoom, Scrollen und Verlauf.",
        [("Browser", [
            app("brave-browser", "Brave"), app("org.mozilla.firefox", "Firefox"),
            hk("Strg+T", "Neuer Tab"), hk("Strg+W", "Tab zu", "Close"),
            hk("Strg+Umschalt+T", "Wieder auf", "Redo"), hk("Alt+Links", "Zurück", "ArrowLeft"),
            hk("Alt+Rechts", "Vor", "ArrowRight"), hk("F5", "Neu laden", "Refresh"),
            hk("Strg+D", "Lesezeich.", "Bookmark"), hk("Strg+Umschalt+N", "Privat", "Lock"),
            hk("Strg+L", "Adresse", "SearchComputer"), hk("Strg+J", "Downloads", "CircleArrowDown")]),
         ("Seite", [
            hk("Strg+F", "Suchen", "SearchComputer"), hk("F11", "Vollbild", "Monitor"),
            hk("Strg+0", "Zoom 100 %", "SmartZoom"), hk("Strg+H", "Verlauf"),
            hk("Strg+Umschalt+B", "Leiste", "BookmarkFilled"), hk("F12", "Entwickler", "Settings"),
            hk("Strg+U", "Quelltext"), hk("Strg+P", "Drucken", "Print"),
            hk("Strg+S", "Speichern", "OpenFile"), hk("Alt+Pos1", "Startseite", "Home"),
            hk("Strg+N", "Neues Fen."), hk("Strg+Umschalt+P", "Privat FF", "Lock")])],
        [enc("Tabs", "Strg+BildAuf", "Strg+BildAb", press="Strg+T"),
         enc("Zoom", "Strg+-", "Strg++", press="Strg+0"), enc("Scrollen", "Hoch", "Runter"),
         enc("Verlauf", "Alt+Links", "Alt+Rechts"), VOLUME],
        wheel("Scrollen", "Hoch", "Runter"), "#ff6000"),
    template(
        "buero", "Büro (LibreOffice, Thunderbird)",
        "LibreOffice Writer und Calc sowie Thunderbird fokussieren oder starten, Fett/Kursiv/"
        "Unterstrichen, Listen, Speichern und Drucken, neue Mail, Antworten, Weiterleiten und "
        "Kalender; Regler für Verlauf, Seiten, Tabellenblätter und Nachrichten.",
        [("Writer & Calc", [
            app("libreoffice-writer", "Writer", "Parchment"), app("libreoffice-calc", "Calc", "Graph"),
            hk("Strg+B", "Fett"), hk("Strg+I", "Kursiv"), hk("Strg+U", "Unterstr."),
            hk("Umschalt+F12", "Liste"), hk("F12", "Nummern"), save(),
            hk("Strg+P", "Drucken", "Print"), hk("Strg+H", "Ersetzen", "SearchComputer"), undo(),
            redo("Strg+Y")]),
         ("Mail", [
            app("org.mozilla.Thunderbird", "Thunderbrd", "SendMessage"),
            hk("Strg+N", "Neue Mail", "SendMessage"), hk("Strg+R", "Antworten", "ChatMessage"),
            hk("Strg+Umschalt+R", "Allen ant."), hk("Strg+L", "Weiterl."),
            hk("Strg+Enter", "Senden", "SendMessage"), hk("Strg+Umschalt+C", "Kalender", "Calendar"),
            hk("Strg+Umschalt+D", "Aufgaben", "CalendarDate"), hk("M", "Gelesen"),
            hk("Entf", "Löschen", "Delete"), hk("Strg+K", "Suchen", "SearchComputer"),
            hk("F5", "Abrufen", "Refresh")])],
        [history("Strg+Y"), enc("Seite", "BildAuf", "BildAb"),
         enc("Blatt", "Strg+BildAuf", "Strg+BildAb"), enc("Nachricht", "B", "F"), VOLUME],
        wheel("Seite", "BildAuf", "BildAb"), "#0090a0"),
    template(
        "textbausteine", "Textbausteine (Mail, Briefe)",
        "Häufige Texte auf Knopfdruck: Anrede, Grüße, Signatur, Adresse, E-Mail, Telefon, IBAN, "
        "Dank und Rückmeldung, dazu das heutige Datum; Platzhalter in eckigen Klammern einmal "
        "anpassen.",
        [("Texte", [
            typed("Hallo [Name],\n\n", "Hallo", "SpeechBubbleRound"),
            typed("Sehr geehrte Damen und Herren,\n\n", "Anrede", "SpeechBubbleSquare"),
            typed("Viele Grüße\n[Dein Name]", "Grüße", "EmojiSmilingFace"),
            typed("Mit freundlichen Grüßen\n[Dein Name]", "MfG", "Parchment"),
            typed("-- \n[Dein Name]\n[Firma]\nTel. [Telefon]\n[deine@mail.de]", "Signatur", "User"),
            typed("[Dein Name]\n[Straße Hausnummer]\n[PLZ Ort]", "Adresse", "Home"),
            typed("[deine@mail.de]", "E-Mail", "SendMessage"),
            typed("[Telefon]", "Telefon", "SpeechBubbleRounded"),
            typed("[IBAN]", "IBAN", "Lock"),
            typed("Vielen Dank!", "Danke!", "ThumbsUp"),
            typed("Ich bin gerade unterwegs und melde mich später.", "Später", "Clock"),
            btn({"type": "date", "format": "date"}, "Datum", "CalendarDate")])],
        [VOLUME],
        wheel("Scrollen", "Hoch", "Runter"), "#ffff99"),
    template(
        "admin", "Konsole & Admin (Konsole, htop, dnf)",
        "Konsole fokussieren oder starten, htop, Systemprotokoll, Updates mit dnf und Flatpak, "
        "Plattenplatz, Speicher, Netz, fehlgeschlagene Dienste, Grafikkarte und eine "
        "SSH-Verbindung (Platzhalter nutzer@rechner anpassen).",
        [("Admin", [
            app("org.kde.konsole", "Konsole", "Keyboard"), term("htop", "htop", "BarGraph"),
            term("journalctl -f", "Journal", "Parchment"),
            term("sudo dnf upgrade", "Update", "CircleArrowDown"),
            term("flatpak update", "Flatpak", "CircleArrowDown"),
            term("df -h", "Platten", "Folder"), term("free -h", "Speicher", "Graph"),
            term("ip a", "Netz", "Devices"), term("systemctl --failed", "Dienste", "NoEntrySign"),
            term("nvidia-smi", "GPU", "Monitor"), term("ssh nutzer@rechner", "SSH", "Devices"),
            kde("files", "Dateien", "OpenFolder")])],
        [VOLUME],
        wheel("Scrollen", "BildAuf", "BildAb"), "#39ff14"),
    template(
        "fenster", "Fenster & Monitore (KDE Plasma)",
        "Fenster kacheln, maximieren, minimieren, Vollbild und schließen, auf den anderen Monitor "
        "oder die nächste Arbeitsfläche schieben, Übersicht und Arbeitsflächen; Regler für "
        "Arbeitsflächen, Lautstärke und Helligkeit.",
        [("Fenster", [
            hk("Meta+Links", "Links", "ArrowLeft"), hk("Meta+Rechts", "Rechts", "ArrowRight"),
            hk("Meta+Hoch", "Oben", "ArrowUp"), hk("Meta+Runter", "Unten", "ArrowDown"),
            hk("Meta+BildAuf", "Maximieren", "DoubleArrowsUp"),
            hk("Meta+BildAb", "Minimieren", "DoubleArrowsDown"),
            ks("Window Fullscreen", "Vollbild", "Monitor"), hk("Alt+F4", "Schließen", "Close"),
            hk("Meta+Umschalt+Links", "Monitor ←", "CircleArrowLeft"),
            hk("Meta+Umschalt+Rechts", "Monitor →", "CircleArrowRight"),
            hk("Meta+T", "Kacheln"), ks("Window Above Other Windows", "Vordergr.", "Star")]),
         ("Arbeitsflächen", [
            kde("overview", "Übersicht", "SwitchPages"), kde("show_desktop", "Desktop", "HideDesktop"),
            kde("window_switcher", "Wechseln"),
            btn({"type": "dynamic_folder", "kind": "windows"}, "Fenster", "Folder"),
            kde("desktop_previous", "Fläche ←", "PillArrowLeft"),
            kde("desktop_next", "Fläche →", "PillArrowRight"),
            ks("Window One Desktop to the Left", "Fenst. ←"),
            ks("Window One Desktop to the Right", "Fenst. →"),
            kde("desktop_add", "+ Fläche"), kde("desktop_remove", "− Fläche")])],
        [enc("Fläche", rotate={"type": "kde_adjust", "left": "desktop_previous",
                               "right": "desktop_next"}, press={"type": "kde", "name": "overview"}),
         VOLUME,
         enc("Helligkeit", rotate={"type": "brightness"}, press={"type": "brightness_reset"},
             strip="bar")],
        wheel("Fläche", rotate={"type": "kde_adjust", "left": "desktop_previous",
                                "right": "desktop_next"}), "#00bfff"),
    template(
        "system", "System & Werkzeuge (KDE Plasma)",
        "Taschenrechner, Systemmonitor, Systemeinstellungen, Zwischenablage, Emoji, Suche, "
        "Bildschirmfoto, Stoppuhr, Uhr und Datum, Sperren und Abmelden; Regler für Lautstärke "
        "und Helligkeit.",
        [("System", [
            app("org.kde.kcalc", "Rechner", "Calculator"),
            app("org.kde.plasma-systemmonitor", "Monitor", "BarGraph"),
            app("systemsettings", "Einstell.", "Settings"),
            hk("Meta+V", "Ablage", "Clipboard"), kde("emoji", "Emoji", "EmojiLaugh"),
            kde("search", "Suche", "SearchComputer"), kde("screenshot", "Foto", "Screenshot"),
            btn({"type": "stopwatch"}, "Stoppuhr", "Stopwatch"), btn({"type": "clock"}, "Uhr", "Clock"),
            btn({"type": "date", "format": "date"}, "Datum", "CalendarDate"),
            kde("lock", "Sperren", "LockWorkstation"),
            ks("Log Out", "Abmelden", "Shutdown", component="ksmserver")])],
        [VOLUME, enc("Helligkeit", rotate={"type": "brightness"},
                     press={"type": "brightness_reset"}, strip="bar")],
        wheel("Lautstärke", rotate={"type": "volume"}, tap={"type": "mute_toggle"},
              display="arc"), "#ff00ff"),
    template(
        "ziffernblock", "Ziffernblock (Rechnen, Zahlen)",
        "Ziffernblock auf den Touch-Feldern: 0–9, Rechenzeichen, Komma und Enter, dazu Rück, "
        "Entf, Tab und Esc; Regler und Rad für die Pfeiltasten.",
        [("Ziffern", [
            hk("kp7", "7"), hk("kp8", "8"), hk("kp9", "9"), hk("kp/", "÷"),
            hk("kp4", "4"), hk("kp5", "5"), hk("kp6", "6"), hk("kp*", "×"),
            hk("kp1", "1"), hk("kp2", "2"), hk("kp3", "3"), hk("kp-", "−")]),
         ("Ziffern 2", [
            hk("kp0", "0"), hk("kp.", ","), hk("kp+", "+"), hk("kpenter", "Enter"),
            hk("Backspace", "Rück", "ArrowLeft"), hk("Entf", "Entf", "Delete"), hk("Tab", "Tab"),
            hk("Esc", "Esc", "Close"), hk("=", "="), hk("%", "%"), hk("(", "("), hk(")", ")")])],
        [enc("Cursor ↔", "Links", "Rechts"), enc("Cursor ↕", "Hoch", "Runter"), VOLUME],
        wheel("Cursor", "Hoch", "Runter"), "#80ffd0"),
]
