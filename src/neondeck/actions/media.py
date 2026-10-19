"""Aktionen: Lautstaerke, Stumm, Medientasten, Monitor-Helligkeit."""
from __future__ import annotations

from ..core.i18n import N_, tr
from ..core.proc import DDCUTIL
from ..core.values import MUTED_MESSAGE
from . import pactl
from .base import Param, Result, keyboard_of, register, run_checked

MEDIA_KEYS = {"play_pause": "KEY_PLAYPAUSE", "next": "KEY_NEXTSONG",
              "previous": "KEY_PREVIOUSSONG", "stop": "KEY_STOPCD"}
BRIGHTNESS_STEP = 5   # Prozent je Drehschritt
BRIGHTNESS_DEFAULT = 70


@register("volume", label=N_("Lautstärke"), category="media", kinds={"rotate"})
def volume(action, ctx, *, steps=0, **_):
    """Standardausgang relativ aendern (hoechstens 100 %); fuer Leiste und Rad der neue Wert
    (stumm: „stumm“, grau)."""
    if not steps:
        return Result(True)
    res = run_checked(ctx, pactl.sink_volume_change(steps))
    if not res.ok:
        return res
    got = run_checked(ctx, pactl.sink_volume_read())
    percent, muted = pactl.parse_sink_volume(got.message) if got.ok else (None, False)
    if muted:
        return Result(True, tr(MUTED_MESSAGE), muted=True)
    if percent is None:
        return Result(True)
    return Result(True, f"{percent} %", value=float(percent))


@register("mute_toggle", label=N_("Stummschalten"), category="media")
def mute_toggle(action, ctx, **_):
    return run_checked(ctx, pactl.argv("set-sink-mute", pactl.SINK, "toggle"))


LOOP = "loop"  # keine Taste: Wiederholen ueber MPRIS (None -> Playlist -> Track -> None)
# Medientaste -> MPRIS-Methode, wenn ein Player gewaehlt ist
MPRIS_METHODS = {"play_pause": "PlayPause", "next": "Next", "previous": "Previous",
                 "stop": "Stop"}


@register("media", label=N_("Medientaste"), category="media", params=[
    Param("key", N_("Taste"), "choice", "play_pause", [*MEDIA_KEYS, LOOP]),
    Param("player", N_("Player (z. B. spotify; leer = Medientaste ans System)"), "text", "")])
def media(action, ctx, **_):
    player = str(action.get("player") or "").strip()
    if action.get("key") == LOOP:
        if ctx.media_loop is None:
            return Result(False, tr("Wiederholen braucht den Dienst (MPRIS)"))
        ctx.media_loop(player)
        return Result(True)
    if player and action.get("key") in MPRIS_METHODS and ctx.media_control is not None:
        ctx.media_control(MPRIS_METHODS[action["key"]], player)
        return Result(True)
    key = MEDIA_KEYS.get(action.get("key"))
    if key is None:
        return Result(False, tr("Unbekannte Medientaste: {key}", key=action.get("key")))
    keyboard_of(ctx).tap(key)
    return None


@register("brightness", label=N_("Helligkeit"), category="media", kinds={"rotate"})
def brightness(action, ctx, *, steps=0, **_):
    if not steps:
        return Result(True)
    res = run_checked(ctx, [DDCUTIL, "setvcp", "10", "+" if steps > 0 else "-",
                            str(abs(steps) * BRIGHTNESS_STEP)])
    return Result(res.ok, "" if res.ok else res.message)


@register("brightness_reset", label=N_("Helligkeit zurücksetzen"), category="media")
def brightness_reset(action, ctx, **_):
    res = run_checked(ctx, [DDCUTIL, "setvcp", "10", str(BRIGHTNESS_DEFAULT)])
    return Result(res.ok, "" if res.ok else res.message)
