"""Beispielprofile fuer Tests."""
from __future__ import annotations

from pathlib import Path

from PIL import Image

from neondeck.profile.model import Assignment, ButtonImage, Profile, TouchPage, empty_profile


def profile_with_image(tmp_path) -> tuple[Profile, Path]:
    img = tmp_path / "bilder" / "logo.png"
    img.parent.mkdir()
    Image.new("RGB", (8, 8), (255, 0, 0)).save(img)
    p = empty_profile("teilen", "Zum Teilen")
    page = p.workspaces[0].touch_pages[0]
    page.buttons[0] = Assignment({"type": "run", "command": "kate"},
                                 ButtonImage(icon=f"file:{img}", text="Kate"))
    page.buttons[1] = Assignment({"type": "mute_toggle"},
                                 ButtonImage(icon="svg:icons/MediaVolume.svg"))
    p.workspaces[0].touch_pages.append(TouchPage("p2", "Zwei"))
    p.workspaces[0].touch_pages[1].buttons[3] = Assignment(
        {"type": "run", "command": "x"}, ButtonImage(icon=f"file:{img}"))  # dasselbe Bild
    return p, img
