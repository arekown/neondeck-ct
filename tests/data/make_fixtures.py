"""Erzeugt die synthetischen Testdaten ``tests/data/synthetic-profile/``.

Eigene Inhalte im Format eines Windows-Loupedeck-Profils (``ProfileInfo.json`` plus
``ActionIcons/*.ict``): eigene Namen, eigene Kennungen, eigene Beschriftungen, Symbole als
einfache selbst gezeichnete Formen (SVG-Text, ein Symbol als PNG mit Pillow).
Die erzeugten Dateien sind eingecheckt; die Tests brauchen diesen Aufruf nicht.

    python tests/data/make_fixtures.py
"""
from __future__ import annotations

import base64
import io
import json
import shutil
import uuid
from pathlib import Path

OUT = Path(__file__).parent / "synthetic-profile"
NS = uuid.UUID("5d1a7c3e-0000-4000-8000-000000000042")


def gid(label: str) -> str:
    """Stabile 32-stellige Kennung (GUID ohne Bindestriche) aus einem Namen."""
    return uuid.uuid5(NS, label).hex.upper()


ARGB_BLACK, ARGB_WHITE = 0xFF000000, 0xFFFFFFFF
T = "$type"
KEYS = "Loupedeck.Service.{}, LoupedeckService"
DICT = ("System.Collections.Generic.Dictionary`2[[System.String, System.Private.CoreLib],"
        "[System.String, System.Private.CoreLib]], System.Private.CoreLib")
NOCASE = "Loupedeck.StringDictionaryNoCase, PluginApi"

WS_ALPHA, WS_BETA = gid("workspace-alpha"), gid("workspace-beta")
PAGE_A, PAGE_B = gid("touch-page-a"), gid("touch-page-b")
ENC_A, WHEEL_A, WHEEL_B = gid("encoder-page-a"), gid("wheel-page-a"), gid("wheel-page-b")
M_CONSOLE, M_NETINFO = gid("macro-console"), gid("macro-netinfo")
M_VIDEO, M_SOCIAL, M_FOX, M_CHROME = (gid("macro-video"), gid("macro-social"),
                                      gid("macro-fox"), gid("macro-chrome"))
A_TRACK, A_SCROLL, A_DESK = gid("adjust-track"), gid("adjust-scroll"), gid("adjust-desk")
P_UP, P_LEFT, P_DOWN, P_RIGHT, P_PGDN, P_FN = (gid(f"pa-{n}") for n in
                                               ("up", "left", "down", "right", "pgdn", "fn"))
E_UP, E_DOWN = gid("cmd-scroll-up"), gid("cmd-scroll-down")
E_WINR, E_ENTER1, E_ENTER2, E_ENTER3 = (gid(f"cmd-{n}") for n in ("winr", "enter1", "enter2",
                                                                   "enter3"))
E_WINR2 = gid("cmd-winr2")


def btn(press=None, fn=None) -> dict:
    return {T: KEYS.format("ProfileLayoutButton"), "pressAction": press, "fnPressAction": fn}


def enc(press=None, rotate=None) -> dict:
    return {T: KEYS.format("ProfileLayoutEncoder"), "pressAction": press, "fnPressAction": None,
            "rotateAction": rotate, "fnRotateAction": None}


def key_cmd(name: str, key: str) -> dict:
    return {T: KEYS.format("MacroActionEditorCommand"), "name": name,
            "templateName": "$@Generic___@KeyboardKey",
            "actionParameters": {T: DICT, "keyboardKey": f"{key}___1___{key}___"}}


def macro(guid: str, title: str, actions: list[str], cmds: list[dict] | None = None) -> dict:
    return {T: KEYS.format("ApplicationProfileMacroCommand"), "isCommand": True, "name": guid,
            "displayName": title, "description": "", "groupName": "Eigene",
            "superGroupName": "@macro", "supportedOs": "All", "supportedModes": ["System"],
            "showAsSingleAction": False, "actionEditorCommands": cmds or [],
            "isMultiState": False, "actions": actions}


def adjustment(guid: str, title: str, left: list[str], right: list[str],
               cmds: list[dict] | None = None) -> dict:
    return {T: KEYS.format("ApplicationProfileMacroAdjustment"), "isCommand": False,
            "name": guid, "displayName": title, "description": "", "groupName": "Eigene",
            "superGroupName": None, "supportedOs": "All", "supportedModes": ["System"],
            "showAsSingleAction": False, "actionEditorCommands": cmds or [],
            "actionsBefore": [], "actionsLeft": left, "actionsRight": right,
            "actionsReset": []}


def profile_action(guid: str, key: str) -> dict:
    return {T: KEYS.format("ApplicationProfileCommand"),
            "isCommand": True, "name": f"$@Generic___@ProfileAction___{guid}",
            "templateActionName": "$@Generic___@KeyboardKey",
            "actionParameters": {T: "Loupedeck.ActionEditorActionParameters, PluginApi",
                                 "parameters": {T: NOCASE, "keyboardKey": f"{key}___1___{key}___"},
                                 "count": 1},
            "displayName": key, "description": "", "groupName": "Eigene",
            "superGroupName": "@macro", "isProfileAction": True, "isMultiState": False,
            "isResetCommand": False, "adjustmentName": None, "states": None}


def build_profile() -> dict:
    ws = lambda g, title, tp, ep, wp: {  # noqa: E731 - kurze Hilfe im Test
        T: KEYS.format("ProfileLayoutWorkspace20"), "name": g, "displayName": title,
        "description": "", "touchPageNames": tp, "encoderPageNames": ep, "wheelPageNames": wp,
        "activationActions": []}
    page_a = [
        "$@Generic___@ButtonClock",
        "$DefaultWin___#DynamicFolder___DynamicFolder#Loupedeck.DefaultWinPlugin."
        "VolumeMixerOutputDynamicFolder",
        "$DefaultWin___#DynamicFolder___DynamicFolder#Loupedeck.DefaultWinPlugin."
        "TaskSwitcherDynamicFolder",
        "$DefaultWin___LockWorkstation",
        "$@Generic___Loupedeck.GenericPlugin.StopwatchDynamicAction",
        "$@Generic___Loupedeck.GenericPlugin.DateTimeDynamicAction___WeekNumber",
        "$@Generic___Loupedeck.GenericPlugin.DateTimeDynamicAction___Date",
        "$DefaultWin___AddDesktop",
        "$DefaultWin___WindowsExplorer",
        "$DefaultWin___WindowsSearch",
        "$DefaultWin___WindowsEmoji",
        "$DefaultWin___WindowsScreenshot",
    ]
    page_b = [
        f"$@Generic___@Macro___{M_CONSOLE}",
        f"$@Generic___@Macro___{M_NETINFO}",
        f"$@Generic___@Macro___{M_VIDEO}",
        f"$@Generic___@Macro___{M_SOCIAL}",
        None, None, None, None,
        f"$@Generic___@Macro___{M_FOX}",
        f"$@Generic___@Macro___{M_CHROME}",
        "$@Generic___@ActivateLoupedeckConfiguration___System",
        None,
    ]
    mode = {
        T: KEYS.format("ProfileLayoutMode"), "deviceType": "None", "modeName": "System",
        "parentModeName": None, "actions": None, "dynamicButtonPages": None,
        "dynamicEncoderPages": None,
        "touchPages": [
            {T: KEYS.format("ProfileLayoutButtonPage"), "name": PAGE_A, "displayName": "Page One",
             "description": None, "controls": [btn(a) for a in page_a]},
            {T: KEYS.format("ProfileLayoutButtonPage"), "name": PAGE_B, "displayName": "Page Two",
             "description": None, "controls": [btn(a) for a in page_b]},
        ],
        "encoderPages": [{
            T: KEYS.format("ProfileLayoutEncoderPage"), "name": ENC_A, "displayName": "Dials",
            "description": None, "controls": [
                enc("$DefaultWin___ResetVolume", "$DefaultWin___Volume"),
                enc("$DefaultWin___MediaPlayPause", f"$@Generic___@MacroAdjustment___{A_TRACK}"),
                enc(f"$@Generic___@ProfileAction___{P_PGDN}",
                    f"$@Generic___@MacroAdjustment___{A_SCROLL}"),
                enc(),
                enc("$DefaultWin___ResetBrightness", "$DefaultWin___Brightness"),
                enc("$DefaultWin___CloseDesktop", f"$@Generic___@MacroAdjustment___{A_DESK}"),
            ]}],
        "wheelPages": [
            {T: KEYS.format("ProfileLayoutWheelPage"), "name": WHEEL_A,
             "displayName": "Dial Clock", "description": None, "templateName": "WheelToolAnalogClock",
             "parameters": {T: NOCASE, "adjustment": f"$@Generic___@MacroAdjustment___{A_SCROLL}",
                            "actions": "$@Generic___@ButtonClock"}},
            {T: KEYS.format("ProfileLayoutWheelPage"), "name": WHEEL_B,
             "displayName": "Dial Plain", "description": None, "templateName": "WheelToolPlain",
             "parameters": {T: NOCASE, "adjustment": f"$@Generic___@MacroAdjustment___{A_DESK}"}},
        ],
        "workspaces": [
            ws(WS_ALPHA, "Alpha Workspace", [PAGE_A], [ENC_A], [WHEEL_A]),
            ws(WS_BETA, "Beta Workspace", [PAGE_B], [], [WHEEL_B]),
        ],
        "homeWorkspaceName": WS_ALPHA,
    }
    page = lambda g, controls: {  # noqa: E731 - kurze Hilfe im Test
        T: KEYS.format("ProfileLayoutButtonPage"), "name": g, "displayName": "",
        "description": None, "controls": controls, "dynamicPageName": None,
        "dynamicPagePluginName": None, "dynamicPageNumber": 0}
    cw = "$@Generic___@ChangeWorkspace___System|"
    round_page = page(gid("round-page"), [btn(cw + WS_ALPHA), btn(cw + WS_BETA)]
                      + [btn() for _ in range(6)])
    pa = "$@Generic___@ProfileAction___"
    square_page = page(gid("square-page"), [btn() for _ in range(6)] + [
        btn(pa + P_UP, pa + P_FN), btn(pa + P_LEFT), btn(), btn(pa + P_DOWN), btn(pa + P_RIGHT),
        btn("$DefaultWin___WindowsActions")])
    exe = "$@Generic___@ExecuteApplication___"
    cmd_names = [key_cmd(E_WINR, "Windows+KeyR"), key_cmd(E_ENTER1, "Return")]
    net_cmds = [key_cmd(E_WINR2, "Windows+KeyR"), key_cmd(E_ENTER2, "Return"),
                key_cmd(E_ENTER3, "Return")]
    macros = [
        macro(M_CONSOLE, "Console Alpha",
              [E_WINR, "$@Generic___@TypeText___cmd", "$@Generic___@Sleep___100", E_ENTER1],
              cmd_names),
        macro(M_NETINFO, "Net\\nInfo",
              [E_WINR2, "$@Generic___@Sleep___100", "$@Generic___@TypeText___cmd", E_ENTER2,
               "$@Generic___@Sleep___200", "$@Generic___@TypeText___ipconfig", E_ENTER3],
              net_cmds),
        macro(M_VIDEO, "Video Site", [exe + "https://video.example.org/"]),
        macro(M_SOCIAL, "Social Site", [exe + "https://social.example.org"]),
        macro(M_FOX, "Fox Browser", [exe + "C:\\Program Files\\Mozilla Firefox\\firefox.exe"]),
        macro(M_CHROME, "Chrome Browser", [
            exe + "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
            exe + "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe"]),
    ]
    adjustments = [
        adjustment(A_TRACK, "Track Skipper", ["$DefaultWin___MediaPrevTrack"],
                   ["$DefaultWin___MediaNextTrack"]),
        adjustment(A_SCROLL, "Scroller", [E_UP], [E_DOWN],
                   [key_cmd(E_UP, "ArrowUp"), key_cmd(E_DOWN, "ArrowDown")]),
        adjustment(A_DESK, "Desk Hopper", ["$DefaultWin___PreviousDesktop"],
                   ["$DefaultWin___NextDesktop"]),
    ]
    return {
        T: KEYS.format("ApplicationProfile"), "name": gid("profile"), "profileFlags": "None",
        "displayName": "Default", "description": "", "deviceType": "Loupedeck20",
        "applicationName": "@_defaultwin", "nativePluginName": "DefaultWin",
        "hasNativePlugin": True, "additionalNativePluginNames": [],
        "lastModifiedTimeUtc": "2026-01-01T00:00:00Z", "actionImages90": None,
        "actionImages60": None, "wheelImages": None, "actionColors": None,
        "profileCommands": [], "profileAdjustments": [],
        "layout": {T: KEYS.format("ProfileLayout"), "deviceType": "Loupedeck20",
                   "profileFlags": "None", "layoutModes": [mode],
                   "roundPage": round_page, "squarePage": square_page},
        "macroCommands": macros, "macroAdjustments": adjustments,
        "profileActions": [profile_action(P_UP, "ArrowUp"), profile_action(P_LEFT, "ArrowLeft"),
                           profile_action(P_DOWN, "ArrowDown"),
                           profile_action(P_RIGHT, "ArrowRight"),
                           profile_action(P_PGDN, "PageDown"), profile_action(P_FN, "Home")],
    }


# -- Symbole ---------------------------------------------------------------------------------
SHAPES = {
    "circle": '<circle cx="16" cy="16" r="12" fill="#222425" stroke="#111111"/>',
    "square": '<rect x="5" y="5" width="22" height="22" fill="#222425"/>',
    "triangle": '<polygon points="16,4 28,28 4,28" fill="#222425"/>',
    "bars": '<rect x="4" y="14" width="24" height="4" fill="#222425"/>'
            '<rect x="14" y="4" width="4" height="24" fill="#222425"/>',
    "ring": '<circle cx="16" cy="16" r="10" fill="none" stroke="#222425" '
            'style="stroke:#222425;fill:none"/>',
}


def svg(shape: str) -> str:
    return ('<svg width="32" height="32" viewBox="0 0 32 32" xmlns="http://www.w3.org/2000/svg">'
            + SHAPES[shape] + "</svg>")


def png_b64() -> str:
    from PIL import Image, ImageDraw
    im = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.ellipse((4, 4, 27, 27), fill=(200, 60, 60, 255))
    d.rectangle((12, 12, 19, 19), fill=(255, 255, 255, 255))
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return base64.b64encode(buf.getvalue()).decode()


def ict(text: str | None, image_b64: str | None, *, text_visible=True) -> dict:
    items = []
    if image_b64:
        items.append({T: "Loupedeck.Service.ActionIconImageItem, LoupedeckShared",
                      "image": image_b64, "imageFileName": None, "imageColor": ARGB_WHITE,
                      "imageRotation": "None", "isVisible": True, "itemType": "Image",
                      "area": {"x": 17, "y": 0, "width": 65, "height": 65}})
    if text is not None:
        items.append({T: "Loupedeck.Service.ActionIconTextItem, LoupedeckShared", "text": text,
                      "textColor": ARGB_WHITE, "fontSize": 4, "fontName": "Sans",
                      "isVisible": text_visible, "itemType": "Text",
                      "area": {"x": 0, "y": 57, "width": 100, "height": 32}})
    return {"backgroundColor": ARGB_BLACK, "items": items}


def b64(s: str) -> str:
    return base64.b64encode(s.encode()).decode()


def build_icons() -> dict[str, dict]:
    pa = "$@Generic___@ProfileAction___"
    adj = "$@Generic___@MacroAdjustment___"
    return {
        "$DefaultWin___LockWorkstation": ict("Lock Screen", b64(svg("square"))),
        "$DefaultWin___AddDesktop": ict("Add Desk", b64(svg("bars"))),
        "$DefaultWin___MediaPlayPause": ict("Play", b64(svg("triangle"))),
        "$DefaultWin___WindowsExplorer": ict("Files", b64(svg("square"))),
        "$DefaultWin___WindowsSearch": ict("Find", b64(svg("ring"))),
        "$DefaultWin___WindowsScreenshot": ict("Snap", png_b64()),
        "$DefaultWin___#DynamicFolder___DynamicFolder#Loupedeck.DefaultWinPlugin."
        "VolumeMixerOutputDynamicFolder": ict("Mixer Out", b64(svg("circle"))),
        "$DefaultWin___#DynamicFolder___DynamicFolder#Loupedeck.DefaultWinPlugin."
        "VolumeMixerInputDynamicFolder": ict("Mixer In", b64(svg("circle"))),
        pa + P_UP: ict(None, b64(svg("triangle"))),
        pa + P_DOWN: ict(None, b64(svg("triangle"))),
        adj + A_TRACK: ict("Media Track Control", None, text_visible=False),
        adj + A_SCROLL: ict("Scroll Control", None, text_visible=False),
        adj + A_DESK: ict("Desk Control", None, text_visible=False),
    }


def main() -> None:
    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / "ActionIcons").mkdir(parents=True)
    (OUT / "ProfileInfo.json").write_text(
        json.dumps(build_profile(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    for name, data in build_icons().items():
        (OUT / "ActionIcons" / f"{name}.ict").write_text(
            json.dumps(data, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
