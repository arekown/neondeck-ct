import pytest

from neondeck.device.layout import ControlRef, Display, control_for_button, touch_target


def test_layout_buttons():
    assert control_for_button(7) == ControlRef("round", 0)
    assert control_for_button(14) == ControlRef("round", 7)
    assert control_for_button(15) == ControlRef("square", 0)
    assert control_for_button(18) == ControlRef("square", 1)
    assert control_for_button(17) == ControlRef("square", 4)
    assert control_for_button(24) == ControlRef("square", 7)
    assert control_for_button(3) == ControlRef("knob", 2)


def test_unknown_button():
    with pytest.raises(KeyError):
        control_for_button(99)


def test_touch_targets():
    assert touch_target(103, 37) == ControlRef("touch", 0)
    assert touch_target(355, 57) == ControlRef("touch", 3)
    assert touch_target(370, 228) == ControlRef("touch", 11)
    assert touch_target(39, 131) == ControlRef("strip", 1)
    assert touch_target(449, 134) == ControlRef("strip", 4)


def test_displays():
    assert (Display.CENTER.id, Display.CENTER.width, Display.CENTER.height) == ("A", 360, 270)
    assert Display.WHEEL.big_endian is True
    assert Display.LEFT.big_endian is False


def test_paths(monkeypatch, tmp_path):
    from neondeck.core import paths
    monkeypatch.setenv("NEONDECK_HOME", str(tmp_path))
    assert paths.config_dir() == tmp_path / "config"
    assert paths.data_dir() == tmp_path / "share"
    assert paths.state_dir() == tmp_path / "state"
    monkeypatch.delenv("NEONDECK_HOME")
    assert paths.config_dir().name == "neondeck-ct"
    assert not tmp_path.joinpath("config").exists()
