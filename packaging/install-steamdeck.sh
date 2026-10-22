#!/usr/bin/env bash
# Installs RetroHome on a Steam Deck (or any Linux PC) and adds it to the application menu.
# Run in Desktop Mode: right-click this file > Run In Konsole (or: bash install-steamdeck.sh)
set -euo pipefail
SRC="$(cd "$(dirname "$0")" && pwd)"
DEST="$HOME/Applications/RetroHome"

echo "Installing RetroHome to $DEST ..."
mkdir -p "$HOME/Applications"
if [ "$SRC" != "$DEST" ]; then
    rm -rf "$DEST"
    cp -r "$SRC" "$DEST"
fi
chmod +x "$DEST/RetroHome"

ICON_DIR="$HOME/.local/share/icons/hicolor/512x512/apps"
mkdir -p "$ICON_DIR" "$HOME/.local/share/applications"
cp "$DEST/retrohome.png" "$ICON_DIR/retrohome.png"

cat > "$HOME/.local/share/applications/retrohome.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=RetroHome
Comment=Console-style home screen for your emulated games
Exec="$DEST/RetroHome"
Path=$DEST
Icon=retrohome
Terminal=false
Categories=Game;Emulator;
EOF
update-desktop-database "$HOME/.local/share/applications" >/dev/null 2>&1 || true

cat <<EOF

Installed!  RetroHome is now in your application menu (Games).

To use it in Game Mode:
  1. Open the Steam app (still in Desktop Mode).
  2. Games > Add a Non-Steam Game to My Library...
  3. Tick "RetroHome" and click "Add Selected Programs".
  4. Back in Game Mode, open it from your Library (Non-Steam).
     If the controls don't work, set the controller layout to "Gamepad".

EOF
