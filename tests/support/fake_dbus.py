"""Ersatz fuer QtDBus-Signal-Abos (Tests abonnieren nie echte logind-/Bildschirmschoner-
Signale)."""
from __future__ import annotations


class FakeSignalBus:
    """Ersatz fuer ``QDBusConnection.connect``/``disconnect`` (Signal-Abos auf System- oder
    Session-Bus). ``emit`` ruft die abonnierten Slots so auf, wie QtDBus es taete – und
    prueft dabei, dass der Slot-Name wirklich ein Qt-Slot des Empfaengers ist."""

    def __init__(self, ok: bool = True):
        self.ok = ok
        self.subscriptions: list[tuple] = []  # (service, path, interface, name, receiver, slot)

    def connect(self, service, path, interface, name, receiver, slot):
        if self.ok:
            self.subscriptions.append((service, path, interface, name, receiver, slot))
        return self.ok

    def disconnect(self, service, path, interface, name, receiver, slot):
        entry = (service, path, interface, name, receiver, slot)
        if entry in self.subscriptions:
            self.subscriptions.remove(entry)
            return True
        return False

    def emit(self, path, interface, name, *args):
        for _service, p, iface, n, receiver, slot in list(self.subscriptions):
            if (p, iface, n) != (path, interface, name):
                continue
            signature = slot[1:]  # QtCore.SLOT("f(bool)") -> "1f(bool)"
            assert receiver.metaObject().indexOfSlot(signature) >= 0, f"kein Slot {signature}"
            getattr(receiver, signature.split("(", 1)[0])(*args)
