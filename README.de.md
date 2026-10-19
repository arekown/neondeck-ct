# Neondeck CT

[English](README.md) · **Deutsch**

Software für den Loupedeck CT unter Linux (KDE Plasma 6, Wayland) in Python/Qt (PySide6).
Das Gerät wird direkt über die serielle Schnittstelle angesprochen. Kein Konto, keine Cloud,
keine Telemetrie, keine Updates aus dem Netz. Netzwerk nutzt nur die Aktion „HTTP-Anfrage“.

> Nicht mit Logitech/Loupedeck verbunden. Loupedeck ist eine Marke von Logitech.

> **Vibecoded:** Dieses Projekt ist mit KI-Unterstützung entstanden („vibecoded“). Der Code wurde
> von einer KI geschrieben, nach Best Practice geprüft und umgebaut und ist durch Tests abgesichert.

Weitere Dokumente: [Aktionen](docs/aktionen.md), [Befehlszeile und JSON-API](docs/cli.md).

## Voraussetzungen

- Loupedeck CT (USB-IDs 2ec2:0003 oder 2ec2:0007), KDE Plasma 6 unter Wayland.
- Systempakete: `python3-pyside6`, `python3-pyserial`, `python3-pillow`, `python3-numpy`,
  `python3-evdev`. Empfohlen: `wl-clipboard` (Texteingabe per Einfügen, sonst wird getippt).
  Fedora: `sudo dnf install python3-pyside6 python3-pyserial python3-pillow python3-numpy python3-evdev wl-clipboard`
- Je nach Aktion: `pactl` und `wpctl` (Audio, PipeWire), `qdbus`, `ddcutil` (Monitorhelligkeit), `konsole`, `spectacle`.
- Zugriff auf `/dev/ttyACM*` und `/dev/uinput` (siehe Fehlersuche).

## Installation

```
git clone https://github.com/arekown/neondeck-ct.git
cd neondeck-ct
tools/install.sh
```

Das Skript läuft ohne sudo: legt `.venv` (mit System-Paketen) an, erzeugt das Startskript
`~/.local/bin/neondeck-ct` und den Menüeintrag `~/.local/share/applications/neondeck-ct.desktop`.

### Grafiken importieren (optional)

Die Original-Loupedeck-Grafiken (Symbolbibliothek, Standardbilder) sind **nicht** enthalten
und liegen nicht im Repository. Wer sie nutzen möchte, importiert sie optional aus dem eigenen
Windows-Installer der Loupedeck-Software. Entpacke ihn (Ordner `assets-unpacked` und
`app/…/Plugins/@Generic`) und rufe auf:

```
/usr/bin/python3 tools/import_assets.py --source <Pfad zum entpackten Windows-Installer>
```

Die Dateien werden nach `~/.local/share/neondeck-ct/assets` kopiert (nur Geändertes).
Ohne Import meldet der Dienst „Grafiken fehlen“ (Diagnose, Tray-Meldung); Tasten lassen sich
trotzdem mit eigenen Bildern oder Text belegen. Zusätzlich lassen sich eigene Bilder, z. B.
CC0-Symbol- und Soundpakete, über den Tastenbild-Editor (Datei wählen) verwenden. Diese
Pakete gehören nicht zum Lieferumfang.

## Start, Autostart, Tray

- Start: `neondeck-ct` (oder Menüeintrag). Der Dienst läuft im Tray (Gerät, Aktionen,
  Fenster-/Sperr-Beobachtung). Es läuft immer nur eine Instanz.
- Tray-Menü: Einstellungen öffnen, Helligkeit (0–10), Display-Schlaf (Aus oder n min),
  „Mit Anmeldung starten“ (Autostart, schreibt `~/.config/autostart/neondeck-ct.desktop`), Beenden.
- Der Editor ist ein eigener Prozess (`neondeck-ct --config`); stürzt er ab, läuft das Gerät weiter.

## Der Editor

Themen: **Cyberpunk Cockpit** (Standard, optional mit Scanlines), **Neutral Dunkel**, **System (KDE)**,
umschaltbar im Menü, live.

- **Geräteansicht** mit allen Touch-Feldern, runden/eckigen Tasten, Reglern, Leisten und Rad.
  Darunter der Inspector, rechts die Aktionsbibliothek (Suche, Ziehen auf eine Taste).
  Siehe [Aktionen](docs/aktionen.md).
- **Bearbeiten**: Klick wählt, Strg-Klick Mehrfachauswahl, Entf löscht. Ziehen verschiebt,
  mit Strg kopiert. Strg+C/X/V/D = Kopieren, Ausschneiden, Einfügen, Duplizieren (auch ganze
  Seiten, zwischen Arbeitsbereichen). Rückgängig Strg+Z, Wiederholen Strg+Umschalt+Z oder Strg+Y
  (100 Schritte). Belegungen liegen als JSON in der Zwischenablage.
- **Tastenbild-Editor**: Layout (nur Symbol, Symbol+Text, nur Text, großer Text), Schrift
  (Noto Sans, Orbitron, Rajdhani, Share Tech Mono, Inter), Größe (auto/fest), Ausrichtung,
  Text- und Symbolfarbe, Symbol einfärben.
- **Zustände**: 2–8 je Taste mit eigenem Bild und optional eigener Aktion. Quelle: manuell,
  stumm (Standard-Audio), Medien (MPRIS), „App läuft“ oder extern (`ctl state`). Bleibt über Seitenwechsel.
- **Tippen, Doppeltippen, Halten** je Taste (Standard 300 ms bzw. 500 ms, in den Einstellungen änderbar:
  Doppeltippen 100–1000 ms, Halten 200–3000 ms).
- **Ordner**: Touch-Taste öffnet eine Ordnerseite, Zurück-Kachel automatisch, optional „Nach Aktion zurück“.
  **Sticky-Kacheln** gelten auf allen Seiten eines Arbeitsbereichs. LED-Farbe je Arbeitsbereich.
- **Anordnen …** (Kopfzeile, Menü „Profil“): Arbeitsbereiche und Seiten per Ziehen sortieren; die runden Tasten,
  die auf Arbeitsbereiche schalten, folgen der Reihenfolge. Seitenreiter lassen sich auch direkt verschieben.
- **Regler und Rad**: Drehen als eine Aktion oder links/rechts getrennt, Richtung umkehren,
  Schrittfaktor 1–10, Stapel (mehrere Ebenen, Drücken wechselt), Leistenanzeige (Name, Name+Wert, Balken).
  „Tippen auf die Leiste“ (`tap` je Regler) löst eine eigene Aktion aus; leer wirkt Tippen wie Drücken.
- **Leisten** (Kopfzeile „Leisten“, je Arbeitsbereich `strip_left`/`strip_right`): `knobs` zeigt die
  Regler, `system` vier Live-Balken – oben CPU und RAM, unten GPU 1 und GPU 2 (`nvidia-smi` im
  Hintergrund alle 2 s; ohne GPU „–“). Abgetastet wird nur, solange eine Leiste das zeigt.
  Rad: Uhr, Text, Wert-Bogen, Bild; Tippen auf die Mitte löst eine eigene Aktion aus.
- **Dynamic Mode** (Standard an): Das Profil folgt dem aktiven Fenster. Dazu lädt der Dienst ein
  KWin-Skript (`data/kwin/neondeck-ct.js`, D-Bus `io.github.arekown.NeondeckCT`); die Zuordnung
  steht im Feld „App“ des Profils (Auswahl aus installierten Programmen). Manueller Profilwechsel
  pausiert den Automatismus bis zum Wechsel auf eine andere App; „haltende“ Profile bleiben aktiv;
  sonst Rückfall auf das Standardprofil. Global oder je Profil abschaltbar.
- **Simulieren**: Klick und Drehen am Gerätebild löst über den Dienst echte Ereignisse aus
  (auch ohne Gerät). „Testen“ führt die gezeigte, noch nicht gespeicherte Aktion aus.
- **Diagnose-Seite**: Sitzung (Wayland/KDE), Gerät gefunden, Zugriff auf `/dev/ttyACM*` und
  `/dev/uinput`, `wl-copy`, KWin-Skript, D-Bus-Dienst, Firmware, Grafiken, mit grün/rot und kopierbarem
  Reparaturbefehl. Der Editor führt nie selbst sudo aus.
- **Ersteinrichtung** beim ersten Editor-Start: Diagnose, Vorlagen ankreuzen (mehrere möglich), Theme wählen.
- **Vorlage einfügen …** (Knopf in der Kopfzeile, Menü „Profil“): angekreuzte Vorlagen kommen als eigene
  Arbeitsbereiche ins gezeigte Profil, jede auf die nächste freie runde Taste; Bestehendes bleibt, Rückgängig geht.
  Mitgelieferte Vorlagen: Medien & Lautstärke, KDE Fenster & Arbeitsflächen, Entwickler, Grafik (GIMP, Inkscape,
  Blender), Gaming (Steam, Lutris, Heroic, Discord), Streaming (OBS über Tastenkürzel).
- **Versionen**: Vor jedem Speichern entsteht ein Snapshot (max. 100 je Profil, höchstens 60 Tage).
  Der Dialog „Versionen“ stellt ein Profil wieder her (vorher wird der aktuelle Stand gesichert).
- **Austausch**: Export/Import einzelner Profile als `.ndprofile` (Zip mit `profile.json` und
  eigenen Bildern; ein Import ersetzt nie ein vorhandenes Profil; ältere `.ldlprofile` lassen sich
  weiter importieren). Windows-Profile (`.lp5`) lassen
  sich importieren; nicht umsetzbare Aktionen erscheinen als „Nicht unterstützt“ mit Hinweis.

### Einstellungen

`~/.config/neondeck-ct/settings.json`, im Editor und über `settings.get/put` änderbar:
`active_profile`, `brightness` (0–10), `autostart`, `theme`, `theme_scanlines`, `language`
(`auto` = Systemsprache, `de`, `en`, `fr` …; wirkt nach Neustart von Editor und Dienst), `device_look`
(`auto`, `classic`, `cockpit`), `dynamic_mode`, `display_sleep_min` (0 = aus), `lock_with_session`, `double_ms`, `hold_ms` und die Meldungs-Schalter
`notify_errors`, `notify_connection`, `notify_profile` (Standard aus), `tray_mono`.

## Sperre und Standby

- Bildschirmsperre (`org.freedesktop.ScreenSaver`): Displays aus, Eingaben ignoriert, Entsperren
  stellt alles wieder her. Abschaltbar (`lock_with_session`).
- Display-Schlaf: nach einstellbarer Zeit ohne Eingabe schwarz (Standard aus); die erste Eingabe weckt nur.
- **Bildschirmschoner** über alle Displays, das Rad und die LEDs: Cockpit-HUD (mit echter CPU-/RAM-Anzeige),
  Synthwave, Matrix, Sternenflug, Aurora; „Passend zum Theme“ wählt selbst. Start nach einstellbarer Zeit
  ohne Eingabe am Gerät (Standard 5 min, 0 = aus), Vorschau in den Einstellungen oder `ctl screensaver`.
  Die erste Berührung beendet ihn, ohne die Aktion dahinter auszulösen; Display-Schlaf und Sperre gehen vor.
- **Geräte-Look** „Cockpit“ (Standard zum Cockpit-Theme, sonst „Klassisch“), in der Stimmung des
  Cockpit-Schoners: Raster mit Scanlines und Scan-Linie, Neonrahmen je Feld mit wanderndem Verlauf
  Cyan ↔ Magenta, Glühen und Eck-Akzenten (schwarzer Tastenhintergrund wird durchsichtig, gedrückt
  Magenta), zufällige Magenta-Pings der Rahmen, Datenstrom in leeren Feldern, Leisten mit Neon-Lauflicht,
  Tick-Ring mit Radar-Strahl am Rad, die LED des aktiven Arbeitsbereichs atmet.
  Höchstens 6 Bilder/s, nur Geändertes wird gesendet; Tasten bleiben dabei sofort bedienbar.
- Nach Standby/Ruhezustand (logind `PrepareForSleep`) verbindet der Dienst neu und sendet
  Helligkeit, LEDs und alle Displays erneut.

## Sprachen

Deutsch steht direkt im Code; jede weitere Sprache ist **eine** Datei `data/i18n/<code>.json`.
Neue Sprache: `en.json` kopieren (z. B. nach `es.json`), `_meta` anpassen, die Werte übersetzen –
fertig, die Auswahl in den Einstellungen findet die Datei selbst. Leere Werte bleiben deutsch.
Einzelheiten: [`data/i18n/README.md`](data/i18n/README.md).

## Datenorte

| Was | Ort |
|---|---|
| Einstellungen | `~/.config/neondeck-ct/settings.json` |
| Profile | `~/.config/neondeck-ct/profiles/` (Versionen in `.versionen/<id>/`) |
| Grafiken, importierte Bilder | `~/.local/share/neondeck-ct/assets`, `…/imported/<id>/` |
| Logs | `~/.local/state/neondeck-ct/log.txt` (Dienst), `editor-log.txt` (Editor); je 1 MB × 3 |
| Autostart | `~/.config/autostart/neondeck-ct.desktop` |
| API-Socket | `$XDG_RUNTIME_DIR/neondeck-ct.sock` |

## Fehlersuche

1. Editor, Seite **Diagnose** öffnen und rote Punkte abarbeiten.
2. Log lesen: `tail -n 50 ~/.local/state/neondeck-ct/log.txt`.
3. Kein Zugriff auf Gerät oder `/dev/uinput`: udev-Regel anlegen (Befehl zeigt die Diagnose):

```
# /etc/udev/rules.d/70-neondeck-ct.rules
SUBSYSTEM=="tty", ACTION=="add", ATTRS{idVendor}=="2ec2", ATTRS{idProduct}=="0003|0007", MODE="0660", TAG+="uaccess"
KERNEL=="uinput", SUBSYSTEM=="misc", ACTION=="add", TAG+="uaccess", OPTIONS+="static_node=uinput"
```

   Danach `sudo udevadm control --reload-rules && sudo udevadm trigger` und das Gerät neu einstecken.
4. Taste blinkt rot: Die Aktion ist fehlgeschlagen; Grund steht im Log und als Tray-Meldung.
5. Profil wechselt nicht mit dem Fenster: Diagnose „KWin-Skript“ prüfen, Dynamic Mode an?
6. `neondeck-ct ctl status` meldet „läuft nicht“: Dienst starten.

Bei Spielen oder Programmen, die Tastatureingaben brauchen, sendet der Dienst über `/dev/uinput`.

## Entwicklung

```
.venv/bin/pip install -e .[dev]   # pytest und ruff in die venv
.venv/bin/python -m pytest -q     # Testsuite
.venv/bin/ruff check src tests tools
```

## Lizenz

[PolyForm Noncommercial 1.0.0](LICENSE). Persönliche und andere nicht-kommerzielle Nutzung und
Veränderung sind erlaubt, kommerzielle Nutzung nicht. Der verbindliche Text steht in
[`LICENSE`](LICENSE).
