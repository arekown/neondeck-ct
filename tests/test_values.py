"""Gemeinsame Qt-freie Grundbausteine: Werte-Helfer, Aufruf mit Log, Bedienelemente."""
import logging

from neondeck.core.guard import call_logged
from neondeck.core.values import is_int, join_errors, parse_view
from neondeck.device.layout import CONTROL_COUNTS, ControlRef, all_controls


def test_is_int_excludes_bool():
    assert is_int(0) and is_int(-3)
    assert not is_int(True) and not is_int(1.0) and not is_int("1")


def test_parse_view_with_and_without_min_page():
    assert parse_view({"workspace": "w", "page": -1}) == ("w", -1)
    assert parse_view({"workspace": "w", "page": -1}, min_page=0) is None
    assert parse_view({"workspace": "w", "page": 2}, min_page=0) == ("w", 2)
    assert parse_view({"workspace": "w", "page": True}) is None
    assert parse_view({"workspace": 1, "page": 0}) is None
    assert parse_view("w") is None


def test_join_errors_limit_and_more():
    errors = [f"e{i}" for i in range(7)]
    assert join_errors(errors, 5) == "e0; e1; e2; e3; e4"
    assert join_errors(errors, 5, with_more=True) == "e0; e1; e2; e3; e4 (und 2 weitere)"
    assert join_errors(errors[:2], 5, with_more=True) == "e0; e1"


def test_call_logged_logs_and_swallows(caplog):
    def boom(x):
        raise RuntimeError(x)

    log = logging.getLogger("neondeck.test_values")
    with caplog.at_level(logging.ERROR):
        assert call_logged(boom, "kaputt", what="Aufruf %s ging schief", what_args=("A",),
                           logger=log) is False
    assert "Aufruf A ging schief" in caplog.text and "kaputt" in caplog.text
    assert call_logged(lambda: None) is True


def test_all_controls_order_and_counts():
    refs = all_controls()
    expected = ([ControlRef("touch", i) for i in range(12)]
                + [ControlRef("strip", i) for i in range(6)]
                + [ControlRef("knob", i) for i in range(6)]
                + [ControlRef("round", i) for i in range(8)]
                + [ControlRef("square", i) for i in range(12)]
                + [ControlRef("wheel", 0)])
    assert refs == expected
    assert CONTROL_COUNTS == {"touch": 12, "round": 8, "square": 12, "knob": 6, "strip": 6,
                              "wheel": 1}
