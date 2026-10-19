"""Engine: Profilzustand, Geraete-Ereignisse -> Aktionen, Zeichnen aller Anzeigen und LEDs.

Ohne Qt. Alle oeffentlichen Methoden werden aus einem Thread aufgerufen; Ergebnisse und
``engine_call`` aus den Aktions-Threads kommen ueber ``post`` in diesen Thread zurueck.

``Engine`` ist eine Fassade: Sie baut die Teile zusammen und reicht weiter.

* ``state`` (``EngineState``): Profil, Ansicht, hell/dunkel, Rueckmeldungen der Ansicht
* ``controls`` (``ControlResolver``): was liegt auf welchem Bedienelement
* ``view`` (``ViewController``): Navigation und gemerkte Ansichten
* ``input`` (``InputRouter`` mit ``TouchTracker``): Eingaben -> Aktionen
* ``dispatch`` (``ActionDispatcher``): Executor, Navigation, Ergebnisse
* ``painter`` (``DisplayPainter``): Displays und LEDs
* ``power`` (``PowerState``), ``saver`` (``ScreensaverRunner``), ``look_clock`` (``LookClock``)
"""
from __future__ import annotations

import logging
from collections.abc import Iterable

from .. import actions  # noqa: F401  (registriert alle Aktionen)
from ..actions.base import Trigger
from ..core.guard import guarded
from ..core.sysload import SystemLoad
from ..core.windows import WindowInfo
from ..device.layout import ControlRef
from ..device.protocol import Event
from ..profile.model import Profile, Workspace
from .controls import ControlResolver
from .dispatch import ActionDispatcher
from .dynamic_folders import DynamicFolders, DynamicSources
from .encoders import Layers
from .input import InputRouter
from .leds import LedController
from .navigation_state import FolderStack
from .painter import DisplayPainter
from .ports import EngineHooks, EngineOptions, EnginePorts, Redraw
from .power import LookClock, PowerState, ScreensaverRunner
from .state import EngineState
from .states import StateStore
from .view import ViewController

log = logging.getLogger(__name__)


class Engine:
    """Erfuellt ``api.contracts.EditorBackend`` (Einstellungsfenster im Testprozess).

    Die Eigenschaften und kurzen Methoden unten reichen an die Teile weiter: Ansicht
    (``state``, ``view``), Bedienung (``dispatch``, ``input``, ``controls``, ``painter``),
    Sperre und Schlaf (``power``), Schoner (``saver``) und Look-Takt (``look_clock``).
    Geaenderte Einstellungen gibt der Dienst ueber ``set_display_sleep``, ``set_saver``,
    ``set_key_timing``, ``saver_name`` und ``device_look`` weiter, Trennen/Verbinden ueber
    ``device_connected``."""

    def __init__(self, profile: Profile, ports: EnginePorts, *,
                 hooks: EngineHooks | None = None, options: EngineOptions | None = None) -> None:
        options = options or EngineOptions()
        self._guard = guard = guarded(log, "Engine-Aufruf %s fehlgeschlagen")
        self.hooks = hooks or EngineHooks()
        self.state = EngineState(profile)
        # Zustaende der Tasten und Werte der Systemquellen (bleiben ueber Profilwechsel)
        self.states = StateStore()
        # dynamischer Ordner (Fenster, Mixer) ueber der aktuellen Seite, nicht im Profil
        self.dynamic = DynamicFolders(
            ports.dynamic_sources or DynamicSources(), call_later=ports.call_later,
            post=lambda fn: ports.post(lambda: guard(fn)), on_change=self.refresh,
            paused=lambda: self.state.paused, on_knobs_changed=self._drop_knob_spins)
        self.controls = ControlResolver(self.state, self.dynamic, FolderStack(), Layers(),
                                        self.states)
        redraw = Redraw(self.refresh, ports.call_later)
        self.dispatch = ActionDispatcher(ports, self.hooks, self.state, self.controls,
                                         call=self.call, redraw=redraw,
                                         after_action=self.dynamic.after_action, guard=guard)
        self.input = InputRouter(ports, self.state, self.controls, self.dispatch,
                                 options=options, call=self.call, redraw=redraw, guard=guard)
        self.look_clock = LookClock(self.state, ports, self.hooks, options.device_look,
                                    redraw=redraw)
        # Leistenanzeige „system“: Systemlast, abgetastet nur, solange eine Leiste sie zeigt
        self._sysload = ports.system_load or SystemLoad()
        self.painter = DisplayPainter(ports, self.state, self.controls, self.look_clock,
                                      self._sysload, LedController(ports.leds),
                                      self.input.touch.strip_pressed)
        self.saver = ScreensaverRunner(self.state, ports, self.hooks, self.painter,
                                       forget_input=self._forget_input,
                                       redraw_all=self.redraw_all,
                                       mode_changed=self._mode_changed)
        self.saver.name, self.saver.minutes = options.saver_name, options.saver_min
        self.saver.options = dict(options.saver_options or {})
        self.power = PowerState(self.state, ports, self.hooks, self.painter, self.saver,
                                forget_input=self._forget_input, redraw_all=self.redraw_all,
                                mode_changed=self._mode_changed)
        self.power.display_sleep_min = options.display_sleep_min
        self.view = ViewController(self.state, self.controls, self.hooks, redraw,
                                   new_view=self._new_view,
                                   clear_gestures=self.input.gestures.clear,
                                   knobs_reassigned=self.dispatch.knobs_reassigned,
                                   reset_caches=self.painter.reset_caches)
        self.view.load_views(options.views)
        self.view.reset(profile)
        self._mode_changed()

    # --- Ansicht (``state``, ``view``) --------------------------------------------------

    @property
    def profile(self) -> Profile:
        return self.state.profile

    @property
    def workspace_id(self) -> str:
        return self.state.workspace_id

    @property
    def page_index(self) -> int:
        return self.state.page_index

    @property
    def workspace(self) -> Workspace | None:
        return self.state.workspace

    @property
    def device_connected(self) -> bool:
        return self.state.device_connected

    @device_connected.setter
    def device_connected(self, value: bool) -> None:  # der Dienst meldet Trennen/Verbinden
        self.state.device_connected = value

    @property
    def locked(self) -> bool:
        return self.state.locked

    @property
    def display_asleep(self) -> bool:
        return self.state.asleep

    @property
    def dark(self) -> bool:
        return self.state.dark

    def view_state(self) -> dict:
        return self.view.view_state()

    def folder_state(self) -> dict:
        return self.view.folder_state()

    def remembered_views(self, existing: Iterable[str] | None = None) -> dict:
        return self.view.remembered_views(existing)

    # --- Bedienung (``dispatch``, ``input``, ``controls``, ``painter``) ------------------

    def trigger(self, ref: ControlRef, action: dict | None, *, steps: int = 0) -> None:
        self.dispatch.trigger(ref, action, steps=steps)

    def activate(self, ref: ControlRef, which: Trigger = Trigger.TAP, *, steps: int = 0) -> bool:
        return self.input.activate(ref, which, steps=steps)

    def set_image_override(self, ref: ControlRef, path: str | None) -> None:
        self.painter.set_override(ref, path)

    def set_key_timing(self, double_ms: int, hold_ms: int) -> None:
        """Schwellen fuer Doppeltippen/Halten, gelten ab dem naechsten Druecken."""
        gestures = self.input.gestures
        gestures.double_ms, gestures.hold_ms = double_ms, hold_ms

    # --- Sperre und Schlaf (``power``) ---------------------------------------------------

    def lock(self) -> None:
        self.power.lock()

    def unlock(self) -> None:
        self.power.unlock()

    def wake(self, *, redraw: bool = True) -> None:
        self.power.wake(redraw=redraw)

    def set_display_sleep(self, minutes: int) -> None:
        """Display-Schlaf nach ``minutes`` Minuten ohne Eingabe (0 = aus: schlafende Displays
        sofort wecken); die Uhr laeuft ab jetzt neu."""
        self.power.display_sleep_min = minutes
        if minutes == 0:
            self.power.wake()
        self.power.note_activity()

    # --- Bildschirmschoner (``saver``) und Look-Takt (``look_clock``) --------------------

    def start_saver(self, name: str | None = None) -> bool:
        return self.saver.start(name)

    def saver_frame(self) -> float | None:
        return self.saver.frame()

    @property
    def saver_active(self) -> bool:
        return self.saver.active

    @property
    def saver_name(self) -> str:
        return self.saver.name

    @saver_name.setter
    def saver_name(self, value: str) -> None:
        self.saver.name = value

    def set_saver(self, minutes: int, name: str, options: dict) -> None:
        """Wartezeit (0 = aus), Variante und Optionen des Bildschirmschoners; die Uhr laeuft
        ab jetzt neu."""
        self.saver.minutes, self.saver.name, self.saver.options = minutes, name, options
        self.power.note_activity()

    @property
    def animating(self) -> bool:
        return self.look_clock.animating

    def look_frame(self) -> float | None:
        return self.look_clock.step()

    # --- Ereignisse und Takt -------------------------------------------------------------

    def handle(self, event: Event) -> None:
        """Ein Geraete-Ereignis verarbeiten; Fehler werden geloggt, nie weitergereicht.
        Gesperrt, im Schlaf und waehrend der Weck-Geste loest nichts aus (``power``)."""
        if self.power.intercept(event):
            return
        try:
            self.input.route(event)
        except Exception:
            log.exception("Ereignis %s nicht verarbeitet", event)

    def tick(self, now: float | None = None) -> None:
        """Jede Sekunde: Live-Kacheln, Rad-Uhr, abgelaufene Leistenwerte/Blinken; nach
        ``power.display_sleep_min`` Minuten ohne Eingabe Display-Schlaf, nach ``saver.minutes``
        Minuten der Bildschirmschoner (der Schlaf gewinnt, wenn er frueher oder gleichzeitig dran ist)."""
        if not self.power.idle_check():
            self.painter.refresh(now)

    def refresh(self, now: float | None = None) -> None:
        """Nur die Anzeigen neu zeichnen, deren Inhalt sich geaendert hat."""
        self.painter.refresh(now)

    def redraw_all(self) -> None:
        """Alles neu senden, auch Unveraendertes (z. B. nach Wiederverbinden); gesperrt oder
        im Display-Schlaf heisst das: schwarz und LEDs aus."""
        if self.state.dark:
            self.painter.blank()
            return
        self.painter.forget()
        if self.state.saver_on:
            return  # das naechste Bild des Bildschirmschoners zeichnet alles
        self.dynamic.resume()  # Mixer: nach Sperre/Schlaf/Trennen einmal nachlesen
        self.painter.refresh()

    # --- Profil und Ansicht --------------------------------------------------------------

    def set_profile(self, profile: Profile, *, keep_view: bool = False) -> None:
        """Neues Profil anzeigen.

        Mit ``keep_view`` (bearbeitetes Profil aus dem Einstellungsfenster) bleiben
        Arbeitsbereich, Seite und der laufende Zustand stehen: Stoppuhren, Leistenwerte,
        Blinken, gesammelte Drehungen und geladene Symbole. Gibt es den Arbeitsbereich
        nicht mehr, wird wie ohne ``keep_view`` auf den Heim-Arbeitsbereich zurueckgesetzt.

        Ohne ``keep_view`` merkt sich die Engine bei einem Wechsel auf ein anderes Profil die
        Ansicht des bisherigen und zeigt vom neuen die zuletzt gemerkte (sonst den
        Heim-Arbeitsbereich, Seite 1). Dasselbe Profil neu geladen beginnt im Heim-Bereich.

        Laesst sich das neue Profil nicht zeichnen, bleibt das alte samt Ansicht stehen
        (die Ausnahme wird weitergereicht).
        """
        snapshot = self.view.snapshot()
        try:
            self.view.load(profile, keep_view=keep_view)
            self.redraw_all()
        except Exception:
            self.view.restore(snapshot)
            self.painter.reset_caches()
            self._guard(self.redraw_all)
            raise
        self.view.changed()

    def call(self, name: str, params: dict) -> None:
        """Navigation (``engine_call`` der Aktionen, siehe ``ViewController.call``)."""
        self.view.call(name, params)

    def show_workspace(self, ws_id: str) -> None:
        """Arbeitsbereich ``ws_id`` zeigen (Einstellungsfenster, wie die Aktion ``workspace``)."""
        self.view.call("workspace", {"id": ws_id})

    def show_page(self, index: int) -> None:
        """Seite ``index`` zeigen (Einstellungsfenster, wie die Aktion ``page``)."""
        self.view.call("page", {"index": index})

    # --- Zustaende, Quellen, Fenster -----------------------------------------------------

    def set_state(self, ref: ControlRef, n: int) -> None:
        """Zustand ``n`` einer Taste setzen (API ``state.set``, gilt fuer die Taste auf der
        aktuellen Seite); eine Touch-Taste zeigt dann das Bild von ``states[n]`` (gibt es den
        Zustand nicht: das Grundbild). Systemquellen (stumm, Medien, App) bestimmen ihren
        Zustand selbst."""
        self.states.set(self.controls.state_key(ref), n)
        self.refresh()

    def set_source_value(self, source: str, value: bool | None) -> None:
        """Wert einer Systemquelle (``mute``, ``mic_mute``, ``media``) melden."""
        if self.states.set_flag(source, value):
            self.refresh()

    def set_windows(self, windows: Iterable[WindowInfo]) -> None:
        """Offene Fenster (KWin-Liste) fuer Zustaende mit Quelle ``app_running``."""
        windows = list(windows)
        self.states.set_windows(windows)
        self.dynamic.set_windows(windows)
        self.refresh()

    # --- Geraete-Look --------------------------------------------------------------------

    @property
    def device_look(self) -> str:
        """``classic`` oder ``cockpit`` (``render.look``; ``auto`` loest der Dienst
        auf)."""
        return self.look_clock.look.name

    @device_look.setter
    def device_look(self, name: str) -> None:
        if self.look_clock.switch(name):
            self.painter.forget()  # alles im neuen Look zeichnen
            self.refresh()
            self._mode_changed()

    # --- Ende ----------------------------------------------------------------------------

    def reset_input(self) -> None:
        """Nach Trennen vom Geraet: gehaltene Tasten loslassen, Beruehrungen vergessen."""
        self._forget_input()
        self.refresh()

    def shutdown(self) -> None:
        """Gehaltene Tasten loslassen, dann Executor und Hintergrundarbeit beenden."""
        self.dispatch.release_held()
        self._sysload.close()
        self.dispatch.shutdown()
        self.dynamic.shutdown()

    # --- Verdrahtung der Teile -----------------------------------------------------------

    def _forget_input(self) -> None:
        """Gehaltenes loslassen, alle angefangenen Eingaben und die Weck-Geste vergessen."""
        self.dispatch.release_held()
        self.input.forget()
        self.dispatch.drop_rotation()
        self.power.wake_guard.clear()

    def _new_view(self) -> None:
        """Ansicht gewechselt: Gesammeltes, laufende Gesten und angefangene Beruehrungen
        gehoeren zur alten Belegung (R24/R25)."""
        self.dispatch.drop_rotation()
        self.input.forget_gestures()
        self.state.view_gen += 1

    def _mode_changed(self) -> None:
        """Hell/dunkel oder Schoner gewechselt: Systemlast-Abtastung und Look-Takt anpassen."""
        self.painter.update_sampling()
        self.look_clock.update()

    def _drop_knob_spins(self, knobs: list[int]) -> None:
        self.dispatch.drop_knob_spins(knobs)
