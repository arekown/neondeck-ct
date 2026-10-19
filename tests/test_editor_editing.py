"""Tastenbild (Layouts, Schriften, Einfaerben), Editor-Felder, schnelles Bearbeiten."""
import json

import pytest
from PySide6.QtCore import QMimeData, QPointF, Qt
from PySide6.QtGui import QColor, QDragEnterEvent, QDropEvent, QKeySequence
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QColorDialog

from neondeck.device.layout import ROUND_CODES, ControlRef
from neondeck.editor.dialogs.profile_settings import ProfileSettingsDialog
from neondeck.editor.editing import clipboard
from neondeck.editor.editing.pages import FOLDER_FIELD_HINT
from neondeck.editor.editing.undo import UndoStack
from neondeck.editor.editing.undoing import STALE_UNDO
from neondeck.editor.widgets.action_form import ActionForm
from neondeck.editor.widgets.device_preview import PREVIEW_VALUE
from neondeck.editor.widgets.nav_targets import NavTargets
from neondeck.editor.widgets.param_widgets import Catalog
from neondeck.engine.painter import strip_image, strip_section
from neondeck.profile import edit
from neondeck.profile.model import (
    Assignment,
    ButtonImage,
    Encoder,
    EncoderLayer,
    TouchPage,
    Wheel,
)
from support.window import choose_type, click, page

pytestmark = pytest.mark.usefixtures("home")

FIREFOX = {"type": "run", "command": "firefox"}


def ws(rig, i=0):
    return rig.engine.profile.workspaces[i]


def show_workspace(rig, ws_id):
    rig.engine.call("workspace", {"id": ws_id})
    rig.win.sync_from_engine(force=True)


def ctrl_click(rig, ref):
    view = rig.win.device_view
    QTest.mouseClick(view, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.ControlModifier,
                     view.control_rect(ref).center())
    QApplication.processEvents()


def drag(view, src, dst, ctrl=False):
    """Ziehen zwischen Elementen, wie Qt es zustellt (Betreten, dann Ablegen)."""
    mime = view.drag_mime([src] if isinstance(src, ControlRef) else src)
    pos = QPointF(view.control_rect(dst).center())
    mods = Qt.KeyboardModifier.ControlModifier if ctrl else Qt.KeyboardModifier.NoModifier
    actions = Qt.DropAction.MoveAction | Qt.DropAction.CopyAction
    enter = QDragEnterEvent(pos.toPoint(), actions, mime, Qt.MouseButton.LeftButton, mods)
    QApplication.sendEvent(view, enter)
    assert enter.isAccepted()
    QApplication.sendEvent(view, QDropEvent(pos, actions, mime, Qt.MouseButton.LeftButton, mods))


def test_copy_paste_between_workspaces(window_rig):
    click(window_rig, ControlRef("touch", 5))
    window_rig.win.edit.copy_action.trigger()
    assert clipboard.has_items()
    show_workspace(window_rig, "ws2")
    click(window_rig, ControlRef("touch", 2))
    window_rig.win.edit.paste_action.trigger()
    window_rig.win.flush()
    assert ws(window_rig, 1).touch_pages[0].buttons[2].action == FIREFOX
    assert ws(window_rig, 1).touch_pages[0].buttons[2].image.text == "Firefox"
    assert ws(window_rig, 0).touch_pages[0].buttons[5].action == FIREFOX  # Kopie, Quelle bleibt
    saved = window_rig.store.load("default")
    assert saved.workspaces[1].touch_pages[0].buttons[2].action == FIREFOX
    # Ausschneiden + Einfuegen: Regler-Belegung wandert, unpassendes Ziel wird abgelehnt
    show_workspace(window_rig, "ws1")
    click(window_rig, ControlRef("knob", 0))
    window_rig.win.edit.cut_action.trigger()
    assert ws(window_rig, 0).encoders[0] == Encoder()
    click(window_rig, ControlRef("touch", 0))
    window_rig.win.edit.paste_action.trigger()
    assert page(window_rig).buttons[0] is None
    click(window_rig, ControlRef("knob", 3))
    window_rig.win.edit.paste_action.trigger()
    window_rig.win.flush()
    assert ws(window_rig, 0).encoders[3].label == "Lautstärke"


def test_drag_move_and_ctrl_copy(window_rig):
    view = window_rig.win.device_view
    drag(view, ControlRef("touch", 5), ControlRef("touch", 6))
    window_rig.win.flush()
    assert page(window_rig).buttons[5] is None and page(window_rig).buttons[6].action == FIREFOX
    drag(view, ControlRef("touch", 6), ControlRef("touch", 7), ctrl=True)
    window_rig.win.flush()
    assert page(window_rig).buttons[6].action == FIREFOX
    assert page(window_rig).buttons[7].action == FIREFOX
    # Verschieben auf eine belegte Taste tauscht
    page(window_rig).buttons[0] = Assignment({"type": "mute_toggle"})
    window_rig.win.sync_from_engine(force=True)
    drag(view, ControlRef("touch", 0), ControlRef("touch", 7))
    window_rig.win.flush()
    assert page(window_rig).buttons[7].action == {"type": "mute_toggle"}
    assert page(window_rig).buttons[0].action == FIREFOX
    # Touch -> runde Taste geht, Touch -> Regler nicht
    drag(view, ControlRef("touch", 0), ControlRef("round", 3), ctrl=True)
    drag(view, ControlRef("touch", 0), ControlRef("knob", 1))
    window_rig.win.flush()
    assert window_rig.engine.profile.round[10].action == FIREFOX
    assert ws(window_rig, 0).encoders[1] == Encoder()
    assert page(window_rig).buttons[0].action == FIREFOX


def test_multi_select_delete(window_rig):
    click(window_rig, ControlRef("touch", 1))
    choose_type(window_rig.win.editor.content.action_form, "mute_toggle")
    ctrl_click(window_rig, ControlRef("touch", 5))
    ctrl_click(window_rig, ControlRef("round", 0))
    view = window_rig.win.device_view
    assert view.selection() == [ControlRef("touch", 1), ControlRef("touch", 5),
                                ControlRef("round", 0)]
    ctrl_click(window_rig, ControlRef("round", 0))  # wieder abwaehlen
    assert view.selection() == [ControlRef("touch", 1), ControlRef("touch", 5)]
    view.setFocus()
    QTest.keyClick(view, Qt.Key.Key_Delete)
    window_rig.win.flush()
    assert page(window_rig).buttons[1] is None and page(window_rig).buttons[5] is None
    assert window_rig.engine.profile.round[7] is not None  # nicht gewaehlt: bleibt
    window_rig.win.undoing.undo_action.trigger()
    assert page(window_rig).buttons[1] is not None and page(window_rig).buttons[5].action == FIREFOX


def test_undo_redo_100(window_rig):
    stack = UndoStack()
    for i in range(105):
        stack.push({"n": i}, {"n": i + 1}, f"Schritt {i}")
    assert len(stack) == 100
    for _ in range(100):
        last = stack.undo()
    assert last == {"n": 5} and stack.undo() is None
    assert stack.redo() == {"n": 6}
    stack.push({"n": 6}, {"n": 7}, "a", merge="x")
    stack.push({"n": 7}, {"n": 8}, "a", merge="x")  # gleiche Eingabe: ein Schritt
    assert not stack.can_redo() and stack.undo() == {"n": 6}

    win = window_rig.win
    assert win.undoing.undo_action.shortcut() == QKeySequence(QKeySequence.StandardKey.Undo)
    assert QKeySequence("Ctrl+Shift+Z") in win.undoing.redo_action.shortcuts()
    ref = ControlRef("touch", 0)
    for i in range(105):  # jede Belegung ein eigener Schritt (neue Auswahl dazwischen)
        win.select(ref)
        win.editor.content.action_form.set_value({"type": "run", "command": f"c{i}"})
        win.editor.content.action_form.changed.emit()
    win.flush()
    assert page(window_rig).buttons[0].action["command"] == "c104"
    assert len(win.undoing.stack()) == 100
    for _ in range(100):
        win.undoing.undo_action.trigger()
    assert page(window_rig).buttons[0].action["command"] == "c4"
    assert not win.undoing.undo_action.isEnabled()
    win.undoing.redo_action.trigger()
    win.undoing.redo_action.trigger()
    assert page(window_rig).buttons[0].action["command"] == "c6"
    assert window_rig.store.load("default").workspaces[0].touch_pages[0].buttons[0].action[
        "command"] == "c6"
    assert win.editor.content.action_form.value()["command"] == "c6"  # Inspector zeigt den Stand
    # Tippen in einem Feld ist ein einziger Schritt
    win.select(ref)
    QTest.keyClicks(win.editor.content.action_form.field("command"), "xyz")
    win.flush()
    win.undoing.undo_action.trigger()
    assert page(window_rig).buttons[0].action["command"] == "c6"


def test_page_copy_paste(window_rig):
    menu = window_rig.win.pages.page_menu(0)
    texts = [a.text() for a in menu.actions()]
    assert "Seite kopieren" in texts and "Als Ordnerseite" in texts
    next(a for a in menu.actions() if a.text() == "Seite kopieren").trigger()
    assert clipboard.has_page()
    show_workspace(window_rig, "ws2")
    window_rig.win.pages.paste_page()
    window_rig.win.flush()
    pages = ws(window_rig, 1).touch_pages
    assert len(pages) == 3
    pasted = pages[1]
    assert pasted.buttons[5].action == FIREFOX
    assert pasted.id not in ("p1", "p2") and len({p.id for p in pages}) == 3
    assert window_rig.engine.workspace_id == "ws2" and window_rig.engine.page_index == 1
    window_rig.win.undoing.undo_action.trigger()
    assert len(ws(window_rig, 1).touch_pages) == 2


def test_double_hold_fields_saved(window_rig):
    click(window_rig, ControlRef("touch", 3))
    ed = window_rig.win.editor.content
    choose_type(ed.action_form, "mute_toggle")
    choose_type(ed.double_form, "media")
    choose_type(ed.hold_form, "run")
    QTest.keyClicks(ed.hold_form.field("command"), "kate")
    states = ed.states_edit
    states.count_combo.setCurrentIndex(states.count_combo.findData(2))
    states.source_combo.setCurrentIndex(states.source_combo.findData("mute"))
    states.list.setCurrentRow(1)
    states.image_editor.text_edit.setText("Stumm")
    choose_type(states.action_form, "mute_toggle")
    window_rig.win.flush()
    a = window_rig.store.load("default").workspaces[0].touch_pages[0].buttons[3]
    assert a.action == {"type": "mute_toggle"}
    assert a.double == {"type": "media", "key": "play_pause"}
    assert a.hold == {"type": "run", "command": "kate"}
    assert len(a.states) == 2 and a.state_source == {"type": "mute"}
    assert a.states[1].image.text == "Stumm" and a.states[1].action == {"type": "mute_toggle"}
    # App laeuft: Anwendung aus der Liste des Dienstes
    window_rig.win.catalog.set("apps.list", [{"id": "org.kde.kate", "name": "Kate", "icon": ""}])
    click(window_rig, ControlRef("touch", 3))
    states = window_rig.win.editor.content.states_edit
    states.source_combo.setCurrentIndex(states.source_combo.findData("app_running"))
    states.app_picker.setCurrentIndex(states.app_picker.findData("org.kde.kate"))
    window_rig.win.flush()
    assert page(window_rig).buttons[3].state_source == {"type": "app_running",
                                                        "app": "org.kde.kate"}


def test_macro_text_mode_roundtrip_in_editor(window_rig):
    click(window_rig, ControlRef("touch", 0))
    form = window_rig.win.editor.content.action_form
    choose_type(form, "macro")
    steps = form.field("steps")
    steps.text_mode.setChecked(True)
    assert steps.text_edit.isVisibleTo(steps) and not steps.list.isVisibleTo(steps)
    steps.text_edit.edit.setPlainText("hotkey ctrl+c\nwait 200\ntext Hallo")
    window_rig.win.flush()
    assert page(window_rig).buttons[0].action["steps"] == [
        {"type": "hotkey", "keys": "KEY_LEFTCTRL+KEY_C"}, {"type": "sleep", "ms": 200},
        {"type": "text", "text": "Hallo"}]
    steps.text_edit.edit.setPlainText("hotkey ctrl+c\nquatsch 1")
    assert steps.text_edit.error.isVisibleTo(steps) and "Zeile 2" in steps.text_edit.error.text()
    window_rig.win.flush()
    assert len(page(window_rig).buttons[0].action["steps"]) == 3  # letzter gueltiger Stand bleibt
    steps.text_mode.setChecked(False)
    assert steps.list.count() == 3
    steps.list.setCurrentRow(1)
    steps.step_form.field("ms").setValue(500)
    steps.text_mode.setChecked(True)
    assert "wait 500" in steps.text_edit.edit.toPlainText()  # zweiwegig
    # nicht darstellbare Schritte: Textmodus geht nicht an, Hinweis statt Datenverlust
    steps.text_mode.setChecked(False)
    form.set_value({"type": "macro", "steps": [{"type": "volume"}]})
    steps = form.field("steps")
    steps.text_mode.setChecked(True)
    assert not steps.text_mode.isChecked() and steps.mode_note.isVisibleTo(steps)


def test_encoder_and_wheel_fields(window_rig):
    click(window_rig, ControlRef("knob", 1))
    ed = window_rig.win.editor.content
    turn = ed.turn
    turn.mode_combo.setCurrentIndex(turn.mode_combo.findData("split"))
    choose_type(turn.left_form, "hotkey")
    QTest.keyClick(turn.left_form.field("keys"), Qt.Key.Key_Left)
    choose_type(turn.right_form, "hotkey")
    QTest.keyClick(turn.right_form.field("keys"), Qt.Key.Key_Right)
    ed.turn_settings.invert_check.setChecked(True)
    ed.turn_settings.factor_spin.setValue(3)
    ed.strip_combo.setCurrentIndex(ed.strip_combo.findData("bar"))
    layers = ed.layers_edit
    layers.add_button.click()
    layers.label_edit.setText("Zoom")
    choose_type(layers.turn.rotate_form, "volume")
    layers.add_button.click()
    choose_type(layers.press_form, "mute_toggle")
    window_rig.win.flush()
    enc = window_rig.store.load("default").workspaces[0].encoders[1]
    assert enc.rotate is None
    assert enc.left == {"type": "hotkey", "keys": "KEY_LEFT"}
    assert enc.right == {"type": "hotkey", "keys": "KEY_RIGHT"}
    assert (enc.invert, enc.factor, enc.strip) == (True, 3, "bar")
    assert enc.layers == [EncoderLayer({"type": "volume"}, None, None, None, "Zoom"),
                          EncoderLayer(None, None, None, {"type": "mute_toggle"}, "")]

    click(window_rig, ControlRef("wheel", 0))
    ed = window_rig.win.editor.content
    ed.display_combo.setCurrentIndex(ed.display_combo.findData("image"))
    ed.image_editor.text_edit.setText("CT")
    choose_type(ed.tap_form, "media")
    ed.turn_settings.factor_spin.setValue(2)
    ed.turn_settings.invert_check.setChecked(True)
    choose_type(ed.turn.rotate_form, "volume")
    window_rig.win.flush()
    wheel = window_rig.store.load("default").workspaces[0].wheel
    assert (wheel.display, wheel.image.text, wheel.factor, wheel.invert) == (
        "image", "CT", 2, True)
    assert wheel.tap == {"type": "media", "key": "play_pause"}
    assert wheel.rotate == {"type": "volume"}


def test_folder_page_picker_and_locked_back_slot(window_rig):
    pages = ws(window_rig).touch_pages
    pages.append(TouchPage("tools", "Werkzeuge", folder=True))
    window_rig.win.sync_from_engine(force=True)
    click(window_rig, ControlRef("touch", 2))
    form = window_rig.win.editor.content.action_form
    choose_type(form, "folder")
    combo = form.field("page")
    assert [combo.itemData(i) for i in range(combo.count())] == ["tools"]
    form.field("auto_exit").setChecked(True)
    window_rig.win.flush()
    assert page(window_rig).buttons[2].action == {"type": "folder", "page": "tools",
                                                  "auto_exit": True}
    window_rig.win.page_bar.tabs.setCurrentIndex(1)
    click(window_rig, ControlRef("touch", 0))
    assert window_rig.win.editor.ref is None and "Zurück" in window_rig.win.editor.hint.text()
    assert window_rig.win.device_view.preview.shown_assignment(0).action == {"type": "folder_back"}
    window_rig.win.pages.toggle_folder(1)  # wieder normale Seite
    assert not pages[1].folder


def test_sticky_via_context_menu(window_rig):
    menu = window_rig.win.edit.control_menu(ControlRef("touch", 5))
    pin = next(a for a in menu.actions() if a.text() == "Auf allen Seiten anheften")
    pin.trigger()
    window_rig.win.flush()
    w = ws(window_rig)
    assert w.sticky[5].action == FIREFOX and page(window_rig).buttons[5] is None
    window_rig.win.pages.add_page()  # neue Seite zeigt die Sticky-Kachel
    view = window_rig.win.device_view
    assert view.preview.is_sticky(5) and view.preview.shown_assignment(5).action == FIREFOX
    click(window_rig, ControlRef("touch", 5))
    assert window_rig.win.editor.content.action_form.value() == FIREFOX  # bearbeitet die Sticky-Kachel
    choose_type(window_rig.win.editor.content.action_form, "mute_toggle")
    window_rig.win.flush()
    assert w.sticky[5].action == {"type": "mute_toggle"}
    menu = window_rig.win.edit.control_menu(ControlRef("touch", 5))
    next(a for a in menu.actions() if a.text().startswith("Nicht mehr")).trigger()
    assert 5 not in w.sticky and page(window_rig, 0, 1).buttons[5].action == {"type": "mute_toggle"}


def test_led_color_and_profile_settings(window_rig, monkeypatch):
    monkeypatch.setattr(QColorDialog, "getColor", staticmethod(lambda *a, **k: QColor("#ff8800")))
    window_rig.win.pages.choose_led_color()
    window_rig.win.flush()
    assert window_rig.store.load("default").workspaces[0].led_color == "#ff8800"
    window_rig.win.pages.set_led_color(None)
    assert ws(window_rig).led_color is None

    catalog = Catalog()
    catalog.set("apps.list", [{"id": "org.kde.kate", "name": "Kate", "icon": ""}])
    profile = window_rig.engine.profile
    dialog = ProfileSettingsDialog(profile, catalog)
    dialog.picker.setCurrentIndex(dialog.picker.findData("org.kde.kate"))
    dialog.add_button.click()
    dialog.picker.setEditText("firefox")
    dialog.add_button.click()
    dialog.dynamic_check.setChecked(False)
    dialog.hold_check.setChecked(True)
    assert dialog.apply(profile)
    assert (profile.app_ids, profile.dynamic, profile.hold_profile) == (
        ["org.kde.kate", "firefox"], False, True)
    dialog.deleteLater()


def test_action_pickers_from_api():
    calls = []

    def fetch(method, params, callback):
        calls.append(method)
        data = {"apps.list": [{"id": "org.kde.dolphin", "name": "Dolphin", "icon": ""}],
                "kde.shortcuts": [{"component": "kwin", "name": "Overview",
                                   "friendly": "Übersicht umschalten"}]}
        callback(data[method], None)

    targets = NavTargets(catalog=Catalog(fetch))
    form = ActionForm("press", targets=targets)
    form.set_value({"type": "app_focus", "app_id": "org.kde.dolphin"})
    assert calls == []  # erst angefragt, wenn das Feld sichtbar wird
    form.show()
    QApplication.processEvents()
    assert form.field("app_id").currentText() == "Dolphin (org.kde.dolphin)"
    assert form.value() == {"type": "app_focus", "app_id": "org.kde.dolphin"}
    form.field("app_id").setEditText("meine-app")
    assert form.value() == {"type": "app_focus", "app_id": "meine-app"}
    form.set_value({"type": "kde_shortcut"})
    QApplication.processEvents()
    picker = form.shortcut_picker
    picker.setCurrentIndex(picker.findText("kwin › Übersicht umschalten"))
    assert form.value() == {"type": "kde_shortcut", "component": "kwin", "name": "Overview"}
    form.set_value({"type": "http", "method": "POST", "url": "http://x",
                    "headers": "A: 1\nB: 2", "body": ""})
    assert form.field("headers").toPlainText() == "A: 1\nB: 2"
    form.field("headers").setPlainText("X: y\nZ: w")
    assert form.value()["headers"] == "X: y\nZ: w"
    form.set_value({"type": "text", "text": "Hallo", "mode": "paste"})
    assert form.paste_hint is not None and form.paste_hint.isVisibleTo(form)
    form.field("mode").setCurrentIndex(form.field("mode").findData("type"))
    assert not form.paste_hint.isVisibleTo(form)
    assert calls.count("apps.list") == 1 and calls.count("kde.shortcuts") == 1
    form.close()


def test_preview_uses_device_rendering(window_rig):
    w = ws(window_rig)
    w.encoders[2] = Encoder(rotate={"type": "volume"}, label="Laut", strip="bar")
    w.encoders[1] = Encoder(layers=[EncoderLayer(label="Zoom"), EncoderLayer(label="Pan")])
    page(window_rig).buttons[4] = Assignment({"type": "run"}, ButtonImage(text="Groß",
                                                                   layout="big_text",
                                                                   font="Orbitron"))
    w.wheel.display = "arc"
    window_rig.win.sync_from_engine(force=True)
    view = window_rig.win.device_view
    expected = strip_image([strip_section("Lautstärke", None, "name_value"),
                            strip_section("Zoom", None, "name_value"),
                            strip_section("Laut", None, "bar", PREVIEW_VALUE)])
    from neondeck.editor.widgets.qt_images import to_qimage
    assert view.preview.strips[0] == to_qimage(expected)
    tile = view.preview.tiles[4]
    from neondeck.engine.painter import button_spec
    from neondeck.render.images import render_tile
    a = page(window_rig).buttons[4]
    assert tile == to_qimage(render_tile(button_spec(a, a.image, None, None)))
    assert view.preview.wheel is not None and not view.preview.wheel.isNull()


# --- Review-Runde 1 ------------------------------------------------------------------------


def run_(cmd):
    return Assignment({"type": "run", "command": cmd}, ButtonImage(text=cmd))


def _commands(rig):
    p = rig.engine.profile
    touch = [(b.action or {}).get("command") or (b.action or {}).get("type") if b else None
             for b in page(rig).buttons]
    rnd = [(a.action or {}).get("command") or (a.action or {}).get("type") if a else None
           for a in (p.round[c] for c in ROUND_CODES)]
    return touch, rnd


def test_mixed_kind_move_loses_nothing(window_rig):
    pg, p = page(window_rig), window_rig.engine.profile
    pg.buttons[0], pg.buttons[5] = run_("A"), run_("X")
    p.round[ROUND_CODES[0]] = run_("R")
    window_rig.win.sync_from_engine(force=True)
    window_rig.win.edit.controls_dropped([ControlRef("touch", 0), ControlRef("round", 0)],
                             ControlRef("touch", 5), False)
    window_rig.win.flush()
    touch, rnd = _commands(window_rig)
    assert touch[5] == "A" and touch[0] == "X"  # Touch-Gruppe getauscht
    assert rnd[0] == "R"                        # runde Taste bleibt, wo sie war
    items = [edit.Item("touch", 0, None), edit.Item("touch", 0, None),
             edit.Item("round", 3, None)]
    assert [d for _, d in edit.place_targets(items, ControlRef("touch", 4))] == [
        ControlRef("touch", 4)]  # doppelte Ziele und fremde Arten entfallen


def test_move_refused_when_displaced_cannot_go_back(window_rig):
    pg, p = page(window_rig), window_rig.engine.profile
    pg.buttons[5] = Assignment({"type": "clock"})
    p.round[ROUND_CODES[0]] = run_("R")
    window_rig.win.sync_from_engine(force=True)
    window_rig.win.edit.controls_dropped([ControlRef("round", 0)], ControlRef("touch", 5), False)
    window_rig.win.flush()
    touch, rnd = _commands(window_rig)
    assert touch[5] == "clock" and rnd[0] == "R"  # nichts verschoben, nichts verloren
    assert "Nicht verschoben" in window_rig.win.statusBar().currentMessage()
    window_rig.win.edit.controls_dropped([ControlRef("round", 0)], ControlRef("touch", 5), True)
    touch, rnd = _commands(window_rig)
    assert touch[5] == "R" and rnd[0] == "R"  # Kopieren (ueberschreibt das Ziel) geht


def test_undo_after_change_elsewhere_does_not_restore_stale(window_rig):
    win, a = window_rig.win, window_rig.engine.profile
    other = Profile_copy(a, "other")
    window_rig.store.save(other)
    win.reload_profiles()
    edit.set_value(win.shown_ctx(), ControlRef("touch", 3), run_("edit"))
    win.commits.schedule(win.profile, label="x")
    win.flush()
    assert win.undoing.stack().can_undo()
    win.navigator.switch_to("other")
    inactive = window_rig.store.load(a.id)
    inactive.name = "Umbenannt"
    win.commits.commit_now(inactive)  # wie die Profilverwaltung
    win.navigator.switch_to(a.id)
    assert window_rig.engine.profile.name == "Umbenannt"
    win.undoing.undo()
    assert window_rig.store.load(a.id).name == "Umbenannt"
    assert page(window_rig).buttons[3].action["command"] == "edit"
    assert win.statusBar().currentMessage() == STALE_UNDO and not win.undoing.stack().can_undo()
    win.undoing.redo()
    assert window_rig.store.load(a.id).name == "Umbenannt"


def Profile_copy(p, pid):
    import copy as _copy
    o = _copy.deepcopy(p)
    o.id, o.name = pid, pid
    return o


def test_unknown_values_are_kept(window_rig):
    w = ws(window_rig)
    w.encoders[2] = Encoder(rotate={"type": "volume"}, strip="sparkline")
    w.wheel = Wheel(display="hologram")
    page(window_rig).buttons[4] = Assignment({"type": "run"}, ButtonImage(
        text="x", layout="poster", font="Comic", align_h="justify", align_v="middle"))
    window_rig.win.sync_from_engine(force=True)
    click(window_rig, ControlRef("knob", 2))
    window_rig.win.editor.content.label_edit.setText("L")
    click(window_rig, ControlRef("wheel", 0))
    window_rig.win.editor.content.turn_settings.factor_spin.setValue(2)
    click(window_rig, ControlRef("touch", 4))
    window_rig.win.editor.content.image_editor.text_edit.setText("y")
    window_rig.win.flush()
    saved = window_rig.store.load("default").workspaces[0]
    assert saved.encoders[2].strip == "sparkline" and saved.wheel.display == "hologram"
    img = saved.touch_pages[0].buttons[4].image
    assert (img.layout, img.font, img.align_h, img.align_v, img.text) == (
        "poster", "Comic", "justify", "middle", "y")


def test_invalid_clipboard_is_rejected(window_rig):
    mime = QMimeData()
    mime.setData(clipboard.ASSIGNMENT_MIME, json.dumps([
        {"kind": "touch", "index": 0, "value": {"action": {"type": "run"},
                                                "image": {"bg": "keine-farbe"}}},
        {"kind": "touch", "index": 1, "value": {"action": {"type": "mute_toggle"}}},
        {"kind": "gibts-nicht", "index": 0, "value": None}]).encode())
    QApplication.clipboard().setMimeData(mime)
    items, bad = clipboard.get_items()
    assert bad == 2 and [i.index for i in items] == [1]
    click(window_rig, ControlRef("touch", 8))
    window_rig.win.edit.paste()
    assert page(window_rig).buttons[8].action == {"type": "mute_toggle"}
    assert "ungültige" in window_rig.win.statusBar().currentMessage()
    mime = QMimeData()
    mime.setData(clipboard.PAGE_MIME, b'{"id": "p9", "buttons": "kaputt"}')
    QApplication.clipboard().setMimeData(mime)
    n = len(ws(window_rig).touch_pages)
    window_rig.win.pages.paste_page()
    assert len(ws(window_rig).touch_pages) == n
    assert "ungültig" in window_rig.win.statusBar().currentMessage()


def test_paste_page_drops_foreign_folder_targets_and_folder_hint(window_rig):
    w = ws(window_rig)
    w.touch_pages.append(TouchPage("tools", "Werkzeuge", folder=True))
    page(window_rig).buttons[2] = Assignment({"type": "folder", "page": "tools"})
    window_rig.win.sync_from_engine(force=True)
    window_rig.win.pages.copy_page(0)
    window_rig.win.pages.paste_page()  # gleicher Arbeitsbereich: Ziel bleibt
    assert w.touch_pages[1].buttons[2].action == {"type": "folder", "page": "tools"}
    show_workspace(window_rig, "ws2")
    window_rig.win.pages.paste_page()  # dort gibt es „tools“ nicht
    pasted = ws(window_rig, 1).touch_pages[1]
    assert pasted.buttons[2].action == {"type": "folder"}
    assert "Ordner-Taste" in window_rig.win.statusBar().currentMessage()
    pasted.buttons[0] = Assignment({"type": "mute_toggle"})
    window_rig.win.pages.toggle_folder(1)
    assert pasted.folder and window_rig.win.statusBar().currentMessage() == FOLDER_FIELD_HINT


def test_paste_page_drops_foreign_folder_targets_in_macro_steps(window_rig):
    """Auch Ordner-Schritte in Makros verlieren ein Ziel, das es im Arbeitsbereich nicht gibt."""
    w = ws(window_rig)
    w.touch_pages.append(TouchPage("tools", "Werkzeuge", folder=True))
    macro = {"type": "macro", "steps": [{"type": "mute_toggle"},
                                        {"type": "folder", "page": "tools"}]}
    page(window_rig).buttons[3] = Assignment(macro)
    window_rig.win.sync_from_engine(force=True)
    window_rig.win.pages.copy_page(0)
    show_workspace(window_rig, "ws2")
    window_rig.win.pages.paste_page()
    steps = ws(window_rig, 1).touch_pages[1].buttons[3].action["steps"]
    assert steps == [{"type": "mute_toggle"}, {"type": "folder"}]
    assert "1 Ordner-Taste" in window_rig.win.statusBar().currentMessage()


def test_ctrl_d_leaves_text_fields_alone(window_rig):
    click(window_rig, ControlRef("touch", 5))
    field = window_rig.win.editor.content.image_editor.text_edit
    field.setFocus()
    QApplication.processEvents()
    if QApplication.focusWidget() is field:  # offscreen: Fokus nur bei aktivem Fenster
        window_rig.win.edit.duplicate_action.trigger()
        assert page(window_rig).buttons[6] is None
    window_rig.win.device_view.setFocus()
    QApplication.processEvents()
    window_rig.win.edit.duplicate_selection()
    assert page(window_rig).buttons[6].action == FIREFOX
