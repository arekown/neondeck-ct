"""Aktionsliste: suchen, Kategorien, Ziehen, Doppelklick aufs gewaehlte Element."""
import json

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget

from neondeck.device.layout import ControlRef
from neondeck.editor.editing.mime import ACTION_MIME
from neondeck.editor.widgets.action_library import ActionLibrary

pytestmark = pytest.mark.usefixtures("home")


def test_library_search_filters():
    lib = ActionLibrary()
    assert {"command", "run", "hotkey", "kde", "workspace", "clock", "macro"} <= set(
        lib.visible_types())
    assert "unsupported" not in lib.visible_types()
    lib.search.setText("Konsole")
    assert lib.visible_types() == ["command", "terminal_layout"]
    lib.search.setText("konsole")  # Gross-/Kleinschreibung egal
    assert lib.visible_types() == ["command", "terminal_layout"]
    lib.search.setText("")
    assert "run" in lib.visible_types()


def test_library_categories_in_order():
    lib = ActionLibrary()
    assert lib.category_names() == ["apps", "input", "media", "system", "navigation",
                                    "display", "macros"]
    assert lib.category_item("input").text(0) == "Eingabe"  # Schluessel -> Anzeigename
    lib.search.setText("Lautstärke")
    assert lib.visible_categories() == ["media"]


def test_drag_payload():
    lib = ActionLibrary()
    mime = lib.mime_data("command")
    assert mime.hasFormat(ACTION_MIME)
    action = json.loads(bytes(mime.data(ACTION_MIME)).decode("utf-8"))
    assert action["type"] == "command"
    assert action["terminal"] is True and action["hold"] is False  # Standardparameter
    assert lib.mime_data("hotkey") is not None
    item = lib.item("hotkey")
    assert item.flags() & Qt.ItemFlag.ItemIsDragEnabled
    assert not lib.category_item("input").flags() & Qt.ItemFlag.ItemIsDragEnabled


def test_library_double_click_applies_to_selection(profiles_rig):
    profiles_rig.win.select(ControlRef("touch", 2))
    profiles_rig.win.library.activated.emit({"type": "command", "terminal": True, "hold": False})
    page = profiles_rig.engine.profile.workspaces[0].touch_pages[0]
    assert page.buttons[2].action["type"] == "command"
    assert profiles_rig.win.editor.content.action_form.type_combo.currentData() == "command"


def test_library_double_click_without_selection_only_hints(profiles_rig):
    profiles_rig.win.selected = None
    profiles_rig.win.load_editor()
    profiles_rig.win.library.activated.emit({"type": "run"})
    assert "wählen" in profiles_rig.win.statusBar().currentMessage()


def test_library_item_activation_emits_template():
    lib = ActionLibrary()
    got = []
    lib.activated.connect(got.append)
    lib.tree.itemDoubleClicked.emit(lib.item("run"), 0)
    lib.tree.itemDoubleClicked.emit(lib.category_item("apps"), 0)
    assert got == [{"type": "run"}]


def test_config_window_has_library_panel_and_profile_menu(profiles_rig):
    assert profiles_rig.win.library.isVisible()
    texts = [a.text() for a in profiles_rig.win.profile_menu.actions() if not a.isSeparator()]
    assert any("verwalten" in t for t in texts)
    assert any("importieren" in t.lower() for t in texts)
    assert [w for w in profiles_rig.win.findChildren(QWidget) if w.styleSheet()] == []


def test_library_drag_is_copy_only(monkeypatch):
    from PySide6.QtGui import QDrag
    calls = []
    monkeypatch.setattr(QDrag, "exec", lambda self, *a: calls.append(a) or Qt.DropAction.MoveAction)
    lib = ActionLibrary()
    lib.tree.setCurrentItem(lib.item("run"))
    lib.tree.startDrag(Qt.DropAction.MoveAction | Qt.DropAction.CopyAction)
    assert calls and all(a == Qt.DropAction.CopyAction for a in calls[0])
    assert lib.item("run").treeWidget() is lib.tree  # Eintrag bleibt trotz „Verschieben“
    assert "run" in lib.visible_types()
    assert lib.tree.supportedDropActions() == Qt.DropAction.CopyAction
