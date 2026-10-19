"""Fensterliste der Aktion „Konsole-Layout“: pruefen und als Text fuer den Editor (ohne Qt,
ohne Prozesse).

Gespeichert als ``[{"title": "Lokal", "place": "top_left", "commands": ["htop"]},
{"title": "Server", "place": "top_right", "split": "vertical", "commands": ["", "ssh …"]}]``
(leerer Befehl = Shell). Mit Registern statt ``commands``: ``{"title": "SSH", "place":
"left", "tabs": [{"title": "PC1", "command": ""}, {"title": "PC2", "command": "ssh …"}]}``.
"""
from __future__ import annotations

from ..core.placement import PLACES

SPLITS = ("horizontal", "vertical")
TABS_MARK = "tabs"     # im Text: Kopfzeilenfeld fuer ein Fenster mit Registern
SHELL_MARK = "-"       # im Text: Ansicht ohne Befehl (nur Shell)


def _clean_tabs(raw: object) -> list[dict]:
    out = []
    for item in raw if isinstance(raw, list) else []:
        t = {"command": item} if isinstance(item, str) else item
        if isinstance(t, dict):
            out.append({"title": str(t.get("title") or ""), "command": str(t.get("command") or "")})
    return out


def _clean_window(item: dict) -> dict:
    tabs = _clean_tabs(item.get("tabs"))
    commands = item.get("commands")
    if isinstance(commands, str):
        commands = [commands]
    if not isinstance(commands, list) or not commands:
        commands = [""]
    win = {"title": str(item.get("title") or ""),
           "place": item.get("place") if item.get("place") in PLACES else "none"}
    if tabs:  # Register statt geteilter Ansichten
        win["tabs"] = tabs
    else:
        win["commands"] = [str(c or "") for c in commands]
        if item.get("split") == "vertical":
            win["split"] = "vertical"
    if item.get("screen"):
        win["screen"] = str(item["screen"])
    return win


def clean_windows(raw: object) -> list[dict]:
    """Gespeicherte Fensterliste pruefen und vereinheitlichen (Unbrauchbares faellt weg)."""
    return [_clean_window(item) for item in (raw if isinstance(raw, list) else [])
            if isinstance(item, dict)]


def _tab_line(tab: dict) -> str:
    if not tab["title"] and not tab["command"]:
        return SHELL_MARK
    return f"{tab['title']} > {tab['command']}" if tab["command"] else tab["title"]


def _parse_tab(text: str) -> dict:
    if text == SHELL_MARK:
        return {"title": "", "command": ""}
    if text.startswith("> "):
        return {"title": "", "command": text[2:].strip()}
    title, sep, cmd = text.partition(" > ")
    return {"title": title.strip(), "command": cmd.strip() if sep else ""}


def windows_to_text(windows: object) -> str:
    """Text fuer den Editor: je Fenster ``Titel | Platz [| vertical] [| Bildschirm]``, darunter
    eingerueckt je Ansicht ein Befehl (``-`` = nur Shell; keine Zeile = eine Shell). Fenster mit
    Registern: ``Titel | Platz | tabs [| Bildschirm]``, darunter je Register ``Titel > Befehl``
    (``Titel`` allein = nur Shell, ``-`` = leeres Register)."""
    blocks = []
    for win in clean_windows(windows):
        head = [win["title"], win["place"]]
        if win.get("tabs"):
            head.append(TABS_MARK)
        if win.get("split"):
            head.append(win["split"])
        if win.get("screen"):
            head.append(win["screen"])
        lines = [" | ".join(head)]
        if win.get("tabs"):
            lines += [f"    {_tab_line(t)}" for t in win["tabs"]]
        elif win["commands"] != [""]:
            lines += [f"    {c or SHELL_MARK}" for c in win["commands"]]
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def _head_field(win: dict, field: str) -> None:
    """Ein Feld nach dem Titel zaehlt nach Inhalt: Platz, ``tabs``, Teilung, sonst Bildschirm."""
    low = field.lower()
    if low in PLACES:
        win["place"] = low
    elif low == TABS_MARK:
        win["tabs"] = []
    elif low in SPLITS:
        if low == "vertical":
            win["split"] = low
    elif field:
        win["screen"] = field


def _parse_head(line: str) -> dict:
    title, *fields = [f.strip() for f in line.split("|")]
    win: dict = {"title": title, "place": "none", "commands": []}
    for field in fields:
        _head_field(win, field)
    return win


def _add_view(windows: list[dict], text: str) -> None:
    """Eingerueckte Zeile: Befehl einer Ansicht bzw. ein Register des letzten Fensters."""
    if not windows:
        windows.append({"title": "", "place": "none", "commands": []})
    win = windows[-1]
    if "tabs" in win:
        win["tabs"].append(_parse_tab(text))
    else:
        win["commands"].append("" if text == SHELL_MARK else text)


def windows_from_text(text: str) -> list[dict]:
    """Umkehrung von ``windows_to_text``."""
    windows: list[dict] = []
    for line in (text or "").splitlines():
        if not line.strip():
            continue
        if line[:1].isspace():
            _add_view(windows, line.strip())
        else:
            windows.append(_parse_head(line))
    for win in windows:  # ``tabs`` ohne Zeilen: ein leeres Register (= eine Shell)
        if win.get("tabs") == []:
            win.pop("tabs")
    return clean_windows(windows)
