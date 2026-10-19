import json
import os
import time
from pathlib import Path

from neondeck.profile.model import (
    Assignment,
    ButtonImage,
    Encoder,
    EncoderLayer,
    Profile,
    StateDef,
    TouchPage,
    Wheel,
    empty_profile,
)
from neondeck.profile.store import ProfileStore

DATA = Path(__file__).parent / "data"


def test_v1_file_migrates():
    p = Profile.from_json(json.loads((DATA / "profile-v1.json").read_text()))
    assert p.app_ids == ["org.kde.konsole"]
    assert p.version == 2
    assert p.dynamic is True and p.hold_profile is False
    a = p.round[7]
    assert a.action == {"type": "shortcut", "keys": "KEY_A"}
    assert a.image.text == "A" and a.image.bg == "#112233"
    assert (a.image.layout, a.image.font, a.image.font_size) == ("auto", None, None)
    assert (a.image.align_h, a.image.align_v, a.image.icon_color) == ("center", "center", None)
    assert (a.double, a.hold, a.states, a.state_source) == (None, None, [], None)
    ws = p.workspaces[0]
    e = ws.encoders[0]
    assert e.rotate == {"type": "volume"} and e.label == "Laut"
    assert (e.left, e.right, e.invert, e.factor, e.layers, e.strip) == \
        (None, None, False, 1, [], "name_value")
    assert (ws.wheel.left, ws.wheel.right, ws.wheel.invert, ws.wheel.factor,
            ws.wheel.tap, ws.wheel.image) == (None, None, False, 1, None, None)
    assert (ws.led_color, ws.sticky) == (None, {})
    assert ws.touch_pages[0].folder is False and ws.touch_pages[0].parent is None


def test_v1_without_app_has_no_app_ids():
    d = json.loads((DATA / "profile-v1.json").read_text())
    d["app"] = None
    assert Profile.from_json(d).app_ids == []


def _full_profile() -> Profile:
    img = ButtonImage(bg="#010203", icon="svg:a.svg", text="T", text_color="#fefefe",
                      layout="icon_text", font="Sans", font_size=18, align_h="left",
                      align_v="bottom", icon_color="#ff0000")
    a = Assignment({"type": "noop"}, img, double={"type": "d"}, hold={"type": "h"},
                   states=[StateDef(img, {"type": "s1"}), StateDef(ButtonImage(text="2"))],
                   state_source={"type": "mute"})
    p = empty_profile("full", "Voll")
    p.app_ids = ["a.b", "c.d"]
    p.dynamic = False
    p.hold_profile = True
    p.round[8] = a
    ws = p.workspaces[0]
    ws.led_color = "#00ff00"
    ws.sticky = {5: a}
    ws.touch_pages = [TouchPage("p1", "Eins", [a] + [None] * 11, folder=True, parent="p0")]
    ws.encoders[2] = Encoder({"type": "r"}, {"type": "p"}, "L", left={"type": "l"},
                             right={"type": "rr"}, invert=True, factor=3,
                             layers=[EncoderLayer({"type": "x"}, {"type": "y"}, {"type": "z"},
                                                  {"type": "w"}, "Lay")],
                             strip="bar")
    ws.wheel = Wheel({"type": "r"}, "image", "W", left={"type": "l"}, right={"type": "rr"},
                     invert=True, factor=2, tap={"type": "t"}, image=img)
    return p


def test_roundtrip_all_new_fields():
    p = _full_profile()
    q = Profile.from_json(json.loads(json.dumps(p.to_json())))
    assert q == p
    assert q.workspaces[0].sticky[5].states[1].image.text == "2"
    assert q.version == 2


def test_missing_new_fields_defaults():
    d = {"id": "x", "name": "X", "workspaces": [
        {"id": "w", "name": "W", "touch_pages": [{"id": "p", "name": "P",
         "buttons": [{"action": {"type": "noop"}}]}],
         "encoders": [{"rotate": None}, {"layers": [{"label": "nur Label"}]}],
         "wheel": {"display": "arc"}}]}
    p = Profile.from_json(d)
    assert p.app_ids == [] and p.dynamic is True and p.version == 2
    b = p.workspaces[0].touch_pages[0].buttons[0]
    assert b.states == [] and b.image == ButtonImage()
    assert p.workspaces[0].encoders[1].layers == [EncoderLayer(label="nur Label")]
    assert p.workspaces[0].wheel.display == "arc"
    assert Profile.from_json(p.to_json()) == p


def _store(tmp_path):
    return ProfileStore(tmp_path / "profiles")


def _prof(text):
    p = empty_profile("t", "Test")
    p.round[7] = Assignment({"type": "noop"}, ButtonImage(text=text))
    return p


def test_snapshot_on_save(tmp_path):
    s = _store(tmp_path)
    s.save(_prof("alt"))
    assert s.versions("t") == []
    s.save(_prof("neu"))
    v = s.versions("t")
    assert len(v) == 1 and v[0].size > 0
    assert (s.dir / ".versionen" / "t" / v[0].name).exists()
    old = json.loads((s.dir / ".versionen" / "t" / v[0].name).read_text())
    assert old["round"]["7"]["image"]["text"] == "alt"
    assert s.load("t").round[7].image.text == "neu"
    assert s.list() == ["t"]


def test_no_snapshot_if_unchanged(tmp_path):
    s = _store(tmp_path)
    s.save(_prof("a"))
    s.save(_prof("a"))
    s.save(_prof("a"))
    assert s.versions("t") == []


def test_rapid_saves_do_not_collide(tmp_path):
    s = _store(tmp_path)
    for i in range(6):
        s.save(_prof(str(i)))
    assert len(s.versions("t")) == 5


def test_list_ignores_snapshots_and_broken(tmp_path):
    s = _store(tmp_path)
    s.save(_prof("a"))
    s.save(_prof("b"))
    (s.dir / "t.json.kaputt-20260101-000000").write_text("x")
    assert s.list() == ["t"]


def _make_snaps(s, n, age_days=0.0):
    d = s.dir / ".versionen" / "t"
    d.mkdir(parents=True, exist_ok=True)
    names = []
    for i in range(n):
        t = time.time() - age_days * 86400 - (n - i)
        name = time.strftime("%Y%m%d-%H%M%S", time.localtime(t)) + f"-{i:06d}.json"
        (d / name).write_text("{}")
        os.utime(d / name, (t, t))
        names.append(name)
    return names


def test_prune_max_100(tmp_path):
    s = _store(tmp_path)
    s.save(_prof("0"))
    _make_snaps(s, 120)
    s.save(_prof("1"))
    assert len(s.versions("t")) == 100


def test_prune_keeps_newest_10(tmp_path):
    s = _store(tmp_path)
    s.save(_prof("0"))
    names = _make_snaps(s, 15, age_days=90)
    s.save(_prof("1"))
    left = {v.name for v in s.versions("t")}
    # 15 alte + 1 frischer Snapshot; alte >60 Tage fallen bis auf die neuesten 10 weg
    assert len(left) == 10
    assert set(names[-9:]) <= left
    assert names[0] not in left


def test_restore_snapshots_current_first(tmp_path):
    s = _store(tmp_path)
    s.save(_prof("eins"))
    s.save(_prof("zwei"))
    first = s.versions("t")[0]
    p = s.restore("t", first.name)
    assert p.round[7].image.text == "eins"
    assert s.load("t").round[7].image.text == "eins"
    texts = [json.loads((s.dir / ".versionen" / "t" / v.name).read_text())
             ["round"]["7"]["image"]["text"] for v in s.versions("t")]
    assert "zwei" in texts and len(texts) == 2
    assert not list(s.dir.glob("*.tmp"))


def test_save_survives_non_utf8_existing_file(tmp_path):
    s = _store(tmp_path)
    s.dir.mkdir(parents=True)
    (s.dir / "t.json").write_bytes(b"\xff\xfe\x00garbage")
    s.save(_prof("neu"))
    assert s.load("t").round[7].image.text == "neu"


def test_save_survives_unwritable_versions_dir(tmp_path):
    s = _store(tmp_path)
    s.save(_prof("alt"))
    (s.dir / ".versionen").write_text("ich bin eine Datei")  # mkdir scheitert
    s.save(_prof("neu"))
    assert s.load("t").round[7].image.text == "neu"


def test_prune_keeps_young_snapshots(tmp_path):
    s = _store(tmp_path)
    s.save(_prof("0"))
    young = _make_snaps(s, 15, age_days=30)
    s.save(_prof("1"))
    assert {v.name for v in s.versions("t")} >= set(young)


def test_sticky_bad_key_skipped():
    d = {"id": "x", "workspaces": [{"id": "w", "sticky": {
        "abc": {"action": {"type": "noop"}}, "20": {"action": {"type": "noop"}},
        "3": {"action": {"type": "noop"}}}}]}
    assert list(Profile.from_json(d).workspaces[0].sticky) == [3]


def test_loaded_profile_is_always_valid():
    """Was ``from_json`` laedt, laesst sich wieder speichern (unbekannte Auswahlwerte bleiben,
    Sticky-Felder ausserhalb 0..11 entfallen)."""
    from neondeck.profile.model import validate_profile_json
    d = {"id": "x", "workspaces": [{"id": "w", "wheel": {"display": "foo"},
         "sticky": {"20": {"action": {}}}, "touch_pages": [{"id": "p", "buttons": [
             {"action": {}, "image": {"layout": "weird", "align_h": "mitte"}}]}]}]}
    out = Profile.from_json(d).to_json()
    assert validate_profile_json(out) == []
    assert out["workspaces"][0]["wheel"]["display"] == "foo"


def test_factor_coerced_and_clamped():
    assert Encoder.from_json({"factor": 99}).factor == 10
    assert Encoder.from_json({"factor": 0}).factor == 1
    assert Encoder.from_json({"factor": "x"}).factor == 1
    assert Wheel.from_json({"factor": "3"}).factor == 3
    assert Wheel.from_json({"factor": None}).factor == 1


def test_future_version_warns(caplog):
    with caplog.at_level("WARNING"):
        Profile.from_json({"id": "x", "version": 3})
    assert "version" in caplog.text.lower()


# --- Strukturpruefung fuer Profile aus der API (validate_profile_json) ----------------------

def test_validate_accepts_everything_to_json_produces():
    from neondeck.profile.model import validate_profile_json
    assert validate_profile_json(_full_profile().to_json()) == []
    assert validate_profile_json(empty_profile("default", "Standard").to_json()) == []
    assert validate_profile_json(json.loads((DATA / "profile-v1.json").read_text())) == []
    d = {"id": "x", "name": "X", "workspaces": [
        {"id": "w", "name": "W", "touch_pages": [{"id": "p", "name": "P",
         "buttons": [{"action": {"type": "noop"}}, None]}],
         "encoders": [{"rotate": None}, {"layers": [{"label": "nur Label"}]}],
         "wheel": {"display": "arc"}}]}
    assert validate_profile_json(d) == []  # fehlende neue Felder sind erlaubt


def test_validate_rejects_broken_structures():
    from neondeck.profile.model import validate_profile_json
    good = empty_profile("t", "T").to_json()

    def broken(change):
        d = json.loads(json.dumps(good))
        change(d)
        return validate_profile_json(d)

    ws = lambda d: d["workspaces"][0]  # noqa: E731 - kurze Hilfe im Test
    page = lambda d: ws(d)["touch_pages"][0]  # noqa: E731 - kurze Hilfe im Test
    cases = {
        "kein Objekt": lambda d: d.clear() or d.update({"x": 1}),
        "id fehlt": lambda d: d.pop("id"),
        "id mit Pfad": lambda d: d.update(id="../settings"),
        "keine Arbeitsbereiche": lambda d: d.update(workspaces=[]),
        "Arbeitsbereiche kein Liste": lambda d: d.update(workspaces={"a": 1}),
        "Arbeitsbereich kein Objekt": lambda d: d.update(workspaces=["ws1"]),
        "Seiten kein Liste": lambda d: ws(d).update(touch_pages="p1"),
        "Seite kein Objekt": lambda d: ws(d).update(touch_pages=[3]),
        "Tasten kein Liste": lambda d: page(d).update(buttons={"0": None}),
        "Taste kein Objekt": lambda d: page(d)["buttons"].__setitem__(0, "Taste"),
        "Aktion kein Objekt": lambda d: page(d)["buttons"].__setitem__(0, {"action": "run"}),
        "Doppel kein Objekt": lambda d: page(d)["buttons"].__setitem__(
            0, {"action": {"type": "noop"}, "double": 5}),
        "Farbe kaputt": lambda d: page(d)["buttons"].__setitem__(
            0, {"action": {"type": "noop"}, "image": {"bg": "#zzzzzz"}}),
        "Text kein String": lambda d: page(d)["buttons"].__setitem__(
            0, {"action": {}, "image": {"text": 5}}),
        "Regler kein Liste": lambda d: ws(d).update(encoders={"0": {}}),
        "Regler-Aktion kaputt": lambda d: ws(d)["encoders"].__setitem__(0, {"rotate": [1]}),
        "Faktor unendlich": lambda d: ws(d)["encoders"].__setitem__(0, {"factor": float("inf")}),
        "Rad kein Objekt": lambda d: ws(d).update(wheel="clock"),
        "runde Taste kaputt": lambda d: d["round"].update({"7": {"action": "x"}}),
        "runde Tasten kein Objekt": lambda d: d.update(round=[1]),
        "Sticky kaputt": lambda d: ws(d).update(sticky={"20": "x"}),
        "app_ids kein Liste": lambda d: d.update(app_ids="firefox"),
        "dynamic kein bool": lambda d: d.update(dynamic="ja"),
        "Zustaende kein Liste": lambda d: page(d)["buttons"].__setitem__(
            0, {"action": {}, "states": {"0": {}}}),
        "Tastencode unbekannt": lambda d: d["round"].update({"99": None}),
        "Sticky-Feld unbekannt": lambda d: ws(d).update(sticky={"99": {"action": {}}}),
    }
    for name, change in cases.items():
        errors = broken(change)
        assert errors, name
        assert all(isinstance(e, str) and e for e in errors), name
