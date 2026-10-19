"""Dynamische Ordner: Ordnerseiten, deren Kacheln aus dem System kommen, ohne Qt.

* „Fenster“ (``windows``): je offenem Fenster (KWin-Liste, ``set_windows``) eine Kachel mit
  gekuerztem Titel und App-Symbol, Tippen holt genau dieses Fenster nach vorn
  (``app_focus`` mit ``window``). Die Kacheln folgen der Liste, solange der Ordner offen ist.
* „Mixer“ (``mixer``): je spielender Anwendung (``pactl list sink-inputs``) eine Kachel mit
  Name und Lautstaerke, Tippen schaltet sie stumm. Regler 1–6 regeln die ersten sechs
  Anwendungen, die Leisten zeigen deren Namen und Lautstaerke. Neu gelesen wird nach jeder
  Aktion (``after_action``) und alle ``MIXER_REFRESH_S`` Sekunden, solange der Ordner offen
  ist.

Was blockieren kann (``pactl``, ``.desktop``-Dateien lesen), laeuft ueber
``DynamicSources.spawn`` (Standard: ein eigener Worker, den ``DynamicFolders.shutdown`` mit
der Engine beendet); das Ergebnis kommt ueber ``post`` in den Engine-Thread zurueck,
``on_change`` laesst die Engine dann neu zeichnen.

Die Seiten stehen nicht im Profil: Die Engine zeigt ``page()`` als Ordnerseite (Kachel 0
„Zurück“) ueber der Seite, von der aus der Ordner geoeffnet wurde.
"""
from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field, replace
from enum import StrEnum
from pathlib import Path

from ..actions.audio import Stream, list_streams
from ..core import desktop_apps, proc
from ..core.i18n import N_, tr
from ..core.windows import WindowInfo
from ..core.workers import Worker
from ..device.layout import ENCODERS, TOUCH_BUTTONS
from ..profile.model import STRIP_BAR, Assignment, ButtonImage, Encoder, TouchPage

log = logging.getLogger(__name__)



class DynamicKind(StrEnum):
    """Art eines dynamischen Ordners (``dynamic_folder``-Aktion ``kind``)."""
    WINDOWS = "windows"
    MIXER = "mixer"


NAMES = {DynamicKind.WINDOWS: N_("Fenster"), DynamicKind.MIXER: N_("Mixer")}
PAGE_PREFIX = "dynamic:"  # Seiten-ID (``view_state``: ``folder``)
MAX_TILES = TOUCH_BUTTONS - 1  # Kachel 0 ist „Zurück“
MIXER_REFRESH_S = 2.0
TITLE_MAX = 24
_TITLE_SEPARATORS = (" — ", " – ", " - ")  # „Dokument — Kate“: App-Name abschneiden
WINDOW_BG = "#14202c"
STREAM_BG = "#10281c"
MUTED_BG = "#3a1414"


@dataclass
class VirtualPage:
    """Inhalt eines geoeffneten dynamischen Ordners."""
    page: TouchPage                          # ``folder=True``, nicht im Profil
    encoders: list[Encoder] | None = None  # ``None``: Regler des Arbeitsbereichs
    # bleibende Leistenwerte je Regler: (Text, Prozent fuer den Balken | None)
    values: dict[int, tuple[str, float | None]] = field(default_factory=dict)


def icon_ref(icon: str) -> str | None:
    """Symbol aus einer ``.desktop``-Datei oder ``pactl``: Pfad -> ``file:``, sonst Name im
    Symbolthema (``theme:``)."""
    if not icon:
        return None
    return f"file:{icon}" if Path(icon).is_absolute() else f"theme:{icon}"


def short_title(caption: str) -> str:
    """Fenstertitel ohne angehaengten App-Namen, hoechstens ``TITLE_MAX`` Zeichen."""
    text = (caption or "").strip()
    for sep in _TITLE_SEPARATORS:
        head, found, _ = text.rpartition(sep)
        if found and head.strip():
            text = head.strip()
            break
    return text if len(text) <= TITLE_MAX else text[:TITLE_MAX - 1].rstrip() + "…"


def _compact(stream: Stream) -> str:
    """Lautstaerke auf der Kachel: ``28%`` (ohne Leerzeichen, sonst bricht ``%`` allein in
    die naechste Zeile), stumm: ``stumm``."""
    return stream.value.replace(" %", "%")


def _default_streams() -> list[Stream]:
    return list_streams(proc.run)


def _default_app_icons() -> dict[str, str]:
    """Symbol je App-Kennung (Desktop-ID und ``StartupWMClass``, klein geschrieben)."""
    icons: dict[str, str] = {}
    for app in desktop_apps.list_apps():
        ref = icon_ref(app.icon)
        if ref is None:
            continue
        icons.setdefault(app.id.lower(), ref)
        if app.wm_class:
            icons.setdefault(app.wm_class.lower(), ref)
    return icons


WORKER_THREADS = 2  # Stream- und Symbolabfrage laufen nebeneinander


@dataclass
class DynamicSources:
    """Woher die Ordner ihre Daten holen (Tests ersetzen alles)."""
    streams: Callable[[], list[Stream]] = _default_streams        # blockiert
    app_icons: Callable[[], dict[str, str]] = _default_app_icons  # blockiert
    # Hintergrundarbeit starten; None: eigener Worker der ``DynamicFolders``
    spawn: Callable[[Callable[[], None]], object] | None = None


class _Background:
    """Blockierende Abfragen ueber ``DynamicSources.spawn``; das Ergebnis kommt ueber
    ``post`` in den Engine-Thread zurueck."""

    def __init__(self, sources: DynamicSources,
                 post: Callable[[Callable[[], None]], None]) -> None:
        self.sources = sources
        self._post = post

    def run(self, work: Callable[[], object], done: Callable[[object], None]) -> bool:
        """``work`` ueber ``spawn``, ``done(ergebnis)`` danach im Engine-Thread (``None``
        bei einem Fehler)."""
        post = self._post

        def job() -> None:
            try:
                result = work()
            except Exception:
                log.exception("Dynamischer Ordner: Daten nicht gelesen")
                result = None
            post(lambda: done(result))

        try:
            self.sources.spawn(job)
        except Exception:
            log.exception("Dynamischer Ordner: Hintergrundarbeit nicht gestartet")
            return False
        return True


def _folder_page(kind: DynamicKind) -> tuple[TouchPage, list[Assignment | None]]:
    buttons: list[Assignment | None] = [None] * TOUCH_BUTTONS
    return TouchPage(PAGE_PREFIX + kind, tr(NAMES[kind]), buttons, folder=True), buttons


class WindowsFolder:
    """„Fenster“: je offenem Fenster eine Kachel mit gekuerztem Titel und App-Symbol."""

    def __init__(self, background: _Background, on_change: Callable[[], None]) -> None:
        self._bg = background
        self._on_change = on_change
        self.active = False
        self.page: VirtualPage | None = None
        self._windows: list[WindowInfo] = []
        self._icons: dict[str, str] = {}
        self._icons_loading = False

    def open(self) -> None:
        self.active = True
        self._load_icons()
        self._rebuild()

    def close(self) -> None:
        self.active = False
        self.page = None

    def set_windows(self, windows: list[WindowInfo]) -> None:
        self._windows = windows
        if self.active:
            self._rebuild()

    def _load_icons(self) -> None:
        """App-Symbole bei jedem Oeffnen neu lesen (neu installierte Apps); bis dahin gelten
        die bisherigen."""
        if self._icons_loading:
            return
        self._icons_loading = True
        if not self._bg.run(self._bg.sources.app_icons, self._got_icons):
            self._icons_loading = False

    def _got_icons(self, icons: object) -> None:
        self._icons_loading = False
        if isinstance(icons, dict):
            self._icons = icons
        if self.active:
            self._rebuild()
            self._on_change()

    def _rebuild(self) -> None:
        page, buttons = _folder_page(DynamicKind.WINDOWS)
        for i, w in enumerate(self._windows[:MAX_TILES], start=1):
            buttons[i] = self._window_tile(w)
        self.page = VirtualPage(page)

    def _window_tile(self, w: WindowInfo) -> Assignment:
        icon = (self._icons.get(w.desktop_file.lower()) or self._icons.get(
            w.resource_class.lower()) or icon_ref(w.desktop_file or w.resource_class))
        return Assignment({"type": "app_focus", "app_id": w.desktop_file or w.resource_class,
                           "window": w.internal_id},
                          ButtonImage(bg=WINDOW_BG, icon=icon,
                                      text=short_title(w.caption) or w.resource_class))


class MixerFolder:
    """„Mixer“: je spielender Anwendung eine Kachel (Tippen: stumm) und ein Regler; neu
    gelesen nach jeder Aktion und alle ``MIXER_REFRESH_S`` Sekunden, solange offen."""

    def __init__(self, background: _Background, *,
                 call_later: Callable[[float, Callable[[], None]], None] | None,
                 on_change: Callable[[], None], paused: Callable[[], bool],
                 on_knobs_changed: Callable[[list[int]], None]) -> None:
        self._bg = background
        self._call_later = call_later
        self._on_change = on_change
        self._paused = paused                    # dunkel/getrennt: kein pactl im Takt
        self._on_knobs_changed = on_knobs_changed  # Regler, die jetzt einen anderen Stream regeln
        self.active = False
        self.page: VirtualPage | None = None
        self._gen = 0                 # jedes Oeffnen/Schliessen: spaete Takte verfallen
        self._streams: list[Stream] = []
        self._loading = False         # eine pactl-Abfrage laeuft
        self._again = False           # ... und danach gleich noch eine
        self._missed = False          # ein Takt fiel in die Pause

    def open(self) -> None:
        self.active = True
        self._gen += 1
        self._streams = []  # alte Werte waeren veraltet
        self.refresh()
        self._schedule(self._gen)
        self._rebuild()

    def close(self) -> None:
        self.active = False
        self._gen += 1
        self.page = None
        self._again = self._missed = False

    def resume(self) -> None:
        """Nach Entsperren/Wecken/Wiederverbinden: einmal nachlesen, wenn waehrend der Pause
        ein Takt ausgefallen ist."""
        if self._missed and self.active and not self._paused():
            self._missed = False
            self.refresh()

    def refresh(self) -> None:
        """Lautstaerken neu lesen (laeuft schon eine Abfrage: danach gleich noch eine)."""
        if self._loading:
            self._again = True
            return
        self._loading, self._again = True, False
        if not self._bg.run(self._bg.sources.streams, self._got_streams):
            self._loading = False

    def _got_streams(self, streams: object) -> None:
        self._loading = False
        if not self.active:
            return  # inzwischen geschlossen
        if streams is not None:
            self._streams = list(streams)
            self._rebuild()
            self._on_change()
        if self._again:
            self.refresh()

    def _schedule(self, gen: int) -> None:
        if self._call_later is not None:
            self._call_later(MIXER_REFRESH_S, lambda: self._tick(gen))

    def _tick(self, gen: int) -> None:
        if gen != self._gen or not self.active:
            return  # Ordner zu (oder neu geoeffnet: der hat seinen eigenen Takt)
        if self._paused():
            self._missed = True  # dunkel/getrennt: nicht abfragen, der Takt laeuft weiter
        else:
            self.refresh()
        self._schedule(gen)

    def _rebuild(self) -> None:
        page, buttons = _folder_page(DynamicKind.MIXER)
        for i, s in enumerate(self._streams[:MAX_TILES], start=1):
            buttons[i] = Assignment({"type": "stream_mute", "index": s.index},
                                    ButtonImage(bg=MUTED_BG if s.muted else STREAM_BG,
                                                icon=icon_ref(s.icon),
                                                text=f"{s.name} {_compact(s)}"))
        old = self.page.encoders if self.page is not None else None
        knobs = self._streams[:ENCODERS]
        encoders = [Encoder(rotate={"type": "stream_volume", "index": s.index},
                            press={"type": "stream_mute", "index": s.index}, label=s.name,
                            strip=STRIP_BAR) for s in knobs]
        encoders += [Encoder() for _ in range(ENCODERS - len(encoders))]
        self.page = VirtualPage(page, encoders,
                                {i: (s.value, s.percent) for i, s in enumerate(knobs)})
        if old is not None:  # Liste verschoben: Gesammeltes gehoerte zum vorigen Stream
            changed = [i for i, (a, b) in enumerate(zip(old, encoders)) if a.rotate != b.rotate]
            if changed:
                self._on_knobs_changed(changed)


class DynamicFolders:
    """Welcher dynamische Ordner offen ist und seine erzeugte Seite."""

    def __init__(self, sources: DynamicSources, *, post: Callable[[Callable[[], None]], None],
                 call_later: Callable[[float, Callable[[], None]], None] | None,
                 on_change: Callable[[], None],
                 paused: Callable[[], bool] = lambda: False,
                 on_knobs_changed: Callable[[list[int]], None] = lambda knobs: None) -> None:
        self._worker: Worker | None = None
        if sources.spawn is None:
            self._worker = Worker("dynamic-folder", threads=WORKER_THREADS)
            sources = replace(sources, spawn=self._worker.submit)
        background = _Background(sources, post)
        self._folders: dict[DynamicKind, WindowsFolder | MixerFolder] = {
            DynamicKind.WINDOWS: WindowsFolder(background, on_change),
            DynamicKind.MIXER: MixerFolder(background, call_later=call_later,
                                           on_change=on_change, paused=paused,
                                           on_knobs_changed=on_knobs_changed)}
        self.kind: DynamicKind | None = None

    def _open_folder(self) -> WindowsFolder | MixerFolder | None:
        return self._folders[self.kind] if self.kind is not None else None

    def page(self) -> VirtualPage | None:
        folder = self._open_folder()
        return folder.page if folder is not None else None

    def open(self, kind: object) -> bool:
        """Ordner ``kind`` zeigen (ein anderer offener wird ersetzt); ``False`` bei
        unbekannter Art."""
        if kind not in NAMES:
            log.warning("Dynamischen Ordner %r gibt es nicht", kind)
            return False
        self.close()
        self.kind = DynamicKind(kind)
        self._folders[self.kind].open()
        return True

    def close(self) -> bool:
        """``True``, wenn ein Ordner offen war."""
        folder = self._open_folder()
        if folder is None:
            return False
        folder.close()
        self.kind = None
        return True

    def set_windows(self, windows: Iterable[WindowInfo]) -> None:
        self._folders[DynamicKind.WINDOWS].set_windows(list(windows))

    def resume(self) -> None:
        """Nach Entsperren/Wecken/Wiederverbinden: im Mixer einmal nachlesen, wenn waehrend der
        Pause ein Takt ausgefallen ist."""
        self._folders[DynamicKind.MIXER].resume()

    def shutdown(self) -> None:
        """Eigenen Worker beenden (Dienstende); noch nicht begonnene Abfragen entfallen."""
        if self._worker is not None:
            self._worker.shutdown(cancel=True)

    def after_action(self) -> None:
        """Eine Aktion ist fertig: im Mixer die Werte neu lesen."""
        mixer = self._folders[DynamicKind.MIXER]
        if mixer.active:
            mixer.refresh()
