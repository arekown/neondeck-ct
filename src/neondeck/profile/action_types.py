"""Kennungen der Aktionstypen (``{"type": ...}`` im Profil-JSON), an einer Stelle.

``ActionType`` ist ein ``StrEnum``: ``ActionType.PAGE == "page"``, das JSON bleibt also
unveraendert, und Stellen, die noch Texte vergleichen, laufen weiter. Registriert werden die
Aktionen unter diesen Namen in ``actions.base.register``.
"""
from __future__ import annotations

from enum import StrEnum


class ActionType(StrEnum):
    ADJUST_HOTKEY = "adjust_hotkey"
    ADJUST_MACRO = "adjust_macro"
    APP_FOCUS = "app_focus"
    AUDIO_OUTPUT_NEXT = "audio_output_next"
    BRIGHTNESS = "brightness"
    BRIGHTNESS_RESET = "brightness_reset"
    CLOCK = "clock"
    COMMAND = "command"
    DATE = "date"
    DYNAMIC_FOLDER = "dynamic_folder"
    FOLDER = "folder"
    FOLDER_BACK = "folder_back"
    HOLD_KEY = "hold_key"
    HOTKEY = "hotkey"
    HTTP = "http"
    KDE = "kde"
    KDE_ADJUST = "kde_adjust"
    KDE_SHORTCUT = "kde_shortcut"
    MACRO = "macro"
    MEDIA = "media"
    MIC_MUTE = "mic_mute"
    MUTE_TOGGLE = "mute_toggle"
    OPEN = "open"
    OPEN_CONFIG = "open_config"
    PAGE = "page"
    PAGE_NEXT = "page_next"
    PAGE_PREVIOUS = "page_previous"
    PROFILE = "profile"
    RUN = "run"
    SCROLL = "scroll"
    SLEEP = "sleep"
    STOPWATCH = "stopwatch"
    STREAM_MUTE = "stream_mute"
    STREAM_VOLUME = "stream_volume"
    TERMINAL_LAYOUT = "terminal_layout"
    TEXT = "text"
    UNSUPPORTED = "unsupported"
    VOLUME = "volume"
    WORKSPACE = "workspace"
