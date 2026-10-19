"""Bausteine der Vorlagen: Tasten, Regler, Rad und ``template`` (baut das Profil-JSON).

Tastenkuerzel schreibt man so, wie sie auf der Tastatur stehen: ``combo("Strg+Umschalt+Z")``,
``combo("Ctrl+[")``. ``combo`` rechnet sie fuer das **deutsche** Layout in evdev-Tasten um
(evdev nennt Tastenpositionen: Strg+Z liegt auf ``KEY_Y``, ``[`` ist AltGr+8 usw.).
"""
from __future__ import annotations

from neondeck.core.keymap import CHAR_MAP, MODIFIER_KEYS, NAMED_KEYS
from neondeck.device.layout import ENCODERS, TOUCH_BUTTONS
from neondeck.profile.model import FORMAT_VERSION

MAX_LABEL = 10  # Zeichen je Tastenbeschriftung (Kacheln sind 90 px breit)


def _split_combo(text: str) -> tuple[list[str], str]:
    """``"Strg+Umschalt+Z"`` -> (Modifikatoren, Taste): kuerzeste Modifikator-Kette, der Rest
    ist die Taste (ein Zeichen oder ein Name aus ``NAMED_KEYS``)."""
    tokens = [t.strip() for t in text.split("+")]
    for i in range(len(tokens)):
        mods, key = tokens[:i], "+".join(tokens[i:])
        if all(m.lower() in MODIFIER_KEYS for m in mods) and \
                (key.lower() in NAMED_KEYS or len(key) == 1):
            return mods, key
    raise ValueError(f"{text}: keine Taste erkannt")


def _main_key(text: str, key: str, out: list[str]) -> str:
    """evdev-Taste zu ``key``; Umschalt/AltGr, die das deutsche Layout dazu braucht, kommen
    in ``out``."""
    if key.lower() in NAMED_KEYS:
        return NAMED_KEYS[key.lower()]
    ch = key.lower() if len(key) == 1 and key.isalpha() else key
    if ch not in CHAR_MAP:
        raise ValueError(f"{text}: Taste {key!r} gibt es auf dem deutschen Layout nicht")
    main, shift, altgr = CHAR_MAP[ch]
    if shift and "KEY_LEFTSHIFT" not in out:
        out.append("KEY_LEFTSHIFT")
    if altgr and "KEY_RIGHTALT" not in out:
        out.append("KEY_RIGHTALT")
    return main


def combo(text: str) -> str:
    """``"Strg+Umschalt+Z"`` → ``"KEY_LEFTCTRL+KEY_LEFTSHIFT+KEY_Y"`` (deutsches Layout).

    Das letzte Glied ist die Taste, davor stehen Modifikatoren. Ein Zeichen, das auf dem
    deutschen Layout Umschalt oder AltGr braucht (``+`` ist eine eigene Taste, ``*`` Umschalt +
    ``+``, ``[`` AltGr + 8), bringt diese mit. Buchstaben sind unabhaengig von der
    Schreibweise: ``Strg+z`` = ``Strg+Z``."""
    mods, key = _split_combo(text)
    out = [MODIFIER_KEYS[m.lower()] for m in mods]
    main = _main_key(text, key, out)
    return "+".join(dict.fromkeys([*out, main]))


def image(text: str, icon: str | None = None, bg: str = "#000000") -> dict:
    return {"bg": bg, "icon": f"svg:icons/{icon}.svg" if icon else None, "text": text,
            "layout": "icon_text" if icon else "text"}


def btn(action: dict, text: str, icon: str | None = None) -> dict:
    return {"action": action, "image": image(text, icon)}


def hk(keys: str, text: str, icon: str | None = None) -> dict:
    """Taste mit Kuerzel in Tastatur-Schreibweise (siehe ``combo``)."""
    return btn(hotkey(keys), text, icon)


def hotkey(keys: str) -> dict:
    return {"type": "hotkey", "keys": combo(keys)}


def app(app_id: str, text: str, icon: str = "OpenApp") -> dict:
    """App fokussieren oder starten (Desktop-ID ohne ``.desktop``)."""
    return btn({"type": "app_focus", "app_id": app_id}, text, icon)


def run(command: str, text: str, icon: str | None = None) -> dict:
    return btn({"type": "run", "command": command}, text, icon)


def term(command: str, text: str, icon: str | None = None, hold: bool = True) -> dict:
    """Befehl in einer Konsole (bleibt offen, wenn ``hold``)."""
    return btn({"type": "command", "command": command, "terminal": True, "hold": hold},
               text, icon)


def typed(text_to_type: str, label: str, icon: str | None = None, mode: str | None = None
          ) -> dict:
    """Text eingeben; ``mode="type"`` tippt Zeichen fuer Zeichen (``\\n`` wird Enter),
    sonst fuegt die App den Text ueber die Zwischenablage ein."""
    action = {"type": "text", "text": text_to_type}
    if mode:
        action["mode"] = mode
    return btn(action, label, icon)


def cad(command: str, label: str, icon: str | None = None) -> dict:
    """CAD-Befehlszeile: Befehl/Alias tippen und mit Enter abschicken."""
    return typed(command + "\n", label, icon, mode="type")


def ks(name: str, text: str, icon: str | None = None, component: str = "kwin") -> dict:
    """Globales KDE-Kuerzel ueber kglobalaccel ausloesen (unabhaengig von der Tastenbelegung)."""
    return btn(ks_action(name, component), text, icon)


def ks_action(name: str, component: str = "kwin") -> dict:
    return {"type": "kde_shortcut", "component": component, "name": name}


def hold(keys: str, text: str, icon: str | None = None) -> dict:
    """Taste halten, solange das Feld gedrueckt ist (z. B. Push-to-Talk)."""
    return btn({"type": "hold_key", "keys": combo(keys)}, text, icon)


def http_action(url: str, method: str = "POST") -> dict:
    return {"type": "http", "method": method, "url": url}


def http(url: str, text: str, icon: str | None = None, method: str = "POST") -> dict:
    """Webhook/HTTP-Anfrage."""
    return btn(http_action(url, method), text, icon)


def kde(name: str, text: str, icon: str | None = None) -> dict:
    return btn({"type": "kde", "name": name}, text, icon)


def enc(label: str = "", left: str | dict | None = None, right: str | dict | None = None, *,
        rotate: dict | None = None, press: str | dict | None = None,
        strip: str = "name_value") -> dict:
    """Drehregler; ``left``/``right``/``press`` als Kuerzel-Text oder als Aktion."""
    def act(a):
        return hotkey(a) if isinstance(a, str) else a
    return {"label": label, "rotate": rotate, "press": act(press), "left": act(left),
            "right": act(right), "strip": strip}


VOLUME = enc("Lautstärke", rotate={"type": "volume"}, press={"type": "mute_toggle"},
             strip="bar")


def wheel(label: str = "", left: str | dict | None = None, right: str | dict | None = None, *,
          rotate: dict | None = None, tap: dict | None = None, display: str = "label") -> dict:
    """Rad; left/right als Kuerzel-Text oder als Aktion."""
    w = {"display": display, "label": label}
    if rotate:
        w["rotate"] = rotate
    if left:
        w["left"] = hotkey(left) if isinstance(left, str) else left
    if right:
        w["right"] = hotkey(right) if isinstance(right, str) else right
    if tap:
        w["tap"] = tap
    return w


def template(tid: str, name: str, description: str, pages: list[tuple[str, list]],
             encoders: list[dict], wheel_def: dict, led: str, ws_name: str | None = None
             ) -> dict:
    """Vorlage mit einem Arbeitsbereich; ``pages`` = [(Seitenname, bis zu 12 Tasten)]."""
    if len(encoders) > ENCODERS:
        raise ValueError(f"{tid}: mehr als {ENCODERS} Regler")
    touch_pages = []
    for n, (page_name, buttons) in enumerate(pages, 1):
        if len(buttons) > TOUCH_BUTTONS:
            raise ValueError(f"{tid}/{page_name}: {len(buttons)} Tasten (hoechstens {TOUCH_BUTTONS})")
        for b in buttons:  # Kacheln sind 90 px breit
            if len(b["image"]["text"]) > MAX_LABEL:
                raise ValueError(f"{tid}/{page_name}: Beschriftung {b['image']['text']!r} "
                                 f"laenger als {MAX_LABEL} Zeichen")
        touch_pages.append({"id": f"p{n}", "name": page_name,
                            "buttons": buttons + [None] * (TOUCH_BUTTONS - len(buttons))})
    return {"version": FORMAT_VERSION, "id": tid, "name": name, "description": description,
            "app_ids": [], "dynamic": True, "hold_profile": False, "round": {}, "square": {},
            "workspaces": [{"id": "ws1", "name": ws_name or name.split(" (")[0],
                            "touch_pages": touch_pages,
                            "encoders": encoders + [enc()] * (ENCODERS - len(encoders)),
                            "wheel": wheel_def, "led_color": led}],
            "home_workspace": "ws1"}


# --- Gemeinsame Kacheln und Regler -----------------------------------------------------------

def undo() -> dict:
    return hk("Strg+Z", "Rückg.", "Undo")


def redo(keys: str = "Strg+Umschalt+Z") -> dict:
    return hk(keys, "Wiederh.", "Redo")


def save() -> dict:
    return hk("Strg+S", "Speichern", "OpenFile")


def save_as(keys: str = "Strg+Umschalt+S") -> dict:
    return hk(keys, "Speich. u.", "OpenFile")


def copy() -> dict:
    return hk("Strg+C", "Kopieren", "Copy")


def paste() -> dict:
    return hk("Strg+V", "Einfügen", "Paste")


def cut() -> dict:
    return hk("Strg+X", "Aussch.", "Cut")


def history(redo_keys: str = "Strg+Umschalt+Z") -> dict:
    return enc("Verlauf", "Strg+Z", redo_keys)


def zoom(press: str | None = "Strg+0") -> dict:
    """Zoom der Craft-Apps: Strg+- / Strg+= (``=`` ist auf Deutsch Umschalt+0)."""
    return enc("Zoom", "Strg+-", "Strg+=", press=press)


def craft_id(name: str) -> str:
    return f"ai.storyteller.{name}"
