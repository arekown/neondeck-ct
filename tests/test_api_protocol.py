"""JSON-API-Protokoll ohne Socket: Steuerelement-Namen, Zeilenpuffer, Ereignisse aus Dicts."""
import pytest

from neondeck.api import protocol
from neondeck.api.protocol import (
    MAX_LINE,
    LineBuffer,
    LineTooLong,
    event_from_dict,
    parse_ref,
)
from neondeck.device.layout import ControlRef
from neondeck.device.protocol import ButtonEvent, RotateEvent, TouchEvent, WheelTouchEvent


def test_parse_ref():
    assert parse_ref("touch:3") == ControlRef("touch", 3)
    assert parse_ref("round:1") == ControlRef("round", 1)
    assert parse_ref("square:5") == ControlRef("square", 5)
    assert parse_ref("knob:2") == ControlRef("knob", 2)
    assert parse_ref("strip:4") == ControlRef("strip", 4)
    assert parse_ref("wheel") == ControlRef("wheel", 0)
    assert parse_ref(" Touch:11 ") == ControlRef("touch", 11)
    for bad in ("touch:12", "round:8", "knob:6", "touch:-1", "touch", "foo:1", "touch:x",
                "wheel:1", "", None, 3):
        with pytest.raises(ValueError):
            parse_ref(bad)
    assert protocol.format_ref(ControlRef("wheel", 0)) == "wheel"
    assert protocol.format_ref(ControlRef("knob", 2)) == "knob:2"


def test_line_buffer_splits_and_limits():
    buf = LineBuffer()
    assert buf.feed(b'{"a":1}\n{"b"') == [b'{"a":1}']
    assert buf.feed(b':2}\n\n') == [b'{"b":2}', b""]
    big = LineBuffer(limit=10)
    assert big.feed(b"1234567890") == []
    with pytest.raises(LineTooLong):
        big.feed(b"1")
    with pytest.raises(LineTooLong):
        LineBuffer(limit=10).feed(b"12345678901\n")
    assert MAX_LINE == 16 * 1024 * 1024


def test_event_from_dict():
    assert event_from_dict({"type": "button", "code": 7, "pressed": True}) == ButtonEvent(7, True)
    assert event_from_dict({"type": "rotate", "code": 1, "delta": -1}) == RotateEvent(1, -1)
    assert event_from_dict({"type": "touch", "finger": 1, "x": 10, "y": 20, "down": True}) == \
        TouchEvent(1, 10, 20, True)
    assert event_from_dict({"type": "wheel_touch", "finger": 1, "x": 1, "y": 2,
                            "down": False}) == WheelTouchEvent(1, 1, 2, False)
    for bad in ({"type": "button", "code": 7}, {"type": "button", "code": "7", "pressed": True},
                {"type": "button", "code": 7, "pressed": 1}, {"type": "nix"}, [],
                {"type": "rotate", "code": True, "delta": 1}):
        with pytest.raises(ValueError):
            event_from_dict(bad)


def test_error_reply_carries_code_and_text():
    from neondeck.api.protocol import ApiError, decode, encode, error_reply, reply_error

    wire = decode(encode(error_reply(7, ApiError("profile.not_found", "Profil {id!r} gibt es nicht",
                                                 {"id": "x"}))))
    assert wire["error"] == "Profil 'x' gibt es nicht"  # aeltere Clients lesen nur den Text
    assert wire["message"] == "Profil {id!r} gibt es nicht"  # Quelltext fuer tr() im Client
    err = ApiError.from_error(reply_error(wire))
    assert (err.code, str(err), err.params) == ("profile.not_found", wire["error"], {"id": "x"})
