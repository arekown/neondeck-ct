"""Ordner, Sticky-Kacheln, LED-Farben je Arbeitsbereich (Task P8)."""
import contextlib

import numpy as np

from neondeck.actions.base import Result
from neondeck.device.layout import ControlRef, Display
from neondeck.device.protocol import ButtonEvent, TouchEvent
from neondeck.engine.leds import LED_ACTIVE, LED_DIM, LED_OFF
from neondeck.engine.navigation_state import MAX_DEPTH
from neondeck.engine.painter import encoder_label
from neondeck.profile.model import Assignment, ButtonImage, StateDef, TouchPage
from neondeck.render import images
from neondeck.render.images import TileSpec
from support.engine_rig import TILE5, Rig, make_profile, make_rig, pixels


def field(i):
    """Touch-Koordinaten der Mitte von Feld i."""
    return 60 + (i % 4) * 90 + 45, (i // 4) * 90 + 45


def run(cmd):
    return Assignment({"type": "run", "command": cmd}, ButtonImage(text=cmd))


def folder_profile(auto_exit=False):
    """ws1: p1 (normal, Feld 3 oeffnet f1), f1 (Ordner), p2 (normal), f2 (Ordner in f1)."""
    p = make_profile()
    ws = p.workspaces[0]
    p1 = ws.touch_pages[0]
    p1.buttons[3] = Assignment({"type": "folder", "page": "f1", "auto_exit": auto_exit},
                               ButtonImage(text="Werkzeuge"))
    f1 = TouchPage("f1", "Werkzeuge", folder=True, parent="p1")
    f1.buttons[2] = run("kate")
    f1.buttons[3] = Assignment({"type": "folder", "page": "f2"})
    f1.buttons[5] = run("im-ordner")
    p2 = TouchPage("p2", "Seite 2")
    p2.buttons[5] = run("seite2")
    f2 = TouchPage("f2", "Tief", folder=True, parent="f1")
    f2.buttons[1] = run("tief")
    ws.touch_pages[1:] = [f1, p2, f2]
    return p


def page_id(rig):
    return rig.engine.workspace.touch_pages[rig.engine.page_index].id


def commands(rig):
    return [c[1].get("command") for c in rig.ex.calls]


# --- Ordner oeffnen / zurueck --------------------------------------------------------

def test_folder_open_back():
    rig = Rig(folder_profile())
    rig.engine.redraw_all()
    rig.tap(*field(3))
    assert page_id(rig) == "f1"
    view = rig.engine.view_state()
    assert view["folder"] == "f1" and view["folder_stack"] == ["p1"]
    assert rig.ex.calls == []  # Navigation laeuft in der Engine
    # Kachel 0 ist automatisch "Zurueck"
    assert rig.engine.controls.action_for(ControlRef("touch", 0)) == {"type": "folder_back"}
    tile0 = rig.last(Display.CENTER)[:90, :90]
    assert tile0.any()
    # verschachtelt: f1 -> f2
    rig.tap(*field(3))
    assert page_id(rig) == "f2"
    assert rig.engine.view_state()["folder_stack"] == ["p1", "f1"]
    rig.tap(*field(0))  # Zurueck: eine Ebene
    assert page_id(rig) == "f1" and rig.engine.view_state()["folder_stack"] == ["p1"]
    rig.tap(*field(0))
    assert page_id(rig) == "p1"
    view = rig.engine.view_state()
    assert view["folder"] is None and view["folder_stack"] == []
    rig.tap(*field(0))  # auf einer normalen Seite ist Feld 0 nicht "Zurueck"
    assert page_id(rig) == "p1" and rig.ex.calls == []


def test_folder_breadcrumb_in_left_strip():
    rig = Rig(folder_profile())
    rig.engine.redraw_all()
    normal = rig.last(Display.LEFT)
    rig.tap(*field(3))
    ws = rig.engine.workspace
    want = images.render_strip([("Ordner › Werkzeuge", None),
                                (encoder_label(ws.encoders[1]), None),
                                (encoder_label(ws.encoders[2]), None)])
    got = rig.last(Display.LEFT)
    assert np.array_equal(got, pixels(Display.LEFT, images.to_rgb565(want)))
    rig.tap(*field(0))
    assert np.array_equal(rig.last(Display.LEFT), normal)


def test_folder_back_tile_wins_over_own_assignment_and_override():
    p = folder_profile()
    f1 = p.workspaces[0].touch_pages[1]
    f1.buttons[0] = run("verdeckt")
    rig = Rig(p)
    rig.engine.set_image_override(ControlRef("touch", 0), "/nicht/da.png")
    rig.tap(*field(3))
    rig.tap(*field(0))
    assert page_id(rig) == "p1" and rig.ex.calls == []


def test_folder_depth_limit():
    p = make_profile()
    ws = p.workspaces[0]
    ws.touch_pages[0].buttons[3] = Assignment({"type": "folder", "page": "f"})
    f = TouchPage("f", "Kreis", folder=True)
    f.buttons[3] = Assignment({"type": "folder", "page": "f"})  # oeffnet sich selbst
    ws.touch_pages.append(f)
    rig = Rig(p)
    for _ in range(MAX_DEPTH + 3):
        rig.tap(*field(3))
    assert MAX_DEPTH == 8
    assert len(rig.engine.view_state()["folder_stack"]) == MAX_DEPTH
    for _ in range(MAX_DEPTH):
        rig.tap(*field(0))
    assert page_id(rig) == "p1"


def test_folder_action_to_missing_or_normal_page_ignored():
    p = folder_profile()
    p1 = p.workspaces[0].touch_pages[0]
    p1.buttons[4] = Assignment({"type": "folder", "page": "gibtsnicht"})
    p1.buttons[6] = Assignment({"type": "folder", "page": "p2"})  # keine Ordnerseite
    rig = Rig(p)
    rig.tap(*field(4))
    rig.tap(*field(6))
    assert page_id(rig) == "p1" and rig.engine.view_state()["folder_stack"] == []


def test_folder_tile_marked():
    rig = Rig(folder_profile())
    rig.engine.redraw_all()
    tile3 = rig.last(Display.CENTER)[:90, 270:360]
    plain = images.render_tile(TileSpec(text="Werkzeuge"))
    marked = images.render_tile(TileSpec(text="Werkzeuge", badge="folder"))
    assert np.asarray(plain).tolist() != np.asarray(marked).tolist()
    want = pixels(Display.CENTER, images.to_rgb565(
        images.compose_center([None] * 3 + [marked] + [None] * 8, 0, 0)))[:90, 270:360]
    assert np.array_equal(tile3, want)


def test_render_folder_badge_in_corner():
    img = np.asarray(images.render_tile(TileSpec(badge="folder")))
    assert img[:20, -20:].any()          # Ecke oben rechts gezeichnet
    assert not img[40:50, 40:50].any()   # Mitte bleibt leer


# --- Auto-Exit -----------------------------------------------------------------------

def test_folder_auto_exit():
    rig = Rig(folder_profile(auto_exit=True))
    rig.tap(*field(3))
    rig.tap(*field(2))
    assert commands(rig) == ["kate"]
    assert page_id(rig) == "f1"  # erst nach dem Ende der Aktion zurueck
    rig.ex.finish()
    assert page_id(rig) == "p1" and rig.engine.view_state()["folder_stack"] == []


def test_folder_auto_exit_not_on_failure():
    rig = Rig(folder_profile(auto_exit=True))
    rig.tap(*field(3))
    rig.tap(*field(2))
    rig.ex.finish(result=Result(False, "kaputt"))
    assert page_id(rig) == "f1"


def test_folder_without_auto_exit_stays():
    rig = Rig(folder_profile(auto_exit=False))
    rig.tap(*field(3))
    rig.tap(*field(2))
    rig.ex.finish()
    assert page_id(rig) == "f1"


def test_folder_auto_exit_only_for_its_own_level():
    """Schon von Hand zurueck (oder tiefer gegangen): das spaete Ergebnis springt nicht."""
    rig = Rig(folder_profile(auto_exit=True))
    rig.tap(*field(3))
    rig.tap(*field(2))
    rig.tap(*field(0))  # von Hand zurueck, bevor die Aktion fertig ist
    assert page_id(rig) == "p1"
    rig.tap(*field(5))  # Feld 5 auf p1: Firefox
    rig.ex.finish(0)    # kate fertig
    rig.ex.finish(0)    # firefox fertig
    assert page_id(rig) == "p1"
    rig.tap(*field(3))
    rig.tap(*field(2))
    rig.tap(*field(3))  # in f2 (ohne Auto-Exit) weiter
    rig.ex.finish(0)
    assert page_id(rig) == "f2"


def test_folder_auto_exit_round_button_does_not_exit():
    rig = Rig(folder_profile(auto_exit=True))
    rig.tap(*field(3))
    rig.engine.handle(ButtonEvent(9, True))  # Hotkey auf runder Taste
    rig.engine.handle(ButtonEvent(9, False))
    rig.ex.finish()
    assert page_id(rig) == "f1"


# --- Ordner gehoeren nicht zu Seitenwechsel / Wischen / Seitenpunkten ----------------

def dot_lit(rig, x):
    return rig.last(Display.CENTER)[265, x].any()


def test_folder_not_in_swipe():
    rig = Rig(folder_profile())
    rig.engine.redraw_all()
    # zwei normale Seiten (p1, p2): Punkte bei x 175 und 185, nichts bei 180
    assert dot_lit(rig, 175) and dot_lit(rig, 185) and not dot_lit(rig, 180)
    rig.tap(300, 135, x_up=100)  # nach links wischen: naechste Seite
    assert page_id(rig) == "p2"
    assert dot_lit(rig, 185) and dot_lit(rig, 175)
    rig.tap(300, 135, x_up=100)
    assert page_id(rig) == "p1"
    rig.tap(100, 135, x_up=300)
    assert page_id(rig) == "p2"
    for name in ("page_next", "page_next", "page_previous"):
        rig.engine.call(name, {})
    assert page_id(rig) == "p1"
    # im Ordner: keine Seitenpunkte, Wischen tut nichts
    rig.tap(*field(3))
    assert not (dot_lit(rig, 175) or dot_lit(rig, 185))
    rig.tap(300, 135, x_up=100)
    assert page_id(rig) == "f1" and rig.ex.calls == []


def test_page_next_from_folder_leaves_it():
    rig = Rig(folder_profile())
    rig.tap(*field(3))
    rig.tap(*field(3))  # f2
    rig.engine.call("page_next", {})
    assert page_id(rig) == "p2" and rig.engine.view_state()["folder_stack"] == []


def test_page_index_to_folder_opens_it_and_normal_page_closes_it():
    rig = Rig(folder_profile())
    rig.engine.call("page", {"index": 1})  # f1 ueber den Index (z. B. Editor-Reiter)
    assert page_id(rig) == "f1" and rig.engine.view_state()["folder_stack"] == ["p1"]
    rig.engine.call("page", {"index": 2})
    assert page_id(rig) == "p2" and rig.engine.view_state()["folder_stack"] == []


def test_workspace_change_clears_folder_stack():
    rig = Rig(folder_profile())
    rig.tap(*field(3))
    rig.engine.handle(ButtonEvent(8, True))
    rig.engine.handle(ButtonEvent(8, False))
    rig.engine.handle(ButtonEvent(7, True))
    rig.engine.handle(ButtonEvent(7, False))
    assert page_id(rig) == "p1" and rig.engine.view_state()["folder_stack"] == []


def test_workspace_starts_on_first_normal_page():
    p = folder_profile()
    ws = p.workspaces[0]
    ws.touch_pages.insert(0, ws.touch_pages.pop(1))  # f1 zuerst
    rig = Rig(p)
    assert page_id(rig) == "p1"
    rig.engine.call("workspace", {"id": "ws2"})
    rig.engine.call("workspace", {"id": "ws1"})
    assert page_id(rig) == "p1"


def test_remembered_view_inside_folder_is_base_page():
    rig = Rig(folder_profile())
    rig.engine.call("page", {"index": 2})  # p2
    rig.engine.call("page", {"index": 1})  # f1 von p2 aus
    assert rig.engine.remembered_views()["default"] == {"workspace": "ws1", "page": 2}
    # gemerkte Ordnerseite (alte Einstellung) wird nicht als normale Seite gezeigt
    rig2 = Rig(folder_profile(), views={"default": {"workspace": "ws1", "page": 1}})
    assert page_id(rig2) == "p1" and rig2.engine.view_state()["folder_stack"] == []


def test_set_profile_keep_view_keeps_folder():
    rig = Rig(folder_profile())
    rig.tap(*field(3))
    p = folder_profile()
    ws = p.workspaces[0]
    ws.touch_pages.insert(0, TouchPage("p0", "Neu davor"))  # Indizes verschieben sich
    rig.engine.set_profile(p, keep_view=True)
    assert page_id(rig) == "f1" and rig.engine.view_state()["folder_stack"] == ["p1"]
    rig.tap(*field(0))
    assert page_id(rig) == "p1"


def test_set_profile_keep_view_drops_removed_folder():
    rig = Rig(folder_profile())
    rig.tap(*field(3))
    p = folder_profile()
    del p.workspaces[0].touch_pages[1]  # f1 geloescht
    rig.engine.set_profile(p, keep_view=True)
    assert page_id(rig) == "p1" and rig.engine.view_state()["folder_stack"] == []


def test_profile_change_clears_folder_stack():
    rig = Rig(folder_profile())
    rig.tap(*field(3))
    rig.engine.set_profile(folder_profile())
    assert page_id(rig) == "p1" and rig.engine.view_state()["folder_stack"] == []


# --- R25: Beruehrung vor einem Ansichtswechsel -----------------------------------------

def test_plain_touch_begun_before_view_change_does_not_fire():
    p = folder_profile()
    rig = Rig(p)
    rig.engine.handle(TouchEvent(1, *TILE5, True))   # Firefox auf p1
    rig.engine.call("page", {"index": 2})            # Seitenwechsel waehrend der Beruehrung
    rig.engine.handle(TouchEvent(1, *TILE5, False))  # p2 Feld 5: "seite2"
    assert rig.ex.calls == []
    rig.tap(*TILE5)  # neue Beruehrung wirkt wieder
    assert commands(rig) == ["seite2"]


def test_plain_touch_begun_before_folder_open_does_not_fire():
    rig = Rig(folder_profile())
    rig.engine.handle(TouchEvent(1, *TILE5, True))
    rig.tap(*field(3), finger=2)                     # zweiter Finger oeffnet den Ordner
    rig.engine.handle(TouchEvent(1, *TILE5, False))  # f1 Feld 5: "im-ordner"
    assert rig.ex.calls == [] and page_id(rig) == "f1"


def test_swipe_begun_before_view_change_does_not_navigate():
    rig = Rig(folder_profile())
    rig.engine.handle(TouchEvent(1, 300, 135, True))
    rig.engine.call("workspace", {"id": "ws2"})
    rig.engine.call("workspace", {"id": "ws1"})
    rig.engine.handle(TouchEvent(1, 100, 135, False))
    assert page_id(rig) == "p1"


# --- Sticky ------------------------------------------------------------------------

def test_sticky_on_all_pages():
    p = folder_profile()
    ws = p.workspaces[0]
    ws.sticky[5] = run("sticky")
    ws.sticky[99] = run("ungueltig")  # kein Feld: wird ignoriert
    rig = Rig(p)
    rig.tap(*TILE5)                       # p1: Firefox ersetzt
    rig.engine.call("page_next", {})
    rig.tap(*TILE5)                       # p2: "seite2" ersetzt
    rig.engine.call("page_next", {})
    rig.tap(*field(3))                    # Ordner f1: nicht sticky
    rig.tap(*TILE5)
    assert commands(rig) == ["sticky", "sticky", "im-ordner"]


def test_sticky_fills_empty_slot_and_shares_state():
    p = folder_profile()
    ws = p.workspaces[0]
    ws.sticky[7] = Assignment({"type": "run", "command": "a"}, ButtonImage(text="A"),
                              states=[StateDef(ButtonImage(text="A"), {"type": "run",
                                                                       "command": "a"}),
                                      StateDef(ButtonImage(text="B"), {"type": "run",
                                                                       "command": "b"})],
                              state_source={"type": "manual"})
    rig = Rig(p)
    rig.tap(*field(7))
    rig.engine.call("page_next", {})
    rig.tap(*field(7))  # Zustand gilt fuer die Sticky-Kachel auf allen Seiten
    assert commands(rig) == ["a", "b"]


# --- LED-Farben --------------------------------------------------------------------

def test_led_colors_per_workspace():
    p = make_profile()
    p.workspaces[0].led_color = "#ff0000"
    p.workspaces[1].led_color = None           # Standard: weiss
    p.round[10] = Assignment({"type": "workspace", "id": "gibtsnicht"})
    rig = Rig(p)
    rig.engine.redraw_all()
    leds = rig.leds[-1]
    assert leds[7] == (255, 0, 0)
    assert leds[8] == (51, 51, 51)             # weiss mit 20 %
    assert leds[9] == LED_DIM                  # andere Aktion wie bisher
    assert leds[10] == LED_OFF and leds[11] == LED_OFF  # Ziel gibt es nicht: aus
    rig.engine.call("workspace", {"id": "ws2"})
    leds = rig.leds[-1]
    assert leds[8] == LED_ACTIVE and leds[7] == (51, 0, 0)


def test_led_colors_stay_off_while_dark():
    p = make_profile()
    p.workspaces[0].led_color = "#00ff00"
    rig = Rig(p)
    rig.engine.redraw_all()
    rig.engine.lock()
    assert set(rig.leds[-1].values()) == {LED_OFF}
    n = len(rig.leds)
    rig.engine.call("workspace", {"id": "ws2"})
    rig.engine.redraw_all()
    assert all(set(c.values()) == {LED_OFF} for c in rig.leds[n - 1:])  # dunkel: nur aus
    rig.engine.unlock()
    assert rig.leds[-1][8] == LED_ACTIVE and rig.leds[-1][7] == (0, 51, 0)


# --- Fix-Runde 1 -------------------------------------------------------------------------

def test_nested_folder_middle_level_removed_on_save():
    rig = Rig(folder_profile())
    rig.tap(*field(3))
    rig.tap(*field(3))  # p1 -> f1 -> f2
    p = folder_profile()
    del p.workspaces[0].touch_pages[1]  # f1 (mittlere Ebene) geloescht, f2 bleibt
    rig.engine.set_profile(p, keep_view=True)
    assert page_id(rig) == "p1" and rig.engine.view_state()["folder_stack"] == []


def test_page_index_of_open_folder_pops_down_to_it():
    rig = Rig(folder_profile())
    rig.tap(*field(3))
    rig.tap(*field(3))  # p1 -> f1 -> f2
    rig.engine.call("page", {"index": 1})  # f1 ist schon offen: dorthin zurueck
    assert page_id(rig) == "f1" and rig.engine.view_state()["folder_stack"] == ["p1"]
    rig.tap(*field(0))
    assert page_id(rig) == "p1"


def test_set_profile_rollback_restores_view_counter():
    rig = Rig(folder_profile())
    rig.engine.handle(TouchEvent(1, *TILE5, True))
    bad = folder_profile()
    bad.workspaces[0].touch_pages[0].buttons[5].image.bg = "#zzzzzz"
    with contextlib.suppress(ValueError):
        rig.engine.set_profile(bad)
    rig.engine.handle(TouchEvent(1, *TILE5, False))  # altes Profil, alte Ansicht: wirkt
    assert commands(rig) == ["firefox"]


# R26: Speichern im Editor (keep_view) ist kein Ansichtswechsel

def test_touch_during_editor_save_unchanged_fires():
    rig = Rig(folder_profile())
    rig.engine.handle(TouchEvent(1, *TILE5, True))
    rig.engine.set_profile(folder_profile(), keep_view=True)  # neue Objekte, gleicher Inhalt
    rig.engine.handle(TouchEvent(1, *TILE5, False))
    assert commands(rig) == ["firefox"]


def test_touch_during_editor_save_changed_does_nothing():
    rig = Rig(folder_profile())
    rig.engine.handle(TouchEvent(1, *TILE5, True))
    p = folder_profile()
    p.workspaces[0].touch_pages[0].buttons[5] = run("anders")
    rig.engine.set_profile(p, keep_view=True)
    rig.engine.handle(TouchEvent(1, *TILE5, False))
    assert rig.ex.calls == []
    rig.tap(*TILE5)
    assert commands(rig) == ["anders"]


def test_touch_during_editor_save_that_closes_folder_does_nothing():
    rig = Rig(folder_profile())
    rig.tap(*field(3))  # f1
    rig.engine.handle(TouchEvent(1, *TILE5, True))
    p = folder_profile()
    del p.workspaces[0].touch_pages[1]  # f1 weg -> zurueck auf p1 (Ansichtswechsel)
    rig.engine.set_profile(p, keep_view=True)
    rig.engine.handle(TouchEvent(1, *TILE5, False))
    assert rig.ex.calls == [] and page_id(rig) == "p1"


HK = {"type": "hold_key", "keys": ["KEY_LEFTSHIFT"]}


def held_profile(hold):
    p = folder_profile()
    p.square[15] = Assignment({"type": "run", "command": "tippen"}, hold=hold)
    return p


def test_held_key_during_editor_save_changed_assignment_released():
    rig = make_rig(held_profile(HK))
    rig.engine.handle(ButtonEvent(15, True))
    rig.timers.advance(0.6)  # Halten: hold_key gedrueckt
    rig.engine.set_profile(held_profile({"type": "run", "command": "neu"}), keep_view=True)
    rig.engine.handle(ButtonEvent(15, False))
    rig.timers.advance(1.0)
    assert [(c[1]["type"], c[3]) for c in rig.ex.calls] == [("hold_key", True),
                                                             ("hold_key", False)]


def test_held_key_during_editor_save_unchanged_keeps_gesture():
    rig = make_rig(held_profile(HK))
    rig.engine.handle(ButtonEvent(15, True))
    rig.timers.advance(0.6)
    rig.engine.set_profile(held_profile(HK), keep_view=True)
    rig.engine.handle(ButtonEvent(15, False))
    rig.timers.advance(1.0)
    assert [(c[1]["type"], c[3]) for c in rig.ex.calls] == [("hold_key", True),
                                                             ("hold_key", False)]


def double_profile():
    p = folder_profile()
    p.workspaces[0].touch_pages[0].buttons[5] = Assignment(
        {"type": "run", "command": "tippen"}, double={"type": "run", "command": "doppelt"})
    return p


def test_pending_double_survives_editor_save():
    rig = make_rig(double_profile())
    rig.tap(*TILE5)
    rig.engine.set_profile(double_profile(), keep_view=True)  # im Doppeltipp-Fenster
    rig.tap(*TILE5)
    rig.timers.advance(1.0)
    assert commands(rig) == ["doppelt"]


def test_pending_tap_on_changed_tile_dropped_by_editor_save():
    rig = make_rig(double_profile())
    rig.tap(*TILE5)
    p = double_profile()
    p.workspaces[0].touch_pages[0].buttons[5].double = {"type": "run", "command": "neu"}
    rig.engine.set_profile(p, keep_view=True)
    rig.timers.advance(1.0)
    assert rig.ex.calls == []
