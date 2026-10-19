import threading

from neondeck.actions import execute, kde_shortcuts, registry
from support.fakes import FakeKeyboard, FakePopen, FakeRun, make_ctx
from support.service import call


def test_registry_has_types():
    assert {"volume", "mute_toggle", "media", "brightness", "brightness_reset",
            "kde", "kde_adjust"} <= registry().keys()


def test_volume_up_3_steps():
    run = FakeRun({"get-volume": (0, "Volume: 0.48\n")})
    r = execute({"type": "volume"}, make_ctx(run), steps=3)
    assert r.ok and r.message == "48 %" and r.value == 48.0
    assert run.calls == [["wpctl", "set-volume", "-l", "1.0", "@DEFAULT_AUDIO_SINK@", "6%+"],
                         ["wpctl", "get-volume", "@DEFAULT_AUDIO_SINK@"]]  # Grenze 100 %


def test_volume_down():
    run = FakeRun({"get-volume": (0, "Volume: 0.26\n")})
    execute({"type": "volume"}, make_ctx(run), steps=-2)
    assert run.calls[0][-1] == "4%-"


def test_volume_zero_steps_noop():
    run = FakeRun()
    assert execute({"type": "volume"}, make_ctx(run), steps=0).ok
    assert run.calls == []


def test_volume_muted_message():
    run = FakeRun({"get-volume": (0, "Volume: 0.42 [MUTED]\n")})
    res = execute({"type": "volume"}, make_ctx(run), steps=1)
    assert res.muted and res.value is None and res.message == "stumm"


def test_volume_failure_and_missing():
    r = execute({"type": "volume"}, make_ctx(FakeRun({"set-volume": (1, "")})), steps=1)
    assert not r.ok and "boom" in r.message
    r = execute({"type": "volume"}, make_ctx(FakeRun(missing=("wpctl",))), steps=1)
    assert not r.ok and r.message == "wpctl nicht installiert"


def test_mute_toggle():
    run = FakeRun()
    assert execute({"type": "mute_toggle"}, make_ctx(run)).ok
    assert run.calls == [["pactl", "set-sink-mute", "@DEFAULT_SINK@", "toggle"]]


def test_media_next_key():
    kb = FakeKeyboard()
    assert execute({"type": "media", "key": "next"}, make_ctx(keyboard=kb)).ok
    assert kb.taps == ["KEY_NEXTSONG"]


def test_media_other_keys_and_unknown():
    kb = FakeKeyboard()
    for key in ("play_pause", "previous", "stop"):
        execute({"type": "media", "key": key}, make_ctx(keyboard=kb))
    assert kb.taps == ["KEY_PLAYPAUSE", "KEY_PREVIOUSSONG", "KEY_STOPCD"]
    assert not execute({"type": "media", "key": "x"}, make_ctx(keyboard=kb)).ok


def test_brightness_steps():
    run = FakeRun()
    assert execute({"type": "brightness"}, make_ctx(run), steps=2).ok
    assert run.calls == [["ddcutil", "setvcp", "10", "+", "10"]]
    run = FakeRun()
    execute({"type": "brightness"}, make_ctx(run), steps=-3)
    assert run.calls == [["ddcutil", "setvcp", "10", "-", "15"]]


def test_brightness_error_and_noop():
    r = execute({"type": "brightness"}, make_ctx(FakeRun({"ddcutil": (1, "")})), steps=1)
    assert not r.ok
    run = FakeRun()
    assert execute({"type": "brightness"}, make_ctx(run), steps=0).ok and run.calls == []


def test_brightness_reset():
    run = FakeRun()
    assert execute({"type": "brightness_reset"}, make_ctx(run)).ok
    assert run.calls == [["ddcutil", "setvcp", "10", "70"]]


def test_kde_overview_invokes_shortcut():
    run = FakeRun()
    assert execute({"type": "kde", "name": "overview"}, make_ctx(run)).ok
    assert run.calls[0][:4] == ["qdbus", "org.kde.kglobalaccel", "/component/kwin",
                                "org.kde.kglobalaccel.Component.invokeShortcut"]
    assert run.calls[0][-1] == "Overview"


def test_kde_shortcut_names():
    expected = {"show_desktop": "Show Desktop", "desktop_next": "Switch to Next Desktop",
                "desktop_previous": "Switch to Previous Desktop",
                "window_switcher": "Walk Through Windows"}
    for name, shortcut in expected.items():
        run = FakeRun()
        execute({"type": "kde", "name": name}, make_ctx(run))
        assert run.calls[0][-1] == shortcut


def test_kde_lock_runs_loginctl():
    run = FakeRun()
    assert execute({"type": "kde", "name": "lock"}, make_ctx(run)).ok
    assert run.calls == [["loginctl", "lock-session"]]


def test_kde_gui_programs_detached():
    for name, argv in {"screenshot": ["spectacle", "-r"], "search": ["krunner"],
                       "files": ["dolphin"], "emoji": ["plasma-emojier"]}.items():
        pop, run = FakePopen(), FakeRun()
        assert execute({"type": "kde", "name": name}, make_ctx(run, pop)).ok
        assert pop.calls[0][0] == argv and pop.calls[0][1]["start_new_session"] is True
        assert run.calls == []


def test_kde_gui_missing_program():
    r = execute({"type": "kde", "name": "files"}, make_ctx(popen=FakePopen(missing=("dolphin",))))
    assert not r.ok and r.message == "dolphin nicht installiert"


def test_kde_unknown_name():
    assert not execute({"type": "kde", "name": "nope"}, make_ctx()).ok


def test_desktop_add():
    run = FakeRun({"VirtualDesktopManager.count": (0, "3\n")})
    assert execute({"type": "kde", "name": "desktop_add"}, make_ctx(run)).ok
    assert run.calls[1] == ["qdbus", "org.kde.KWin", "/VirtualDesktopManager",
                            "org.kde.KWin.VirtualDesktopManager.createDesktop", "3",
                            "Arbeitsfläche 4"]


def test_desktop_remove_only_if_more_than_one():
    run = FakeRun({"VirtualDesktopManager.count": (0, "1\n")})
    assert execute({"type": "kde", "name": "desktop_remove"}, make_ctx(run)).ok
    assert not any("removeDesktop" in " ".join(c) for c in run.calls)


def test_desktop_remove_current():
    run = FakeRun({"VirtualDesktopManager.count": (0, "2\n"),
                   "VirtualDesktopManager.current": (0, "abc-123\n")})
    assert execute({"type": "kde", "name": "desktop_remove"}, make_ctx(run)).ok
    assert run.calls[-1] == ["qdbus", "org.kde.KWin", "/VirtualDesktopManager",
                             "org.kde.KWin.VirtualDesktopManager.removeDesktop", "abc-123"]


def test_kde_adjust():
    run = FakeRun()
    action = {"type": "kde_adjust", "left": "desktop_previous", "right": "desktop_next"}
    assert execute(action, make_ctx(run), steps=2).ok
    assert [c[-1] for c in run.calls] == ["Switch to Next Desktop"] * 2
    run = FakeRun()
    execute(action, make_ctx(run), steps=-1)
    assert [c[-1] for c in run.calls] == ["Switch to Previous Desktop"]
    run = FakeRun()
    assert execute(action, make_ctx(run), steps=0).ok and run.calls == []


def test_kde_qdbus_missing():
    r = execute({"type": "kde", "name": "overview"}, make_ctx(FakeRun(missing=("qdbus",))))
    assert not r.ok and r.message == "qdbus nicht installiert"


# --- KDE-Kürzel ------------------------------------------------------------------------

COMPONENTS = ("[Argument: ao {[ObjectPath: /component/kwin], "
              "[ObjectPath: /component/org_kde_spectacle_desktop]}]\n")
KWIN_INFOS = ('[Argument: a(ssssssaiai) {[Argument: (ssssssaiai) "Kill Window", '
              '"Fenster beseitigen", "kwin", "KWin", "default", "Default Context", '
              '[Argument: ai {352321536}], [Argument: ai {352321536}]], '
              '[Argument: (ssssssaiai) "Say \\"hi\\"", "", "kwin", "KWin", "default", '
              '"Default Context", [Argument: ai {}], [Argument: ai {}]]}]\n')
SPECTACLE_INFOS = ('[Argument: a(ssssssaiai) {[Argument: (ssssssaiai) "_launch", '
                   '"Spectacle starten", "org.kde.spectacle.desktop", "Spectacle", "default", '
                   '"Default Context", [Argument: ai {}], [Argument: ai {}]]}]\n')


def test_kde_shortcut_invokes():
    run = FakeRun()
    r = execute({"type": "kde_shortcut", "component": "org.kde.spectacle.desktop",
                 "name": "RectangularRegionScreenShot"}, make_ctx(run))
    assert r.ok
    assert run.calls == [["qdbus", "org.kde.kglobalaccel", "/component/org_kde_spectacle_desktop",
                          "org.kde.kglobalaccel.Component.invokeShortcut",
                          "RectangularRegionScreenShot"]]
    assert not execute({"type": "kde_shortcut", "component": "kwin", "name": ""}, make_ctx()).ok
    assert not execute({"type": "kde_shortcut", "component": "kwin", "name": "X"},
                       make_ctx(FakeRun({"qdbus": (1, "")}))).ok
    # Liste aller Kuerzel ueber kglobalaccel
    run = FakeRun({"allComponents": (0, COMPONENTS),
                   "/component/kwin org": (0, KWIN_INFOS),
                   "/component/org_kde_spectacle_desktop org": (0, SPECTACLE_INFOS)})
    assert kde_shortcuts.list_shortcuts(run) == [
        ("kwin", "Kill Window", "Fenster beseitigen"), ("kwin", 'Say "hi"', 'Say "hi"'),
        ("org.kde.spectacle.desktop", "_launch", "Spectacle starten")]
    assert run.calls[0] == ["qdbus", "--literal", "org.kde.kglobalaccel", "/kglobalaccel",
                            "org.kde.KGlobalAccel.allComponents"]
    assert run.calls[1] == ["qdbus", "--literal", "org.kde.kglobalaccel", "/component/kwin",
                            "org.kde.kglobalaccel.Component.allShortcutInfos"]
    assert kde_shortcuts.list_shortcuts(FakeRun(missing=("qdbus",))) == []


def test_kde_shortcuts_api_cached_off_gui_thread(api_service, api_client, monkeypatch):
    calls = []

    def fake(run=None):
        calls.append(threading.current_thread() is threading.main_thread())
        return [("kwin", "Kill Window", "Fenster beseitigen")]

    monkeypatch.setattr(kde_shortcuts, "list_shortcuts", fake)
    want = [{"component": "kwin", "name": "Kill Window", "friendly": "Fenster beseitigen"}]
    assert call(api_client, "kde.shortcuts") == want
    assert call(api_client, "kde.shortcuts") == want
    assert calls == [False]  # einmal gelesen, nicht im GUI-Thread
