"""Ersatz fuer Session-Bus und KWin-Scripting (Tests laden nie Skripte ins echte KWin und
belegen nie den echten Dienstnamen)."""
from __future__ import annotations


class FakeBus:
    """Nimmt Dienst und Objekt entgegen wie ``QDBusConnection``; die Tests rufen die Slots
    des registrierten Objekts direkt auf (so, wie KWin per ``callDBus`` es taete)."""

    def __init__(self, service_ok: bool = True):
        self.service_ok = service_ok
        self.services: list[str] = []
        self.objects: dict[str, tuple[object, object]] = {}
        self.log: list[tuple] = []

    def registerService(self, name):
        self.log.append(("registerService", name))
        if self.service_ok:
            self.services.append(name)
        return self.service_ok

    def unregisterService(self, name):
        self.log.append(("unregisterService", name))
        if name in self.services:
            self.services.remove(name)
            return True
        return False

    def registerObject(self, path, obj, options):
        self.log.append(("registerObject", path))
        self.objects[path] = (obj, options)
        return True

    def unregisterObject(self, path):
        self.log.append(("unregisterObject", path))
        self.objects.pop(path, None)

    def receiver(self, path="/Window"):
        return self.objects[path][0]


class FakeKWin:
    """``kwin_iface_factory``: zeichnet alle Aufrufe als ``(pfad, methode, *args)`` auf.

    ``loadScript`` liefert ``script_id`` (negativ = Fehler); geladene Skripte werden samt
    Inhalt (zum Ladezeitpunkt) in ``loaded`` gemerkt."""

    def __init__(self, script_id: int = 7, run_ok: bool = True):
        self.script_id = script_id
        self.run_ok = run_ok  # False: "run" antwortet mit D-Bus-Fehler (None)
        self.calls: list[tuple] = []
        self.loaded: dict[str, str] = {}  # Name -> Skripttext
        self.contents: list[str] = []

    def __call__(self, path, interface):
        return _FakeIface(self, path, interface)

    def methods(self):
        return [c[1:] for c in self.calls]


class _FakeIface:
    def __init__(self, kwin: FakeKWin, path: str, interface: str):
        self.kwin, self.path, self.interface = kwin, path, interface

    def call(self, method, *args):
        self.kwin.calls.append((self.path, method, *args))
        if method == "loadScript":
            path, name = args
            with open(path, encoding="utf-8") as f:
                text = f.read()
            self.kwin.contents.append(text)
            if self.kwin.script_id >= 0:
                self.kwin.loaded[name] = text
            return [self.kwin.script_id]
        if method == "unloadScript":
            return [self.kwin.loaded.pop(args[0], None) is not None]
        if method == "run" and not self.kwin.run_ok:
            return None
        return []

