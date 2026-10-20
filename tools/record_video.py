"""Video der Geraete-Animation ohne Geraet: Cockpit-Look (wach) und Bildschirmschoner.

/usr/bin/python3 tools/record_video.py --out <Ordner> [--seconds 20] [--gif <Ordner>]

Die Engine laeuft wie im Dienst mit dem aktiven Profil und den Einstellungen; statt ans Geraet
gehen die Bilder (RGB565, wie gesendet) in eine Zeichnung des CT mit den Massen der
Geraeteansicht im Editor. Die Uhr der Engine springt ueber die Pausen, laeuft aber waehrend des
Zeichnens echt mit – der Takt ist also derselbe wie am Geraet (Look 6 Bilder/s, Schoner je nach
Zeichenzeit). Ergebnis: ``cockpit-wach.mp4`` und ``bildschirmschoner.mp4`` (H.264), mit
``--gif`` zusaetzlich kleine GIFs fuer die README.
"""
import argparse
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from neondeck.core import paths
from neondeck.core.settings import Settings
from neondeck.core.sysload import SystemLoad
from neondeck.device.layout import ROUND_FIRST, Display
from neondeck.editor.widgets import device_geometry as geo
from neondeck.engine import Engine
from neondeck.engine.ports import EngineOptions, EnginePorts
from neondeck.profile.store import ProfileStore
from neondeck.service.settings_effects import look_name, saver_name, saver_options

SCALE = 2                 # Geraete-Pixel -> Video-Pixel
MARGIN = 24               # Rand um das Geraet (Geraete-Einheiten)
FPS = 30                  # Bildrate des Videos (das Geraet zeigt weniger, Bilder werden gehalten)
# USB zum CT: Schoner-Bild (480 × 270 + 240 × 240 RGB565) am Geraet 41 ms (Log), davon 6,4 ms
# Zeichnen -> rund 10,8 MB/s; so viel Zeit kostet jedes gesendete Bild auch im Video
DEVICE_BYTES_PER_S = 10.8e6
GIF_FPS, GIF_WIDTH, GIF_SECONDS = 12, 640, 10
BACKDROP, BODY, EDGE = (8, 9, 12), (18, 20, 26), (44, 48, 58)
KEY, KEY_EDGE, KNOB, KNOB_EDGE = (24, 27, 34), (52, 57, 70), (30, 33, 41), (64, 70, 84)


class SkipClock:
    """Engine-Uhr: laeuft echt, ``skip`` springt ueber eine Pause, ohne zu warten."""

    def __init__(self) -> None:
        self._offset = 0.0
        self._mono0 = time.perf_counter()
        self._wall0 = time.time()

    def mono(self) -> float:
        return time.perf_counter() - self._mono0 + self._offset

    def wall(self) -> float:
        return self._wall0 + self.mono()

    def skip(self, seconds: float) -> None:
        self._offset += seconds


class NullExecutor:
    """Keine Aktionen (es gibt keine Eingaben)."""

    def __init__(self, *_) -> None:
        pass

    def submit(self, *_, **__) -> None:
        pass

    def shutdown(self) -> None:
        pass


def from_rgb565(display: Display, data: bytes) -> Image.Image:
    v = np.frombuffer(data, dtype=">u2" if display.big_endian else "<u2").reshape(
        display.height, display.width).astype(np.uint16)
    rgb = np.stack([(v >> 8) & 0xF8, (v >> 3) & 0xFC, (v << 3) & 0xF8], axis=-1)
    return Image.fromarray(rgb.astype(np.uint8), "RGB")


def _box(rect, pad: float = 0) -> tuple[int, int, int, int]:
    """QRectF in Geraete-Einheiten -> Pixelrechteck im Video."""
    return (round((rect.x() - pad + MARGIN) * SCALE), round((rect.y() - pad + MARGIN) * SCALE),
            round((rect.right() + pad + MARGIN) * SCALE), round((rect.bottom() + pad + MARGIN) * SCALE))


class DeviceCanvas:
    """Zeichnung des CT: festes Gehaeuse, darauf je Bild Displays und LED-Ringe."""

    def __init__(self) -> None:
        w, h = (geo.WIDTH + 2 * MARGIN) * SCALE, (geo.HEIGHT + 2 * MARGIN) * SCALE
        self.size = (w + w % 2, h + h % 2)  # H.264: gerade Masse
        self._base = self._body()
        self._wheel_mask = Image.new("L", (geo.WHEEL_SIZE * SCALE,) * 2, 0)
        ImageDraw.Draw(self._wheel_mask).ellipse((0, 0, *self._wheel_mask.size), fill=255)
        self._glow: dict[tuple, tuple[Image.Image, Image.Image]] = {}

    def _body(self) -> Image.Image:
        img = Image.new("RGB", self.size, BACKDROP)
        d = ImageDraw.Draw(img)
        body = (MARGIN * SCALE, MARGIN * SCALE, (geo.WIDTH + MARGIN) * SCALE,
                (geo.HEIGHT + MARGIN) * SCALE)
        d.rounded_rectangle(body, geo.BODY_RADIUS * SCALE, fill=BODY, outline=EDGE, width=SCALE)
        d.rectangle(_box(geo.SCREEN, 4), fill=(0, 0, 0))
        for i in range(6):
            r = _box(geo.knob_rect(i))
            d.ellipse(r, fill=KNOB, outline=KNOB_EDGE, width=SCALE)
            cx = (r[0] + r[2]) // 2
            d.line((cx, r[1] + 5 * SCALE, cx, r[1] + 16 * SCALE), fill=KNOB_EDGE, width=2 * SCALE)
        for i in range(12):
            d.rounded_rectangle(_box(geo.square_rect(i)), 8 * SCALE, fill=KEY, outline=KEY_EDGE,
                                width=SCALE)
        d.ellipse(_box(geo.WHEEL, geo.WHEEL_RIM), fill=KNOB, outline=KNOB_EDGE, width=SCALE)
        return img

    def _leds(self, leds: dict[int, tuple]) -> tuple[Image.Image, Image.Image]:
        """Gluehen und runde Tasten mit LED-Ring (zwischengespeichert je Farbsatz)."""
        key = tuple(sorted(leds.items()))
        if key not in self._glow:
            glow = Image.new("RGB", self.size, (0, 0, 0))
            gd = ImageDraw.Draw(glow)
            for i in range(8):
                color = leds.get(ROUND_FIRST + i, (0, 0, 0))[:3]
                gd.ellipse(_box(geo.round_rect(i), 3), outline=color, width=4 * SCALE)
            glow = glow.filter(ImageFilter.GaussianBlur(6 * SCALE))
            layer = Image.new("RGB", self.size, (0, 0, 0))
            ld = ImageDraw.Draw(layer)
            for i in range(8):
                color = leds.get(ROUND_FIRST + i, (0, 0, 0))[:3]
                r = _box(geo.round_rect(i))
                ld.ellipse(r, fill=KEY, outline=color, width=3 * SCALE)
            self._glow[key] = (glow, layer)
        return self._glow[key]

    def render(self, screens: dict[Display, Image.Image], leds: dict[int, tuple]) -> Image.Image:
        glow, keys = self._leds(leds)
        img = Image.fromarray(np.minimum(np.asarray(self._base, np.uint16)
                                         + np.asarray(glow, np.uint16), 255).astype(np.uint8))
        mask = Image.new("L", self.size, 0)
        md = ImageDraw.Draw(mask)
        for i in range(8):
            md.ellipse(_box(geo.round_rect(i)), fill=255)
        img.paste(keys, (0, 0), mask)
        x0, y0 = _box(geo.SCREEN)[:2]
        for display, dx in ((Display.LEFT, 0), (Display.CENTER, geo.STRIP_W),
                            (Display.RIGHT, geo.STRIP_W + Display.CENTER.width)):
            if display in screens:
                img.paste(self._scaled(screens[display]), (x0 + dx * SCALE, y0))
        if Display.WHEEL in screens:
            img.paste(self._scaled(screens[Display.WHEEL]), _box(geo.WHEEL)[:2], self._wheel_mask)
        return img

    @staticmethod
    def _scaled(img: Image.Image) -> Image.Image:
        return img.resize((img.width * SCALE, img.height * SCALE), Image.Resampling.NEAREST)


class Recorder:
    """Engine mit Aufzeichnung statt Geraet; ``run`` liefert (Zeit, Bild) je gezeichnetem Takt."""

    def __init__(self, canvas: DeviceCanvas) -> None:
        self.clock = SkipClock()
        self.canvas = canvas
        self.screens: dict[Display, Image.Image] = {}
        self.leds: dict[int, tuple] = {}
        settings = Settings.load()
        profile = ProfileStore(paths.config_dir() / "profiles").load(settings.active_profile)
        ports = EnginePorts(self._draw, self.leds.update, NullExecutor, post=lambda fn: fn(),
                            clock=self.clock.wall, monotonic=self.clock.mono,
                            system_load=SystemLoad(monotonic=self.clock.mono))
        self.saver = saver_name(settings)
        self.engine = Engine(profile, ports, options=EngineOptions(
            views=settings.last_pages, saver_name=self.saver,
            saver_options=saver_options(settings), device_look=look_name(settings)))
        self.engine.device_connected = True

    def _draw(self, display: Display, data: bytes) -> None:
        t = time.perf_counter()
        self.screens[display] = from_rgb565(display, data)
        # Umwandeln zaehlt nicht mit, die Uebertragung zum Geraet schon
        self.clock.skip(len(data) / DEVICE_BYTES_PER_S - (time.perf_counter() - t))

    def run(self, step, seconds: float) -> list[tuple[float, Image.Image]]:
        """``step`` zeichnet ein Bild und liefert die Pause bis zum naechsten."""
        frames, start = [], self.clock.mono()
        while (now := self.clock.mono()) - start < seconds:
            delay = step()
            if delay is None:
                raise RuntimeError("Animation laeuft nicht (Look nicht animiert?)")
            t = time.perf_counter()
            frames.append((now - start, self.canvas.render(self.screens, self.leds)))
            self.clock.skip(delay - (time.perf_counter() - t))  # Videobild zaehlt nicht mit
        return frames

    def awake(self, seconds: float) -> list[tuple[float, Image.Image]]:
        self.engine.redraw_all()
        return self.run(self.engine.look_frame, seconds)

    def screensaver(self, seconds: float) -> list[tuple[float, Image.Image]]:
        if not self.engine.start_saver(self.saver):
            raise RuntimeError("Bildschirmschoner startet nicht")
        return self.run(self.engine.saver_frame, seconds)


def write_mp4(frames: list[tuple[float, Image.Image]], seconds: float, out: Path) -> None:
    """Bilder zu festen ``FPS`` halten, bis das naechste gezeichnet ist."""
    w, h = frames[0][1].size
    cmd = ["ffmpeg", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
           "-s", f"{w}x{h}", "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "slow",
           "-crf", "18", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(out)]
    with subprocess.Popen(cmd, stdin=subprocess.PIPE) as ff:
        i = 0
        for n in range(round(seconds * FPS)):
            while i + 1 < len(frames) and frames[i + 1][0] <= n / FPS:
                i += 1
            ff.stdin.write(frames[i][1].tobytes())
        ff.stdin.close()
    if ff.returncode:
        raise RuntimeError(f"ffmpeg fehlgeschlagen ({ff.returncode})")


def write_gif(mp4: Path, out: Path) -> None:
    graph = (f"fps={GIF_FPS},scale={GIF_WIDTH}:-1:flags=lanczos,split[a][b];"
             "[a]palettegen=stats_mode=diff[p];[b][p]paletteuse=dither=bayer:bayer_scale=4")
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-t", str(GIF_SECONDS), "-i", str(mp4),
                    "-filter_complex", graph, str(out)], check=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, required=True, help="Ordner fuer die MP4-Dateien")
    ap.add_argument("--seconds", type=float, default=20, help="Laenge je Video")
    ap.add_argument("--gif", type=Path, help="Ordner fuer kleine GIFs (README)")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    rec = Recorder(DeviceCanvas())
    try:
        clips = {"cockpit-wach": rec.awake(args.seconds),
                 "bildschirmschoner": rec.screensaver(args.seconds)}
    finally:
        rec.engine.shutdown()
    for name, frames in clips.items():
        mp4 = args.out / f"{name}.mp4"
        write_mp4(frames, args.seconds, mp4)
        print(f"{mp4}: {len(frames)} Bilder in {args.seconds:g} s "
              f"({len(frames) / args.seconds:.1f} Bilder/s)")
        if args.gif:
            args.gif.mkdir(parents=True, exist_ok=True)
            write_gif(mp4, args.gif / f"{name}.gif")
    return 0


if __name__ == "__main__":
    sys.exit(main())
