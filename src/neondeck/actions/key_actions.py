"""Aktionen: Tastenkuerzel, gehaltene Taste, Texteingabe, Kuerzel je Drehschritt."""
from __future__ import annotations

import shutil
import time

from ..core import proc
from ..core.i18n import N_, tr
from .base import ActionContext, Param, Result, keyboard_of, register

PASTE_DELAY = 0.05  # der Compositor soll die neue Zwischenablage vor Strg+V sehen
WL_COPY_TIMEOUT = 2


@register("hotkey", label=N_("Tastenkürzel"), category="input",
          params=[Param("keys", N_("Tasten"), "keys")], kinds={"press"})
def hotkey(action, ctx, **_):
    keyboard_of(ctx).tap(action.get("keys", ""))


@register("hold_key", label=N_("Taste halten"), category="input",
          params=[Param("keys", N_("Tasten"), "keys")], kinds={"press"}, on_release=True)
def hold_key(action, ctx, *, pressed=True, **_):
    kb = keyboard_of(ctx)
    if pressed and not action.get("release"):  # "release": Makroschritt „Taste los“
        kb.press(action.get("keys", ""))
    else:
        kb.release(action.get("keys", ""))


def _paste(value: str, ctx: ActionContext) -> Result:
    # wl-copy startet ein Kind, das die Zwischenablage weiter bedient und unsere Ein-/Ausgaben
    # erbt: mitgeschnittene Pipes kaemen nie ans Ende, darum DEVNULL; die Zeitgrenze gilt nur
    # dem (sofort endenden) Elternprozess.
    try:
        done = ctx.run([proc.WL_COPY, "--", value], stdin=proc.DEVNULL,
                       stdout=proc.DEVNULL, stderr=proc.DEVNULL, timeout=WL_COPY_TIMEOUT)
    except FileNotFoundError:
        return Result(False, tr("Programm nicht gefunden: {program}", program="wl-copy"))
    except proc.TimeoutExpired:
        return Result(False, tr("wl-copy reagiert nicht"))
    if done.returncode:
        return Result(False, tr("wl-copy endete mit Exit-Code {code}", code=done.returncode))
    time.sleep(PASTE_DELAY)
    keyboard_of(ctx).tap("KEY_LEFTCTRL+KEY_V")
    return Result(True)


@register("text", label=N_("Text eingeben"), category="input", params=[
    Param("text", N_("Text"), "text"),
    Param("mode", N_("Art"), "choice", "auto", ["auto", "paste", "type"])])
def text_input(action, ctx, **_):
    value = action.get("text", "")
    mode = action.get("mode", "auto")
    if mode == "auto":
        mode = "paste" if shutil.which("wl-copy") else "type"
    if mode == "paste":
        return _paste(value, ctx)
    if mode == "type":
        keyboard_of(ctx).type_text(value)
        return Result(True)
    return Result(False, tr("Unbekannte Art der Texteingabe: {mode}", mode=mode))


@register("adjust_hotkey", label=N_("Tastenkürzel je Drehschritt"), category="input", params=[
    Param("left", N_("Links drehen"), "keys"), Param("right", N_("Rechts drehen"), "keys")],
    kinds={"rotate"})
def adjust_hotkey(action, ctx, *, steps=0, **_):
    if not steps:
        return Result(True)
    combo = action.get("left" if steps < 0 else "right", "")
    kb = keyboard_of(ctx)
    for _ in range(abs(steps)):
        kb.tap(combo)
    return None
