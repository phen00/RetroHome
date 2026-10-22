"""Self-update from GitHub Releases (release builds only).

1. check()    asks GitHub for the latest release and compares versions
2. download() fetches this platform's asset (Windows .zip / Linux .tar.gz) and unpacks it
3. Windows: apply() writes a small helper script that waits for RetroHome to exit, copies the new
              files over the install folder, and starts RetroHome again (a running .exe can't be
              replaced).
   Linux / Steam Deck: apply_in_place() swaps the files while RetroHome is still running (Linux
              allows replacing a running program's files), then exec_restart() turns this very
              process into the new version. No helper has to outlive RetroHome - Steam closes
              everything a game started when the game exits, which killed the helper before.

Settings, users and caches live outside the install folder (%APPDATA%, ~/.config), so they
are never touched by an update.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import time
import urllib.request
import zipfile
from pathlib import Path

from . import __version__, net
from .paths import FROZEN, IS_WINDOWS, cache_dir

REPO = os.environ.get("RETROHOME_UPDATE_REPO", "phen00/RetroHome")
API = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES_PAGE = f"https://github.com/{REPO}/releases/latest"


class UpdateError(Exception):
    pass


def parse_version(v: str) -> tuple:
    nums = re.findall(r"\d+", v or "")
    return tuple(int(n) for n in nums[:4]) or (0,)


def install_dir() -> Path:
    return Path(sys.executable).resolve().parent


def can_self_update() -> bool:
    """Only release builds update themselves, and only if their folder is writable."""
    if not FROZEN:
        return False
    d = install_dir()
    try:
        probe = d / ".rh-write-test"
        probe.write_text("x")
        probe.unlink()
        return True
    except OSError:
        return False


def asset_matches(name: str) -> bool:
    n = name.lower()
    if IS_WINDOWS:
        return "windows" in n and n.endswith(".zip")
    return ("linux" in n or "steamdeck" in n) and n.endswith((".tar.gz", ".tgz"))


def check(timeout=15):
    """-> None if up to date, else dict(version, notes, url, size, name, page)."""
    try:
        data = json.loads(net.get(API, timeout=timeout).decode("utf-8", "replace"))
    except (OSError, ValueError) as e:
        raise UpdateError(f"Couldn't check for updates ({e}).") from None
    tag = data.get("tag_name") or ""
    if data.get("draft") or data.get("prerelease"):
        return None
    if parse_version(tag) <= parse_version(__version__):
        return None
    asset = next((a for a in data.get("assets") or [] if asset_matches(a.get("name", ""))), None)
    if asset is None:
        return None     # builds are still being attached (a few minutes after publishing) - try later
    return dict(version=tag.lstrip("vV"), notes=(data.get("body") or "").strip(), page=data.get("html_url") or
                RELEASES_PAGE, url=asset and asset.get("browser_download_url"), size=asset and asset.get("size"),
                name=asset and asset.get("name"))


def download(info, progress=None, cancel=None) -> Path:
    """Download + unpack the update. Returns the folder holding the new RetroHome files."""
    if not info.get("url"):
        raise UpdateError("This release has no download for your system yet.")
    work = cache_dir() / "update"
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    archive = work / info["name"]
    req = urllib.request.Request(info["url"], headers={"User-Agent": net.UA, "Accept": "application/octet-stream"})
    try:
        with urllib.request.urlopen(req, timeout=60, context=net._ctx) as r, open(archive, "wb") as f:
            total = int(r.headers.get("Content-Length") or info.get("size") or 0)
            got = 0
            while True:
                if cancel and cancel():
                    raise UpdateError("Update cancelled.")
                chunk = r.read(1 << 20)
                if not chunk:
                    break
                f.write(chunk)
                got += len(chunk)
                if progress:
                    progress(got, total)
    except OSError as e:
        raise UpdateError(f"Download failed ({e}).") from None
    if info.get("size") and archive.stat().st_size != info["size"]:
        raise UpdateError("The download was incomplete - please try again.")
    out = work / "new"
    try:
        if archive.name.lower().endswith(".zip"):
            with zipfile.ZipFile(archive) as z:
                z.extractall(out)
        else:
            with tarfile.open(archive) as t:
                try:
                    t.extractall(out, filter="tar")
                except TypeError:
                    t.extractall(out)
    except (zipfile.BadZipFile, tarfile.TarError, OSError) as e:
        raise UpdateError(f"Couldn't unpack the update ({e}).") from None
    archive.unlink(missing_ok=True)
    exe = "RetroHome.exe" if IS_WINDOWS else "RetroHome"
    hits = [p.parent for p in out.rglob(exe) if p.is_file()]
    if not hits:
        raise UpdateError("The update didn't contain RetroHome - nothing was changed.")
    return min(hits, key=lambda p: len(p.parts))


def apply(new_dir: Path, target: Path = None, pid: int = None, relaunch: bool = True) -> Path:
    """Start the helper that swaps the files after this process exits. Returns the script path."""
    target = Path(target or install_dir())
    pid = pid or os.getpid()
    exe = target / ("RetroHome.exe" if IS_WINDOWS else "RetroHome")
    log = cache_dir() / "update" / "update.log"
    if IS_WINDOWS:
        script = cache_dir() / "update" / "apply_update.bat"
        script.write_text("\r\n".join([
            "@echo off",
            "chcp 65001 >nul",          # UTF-8, so user folders with accents work
            "setlocal",
            ":wait",
            f'tasklist /FI "PID eq {pid}" 2>nul | find "{pid}" >nul',
            "if not errorlevel 1 (",
            "  ping -n 2 127.0.0.1 >nul",   # ~1 s pause ('timeout' fails without a visible console)
            "  goto wait",
            ")",
            # copy everything over the old install (keeps any extra files the user added)
            f'robocopy "{new_dir}" "{target}" /E /R:5 /W:1 /NFL /NDL /NJH /NJS /NP > "{log}"',
            "if errorlevel 8 goto failed",
            f'rmdir /s /q "{new_dir.parent}"' if new_dir.parent.name == "new" else "",
            f'if "{int(relaunch)}"=="1" start "" "{exe}"',
            "exit /b 0",
            ":failed",
            f'echo Update failed - see {log} >> "{log}"',
            f'start "" "{exe}"',
            "exit /b 1",
        ]) + "\r\n", encoding="utf-8")
        # hidden console shared by the helper's commands (no flashing windows); own process group so it
        # keeps running after RetroHome exits
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP",
                                                                              0x200)
        subprocess.Popen(["cmd", "/c", str(script)], creationflags=flags, close_fds=True,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        script = cache_dir() / "update" / "apply_update.sh"
        script.write_text("\n".join([
            "#!/bin/sh",
            f"while kill -0 {pid} 2>/dev/null; do sleep 0.5; done",
            f'cp -a "{new_dir}/." "{target}/" > "{log}" 2>&1 || {{ echo "update failed" >> "{log}"; }}',
            f'chmod +x "{exe}" 2>/dev/null',
            f'rm -rf "{new_dir.parent}"' if new_dir.parent.name == "new" else "",
            f'[ "{int(relaunch)}" = "1" ] && cd "{target}" && nohup "{exe}" >/dev/null 2>&1 &',
            "exit 0",
        ]) + "\n", encoding="utf-8")
        script.chmod(0o755)
        subprocess.Popen(["/bin/sh", str(script)], start_new_session=True, close_fds=True,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return script


RECHECK_EVERY = 6 * 3600     # while RetroHome stays open


def apply_in_place(new_dir: Path, target: Path = None) -> Path:
    """Linux: copy the new version over the install folder now. Every file is first written next to
    its final name, then all are renamed into place, so a failed copy (disk full...) changes nothing.
    Returns the new executable."""
    new_dir, target = Path(new_dir), Path(target or install_dir())
    staged = []
    try:
        for src in sorted(new_dir.rglob("*")):
            rel = src.relative_to(new_dir)
            dest = target / rel
            if src.is_dir() and not src.is_symlink():
                dest.mkdir(parents=True, exist_ok=True)
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            tmp = dest.with_name(dest.name + ".rh-new")
            if tmp.is_symlink() or tmp.exists():
                tmp.unlink()
            if src.is_symlink():
                os.symlink(os.readlink(src), tmp)
            else:
                shutil.copy2(src, tmp)
            staged.append((tmp, dest))
    except OSError as e:
        for tmp, _ in staged:
            try:
                tmp.unlink()
            except OSError:
                pass
        raise UpdateError(f"Couldn't copy the update ({e}) - nothing was changed.") from None
    for tmp, dest in staged:
        if dest.is_dir() and not dest.is_symlink():
            shutil.rmtree(dest)
        os.replace(tmp, dest)       # atomic; the running program keeps its old copy until it restarts
    exe = target / "RetroHome"
    try:
        exe.chmod(exe.stat().st_mode | 0o111)
    except OSError:
        pass
    if new_dir.parent.name == "new":
        shutil.rmtree(new_dir.parent.parent / "new", ignore_errors=True)
    return exe


def exec_restart(exe: Path, args=()):
    """Replace this process with the freshly installed RetroHome (same process, so Steam keeps
    tracking it). PyInstaller-specific environment is reset so the new copy starts cleanly."""
    env = dict(os.environ)
    env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    for k in list(env):
        if k.startswith("_PYI_") or k == "_MEIPASS2":
            env.pop(k, None)
    if "LD_LIBRARY_PATH_ORIG" in env:
        env["LD_LIBRARY_PATH"] = env.pop("LD_LIBRARY_PATH_ORIG")
    os.chdir(str(Path(exe).parent))
    os.execve(str(exe), [str(exe), *args], env)


def should_auto_check(config, at_launch=True) -> bool:
    """Every launch checks (one small request); a long-running session checks again every 6 hours."""
    if not config["auto_update_check"]:
        return False
    if at_launch:
        return True
    last = float(config.data.get("update_checked_at") or 0)
    return time.time() - last > RECHECK_EVERY
