"""Start: ``python -m neondeck`` (Dienst), ``… --config`` (Einstellungen als eigener
Prozess) bzw. ``… ctl …`` (Befehlszeile)."""
from __future__ import annotations

import sys


def run(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["ctl"]:  # CLI: ohne GUI, Tray und Geraet
        from .cli import main as cli_main
        return cli_main(argv[1:])
    if "--config" in argv:  # Editor: eigener Prozess, nur ueber die JSON-API
        from .editor import main as editor_main
        return editor_main.run(argv)
    from .service.app import main
    return main(argv)


if __name__ == "__main__":
    raise SystemExit(run())
