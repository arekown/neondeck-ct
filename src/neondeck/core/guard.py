"""Aufrufen und Fehler loggen: Ausnahmen aus Rueckrufen nie bis in die Qt-Ereignisschleife.

Ein Ort fuer das Muster „try: fn() except Exception: log.exception(...)“, das Dienst, Editor
und API an vielen Stellen brauchen (Rueckrufe, Zuhoerer, Aufrufe aus anderen Threads).
"""
from __future__ import annotations

import logging
from collections.abc import Callable

log = logging.getLogger(__name__)


def call_logged(fn: Callable[..., object], *args: object, what: str = "Aufruf fehlgeschlagen",
                what_args: tuple = (), logger: logging.Logger = log) -> bool:
    """``fn(*args)``; jede Ausnahme wird mit ``logger.exception(what, *what_args)`` geloggt und
    nie weitergereicht. True bei Erfolg."""
    try:
        fn(*args)
    except Exception:
        logger.exception(what, *what_args)
        return False
    return True


def guarded(logger: logging.Logger = log,
            what: str = "Aufruf %s fehlgeschlagen") -> Callable[..., None]:
    """Schutzfunktion ``guard(fn, *args)`` fuer Rueckrufe: ruft ``call_logged`` mit dem Namen
    von ``fn`` als ``%s`` in ``what``."""
    def guard(fn: Callable[..., object], *args: object) -> None:
        call_logged(fn, *args, what=what, what_args=(getattr(fn, "__name__", fn),),
                    logger=logger)
    return guard
