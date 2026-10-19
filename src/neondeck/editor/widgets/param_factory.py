"""Ein Eingabe-Widget je Aktionsparameter: gemeinsames Wert-Protokoll ``ParamWidget`` und die
Fabrik ``make_param_widget`` (statt einer ``isinstance``-Kette im Formular)."""
from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol

from PySide6.QtWidgets import QWidget

from ...actions.base import Param
from ...core.i18n import tr
from .action_meta import CHOICE_LABELS
from .key_capture import KeyCaptureEdit
from .nav_targets import NavTargets
from .param_widgets import (
    AppPicker,
    CheckParam,
    ChoiceParam,
    LineParam,
    MultiLineEdit,
    PathEdit,
    SpinParam,
    TerminalsEdit,
)
from .steps_edit import StepsEdit

MULTILINE_PARAMS = frozenset({("http", "headers"), ("http", "body")})
APP_PARAMS = frozenset({("app_focus", "app_id")})


class ParamWidget(Protocol):
    """Was das Aktionsformular von jeder Parameter-Eingabe braucht (``changed``: Signal)."""

    changed: Any

    def value(self) -> Any: ...
    def set_value(self, v) -> None: ...


def _choice(param: Param) -> ChoiceParam:
    return ChoiceParam([(c, tr(CHOICE_LABELS.get(c, str(c)))) for c in param.choices or []],
                       param.default)


def _multiline(param: Param) -> MultiLineEdit:
    w = MultiLineEdit()
    if param.default:
        w.set_value(param.default)
    return w


_BY_KIND: dict[str, Callable[[Param], QWidget]] = {
    "file": lambda p: PathEdit(directory=False),
    "dir": lambda p: PathEdit(directory=True),
    "bool": lambda p: CheckParam(p.default),
    "int": lambda p: SpinParam(p.default),
    "keys": lambda p: KeyCaptureEdit(),
    "choice": _choice,
    "terminals": lambda p: TerminalsEdit(),
}


def make_param_widget(action_type: str | None, param: Param, targets: NavTargets | None,
                      nested_form: Callable[[], QWidget]) -> QWidget:
    """Eingabe fuer ``param`` von ``action_type``: Auswahl aus ``targets`` (Arbeitsbereich,
    Profil, Ordnerseite), mehrzeilig, Anwendungsauswahl oder nach ``param.kind``;
    ``nested_form`` baut das Formular eines Makro-Schritts."""
    choices = targets.choices(action_type, param.name) if targets else None
    if choices is not None:
        return ChoiceParam([(value, label or value) for value, label in choices])
    if (action_type, param.name) in MULTILINE_PARAMS:
        return _multiline(param)
    if (action_type, param.name) in APP_PARAMS:
        return AppPicker(targets.catalog if targets else None)
    if param.kind == "steps":
        return StepsEdit(nested_form)
    return _BY_KIND.get(param.kind, lambda p: LineParam(p.default))(param)
