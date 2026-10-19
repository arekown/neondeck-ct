"""Editor-Seite „Diagnose“: alle Pruefungen aus ``diagnose`` mit gruen/rot und kopierbarem
Reparaturbefehl.

Die Pruefungen laufen im Dienst (API ``diag``: er kennt Geraet, Firmware, KWin-Skript,
Sitzungswaechter); ist er nicht erreichbar, prueft der Editor das Lokale selbst und meldet
den Rest als „Dienst nicht erreichbar“. Befehle werden nur angezeigt und kopiert, nie
ausgefuehrt.
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QStyle,
    QVBoxLayout,
    QWidget,
)

from ...core.i18n import N_, tr
from ...diagnose import Check, run_checks
from ...ui.common import Request

log = logging.getLogger(__name__)

OK_MARK, FAIL_MARK = "✔", "✘"
INTRO = N_("Prüft Sitzung, Gerät, Rechte und Hilfsprogramme. Rote Punkte haben, wo möglich, "
           "einen Befehl zum Kopieren – Neondeck CT führt ihn nie selbst aus.")


def checks_from_reply(reply: Any) -> list[Check] | None:
    """``diag``-Antwort -> Pruefungen (``None`` bei unerwarteter Antwort)."""
    if not isinstance(reply, dict) or not isinstance(reply.get("checks"), list):
        return None
    out = []
    for c in reply["checks"]:
        if not isinstance(c, dict) or not isinstance(c.get("id"), str):
            return None
        out.append(Check(c["id"], str(c.get("label", c["id"])), bool(c.get("ok")),
                         str(c.get("detail") or ""), c.get("fix") or None))
    return out


class DiagnosePage(QWidget):
    def __init__(self, request: Request | None = None, parent=None,
                 local: Callable[[], list[Check]] = run_checks) -> None:
        super().__init__(parent)
        self._request = request
        self._local = local
        self.checks: list[Check] = []
        self.service_reachable = False

        heading = QLabel(tr("Diagnose"))
        heading.setObjectName("heading")
        intro = QLabel(tr(INTRO))
        intro.setObjectName("hint")
        intro.setWordWrap(True)
        self.summary = QLabel()
        self.refresh_button = QPushButton(tr("Erneut prüfen"))
        self.refresh_button.clicked.connect(self.refresh)
        top = QHBoxLayout()
        top.addWidget(self.summary, 1)
        top.addWidget(self.refresh_button)

        self._rows = QWidget()
        self._grid = QGridLayout()
        self._grid.setColumnStretch(1, 1)
        self._grid.setVerticalSpacing(10)
        rows = QVBoxLayout(self._rows)
        rows.addLayout(self._grid)
        rows.addStretch(1)  # Zeilen oben zusammenhalten
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(self._rows)

        layout = QVBoxLayout(self)
        layout.addWidget(heading)
        layout.addWidget(intro)
        layout.addLayout(top)
        layout.addWidget(scroll, 1)

    def refresh(self) -> list[Check]:
        """Pruefen (Dienst, sonst lokal) und anzeigen."""
        checks = None
        if self._request is not None:
            try:
                checks = checks_from_reply(self._request("diag", {}))
            except Exception as e:  # noqa: BLE001 - Dienst weg: lokal pruefen
                log.info("Diagnose ohne Dienst: %s", e)
        self.service_reachable = checks is not None
        self.checks = checks if checks is not None else self._local()
        self._show()
        return self.checks

    def _show(self) -> None:
        while self._grid.count():
            item = self._grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        for row, check in enumerate(self.checks):
            mark = QLabel(OK_MARK if check.ok else FAIL_MARK)
            mark.setObjectName("ok" if check.ok else "error")
            self._grid.addWidget(mark, row, 0, Qt.AlignmentFlag.AlignTop)
            self._grid.addWidget(self._entry(check), row, 1, Qt.AlignmentFlag.AlignTop)
        bad = sum(not c.ok for c in self.checks)
        text = tr("{ok} von {total} Prüfungen in Ordnung", ok=len(self.checks) - bad,
                  total=len(self.checks))
        if not self.service_reachable:
            text += tr(" – Dienst nicht erreichbar, nur lokal geprüft")
        self.summary.setText(text)
        self.summary.setObjectName("ok" if bad == 0 else "error")
        self.summary.style().unpolish(self.summary)
        self.summary.style().polish(self.summary)

    @staticmethod
    def _entry(check: Check) -> QWidget:
        box = QWidget()
        layout = QVBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        label = QLabel(check.label)
        detail = QLabel(check.detail)
        detail.setObjectName("hint")
        detail.setWordWrap(True)
        layout.addWidget(label)
        layout.addWidget(detail)
        if check.fix:
            fix = QPlainTextEdit(check.fix)
            fix.setObjectName("fix")
            fix.setReadOnly(True)
            fix.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
            lines = check.fix.count("\n") + 1
            bar = fix.style().pixelMetric(QStyle.PixelMetric.PM_ScrollBarExtent)
            fix.setFixedHeight(fix.fontMetrics().lineSpacing() * min(lines, 8) + bar + 20)
            copy = QPushButton(tr("Befehl kopieren"))
            copy.clicked.connect(lambda _checked=False, text=check.fix:
                                 QApplication.clipboard().setText(text))
            row = QHBoxLayout()
            row.addWidget(fix, 1)
            row.addWidget(copy)
            layout.addLayout(row)
        return box
