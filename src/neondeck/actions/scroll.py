"""Aktion: Scrollen bzw. Zoomen je Drehschritt (Mausrad der virtuellen Maus, ``mouse``)."""
from __future__ import annotations

import time

from ..core.i18n import N_
from .base import Param, Result, keyboard_of, mouse_of, register

MODIFIER_DELAY = 0.01  # Modifikator vor dem ersten Radereignis beim Compositor ankommen lassen


@register("scroll", label=N_("Scrollen / Zoomen je Drehschritt"), category="input", params=[
    Param("direction", N_("Richtung"), "choice", "vertical", ["vertical", "horizontal"]),
    Param("lines", N_("Rastungen je Drehschritt"), "int", 1),
    Param("keys", N_("Dabei halten (Strg = Zoom)"), "keys"),
    Param("invert", N_("Richtung umkehren"), "bool", False)], kinds={"rotate"})
def scroll(action, ctx, *, steps=0, **_):
    """Mausrad per Regler/Rad: rechts drehen = nach unten bzw. rechts scrollen (``invert``
    kehrt um); mit ``keys`` (z. B. ``KEY_LEFTCTRL``) gehalten = Zoom in den meisten Apps."""
    if not steps:
        return Result(True)
    try:
        per = max(1, int(action.get("lines") or 1))
    except (TypeError, ValueError):
        per = 1
    amount = steps * per * (-1 if action.get("invert") else 1)
    if action.get("direction") == "horizontal":
        move = {"horizontal": amount}
    else:
        move = {"vertical": -amount}  # REL_WHEEL > 0 ist nach oben
    mouse = mouse_of(ctx)
    keys = action.get("keys") or ""
    if not keys:
        mouse.scroll(**move)
        return Result(True)
    kb = keyboard_of(ctx)
    kb.press(keys)
    try:
        time.sleep(MODIFIER_DELAY)
        mouse.scroll(**move)
        time.sleep(MODIFIER_DELAY)
    finally:
        kb.release(keys)
    return Result(True)
