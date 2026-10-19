"""Action registry; importing this package registers all action modules."""
from . import (  # noqa: F401 - Import registriert die Aktionen
    apps,
    audio,
    display,
    http,
    kde,
    kde_shortcuts,
    key_actions,
    macro,
    media,
    navigation,
    scroll,
    system,
    terminal,
)
from .base import ActionContext, Executor, Param, Result, execute, register, registry

__all__ = ["ActionContext", "Executor", "Param", "Result", "execute", "register", "registry"]
