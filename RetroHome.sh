#!/usr/bin/env bash
# RetroHome launcher for Steam Deck / Linux.
# First run creates a private Python environment next to this script and installs pygame-ce.
# Add this file to Steam as a Non-Steam Game to use it in Game Mode.
set -e
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$DIR/.venv"
LOG="$DIR/retrohome.log"

if [ ! -x "$VENV/bin/python" ]; then
    echo "Setting up RetroHome (first run)…"
    python3 -m venv "$VENV" 2>/dev/null || {
        # SteamOS sometimes lacks ensurepip: bootstrap pip manually
        python3 -m venv --without-pip "$VENV"
        curl -sSL https://bootstrap.pypa.io/get-pip.py -o "$DIR/get-pip.py"
        "$VENV/bin/python" "$DIR/get-pip.py"
        rm -f "$DIR/get-pip.py"
    }
    "$VENV/bin/python" -m pip install --upgrade pip >/dev/null
    "$VENV/bin/python" -m pip install -r "$DIR/requirements.txt"
fi

exec "$VENV/bin/python" "$DIR/run.py" "$@" >"$LOG" 2>&1
