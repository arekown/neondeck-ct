"""Stumm-Zustand des Standard-Audioausgangs und -eingangs (Zustandsquellen ``mute`` und
``mic_mute``).

Ein dauerhaft laufender Kindprozess ``pactl subscribe`` meldet Aenderungen; bei Ereignissen
an ``sink`` (Ausgang), ``source`` (Eingang) oder ``server`` (Standardgeraet gewechselt) wird
``pactl get-sink-mute @DEFAULT_SINK@`` bzw. ``pactl get-source-mute @DEFAULT_SOURCE@`` neu
gelesen. Alles asynchron ueber ``QProcess`` – der GUI-Thread wartet nie. Je Wert laeuft
hoechstens eine Abfrage; Ereignisse waehrenddessen fuehren zu genau einer weiteren.

Belegt am 18.10.2026 (pactl 17.0, PipeWire): die Ausgabe ist uebersetzt („Mute: nein“),
mit ``LC_ALL=C`` lautet sie ``Mute: yes``/``Mute: no`` und die Ereigniszeilen
``Event 'change' on sink #56`` (weitere Arten: ``sink-input``, ``source-output``,
``client``, ``module``, ``card``, ``server``).

Stirbt ``pactl subscribe``, startet es nach 1 s neu, bei wiederholtem Sterben mit
verdoppelter Wartezeit bis 30 s (lief es mindestens 30 s, beginnt es wieder bei 1 s).
``stop`` beendet alle Kindprozesse. Gibt es ``setpriv`` (util-linux), laeuft ``pactl
subscribe`` mit ``--pdeathsig TERM``: stirbt der Dienst hart, bleibt kein verwaister
Kindprozess zurueck (am 18.10.2026 hier geprueft: ohne setpriv bleibt pactl nach SIGKILL des
Elternprozesses liegen, mit setpriv beendet es sich).
"""
from __future__ import annotations

import logging
import os
import re
import time
from collections.abc import Callable
from functools import partial
from typing import Any

from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, QTimer, Signal

from ..actions.pactl import MUTE_READS as READS
from ..actions.pactl import parse_mute
from ..core.proc import PACTL

log = logging.getLogger(__name__)

SETPRIV = "/usr/bin/setpriv"  # util-linux; --pdeathsig: pactl stirbt mit dem Dienst
_DETECT = object()
FACILITIES = {"sink": ("mute",), "source": ("mic_mute",), "server": ("mute", "mic_mute")}
RESTART_MIN_S = 1.0
RESTART_MAX_S = 30.0
STABLE_S = 30.0          # lief so lange: Wartezeit beim naechsten Sterben wieder kurz
MAX_LINE = 4096          # laengere Zeilen ohne Umbruch werden verworfen
STOP_WAIT_MS = 1000
_EVENT = re.compile(r"^Event '([\w-]+)' on ([\w-]+) #")

ProcessFactory = Callable[[], Any]  # -> QProcess (oder Ersatz in Tests)


class AudioState(QObject):
    """Meldet ``changed(art, wert)`` mit ``art`` = ``mute`` | ``mic_mute``."""

    changed = Signal(str, bool)

    def __init__(self, process_factory: ProcessFactory | None = None,
                 call_later: Callable[[float, Callable[[], None]], None] | None = None,
                 monotonic: Callable[[], float] = time.monotonic,
                 parent: QObject | None = None, setpriv: Any = _DETECT) -> None:
        super().__init__(parent)
        if setpriv is _DETECT:
            setpriv = SETPRIV if os.access(SETPRIV, os.X_OK) else None
        self._setpriv: str | None = setpriv
        self._factory = process_factory or QProcess
        self._call_later = call_later or (
            lambda delay, fn: QTimer.singleShot(round(delay * 1000), self, fn))
        self._mono = monotonic
        self._values: dict[str, bool | None] = {kind: None for kind in READS}
        self._running = False
        self._sub: Any = None
        self._buf = b""
        self._started_at = 0.0
        self._backoff = RESTART_MIN_S
        self._restart_token: object | None = None
        self._reads: dict[str, Any] = {}
        self._again: set[str] = set()
        self._warned = False

    def value(self, kind: str) -> bool | None:
        """Zuletzt gelesener Wert (``None``: noch unbekannt)."""
        return self._values.get(kind)

    # --- Start / Ende --------------------------------------------------------------------

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._spawn_subscribe()

    def stop(self) -> None:
        """Kindprozesse beenden, keinen Neustart mehr (mehrfach aufrufbar)."""
        self._running = False
        self._restart_token = None
        procs = [p for p in (self._sub, *self._reads.values()) if p is not None]
        for proc in procs:
            if proc.state() != QProcess.ProcessState.NotRunning:
                proc.kill()
                proc.waitForFinished(STOP_WAIT_MS)
        self._sub = None
        self._reads.clear()
        self._again.clear()

    def _process(self) -> Any:
        proc = self._factory()
        env = QProcessEnvironment.systemEnvironment()
        env.insert("LC_ALL", "C")  # unuebersetzte Ausgabe
        proc.setProcessEnvironment(env)
        proc.setStandardErrorFile(QProcess.nullDevice())
        return proc

    # --- pactl subscribe -----------------------------------------------------------------

    def _spawn_subscribe(self) -> None:
        proc = self._process()
        proc.readyReadStandardOutput.connect(partial(self._on_output, proc))
        proc.finished.connect(partial(self._on_subscribe_ended, proc))
        proc.errorOccurred.connect(partial(self._on_subscribe_error, proc))
        self._sub, self._buf, self._started_at = proc, b"", self._mono()
        if self._setpriv:  # stirbt der Dienst hart (SIGKILL), bekommt pactl SIGTERM
            proc.start(self._setpriv, ["--pdeathsig", "TERM", "--", PACTL, "subscribe"])
        else:
            proc.start(PACTL, ["subscribe"])
        for kind in READS:  # waehrend der Pause kann sich etwas geaendert haben
            self._read(kind)

    def _on_output(self, proc: Any) -> None:
        if proc is not self._sub:
            return
        self._buf += bytes(proc.readAllStandardOutput())
        *lines, self._buf = self._buf.split(b"\n")
        if len(self._buf) > MAX_LINE:
            self._buf = b""
        kinds: list[str] = []
        for line in lines:
            m = _EVENT.match(line.decode("utf-8", "replace"))
            if m:
                kinds += [k for k in FACILITIES.get(m.group(2), ()) if k not in kinds]
        for kind in kinds:
            self._read(kind)

    def _on_subscribe_error(self, proc: Any, error: Any) -> None:
        # Nur „startet nicht“ beendet ohne ``finished``; Absturz meldet finished selbst.
        if error == QProcess.ProcessError.FailedToStart:
            if not self._warned:
                self._warned = True
                log.warning("pactl subscribe startet nicht – Stumm-Zustände bleiben unbekannt")
            self._on_subscribe_ended(proc)

    def _on_subscribe_ended(self, proc: Any, *_: Any) -> None:
        if proc is not self._sub:
            return
        self._sub = None
        proc.deleteLater()
        if not self._running:
            return
        if self._mono() - self._started_at >= STABLE_S:
            self._backoff = RESTART_MIN_S
        delay = self._backoff
        self._backoff = min(self._backoff * 2, RESTART_MAX_S)
        log.info("pactl subscribe beendet – Neustart in %.0f s", delay)
        token = self._restart_token = object()
        self._call_later(delay, lambda: self._restart(token))

    def _restart(self, token: object) -> None:
        if token is not self._restart_token or not self._running:
            return
        self._restart_token = None
        self._spawn_subscribe()

    # --- get-*-mute --------------------------------------------------------------------

    def _read(self, kind: str) -> None:
        if kind in self._reads:
            self._again.add(kind)  # nach der laufenden Abfrage noch einmal lesen
            return
        proc = self._process()
        proc.finished.connect(partial(self._on_read_done, kind, proc))
        proc.errorOccurred.connect(partial(self._on_read_error, kind, proc))
        self._reads[kind] = proc
        proc.start(PACTL, READS[kind])

    def _on_read_error(self, kind: str, proc: Any, error: Any) -> None:
        if error == QProcess.ProcessError.FailedToStart:
            self._on_read_done(kind, proc, -1)

    def _on_read_done(self, kind: str, proc: Any, code: int = 0, status: Any = None) -> None:
        if self._reads.get(kind) is not proc:
            return
        del self._reads[kind]
        out = bytes(proc.readAllStandardOutput()).decode("utf-8", "replace")
        proc.deleteLater()
        if not self._running:
            return
        ok = code == 0 and status != QProcess.ExitStatus.CrashExit
        value = parse_mute(out) if ok else None
        if value is None:
            log.debug("pactl %s: keine Antwort (%s) %r", READS[kind][0], code, out[:200])
        elif value is not self._values[kind]:
            self._values[kind] = value
            self.changed.emit(kind, value)
        if kind in self._again:
            self._again.discard(kind)
            self._read(kind)
