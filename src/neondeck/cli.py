"""Befehlszeile ``neondeck-ct ctl …`` – steuert den laufenden Dienst ueber die JSON-API.

Ausgabe: Ergebnis als JSON (stdout) bzw. Fehlertext (stderr) mit Exit-Code 1. Die CLI
startet den Dienst nicht selbst und braucht kein Qt (blockierender Client ``api.blocking``).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, TextIO

from .api.blocking import BlockingClient
from .api.protocol import CONNECT_TIMEOUT_S, ApiError, format_ref, parse_ref, ref_help
from .core import i18n
from .core.errors import LoupedeckError
from .core.i18n import N_, tr
from .core.settings import Settings

CALL_TIMEOUT_S = 5.0
NOT_RUNNING = N_("Neondeck CT läuft nicht (Dienst nicht erreichbar)")


class _Usage(LoupedeckError):
    pass


class _Parser(argparse.ArgumentParser):
    def error(self, message: str):  # statt sys.exit(2): Exit-Code 1 wie jeder Fehler
        raise _Usage(message)


def _parser() -> _Parser:
    p = _Parser(prog="neondeck-ct ctl",
                description=tr("Laufendes Neondeck CT steuern. Bedienelemente: {refs} "
                               "(Index ab 0).", refs=ref_help()))
    # fuer Tests; ohne Angabe die Adresse des Dienstes (protocol.socket_path)
    p.add_argument("--server", default=None, help=argparse.SUPPRESS)
    sub = p.add_subparsers(dest="cmd", required=True, metavar=tr("Befehl"))
    sub.add_parser("status", help=tr("Zustand als JSON"))
    pg = sub.add_parser("page", help=tr("Seite wechseln: next, prev oder Nummer (ab 0)"))
    pg.add_argument("target")
    sub.add_parser("workspace", help=tr("Arbeitsbereich (Name oder Kennung)")).add_argument("name")
    sub.add_parser("profile", help=tr("Profil aktivieren (Name oder Kennung)")).add_argument("name")
    sub.add_parser("press", help=tr("Taste auslösen, z. B. touch:3")).add_argument("ref")
    st = sub.add_parser("state", help=tr("Zustand einer Taste setzen"))
    st.add_argument("ref")
    st.add_argument("n", type=int)
    sv = sub.add_parser("screensaver", help=tr("Bildschirmschoner jetzt starten (Vorschau)"))
    sv.add_argument("name", nargs="?", default=None,
                    help=tr("cockpit, synthwave, matrix, warp, aurora oder auto"))
    im = sub.add_parser("image", help=tr("Tastenbild bis zum Neustart ersetzen"))
    im.add_argument("ref")
    im.add_argument("path")
    return p


def _prepare(args: argparse.Namespace) -> None:
    """Angaben pruefen und normalisieren, bevor eine Verbindung aufgebaut wird."""
    if getattr(args, "ref", None) is not None:
        args.ref = format_ref(parse_ref(args.ref))  # ValueError mit Hinweis
    if args.cmd == "page" and args.target not in ("next", "prev"):
        try:
            args.target = int(args.target)
        except ValueError:
            raise ValueError(tr("Seite {target!r}: next, prev oder Nummer (ab 0)",
                               target=args.target)) from None
    if args.cmd == "image":
        args.path = str(Path(args.path).expanduser().absolute())  # der Dienst hat ein anderes cwd


def _resolve(items: list[dict], wanted: str, what: str) -> str:
    """Kennung zu ``wanted``: exakte Kennung, sonst eindeutiger Name (Gross/klein egal)."""
    if any(x.get("id") == wanted for x in items):
        return wanted
    hits = [x["id"] for x in items if str(x.get("name", "")).casefold() == wanted.casefold()]
    if len(hits) == 1:
        return hits[0]
    if hits:
        raise ApiError("cli.ambiguous", N_("{what} {name!r} ist mehrdeutig: {hits}"),
                       {"what": tr(what), "name": wanted, "hits": ", ".join(hits)})
    raise ApiError("cli.not_found", N_("{what} {name!r} gibt es nicht"),
                   {"what": tr(what), "name": wanted})


def _run(args: argparse.Namespace, client: BlockingClient) -> Any:
    def call(method: str, params: dict | None = None) -> Any:
        return client.call(method, params or {}, timeout=CALL_TIMEOUT_S)

    if args.cmd == "status":
        return call("status")
    if args.cmd == "page":
        return call("page", {"dir": args.target} if isinstance(args.target, str)
                    else {"index": args.target})
    if args.cmd == "workspace":
        ws = _resolve(call("view.get").get("workspaces", []), args.name, N_("Arbeitsbereich"))
        return call("view.set", {"workspace": ws})
    if args.cmd == "profile":
        return call("profile.activate", {"id": _resolve(call("profile.list"), args.name,
                                                         N_("Profil"))})
    if args.cmd == "press":
        return call("trigger", {"ref": args.ref, "which": "tap"})
    if args.cmd == "state":
        return call("state.set", {"ref": args.ref, "n": args.n})
    if args.cmd == "screensaver":
        return call("screensaver.start", {"name": args.name} if args.name else {})
    if args.cmd == "image":
        return call("image.set", {"ref": args.ref, "path": args.path})
    raise ApiError("cli.unknown_command", N_("Unbekannter Befehl {name!r}"),
                   {"name": args.cmd})  # argparse laesst nichts anderes durch


def main(argv: list[str] | None = None, *, out: TextIO | None = None,
         err: TextIO | None = None) -> int:
    out = out or sys.stdout
    err = err or sys.stderr
    i18n.set_language(Settings.load().language)  # Fehler des Dienstes in dieser Sprache
    parser = _parser()
    try:
        args = parser.parse_args(argv)
        _prepare(args)
    except _Usage as e:
        print(tr("Aufruf falsch: {error}", error=e) + "\n" + parser.format_usage(), file=err, end="")
        return 1
    except ValueError as e:
        print(tr("Fehler: {error}", error=e), file=err)
        return 1
    client = BlockingClient(args.server)
    try:
        if not client.connect(CONNECT_TIMEOUT_S):
            print(tr(NOT_RUNNING), file=err)
            return 1
        result = _run(args, client)
    except Exception as e:  # noqa: BLE001 - ApiError und Unerwartetes: Meldung statt Traceback
        print(tr("Fehler: {error}", error=e), file=err)
        return 1
    finally:
        client.close()
    print(json.dumps(result, ensure_ascii=False, indent=2), file=out)
    return 0
