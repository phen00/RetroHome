#!/usr/bin/env python3
"""Start RetroHome (also the entry point of the release builds)."""
import os
import sys

if not getattr(sys, "frozen", False):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _log_to_file():
    """Windowed release builds have no console: keep a log next to the settings."""
    if sys.stdout is not None and sys.stderr is not None:
        return
    from retrohome.paths import config_dir
    log = open(config_dir() / "retrohome.log", "a", encoding="utf-8", buffering=1)
    sys.stdout = sys.stdout or log
    sys.stderr = sys.stderr or log


def main():
    _log_to_file()
    if len(sys.argv) > 1 and sys.argv[1] == "--browser":
        # the built-in browser runs as a second copy of this program
        sys.argv = [sys.argv[0]] + sys.argv[2:]
        from retrohome.browser import main as browser_main
        browser_main()
        return
    try:
        import pygame  # noqa: F401
    except ImportError:
        print("RetroHome needs pygame-ce:  python -m pip install pygame-ce")
        sys.exit(1)
    from retrohome.ui.app import main as app_main
    app_main()


if __name__ == "__main__":
    main()
