"""Navigationsziele (Arbeitsbereich, Profil) als Auswahl im Aktionsformular."""
import pytest

from neondeck.device.layout import ControlRef
from neondeck.editor.widgets.action_form import ActionForm
from neondeck.editor.widgets.nav_targets import NavTargets

pytestmark = pytest.mark.usefixtures("home")


def test_workspace_and_profile_params_are_pickers():
    targets = NavTargets(workspaces=[("ws1", "Allgemein"), ("ws2", "Zwei")],
                         profiles=[("default", "Standard"), ("spiel", "Spiele")])
    form = ActionForm("press", targets=targets)
    form.set_value({"type": "workspace", "id": "ws2"})
    combo = form.field("id")
    assert [combo.itemText(i) for i in range(combo.count())] == ["Allgemein", "Zwei"]
    assert combo.currentText() == "Zwei"
    combo.setCurrentIndex(0)
    assert form.value() == {"type": "workspace", "id": "ws1"}
    form.set_value({"type": "profile", "id": "spiel"})
    combo = form.field("id")
    assert combo.currentText() == "Spiele"
    assert form.value() == {"type": "profile", "id": "spiel"}
    form.set_value({"type": "workspace", "id": "weg"})  # unbekannt: anzeigen, nicht verwerfen
    assert form.value() == {"type": "workspace", "id": "weg"}


def test_new_navigation_action_defaults_to_first_target():
    targets = NavTargets(workspaces=[("ws1", "Allgemein")], profiles=[])
    form = ActionForm("press", targets=targets)
    form.type_combo.setCurrentIndex(form.type_combo.findData("workspace"))
    assert form.value() == {"type": "workspace", "id": "ws1"}
    form.type_combo.setCurrentIndex(form.type_combo.findData("profile"))
    assert form.value() == {"type": "profile"}  # keine Profile: kein Wert


def test_editor_offers_workspaces_of_profile(profiles_rig):
    profiles_rig.win.select(ControlRef("round", 1))
    form = profiles_rig.win.editor.content.action_form
    form.type_combo.setCurrentIndex(form.type_combo.findData("workspace"))
    combo = form.field("id")
    assert [combo.itemData(i) for i in range(combo.count())] == ["ws1", "ws2"]
    form.type_combo.setCurrentIndex(form.type_combo.findData("profile"))
    combo = form.field("id")
    assert [combo.itemData(i) for i in range(combo.count())] == ["default", "spiel"]
