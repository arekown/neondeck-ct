# Neondeck CT

**English** · [Deutsch](README.de.md)

Software for the Loupedeck CT on Linux (KDE Plasma 6, Wayland), written in Python/Qt (PySide6).
The device is driven directly over its serial interface. No account, no cloud, no telemetry, no
updates from the network. Only the "HTTP request" action uses the network.

> Not affiliated with Logitech/Loupedeck. Loupedeck is a trademark of Logitech.

> **Vibecoded:** This project was built with AI assistance ("vibecoded"). The code was written by
> an AI, reviewed and refactored according to best practice, and is covered by tests.

Further documents (German): [Actions](docs/aktionen.md), [Command line and JSON API](docs/cli.md).

## Requirements

- Loupedeck CT (USB IDs 2ec2:0003 or 2ec2:0007), KDE Plasma 6 on Wayland.
- System packages: `python3-pyside6`, `python3-pyserial`, `python3-pillow`, `python3-numpy`,
  `python3-evdev`. Recommended: `wl-clipboard` (text input by pasting, otherwise it is typed).
  Fedora: `sudo dnf install python3-pyside6 python3-pyserial python3-pillow python3-numpy python3-evdev wl-clipboard`
- Depending on the action: `pactl` and `wpctl` (audio, PipeWire), `qdbus`, `ddcutil` (monitor brightness), `konsole`, `spectacle`.
- Access to `/dev/ttyACM*` and `/dev/uinput` (see Troubleshooting).

## Installation

```
git clone https://github.com/arekown/neondeck-ct.git
cd neondeck-ct
tools/install.sh
```

The script runs without sudo: it creates `.venv` (with system packages), the launcher
`~/.local/bin/neondeck-ct` and the menu entry `~/.local/share/applications/neondeck-ct.desktop`.

### Importing graphics (optional)

The original Loupedeck graphics (icon library, default images) are **not** included and are not
in the repository. If you want to use them, you can optionally import them from your own Windows
installer of the Loupedeck software. Unpack it (folders `assets-unpacked` and
`app/…/Plugins/@Generic`) and run:

```
/usr/bin/python3 tools/import_assets.py --source <path to the unpacked Windows installer>
```

The files are copied to `~/.local/share/neondeck-ct/assets` (only what changed).
Without the import the service reports "Graphics missing" (diagnostics, tray message); keys can
still be assigned your own images or text. You can also use your own images, e.g. CC0 icon and
sound packs, through the key image editor (Choose file). These packs are not part of the
distribution.

## Start, autostart, tray

- Start: `neondeck-ct` (or the menu entry). The service runs in the tray (device, actions,
  window and lock watching). Only one instance ever runs.
- Tray menu: Open settings, Brightness (0–10), Display sleep (off or n min),
  "Start at login" (autostart, writes `~/.config/autostart/neondeck-ct.desktop`), Quit.
- The editor is a separate process (`neondeck-ct --config`); if it crashes, the device keeps working.

## The editor

Themes: **Cyberpunk Cockpit** (default, optionally with scanlines), **Neutral Dark**, **System (KDE)**,
switchable in the menu, live.

- **Device view** with all touch fields, round/square buttons, knobs, bars and the wheel.
  Below it the inspector, on the right the action library (search, drag onto a key).
  See [Actions](docs/aktionen.md).
- **Editing**: click selects, Ctrl-click multi-selects, Del deletes. Dragging moves, with Ctrl it
  copies. Ctrl+C/X/V/D = copy, cut, paste, duplicate (also whole pages, between workspaces).
  Undo Ctrl+Z, redo Ctrl+Shift+Z or Ctrl+Y (100 steps). Assignments go to the clipboard as JSON.
- **Key image editor**: layout (icon only, icon + text, plain text, large text), font
  (Noto Sans, Orbitron, Rajdhani, Share Tech Mono, Inter), size (auto/fixed), alignment,
  text and icon colour, icon tint.
- **States**: 2–8 per key, each with its own image and optionally its own action. Source: manual,
  muted (default audio), media (MPRIS), "app running" or external (`ctl state`). Kept across page changes.
- **Tap, double-tap, hold** per key (default 300 ms and 500 ms, adjustable in the settings:
  double-tap 100–1000 ms, hold 200–3000 ms).
- **Folders**: a touch key opens a folder page, back tile added automatically, optionally "Back after action".
  **Sticky tiles** apply to all pages of a workspace. LED colour per workspace.
- **Arrange …** (header, menu "Profile"): sort workspaces and pages by dragging; the round buttons
  that switch workspaces follow the order. Page tabs can also be moved directly.
- **Knobs and wheel**: rotation as one action or left/right separately, reverse direction,
  step factor 1–10, stack (several layers, pressing switches), bar display (name, name + value, bar).
  "Tap on the bar" (`tap` per knob) triggers its own action; if empty, tapping acts like pressing.
- **Bars** (header "Bars", per workspace `strip_left`/`strip_right`): `knobs` shows the knobs,
  `system` four live bars – CPU and RAM on top, GPU 1 and GPU 2 below (`nvidia-smi` in the
  background every 2 s; without a GPU "–"). Sampling only runs while a bar shows it.
  Wheel: clock, text, value arc, image; tapping the centre triggers its own action.
- **Dynamic Mode** (on by default): the profile follows the active window. For this the service
  loads a KWin script (`data/kwin/neondeck-ct.js`, D-Bus `io.github.arekown.NeondeckCT`); the
  mapping is the "App" field of the profile (chosen from installed programs). A manual profile
  switch pauses the automation until you switch to another app; "holding" profiles stay active;
  otherwise it falls back to the default profile. Can be switched off globally or per profile.
- **Simulate**: clicking and turning on the device picture triggers real events through the
  service (even without a device). "Test" runs the shown, not yet saved action.
- **Diagnostics page**: session (Wayland/KDE), device found, access to `/dev/ttyACM*` and
  `/dev/uinput`, `wl-copy`, KWin script, D-Bus service, firmware, graphics, with green/red and a
  repair command to copy. The editor never runs sudo itself.
- **First-time setup** on the first editor start: diagnostics, tick templates (several possible), choose a theme.
- **Insert template …** (button in the header, menu "Profile"): ticked templates are added as
  separate workspaces to the shown profile, each on the next free round button; existing content
  stays, undo works. Bundled templates: media & volume, KDE windows & desktops, developer,
  graphics (GIMP, Inkscape, Blender), gaming (Steam, Lutris, Heroic, Discord), streaming (OBS via shortcuts).
- **Versions**: every save creates a snapshot first (max. 100 per profile, at most 60 days).
  The "Versions" dialog restores a profile (the current state is backed up first).
- **Sharing**: export/import single profiles as `.ndprofile` (zip with `profile.json` and your own
  images; an import never replaces an existing profile; older `.ldlprofile` files can still be
  imported). Windows profiles (`.lp5`) can be imported; actions that cannot be mapped appear as
  "Not supported" with a note.

### Settings

`~/.config/neondeck-ct/settings.json`, editable in the editor and via `settings.get/put`:
`active_profile`, `brightness` (0–10), `autostart`, `theme`, `theme_scanlines`, `language`
(`auto` = system language, `de`, `en`, `fr` …; takes effect after restarting editor and service),
`device_look` (`auto`, `classic`, `cockpit`), `dynamic_mode`, `display_sleep_min` (0 = off),
`lock_with_session`, `double_ms`, `hold_ms` and the notification switches
`notify_errors`, `notify_connection`, `notify_profile` (off by default), `tray_mono`.

## Lock and standby

- Screen lock (`org.freedesktop.ScreenSaver`): displays off, input ignored, unlocking restores
  everything. Can be switched off (`lock_with_session`).
- Display sleep: black after a configurable time without input (off by default); the first input only wakes.
- **Screensaver** across all displays, the wheel and the LEDs: cockpit HUD (with real CPU/RAM
  readout), Synthwave, Matrix, Starflight, Aurora; "Match theme" picks one itself. Starts after a
  configurable time without input on the device (default 5 min, 0 = off), preview in the settings
  or `ctl screensaver`. The first touch ends it without triggering the action underneath;
  display sleep and lock take precedence.
- **Device look** "Cockpit" (default with the Cockpit theme, otherwise "Classic"), in the mood of the
  cockpit screensaver: grid with scanlines and a scan line, neon frame per field with a moving
  cyan ↔ magenta gradient, glow and corner accents (black key backgrounds become transparent,
  pressed is magenta), random magenta pings of the frames, data stream in empty fields, bars with
  neon chaser lights, tick ring with radar beam on the wheel, the LED of the active workspace breathes.
  At most 6 frames/s, only changes are sent; keys stay instantly usable.
- After standby/hibernation (logind `PrepareForSleep`) the service reconnects and sends
  brightness, LEDs and all displays again.

## Languages

German is written directly in the code; every further language is **one** file
`data/i18n/<code>.json`. New language: copy `en.json` (e.g. to `es.json`), adjust `_meta`,
translate the values – done, the selection in the settings finds the file by itself. Empty values
stay German. Details: [`data/i18n/README.md`](data/i18n/README.md).

## Data locations

| What | Location |
|---|---|
| Settings | `~/.config/neondeck-ct/settings.json` |
| Profiles | `~/.config/neondeck-ct/profiles/` (versions in `.versionen/<id>/`) |
| Graphics, imported images | `~/.local/share/neondeck-ct/assets`, `…/imported/<id>/` |
| Logs | `~/.local/state/neondeck-ct/log.txt` (service), `editor-log.txt` (editor); 1 MB × 3 each |
| Autostart | `~/.config/autostart/neondeck-ct.desktop` |
| API socket | `$XDG_RUNTIME_DIR/neondeck-ct.sock` |

## Troubleshooting

1. Open the editor, page **Diagnostics**, and work through the red dots.
2. Read the log: `tail -n 50 ~/.local/state/neondeck-ct/log.txt`.
3. No access to the device or `/dev/uinput`: create a udev rule (diagnostics shows the command):

```
# /etc/udev/rules.d/70-neondeck-ct.rules
SUBSYSTEM=="tty", ACTION=="add", ATTRS{idVendor}=="2ec2", ATTRS{idProduct}=="0003|0007", MODE="0660", TAG+="uaccess"
KERNEL=="uinput", SUBSYSTEM=="misc", ACTION=="add", TAG+="uaccess", OPTIONS+="static_node=uinput"
```

   Then `sudo udevadm control --reload-rules && sudo udevadm trigger` and replug the device.
4. A key flashes red: the action failed; the reason is in the log and in a tray message.
5. The profile does not follow the window: check "KWin script" in diagnostics – is Dynamic Mode on?
6. `neondeck-ct ctl status` reports "not running": start the service.

For games or programs that need keyboard input, the service sends through `/dev/uinput`.

## Development

```
.venv/bin/pip install -e .[dev]   # pytest and ruff into the venv
.venv/bin/python -m pytest -q     # test suite
.venv/bin/ruff check src tests tools
```

## License

[PolyForm Noncommercial 1.0.0](LICENSE). Personal and other noncommercial use and modification
are permitted; commercial use is not. The binding text is in [`LICENSE`](LICENSE).
