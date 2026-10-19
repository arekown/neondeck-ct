"""Ruhe: Meldungen des Trays folgen den Einstellungen."""
import pytest

from neondeck.api.server import ApiServer
from neondeck.core.settings import Settings
from neondeck.service.app import App
from neondeck.service.device_link import DEVICE_BACK, DEVICE_LOST
from neondeck.ui.poster import QtPoster
from support.fakes import FakeDevice, FakeKeyboard


def test_notifications_respect_settings():
    app = App(device_factory=FakeDevice, keyboard=FakeKeyboard(), editor_starter=lambda n: None)
    shown = []
    app.tray.icon.showMessage = lambda title, text, *a: shown.append(text)
    try:
        app.device_link.on_state(True)  # erstes Verbinden: keine Meldung
        app.device_link.on_state(False)
        assert shown == [DEVICE_LOST]
        app.device_link.on_state(True)
        assert shown == [DEVICE_LOST, DEVICE_BACK]

        server = ApiServer(app, poster=QtPoster())
        server.methods["settings.put"](None, {"notify_connection": False, "notify_errors": False})
        app.device_link.on_state(False)
        app.device_link.on_state(True)
        app.tray.notify("Profil kaputt", warning=True)
        app.tray.notify("Profil „X“", kind="profile")  # Profilwechsel: Standard aus
        assert len(shown) == 2
        server.methods["settings.put"](None, {"notify_errors": True, "notify_profile": True,
                                    "tray_mono": True})
        app.tray.notify("Profil kaputt", warning=True)
        app.tray.notify("Profil „X“", kind="profile")
        assert shown[2:] == ["Profil kaputt", "Profil „X“"]
        assert app.tray.mono
        saved = Settings.load()
        assert (saved.notify_connection, saved.notify_errors, saved.notify_profile,
                saved.tray_mono) == (False, True, True, True)
        with pytest.raises(Exception, match="true oder false"):
            server.methods["settings.put"](None, {"tray_mono": "ja"})
    finally:
        app.quit()
