"""Dienst im Testprozess: ``App`` mit Fake-Geraet hinter einem ``ApiServer`` unter eigenem
Socket-Namen (nie dem des laufenden Dienstes des Nutzers), dazu Aufruf-Helfer fuer den Client.

Die Fixtures, die darauf aufbauen (``api_service``, ``api_client``, ``editor_service``,
``editor``), stehen in ``conftest.py``.
"""
from __future__ import annotations

import uuid

from neondeck.api.client import ApiClient, ApiError
from neondeck.api.server import ApiServer
from neondeck.core import paths
from neondeck.profile.store import ProfileStore
from neondeck.service.app import App
from neondeck.ui.poster import QtPoster

from .fakes import FakeDevice, FakeKeyboard
from .waiting import wait_until


def unique_name() -> str:
    """Eigener Socket-Name je Test."""
    return f"ldl-test-{uuid.uuid4().hex}"


def no_start():
    """Starter, der nie startet: der Dienst muss schon laufen."""
    raise AssertionError("darf den Dienst nicht starten")


def call(c: ApiClient, method: str, params=None, timeout=15.0):
    """Asynchroner Aufruf, wartet mit laufender Ereignisschleife (Server im selben Thread)."""
    got = []
    c.call(method, params or {}, lambda result, error: got.append((result, error)))
    assert wait_until(lambda: got, timeout), f"keine Antwort auf {method}"
    result, error = got[0]
    if error is not None:
        raise ApiError.from_error(error)
    return result


class OpenConfigFacade:
    """Kleinste Dienst-Fassade fuer Einzelinstanz-Tests: zaehlt ``open_config``; was der
    ``ApiServer`` beim Anmelden braucht (``add_listener``, ``api``), ist leer da."""

    def __init__(self):
        self.opened = 0
        self.api = None

    def open_config(self):
        self.opened += 1

    def add_listener(self, fn):
        pass


class Service:
    """Dienst (App mit Fake-Geraet) mit API unter eigenem Namen; neu startbar."""

    def __init__(self, name: str, *, editor_starter=None):
        self.name = name
        self.started_editors: list = []
        self.app = App(device_factory=FakeDevice, keyboard=FakeKeyboard(),
                       editor_starter=editor_starter or self.started_editors.append)
        self.server = None
        self.start_server()

    def start_server(self) -> None:
        self.server = ApiServer(self.app, self.name, poster=QtPoster())
        assert self.server.listen()

    def stop_server(self) -> None:
        self.server.close()
        self.server = None

    @property
    def store(self) -> ProfileStore:
        return ProfileStore(paths.config_dir() / "profiles")

    def close(self) -> None:
        if self.server is not None:
            self.server.close()
        self.app.quit()
