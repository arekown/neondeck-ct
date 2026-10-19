from datetime import datetime
from pathlib import Path

import numpy as np
from PIL import Image

from neondeck.render import icons, images
from neondeck.render.images import TileSpec


def test_rgb565_little_and_big():
    red = Image.new("RGB", (1, 1), (255, 0, 0))
    assert images.to_rgb565(red) == b"\x00\xf8"
    assert images.to_rgb565(red, big_endian=True) == b"\xf8\x00"
    green = Image.new("RGB", (1, 1), (0, 255, 0))
    assert images.to_rgb565(green) == b"\xe0\x07"


def test_tile_size_and_bg():
    img = images.render_tile(TileSpec(bg="#ff0000"))
    assert img.size == (90, 90)
    assert img.convert("RGB").getpixel((2, 2)) == (255, 0, 0)


def test_tile_text_fits():
    img = images.render_tile(TileSpec(text="Systemeinstellungen öffnen")).convert("RGB")
    w, h = img.size
    bg = (0, 0, 0)
    edge = [(x, y) for x in range(w) for y in range(h) if x < 2 or y < 2 or x >= w - 2 or y >= h - 2]
    assert all(img.getpixel(p) == bg for p in edge)
    # es wurde wirklich Text gezeichnet
    assert any(img.getpixel((x, y)) != bg for x in range(w) for y in range(h))


def test_tile_flash_border():
    img = images.render_tile(TileSpec(flash="#ff0000")).convert("RGB")
    assert img.getpixel((2, 45)) == (255, 0, 0)
    assert img.getpixel((45, 45)) == (0, 0, 0)


def test_compose_center_positions():
    red = images.render_tile(TileSpec(bg="#ff0000"))
    tiles = [None] * 12
    tiles[5] = red
    img = images.compose_center(tiles, 0, 1)
    assert img.size == (360, 270)
    img = img.convert("RGB")
    assert img.getpixel((90 + 45, 90 + 45)) == (255, 0, 0)
    assert img.getpixel((45, 45)) == (0, 0, 0)


def test_compose_center_page_dots():
    img = images.compose_center([None] * 12, 0, 3).convert("RGB")
    assert any(img.getpixel((x, 266)) != (0, 0, 0) for x in range(360))
    single = images.compose_center([None] * 12, 0, 1).convert("RGB")
    assert all(single.getpixel((x, 266)) == (0, 0, 0) for x in range(360))


def test_render_strip_size():
    img = images.render_strip([("Lautstärke", "50%"), ("Hell", None), ("", None)])
    assert img.size == (60, 270)


def test_svg_icon_renders(tmp_path: Path):
    svg = tmp_path / "c.svg"
    svg.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24">'
        '<circle cx="12" cy="12" r="10" fill="#E2E2E2"/></svg>'
    )
    icon = icons.load_icon("svg:x", 48, resolver=lambda ref: svg)
    assert icon is not None and icon.size == (48, 48)
    r, g, b, a = icon.convert("RGBA").getpixel((24, 24))
    assert a > 200 and r > 200


def test_load_icon_png_file_and_missing(tmp_path: Path):
    p = tmp_path / "a.png"
    Image.new("RGB", (20, 10), (255, 0, 0)).save(p)
    icon = icons.load_icon(f"file:{p}", 40)
    assert icon is not None and icon.size == (40, 40)
    assert icons.load_icon("lib:nope", 40) is None
    assert icons.load_icon("file:/does/not/exist.png", 40) is None


def test_wheel_clock():
    img = images.render_wheel("clock", now=datetime(2026, 10, 17, 3, 0)).convert("RGB")
    assert img.size == (240, 240)
    r, g, b = img.getpixel((120 + 40, 120))
    assert min(r, g, b) > 180


def test_wheel_label_and_blank():
    assert images.render_wheel("blank").convert("RGB").getbbox() is None
    assert images.render_wheel("label", "Hallo").convert("RGB").getbbox() is not None


def test_tile_icon_and_two_line_text_do_not_overlap():
    icon = Image.new("RGBA", (90, 90), (255, 0, 0, 255))  # deckend rot
    img = images.render_tile(images.TileSpec("#000000", icon, "Windows Explorer", "#ffffff"))
    a = np.asarray(img.convert("RGB")).astype(int)
    red = (a[..., 0] > 200) & (a[..., 1] < 60) & (a[..., 2] < 60)
    white = (a[..., 0] > 128) & (a[..., 1] > 128) & (a[..., 2] > 128)
    icon_rows = np.flatnonzero(red.any(axis=1))
    text_rows = np.flatnonzero(white.any(axis=1))
    assert icon_rows.size and text_rows.size
    assert icon_rows.max() < text_rows.min()
    assert text_rows.max() - text_rows.min() > 20  # wirklich zwei Zeilen


# --- P9: Leisten-Balken, Rad-Bogen und Rad-Bild ------------------------------------------

def _cyan(px):
    r, g, b = px
    return b > 200 and g > 150 and r < 160  # Wertfarbe #7fd0ff


def test_render_strip_bar():
    img = images.render_strip([("Laut", None), ("Hell", "50 %"), ("", None)],
                              bars=[25.0, None, None]).convert("RGB")
    top, bottom = images.STRIP_BAR_Y, images.STRIP_BAR_Y + images.STRIP_BAR_H - 1
    mid = (top + bottom) // 2
    left, right = images.STRIP_BAR_X0, images.STRIP_BAR_X1
    filled = left + (right - left) * 25 // 100
    assert _cyan(img.getpixel((left + 1, mid))) and _cyan(img.getpixel((filled - 1, mid)))
    assert not _cyan(img.getpixel((filled + 2, mid)))       # Rest: nur die Spur
    assert img.getpixel((filled + 2, mid)) != (0, 0, 0)
    # Abschnitt 2 ohne Balken zeigt den Wert als Text wie bisher
    plain = images.render_strip([("Laut", None), ("Hell", "50 %"), ("", None)]).convert("RGB")
    assert img.crop((0, 90, 60, 180)).tobytes() == plain.crop((0, 90, 60, 180)).tobytes()


def test_render_strip_bar_bounds():
    full = images.render_strip([("", None)], bars=[100.0]).convert("RGB")
    empty = images.render_strip([("", None)], bars=[0.0]).convert("RGB")
    mid = images.STRIP_BAR_Y + images.STRIP_BAR_H // 2
    assert _cyan(full.getpixel((images.STRIP_BAR_X1 - 1, mid)))
    assert not any(_cyan(empty.getpixel((x, mid))) for x in range(60))


def test_wheel_arc():
    empty = images.render_wheel("arc").convert("RGB")
    half = images.render_wheel("arc", value=50.0).convert("RGB")
    assert empty.getbbox() is not None                     # Spur ist immer zu sehen
    # 50 %: Bogen von unten links ueber links bis oben (Mitte = 12 Uhr)
    r = images.WHEEL_ARC_R - images.WHEEL_ARC_W // 2
    assert _cyan(half.getpixel((120 - r, 120)))              # 9 Uhr: gefuellt
    assert not _cyan(half.getpixel((120 + r, 120)))          # 3 Uhr: noch nicht
    assert not _cyan(empty.getpixel((120 - r, 120)))
    assert half.getpixel((120, 120)) != (0, 0, 0) or half.crop((80, 95, 160, 145)).getbbox()


def test_wheel_image():
    tile = Image.new("RGB", (240, 240), (10, 200, 30))
    img = images.render_wheel("image", image=tile).convert("RGB")
    assert img.size == (240, 240) and img.getpixel((120, 120)) == (10, 200, 30)
    assert images.render_wheel("image").convert("RGB").getbbox() is None  # kein Bild: schwarz


def test_tile_text_scales_with_size():
    small = images.render_tile(TileSpec(text="Rad"), 90)
    big = images.render_tile(TileSpec(text="Rad"), 240)
    sb, bb = small.convert("L").getbbox(), big.convert("L").getbbox()
    assert (bb[3] - bb[1]) > 2 * (sb[3] - sb[1])


def test_wheel_tile_fits_round_display():
    img = images.wheel_tile(TileSpec("#203040", None, "Lautstärke Lautstärke")).convert("RGB")
    assert img.size == (240, 240) and img.getpixel((2, 2)) == (0x20, 0x30, 0x40)
    a = np.asarray(img).astype(int)
    ys, xs = np.nonzero((a != (0x20, 0x30, 0x40)).any(axis=-1))  # Text-Pixel
    assert len(xs) and (np.hypot(xs - 119.5, ys - 119.5) < 118).all()  # im Kreis
