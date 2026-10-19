"""Dialog „Versionen“: Snapshots ansehen und wiederherstellen."""
import pytest
from PySide6.QtCore import Qt

from support.waiting import wait_until

pytestmark = pytest.mark.usefixtures("no_modal_error")


def test_versions_dialog_restore(editor_service, editor):
    win = editor.window
    for name in ("Alt", "Neu"):
        p = win.profile
        p.workspaces[0].touch_pages[0].name = name
        win.commits.commit_now(p)
        assert editor.remote.drain(10.0)
    assert editor_service.store.load("default").workspaces[0].touch_pages[0].name == "Neu"
    dialog = win.extras.make_versions_dialog(win.profile)
    try:
        assert dialog.list.count() >= 1 and dialog.selected_name()
        preview = dialog.preview_profile
        assert preview is not None and preview.workspaces[0].touch_pages[0].name == "Alt"
        assert dialog.page_combo.count() == 1
        assert not dialog.preview.acceptDrops()  # nur lesend
        assert dialog.preview.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        before = dialog.list.count()
        assert dialog.restore(confirm=False)
        assert dialog.list.count() == before + 1  # Stand vor dem Wiederherstellen gesichert
    finally:
        dialog.deleteLater()
    assert editor_service.store.load("default").workspaces[0].touch_pages[0].name == "Alt"
    assert editor_service.app.engine.profile.workspaces[0].touch_pages[0].name == "Alt"
    assert wait_until(lambda: win.profile.workspaces[0].touch_pages[0].name == "Alt")
    assert wait_until(lambda: win.page_bar.tabs.tabText(0) == "Alt")
