"""Where RetroHome keeps its settings and caches."""
import os
import sys
from pathlib import Path

IS_WINDOWS = sys.platform.startswith("win")
IS_MAC = sys.platform == "darwin"
IS_LINUX = not IS_WINDOWS and not IS_MAC
FROZEN = bool(getattr(sys, "frozen", False))   # running from a PyInstaller release build


def resource(*parts) -> Path:
    """A bundled file (assets/...), both from source and from a release build."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base.joinpath(*parts)


def config_dir() -> Path:
    if IS_WINDOWS:
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        d = base / "RetroHome"
    elif IS_MAC:
        d = Path.home() / "Library" / "Application Support" / "RetroHome"
    else:
        d = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "retrohome"
    d.mkdir(parents=True, exist_ok=True)
    return d


def cache_dir() -> Path:
    if IS_WINDOWS:
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        d = base / "RetroHome" / "cache"
    elif IS_MAC:
        d = Path.home() / "Library" / "Caches" / "RetroHome"
    else:
        d = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "retrohome"
    d.mkdir(parents=True, exist_ok=True)
    return d


def is_steam_deck() -> bool:
    if not IS_LINUX:
        return False
    try:
        with open("/sys/devices/virtual/dmi/id/board_vendor") as f:
            vendor = f.read().strip().lower()
        with open("/sys/devices/virtual/dmi/id/product_name") as f:
            product = f.read().strip().lower()
        return "valve" in vendor and product in ("jupiter", "galileo")
    except OSError:
        return os.environ.get("SteamDeck") == "1"


def default_rom_dir_candidates() -> list:
    """Likely EmuDeck ROM folders, existing ones first."""
    cands = []
    home = Path.home()
    if IS_WINDOWS:
        import string
        for letter in string.ascii_uppercase:
            root = Path(f"{letter}:/")
            try:
                if root.exists():
                    cands.append(root / "Emulation" / "roms")
            except OSError:
                pass
        cands.append(home / "Emulation" / "roms")
    else:
        cands.append(home / "Emulation" / "roms")
        for media_root in (Path("/run/media"), Path("/media"), Path("/mnt")):
            try:
                for p in media_root.iterdir():
                    cands.append(p / "Emulation" / "roms")
                    try:
                        for q in p.iterdir():
                            cands.append(q / "Emulation" / "roms")
                    except OSError:
                        pass
            except OSError:
                pass
    existing, seen = [], set()
    for c in cands:
        try:
            if c.is_dir() and str(c) not in seen:
                existing.append(c)
                seen.add(str(c))
        except OSError:
            pass
    return existing


def default_new_rom_dir() -> Path:
    if IS_WINDOWS:
        return Path(os.environ.get("USERPROFILE", str(Path.home()))) / "Emulation" / "roms"
    return Path.home() / "Emulation" / "roms"
