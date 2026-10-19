"""Tastenbild: Vorlagen, Ausrichtung, feste Schriftgroesse, Schriftfamilien, Einfaerben."""
import numpy as np
from PIL import Image

from neondeck.render import fonts, images
from neondeck.render.images import TileSpec


def _text_rows(img: Image.Image) -> np.ndarray:
    """Zeilen mit hellen (Text-)Pixeln."""
    a = np.asarray(img.convert("L"))
    return np.nonzero((a > 128).any(axis=1))[0]


def test_image_layouts_render():
    icon = Image.new("RGBA", (64, 64), (0, 0, 255, 255))
    small = images.render_tile(TileSpec(icon=icon, text="OBS", layout="icon_text"))
    big = images.render_tile(TileSpec(icon=icon, text="OBS", layout="big_text"))
    # icon_text: Symbol (blau) da, Text klein; big_text: kein Symbol, Text deutlich groesser
    blue = lambda img: ((np.asarray(img)[..., 2] > 200)  # noqa: E731 - kurze Hilfe im Test
                        & (np.asarray(img)[..., 0] < 50)).any()
    assert blue(small) and not blue(big)
    rows_small = _text_rows(small.crop((0, 60, 90, 90)))
    rows_big = _text_rows(big)
    assert rows_big.size > 2 * rows_small.size
    only_icon = images.render_tile(TileSpec(icon=icon, text="OBS", layout="icon"))
    assert _text_rows(only_icon).size == 0  # kein (weisser) Text
    # Ausrichtung: oben -> alle Textpixel im oberen Drittel, unten -> im unteren
    top = images.render_tile(TileSpec(text="Hallo", layout="text", align_v="top"))
    bottom = images.render_tile(TileSpec(text="Hallo", layout="text", align_v="bottom"))
    assert _text_rows(top).max() < 30
    assert _text_rows(bottom).min() > 60
    left = np.asarray(images.render_tile(TileSpec(text="Hi", layout="text", align_h="left")))
    right = np.asarray(images.render_tile(TileSpec(text="Hi", layout="text", align_h="right")))
    cols = lambda a: np.nonzero((a.max(axis=2) > 128).any(axis=0))[0]  # noqa: E731 - kurze Hilfe im Test
    assert cols(left).max() < 45 < cols(right).min()


def test_fixed_font_size_and_families():
    auto = images.render_tile(TileSpec(text="A", layout="text"))
    fixed = images.render_tile(TileSpec(text="A", layout="text", font_size=40))
    assert _text_rows(fixed).size > _text_rows(auto).size
    paths = set()
    for family in fonts.FAMILIES:
        f = fonts.font(20, False, family)
        paths.add(f.path)
        assert f.size == 20
    assert len(paths) == len(fonts.FAMILIES)  # jede Familie aus ihrer eigenen Datei
    assert fonts.font(20, False, "Gibt es nicht").path == fonts.font(20).path  # Noto Sans
    a = np.asarray(images.render_tile(TileSpec(text="Wg", layout="text", font="Orbitron")))
    b = np.asarray(images.render_tile(TileSpec(text="Wg", layout="text")))
    assert (a != b).any()


def test_icon_tint():
    icon = Image.new("RGBA", (40, 40), (0, 0, 0, 0))
    icon.paste((255, 255, 255, 255), (10, 10, 30, 30))
    plain = np.asarray(images.render_tile(TileSpec(bg="#000000", icon=icon)))
    tinted = np.asarray(images.render_tile(TileSpec(bg="#000000", icon=icon,
                                                    icon_color="#ff0000")))
    assert (plain[45, 45] == (255, 255, 255)).all()
    r, g, b = tinted[45, 45]
    assert r > 240 and g < 15 and b < 15
    assert (tinted[2, 2] == (0, 0, 0)).all()  # Hintergrund bleibt
