# Sprachdateien

**Neue Sprache = eine Datei.** `en.json` kopieren und nach dem Sprachcode benennen
(`es.json`, `it.json` …), in `_meta` Name und Code eintragen, dann jeden Wert übersetzen.
Die Sprachauswahl im Editor (Einstellungen → Sprache) findet die Datei von selbst; die
Sprache wirkt nach einem Neustart von Editor und Dienst.

```json
{
 "_meta": {"name": "Español", "code": "es"},
 "Profil {id!r} gibt es nicht": "El perfil {id!r} no existe"
}
```

Regeln:

- Der **Schlüssel** ist der deutsche Text aus dem Programm, genau so, wie er dort steht. Nur
  den **Wert** übersetzen.
- Platzhalter in geschweiften Klammern (`{name}`, `{id!r}`, `{n}`) bleiben in der Übersetzung
  genau gleich; ihre Reihenfolge darf sich ändern.
- Leerer Wert (`""`) oder fehlender Schlüssel: Das Programm zeigt den deutschen Text.
- Deutsch selbst braucht keine Datei.

Für Entwickler: `python3 tools/i18n.py --check` meldet fehlende und veraltete Texte aller
Sprachdateien, `python3 tools/i18n.py --update` trägt fehlende Texte mit leerem Wert ein.
Im Code: `tr("Text {name}", name=…)` übersetzt beim Anzeigen; `N_("Text")` markiert Texte,
die schon beim Import entstehen (Tabellen, Beschriftungen von Aktionen und Parametern) – die
werden erst beim Anzeigen mit `tr(wert)` übersetzt.
