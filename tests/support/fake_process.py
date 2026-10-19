"""Ersatz fuer ``QProcess`` (Tests starten nie echtes ``pactl``)."""
from __future__ import annotations

from PySide6.QtCore import QObject, QProcess, Signal


class FakeProcess(QObject):
    """Ersatz fuer ``QProcess``: der Test schreibt Ausgabe und beendet den Prozess."""

    readyReadStandardOutput = Signal()
    finished = Signal(int, object)
    errorOccurred = Signal(object)

    def __init__(self, registry=None):
        super().__init__()
        self.registry = registry if registry is not None else []
        self.program, self.args, self.env = None, None, None
        self.running = False
        self.killed = False
        self._out = b""

    # QProcess-Schnittstelle
    def setProcessEnvironment(self, env):
        self.env = {k: env.value(k) for k in env.keys()}  # noqa: SIM118  # QProcessEnvironment, kein dict

    def setStandardErrorFile(self, name):
        pass

    def start(self, program, args):
        self.program, self.args, self.running = program, list(args), True
        self.registry.append(self)

    def readAllStandardOutput(self):
        out, self._out = self._out, b""
        return out

    def state(self):
        return (QProcess.ProcessState.Running if self.running
                else QProcess.ProcessState.NotRunning)

    def kill(self):
        self.killed = True
        if self.running:
            self.exit(9)

    def waitForFinished(self, ms=0):
        return True

    # Test-Seite
    def write(self, text):
        self._out += text.encode()
        self.readyReadStandardOutput.emit()

    def exit(self, code=0, output=""):
        if output:
            self._out += output.encode()
        self.running = False
        self.finished.emit(code, 0)
