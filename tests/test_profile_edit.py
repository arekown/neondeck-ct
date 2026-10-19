"""Profil bearbeiten ohne Fenster (``profile.edit``)."""
from neondeck.device.layout import ControlRef
from neondeck.profile import edit
from neondeck.profile.model import Assignment, Profile


def test_move_swaps_and_sticky_field_takes_the_value():
    p = Profile.empty()
    ws = p.workspaces[0]
    page = ws.touch_pages[0]
    page.buttons[0] = Assignment({"type": "run", "command": "a"})
    page.buttons[1] = Assignment({"type": "run", "command": "b"})
    ctx = edit.EditContext(p, ws, page)
    items = edit.take_items(ctx, [ControlRef("touch", 0)])
    result = edit.place(ctx, items, ControlRef("touch", 1), touch_only=(), move=True)
    assert result.placed == [ControlRef("touch", 1)] and result.blocked is None
    assert [page.buttons[i].action["command"] for i in (0, 1)] == ["b", "a"]
    assert edit.toggle_sticky(ctx, 1) == edit.StickyChange(pinned=True)
    edit.set_value(ctx, ControlRef("touch", 1), Assignment({"type": "run", "command": "c"}))
    assert page.buttons[1] is None and ws.sticky[1].action["command"] == "c"
