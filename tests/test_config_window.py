"""Einstellungsfenster (offscreen): Geraetebild, Belegung, Seiten, Tastenaufnahme."""
import json

import pytest
import shiboken6
from PySide6.QtCore import QMimeData, QPointF, Qt
from PySide6.QtGui import (
    QAction,
    QColor,
    QDragEnterEvent,
    QDropEvent,
    QIcon,
    QStandardItem,
)
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QColorDialog, QInputDialog, QMenu, QMessageBox, QWidget

from neondeck.actions.base import Result
from neondeck.device.layout import ControlRef
from neondeck.editor.editing.mime import ACTION_MIME
from neondeck.editor.widgets.action_form import ActionForm
from neondeck.editor.widgets.icon_picker import IconPicker
from neondeck.profile.model import Assignment, Encoder, Profile
from neondeck.ui import theme
from support.waiting import wait_until
from support.window import choose_type, click, page

pytestmark = pytest.mark.usefixtures("home")


# --- Belegen ---------------------------------------------------------------------------

def test_select_touch_and_assign_run(window_rig):
    selected = []
    window_rig.win.device_view.selected.connect(selected.append)
    click(window_rig, ControlRef("touch", 0))
    assert selected == [ControlRef("touch", 0)]
    form = window_rig.win.editor.content.action_form
    choose_type(form, "run")
    QTest.keyClicks(form.field("command"), "kate")
    window_rig.win.flush()
    assert page(window_rig).buttons[0].action == {"type": "run", "command": "kate"}
    assert window_rig.store.saved and window_rig.store.saved[-1] == "default"
    assert window_rig.store.load("default").workspaces[0].touch_pages[0].buttons[0].action == {
        "type": "run", "command": "kate"}


def test_edits_are_debounced_then_saved(window_rig):
    click(window_rig, ControlRef("touch", 1))
    form = window_rig.win.editor.content.action_form
    choose_type(form, "open")
    QTest.keyClicks(form.field("target"), "https://kde.org")
    assert window_rig.store.saved == []          # noch nicht: jeder Tastendruck wuerde speichern
    assert wait_until(lambda: window_rig.store.saved)
    assert page(window_rig).buttons[1].action == {"type": "open", "target": "https://kde.org"}


def test_change_keeps_current_workspace_and_page_on_device(window_rig):
    window_rig.win.toolbar.workspace_combo.setCurrentIndex(1)
    window_rig.win.page_bar.tabs.setCurrentIndex(1)
    assert (window_rig.engine.workspace_id, window_rig.engine.page_index) == ("ws2", 1)
    click(window_rig, ControlRef("touch", 2))
    choose_type(window_rig.win.editor.content.action_form, "mute_toggle")
    n = len(window_rig.draws)
    window_rig.win.flush()
    assert (window_rig.engine.workspace_id, window_rig.engine.page_index) == ("ws2", 1)
    assert len(window_rig.draws) > n  # Geraet zeigt die Aenderung sofort
    assert page(window_rig, 1, 1).buttons[2].action == {"type": "mute_toggle"}


def test_edit_stays_on_page_shown_in_editor(window_rig):
    """Blaettert das Geraet waehrend der Eingabe, landet die Aenderung trotzdem auf der
    Seite, die der Editor zeigt (nicht auf der neuen Seite des Geraets)."""
    click(window_rig, ControlRef("touch", 0))
    form = window_rig.win.editor.content.action_form
    choose_type(form, "run")
    # am Geraet, Fenster hat noch nicht nachgezogen
    window_rig.engine.call("workspace", {"id": "ws2"})
    QTest.keyClicks(form.field("command"), "kate")
    window_rig.win.flush()
    assert page(window_rig).buttons[0].action == {"type": "run", "command": "kate"}
    assert page(window_rig, 1, 0).buttons[0] is None
    window_rig.win.sync_from_engine()
    assert window_rig.win.toolbar.workspace_combo.currentIndex() == 1
    assert window_rig.win.editor.content.action_form.value() is None  # Editor zeigt jetzt ws2


def test_tile_image_fields(window_rig, monkeypatch, tmp_path):
    click(window_rig, ControlRef("touch", 5))
    ed = window_rig.win.editor.content
    assert ed.image_editor.text_edit.text() == "Firefox"
    ed.image_editor.text_edit.clear()
    QTest.keyClicks(ed.image_editor.text_edit, "Web")
    monkeypatch.setattr(QColorDialog, "getColor", staticmethod(lambda *a, **k: QColor("#204060")))
    ed.image_editor.bg_button.click()
    icon = tmp_path / "icon.png"
    icon.write_bytes(b"")
    monkeypatch.setattr(IconPicker, "choose", staticmethod(lambda *a, **k: f"file:{icon}"))
    ed.image_editor.icon_button.click()
    window_rig.win.flush()
    img = page(window_rig).buttons[5].image
    assert (img.text, img.bg, img.icon) == ("Web", "#204060", f"file:{icon}")
    assert page(window_rig).buttons[5].action == {"type": "run", "command": "firefox"}


def test_knob_via_strip_rotate_press_label(window_rig):
    click(window_rig, ControlRef("strip", 4))
    assert window_rig.win.selected == ControlRef("knob", 4)
    ed = window_rig.win.editor.content
    rotate_types = {ed.turn.rotate_form.type_combo.itemData(i)
                    for i in range(ed.turn.rotate_form.type_combo.count())}
    assert "volume" in rotate_types and "run" not in rotate_types
    choose_type(ed.turn.rotate_form, "adjust_hotkey")
    left = ed.turn.rotate_form.field("left")
    QTest.keyClick(left, Qt.Key.Key_Minus, Qt.KeyboardModifier.ControlModifier)
    choose_type(ed.press_form, "mute_toggle")
    QTest.keyClicks(ed.label_edit, "Zoom")
    window_rig.win.flush()
    enc = window_rig.engine.profile.workspaces[0].encoders[4]
    assert enc.rotate == {"type": "adjust_hotkey", "left": "KEY_LEFTCTRL+KEY_SLASH"}
    assert enc.press == {"type": "mute_toggle"} and enc.label == "Zoom"


def test_wheel_display_and_rotate(window_rig):
    click(window_rig, ControlRef("wheel", 0))
    ed = window_rig.win.editor.content
    ed.display_combo.setCurrentIndex(ed.display_combo.findData("label"))
    QTest.keyClicks(ed.label_edit, "CT")
    choose_type(ed.turn.rotate_form, "volume")
    window_rig.win.flush()
    wheel = window_rig.engine.profile.workspaces[0].wheel
    assert (wheel.display, wheel.label, wheel.rotate) == ("label", "CT", {"type": "volume"})


def test_square_button_uses_layout_code(window_rig):
    click(window_rig, ControlRef("square", 1))  # oben rechts im linken Block = Code 18
    choose_type(window_rig.win.editor.content.action_form, "mute_toggle")
    window_rig.win.flush()
    assert window_rig.engine.profile.square[18].action == {"type": "mute_toggle"}
    # Tasten ohne Display bekommen eine eigene Bezeichnung statt des Aktionsnamens
    window_rig.win.editor.content.label_edit.setText("Ton aus")
    window_rig.win.flush()
    assert window_rig.engine.profile.square[18].image.text == "Ton aus"
    assert window_rig.win.device_view.preview.control_label(ControlRef("square", 1)) == "Ton aus"


def test_clear_removes_assignment(window_rig):
    click(window_rig, ControlRef("touch", 5))
    window_rig.win.editor.clear_button.click()
    window_rig.win.flush()
    assert page(window_rig).buttons[5] is None
    click(window_rig, ControlRef("knob", 0))
    window_rig.win.editor.clear_button.click()
    window_rig.win.flush()
    assert window_rig.engine.profile.workspaces[0].encoders[0] == Encoder()


def test_unknown_params_are_kept(window_rig):
    page(window_rig).buttons[3] = Assignment({"type": "unsupported", "original": "TaskSwitcher"})
    click(window_rig, ControlRef("touch", 3))
    form = window_rig.win.editor.content.action_form
    assert form.type_combo.currentData() == "unsupported"
    assert form.value() == {"type": "unsupported", "original": "TaskSwitcher"}


def test_macro_steps_with_nested_form(window_rig):
    click(window_rig, ControlRef("touch", 0))
    form = window_rig.win.editor.content.action_form
    choose_type(form, "macro")
    steps = form.field("steps")
    steps.add_button.click()
    choose_type(steps.step_form, "hotkey")
    QTest.keyClick(steps.step_form.field("keys"), Qt.Key.Key_C, Qt.KeyboardModifier.ControlModifier)
    steps.add_button.click()
    choose_type(steps.step_form, "sleep")
    steps.up_button.click()  # Warten nach oben
    window_rig.win.flush()
    assert page(window_rig).buttons[0].action == {"type": "macro", "steps": [
        {"type": "sleep", "ms": 100}, {"type": "hotkey", "keys": "KEY_LEFTCTRL+KEY_C"}]}
    steps.list.setCurrentRow(0)
    steps.remove_button.click()
    window_rig.win.flush()
    assert page(window_rig).buttons[0].action["steps"] == [
        {"type": "hotkey", "keys": "KEY_LEFTCTRL+KEY_C"}]


def test_test_button_runs_through_engine_executor(window_rig):
    click(window_rig, ControlRef("touch", 5))
    window_rig.win.editor.test_button.click()
    assert window_rig.ex.calls == [
        (ControlRef("touch", 5), {"type": "run", "command": "firefox"}, 0, True)]
    click(window_rig, ControlRef("knob", 0))
    window_rig.win.editor.test_button.click()
    assert window_rig.ex.calls[-1] == (ControlRef("knob", 0), {"type": "mute_toggle"}, 0, True)
    # Ergebnis kommt spaeter, kein Fehler
    window_rig.ex.on_result(ControlRef("knob", 0), Result(True))


def drop(view, ref, action):
    """Ziehen-Ablegen wie Qt es zustellt: erst Betreten (muss angenommen werden), dann Ablegen."""
    mime = QMimeData()
    mime.setData(ACTION_MIME, json.dumps(action).encode())
    pos = QPointF(view.control_rect(ref).center())
    enter = QDragEnterEvent(pos.toPoint(), Qt.DropAction.CopyAction, mime,
                            Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(view, enter)
    assert enter.isAccepted()
    QApplication.sendEvent(view, QDropEvent(pos, Qt.DropAction.CopyAction, mime,
                                            Qt.MouseButton.LeftButton,
                                            Qt.KeyboardModifier.NoModifier))


def test_drop_action_on_tile(window_rig):
    drop(window_rig.win.device_view, ControlRef("touch", 7), {"type": "run", "command": "dolphin"})
    window_rig.win.flush()
    assert page(window_rig).buttons[7].action == {"type": "run", "command": "dolphin"}
    assert window_rig.win.selected == ControlRef("touch", 7)


def test_drop_rotate_action_on_knob_goes_to_rotate(window_rig):
    drop(window_rig.win.device_view, ControlRef("knob", 2), {"type": "brightness"})
    drop(window_rig.win.device_view, ControlRef("strip", 2), {"type": "mute_toggle"})
    window_rig.win.flush()
    enc = window_rig.engine.profile.workspaces[0].encoders[2]
    assert (enc.rotate, enc.press) == ({"type": "brightness"}, {"type": "mute_toggle"})


def test_drop_rejects_wrong_kind_and_bad_payload(window_rig):
    drop(window_rig.win.device_view, ControlRef("wheel", 0), {"type": "run", "command": "x"})
    drop(window_rig.win.device_view, ControlRef("touch", 0), {"type": "volume"})
    view = window_rig.win.device_view
    mime = QMimeData()
    mime.setData(ACTION_MIME, b"kein json")
    pos = QPointF(view.control_rect(ControlRef("touch", 1)).center())
    QApplication.sendEvent(view, QDragEnterEvent(pos.toPoint(), Qt.DropAction.CopyAction, mime,
                                                 Qt.MouseButton.LeftButton,
                                                 Qt.KeyboardModifier.NoModifier))
    QApplication.sendEvent(view, QDropEvent(pos, Qt.DropAction.CopyAction, mime,
                                            Qt.MouseButton.LeftButton,
                                            Qt.KeyboardModifier.NoModifier))
    window_rig.win.flush()
    assert window_rig.engine.profile.workspaces[0].wheel.rotate is None
    assert page(window_rig).buttons[0] is None and page(window_rig).buttons[1] is None
    assert window_rig.store.saved == []


# --- Seiten, Arbeitsbereiche, Profile ------------------------------------------------

def test_add_page(window_rig):
    ws = window_rig.engine.profile.workspaces[0]
    assert len(ws.touch_pages) == 1
    window_rig.win.page_bar.add_button.click()
    assert len(ws.touch_pages) == 2
    assert ws.touch_pages[1].buttons == [None] * 12
    assert ws.touch_pages[1].id != ws.touch_pages[0].id
    assert window_rig.win.page_bar.tabs.count() == 2 and window_rig.win.page_bar.tabs.currentIndex() == 1
    assert window_rig.engine.page_index == 1
    assert window_rig.store.load("default").workspaces[0].touch_pages[1].name == "Seite 2"


def test_rename_and_remove_page(window_rig, monkeypatch):
    window_rig.win.page_bar.add_button.click()
    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: ("Extra", True)))
    window_rig.win.page_bar.rename_button.click()
    ws = window_rig.engine.profile.workspaces[0]
    assert ws.touch_pages[1].name == "Extra" and window_rig.win.page_bar.tabs.tabText(1) == "Extra"
    ws.touch_pages[1].buttons[0] = Assignment({"type": "clock"})
    monkeypatch.setattr(QMessageBox, "question",
                        staticmethod(lambda *a, **k: QMessageBox.StandardButton.No))
    window_rig.win.page_bar.remove_button.click()
    assert len(ws.touch_pages) == 2  # belegte Seite: Rueckfrage mit „Nein“
    monkeypatch.setattr(QMessageBox, "question",
                        staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))
    window_rig.win.page_bar.remove_button.click()
    assert len(ws.touch_pages) == 1 and window_rig.engine.page_index == 0
    assert not window_rig.win.page_bar.remove_button.isEnabled()  # letzte Seite bleibt


def test_workspace_combo_drives_device(window_rig):
    assert [window_rig.win.toolbar.workspace_combo.itemText(i) for i in range(2)] == ["Allgemein", "Zwei"]
    window_rig.win.toolbar.workspace_combo.setCurrentIndex(1)
    assert window_rig.engine.workspace_id == "ws2"
    assert window_rig.win.page_bar.tabs.count() == 2


def test_window_follows_device_navigation(window_rig):
    window_rig.engine.call("workspace", {"id": "ws2"})
    window_rig.engine.call("page_next", {})
    window_rig.win.sync_from_engine()
    assert window_rig.win.toolbar.workspace_combo.currentIndex() == 1
    assert window_rig.win.page_bar.tabs.currentIndex() == 1


def test_profile_combo_switches_profile(window_rig):
    other = Profile.empty("spiel", "Spiele")
    window_rig.store.save(other)
    window_rig.win.reload_profiles()
    combo = window_rig.win.toolbar.profile_combo
    combo.setCurrentIndex(combo.findData("spiel"))
    assert window_rig.switched == ["spiel"]
    assert window_rig.engine.profile.id == "spiel"
    assert combo.currentData() == "spiel"


def test_profile_combo_failed_switch_shows_current_again(window_rig):
    window_rig.store.save(Profile.empty("spiel", "Spiele"))
    window_rig.win.reload_profiles()
    window_rig.refuse_switch = True  # App lehnt ab (z. B. kaputtes Profil)
    combo = window_rig.win.toolbar.profile_combo
    combo.setCurrentIndex(combo.findData("spiel"))
    assert window_rig.engine.profile.id == "default"
    assert combo.currentData() == "default"
    assert "„Spiele“" in window_rig.win.statusBar().currentMessage()  # Name, nicht die Id


# --- Systemdesign ----------------------------------------------------------------------

def test_no_stylesheet(window_rig):
    for ref in (ControlRef("touch", 0), ControlRef("knob", 0), ControlRef("wheel", 0),
                ControlRef("round", 0)):
        click(window_rig, ref)
    choose_type(window_rig.win.editor.content.action_form, "macro")
    window_rig.win.editor.content.action_form.field("steps").add_button.click()
    assert QApplication.instance().styleSheet() == ""
    assert window_rig.win.styleSheet() == ""
    widgets = window_rig.win.findChildren(QWidget)
    assert len(widgets) > 30
    assert [w for w in widgets if w.styleSheet()] == []
    assert not window_rig.win.windowFlags() & Qt.WindowType.FramelessWindowHint


# --- Fix-Runde 1 ------------------------------------------------------------------------

def test_click_and_drop_use_page_shown_in_window(window_rig):
    page(window_rig).buttons[3] = Assignment({"type": "run", "command": "kate"})
    window_rig.win.sync_from_engine(force=True)
    window_rig.engine.call("workspace", {"id": "ws2"})  # am Geraet; Fenster zeigt noch ws1
    click(window_rig, ControlRef("touch", 3))
    assert window_rig.win.editor.content.action_form.value() == {"type": "run", "command": "kate"}
    drop(window_rig.win.device_view, ControlRef("touch", 4), {"type": "mute_toggle"})
    window_rig.win.flush()
    assert page(window_rig).buttons[4].action == {"type": "mute_toggle"}
    assert page(window_rig, 1, 0).buttons[4] is None


def test_failed_save_is_retried_and_never_raises(window_rig):
    real_save = window_rig.store.save
    calls = []

    def broken(p):
        calls.append(p.id)
        raise PermissionError("schreibgeschuetzt")

    window_rig.store.save = broken
    click(window_rig, ControlRef("round", 2))
    choose_type(window_rig.win.editor.content.action_form, "mute_toggle")
    window_rig.win.flush()  # darf nicht werfen (laeuft sonst im Timer-Slot)
    assert calls == ["default"]
    assert "Speichern fehlgeschlagen" in window_rig.win.statusBar().currentMessage()
    assert window_rig.engine.profile.round[9].action == {"type": "mute_toggle"}  # Geraet zeigt es
    window_rig.store.save = real_save
    window_rig.win.flush()  # naechster Versuch speichert
    assert window_rig.store.load("default").round[9].action == {"type": "mute_toggle"}


def test_test_button_on_live_tile_says_nothing_to_test(window_rig):
    page(window_rig).buttons[0] = Assignment({"type": "clock"})
    window_rig.win.sync_from_engine(force=True)
    click(window_rig, ControlRef("touch", 0))
    window_rig.win.editor.test_button.click()
    assert window_rig.win.statusBar().currentMessage() == "Keine Aktion zum Testen"
    assert window_rig.ex.calls == []


def test_drop_live_type_only_on_touch(window_rig):
    drop(window_rig.win.device_view, ControlRef("knob", 1), {"type": "stopwatch"})
    drop(window_rig.win.device_view, ControlRef("square", 0), {"type": "clock"})
    window_rig.win.flush()
    assert window_rig.engine.profile.workspaces[0].encoders[1].press is None
    assert window_rig.engine.profile.square[15] is None
    drop(window_rig.win.device_view, ControlRef("touch", 9), {"type": "clock"})
    window_rig.win.flush()
    assert page(window_rig).buttons[9].action == {"type": "clock"}


# --- Veraltete Qt-Wrapper ---------------------------------------------------------------

def _held_objects(obj, seen=None):
    """Alles, was ``obj`` ueber Attribute, Listen, Tupel und Dicts festhaelt."""
    seen = set() if seen is None else seen
    values = obj.__dict__.values() if hasattr(obj, "__dict__") else (
        obj.values() if isinstance(obj, dict) else obj)
    for value in values:
        if id(value) in seen:
            continue
        seen.add(id(value))
        yield value
        if isinstance(value, (list, tuple, set, dict)):
            yield from _held_objects(value, seen)


def test_destroyed_action_form_keeps_no_stale_qstandarditems():
    """Lebt das Python-Objekt eines ActionForm laenger als seine C++-Seite (Referenzzyklus,
    der GC ist noch nicht gelaufen), darf es keine QStandardItem-Wrapper festhalten: Qt
    loescht die Eintraege mit dem Modell, ohne dass PySide es merkt, vergibt die Adressen
    neu, und PySide liefert dann den alten Wrapper statt des neuen Objekts (so brach
    ``QMenu.addAction(icon, text, slot)`` in ConfigWindow mit "'QStandardItem' object has no
    attribute 'connect'")."""
    forms = []
    for _ in range(30):
        form = ActionForm()
        forms.append(form)      # Python-Seite bleibt, wie in einem noch offenen Zyklus
        shiboken6.delete(form)  # C++-Seite samt Modell und Eintraegen ist weg
    menu = QMenu()
    for _ in range(3000):  # neue QActions landen auf den freien Adressen der Eintraege
        action = menu.addAction(QIcon(), "x", lambda: None)
        assert type(action) is QAction
    stale = [o for f in forms for o in _held_objects(f) if isinstance(o, QStandardItem)]
    assert stale == []
    theme.apply(QApplication.instance(), "neutral")  # Theme-Wechsel trifft keine toten Formulare


def test_desktop_files_dropped_onto_tiles(window_rig, tmp_path):
    """.desktop-Verknuepfungen aus dem Dateimanager: Name und Bildpfad-Symbol uebernehmen,
    weitere Dateien auf die naechsten freien Felder, ein Rückgängig-Schritt."""
    from PIL import Image

    from neondeck.actions.base import execute
    from support.fakes import FakePopen, make_ctx
    icon = tmp_path / "icon.png"
    Image.new("RGB", (8, 8), "red").save(icon)
    app = tmp_path / "Projekt.desktop"
    app.write_text(f"[Desktop Entry]\nType=Application\nName=Mein Projekt\nExec=true\n"
                   f"Icon={icon}\n")
    link = tmp_path / "Plane.desktop"
    link.write_text("[Desktop Entry]\nType=Link\nName=Plane · Test\nIcon=view-task\n"
                    "URL=http://example.invalid\n")
    win = window_rig.win
    page = win.shown_ctx().page
    free_before = [i for i in range(1, 12) if page.buttons[i] is None]
    win.edit.files_dropped(ControlRef("touch", 0), [app, link])
    page = win.shown_ctx().page
    first = page.buttons[0]
    assert first.action == {"type": "open", "target": str(app)}
    assert first.image.text == "Mein Projekt" and first.image.icon == f"file:{icon}"
    second_index = free_before[0]  # naechstes freies Feld
    assert page.buttons[second_index].action == {"type": "open", "target": str(link)}
    assert page.buttons[second_index].image.text == "Plane · Test"
    assert page.buttons[second_index].image.icon is None  # Theme-Symbolname: nur Text
    assert win.undoing.stack().undo_label() == "Dateien ablegen"
    popen = FakePopen()
    assert execute(first.action, make_ctx(popen=popen)).ok
    assert popen.calls[-1][0] == ["kioclient", "exec", str(app)]
