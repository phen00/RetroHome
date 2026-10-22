#!/usr/bin/env bash
# Builds the Linux / Steam Deck release: dist/RetroHome/RetroHome plus a .tar.gz with an installer.
# Works on the Steam Deck itself (Desktop Mode, in Konsole) or any x86-64 Linux with Python 3.10-3.13.
set -euo pipefail
cd "$(dirname "$0")/.."

PY=""
for v in python3.12 python3.13 python3.11 python3.10 python3; do
    if command -v "$v" >/dev/null 2>&1; then PY="$v"; break; fi
done
[ -n "$PY" ] || { echo "Python 3 not found"; exit 1; }
echo "Using $($PY --version)"

rm -rf .build-venv
if ! $PY -m venv .build-venv 2>/dev/null; then
    # SteamOS's Python has no ensurepip: bootstrap pip by hand
    $PY -m venv --without-pip .build-venv
    curl -sSL https://bootstrap.pypa.io/get-pip.py -o .build-venv/get-pip.py
    .build-venv/bin/python .build-venv/get-pip.py
fi
VPY=.build-venv/bin/python
$VPY -m pip install --upgrade pip
$VPY -m pip install --only-binary :all: -r packaging/requirements-build.txt
$VPY -m pip install --only-binary :all: py7zr >/dev/null 2>&1 || true

VERSION=$($VPY -c "import retrohome; print(retrohome.__version__)")
echo "Building RetroHome $VERSION ..."
$VPY -m PyInstaller --noconfirm --clean --distpath dist --workpath build/pyinstaller packaging/RetroHome.spec

cp README.md packaging/RELEASE_NOTES.md dist/RetroHome/
cp packaging/install-steamdeck.sh dist/RetroHome/
cp assets/icon.png dist/RetroHome/retrohome.png
chmod +x dist/RetroHome/RetroHome dist/RetroHome/install-steamdeck.sh

NAME="RetroHome-$VERSION-Linux-SteamDeck-x86_64"
tar -C dist -czf "dist/$NAME.tar.gz" RetroHome
echo
echo "============================================================"
echo " Done!  dist/RetroHome/RetroHome"
echo "        dist/$NAME.tar.gz"
echo "============================================================"
