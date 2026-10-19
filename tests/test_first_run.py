"""Ersteinrichtung: Diagnose, Vorlagen ankreuzen, Theme waehlen."""
import pytest

from neondeck.core.settings import Settings
from neondeck.editor.dialogs.first_run import FirstRunWizard
from neondeck.ui import theme
from support.waiting import wait_until

pytestmark = pytest.mark.usefixtures("no_modal_error")


def test_first_run_inserts_chosen_templates(editor_service, editor, monkeypatch):
    assert editor_service.app.settings.first_run_done is False
    opened = []
    monkeypatch.setattr(editor.window.extras, "open_first_run", lambda: opened.append(True))
    assert editor.first_run_if_needed()
    assert wait_until(lambda: opened)

    pid = editor.window.profile.id
    before = len(editor.window.profile.workspaces)
    win = editor.window
    wizard = FirstRunWizard(editor.remote.request, win.theme_menu.set_theme,
                            win.extras.insert_templates, win.say, win)
    try:
        wizard.diagnose.page.refresh()
        assert wizard.diagnose.page.service_reachable
        assert wizard.diagnose.page.checks
        wizard.templates.choose(["entwickler", "grafik", "gaming"])
        assert wizard.templates.chosen() == ["grafik", "gaming", "entwickler"]  # Listenfolge
        wizard.themes.choose("neutral")
        wizard.accept()
        inserted = wizard.inserted
    finally:
        wizard.deleteLater()
    assert [i.name for i in inserted] == ["Grafik", "Gaming", "Entwicklung"]
    stored = lambda: editor_service.store.load(pid)  # noqa: E731 - kurze Hilfe im Test
    assert wait_until(lambda: len(stored().workspaces) == before + 3)
    assert editor_service.app.engine.profile.id == pid  # gleiches Profil, nichts Neues angelegt
    assert wait_until(lambda: editor_service.app.engine.workspace_id == inserted[0].workspace_id)
    assert editor.window.undoing.stack().undo_label() == "Vorlage einfügen"
    assert theme.current().name == "neutral"
    assert wait_until(lambda: editor_service.app.settings.theme == "neutral")
    assert editor_service.app.settings.first_run_done is True
    assert Settings.load().first_run_done is True
    editor.remote.settings_snapshot = editor.remote.request("settings.get")
    assert not editor.first_run_if_needed()
