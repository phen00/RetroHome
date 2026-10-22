"""Unpack a downloaded game and file it into the right roms/<system> folder.

Archives: .zip (built in), .7z (py7zr, or 7-Zip), .rar (7-Zip, unrar, or bsdtar/tar),
.tar/.tar.gz (built in). Plain game files are moved as they are.
"""
import os
import re
import shutil
import subprocess
import tarfile
import zipfile
from pathlib import Path

from .paths import IS_WINDOWS
from .scanner import JUNK_EXT, _game_dir_target, disc_info
from .systems import BY_FOLDER, get_system

ARCHIVE_EXT = (".zip", ".7z", ".rar", ".tar", ".gz", ".tgz")
PLAYLIST_EXT = (".cue", ".gdi", ".m3u", ".ccd", ".mds")


class InstallError(Exception):
    pass


# ---------------------------------------------------------------- console -> folder
def folders_for_console(ra_console_id: int) -> list:
    return [f for f, s in BY_FOLDER.items() if s.ra == ra_console_id]


def folder_for_console(ra_console_id: int, rom_dir: Path):
    """Best existing roms sub-folder for a RetroAchievements console (EmuDeck naming)."""
    cands = folders_for_console(ra_console_id)
    if not cands:
        return None
    best, best_n = None, -1
    for f in cands:
        d = Path(rom_dir) / f
        if d.is_dir():
            try:
                n = sum(1 for _ in os.scandir(d))
            except OSError:
                n = 0
            if n > best_n:
                best, best_n = f, n
    return best or cands[0]


# ---------------------------------------------------------------- extraction
def _tool(*names):
    for n in names:
        w = shutil.which(n)
        if w:
            return w
    if IS_WINDOWS:
        for base in (os.environ.get("ProgramFiles", r"C:\Program Files"),
                     os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")):
            for rel in (r"7-Zip\7z.exe", r"WinRAR\UnRAR.exe"):
                p = Path(base) / rel
                if p.exists():
                    return str(p)
    return None


def _run(cmd):
    kw = {"creationflags": 0x08000000} if IS_WINDOWS else {}   # no console window
    r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, **kw)
    if r.returncode != 0:
        raise InstallError(r.stdout.decode(errors="replace").strip().splitlines()[-1:] or ["extract failed"])


def _safe_members(dest: Path):
    dest = dest.resolve()
    for p in dest.rglob("*"):
        if not str(p.resolve()).startswith(str(dest)):
            raise InstallError("Archive tried to write outside its folder - refused.")


def extract(archive: Path, dest: Path):
    dest.mkdir(parents=True, exist_ok=True)
    name = archive.name.lower()
    try:
        if name.endswith(".zip"):
            with zipfile.ZipFile(archive) as z:
                for m in z.infolist():
                    target = (dest / m.filename).resolve()
                    if not str(target).startswith(str(dest.resolve())):
                        raise InstallError("Archive contains unsafe paths - refused.")
                z.extractall(dest)
        elif name.endswith((".tar", ".tar.gz", ".tgz")):
            with tarfile.open(archive) as t:
                try:
                    t.extractall(dest, filter="data")
                except TypeError:  # Python < 3.12
                    t.extractall(dest)
        elif name.endswith(".7z"):
            try:
                import py7zr
                with py7zr.SevenZipFile(archive) as z:
                    z.extractall(dest)
            except ImportError:
                tool = _tool("7z", "7za", "7zz")
                bsdtar = _tool("bsdtar") or _tool("tar")   # Windows 10/11 + SteamOS tar is libarchive
                if tool:
                    _run([tool, "x", "-y", f"-o{dest}", str(archive)])
                elif bsdtar:
                    _run([bsdtar, "-xf", str(archive), "-C", str(dest)])
                else:
                    raise InstallError("Can't open .7z files: install 7-Zip.") from None
        elif name.endswith(".rar"):
            seven = _tool("7z", "7zz")
            unrar = _tool("unrar", "UnRAR.exe")
            bsdtar = _tool("bsdtar") or (_tool("tar") if IS_WINDOWS else None)
            if seven:
                _run([seven, "x", "-y", f"-o{dest}", str(archive)])
            elif unrar:
                _run([unrar, "x", "-o+", str(archive), str(dest) + os.sep])
            elif bsdtar:
                _run([bsdtar, "-xf", str(archive), "-C", str(dest)])
            else:
                raise InstallError("Can't open .rar files: install 7-Zip (Windows) or unrar.")
        else:
            raise InstallError(f"Unsupported archive: {archive.name}")
    except (zipfile.BadZipFile, tarfile.TarError, OSError) as e:
        raise InstallError(f"Couldn't extract {archive.name}: {e}") from None
    _safe_members(dest)


# ---------------------------------------------------------------- placement
def _unique(target: Path, src: Path) -> Path:
    if not target.exists():
        return target
    try:
        if src.is_file() and target.is_file() and src.stat().st_size == target.stat().st_size:
            return None   # same file already installed
    except OSError:
        pass
    stem, suf = target.stem, target.suffix
    for i in range(1, 100):
        cand = target.with_name(f"{stem} ({i}){suf}")
        if not cand.exists():
            return cand
    raise InstallError(f"Too many copies of {target.name}")


def _move(src: Path, target: Path, installed: list):
    target = _unique(target, src)
    if target is None:
        installed.append(("exists", src.name))
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(target))
    installed.append(("installed", str(target)))


def _part_number(name: str):
    m = re.search(r"\.part(\d+)\.rar$", name, re.I)
    return int(m.group(1)) if m else None


def install(download: Path, rom_dir: Path, folder: str) -> dict:
    """Extract/move a finished download into roms/<folder>. Returns a summary dict."""
    download = Path(download)
    system = get_system(folder)
    dest_root = Path(rom_dir) / folder
    dest_root.mkdir(parents=True, exist_ok=True)
    installed = []
    name = download.name.lower()
    part = _part_number(name)
    if part and part > 1:
        return {"status": "skipped", "message": f"{download.name}: extracted with part 1", "files": []}

    if name.endswith(ARCHIVE_EXT):
        staging = Path(rom_dir) / ".rh-incoming" / re.sub(r"[^\w.-]+", "_", download.stem)[:80]
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
        try:
            extract(download, staging)
            _place_tree(staging, dest_root, system, download, installed)
        finally:
            shutil.rmtree(staging, ignore_errors=True)
            try:
                staging.parent.rmdir()
            except OSError:
                pass
    else:
        ext = download.suffix.lower()
        if system.exts is not None and ext not in system.exts:
            raise InstallError(f"{download.name} isn't a {system.name} game file.")
        _move(download, dest_root / download.name, installed)

    new = [p for kind, p in installed if kind == "installed"]
    if not installed:
        raise InstallError(f"No {system.name} game files were found in {download.name}.")
    if new and name.endswith(ARCHIVE_EXT):
        try:
            download.unlink()   # archive no longer needed once unpacked
        except OSError:
            pass
    return {"status": "ok", "files": new,
            "message": (f"Added {len(new)} file(s) to {folder}" if new else f"Already in {folder}")}


def _is_game_file(p: Path, system) -> bool:
    ext = p.suffix.lower()
    if ext in JUNK_EXT or p.name.lower() in ("systems.txt",):
        return False
    return system.exts is None or ext in system.exts or ext in PLAYLIST_EXT or ext in (".bin", ".img", ".iso")


def _place_tree(staging: Path, dest_root: Path, system, download: Path, installed: list):
    # unwrap a single top-level folder ("Game (USA)/Game (USA).cue")
    root = staging
    while True:
        kids = [k for k in root.iterdir() if not k.name.startswith(".") and k.name != "__MACOSX"]
        if len(kids) == 1 and kids[0].is_dir() and _game_dir_target(kids[0]) is None:
            root = kids[0]
            continue
        break
    # folder-style games (PS3, Wii U) move whole
    for d in [k for k in root.iterdir() if k.is_dir()]:
        if _game_dir_target(d) is not None:
            _move(d, dest_root / d.name, installed)
    if _game_dir_target(root) is not None and root != staging:
        _move(root, dest_root / root.name, installed)
        return
    files = [p for p in root.rglob("*") if p.is_file() and _is_game_file(p, system)]
    playlists = [p for p in files if p.suffix.lower() in PLAYLIST_EXT]
    if playlists:
        # disc images reference their tracks by name: keep them together in one sub-folder
        base = disc_info(download.stem.split(".part")[0])[0]   # all discs of a game share a folder
        sub = dest_root / re.sub(r'[<>:"/\\|?*]', "_", base)
        for p in files:
            _move(p, sub / p.relative_to(root), installed)
        return
    keep = [p for p in files if system.exts is None or p.suffix.lower() in system.exts]
    for p in keep:
        _move(p, dest_root / p.name, installed)
