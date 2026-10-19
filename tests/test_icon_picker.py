"""Symbolauswahl: Gruppen, Suche, eigene Datei, faule Vorschau, kurze Namen."""
from pathlib import Path

import pytest
from PIL import Image
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QFileDialog

from neondeck.device.layout import ControlRef
from neondeck.editor.widgets.icon_picker import IconPicker

pytestmark = pytest.mark.usefixtures("home")


def _png(path: Path, color=(200, 0, 0)) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (80, 80), color).save(path)


@pytest.fixture
def mini_assets(home):
    lib = home / "share" / "assets" / "library" / "de" / "80x80"
    _png(lib / "Home.png")
    _png(lib / "Photoshop" / "Brush.png")
    _png(lib / "Photoshop" / "Eraser.png", (0, 0, 200))
    return lib


def test_icon_picker_groups_and_search(mini_assets):
    picker = IconPicker()
    assert picker.group_names() == ["Allgemein", "Photoshop"]
    assert picker.visible_refs() == ["lib:80x80/Home.png"]  # erste Gruppe
    picker.select_group("Photoshop")
    assert len(picker.visible_refs()) == 2
    picker.search.setText("brush")
    assert picker.visible_refs() == ["lib:80x80/Photoshop/Brush.png"]
    picker.select_group("Allgemein")  # Suche gilt fuer alle Gruppen
    assert picker.visible_refs() == ["lib:80x80/Photoshop/Brush.png"]
    picker.view.setCurrentIndex(picker.model.index(0))
    assert picker.ok_button.isEnabled()
    picker.ok_button.click()
    assert picker.result() == IconPicker.DialogCode.Accepted
    assert picker.selected_ref() == "lib:80x80/Photoshop/Brush.png"


def test_icon_picker_preselects_current(mini_assets):
    picker = IconPicker(current="lib:80x80/Photoshop/Eraser.png")
    assert picker.current_group() == "Photoshop"
    assert picker.selected_ref() == "lib:80x80/Photoshop/Eraser.png"


def test_icon_picker_own_file(mini_assets, monkeypatch, tmp_path):
    own = tmp_path / "eigen.png"
    _png(own)
    monkeypatch.setattr(QFileDialog, "getOpenFileName",
                        staticmethod(lambda *a, **k: (str(own), "")))
    picker = IconPicker()
    picker.file_button.click()
    assert picker.result() == IconPicker.DialogCode.Accepted
    assert picker.selected_ref() == f"file:{own}"


def test_icon_picker_thumbnails_are_lazy(home):
    lib = home / "share" / "assets" / "library" / "de" / "80x80"
    for i in range(400):
        _png(lib / f"Icon{i:03}.png", (i % 255, 0, 0))
    picker = IconPicker()
    picker.resize(500, 400)
    picker.show()
    QApplication.processEvents()
    assert len(picker.visible_refs()) == 400
    assert 0 < picker.model.rendered < 200  # nur sichtbare Bildchen werden geladen
    picker.close()


def test_icon_button_uses_picker(profiles_rig, monkeypatch):
    seen = []

    def choose(parent=None, current=None):
        seen.append(current)
        return "lib:80x80/Photoshop/Brush.png"

    monkeypatch.setattr(IconPicker, "choose", staticmethod(choose))
    profiles_rig.win.select(ControlRef("touch", 0))
    profiles_rig.win.editor.content.image_editor.icon_button.click()
    profiles_rig.win.flush()
    assert seen == [None]
    btn = profiles_rig.engine.profile.workspaces[0].touch_pages[0].buttons[0]
    assert btn.image.icon == "lib:80x80/Photoshop/Brush.png"


def test_picker_choose_cancel_returns_none(mini_assets, monkeypatch):
    monkeypatch.setattr(IconPicker, "exec", lambda self: IconPicker.DialogCode.Rejected)
    assert IconPicker.choose(None, None) is None


def test_icon_names_without_common_prefix(home):
    lib = home / "share" / "assets" / "library" / "de" / "80x80" / "Photoshop"
    for n in ("AdobePsMagicWandSelect", "AdobePsQuickSelect", "AdobePsBrush"):
        _png(lib / f"{n}.png")
    picker = IconPicker()
    model = picker.model
    shown = [model.data(model.index(i)) for i in range(model.rowCount())]
    assert shown == ["Brush", "MagicWandSelect", "QuickSelect"]
    tips = [model.data(model.index(i), Qt.ItemDataRole.ToolTipRole) for i in range(3)]
    assert tips[0].startswith("AdobePsBrush")
    assert picker.view.textElideMode() == Qt.TextElideMode.ElideLeft


def test_common_prefix_keeps_at_least_one_char():
    from neondeck.editor.widgets.icon_picker import display_names
    assert display_names(["Brush", "BrushSize"]) == ["Brush", "BrushSize"]
    assert display_names(["AbcX", "AbcY"]) == ["X", "Y"]
    assert display_names(["Solo"]) == ["Solo"]


def test_common_prefix_cut_at_word_start():
    from neondeck.editor.widgets.icon_picker import display_names
    assert display_names(["AdobePsMagic", "AdobePsMask"]) == ["Magic", "Mask"]
    assert display_names(["Brush_TextA-B", "Brush_TextApply"]) == ["A-B", "Apply"]
