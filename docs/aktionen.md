# Aktionen

Auswahl in der Aktionsbibliothek des Editors. Fehlgeschlagene Aktionen lassen die Taste rot
blinken und stehen im Log. Aktionen laufen nie im Geräte-Thread. Tastenvorgaben sind
Kombinationen wie `ctrl+shift+t` (Aufnahme per Tastendruck im Editor).
„Dreh“ = nur für Regler/Rad (jeder Drehschritt), „Taste“ = nur für Tasten.

## Tastatur
| Typ (`type`) | Label | Parameter | Wirkung unter Linux |
|---|---|---|---|
| `hotkey` | Tastenkürzel | `keys` | Kombination über `/dev/uinput` (virtuelle Tastatur) tippen |
| `hold_key` | Taste halten | `keys` | gedrückt halten, solange die Taste gedrückt ist |
| `text` | Text eingeben | `text`, `mode` (auto/paste/type) | auto: per `wl-copy` einfügen, sonst Zeichen tippen |
| `adjust_hotkey` | Tastenkürzel je Drehschritt | `left`, `right` | Dreh: Kürzel je Schritt |
| `scroll` | Scrollen / Zoomen je Drehschritt | `direction` (vertical/horizontal), `lines` (Rastungen je Drehschritt, 1), `keys` (dabei halten, z. B. `KEY_LEFTCTRL` = Zoom), `invert` | Dreh: Mausrad über eine eigene virtuelle uinput-Maus; rechts drehen = nach unten/rechts |

## Programme
| Typ | Label | Parameter | Wirkung |
|---|---|---|---|
| `run` | Programm starten | `command`, `workdir`, `screen`, `place` | startet ohne Shell (Argumente wie `shlex`); `screen`/`place` siehe unten |
| `open` | Öffnen | `target` | Datei, Ordner oder URL via `xdg-open` |
| `command` | Befehl ausführen | `command`, `terminal` (an), `hold`, `workdir`, `title` | Befehl in Konsole (oder ohne Terminal); `title` = fester Fenster-/Tabtitel (`konsole -p tabtitle=…`, auch bei ssh) |
| `app_focus` | App fokussieren oder starten | `app_id` (Desktop-ID), `screen`, `place` | holt laufendes Fenster per KWin nach vorn, sonst Start über `.desktop` (dann mit Platzierung) |
| `terminal_layout` | Konsole-Layout | `screen`, `windows` | mehrere Konsole-Fenster nacheinander, je mit Titel, Platz und einer oder mehreren geteilten Ansichten (je Ansicht ein Befehl) |
| `http` | HTTP-Anfrage | `method` (GET/POST/PUT…), `url`, `headers`, `body` | nur http/https, 5 s Limit; Antwortstatus als Leistenwert |

### Fenster platzieren (`run`, `app_focus`, `terminal_layout`)

`screen`: Ausgangsname (`DP-3`, wie `kscreen-doctor -o`) oder Lage `left`/`center`/`right`/`top`/`bottom`
(auch `links`/`mitte`/`rechts`/`oben`/`unten`, nach den Bildschirm-Mitten; bei Gleichstand gewinnt
der untere bzw. der waagerecht mittigste). Leer = Bildschirm, den KWin wählt.
`place`: `none` (Größe behalten), `maximize`, `left`/`right`/`top`/`bottom` (Hälften),
`top_left`/`top_right`/`bottom_left`/`bottom_right` (Viertel) – jeweils der Arbeitsfläche ohne Leisten.
Der Dienst merkt sich „nächstes Fenster von App X → Ziel“ (15 s); das KWin-Skript fragt bei jedem
neuen Fenster nach (`placement`) und setzt es. Passt über Desktop-ID/Fensterklasse (`konsole` passt
auf `org.kde.konsole`) oder die Prozessnummer des Starts; bei Apps mit Startfenster (z. B. Steam)
trifft es das erste Fenster.

### Konsole-Layout (`terminal_layout`)

```json
{"type": "terminal_layout", "screen": "DP-3", "windows": [
  {"title": "Lokal", "place": "top_left", "commands": ["htop"]},
  {"title": "Server", "place": "top_right", "split": "vertical", "screen": "DP-2",
   "commands": ["", "ssh 192.0.2.10", "ssh 192.0.2.11"]}]}
```

Je Fenster `konsole --separate --layout <json>`; leerer Befehl = nur Shell, Befehle werden in die
Shell getippt (nach `exit` von ssh bleibt die lokale Shell). `split`: `horizontal` (nebeneinander,
Vorgabe) oder `vertical` (untereinander). Der Titel kommt über Konsoles D-Bus
(`setTabTitleFormat`). Im Editor als Text: `Titel | Platz [| vertical] [| Bildschirm]`, darunter
eingerückt je Ansicht ein Befehl (`-` = Shell).

**Register (Tabs)** statt geteilter Ansichten: je Fenster `tabs` statt `commands`/`split`
(`tabs` hat Vorrang):

```json
{"type": "terminal_layout", "windows": [{"title": "SSH", "place": "left", "tabs": [
  {"title": "PC1", "command": ""},
  {"title": "PC2", "command": "ssh user@server1"},
  {"title": "PC3", "command": "ssh user@server2"}]}]}
```

Weg: `konsole --separate --tabs-from-file <datei>` (Zeile `title: …;; command: …`), die Register-Titel
bleiben stehen. Befehle laufen als `<befehl>; exec "$SHELL"`: nach Ende von `ssh` bleibt die Shell
offen. Konsole 26.08.1 hängt immer ein Standard-Register an und lässt sich über D-Bus keines
schließen; darum steht das letzte Register per `-e` auf der Befehlszeile und sein Titel kommt über
D-Bus. Das erste Register wird nach vorn geholt. Leerer Titel nimmt den Fenstertitel. Im Editor:
`Titel | Platz | tabs [| Bildschirm]`, darunter je Register `Titel > Befehl` (`Titel` allein =
Shell, `-` = leeres Register).

## Medien
| Typ | Label | Parameter | Wirkung |
|---|---|---|---|
| `volume` | Lautstärke | – | Dreh: Standard-Ausgang ±2 % je Schritt (`wpctl`, max. 100 %) |
| `mute_toggle` | Stummschalten | – | Standard-Ausgang stumm umschalten |
| `mic_mute` | Mikrofon stumm | – | Standard-Eingang umschalten (`pactl`) |
| `audio_output_next` | Audioausgang wechseln | – | nächster Ausgang im Kreis wird Standard |
| `stream_volume` | Lautstärke einer Anwendung | `index` (Stream) | Dreh: ±2 % je Schritt für einen Wiedergabestream |
| `stream_mute` | Anwendung stumm | `index` | Stream stumm umschalten |
| `media` | Medientaste | `key` (play_pause, next, previous, stop, loop) | Medientaste senden; `loop`: Wiederholen über MPRIS `LoopStatus` (None → Playlist → Track → None) beim spielenden bzw. zuletzt spielenden Player |
| `brightness` | Helligkeit | – | Dreh: Monitor ±5 % je Schritt (`ddcutil`) |
| `brightness_reset` | Helligkeit zurücksetzen | – | Monitor auf 70 % |

## System (KDE)
| Typ | Label | Parameter | Wirkung |
|---|---|---|---|
| `kde` | KDE-Funktion | `name`: lock, screenshot, screenshot_window, search, files, emoji, overview, show_desktop, desktop_next, desktop_previous, window_switcher, desktop_add, desktop_remove | Sperren (`loginctl`), Spectacle (Bereich `-r` bzw. aktives Fenster `-a -b -n`), KRunner, Dolphin, Emojier, globale KWin-Kürzel, Arbeitsflächen anlegen/entfernen |
| `kde_adjust` | KDE-Funktion je Drehschritt | `left`, `right` (wie oben) | Dreh: Funktion je Schritt, z. B. Arbeitsfläche wechseln |
| `kde_shortcut` | KDE-Kürzel auslösen | `component` (z. B. kwin), `name` | beliebiges globales Kürzel über kglobalaccel/D-Bus |

## Navigation
| Typ | Label | Parameter | Wirkung |
|---|---|---|---|
| `workspace` | Arbeitsbereich | `id` | Arbeitsbereich wechseln |
| `page_next` / `page_previous` | Nächste / Vorherige Seite | – | blättern |
| `page` | Seite | `index` (ab 0) | zu Seite springen |
| `profile` | Profil | `id` | Profil aktivieren |
| `open_config` | Konfiguration öffnen | – | Editor öffnen |
| `folder` | Ordner öffnen | `page`, `auto_exit` | Ordnerseite öffnen, optional nach der nächsten Aktion zurück |
| `folder_back` | Ordner: Zurück | – | eine Ebene zurück |
| `dynamic_folder` | Dynamischer Ordner | `kind` (windows, mixer) | Fensterliste (KWin) bzw. Lautstärke je Anwendung |

## Makros
| Typ | Label | Parameter | Wirkung |
|---|---|---|---|
| `macro` | Makro | `steps` | Schritte nacheinander; bei Fehler Abbruch. Editor-Modus „Text“: `hotkey ctrl+c`, `text …`, `wait 200`, `run …`, `open …`, `command …`, `key down/up …` |
| `sleep` | Warten | `ms` | Pause (begrenzt) |
| `adjust_macro` | Regler-Makro | `left`, `right`, `reset` | Dreh: Schritte links/rechts je Drehschritt; Drücken: `reset` |
| `unsupported` | Nicht unterstützt | – | Platzhalter für nicht umsetzbare Windows-Aktionen; meldet den Originalnamen als Fehler |

## Anzeige
| Typ | Label | Parameter | Wirkung |
|---|---|---|---|
| `clock` | Uhr | – | zeigt Uhrzeit und Datum, aktualisiert sich selbst |
| `date` | Datum | `format` (date, week) | Datum bzw. Kalenderwoche |
| `stopwatch` | Stoppuhr | – | Tippen startet/stoppt, Halten (> 1 s) setzt zurück |
