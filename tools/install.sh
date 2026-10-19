#!/usr/bin/env bash
# Richtet Neondeck CT fuer den aktuellen Benutzer ein (ohne sudo):
# venv, Startskript ~/.local/bin/neondeck-ct, Eintrag im Anwendungsmenue.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON=/usr/bin/python3
BIN_DIR="$HOME/.local/bin"
APPS_DIR="$HOME/.local/share/applications"
LAUNCHER="$BIN_DIR/neondeck-ct"

if [ "$(id -u)" -eq 0 ]; then
    echo "Bitte als normaler Benutzer ausfuehren, nicht als root." >&2
    exit 1
fi

# venv mit System-Paketen (PySide6, pyserial, evdev, Pillow, numpy kommen vom System).
if [ ! -x "$REPO/.venv/bin/python" ]; then
    "$PYTHON" -m venv --system-site-packages "$REPO/.venv"
fi
# --no-deps: die Laufzeit-Abhaengigkeiten (pyproject) kommen vom System, pip holt keine
# eigenen (PySide6 aus PyPI haette kein Breeze); dazu die Entwicklerwerkzeuge (dev).
"$REPO/.venv/bin/pip" install --quiet --disable-pip-version-check --no-build-isolation --no-deps \
    -e "$REPO"
"$REPO/.venv/bin/pip" install --quiet --disable-pip-version-check pytest ruff

mkdir -p "$BIN_DIR" "$APPS_DIR"
cat > "$LAUNCHER" <<LAUNCH
#!/bin/sh
# Erzeugt von $REPO/tools/install.sh
PYTHONPATH="$REPO/src\${PYTHONPATH:+:\$PYTHONPATH}"
export PYTHONPATH
exec $PYTHON -m neondeck "\$@"
LAUNCH
chmod +x "$LAUNCHER"

sed "s|^Exec=.*|Exec=$LAUNCHER|" "$REPO/data/neondeck-ct.desktop" \
    > "$APPS_DIR/neondeck-ct.desktop"
# Namen vor der Umbenennung (loupedeck-linux): alten Starter und Menueeintrag entfernen
rm -f "$BIN_DIR/loupedeck-linux" "$APPS_DIR/loupedeck-linux.desktop"
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$APPS_DIR" || true
fi

echo "Installiert:"
echo "  Startskript:  $LAUNCHER"
echo "  Menueeintrag: $APPS_DIR/neondeck-ct.desktop"
echo "Grafiken fehlen? -> $PYTHON $REPO/tools/import_assets.py --source <Pfad zum entpackten Windows-Installer (siehe README)>"
echo "Start: neondeck-ct   (Autostart im Tray-Menue: \"Mit Anmeldung starten\")"
