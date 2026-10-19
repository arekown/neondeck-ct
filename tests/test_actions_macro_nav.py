import time
from datetime import datetime

from neondeck.actions import execute, registry
from neondeck.engine.stopwatch import Stopwatch
from neondeck.render.live import live_image
from support.fakes import FakePopen, make_ctx


def make():
    popen, nav = FakePopen(), []
    return make_ctx(popen=popen, engine_call=lambda n, p: nav.append((n, p))), popen, nav


def test_macro_runs_in_order_with_sleep():
    ctx, popen, _ = make()
    t = time.monotonic()
    res = execute({"type": "macro", "steps": [{"type": "run", "command": "a"},
                                              {"type": "sleep", "ms": 50},
                                              {"type": "run", "command": "b"}]}, ctx)
    assert res.ok and time.monotonic() - t >= 0.05
    assert [c[0][0] for c in popen.calls] == ["a", "b"]


def test_macro_stops_on_error():
    ctx, popen, _ = make()
    res = execute({"type": "macro", "steps": [{"type": "run", "command": "a"}, {"type": "nope"},
                                              {"type": "run", "command": "c"}]}, ctx)
    assert not res.ok and res.message.startswith("Schritt 2:")
    assert [c[0][0] for c in popen.calls] == ["a"]


def test_macro_recursion_limit():
    ctx, _, _ = make()
    m = {"type": "macro", "steps": []}
    m["steps"].append(m)
    res = execute(m, ctx)
    assert not res.ok and "verschachtelt" in res.message


def test_sleep_clamped():
    ctx, _, _ = make()
    assert execute({"type": "sleep", "ms": 0}, ctx).ok


def test_adjust_macro():
    ctx, popen, _ = make()
    a = {"type": "adjust_macro", "left": [{"type": "run", "command": "l"}],
         "right": [{"type": "run", "command": "r"}], "reset": [{"type": "run", "command": "z"}]}
    execute(a, ctx, steps=2, pressed=False)
    execute(a, ctx, steps=-1, pressed=False)
    execute(a, ctx, steps=0, pressed=True)
    assert [c[0][0] for c in popen.calls] == ["r", "r", "l", "z"]
    assert execute({"type": "adjust_macro"}, ctx).ok
    assert registry()["adjust_macro"].kinds == {"rotate", "press"}


def test_unsupported():
    ctx, _, _ = make()
    res = execute({"type": "unsupported", "original": "Foo"}, ctx)
    assert not res.ok and res.message == "Noch nicht umgesetzt: Foo"


def test_workspace_calls_engine():
    ctx, _, nav = make()
    execute({"type": "workspace", "id": "ws2"}, ctx)
    execute({"type": "page_next"}, ctx)
    execute({"type": "page_previous"}, ctx)
    execute({"type": "page", "index": 3}, ctx)
    execute({"type": "open_config"}, ctx)
    execute({"type": "profile", "id": "p1"}, ctx)
    assert nav == [("workspace", {"id": "ws2"}), ("page_next", {}), ("page_previous", {}),
                   ("page", {"index": 3}), ("open_config", {}), ("profile", {"id": "p1"})]


def test_live_date_week():
    d = datetime(2026, 10, 17, 9, 5)
    assert live_image({"type": "date", "format": "week"}, d).text == "KW 42"
    assert live_image({"type": "date", "format": "date"}, d).text == "17.10."
    c = live_image({"type": "clock"}, d)
    assert c.text == "09:05" and c.value == "Sa 17.10."
    assert live_image({"type": "run"}, d) is None


def test_display_actions_noop():
    ctx, _, _ = make()
    for t in ("clock", "date", "stopwatch"):
        assert execute({"type": t}, ctx).ok


def test_stopwatch_start_stop_reset():
    sw = Stopwatch()
    assert sw.display(0) == "00:00"
    sw.press(0.1, 100.0)
    assert sw.display(165.0) == "01:05"
    sw.press(0.1, 170.0)
    assert sw.display(999.0) == "01:10"
    sw.press(0.1, 1000.0)
    assert sw.display(1000.0 + 3700) == "1:02:50"
    sw.press(1.5, 5000.0)
    assert sw.display(6000.0) == "00:00" and not sw.running
    st = Stopwatch()
    st.press(0.1, 0.0)
    assert live_image({"type": "stopwatch"}, datetime.fromtimestamp(7), st).text == "00:07"
