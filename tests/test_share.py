"""Profil teilen: .ndprofile exportieren und importieren (mit Bildern, sicher)."""
import json
import zipfile
from pathlib import Path

import pytest

from neondeck.core import paths
from neondeck.profile import share
from support.profiles import profile_with_image
from support.waiting import wait_until

pytestmark = pytest.mark.usefixtures("no_modal_error")


def test_export_import_roundtrip_with_images(tmp_path, editor_service, editor):
    p, img = profile_with_image(tmp_path)
    archive = tmp_path / "teilen.ndprofile"
    assert share.export_profile(p, archive) == []
    with zipfile.ZipFile(archive) as z:
        assert sorted(z.namelist()) == ["files/logo.png", "profile.json"]
        inner = json.loads(z.read("profile.json"))["profile"]
    assert inner["workspaces"][0]["touch_pages"][0]["buttons"][0]["image"]["icon"] == \
        "file:files/logo.png"

    q = share.import_profile(archive, existing={"teilen"})
    assert q.id != "teilen" and q.id.startswith("teilen-")
    new_icon = q.workspaces[0].touch_pages[0].buttons[0].image.icon
    target = paths.data_dir() / "imported" / q.id / "logo.png"
    assert new_icon == f"file:{target}" and target.read_bytes() == img.read_bytes()
    assert q.workspaces[0].touch_pages[1].buttons[3].image.icon == new_icon
    assert q.workspaces[0].touch_pages[0].buttons[1].image.icon == "svg:icons/MediaVolume.svg"
    a, b = p.to_json(), q.to_json()
    for d in (a, b):
        d.pop("id")
        for page in d["workspaces"][0]["touch_pages"]:
            for button in page["buttons"]:
                if button and button["image"]["icon"].startswith("file:"):
                    button["image"]["icon"] = "file:"
    assert a == b

    # im Editor: ueber den Dienst gespeichert und aktiviert
    win = editor.window
    imported = win.extras.import_shared_profile_from(archive)
    assert imported is not None and imported.id == "teilen"  # dort frei: Kennung bleibt
    assert wait_until(lambda: imported.id in editor_service.store.list())
    assert editor_service.app.engine.profile.id == imported.id
    icon = editor_service.store.load(imported.id).workspaces[0].touch_pages[0].buttons[0].image.icon
    assert Path(icon[len("file:"):]).read_bytes() == img.read_bytes()
    out = tmp_path / "wieder"
    assert win.extras.export_profile_to(out)
    assert (tmp_path / "wieder.ndprofile").is_file()


def test_import_rejects_traversal(tmp_path):
    p, _ = profile_with_image(tmp_path)
    data = json.dumps({"format": "ldlprofile", "profile": p.to_json()})
    for evil in ("../boese.png", "files/../../boese.png", "/tmp/boese.png"):
        archive = tmp_path / "boese.ldlprofile"
        with zipfile.ZipFile(archive, "w") as z:
            z.writestr("profile.json", data)
            z.writestr(evil, b"x")
        with pytest.raises(ValueError, match="Unsicherer Pfad"):
            share.import_profile(archive, existing=set())
    assert not (tmp_path / "boese.png").exists()
    assert not (paths.data_dir() / "imported").exists()
    broken = tmp_path / "kaputt.ndprofile"
    broken.write_bytes(b"kein zip")
    with pytest.raises(ValueError, match="Keine gültige .ndprofile-Datei"):
        share.import_profile(broken, existing=set())
    bad = tmp_path / "ungueltig.ldlprofile"
    with zipfile.ZipFile(bad, "w") as z:
        z.writestr("profile.json", json.dumps({"id": "x", "workspaces": "nein"}))
    with pytest.raises(ValueError, match="Profil ungültig"):
        share.import_profile(bad, existing=set())
