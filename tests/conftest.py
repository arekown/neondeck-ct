import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent  # noqa: E402 - erst nach QT_QPA_PLATFORM
from PySide6.QtWidgets import QApplication  # noqa: E402 - erst nach QT_QPA_PLATFORM

# Eine QApplication fuer alle Tests: Tray/Fenster brauchen sie, und eine zuerst von
# render angelegte QGuiApplication liesse sich nicht mehr ersetzen.
_QAPP = QApplication.instance() or QApplication([])

import pytest  # noqa: E402 - erst nach der QApplication

from neondeck.ui import theme  # noqa: E402 - erst nach der QApplication


@pytest.fixture(autouse=True)
def _private_data_dirs(tmp_path, monkeypatch):
    """Kein Test liest oder schreibt die echten Datenorte (``~/.config/neondeck-ct``,
    ``~/.local/share|state/neondeck-ct``, Autostart): ``NEONDECK_HOME`` zeigt immer auf einen
    eigenen tmp-Ordner. Module mit ``usefixtures("home")`` biegen ihn nur weiter um.

    Zweite Sicherung: auch ``HOME`` und die XDG-Benutzerordner zeigen auf einen tmp-Ordner –
    was ``NEONDECK_HOME`` vergisst (``Path.home()``, Starter in ``~/.local/bin``), landet so
    nie beim Nutzer. Die QApplication (und damit Schriften/fontconfig) ist da schon mit dem echten
    ``HOME`` angelegt."""
    monkeypatch.setenv("NEONDECK_HOME", str(tmp_path / "ldl-home"))
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    for var, sub in (("XDG_CONFIG_HOME", ".config"), ("XDG_DATA_HOME", ".local/share"),
                     ("XDG_STATE_HOME", ".local/state"), ("XDG_CACHE_HOME", ".cache")):
        monkeypatch.setenv(var, str(home / sub))


@pytest.fixture(autouse=True)
def _german(monkeypatch):
    """Tests sehen immer Deutsch (Quelltext): Systemsprache ``de``, und eine von Dienst,
    Editor oder CLI gesetzte Sprache gilt nur bis zum Testende."""
    from neondeck.core import i18n

    for var in ("LC_ALL", "LC_MESSAGES"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("LANG", "de_DE.UTF-8")
    yield
    i18n.set_language(i18n.SOURCE)


@pytest.fixture(autouse=True)
def _system_theme_after_test():
    """Ein Test, der ein Theme anlegt (auch ueber main()), vererbt es nicht weiter.

    Die Zwischenablage wird geleert (Exit 139, siehe unten).

    Danach werden mit ``deleteLater`` freigegebene Widgets wirklich geloescht: ohne laufende
    Ereignisschleife blieben sie bis Testende liegen, und jedes spaetere ``setStyleSheet`` der
    Anwendung muesste sie alle neu gestalten (Sekunden je Theme-Wechsel)."""
    yield
    if theme.current().name != theme.SYSTEM:
        theme.apply(_QAPP, theme.SYSTEM)
    # Offscreen haelt Qt gesetzte QMimeData in einer prozessweiten statischen Variable, die
    # erst nach dem Python-Interpreter zerstoert wird -> Segfault (Exit 139) beim Beenden.
    # Leeren je Test: kein Absturz am Ende, und Kopier-Tests haengen nicht voneinander ab.
    _QAPP.clipboard().clear()
    _QAPP.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)


def pytest_configure(config):
    config.addinivalue_line("markers", "real_spawn: Test prueft das echte Starten "
                            "(und ersetzt dafuer selbst subprocess.Popen)")


@pytest.fixture(autouse=True)
def _no_real_processes(request, monkeypatch):
    """Kein Test startet einen echten Dienst oder Editor (Tests injizieren ihren Starter)."""
    from neondeck.api import client as api_client

    if request.node.get_closest_marker("real_spawn"):
        return

    def refuse(cmd, env):
        raise AssertionError(f"Test wollte einen Prozess starten: {cmd}")

    monkeypatch.setattr(api_client, "_spawn", refuse)


@pytest.fixture(autouse=True)
def _no_real_service(monkeypatch):
    """``main()`` darf in Tests nie einen echten Dienst (Geraet, Ereignisschleife) starten."""
    from neondeck.service import app as app_main

    def refuse(qapp, server_name):
        raise AssertionError(f"Test wollte einen echten Dienst starten ({server_name})")

    monkeypatch.setattr(app_main, "_serve", refuse, raising=False)


@pytest.fixture(autouse=True)
def _private_addresses(monkeypatch):
    """Standardadressen zeigen nie auf den Dienst des Nutzers: eigener Laufzeitordner,
    eigene „alte“ Adresse (sonst fragte die Einzelinstanz-Pruefung /tmp/neondeck-ct)."""
    import shutil
    import tempfile
    import uuid

    from neondeck.api import protocol

    runtime = tempfile.mkdtemp(prefix="ldl-run-")  # kurz: Socket-Pfade max. 107 Zeichen
    monkeypatch.setenv("XDG_RUNTIME_DIR", runtime)
    monkeypatch.setattr(protocol, "LEGACY_NAME", f"ldl-legacy-{uuid.uuid4().hex}")
    yield
    shutil.rmtree(runtime, ignore_errors=True)


@pytest.fixture(autouse=True)
def _no_real_kwin(monkeypatch):
    """Kein Test belegt den echten D-Bus-Dienstnamen oder laedt Skripte ins echte KWin:
    der Dienst bekommt einen Fensterwaechter mit Ersatz-Bus und Ersatz-KWin."""
    from neondeck.desktop.kwin import KWinWatcher
    from neondeck.service import app as app_main
    from support.fake_kwin import FakeBus, FakeKWin

    monkeypatch.setattr(app_main, "_make_window_watcher",
                        lambda: KWinWatcher(bus=FakeBus(), kwin_iface_factory=FakeKWin()))


@pytest.fixture(autouse=True)
def _no_real_shortcut_block(monkeypatch):
    """Kein Test sperrt die echten globalen KDE-Kuerzel: die Aufnahme-Sperre schreibt nur mit."""
    from neondeck.editor.widgets import shortcut_block

    calls: list[bool] = []
    old = shortcut_block.replace(shortcut_block.ShortcutBlock(calls.append))
    yield calls
    shortcut_block.replace(old)


@pytest.fixture(autouse=True)
def _no_real_session_bus(monkeypatch):
    """Kein Test abonniert echte logind-/Bildschirmschoner-Signale: der Dienst bekommt einen
    Sitzungswaechter mit Ersatz-Bussen."""
    from neondeck.service import app as app_main
    from support.fake_dbus import FakeSignalBus

    def fake():
        from neondeck.desktop.session import SessionWatcher
        return SessionWatcher(bus=FakeSignalBus(), system_bus=FakeSignalBus())

    monkeypatch.setattr(app_main, "_make_session_watcher", fake)


@pytest.fixture(autouse=True)
def _no_real_audio_or_mpris(monkeypatch):
    """Kein Test startet echtes ``pactl subscribe`` oder fragt echte MPRIS-Player ab: der
    Dienst bekommt Ersatz-Prozesse und einen Ersatz-Bus."""
    from neondeck.desktop.audio_state import AudioState
    from neondeck.desktop.mpris import Mpris
    from neondeck.service import app as app_main
    from support.fake_dbus import FakeSignalBus
    from support.fake_process import FakeProcess

    monkeypatch.setattr(app_main, "_make_audio_state",
                        lambda: AudioState(process_factory=FakeProcess))
    monkeypatch.setattr(app_main, "_make_mpris",
                        lambda: Mpris(bus=FakeSignalBus(), caller=lambda *args: None))


@pytest.fixture(autouse=True)
def _no_real_flatpak(monkeypatch):
    """Die Profil-Uebernahme fragt in Tests nie das echte ``flatpak info`` (Tests, die es
    pruefen, geben ``flatpak_installed`` selbst an)."""
    from neondeck.profile.importers.windows import context

    monkeypatch.setattr(context, "flatpak_app_installed", lambda app_id: False)


# --- Gemeinsame Fixtures (Hilfen in ``support/``) ------------------------------------------

@pytest.fixture
def home(tmp_path, monkeypatch):
    """``NEONDECK_HOME`` direkt im tmp-Ordner des Tests (Module mit ``usefixtures("home")``)."""
    monkeypatch.setenv("NEONDECK_HOME", str(tmp_path))
    return tmp_path


@pytest.fixture
def no_modal_error(monkeypatch):
    """Eine Startfehler-Meldung des Editors darf einen Test nie anhalten (QMessageBox ist
    modal)."""
    from neondeck.editor import main as editor_main

    monkeypatch.setattr(editor_main, "_show_error", lambda text: None)


@pytest.fixture
def api_service():
    """Laufender Dienst (App mit Fake-Geraet) mit API unter eigenem Namen:
    ``(app, server, name)``."""
    from neondeck.api.server import ApiServer
    from neondeck.service.app import App
    from neondeck.ui.poster import QtPoster
    from support.fakes import FakeDevice, FakeKeyboard
    from support.service import unique_name

    app = App(device_factory=FakeDevice, keyboard=FakeKeyboard())
    name = unique_name()
    server = ApiServer(app, name, poster=QtPoster())
    assert server.listen()
    yield app, server, name
    server.close()
    app.quit()


@pytest.fixture
def api_client(api_service):
    """Mit ``api_service`` verbundener ``ApiClient``."""
    from neondeck.api.client import ApiClient
    from support.service import no_start

    c = ApiClient(api_service[2])
    assert c.connect_or_start(timeout=1.0, starter=no_start)
    yield c
    c.close()


@pytest.fixture
def editor_service():
    """Neu startbarer Dienst fuer Editor-Tests (``support.service.Service``)."""
    from support.service import Service, unique_name

    s = Service(unique_name())
    yield s
    s.close()


@pytest.fixture
def editor(editor_service):
    """Editor (``ConfigWindow`` ueber ``RemoteEngine``), verbunden mit ``editor_service``."""
    from neondeck.editor import main as editor_main
    from support.service import no_start

    ed = editor_main.start(server_name=editor_service.name, starter=no_start, timeout=2.0)
    yield ed
    ed.shutdown()


@pytest.fixture
def window_rig(home):
    """``ConfigWindow`` an einer lokalen Engine (``support.window.window_rig``)."""
    from support.window import window_rig as make

    yield from make(home)


@pytest.fixture
def profiles_rig(home):
    """``ConfigWindow`` mit zwei Profilen (``support.window.profiles_rig``)."""
    from support.window import profiles_rig as make

    yield from make(home)
