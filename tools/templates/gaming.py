"""Vorlagen: Gaming und Videokonferenz."""
from __future__ import annotations

from .build import (
    VOLUME,
    app,
    btn,
    enc,
    hk,
    hold,
    kde,
    template,
    wheel,
)

TEMPLATES: list[dict] = [
    template(
        "gaming", "Gaming (Steam, Lutris, Discord)",
        "Steam, Lutris, Heroic und Discord fokussieren oder starten, Mikrofon und Ton stumm, "
        "Audioausgang wechseln, Lautstärke-Mixer, MangoHud, Bildschirmfoto; Regler je Anwendung.",
        [("Gaming", [
            app("steam", "Steam"), app("net.lutris.Lutris", "Lutris"),
            app("com.heroicgameslauncher.hgl", "Heroic"),
            app("com.discordapp.Discord", "Discord", "ChatMessage"),
            btn({"type": "mic_mute"}, "Mikro", "MediaMuteMic"),
            btn({"type": "mute_toggle"}, "Ton aus", "MediaVolumeMute"),
            btn({"type": "audio_output_next"}, "Ausgang", "MediaHeadphones"),
            btn({"type": "dynamic_folder", "kind": "mixer"}, "Mixer", "BarGraph"),
            btn({"type": "hotkey", "keys": "KEY_RIGHTSHIFT+KEY_F12"}, "HUD", "Monitor"),
            kde("screenshot", "Foto", "Screenshot"),
            btn({"type": "media", "key": "play_pause"}, "Musik", "MediaPlayPause"),
            kde("overview", "Fenster", "SwitchPages")])],
        [VOLUME,
         *[enc(f"App {i + 1}", rotate={"type": "stream_volume", "index": i},
               press={"type": "stream_mute", "index": i}) for i in range(3)],
         enc("Helligkeit", rotate={"type": "brightness"}, press={"type": "brightness_reset"},
             strip="bar")],
        wheel("Lautstärke", rotate={"type": "volume"}, tap={"type": "mute_toggle"},
              display="arc"), "#ff003c"),
    template(
        "konferenz", "Videokonferenz (Zoom, Teams, Jitsi, Discord)",
        "Je Programm eine Seite: Mikrofon und Kamera, Hand heben, Bildschirm teilen, Auflegen und "
        "mehr (Zoom, Teams, Jitsi, Discord), dazu das Systemmikrofon stumm; Regler für "
        "Lautstärke und Anwendungen.",
        [("Zoom", [
            app("us.zoom.Zoom", "Zoom"), hk("Alt+A", "Mikro", "MediaMuteMic"),
            hk("Alt+V", "Kamera", "MediaVideoOn"), hk("Alt+S", "Teilen", "ScreenCapture"),
            hk("Alt+Y", "Hand", "UserVoice"), hk("Alt+Q", "Auflegen", "Close"),
            btn({"type": "mic_mute"}, "Mikro Sys.", "MediaMuteMic"),
            hk("Alt+F1", "Sprecher", "User"), hk("Alt+F2", "Galerie"),
            hk("Alt+H", "Chat", "ChatMessage"), hk("Alt+U", "Teilnehmer"),
            hk("Alt+F", "Vollbild", "Monitor")]),
         ("Teams", [
            app("com.github.IsmaelMartinez.teams_for_linux", "Teams"),
            hk("Strg+Umschalt+M", "Mikro", "MediaMuteMic"),
            hk("Strg+Umschalt+O", "Kamera", "MediaVideoOn"),
            hk("Strg+Umschalt+E", "Teilen", "ScreenCapture"),
            hk("Strg+Umschalt+K", "Hand", "UserVoice"), hk("Strg+Umschalt+H", "Auflegen", "Close"),
            btn({"type": "mic_mute"}, "Mikro Sys.", "MediaMuteMic"),
            hk("Strg+Umschalt+S", "Annehmen", "ThumbsUp"),
            hk("Strg+Umschalt+D", "Ablehnen", "ThumbsDown"),
            hk("Strg+Umschalt+P", "Weichzeic.")]),
         ("Jitsi", [
            app("org.jitsi.jitsi-meet", "Jitsi"), hk("M", "Mikro", "MediaMuteMic"),
            hk("V", "Kamera", "MediaVideoOn"), hk("D", "Teilen", "ScreenCapture"),
            hk("R", "Hand", "UserVoice"), hold("Leertaste", "Sprechen", "Dictation"),
            btn({"type": "mic_mute"}, "Mikro Sys.", "MediaMuteMic"), hk("W", "Kacheln"),
            hk("C", "Chat", "ChatMessage"), hk("S", "Vollbild", "Monitor")]),
         ("Discord", [
            app("com.discordapp.Discord", "Discord", "ChatMessage"),
            hk("Strg+Umschalt+M", "Mikro", "MediaMuteMic"),
            hk("Strg+Umschalt+D", "Taub", "MediaHeadphonesOff"),
            hk("Strg+Enter", "Annehmen", "ThumbsUp"), hk("Esc", "Ablehnen", "ThumbsDown"),
            btn({"type": "mic_mute"}, "Mikro Sys.", "MediaMuteMic"),
            btn({"type": "mute_toggle"}, "Ton aus", "MediaVolumeMute")])],
        [VOLUME, *[enc(f"App {i + 1}", rotate={"type": "stream_volume", "index": i},
                       press={"type": "stream_mute", "index": i}) for i in range(2)]],
        wheel("Lautstärke", rotate={"type": "volume"}, tap={"type": "mute_toggle"},
              display="arc"), "#8a2be2"),
]
