"""Profilverwaltung: Profile und Arbeitsbereiche, Windows-Profil (.lp5) importieren."""
import json
import zipfile
from pathlib import Path

import pytest
from PySide6.QtWidgets import QFileDialog, QInputDialog, QMessageBox

from neondeck.core import paths
from neondeck.editor.dialogs.import_report import ImportReport
from neondeck.editor.windows.profile_manager import ProfileManager
from support.lp5 import corrupt_lp5, make_lp5

pytestmark = pytest.mark.usefixtures("home")
YES, NO = QMessageBox.StandardButton.Yes, QMessageBox.StandardButton.No


def manager(profiles_rig) -> ProfileManager:
    return profiles_rig.win.extras.make_profile_manager()


def test_delete_profile_asks(profiles_rig, monkeypatch):
    asked = []
    monkeypatch.setattr(QMessageBox, "question",
                        staticmethod(lambda *a, **k: asked.append(a) or NO))
    m = manager(profiles_rig)
    m.select_profile("spiel")
    m.delete_profile()
    assert asked
    assert "spiel" in profiles_rig.store.list()
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: YES))
    m.delete_profile()
    assert "spiel" not in profiles_rig.store.list()
    assert m.profile_ids() == ["default"]


def test_delete_active_profile_switches_first(profiles_rig, monkeypatch):
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: YES))
    m = manager(profiles_rig)
    m.select_profile("default")
    m.delete_profile()
    assert profiles_rig.switched == ["spiel"]
    assert profiles_rig.engine.profile.id == "spiel"
    assert profiles_rig.store.list() == ["spiel"]
    assert profiles_rig.win.toolbar.profile_combo.currentData() == "spiel"


def test_delete_active_profile_kept_if_switch_fails(profiles_rig, monkeypatch):
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: YES))
    warned = []
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: warned.append(a)))
    m = ProfileManager(profiles_rig.store, profiles_rig.engine, profiles_rig.win.commits.commit_now, lambda pid: None)
    m.select_profile("default")
    m.delete_profile()
    assert warned
    assert "default" in profiles_rig.store.list()


def test_last_profile_cannot_be_deleted(profiles_rig, monkeypatch):
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: YES))
    profiles_rig.store.delete("spiel")
    m = manager(profiles_rig)
    m.select_profile("default")
    assert not m.delete_profile_button.isEnabled()
    m.delete_profile()
    assert profiles_rig.store.list() == ["default"]


def test_new_rename_duplicate_profile(profiles_rig, monkeypatch):
    names = iter(["Bildbearbeitung", "Fotos", "Kopie hier"])
    monkeypatch.setattr(QInputDialog, "getText",
                        staticmethod(lambda *a, **k: (next(names), True)))
    m = manager(profiles_rig)
    m.new_profile()
    pid = m.current_pid()
    assert pid.startswith("bildbearbeitung-") and pid in profiles_rig.store.list()
    assert profiles_rig.store.load(pid).name == "Bildbearbeitung"
    m.rename_profile()
    assert profiles_rig.store.load(pid).name == "Fotos"
    m.select_profile("default")
    m.duplicate_profile()
    copy_id = m.current_pid()
    assert copy_id not in ("default", pid)
    dup = profiles_rig.store.load(copy_id)
    assert dup.name == "Kopie hier" and [w.id for w in dup.workspaces] == ["ws1", "ws2"]
    assert profiles_rig.win.toolbar.profile_combo.findData(pid) >= 0  # Fenster kennt die neuen Profile


def test_rename_active_profile_updates_engine(profiles_rig, monkeypatch):
    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: ("Neu", True)))
    m = manager(profiles_rig)
    m.select_profile("default")
    m.rename_profile()
    assert profiles_rig.engine.profile.name == "Neu"
    assert profiles_rig.store.load("default").name == "Neu"
    assert profiles_rig.win.toolbar.profile_combo.currentText() == "Neu"


def test_workspaces_add_rename_move_home_delete(profiles_rig, monkeypatch):
    names = iter(["Drei", "Drei neu"])
    monkeypatch.setattr(QInputDialog, "getText",
                        staticmethod(lambda *a, **k: (next(names), True)))
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: YES))
    m = manager(profiles_rig)
    m.select_profile("default")
    m.new_workspace()
    p = profiles_rig.engine.profile
    assert [w.name for w in p.workspaces] == ["Allgemein", "Zwei", "Drei"]
    assert len(p.workspaces[2].touch_pages) == 1
    m.rename_workspace()
    assert p.workspaces[2].name == "Drei neu"
    m.move_workspace(-1)
    assert [w.name for w in p.workspaces] == ["Allgemein", "Drei neu", "Zwei"]
    m.set_home()
    assert p.home_workspace == p.workspaces[1].id
    assert profiles_rig.store.load("default").home_workspace == p.home_workspace
    assert [profiles_rig.win.toolbar.workspace_combo.itemText(i) for i in range(3)] == [
        "Allgemein", "Drei neu", "Zwei"]
    m.delete_workspace()  # der Heim-Arbeitsbereich: Heim wird der erste
    assert [w.name for w in p.workspaces] == ["Allgemein", "Zwei"]
    assert p.home_workspace == "ws1"
    assert [w.name for w in profiles_rig.store.load("default").workspaces] == ["Allgemein", "Zwei"]


def test_last_workspace_cannot_be_deleted(profiles_rig, monkeypatch):
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: YES))
    m = manager(profiles_rig)
    m.select_profile("spiel")
    assert not m.delete_workspace_button.isEnabled()
    m.delete_workspace()
    assert len(profiles_rig.store.load("spiel").workspaces) == 1


def test_workspace_of_other_profile_saved_to_store(profiles_rig, monkeypatch):
    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: ("Extra", True)))
    m = manager(profiles_rig)
    m.select_profile("spiel")
    m.new_workspace()
    assert [w.name for w in profiles_rig.store.load("spiel").workspaces] == ["Allgemein", "Extra"]
    assert profiles_rig.engine.profile.id == "default"


def test_import_lp5_reports_unsupported(profiles_rig, monkeypatch, tmp_path):
    lp5 = make_lp5(tmp_path / "Standard.lp5")
    monkeypatch.setattr(QFileDialog, "getOpenFileName",
                        staticmethod(lambda *a, **k: (str(lp5), "")))
    shown = []
    monkeypatch.setattr(ImportReport, "exec", lambda self: shown.append(self) or 0)
    m = manager(profiles_rig)
    m.import_profile()
    assert len(shown) == 1
    lines = [shown[0].list.item(i).text() for i in range(shown[0].list.count())]
    assert any("Fn-Belegung nicht übernommen" in line for line in lines)  # Mixer/Fenster: P10
    pid = m.current_pid()
    assert pid.startswith("default-") and pid in profiles_rig.store.list()
    imported = profiles_rig.store.load(pid)
    assert len(imported.workspaces) >= 2
    icons = [b.image.icon for w in imported.workspaces for pg in w.touch_pages
             for b in pg.buttons if b and b.image.icon and b.image.icon.startswith("file:")]
    out = (paths.data_dir() / "imported" / pid).resolve()
    assert icons and all(i.startswith(f"file:{out}/") for i in icons)
    assert all(Path(i[5:]).is_file() for i in icons)
    assert profiles_rig.engine.profile.id == "default"  # Import wechselt nicht


def test_import_error_shown_not_raised(profiles_rig, monkeypatch, tmp_path):
    bad = tmp_path / "kaputt.lp5"
    bad.write_bytes(b"kein zip")
    monkeypatch.setattr(QFileDialog, "getOpenFileName",
                        staticmethod(lambda *a, **k: (str(bad), "")))
    warned = []
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: warned.append(a)))
    m = manager(profiles_rig)
    m.import_profile()
    assert warned and profiles_rig.store.list() == ["default", "spiel"]


@pytest.mark.parametrize("make", ["crc", "structure"])
def test_import_dialog_warns_for_broken_files(profiles_rig, monkeypatch, tmp_path, make):
    if make == "crc":
        lp5 = corrupt_lp5(tmp_path / "crc.lp5")
    else:
        lp5 = tmp_path / "falsch.lp5"
        with zipfile.ZipFile(lp5, "w") as z:
            z.writestr("ProfileInfo.json", json.dumps({"layout": 3, "workspaces": [None]}))
    monkeypatch.setattr(QFileDialog, "getOpenFileName",
                        staticmethod(lambda *a, **k: (str(lp5), "")))
    warned = []
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: warned.append(a)))
    manager(profiles_rig).import_profile()
    assert len(warned) == 1


def test_failed_switch_status_shows_name(profiles_rig):
    profiles_rig.refuse_switch = True
    profiles_rig.win.navigator.switch_to("spiel")
    msg = profiles_rig.win.statusBar().currentMessage()
    assert "Spiele" in msg and "„spiel“" not in msg
