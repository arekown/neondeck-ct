"""Tastenbilder aus ``ActionIcons/*.ict`` und ``ActionImages/*.png``."""
from __future__ import annotations

import base64
import binascii
import hashlib
import re
from pathlib import Path

from ....core import assets
from ....core.fileio import read_json
from ....core.i18n import tr
from ...model import ButtonImage
from .context import Context

_ATTR_COLOR = re.compile(r'\b(fill|stroke)="(?!none")[^"]*"')
_STYLE_COLOR = re.compile(r"\b(fill|stroke)\s*:\s*(?!none\b)[^;\"'}<]+")


def _argb(value, default: str) -> str:
    if isinstance(value, int):
        return f"#{value & 0xFFFFFF:06x}"
    return default


def _index(folder: Path | None, suffix: str) -> dict[str, Path]:
    if folder is None or not Path(folder).is_dir():
        return {}
    return {p.name.lower(): p for p in Path(folder).iterdir()
            if p.is_file() and p.suffix.lower() == suffix}


def _recolor_svg(svg: str, color: str) -> str:
    svg = _ATTR_COLOR.sub(lambda m: f'{m.group(1)}="{color}"', svg)
    return _STYLE_COLOR.sub(lambda m: f"{m.group(1)}:{color}", svg)


class IconSink:
    """Schreibt eingebettete Symbole als Dateien (Name = Pruefsumme) und liefert den Verweis."""

    def __init__(self, out_dir: Path):
        self.out_dir = out_dir

    def write(self, raw: bytes, suffix: str) -> str:
        self.out_dir.mkdir(parents=True, exist_ok=True)
        path = self.out_dir / f"{hashlib.sha1(raw).hexdigest()}{suffix}"
        if not path.exists():
            path.write_bytes(raw)
        return f"file:{path.resolve()}"


class IconReader:
    """Liest Symbole und Beschriftungen zu Aktionszeichenketten."""

    def __init__(self, ctx: Context, ict_dir: Path | None, images_dir: Path | None,
                 sink: IconSink | None):
        self.ctx = ctx
        self.sink = sink
        if images_dir is None and ict_dir is not None:
            images_dir = Path(ict_dir).parent / "ActionImages"
        self.icts = _index(ict_dir, ".ict")
        self.pngs = _index(images_dir, ".png")

    def _load_ict(self, s: str, where: str) -> dict | None:
        path = self.icts.get(s.lower() + ".ict")
        if path is None:
            return None
        try:
            d = read_json(path)
            return d if isinstance(d, dict) else None
        except (OSError, ValueError) as e:
            self.ctx.note(where, tr("Symboldatei {name} unlesbar ({e})", name=path.name, e=e))
            return None

    def _embedded(self, item: dict) -> str | None:
        """Eingebettetes Bild (PNG oder SVG, base64) als Datei; ohne Ziel/Bild: None."""
        data = item.get("image")
        if not data or self.sink is None:
            return None
        try:
            raw = base64.b64decode(data, validate=True)
        except (binascii.Error, ValueError):
            raw = b""
        if raw.startswith(b"\x89PNG"):
            return self.sink.write(raw, ".png")
        text = raw.decode("utf-8", errors="replace")
        if "<svg" not in text[:1024]:
            return None
        color = item.get("imageColor")
        if isinstance(color, int):
            text = _recolor_svg(text, _argb(color, "#ffffff"))
        return self.sink.write(text.encode("utf-8"), ".svg")

    def _icon_from_item(self, item: dict) -> str | None:
        embedded = self._embedded(item)
        if embedded is not None:
            return embedded
        file_name = item.get("imageFileName")
        if file_name:
            ref = f"svg:actionicons/{file_name}"
            if assets.resolve(ref) is not None:
                return ref
        return None

    def image(self, s: str, where: str) -> ButtonImage:
        img = ButtonImage()
        ict = self._load_ict(s, where)
        png = self.pngs.get(s.lower() + ".png")
        if ict is not None:
            img.bg = _argb(ict.get("backgroundColor"), img.bg)
            items = [i for i in ict.get("items") or []
                     if isinstance(i, dict) and i.get("isVisible")]
            text = next((i for i in items if i.get("itemType") == "Text"), None)
            if text is not None:
                img.text = text.get("text") or ""
                img.text_color = _argb(text.get("textColor"), img.text_color)
            pic = next((i for i in items if i.get("itemType") == "Image"), None)
            if pic is not None and png is None:
                img.icon = self._icon_from_item(pic)
        if png is not None:
            img.icon = f"file:{png.resolve()}"
        if ict is None and png is None:
            img.text = self.ctx.display_name(s)
        return img

    def label(self, s: str | None) -> str:
        if not s:
            return ""
        d = self._load_ict(s, tr("Beschriftung")) or {}
        for i in d.get("items") or []:
            if isinstance(i, dict) and i.get("itemType") == "Text" and i.get("text"):
                return i["text"]
        return self.ctx.display_name(s)
