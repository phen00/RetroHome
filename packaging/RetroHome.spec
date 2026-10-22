# PyInstaller recipe for RetroHome release builds (Windows .exe and Linux / Steam Deck binary).
# Run through packaging/build_windows.bat or packaging/build_linux.sh rather than directly.
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

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

try:
    import py7zr  # noqa: F401
    hidden += collect_submodules("py7zr")
except ImportError:
    pass

a = Analysis(
    [str(ROOT / "run.py")],
    pathex=[str(ROOT)],
    datas=[(str(ROOT / "assets"), "assets")],
    hiddenimports=hidden,
    excludes=["tkinter", "unittest", "pydoc", "PyQt5", "PySide2", "PySide6"],
    noarchive=False,
)
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
