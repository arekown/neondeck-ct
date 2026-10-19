"""Systemlast fuer die Leistenanzeige „system“ und den Cockpit-Schoner (ohne Qt).

* CPU und RAM: ``CpuMeter`` liest ``/proc/stat`` und ``/proc/meminfo`` (billig, im
  Engine-Thread, hoechstens einmal je ``CPU_EVERY_S``).
* GPU: ``GpuSampler`` fragt ``nvidia-smi`` in einem eigenen Hintergrund-Thread alle
  ``GPU_EVERY_S`` ab – der Engine-Thread liest nur das letzte Ergebnis und blockiert nie.
  Ohne ``nvidia-smi`` oder GPU bleiben die Werte ``None`` (Anzeige „–“).

``SystemLoad`` buendelt beides; ``set_active(False)`` haelt den GPU-Thread an (keine Leiste
zeigt ``system`` oder das Geraet ist dunkel).
"""
from __future__ import annotations

import logging
import shutil
import threading
import time
from collections.abc import Callable
from pathlib import Path

from . import proc
from .proc import NVIDIA_SMI

log = logging.getLogger(__name__)

GPU_QUERY = (NVIDIA_SMI, "--query-gpu=index,utilization.gpu",
             "--format=csv,noheader,nounits")
GPU_EVERY_S = 2.0
GPU_TIMEOUT_S = 5.0
GPUS = 2               # Anzeige: GPU 1 und GPU 2 (nvidia-smi-Index 0 und 1)
CPU_EVERY_S = 1.0

Percent = int | None  # 0–100, ``None`` = unbekannt


class CpuMeter:
    """CPU-Auslastung aus /proc/stat (Differenz zum letzten Aufruf) und RAM aus /proc/meminfo
    (je 0–1). ``cpu`` gilt erst ab dem zweiten ``update`` (``samples`` zaehlt mit)."""

    def __init__(self) -> None:
        self._last: tuple[int, int] | None = None
        self.cpu = 0.0
        self.mem = 0.0
        self.samples = 0

    def update(self) -> None:
        try:
            first = Path("/proc/stat").read_text(encoding="ascii").split("\n", 1)[0]
            parts = [int(v) for v in first.split()[1:]]
            idle, total = parts[3] + parts[4], sum(parts)
            if self._last is not None and total > self._last[1]:
                self.cpu = 1.0 - (idle - self._last[0]) / (total - self._last[1])
            self._last = (idle, total)
            info = {}
            for line in Path("/proc/meminfo").read_text(encoding="ascii").splitlines():
                key, value = line.split(":", 1)
                info[key] = int(value.split()[0])
            self.mem = 1.0 - info["MemAvailable"] / info["MemTotal"]
            self.samples += 1
        except (OSError, ValueError, KeyError, IndexError, ZeroDivisionError):
            pass


def parse_gpu(text: str) -> tuple[Percent, ...]:
    """Ausgabe von ``GPU_QUERY`` (``"0, 37"`` je Zeile) → Auslastung je Index 0 … GPUS-1;
    fehlende oder „[N/A]“ → ``None``."""
    out: list[Percent] = [None] * GPUS
    for line in text.splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 2:
            continue
        try:
            index, util = int(parts[0]), float(parts[1])
        except ValueError:
            continue
        if 0 <= index < GPUS:
            out[index] = max(0, min(100, round(util)))
    return tuple(out)


def _run_query() -> str:
    res = proc.run(list(GPU_QUERY), timeout=GPU_TIMEOUT_S)
    if res.returncode:
        raise proc.SubprocessError(f"{NVIDIA_SMI} endete mit Exit-Code {res.returncode}")
    return res.stdout


class GpuSampler:
    """GPU-Auslastung im Hintergrund; ``values`` ist immer sofort da (letzter Stand)."""

    def __init__(self, run: Callable[[], str] = _run_query, every: float = GPU_EVERY_S,
                 available: Callable[[], bool] | None = None) -> None:
        self._run = run
        self._every = every
        self._available = available or (lambda: shutil.which(GPU_QUERY[0]) is not None)
        self.values: tuple[Percent, ...] = (None,) * GPUS
        self._thread: threading.Thread | None = None
        self._stop: threading.Event | None = None
        self._warned = False

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def set_active(self, on: bool) -> None:
        if on and not self.running:
            if not self._available():
                self.values = (None,) * GPUS
                return
            stop = self._stop = threading.Event()
            self._thread = threading.Thread(target=self._loop, args=(stop,),
                                            name="gpu-sampler", daemon=True)
            self._thread.start()
        elif not on and self._stop is not None:
            self._stop.set()
            self._stop = self._thread = None

    def sample(self) -> None:
        """Einmal abfragen (im Thread; Tests rufen es direkt auf)."""
        try:
            self.values = parse_gpu(self._run())
        except (OSError, proc.SubprocessError, ValueError) as e:
            self.values = (None,) * GPUS
            if not self._warned:
                self._warned = True
                log.warning("GPU-Auslastung nicht lesbar: %s", e)

    def _loop(self, stop: threading.Event) -> None:
        while not stop.is_set():
            self.sample()
            stop.wait(self._every)


class SystemLoad:
    """CPU, RAM, GPU 1, GPU 2 in Prozent fuer die Leiste „system“."""

    def __init__(self, cpu: CpuMeter | None = None, gpu: GpuSampler | None = None,
                 monotonic: Callable[[], float] = time.monotonic) -> None:
        self._cpu = cpu or CpuMeter()
        self._gpu = gpu or GpuSampler()
        self._mono = monotonic
        self._cpu_at = float("-inf")
        self.active = False

    def set_active(self, on: bool) -> None:
        if on == self.active:
            return
        self.active = on
        self._gpu.set_active(on)
        if on:
            self._cpu_at = float("-inf")  # beim Wiedereinschalten gleich frisch lesen

    def values(self) -> tuple[Percent, Percent, Percent, Percent]:
        """``(cpu, ram, gpu1, gpu2)``; CPU/RAM werden hier hoechstens einmal je
        ``CPU_EVERY_S`` neu gelesen."""
        now = self._mono()
        if now - self._cpu_at >= CPU_EVERY_S:
            self._cpu.update()
            self._cpu_at = now
        m = self._cpu
        cpu = round(100 * m.cpu) if m.samples >= 2 else None
        mem = round(100 * m.mem) if m.samples >= 1 else None
        g = tuple(self._gpu.values) + (None,) * GPUS
        return cpu, mem, g[0], g[1]

    def close(self) -> None:
        self.set_active(False)
