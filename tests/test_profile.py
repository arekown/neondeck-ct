import json

from neondeck.profile.model import (
    Assignment,
    ButtonImage,
    Encoder,
    Profile,
    TouchPage,
    Wheel,
    Workspace,
    empty_profile,
)
from neondeck.profile.store import ProfileStore


def _two_ws_profile() -> Profile:
    p = empty_profile("t", "Test")
    buttons = [None] * 12
    buttons[3] = Assignment({"type": "shortcut", "keys": "KEY_A"},
                            ButtonImage(bg="#123456", icon="svg:x.svg", text="A"))
    p.workspaces[0].touch_pages[0].buttons = buttons
    p.round[8] = Assignment({"type": "noop"}, ButtonImage())
    p.square[20] = Assignment({"type": "noop"}, ButtonImage(text="x"))
    enc = [Encoder(None, None) for _ in range(6)]
    enc[1] = Encoder({"type": "volume"}, {"type": "mute"}, "Lautstärke")
    p.workspaces.append(Workspace("ws2", "Zwei", [TouchPage("p9", "Neun", [None] * 12)],
                                  enc, Wheel({"type": "scroll"}, "label", "Rad")))
    return p


def test_roundtrip():
    p = _two_ws_profile()
    q = Profile.from_json(json.loads(json.dumps(p.to_json())))
    assert q == p
    assert q.workspaces[0].touch_pages[0].buttons[3].image.text == "A"


def test_pads_lists():
    d = empty_profile().to_json()
    d["workspaces"][0]["touch_pages"][0]["buttons"] = [None] * 4 + [
        {"action": {"type": "noop"}}] + [None]
    d["workspaces"][0]["encoders"] = d["workspaces"][0]["encoders"][:2]
    p = Profile.from_json(d)
    page = p.workspaces[0].touch_pages[0]
    assert len(page.buttons) == 12
    assert page.buttons[4].action == {"type": "noop"}
    assert page.buttons[4].image == ButtonImage()
    assert all(b is None for b in page.buttons[5:])
    assert len(p.workspaces[0].encoders) == 6
    d["workspaces"][0]["touch_pages"][0]["buttons"] = [None] * 20
    assert len(Profile.from_json(d).workspaces[0].touch_pages[0].buttons) == 12


def test_round_keys_are_codes():
    d = empty_profile().to_json()
    d["round"] = {"7": None, "9": {"action": {"type": "noop"}}}
    d["square"] = {"15": None}
    p = Profile.from_json(d)
    assert sorted(p.round) == list(range(7, 15))
    assert sorted(p.square) == list(range(15, 27))
    assert p.round[9].action == {"type": "noop"}
    assert p.round[7] is None
    out = p.to_json()
    assert set(out["round"]) == {str(i) for i in range(7, 15)}


def test_empty_profile_shape():
    p = Profile.empty("x")
    assert (p.id, p.name, p.version) == ("x", "Standard", 2)
    assert len(p.workspaces) == 1 and p.workspaces[0].name == "Allgemein"
    assert p.home_workspace == p.workspaces[0].id


def test_save_atomic(tmp_path):
    s = ProfileStore(tmp_path / "profiles")
    s.save(_two_ws_profile())
    assert not list((tmp_path / "profiles").glob("*.tmp"))
    assert json.loads((tmp_path / "profiles" / "t.json").read_text())["id"] == "t"
    assert s.list() == ["t"]
    assert s.load("t") == _two_ws_profile()


def test_broken_json_recovered(tmp_path):
    s = ProfileStore(tmp_path)
    (tmp_path / "default.json").write_text("{kaputt")
    p, err = s.load_or_recover("default")
    assert p == empty_profile("default") and err
    assert (tmp_path / "default.json").read_text() == "{kaputt"
    copies = list(tmp_path.glob("default.json.kaputt-*"))
    assert len(copies) == 1 and copies[0].read_text() == "{kaputt"


def test_missing_is_no_error(tmp_path):
    p, err = ProfileStore(tmp_path).load_or_recover("nix")
    assert err is None and p.id == "nix"


def test_delete_removes_only_the_profile_file(tmp_path):
    store = ProfileStore(tmp_path)
    store.save(Profile.empty("a", "A"))
    store.save(Profile.empty("b", "B"))
    backup = tmp_path / "a.json.kaputt-20260101-000000"
    backup.write_text("{")
    store.delete("a")
    store.delete("gibtsnicht")  # fehlend: kein Fehler
    assert store.list() == ["b"]
    assert backup.exists()
    assert store.path("b") == tmp_path / "b.json"


def test_infinite_factor_recovered(tmp_path):
    """I-2: ``"factor": Infinity`` (gueltiges Python-JSON) darf den Start nie verhindern."""
    s = ProfileStore(tmp_path)
    s.save(_two_ws_profile())
    path = s.path("t")
    text = path.read_text()
    assert '"factor": 1' in text
    path.write_text(text.replace('"factor": 1', '"factor": Infinity', 1))
    p, err = s.load_or_recover("t")
    assert err is None  # Faktor wird wie jeder ungueltige Wert zu 1, der Rest bleibt
    assert p == _two_ws_profile()
    assert not list(path.parent.glob("t.json.kaputt-*"))


def test_deeply_nested_json_recovered(tmp_path):
    """I-2: tief verschachteltes JSON (RecursionError) wird wie kaputtes JSON behandelt."""
    s = ProfileStore(tmp_path)
    (tmp_path / "default.json").write_text("[" * 100_000)
    p, err = s.load_or_recover("default")
    assert p == empty_profile("default") and err
    assert len(list(tmp_path.glob("default.json.kaputt-*"))) == 1


def test_factor_overflow_is_one():
    from neondeck.profile.schema import clamp_factor as _factor
    assert _factor(float("inf")) == 1 and _factor(float("-inf")) == 1
