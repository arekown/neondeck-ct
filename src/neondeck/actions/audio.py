"""Aktionen: Mikrofon stumm, Audioausgang wechseln, Lautstaerke einzelner Anwendungen.

Alles ueber ``pactl`` (PipeWire-Pulse). ``stream_volume``/``stream_mute`` sind die Aktionen
der Kacheln und Regler im dynamischen Ordner „Mixer“ (``dynamic_folders``); sie stehen nicht
in der Aktionsliste des Editors, weil die Stream-Nummern nur so lange gelten, wie die
Anwendung spielt.
"""
from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass

from ..core import proc
from ..core.i18n import N_, tr
from ..core.values import MUTED_MESSAGE, is_int
from . import pactl
from .base import Param, Result, register, run_checked

MUTED = MUTED_MESSAGE  # Meldung wie bei der Lautstaerke-Aktion
STREAM_MAX = pactl.MAX_PERCENT  # hoeher dreht ein Regler eine Anwendung nicht


@dataclass(frozen=True)
class Stream:
    """Eine spielende Anwendung (``pactl list sink-inputs``)."""
    index: int
    name: str
    volume: int   # Prozent (erster Kanal)
    muted: bool
    icon: str     # Symbolname: ``application.icon_name``, sonst Programmname (oder leer)

    @property
    def value(self) -> str:
        """Leistenwert: ``"28 %"`` oder ``"stumm"``."""
        return tr(MUTED) if self.muted else f"{self.volume} %"

    @property
    def percent(self) -> float | None:
        """Wert fuer den Balken (0–100); stumm: ``None`` (die Leiste zeigt „stumm“)."""
        return None if self.muted else float(min(100, max(0, self.volume)))


def _stream(raw: dict) -> Stream | None:
    index = raw.get("index")
    if not is_int(index):
        return None
    props = raw.get("properties") if isinstance(raw.get("properties"), dict) else {}
    name = next((str(props[k]) for k in ("application.name", "media.name")
                 if props.get(k)), f"Stream {index}")
    volume = 0
    channels = raw.get("volume") if isinstance(raw.get("volume"), dict) else {}
    for channel in channels.values():
        percent = pactl.parse_percent(str((channel or {}).get("value_percent", "")))
        if percent is not None:
            volume = percent
            break
    icon = props.get("application.icon_name") or props.get("application.process.binary")
    return Stream(index, name, volume, raw.get("mute") is True, str(icon or ""))


def list_streams(run: Callable) -> list[Stream]:
    """Spielende Anwendungen ueber ``pactl -f json list sink-inputs`` (``run`` wie
    ``ActionContext.run``; blockiert kurz: nie im GUI-Thread). Bei jedem Fehler leer."""
    try:
        p = run(pactl.argv("-f", "json", "list", "sink-inputs"))
        raw = json.loads(p.stdout or "[]") if p.returncode == 0 else []
    except (OSError, ValueError, proc.SubprocessError):
        return []
    if not isinstance(raw, list):
        return []
    return [s for s in (_stream(r) for r in raw if isinstance(r, dict)) if s is not None]


def _index(action: dict) -> int | None:
    v = action.get("index")
    return v if is_int(v) and v >= 0 else None


@register("mic_mute", label=N_("Mikrofon stumm"), category="media")
def mic_mute(action, ctx, **_):
    res = run_checked(ctx, pactl.argv("set-source-mute", pactl.SOURCE, "toggle"))
    return Result(res.ok, "" if res.ok else res.message)


@register("audio_output_next", label=N_("Audioausgang wechseln"), category="media")
def audio_output_next(action, ctx, **_):
    """Naechster Ausgang aus ``pactl list short sinks`` (im Kreis) wird Standard."""
    res = run_checked(ctx, pactl.argv("list", "short", "sinks"))
    if not res.ok:
        return res
    names = [cols[1] for cols in (line.split("\t") for line in res.message.splitlines())
             if len(cols) > 1 and cols[1]]
    if not names:
        return Result(False, tr("Kein Audioausgang gefunden"))
    cur = run_checked(ctx, pactl.argv("get-default-sink"))
    current = cur.message.strip() if cur.ok else ""
    target = names[(names.index(current) + 1) % len(names)] if current in names else names[0]
    res = run_checked(ctx, pactl.argv("set-default-sink", target))
    return Result(True, target) if res.ok else res


@register("stream_volume", label=N_("Lautstärke einer Anwendung"), category="media",
          params=[Param("index", N_("Stream"), "int", 0)], kinds={"rotate"})
def stream_volume(action, ctx, *, steps=0, **_):
    index = _index(action)
    if index is None:
        return Result(False, tr("Ungültiger Stream: {index!r}", index=action.get("index")))
    if not steps:
        return Result(True)
    res = run_checked(ctx, pactl.argv("set-sink-input-volume", str(index),
                                      pactl.volume_delta(steps)))
    if not res.ok:
        return res
    stream = next((s for s in list_streams(ctx.run) if s.index == index), None)
    if stream is None:
        return Result(True)
    if stream.volume > STREAM_MAX:  # relativ ueber 100 % hinaus: zurueck auf 100 %
        run_checked(ctx, pactl.argv("set-sink-input-volume", str(index), f"{STREAM_MAX}%"))
        return Result(True, f"{STREAM_MAX} %", value=float(STREAM_MAX))
    return Result(True, stream.value, value=stream.percent, muted=stream.muted)


@register("stream_mute", label=N_("Anwendung stumm"), category="media",
          params=[Param("index", N_("Stream"), "int", 0)])
def stream_mute(action, ctx, **_):
    index = _index(action)
    if index is None:
        return Result(False, tr("Ungültiger Stream: {index!r}", index=action.get("index")))
    res = run_checked(ctx, pactl.argv("set-sink-input-mute", str(index), "toggle"))
    return Result(res.ok, "" if res.ok else res.message)
