"""Arbeitsbereiche und Seiten anordnen (Dialog, verschiebbare Reiter, Umsortieren im Modell)."""
import pytest

from neondeck.editor.dialogs.arrange_dialog import ArrangeDialog
from neondeck.profile import arrange
from neondeck.profile.model import Assignment, Profile, TouchPage, Workspace, empty_profile
from support.waiting import wait_until


def _profile() -> Profile:
    p = empty_profile("p", "P")
    p.workspaces = [Workspace(f"w{i}", f"W{i}", [TouchPage("a", "A"), TouchPage("b", "B"),
                                                 TouchPage("c", "C")]) for i in range(1, 4)]
    p.home_workspace = "w1"
    p.round[7] = Assignment({"type": "workspace", "id": "w1"})
    p.round[8] = Assignment({"type": "hotkey", "keys": "KEY_A"})  # bleibt, wo sie ist
    p.round[9] = Assignment({"type": "workspace", "id": "w2"})
    p.round[11] = Assignment({"type": "workspace", "id": "w3"})
    return p


def test_reorder_workspaces_round_buttons_follow():
    p = _profile()
    arrange.reorder_workspaces(p, ["w3", "w1", "w2"])
    assert [w.id for w in p.workspaces] == ["w3", "w1", "w2"]
    assert [p.round[c].action.get("id") for c in (7, 9, 11)] == ["w3", "w1", "w2"]
    assert p.round[8].action == {"type": "hotkey", "keys": "KEY_A"}
    with pytest.raises(ValueError):
        arrange.reorder_workspaces(p, ["w1", "w2"])


def test_reorder_pages_keeps_page_actions_on_their_page():
    ws = _profile().workspaces[0]
    ws.touch_pages[0].buttons[0] = Assignment({"type": "page", "index": 2})  # zeigt auf „c“
    ws.touch_pages[0].buttons[1] = Assignment(
        {"type": "macro", "steps": [{"type": "page", "index": 0}]})        # zeigt auf „a“
    arrange.reorder_pages(ws, ["c", "a", "b"])
    a = ws.touch_pages[1]
    assert [p.id for p in ws.touch_pages] == ["c", "a", "b"]
    assert a.buttons[0].action["index"] == 0 and a.buttons[1].action["steps"][0]["index"] == 1


def test_arrange_dialog_and_tabs_in_editor(editor_service, editor):
    win = editor.window
    p = win.profile
    p.workspaces = _profile().workspaces
    p.round.update(_profile().round)
    win.commits.commit_now(p, label="Vorbereiten")
    win.sync_from_engine(force=True)

    dialog = ArrangeDialog(win.profile, "w1", win)
    try:
        dialog.move_workspace(2, 0)  # W3 nach vorn
        assert dialog.workspace_order()[0] == "w3"
        assert "runde Taste 1" in dialog.workspaces.item(0).text()
        dialog.workspaces.setCurrentRow(1)  # W1
        dialog.move_page(0, 3)          # A ans Ende
        assert dialog.page_orders()["w1"] == ["b", "c", "a"]
        win.pages.apply_arrangement(dialog.workspace_order(), dialog.page_orders())
    finally:
        dialog.deleteLater()
    stored = lambda: editor_service.store.load(p.id)  # noqa: E731 - kurze Hilfe im Test
    assert wait_until(lambda: [w.id for w in stored().workspaces][:3] == ["w3", "w1", "w2"])
    assert [x.id for x in stored().workspaces[1].touch_pages] == ["b", "c", "a"]
    assert stored().round[7].action["id"] == "w3"
    assert win.undoing.stack().undo_label() == "Anordnen"

    win.engine.show_workspace("w2")
    win.sync_from_engine(force=True)
    win.page_bar.tabs.moveTab(0, 2)  # Reiter ziehen
    assert wait_until(lambda: [x.id for x in stored().workspaces[2].touch_pages] == ["b", "c", "a"])
