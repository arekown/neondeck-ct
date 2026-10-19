"""Einstellungsfenster im Testprozess: ``ConfigWindow`` direkt an einer lokalen ``Engine``
(Fake-Executor, mitgeschriebene Zeichnungen, mitgezaehlte Speicherungen) und Klick-Helfer.

Die Fixtures ``window_rig`` (ein Profil mit Belegungen) und ``profiles_rig`` (zwei Profile,
fuer Profilverwaltung und Auswahllisten) dazu stehen in ``conftest.py``.
"""
from __future__ import annotations

from types import SimpleNamespace

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from neondeck.editor.windows.config_window import ConfigWindow
from neondeck.profile.model import (
    Assignment,
    ButtonImage,
    Encoder,
    Profile,
    TouchPage,
    Workspace,
)
from neondeck.profile.store import ProfileStore

from .engine_rig import make_engine
from .fakes import FakeExecutor


class SpyStore(ProfileStore):
    def __init__(self, dir):
        super().__init__(dir)
        self.saved = []

    def save(self, p):
        self.saved.append(p.id)
        super().save(p)


def make_window_profile():
    p = Profile.empty()
    ws1 = p.workspaces[0]
    ws1.touch_pages[0].buttons[5] = Assignment({"type": "run", "command": "firefox"},
                                               ButtonImage(text="Firefox"))
    ws1.encoders[0] = Encoder(rotate={"type": "volume"}, press={"type": "mute_toggle"},
                              label="Lautstärke")
    p.workspaces.append(Workspace("ws2", "Zwei", [TouchPage("p1", "Seite 1"),
                                                  TouchPage("p2", "Seite 2")]))
    p.round[7] = Assignment({"type": "workspace", "id": "ws1"})
    return p


def two_workspace_profile(pid="default", name="Standard"):
    p = Profile.empty(pid, name)
    p.workspaces.append(Workspace("ws2", "Zwei", [TouchPage("p1", "Seite 1")]))
    return p


def _rig(home, profile: Profile, others=(), size=(1300, 850)):
    """Pruefstand (Generator fuer die Fixtures): ``store``, ``engine``, ``win``, ``draws``,
    ``ex`` (zuletzt angelegter Executor), ``switched`` (Profilwechsel), ``refuse_switch``."""
    store = SpyStore(home / "config" / "profiles")
    for p in (profile, *others):
        store.save(p)
    store.saved.clear()
    r = SimpleNamespace(store=store, draws=[], ex=None, switched=[], refuse_switch=False)

    def factory(engine_call, on_result):
        r.ex = FakeExecutor(engine_call, on_result)
        return r.ex

    r.engine = make_engine(profile, lambda d, b: r.draws.append(d), executor_factory=factory)

    def switch(pid):  # wie App.switch_profile (dort getestet): laden, an die Engine geben
        if r.refuse_switch:  # wie eine App, die ablehnt (z. B. kaputtes Profil)
            return
        r.switched.append(pid)
        r.engine.set_profile(store.load(pid))

    r.win = ConfigWindow(store, r.engine, switch)
    r.win.resize(*size)
    r.win.show()
    QApplication.processEvents()
    yield r
    r.win.close()
    r.win.deleteLater()


def window_rig(home):
    yield from _rig(home, make_window_profile())


def profiles_rig(home):
    """Zwei Profile: „default“ (zwei Arbeitsbereiche, aktiv) und „spiel“."""
    yield from _rig(home, two_workspace_profile(), [Profile.empty("spiel", "Spiele")],
                    size=(1400, 850))


def click(rig, ref):
    view = rig.win.device_view
    QTest.mouseClick(view, Qt.MouseButton.LeftButton, pos=view.control_rect(ref).center())
    QApplication.processEvents()


def choose_type(form, name):
    combo = form.type_combo
    i = combo.findData(name)
    assert i >= 0, name
    combo.setCurrentIndex(i)


def page(rig, ws=0, index=0):
    return rig.engine.profile.workspaces[ws].touch_pages[index]
