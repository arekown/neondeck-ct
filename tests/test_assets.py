import json
import os
import shutil

from neondeck.core import assets


def _make_source(root):
    de = root / "assets-unpacked" / "imagelib-Loupedeck_de-DE"
    ne = root / "assets-unpacked" / "imagelib-Loupedeck"
    for base in (de,):
        (base / "80x80" / "Photoshop").mkdir(parents=True)
        (base / "80x80" / "Photoshop" / "Brush.png").write_bytes(b"png1")
        (base / "80x80" / "0.png").write_bytes(b"png2")
    (ne / "80x80").mkdir(parents=True)
    gen = root / "app/service/ProgramFiles64Folder/Logi/LogiPluginService/Plugins/@Generic"
    (gen / "actionicons").mkdir(parents=True)
    (gen / "actionicons" / "a.svg").write_text("<svg/>")
    (gen / "actionsymbols").mkdir(parents=True)
    ic = root / "assets-unpacked" / "licons-DefaultIcons" / "sub"
    ic.mkdir(parents=True)
    (ic / "i.svg").write_text("<svg/>")
    (ic / "skip.txt").write_text("x")
    snd = root / "assets-unpacked" / "lsounds-LoupedeckSoundPack"
    snd.mkdir(parents=True)
    (snd / "s.wav").write_bytes(b"w")
    prof = root / "assets-unpacked" / "lp5-DefaultProfile20"
    prof.mkdir(parents=True)
    (prof / "ProfileInfo.json").write_text("{}")


def test_import_copies_and_manifest(tmp_path, monkeypatch):
    monkeypatch.setenv("NEONDECK_HOME", str(tmp_path / "home"))
    src = tmp_path / "src"
    _make_source(src)
    m = assets.import_assets(src)
    root = assets.assets_dir()
    assert m["library"] == 2
    assert m["library_neutral"] == 0
    assert m["actionicons"] == 1 and m["actionsymbols"] == 0
    assert m["icons"] == 1 and m["sounds"] == 1
    assert json.loads((root / "manifest.json").read_text()) == m
    assert (root / "library/de/80x80/Photoshop/Brush.png").exists()
    assert (root / "icons/i.svg").exists()
    assert (root / "defaults/DefaultProfile20/ProfileInfo.json").exists()
    calls = []
    real = shutil.copy2
    monkeypatch.setattr(shutil, "copy2", lambda a, b: calls.append(b) or real(a, b))
    assets.import_assets(src)
    assert calls == []
    # destination with differing mtime is recopied
    f = root / "library/de/80x80/0.png"
    os.utime(f, (1, 1))
    assets.import_assets(src)
    assert calls == [f]
    assert f.stat().st_mtime_ns == (src / "assets-unpacked/imagelib-Loupedeck_de-DE/80x80/0.png").stat().st_mtime_ns


def test_resolve_prefers_de(tmp_path, monkeypatch):
    monkeypatch.setenv("NEONDECK_HOME", str(tmp_path))
    root = assets.assets_dir()
    for lang in ("de", "neutral"):
        (root / "library" / lang / "80x80").mkdir(parents=True)
        (root / "library" / lang / "80x80" / "a.png").write_bytes(b"x")
    (root / "library/neutral/80x80/b.png").write_bytes(b"x")
    assert assets.resolve("lib:80x80/a.png") == root / "library/de/80x80/a.png"
    assert assets.resolve("lib:80x80/b.png") == root / "library/neutral/80x80/b.png"


def test_resolve_svg_and_file(tmp_path, monkeypatch):
    monkeypatch.setenv("NEONDECK_HOME", str(tmp_path))
    root = assets.assets_dir()
    (root / "icons").mkdir(parents=True)
    (root / "icons/x.svg").write_text("<svg/>")
    assert assets.resolve("svg:icons/x.svg") == root / "icons/x.svg"
    f = tmp_path / "f.png"
    f.write_bytes(b"x")
    assert assets.resolve(f"file:{f}") == f


def test_resolve_missing_none(tmp_path, monkeypatch):
    monkeypatch.setenv("NEONDECK_HOME", str(tmp_path))
    assert assets.resolve("lib:80x80/nope.png") is None
    assert assets.resolve("svg:icons/nope.svg") is None
    assert assets.resolve("file:/nonexistent/x.png") is None
    assert assets.resolve("quatsch") is None
    assert assets.resolve("svg:icons/../../x") is None


def test_catalog_groups(tmp_path, monkeypatch):
    monkeypatch.setenv("NEONDECK_HOME", str(tmp_path))
    root = assets.assets_dir()
    d = root / "library/de/80x80"
    (d / "Photoshop").mkdir(parents=True)
    (d / "Photoshop/Brush.png").write_bytes(b"x")
    (d / "0.png").write_bytes(b"x")
    (root / "library/neutral/80x80").mkdir(parents=True)
    (root / "library/neutral/80x80/0.png").write_bytes(b"x")
    (root / "library/neutral/80x80/n.png").write_bytes(b"x")
    (root / "actionicons").mkdir()
    (root / "actionicons/a.svg").write_text("<svg/>")
    (root / "icons").mkdir()
    (root / "icons/i.svg").write_text("<svg/>")
    cat = {e.ref: e for e in assets.catalog()}
    assert cat["lib:80x80/Photoshop/Brush.png"].group == "Photoshop"
    assert cat["lib:80x80/Photoshop/Brush.png"].name == "Brush"
    assert cat["lib:80x80/0.png"].group == "Allgemein"
    assert "lib:80x80/n.png" in cat
    assert cat["svg:actionicons/a.svg"].group == "Aktions-Icons"
    assert cat["svg:icons/i.svg"].group == "Icons"
    assert len([e for e in assets.catalog() if e.ref == "lib:80x80/0.png"]) == 1


def test_resolve_rejects_absolute_and_foreign_dirs(tmp_path, monkeypatch):
    monkeypatch.setenv("NEONDECK_HOME", str(tmp_path))
    f = tmp_path / "x.svg"
    f.write_text("<svg/>")
    assert assets.resolve("svg:/etc/passwd") is None
    assert assets.resolve(f"svg:{f}") is None
    assert assets.resolve(f"lib:{f}") is None
    assert assets.resolve("svg:sounds/s.wav") is None
    assert assets.resolve("svg:manifest.json") is None
