# PyInstaller recipe for RetroHome release builds (Windows .exe and Linux / Steam Deck binary).
# Run through packaging/build_windows.bat or packaging/build_linux.sh rather than directly.
import os
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = Path(SPECPATH).parent          # noqa: F821  (SPECPATH is provided by PyInstaller)
IS_WIN = sys.platform.startswith("win")

hidden = collect_submodules("retrohome", filter=lambda name: name != "retrohome.browser")
hidden += ["pygame._sdl2", "pygame._sdl2.controller", "pygame._sdl2.video"]

try:  # the built-in browser is included whenever PyQt6-WebEngine is installed in the build env
    import PyQt6.QtWebEngineWidgets  # noqa: F401
    hidden += ["retrohome.browser", "PyQt6.QtWebEngineWidgets", "PyQt6.QtWebEngineCore", "PyQt6.QtTest",
               "PyQt6.QtGui", "PyQt6.QtWidgets", "PyQt6.QtCore"]
    print(">>> Building WITH the built-in browser (PyQt6-WebEngine found)")
except ImportError:
    print(">>> Building WITHOUT the built-in browser (PyQt6-WebEngine not installed)")

# trusted certificates for HTTPS (the Steam Deck has none where the bundled OpenSSL looks)
extra_datas = collect_data_files("certifi")
hidden += ["certifi"]

try:
    import py7zr  # noqa: F401
    hidden += collect_submodules("py7zr")
except ImportError:
    pass

a = Analysis(
    [str(ROOT / "run.py")],
    pathex=[str(ROOT)],
    datas=[(str(ROOT / "assets"), "assets")] + extra_datas,
    hiddenimports=hidden,
    excludes=["tkinter", "unittest", "pydoc", "PyQt5", "PySide2", "PySide6"],
    noarchive=False,
)
if not IS_WIN:
    # Don't ship the build machine's graphics stack / C++ runtime: on SteamOS the Mesa drivers loaded
    # by the browser's GPU process need the system's own (newer) copies, and the old ones made it
    # abort on start (exit code -6). Every Linux desktop and SteamOS has these libraries.
    SYSTEM_LIBS = ("libstdc++.so", "libgcc_s.so", "libgbm.so", "libdrm", "libEGL", "libGL.", "libGLX",
                   "libGLdispatch", "libOpenGL", "libvulkan", "libfontconfig.so", "libfreetype.so",
                   "libX11.so", "libX11-xcb.so", "libxcb.so", "libwayland-", "libdbus-1.so", "libglib-2.0.so",
                   "libgobject-2.0.so", "libgio-2.0.so", "libgmodule-2.0.so", "libz.so")
    before = len(a.binaries)
    a.binaries = [b for b in a.binaries if not os.path.basename(b[0]).startswith(SYSTEM_LIBS)]
    print(f">>> Left out {before - len(a.binaries)} system libraries (use the system's own)")

pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="RetroHome",
    console=False,
    icon=str(ROOT / "assets" / ("icon.ico" if IS_WIN else "icon.png")),
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="RetroHome", upx=False)
