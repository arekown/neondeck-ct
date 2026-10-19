"""API-Methoden ``profile.*`` und ``versions.*``: Profile lesen, speichern, wechseln, Versionen."""
from __future__ import annotations

import logging
from collections.abc import Callable, Iterator
from contextlib import contextmanager

from ...core.i18n import N_, tr
from ...core.values import join_errors
from ...profile.ids import new_profile_id
from ...profile.importers.lp5 import remove_unused_imports
from ...profile.model import Profile, empty_profile, validate_profile_json
from ...profile.store import DEFAULT_ID
from ..contracts import ServiceFacade
from ..params import Obj, ProfileId, Text, api_method
from ..protocol import ERR_SHOW_FAILED, SHOW_FAILED, ApiError
from . import Handlers

log = logging.getLogger(__name__)

MAX_REPORTED_ERRORS = 5
VERSION_NAME = Text(missing=N_("name fehlt"))


@contextmanager
def showing(pid: str, text: str = SHOW_FAILED) -> Iterator[None]:
    """Ein Profil anzeigen: laesst es sich nicht zeichnen, wird das zur Fehlerantwort
    ``ERR_SHOW_FAILED`` (nie eine Ausnahme bis in die Ereignisschleife)."""
    try:
        yield
    except Exception as err:
        log.exception("API: Profil %s lässt sich nicht anzeigen", pid)
        raise ApiError(ERR_SHOW_FAILED, N_("{what}: {error}"),
                       {"id": pid, "what": tr(text), "error": str(err)}) from None


def profile_ids(facade: ServiceFacade) -> list[str]:
    """Gespeicherte Profile plus das aktive (auch wenn es noch nicht gespeichert ist)."""
    ids = facade.store.list()
    active = facade.engine.profile.id
    return ids if active in ids else sorted(ids + [active])


def require_known(facade: ServiceFacade, pid: str) -> str:
    if pid not in profile_ids(facade):
        # Quelltext mit Platzhaltern, Werte in params; uebersetzt wird im Client (N_ markiert)
        raise ApiError("profile.not_found", N_("Profil {id!r} gibt es nicht"), {"id": pid})
    return pid


def activate(facade: ServiceFacade, pid: str) -> None:
    """Profilwechsel ueber den Dienst; scheitert er, ist es eine Fehlerantwort."""
    with showing(pid):
        facade.switch_profile(pid)
    if facade.engine.profile.id != pid:
        raise ApiError("profile.load_failed", N_("Profil {id!r} konnte nicht geladen werden"),
                       {"id": pid})


def _version_error(err: Exception, pid: str, name: str, code: str, text: str) -> ApiError:
    """``text``: Quelltext (``N_``) mit ``{name}``; der Fehler der Platte haengt dran."""
    if isinstance(err, FileNotFoundError):
        return ApiError("version.not_found", N_("Version {name!r} von Profil {id!r} gibt es nicht"),
                        {"id": pid, "name": name})
    return ApiError(code, N_("{what}: {error}"),
                    {"id": pid, "name": name, "what": tr(text, name=name), "error": str(err)})


class ProfileHandlers(Handlers):
    """``emit(name, daten)`` meldet Profilaenderungen an alle Abonnenten."""

    def __init__(self, service: Callable[[], ServiceFacade],
                 emit: Callable[[str, dict], None]) -> None:
        super().__init__(service)
        self._emit = emit

    def _changed(self, pid: str) -> None:
        self._emit("profile.changed", {"id": pid, "active": self.engine.profile.id})

    def _known(self, pid: str) -> str:
        return require_known(self.facade, pid)

    @api_method("profile.list")
    def list(self) -> list[dict]:
        active = self.engine.profile
        out = []
        for pid in profile_ids(self.facade):
            if pid == active.id:
                name, ok = active.name, True
            else:
                try:
                    name, ok = self.store.load(pid).name, True
                except Exception:  # noqa: BLE001 - kaputte Datei: trotzdem auflisten
                    name, ok = pid, False
            out.append({"id": pid, "name": name or pid, "active": pid == active.id, "ok": ok})
        return out

    @api_method("profile.get", id=ProfileId())
    def get(self, id: str) -> dict:
        pid = self._known(id)
        if pid == self.engine.profile.id:
            return self.engine.profile.to_json()
        try:
            return self.store.load(pid).to_json()
        except Exception as e:  # noqa: BLE001 - jeder Lesefehler wird zu profile.unreadable
            raise ApiError("profile.unreadable", N_("Profil {id!r} nicht lesbar: {error}"),
                           {"id": pid, "error": str(e)}) from None

    @api_method("profile.put", profile=Obj(required=True,
                                           message=N_("profile muss ein JSON-Objekt sein")))
    def put(self, profile: dict) -> dict:
        errors = validate_profile_json(profile)  # vor allem anderen: nichts Halbes speichern
        if errors:
            raise ApiError("profile.invalid", N_("Profil ungültig: {errors}"),
                           {"errors": join_errors(errors, MAX_REPORTED_ERRORS, with_more=True)})
        try:
            new = Profile.from_json(profile)
        except Exception as e:  # noqa: BLE001 - sollte nach der Pruefung nicht vorkommen
            raise ApiError("profile.invalid", N_("Profil ungültig: {errors}"),
                           {"errors": str(e)}) from None
        self._show_then_save(new)
        self._changed(new.id)
        return {"id": new.id}

    def _show_then_save(self, profile: Profile) -> None:
        """Das aktive Profil erst anzeigen (Probe), dann speichern; scheitert das Speichern,
        zeigt die Engine wieder den Stand von der Platte."""
        engine = self.engine
        old = engine.profile if profile.id == engine.profile.id else None
        if old is not None:
            with showing(profile.id):  # bei Fehler bleibt das alte stehen
                engine.set_profile(profile, keep_view=True)
        try:
            self.store.save(profile)  # atomar, vorher Snapshot
        except Exception as err:  # noqa: BLE001 - jeder Speicherfehler: altes Profil zurueck
            if old is not None:
                engine.set_profile(old, keep_view=True)
            raise ApiError("profile.save_failed", N_("Speichern fehlgeschlagen: {error}"),
                           {"error": str(err)}) from None

    @api_method("profile.activate", id=ProfileId())
    def activate(self, id: str) -> dict:
        activate(self.facade, self._known(id))
        return {"id": id}

    @api_method("profile.create", name=Text(missing=N_("Name fehlt"), strip=True))
    def create(self, name: str) -> dict:
        profile = empty_profile(new_profile_id(name, set(profile_ids(self.facade))), name)
        try:
            self.store.save(profile)
        except OSError as e:
            raise ApiError("profile.save_failed", N_("Speichern fehlgeschlagen: {error}"),
                           {"error": str(e)}) from None
        self._changed(profile.id)
        return {"id": profile.id}

    @api_method("profile.delete", id=ProfileId())
    def delete(self, id: str) -> dict:
        pid = self._known(id)
        if len(profile_ids(self.facade)) <= 1:
            raise ApiError("profile.last", N_("Das letzte Profil kann nicht gelöscht werden"))
        if pid == self.engine.profile.id:  # nie das aktive Profil loeschen: erst wechseln
            self._leave(pid)
        try:
            self.store.delete(pid)
        except OSError as e:
            raise ApiError("profile.delete_failed", N_("Löschen fehlgeschlagen: {error}"),
                           {"error": str(e)}) from None
        try:
            remove_unused_imports(self.store)
        except Exception:
            log.exception("API: importierte Symbole nicht aufgeräumt")
        self._changed(pid)
        return {}

    def _leave(self, pid: str) -> None:
        """Vom aktiven Profil ``pid`` auf ein anderes gespeichertes wechseln."""
        others = [i for i in self.store.list() if i != pid]
        if not others:
            raise ApiError("profile.no_other", N_("Kein anderes gespeichertes Profil zum Wechseln"))
        target = DEFAULT_ID if DEFAULT_ID in others else others[0]
        with showing(target):
            self.facade.switch_profile(target)
        if self.engine.profile.id == pid:
            raise ApiError("profile.switch_failed",
                           N_("Wechsel auf ein anderes Profil fehlgeschlagen – {id!r} "
                              "wurde nicht gelöscht"), {"id": pid})

    @api_method("versions.list", id=ProfileId())
    def versions(self, id: str) -> list[dict]:
        return [{"name": v.name, "time": v.time, "size": v.size}
                for v in self.store.versions(id)]

    @api_method("versions.get", id=ProfileId(), name=VERSION_NAME)
    def version(self, id: str, name: str) -> dict:
        """Inhalt eines Snapshots (Vorschau im Versionen-Dialog)."""
        try:
            return self.store.version_json(id, name)
        except Exception as e:  # noqa: BLE001 - fehlender oder kaputter Snapshot
            raise _version_error(e, id, name, "version.unreadable",
                                 N_("Version {name!r} nicht lesbar")) from None

    @api_method("versions.restore", id=ProfileId(), name=VERSION_NAME)
    def restore(self, id: str, name: str) -> dict:
        profile = self._restored(id, name)
        if profile.id == self.engine.profile.id:
            with showing(id, N_("Wiederhergestellt, aber nicht anzeigbar")):
                self.engine.set_profile(profile, keep_view=True)
        self._changed(id)
        return {"id": id}

    def _restored(self, pid: str, name: str) -> Profile:
        try:
            errors = validate_profile_json(self.store.version_json(pid, name))
        except Exception as e:  # noqa: BLE001 - fehlender oder kaputter Snapshot
            raise _version_error(e, pid, name, "version.restore_failed",
                                 N_("Wiederherstellen fehlgeschlagen")) from None
        if errors:
            raise ApiError("version.invalid", N_("Version {name!r} ist ungültig: {errors}"),
                           {"id": pid, "name": name,
                            "errors": join_errors(errors, MAX_REPORTED_ERRORS)})
        try:
            return self.store.restore(pid, name)
        except Exception as e:  # noqa: BLE001 - kaputter Snapshot, Schreibfehler
            raise _version_error(e, pid, name, "version.restore_failed",
                                 N_("Wiederherstellen fehlgeschlagen")) from None
