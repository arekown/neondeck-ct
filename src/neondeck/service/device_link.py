"""Verbindung zum Geraet aus Sicht des Dienstes: Zustand, Tray-Meldungen, Seriennummer,
Helligkeit, Standby.

Alle Aufrufe im GUI-Thread (der Dienst reicht die Rueckrufe des Geraete-Threads ueber den
Poster herein). Die Engine kommt mit ``attach`` dazu (sie entsteht nach der Verbindung,
weil sie deren ``on_dark`` braucht).
"""
from __future__ import annotations

import time
from collections.abc import Callable
from functools import partial
from typing import TYPE_CHECKING, Any

from ..core.i18n import N_, tr
from ..device.layout import ROUND_CODES, Display

if TYPE_CHECKING:
    from ..core.settings import Settings
    from ..engine import Engine
    from .tray import Tray

SERIAL_POLL_S = 0.2   # Seriennummer kommt kurz nach dem Verbinden
SERIAL_POLL_TRIES = 25
DEVICE_LOST = N_("Loupedeck CT getrennt")
DEVICE_BACK = N_("Loupedeck CT wieder verbunden")
RESUME_QUIET_S = 10.0  # nach dem Aufwachen: „getrennt“ erst melden, wenn es so lange anhaelt


class DeviceLink:
    """``call_later(sekunden, fn)`` plant im GUI-Thread (Tests ersetzen es);
    ``emit(name, daten)`` meldet ``device.state`` an die API."""

    def __init__(self, device: Any, tray: Tray, settings: Settings, *,
                 emit: Callable[[str, dict], None],
                 call_later: Callable[[float, Callable[[], None]], None]) -> None:
        self.device, self._tray, self._settings, self._emit = device, tray, settings, emit
        self.call_later = call_later
        self._engine: Engine | None = None
        self._connected = False
        self._was_connected = False  # Verbindung bestand schon einmal (sonst kein „getrennt“)
        self._lost_shown = False  # „getrennt“ gemeldet (nur dann spaeter „wieder verbunden“)
        self._quiet_until = 0.0  # bis dahin ist ein Trennen das Neuverbinden nach dem Standby
        self._connection = 0
        self._closed = False

    def attach(self, engine: Engine) -> None:
        self._engine = engine

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def connection(self) -> int:
        """Zaehlt Verbindungswechsel (verbunden und getrennt)."""
        return self._connection

    def status(self) -> dict:
        serial = self.device.serial_number() if self._connected else None
        return {"connected": self._connected, "serial": serial}

    def firmware(self) -> str | None:
        """Firmware-Version; fragt das verbundene Geraet an, solange sie unbekannt ist."""
        query = getattr(self.device, "firmware_version", None) if self._connected else None
        return query(request=True) if query is not None else None

    def close(self) -> None:
        """Beim Beenden: kein „getrennt“ mehr melden."""
        self._closed = True

    # --- Verbinden / Trennen -------------------------------------------------------------

    def on_state(self, connected: bool) -> None:
        self._connected = connected
        self._engine.device_connected = connected  # getrennt: Mixer-Takt fragt pactl nicht ab
        self._connection += 1
        if connected:
            self._on_connected()
        else:
            self._on_lost()
        self._emit("device.state", self.status())

    def _on_connected(self) -> None:
        # Anstecken zaehlt als Eingabe: weckt aus dem Display-Schlaf (gesperrt bleibt es
        # dunkel) und startet die Schlafuhr neu – vor der Helligkeit, sonst ginge 0 raus.
        self._engine.wake(redraw=False)
        self.device.set_brightness(self.brightness_now())
        self._engine.redraw_all()
        self._tray.set_status(tr("verbunden"))
        if self._lost_shown:
            self._tray.notify(tr(DEVICE_BACK), kind="connection")
        self._lost_shown = False
        self._quiet_until = 0.0
        self._was_connected = True
        self._poll_serial(self._connection, SERIAL_POLL_TRIES)

    def _on_lost(self) -> None:
        self._engine.reset_input()
        self._tray.set_status(tr("getrennt"))
        if self._was_connected and not self._closed:
            if time.monotonic() < self._quiet_until:
                # Neuverbinden nach dem Standby: nur melden, wenn es nicht wiederkommt
                self.call_later(RESUME_QUIET_S, partial(self._late_lost, self._connection))
            else:
                self._show_lost()

    def _show_lost(self) -> None:
        self._lost_shown = True
        self._tray.notify(tr(DEVICE_LOST), kind="connection")

    def _late_lost(self, connection: int) -> None:
        """Frist nach dem Aufwachen um: noch immer dieselbe Trennung -> jetzt melden."""
        if connection == self._connection and not self._connected and not self._closed:
            self._show_lost()

    def _poll_serial(self, connection: int, tries: int) -> None:
        if connection != self._connection or not self._connected:
            return  # inzwischen getrennt oder neu verbunden
        serial = self.device.serial_number()
        if serial:
            self._tray.set_status(tr("verbunden ({serial})", serial=serial))
            self._emit("device.state", {"connected": True, "serial": serial})
        elif tries > 0:
            self.call_later(SERIAL_POLL_S, partial(self._poll_serial, connection, tries - 1))

    # --- Standby, Helligkeit -------------------------------------------------------------

    def on_about_to_sleep(self) -> None:
        """Vor dem Standby: gehaltene Tasten loslassen (ihr Loslassen kaeme nie an)."""
        self._engine.reset_input()

    def on_resumed(self) -> None:
        """Nach dem Aufwachen: zuerst Geraet neu verbinden (die alte Sitzung kann stumm
        haengen, also nichts mehr an sie senden); ``on_state(True)`` sendet dann
        Helligkeit, LEDs und alle Displays (gesperrt: Helligkeit 0 und schwarz). Das gewollte
        Trennen meldet der Tray nicht (nur wenn das Geraet binnen ``RESUME_QUIET_S`` nicht
        wiederkommt)."""
        self._quiet_until = time.monotonic() + RESUME_QUIET_S
        self.device.reconnect()
        self._engine.wake(redraw=False)

    def brightness_now(self) -> int:
        """Gesperrt oder im Display-Schlaf: 0 (Hintergrundbeleuchtung aus), sonst die
        eingestellte Helligkeit."""
        return 0 if self._engine.dark else self._settings.brightness

    def on_dark(self, dark: bool) -> None:
        self.device.set_brightness(self.brightness_now())

    def show_brightness(self) -> None:
        """Eingestellte Helligkeit senden; gesperrt/im Display-Schlaf gilt sie ab dem Wecken."""
        if not self._engine.dark:
            self.device.set_brightness(self._settings.brightness)

    def blank(self) -> None:
        """Displays schwarz, LEDs aus (Beenden)."""
        for display in Display:
            self.device.draw(display, bytes(display.width * display.height * 2))
        self.device.set_leds({code: (0, 0, 0) for code in ROUND_CODES})
