"""Aktionen: Makros (verschachtelte Schrittlisten), Warten, Regler-Makro, „nicht unterstuetzt“."""
from __future__ import annotations

import contextvars
import time

from ..core.i18n import N_, tr
from .base import Param, Result, execute, register

MAX_DEPTH = 5
SLEEP_MIN_MS, SLEEP_MAX_MS = 10, 10000
_depth: contextvars.ContextVar[int] = contextvars.ContextVar("macro_depth", default=0)


def run_steps(steps: list[dict], ctx) -> Result:
    """Schritte der Reihe nach ausfuehren; beim ersten Fehler Schluss („Schritt n: …“)."""
    depth = _depth.get()
    if depth >= MAX_DEPTH:
        return Result(False, tr("Makro zu tief verschachtelt (max. {depth})", depth=MAX_DEPTH))
    token = _depth.set(depth + 1)
    try:
        for n, step in enumerate(steps, 1):
            res = execute(step, ctx)
            if not res.ok:
                return Result(False, tr("Schritt {n}: {message}", n=n, message=res.message))
    finally:
        _depth.reset(token)
    return Result(True)


@register("macro", label=N_("Makro"), category="macros", params=[Param("steps", N_("Schritte"), "steps")])
def macro(action, ctx, **_):
    return run_steps(action.get("steps") or [], ctx)


@register("sleep", label=N_("Warten"), category="macros", params=[Param("ms", N_("Millisekunden"), "int", 100)])
def sleep(action, ctx, **_):
    try:
        ms = int(action.get("ms", 100))
    except (TypeError, ValueError):
        return Result(False, tr("Ungültige Wartezeit"))
    time.sleep(max(SLEEP_MIN_MS, min(SLEEP_MAX_MS, ms)) / 1000)
    return Result(True)


@register("adjust_macro", label=N_("Regler-Makro"), category="macros", params=[
    Param("left", N_("Links drehen"), "steps"), Param("right", N_("Rechts drehen"), "steps"),
    Param("reset", N_("Drücken"), "steps")], kinds={"rotate", "press"})
def adjust_macro(action, ctx, *, steps=0, pressed=True, **_):
    """Drehen: steps>0 fuehrt ``right`` |steps|-mal aus, steps<0 ``left``. Druecken
    (steps == 0, pressed=True) fuehrt ``reset`` aus. Die Engine ruft es fuer beides."""
    if steps:
        lst = action.get("right" if steps > 0 else "left") or []
        for _i in range(abs(steps)):
            res = run_steps(lst, ctx)
            if not res.ok:
                return res
        return Result(True)
    if pressed:
        return run_steps(action.get("reset") or [], ctx)
    return Result(True)


@register("unsupported", label=N_("Nicht unterstützt"), category="macros")
def unsupported(action, ctx, **_):
    return Result(False, tr("Noch nicht umgesetzt: {original}", original=action.get("original", "")))
