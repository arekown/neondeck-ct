"""Windows-Profil (.lp5) importieren: Archiv-Pruefung und Fehlerbehandlung (ohne Oberflaeche)."""
import json
import zipfile

import pytest

from neondeck.core import paths
from neondeck.profile.importers.lp5 import import_lp5
from neondeck.profile.store import ProfileStore
from support.lp5 import corrupt_lp5, make_lp5

pytestmark = pytest.mark.usefixtures("home")


@pytest.fixture
def store(home):
    return ProfileStore(paths.config_dir() / "profiles")


@pytest.mark.parametrize("bad", ["../boese.txt", "/tmp/boese.txt", "a/../../boese.txt",
                                 "..\\boese.txt"])
def test_import_rejects_path_traversal(store, tmp_path, bad):
    lp5 = make_lp5(tmp_path / "x.lp5", extra={bad: "x"})
    with pytest.raises(ValueError):
        import_lp5(lp5, store)
    assert store.list() == []
    assert not (tmp_path.parent / "boese.txt").exists()


def test_import_corrupt_member_becomes_value_error(store, tmp_path):
    with pytest.raises(ValueError, match="beschädigt"):
        import_lp5(corrupt_lp5(tmp_path / "crc.lp5"), store)
    assert store.list() == []


def test_import_wrong_structure_becomes_value_error(store, tmp_path):
    lp5 = tmp_path / "falsch.lp5"
    with zipfile.ZipFile(lp5, "w") as z:
        z.writestr("ProfileInfo.json", json.dumps({"displayName": "X", "layout": 3,
                                                   "workspaces": [None]}))
    with pytest.raises(ValueError, match="Format"):
        import_lp5(lp5, store)
    assert store.list() == []
    assert not list((paths.data_dir() / "imported").glob("*"))  # nichts liegen geblieben
