# Befehlszeile und JSON-API

Der Dienst muss laufen (Tray). Die CLI startet weder Dienst noch Oberfläche.

```
neondeck-ct ctl <Befehl> [Argumente]
```

| Befehl | Wirkung |
|---|---|
| `status` | Zustand als JSON (verbunden, Seriennummer, Profil, Arbeitsbereich, Seite, Ordner, Theme, Dynamic Mode, gesperrt, Display schläft) |
| `page next\|prev\|<n>` | Seite wechseln (n ab 0) |
| `workspace <Name\|Kennung>` | Arbeitsbereich wechseln |
| `profile <Name\|Kennung>` | Profil aktivieren |
| `press <ref>` | Taste auslösen (Tippen), wie am Gerät inkl. Zuständen |
| `state <ref> <n>` | Zustand n (ab 0) einer Taste setzen (Quelle „extern“) |
| `image <ref> <Datei>` | Tastenbild bis zum Neustart ersetzen (nur `touch:`; Pfad wird absolut gemacht) |
| `screensaver [Variante]` | Bildschirmschoner sofort starten: `cockpit`, `synthwave`, `matrix`, `warp`, `aurora` oder `auto` (zum Theme); ohne Angabe die eingestellte |

Namen sind eindeutig und ohne Beachtung der Groß-/Kleinschreibung; mehrdeutig führt zum Fehler.

## Ref-Format

`touch:0-11`, `round:0-7`, `square:0-11`, `knob:0-5`, `strip:0-5` oder `wheel` (ohne Index).
Index ab 0. Touch-Felder zeilenweise 4 × 3.

## Ausgabe und Exit-Codes

- Erfolg: Ergebnis als JSON auf stdout, Exit-Code `0`.
- Jeder Fehler (falscher Aufruf, ungültiges Ref, Dienst nicht erreichbar, Fehler vom Dienst):
  Text auf stderr, Exit-Code `1`. Verbindungs-Timeout 2 s, Antwort-Timeout 5 s.

## Beispiele

```
neondeck-ct ctl status
neondeck-ct ctl page next
neondeck-ct ctl workspace Medien
neondeck-ct ctl press touch:3
neondeck-ct ctl state touch:5 1
neondeck-ct ctl image touch:0 ~/Bilder/build-ok.png
neondeck-ct ctl screensaver synthwave
neondeck-ct ctl status | jq -r .profile_name
```

## JSON-API für Skripte

Lokaler Unix-Socket `$XDG_RUNTIME_DIR/neondeck-ct.sock` (ohne Laufzeitordner: Name `neondeck-ct`).
Eine UTF-8-JSON-Zeile je Nachricht (max. 16 MB):

```
-> {"id": 1, "method": "page", "params": {"dir": "next"}}
<- {"id": 1, "result": {...}}        oder   {"id": 1, "error": "Text"}
<- {"event": "view.changed", "data": {...}}   (nur nach "subscribe")
```

Beispiel: `echo '{"id":1,"method":"status"}' | socat - UNIX-CONNECT:$XDG_RUNTIME_DIR/neondeck-ct.sock`

### Methoden

| Methode | Parameter | Ergebnis |
|---|---|---|
| `ping` | – | `"pong"` |
| `status` | – | wie `ctl status` |
| `subscribe` | `role` (optional) | Ereignisse abonnieren |
| `open_config` | – | Editor öffnen |
| `profile.list` | – | `[{id, name, active, ok}]` |
| `profile.get` | `id` | Profil-JSON |
| `profile.put` | `profile` | prüft, zeigt (wenn aktiv), sichert Snapshot, speichert |
| `profile.activate` | `id` | Profil wechseln |
| `profile.create` / `profile.delete` | `name` bzw. `id` | anlegen / löschen |
| `versions.list` / `.get` / `.restore` | `id` (+ Version) | Versionen eines Profils |
| `view.get` | – | Profil, Arbeitsbereich, Seite, Seitenzahl, Ordner, `workspaces` |
| `view.set` | `workspace`, `page` | Ansicht setzen |
| `page` | `dir` (`next`/`prev`) oder `index` | blättern |
| `trigger` | `ref`, `which` (tap, double, hold, rotate), `steps`, `action` (optional, ungespeichert testen) | Taste/Regler auslösen |
| `simulate` | `event`: `{type: button\|rotate\|touch\|wheel_touch, …Felder}` | Geräteereignis einspeisen |
| `state.set` | `ref`, `n` | Zustand setzen |
| `image.set` | `ref`, `path` (leer = aufheben) | Bild überschreiben |
| `diag` | – | `{service, checks[]}` wie die Diagnose-Seite |
| `settings.get` / `settings.put` | Schlüssel/Werte | Einstellungen lesen, prüfen und setzen |

### Ereignisse

| Ereignis | Daten |
|---|---|
| `view.changed` | wie `view.get` |
| `device.state` | `{connected, serial, …}` |
| `profile.changed` | `{id, active}` |
| `value` | `{ref, text}` (z. B. Lautstärke nach Drehen) |
| `window.active` | `{resource_class, desktop_file, caption, pid}` |
| `raise` | Editor soll sich in den Vordergrund holen |
