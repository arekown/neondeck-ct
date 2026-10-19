"""Aktion „Konsole-Layout“: Layoutdateien, Platzierung, Titel ueber Konsole-D-Bus, Text im
Editor (nie echte Konsole: Ersatz fuer Popen und qdbus)."""
import json

import pytest

from neondeck.actions import execute, konsole
from neondeck.actions.terminal_windows import (
    clean_windows,
    windows_from_text,
    windows_to_text,
)
from neondeck.core.placement import PlacementBook
from neondeck.editor.widgets.param_widgets import TerminalsEdit
from support.fakes import FakePopen, FakeRun, make_ctx

WINDOWS = [{"title": "Lokal", "place": "top_left", "commands": ["htop"]},
           {"title": "Server", "place": "top_right", "split": "vertical", "screen": "DP-2",
            "commands": ["", "ssh 192.0.2.10", "ssh 192.0.2.11"]}]


class ReadingPopen(FakePopen):
    """Liest die Layoutdatei beim Start (danach loescht die Aktion sie)."""

    def __init__(self, **kw):
        super().__init__(**kw)
        self.layouts = []

    def __call__(self, argv, **kw):
        proc = super().__call__(argv, **kw)
        with open(argv[argv.index("--layout") + 1], encoding="utf-8") as f:
            self.layouts.append(json.load(f))
        return proc


class AutoPlacer:
    """``ctx.place``, bei dem KWin jedes Fenster sofort meldet (Ticket gleich erledigt)."""

    def __init__(self):
        self.book = PlacementBook()
        self.asked = []

    def __call__(self, app, screen, place):
        self.asked.append((app, screen, place))
        ticket = self.book.expect(app, screen, place)
        if ticket is not None:
            ticket.done.set()
        return ticket


@pytest.fixture(autouse=True)
def _runtime_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))


def quick_ctx(**kw):
    """Kontext ohne Warten (Konsole meldet sich in den Tests sofort oder nie)."""
    return make_ctx(sleep=lambda s: None, **kw)


def test_layout_opens_windows_in_order_with_titles(tmp_path):
    popen, placer = ReadingPopen(pids=[501, 502]), AutoPlacer()
    run = FakeRun({"sessionList": (0, "1\n")})
    r = execute({"type": "terminal_layout", "screen": "DP-3", "windows": WINDOWS},
                quick_ctx(run=run, popen=popen, place=placer))
    assert r.ok, r.message
    assert [c[0][:3] for c in popen.calls] == [["konsole", "--separate", "--layout"]] * 2
    assert popen.layouts == [
        {"Orientation": "Horizontal", "Widgets": [{"SessionRestoreId": 0, "Command": "htop"}]},
        {"Orientation": "Vertical", "Widgets": [
            {"SessionRestoreId": 0}, {"SessionRestoreId": 0, "Command": "ssh 192.0.2.10"},
            {"SessionRestoreId": 0, "Command": "ssh 192.0.2.11"}]}]
    # Fenster-Bildschirm vor dem der Aktion; Konsole-Fenster passen ueber die Desktop-ID
    assert placer.asked == [("org.kde.konsole", "DP-3", "top_left"),
                            ("org.kde.konsole", "DP-2", "top_right")]
    titles = [c for c in run.calls if "setTabTitleFormat" in " ".join(c)]
    assert titles[:2] == [
        ["qdbus", "org.kde.konsole-501", "/Sessions/1", "org.kde.konsole.Session.setTabTitleFormat",
         "0", "Lokal"],
        ["qdbus", "org.kde.konsole-501", "/Sessions/1", "org.kde.konsole.Session.setTabTitleFormat",
         "1", "Lokal"]]
    assert titles[-1][1] == "org.kde.konsole-502" and titles[-1][-1] == "Server"
    assert list(tmp_path.glob("neondeck-ct-layout-*")) == []  # Layoutdateien weg


def test_layout_without_window_watcher_and_errors(tmp_path):
    # ohne KWin: startet trotzdem, wartet auf Konsoles D-Bus statt auf das Fenster
    popen = ReadingPopen(pids=[7])
    run = FakeRun({"sessionList": (0, "1 2\n")})
    win = {"title": "A;B", "commands": "top"}
    assert execute({"type": "terminal_layout", "windows": [win]},
                   quick_ctx(run=run, popen=popen)).ok
    sessions = {c[2] for c in run.calls if "setTabTitleFormat" in " ".join(c)}
    assert sessions == {"/Sessions/1", "/Sessions/2"}
    # Konsole meldet sich nie: kein Titel, aber kein Fehler (begrenzt oft gefragt)
    run = FakeRun({"sessionList": (1, "")})
    assert execute({"type": "terminal_layout", "windows": [win]},
                   quick_ctx(run=run, popen=ReadingPopen(pids=[8]))).ok
    assert len(run.calls) == konsole.SESSION_TRIES
    # keine Fenster / Konsole fehlt
    r = execute({"type": "terminal_layout", "windows": []}, quick_ctx())
    assert not r.ok and "Keine Fenster" in r.message
    r = execute({"type": "terminal_layout", "windows": [win]},
                quick_ctx(popen=FakePopen(missing=("konsole",))))
    assert not r.ok and "konsole" in r.message
    assert list(tmp_path.glob("neondeck-ct-layout-*")) == []


def test_windows_text_round_trip():
    text = windows_to_text(WINDOWS)
    assert text == ("Lokal | top_left\n    htop\n\n"
                    "Server | top_right | vertical | DP-2\n    -\n    ssh 192.0.2.10\n"
                    "    ssh 192.0.2.11")
    assert windows_from_text(text) == WINDOWS
    # Felder nach Inhalt, Gross/klein egal; ohne Befehl eine Shell
    assert windows_from_text("Notizen | rechts | MAXIMIZE\n\n  \n") == [
        {"title": "Notizen", "place": "maximize", "commands": [""], "screen": "rechts"}]
    assert clean_windows([{"title": 3, "place": "x"}, "kaputt"]) == [
        {"title": "3", "place": "none", "commands": [""]}]


def test_terminals_edit_widget():
    w = TerminalsEdit()
    w.set_value(WINDOWS)
    assert w.value() == WINDOWS
    w.setPlainText("Eins | left\n    ls")
    w.set_value(w.value())  # gleicher Inhalt: Text bleibt wie getippt
    assert w.toPlainText() == "Eins | left\n    ls"


TABBED = [{"title": "SSH", "place": "left", "tabs": [
    {"title": "PC1", "command": ""},
    {"title": "PC2", "command": "ssh user@server1"},
    {"title": "PC3", "command": "ssh user@server2"}]}]


class TabsPopen(FakePopen):
    """Liest die Register-Datei beim Start."""

    def __init__(self, **kw):
        super().__init__(**kw)
        self.files = []

    def __call__(self, argv, **kw):
        proc = super().__call__(argv, **kw)
        with open(argv[argv.index("--tabs-from-file") + 1], encoding="utf-8") as f:
            self.files.append(f.read())
        return proc


def test_tabs_window_file_and_last_tab(tmp_path):
    popen = TabsPopen(pids=[601])
    run = FakeRun({"sessionList": (0, "1\n2\n3\n4\n")})
    r = execute({"type": "terminal_layout", "windows": TABBED},
                quick_ctx(run=run, popen=popen))
    assert r.ok, r.message
    argv = popen.calls[0][0]
    assert argv[:2] == ["konsole", "--separate"] and "--layout" not in argv
    assert argv[argv.index("-e"):] == ["-e", "sh", "-c",
                                       'ssh user@server2; exec "$SHELL"']
    assert popen.files == ['title: PC1\n'
                           'title: PC2;; command: ssh user@server1; exec "$SHELL"\n']
    # Titel des letzten Registers ueber D-Bus (Session 3), erstes Register nach vorn
    titles = [c for c in run.calls if "setTabTitleFormat" in " ".join(c)]
    assert [(c[2], c[-2], c[-1]) for c in titles] == [("/Sessions/3", "0", "PC3"),
                                                       ("/Sessions/3", "1", "PC3")]
    assert run.calls[-1][-2:] == ["org.kde.konsole.Window.setCurrentSession", "1"]
    assert list(tmp_path.glob("neondeck-ct-*")) == []


def test_tabs_single_and_shell_tab():
    from neondeck.actions.konsole import tabs_argv
    assert tabs_argv({"title": "", "tabs": [{"title": "A", "command": ""}]}, "x") == [
        "konsole", "--separate"]
    assert tabs_argv({"title": "", "tabs": [{"title": "A", "command": "top"}]}, "x")[2:3] == ["-e"]


def test_tabs_text_round_trip_and_clean():
    text = windows_to_text(TABBED)
    assert text == ("SSH | left | tabs\n    PC1\n    PC2 > ssh user@server1\n"
                    "    PC3 > ssh user@server2")
    assert windows_from_text(text) == TABBED
    odd = [{"title": "W", "place": "none", "screen": "DP-1", "tabs": [
        {"title": "", "command": ""}, {"title": "", "command": "top > x"}]}]
    assert windows_from_text(windows_to_text(odd)) == odd
    # tabs hat Vorrang vor commands/split; leere tabs fallen zurueck
    assert clean_windows([{"title": "a", "split": "vertical", "commands": ["x"],
                                    "tabs": [{"command": "y"}]}]) == [
        {"title": "a", "place": "none", "tabs": [{"title": "", "command": "y"}]}]
    assert clean_windows([{"title": "a", "tabs": []}])[0]["commands"] == [""]
    w = TerminalsEdit()
    w.set_value(TABBED)
    assert w.value() == TABBED
