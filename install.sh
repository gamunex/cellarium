#!/bin/sh
# Installiert Cellarium für den aktuellen Nutzer (kein root nötig).
#   ./install.sh              installieren oder aktualisieren
#   ./install.sh --uninstall  wieder entfernen (Einstellungen in ~/.config/cellarium bleiben)
set -eu

DATA="${XDG_DATA_HOME:-$HOME/.local/share}"
DEST="$DATA/cellarium"
BIN="$HOME/.local/bin"
APPS="$DATA/applications"
ICONS="$DATA/icons/hicolor/scalable/apps"
SRC=$(cd "$(dirname "$0")" && pwd)

if [ "${1:-}" = "--uninstall" ]; then
    rm -rf "$DEST" "$BIN/cellarium" "$APPS/cellarium.desktop" "$ICONS/cellarium.svg"
    echo "Cellarium entfernt."
    exit 0
fi

command -v python3 >/dev/null || { echo "python3 fehlt." >&2; exit 1; }
python3 -c 'import sys; sys.exit(sys.version_info < (3, 10))' || { echo "Python 3.10 oder neuer nötig." >&2; exit 1; }

mkdir -p "$DEST" "$BIN" "$APPS" "$ICONS"
rm -rf "$DEST/cellarium"
cp -r "$SRC/cellarium" "$DEST/"
rm -f "$DEST/cellarium/web/demo.json"
find "$DEST" -name __pycache__ -prune -exec rm -rf {} +

cat > "$BIN/cellarium" <<SH
#!/bin/sh
PYTHONPATH="$DEST" exec python3 -m cellarium "\$@"
SH
chmod +x "$BIN/cellarium"

cp "$SRC/cellarium/web/icon.svg" "$ICONS/cellarium.svg"
cat > "$APPS/cellarium.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=Cellarium
GenericName=Wine-Prefix-Übersicht
Comment=Alle Wine- und Proton-Prefixe auf einen Blick
Exec=$BIN/cellarium
Icon=cellarium
Terminal=false
Categories=Utility;Game;
Keywords=wine;proton;prefix;lutris;steam;faugus;umu;
StartupWMClass=cellarium
DESKTOP
command -v update-desktop-database >/dev/null && update-desktop-database -q "$APPS" 2>/dev/null || true

echo "Cellarium installiert. Starten über das Startmenü oder mit: cellarium"
case ":$PATH:" in *":$BIN:"*) ;; *) echo "Hinweis: $BIN liegt nicht im PATH." ;; esac
