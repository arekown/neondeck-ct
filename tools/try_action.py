"""Probe: eine Aktion mit echter Tastatur (uinput) ausfuehren (nur am echten System).

/usr/bin/python3 tools/try_action.py '{"type": "text", "text": "Grüße @ 3€"}'
/usr/bin/python3 tools/try_action.py '{"type": "hotkey", "keys": "KEY_LEFTCTRL+KEY_A"}'
/usr/bin/python3 tools/try_action.py --steps -3 '{"type": "adjust_hotkey", "left": "KEY_LEFT", "right": "KEY_RIGHT"}'

Wartet 3 s (Zeit zum Fokussieren des Zielfensters), fuehrt die Aktion aus und druckt
das Ergebnis. Aktionen mit Loslassen (hold_key) werden nach --hold Sekunden losgelassen.
"""
import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from neondeck.actions import ActionContext, execute, registry
from neondeck.actions.keyboard import Keyboard


def main() -> int:
    ap = argparse.ArgumentParser(description="Aktion mit echter Tastatur ausprobieren")
    ap.add_argument("action", help="Aktion als JSON")
    ap.add_argument("--steps", type=int, default=0, help="Drehschritte (Dreh-Aktionen)")
    ap.add_argument("--delay", type=float, default=3.0, help="Wartezeit vor dem Ausloesen")
    ap.add_argument("--hold", type=float, default=1.0, help="Haltedauer fuer hold_key")
    args = ap.parse_args()
    action = json.loads(args.action)

    kb = Keyboard()
    ctx = ActionContext(engine_call=lambda name, a: print("engine_call:", name, a), keyboard=kb)
    print(f"Ausloesen in {args.delay:g} s – Zielfenster fokussieren …", flush=True)
    time.sleep(args.delay)
    try:
        result = execute(action, ctx, steps=args.steps, pressed=True)
        print("Druecken:", result, flush=True)
        t = registry().get(action.get("type"))
        if t is not None and t.on_release:
            time.sleep(args.hold)
            print("Loslassen:", execute(action, ctx, steps=args.steps, pressed=False))
        time.sleep(0.2)  # let the compositor consume the last events before the device goes
    finally:
        kb.close()
    return 0 if result.ok else 1


if __name__ == "__main__":
    sys.exit(main())
