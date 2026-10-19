"""Zentrale Helfer aus ``core`` (je Baustein ein Test)."""
import pytest

from neondeck.core import fileio, paths


def test_fileio_write_read_tempfile(tmp_path):
    target = tmp_path / "a.json"
    fileio.write_atomic(target, '{"x": 1}')
    assert fileio.read_json(target) == {"x": 1}
    assert not (tmp_path / "a.json.tmp").exists()
    temp = fileio.runtime_tempfile("ldl-", ".txt", "hallo")
    assert temp.read_text(encoding="utf-8") == "hallo"
    temp.unlink()


def test_profile_format_error_is_loupedeck_error():
    from neondeck.core.errors import LoupedeckError, ProfileFormatError
    from neondeck.profile.model import Profile

    with pytest.raises(ProfileFormatError) as info:
        Profile.from_json({"workspaces": [5]})
    assert isinstance(info.value, LoupedeckError) and isinstance(info.value, ValueError)


def test_worker_runs_in_background_and_posts_done():
    import threading

    from neondeck.core.workers import Worker

    posted, got = [], []

    class Poster:
        def post(self, fn):
            posted.append(fn)

    worker = Worker("test", poster=Poster())
    future = worker.submit(threading.current_thread, lambda r, e: got.append((r, e)))
    worker.shutdown(wait=True)
    assert future.result() is not threading.current_thread()
    posted[0]()  # „im Hauptthread“
    assert got == [(future.result(), None)]


def test_migrate_legacy_moves_old_dirs_and_autostart(monkeypatch):
    """Alte Ordner ``loupedeck-linux`` und alter Autostart werden einmalig uebernommen
    (nur in den tmp-XDG-Ordnern der Tests)."""
    monkeypatch.delenv("NEONDECK_HOME")
    old = paths.xdg_config_home() / "loupedeck-linux"
    (old / "profiles").mkdir(parents=True)
    (old / "settings.json").write_text("{}", encoding="utf-8")
    (paths.xdg_state_home() / "loupedeck-linux").mkdir(parents=True)
    (paths.xdg_state_home() / "neondeck-ct").mkdir(parents=True)  # neu schon da: bleibt
    old_auto = paths.autostart_dir() / "loupedeck-linux.desktop"
    old_auto.parent.mkdir(parents=True, exist_ok=True)
    old_auto.write_text("[Desktop Entry]\nExec=alt\n", encoding="utf-8")

    notes = paths.migrate_legacy("[Desktop Entry]\nExec=neu\n")
    assert len(notes) == 2
    assert not old.exists() and (paths.config_dir() / "settings.json").is_file()
    assert (paths.xdg_state_home() / "loupedeck-linux").is_dir()
    assert not old_auto.exists()
    assert "Exec=neu" in (paths.autostart_dir() / "neondeck-ct.desktop").read_text(encoding="utf-8")
    assert paths.migrate_legacy("x") == []  # einmalig
