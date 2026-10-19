import pytest

from neondeck.actions.macro_text import MacroSyntaxError, format, parse

SRC = """# Kommentar

hotkey ctrl+shift+t
text Hallo  Welt
wait 200
run firefox --private
open https://example.org
command htop
shell notify-send hi
key down shift
key up shift
"""

STEPS = [
    {"type": "hotkey", "keys": "KEY_LEFTCTRL+KEY_LEFTSHIFT+KEY_T"},
    {"type": "text", "text": "Hallo  Welt"},
    {"type": "sleep", "ms": 200},
    {"type": "run", "command": "firefox --private"},
    {"type": "open", "target": "https://example.org"},
    {"type": "command", "command": "htop", "terminal": True},
    {"type": "command", "command": "notify-send hi", "terminal": False},
    {"type": "hold_key", "keys": "KEY_LEFTSHIFT"},
    {"type": "hold_key", "keys": "KEY_LEFTSHIFT", "release": True},
]


def test_parse_all_kinds():
    assert parse(SRC) == STEPS


def test_roundtrip():
    assert parse(format(STEPS)) == STEPS
    assert parse(format(parse("hotkey strg+alt+entf\nhotkey super+e\nhotkey alt+F4\nhotkey KEY_PLAYPAUSE"))) == \
        parse("hotkey strg+alt+entf\nhotkey super+e\nhotkey alt+F4\nhotkey KEY_PLAYPAUSE")


def test_error_line_number():
    with pytest.raises(MacroSyntaxError) as e:
        parse("# x\n\nwait 10\nhotkey ctrl+bogus\n")
    assert e.value.line == 4
    for bad in ("wait abc", "frob", "run", "key sideways x", "hotkey"):
        with pytest.raises(MacroSyntaxError):
            parse(bad)


def test_shortforms_map_to_evdev():
    keys = lambda s: parse(f"hotkey {s}")[0]["keys"]  # noqa: E731 - kurze Hilfe im Test
    assert keys("ctrl+shift+t") == "KEY_LEFTCTRL+KEY_LEFTSHIFT+KEY_T"
    assert keys("super+e") == "KEY_LEFTMETA+KEY_E"
    assert keys("alt+f4") == "KEY_LEFTALT+KEY_F4"
    assert keys("strg+y") == "KEY_LEFTCTRL+KEY_Z"  # German layout
    assert keys("ctrl+z") == "KEY_LEFTCTRL+KEY_Y"
    assert keys("altgr+7") == "KEY_RIGHTALT+KEY_7"
    assert keys("Umschalt+Entf") == "KEY_LEFTSHIFT+KEY_DELETE"
    assert format([{"type": "hotkey", "keys": "KEY_LEFTCTRL+KEY_Z"}]) == "hotkey ctrl+y\n"


def test_text_keeps_trailing_spaces():
    """F3: Liste <-> Text verliert keine Leerzeichen am Ende eines ``text``-Schritts."""
    steps = [{"type": "text", "text": "a "}, {"type": "text", "text": "  b  "}]
    assert parse(format(steps)) == steps
    assert parse("  text a \n") == [{"type": "text", "text": "a "}]
    assert parse("wait 100 \nhotkey ctrl+c \nrun firefox \nkey down shift ") == [
        {"type": "sleep", "ms": 100}, {"type": "hotkey", "keys": "KEY_LEFTCTRL+KEY_C"},
        {"type": "run", "command": "firefox"}, {"type": "hold_key", "keys": "KEY_LEFTSHIFT"}]
