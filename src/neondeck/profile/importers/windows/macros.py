"""Windows-Makros, Regler-Makros und Profilaktionen -> Aktionen (``macro``, ``adjust_macro``)."""
from __future__ import annotations

from ....core.i18n import tr
from ...action_types import ActionType
from .context import ActionSource, Context, display, nocase, split, unsupported_action
from .keys import keyboard_combo

KEYBOARD_TEMPLATE = "$@generic___@keyboardkey"


def template_action(ctx: Context, template: str | None, params: dict | None, original: str,
                    where: str) -> dict:
    """Aktion einer Vorlage (heute nur Tastendruck)."""
    if (template or "").lower() == KEYBOARD_TEMPLATE:
        keys = keyboard_combo(nocase(params).get("keyboardkey"))
        if keys:
            return {"type": ActionType.HOTKEY, "keys": keys}
        return ctx.unsupported(original, where, tr("unbekannte Taste"))
    return ctx.unsupported(original, where, tr("Vorlage {name}", name=template))


def profile_action(ctx: Context, guid: str, original: str, where: str) -> dict:
    pa = ctx.profile_actions.get(guid.lower())
    if pa is None:
        return ctx.unsupported(original, where, tr("Profilaktion fehlt"))
    ap = pa.get("actionParameters") or {}
    if pa.get("isMultiState") or ap.get("count", 1) != 1:
        return ctx.unsupported(original, where, tr("mehrstufig/wiederholt"))
    return template_action(ctx, pa.get("templateActionName"), ap.get("parameters"),
                           original, where)


def _editor_commands(macro: dict) -> dict[str, dict]:
    return {c.get("name", "").lower(): c for c in macro.get("actionEditorCommands") or []}


class _ConsoleScan:
    """Erkennt Win+R -> ``cmd`` [-> Befehl]; ``feed`` liefert False, wenn es etwas anderes ist."""

    def __init__(self, cmds: dict[str, dict]):
        self.cmds = cmds
        self.run_dialog = self.opened = False
        self.typed: list[str] = []

    def feed(self, entry: str) -> bool:
        c = self.cmds.get(entry.lower())
        if c is not None:
            keys = keyboard_combo(nocase(c.get("actionParameters")).get("keyboardkey"))
            if keys == "KEY_LEFTMETA+KEY_R":
                self.run_dialog = True
                return True
            return keys == "KEY_ENTER"
        plugin, name, param = split(entry)
        if plugin != "@generic":
            return False
        if name.lower() == "@sleep":
            return True
        return name.lower() == "@typetext" and self._text(param)

    def _text(self, param: str) -> bool:
        if self.run_dialog and not self.opened and param.strip().lower() == "cmd":
            self.opened = True
        elif self.opened:
            self.typed.append(param.strip())
        else:
            return False
        return True


def _console_macro(ctx: Context, entries: list[str], cmds: dict[str, dict], original: str,
                   where: str) -> dict | None:
    """Erkennt Win+R -> ``cmd`` [-> Befehl] und bildet es auf eine Konsole ab."""
    scan = _ConsoleScan(cmds)
    if not all(scan.feed(e) for e in entries) or not scan.opened:
        return None
    if not scan.typed:
        return {"type": ActionType.COMMAND, "command": "", "terminal": True}
    if scan.typed == ["ipconfig"]:
        return {"type": ActionType.COMMAND, "command": "ip -c a", "terminal": True,
                "hold": True}
    return ctx.unsupported(original, where, tr("Windows-Befehl {name}", name=" / ".join(scan.typed)))


def _entry(mapper: ActionSource, entry: str, cmds: dict[str, dict], where: str) -> dict | None:
    c = cmds.get(entry.lower())
    if c is not None:
        return template_action(mapper.ctx, c.get("templateName"), c.get("actionParameters"),
                               entry, where)
    return mapper.action(entry, where)


def macro(mapper: ActionSource, guid: str, original: str, where: str) -> dict | None:
    ctx = mapper.ctx
    m = ctx.macros.get(guid.lower())
    if m is None:
        return ctx.unsupported(original, where, tr("Makro fehlt"))
    where_m = tr("{where}, Makro „{name}“", where=where, name=display(m))
    cmds = _editor_commands(m)
    entries = [e for e in m.get("actions") or [] if e]
    console = _console_macro(ctx, entries, cmds, original, where_m)
    if console is not None:
        return console
    steps: list[dict] = []
    for e in entries:
        step = _entry(mapper, e, cmds, where_m)
        if step is None:
            continue
        if step["type"] == ActionType.UNSUPPORTED:
            return unsupported_action(original)
        # Windows-Makros starten dasselbe Programm oft ueber alternative Pfade.
        if step["type"] in (ActionType.RUN, ActionType.OPEN) and step in steps:
            continue
        steps.append(step)
    if not steps:
        return None
    return steps[0] if len(steps) == 1 else {"type": ActionType.MACRO, "steps": steps}


def adjustment(mapper: ActionSource, guid: str, original: str, where: str) -> dict:
    ctx = mapper.ctx
    a = ctx.adjustments.get(guid.lower())
    if a is None:
        return ctx.unsupported(original, where, tr("Regler-Makro fehlt"))
    where_a = tr("{where}, Regler-Makro „{name}“", where=where, name=display(a))
    if any(a.get("actionsBefore") or []):
        return ctx.unsupported(original, where_a, tr("Vorab-Aktionen"))
    cmds = _editor_commands(a)
    lists: dict[str, list[dict]] = {}
    for key, src in (("left", "actionsLeft"), ("right", "actionsRight"),
                     ("reset", "actionsReset")):
        steps = []
        for e in a.get(src) or []:
            step = _entry(mapper, e, cmds, where_a) if e else None
            if step is None:
                continue
            if step["type"] == ActionType.UNSUPPORTED:
                return unsupported_action(original)
            steps.append(step)
        lists[key] = steps
    left, right = lists["left"], lists["right"]
    if (not lists["reset"] and len(left) == 1 and len(right) == 1
            and left[0]["type"] == ActionType.KDE and right[0]["type"] == ActionType.KDE):
        return {"type": ActionType.KDE_ADJUST, "left": left[0]["name"], "right": right[0]["name"]}
    return {"type": ActionType.ADJUST_MACRO, **lists}
