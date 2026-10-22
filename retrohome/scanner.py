"""Scan an EmuDeck-style roms folder into a list of games."""
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from .systems import ALL_FOLDERS, System, get_system

JUNK_EXT = {
    ".txt", ".xml", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".mp4", ".mkv", ".avi",
    ".pdf", ".nfo", ".srm", ".sav", ".state", ".db", ".ini", ".cfg", ".json", ".log", ".md",
    ".dat", ".sfv", ".md5", ".sha1", ".htm", ".html", ".url", ".ds_store", ".part", ".tmp",
    ".rtc", ".mcr", ".cht", ".ips", ".bps", ".ups", ".xdelta", ".sbi", ".ignore", ".pal",
}
SKIP_DIRS = {"media", "images", "videos", "manuals", "covers", "screenshots", "marquees",
             "snap", "snaps", "downloaded_media", "gamelists", "saves", "states", "bios",
             "systemsettings", "__macosx", "patches", "shaders", "updates", "dlc"}
SKIP_FILES = {"systems.txt", "metadata.txt", "gamelist.xml", "readme.txt"}

_TAG_RE = re.compile(r"\s*[\(\[][^\)\]]*[\)\]]")
_REGION_WORDS = ("usa", "europe", "japan", "world", "en", "fr", "de", "es", "it", "uk",
                 "australia", "korea", "brazil", "rev", "v1", "beta", "proto", "demo")


@dataclass
class Game:
    id: str                 # stable key: "<system>/<relative path>"
    system: System
    path: Path              # file to launch (or folder for dir-games)
    file_name: str          # base name without extension
    title: str              # clean display title
    tags: str = ""          # "(USA) (Rev 1)" etc.
    size: int = 0
    is_dir: bool = False
    alt_names: list = field(default_factory=list)   # e.g. name without "2239 - " release number
    discs: list = field(default_factory=list)       # [(label, Path)] for multi-disc games
    ra_game_id: int = 0     # filled in by RetroAchievements matcher
    ra_title: str = ""
    extra: dict = field(default_factory=dict)

    @property
    def display_title(self):
        return self.ra_title_clean or self.title

    @property
    def ra_title_clean(self):
        if not self.ra_title:
            return ""
        t = re.sub(r"~[^~]*~\s*", "", self.ra_title)
        return t.split(" | ")[0].strip()


_RELNUM_RE = re.compile(r"^(\d{4})\s*-\s+(\S.*)$")


def strip_release_number(name: str):
    """'2239 - Metal Gear Solid (Europe)' -> ('Metal Gear Solid (Europe)', certain?) or (None, False).

    Release-numbered sets (No-Intro/scene NDS, GBA, PSP...) prefix a 4-digit number. Numbers that
    look like years (1943 - The Battle of Midway) are ambiguous, so callers try both forms."""
    m = _RELNUM_RE.match(name)
    if not m:
        return None, False
    num = m.group(1)
    certain = num.startswith("0") or not 1900 <= int(num) <= 2099
    return m.group(2), certain


_DISC_RE = re.compile(r"\s*[\(\[]\s*(?:disc|disk|cd|dvd)\s*(\d+)(?:\s*of\s*\d+)?\s*[\)\]]", re.I)


def disc_info(name: str):
    """'Final Fantasy VII (USA) (Disc 2)' -> ('Final Fantasy VII (USA)', 2) or (name, None)."""
    m = _DISC_RE.search(name)
    if not m:
        return name, None
    return (name[:m.start()] + name[m.end():]).strip(), int(m.group(1))


def group_discs(games: list) -> list:
    """Merge 'X (Disc 1)', 'X (Disc 2)'... in the same folder into one game with a disc list."""
    groups, out = {}, []
    for g in games:
        base, n = disc_info(g.file_name)
        if n is None or g.is_dir:
            out.append(g)
            continue
        groups.setdefault((str(g.path.parent), base.lower(), g.path.suffix.lower()), []).append((n, g))
    for (_, _, _), members in groups.items():
        members.sort(key=lambda x: x[0])
        first = members[0][1]
        if len(members) > 1:
            first.discs = [(f"Disc {n}", g.path) for n, g in members]
            first.tags = _DISC_RE.sub("", first.tags).strip()
            first.size = sum(g.size for _, g in members)
        out.append(first)
    return out


def clean_title(name: str) -> tuple:
    """'Legend of Zelda, The - A Link (USA) [!]' -> ('The Legend of Zelda - A Link', '(USA) [!]')"""
    stripped, certain = strip_release_number(name)
    if stripped and certain:
        name = stripped
    tags = " ".join(m.group(0).strip() for m in _TAG_RE.finditer(name))
    t = _TAG_RE.sub("", name).strip()
    t = t.replace("_", " ")
    # "Name, The - Subtitle" / "Name, The"
    m = re.match(r"^(.*?),\s*(The|A|An|Le|La|Les|Der|Die|Das)(\s*[-:].*)?$", t, re.I)
    if m:
        t = f"{m.group(2)} {m.group(1)}{m.group(3) or ''}"
    t = re.sub(r"\s{2,}", " ", t).strip(" -")
    return (t or name), tags


def _game_dir_target(d: Path):
    """If d is a folder-style game (PS3 / Wii U / .ps3 dir), return the path to launch."""
    try:
        names = {p.name.lower(): p for p in d.iterdir()}
    except OSError:
        return None
    if d.suffix.lower() in (".ps3", ".ps3dir") or "ps3_game" in names:
        return d
    if "code" in names and names["code"].is_dir():  # Wii U loadiine format
        try:
            for f in names["code"].iterdir():
                if f.suffix.lower() == ".rpx":
                    return f
        except OSError:
            pass
    if d.suffix.lower() in (".scummvm", ".dosz"):
        return d
    return None


def _referenced_files(path: Path) -> set:
    """Files referenced by a .cue/.m3u/.gdi so we can hide them from the list."""
    refs = set()
    ext = path.suffix.lower()
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            text = f.read(200_000)
    except OSError:
        return refs
    if ext == ".cue":
        for m in re.finditer(r'FILE\s+"?([^"\r\n]+?)"?\s+(BINARY|WAVE|MP3|MOTOROLA|AIFF)', text, re.I):
            refs.add((path.parent / m.group(1)).resolve())
    elif ext == ".m3u":
        for line in text.splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                refs.add((path.parent / line).resolve())
    elif ext == ".gdi":
        for line in text.splitlines()[1:]:
            parts = line.split()
            if len(parts) >= 5:
                name = " ".join(parts[4:-1]).strip('"') if len(parts) > 5 else parts[4].strip('"')
                refs.add((path.parent / name).resolve())
    return refs


def scan_system(rom_dir: Path, folder: str, max_depth: int = 3) -> list:
    system = get_system(folder)
    root = rom_dir / folder
    files, hidden = [], set()

    def walk(d: Path, depth: int):
        try:
            entries = list(os.scandir(d))
        except OSError:
            return
        for e in entries:
            name = e.name
            if name.startswith("."):
                continue
            p = Path(e.path)
            try:
                if e.is_dir():
                    if name.lower() in SKIP_DIRS:
                        continue
                    target = _game_dir_target(p)
                    if target is not None:
                        files.append((target, True if target == p else False, p))
                    elif depth < max_depth:
                        walk(p, depth + 1)
                    continue
            except OSError:
                continue
            low = name.lower()
            ext = p.suffix.lower()
            if low in SKIP_FILES or ext in JUNK_EXT:
                continue
            if system.exts is not None and ext not in system.exts:
                continue
            if ext in (".cue", ".m3u", ".gdi"):
                hidden.update(_referenced_files(p))
            files.append((p, False, None))

    walk(root, 0)
    games, seen = [], set()
    for path, is_dir, container in files:
        try:
            if path.resolve() in hidden:
                continue
        except OSError:
            pass
        key_path = container or path
        rel = key_path.relative_to(root).as_posix()
        if rel in seen:
            continue
        seen.add(rel)
        base = key_path.name if is_dir or container else path.stem
        if is_dir and key_path.suffix:
            base = key_path.stem
        title, tags = clean_title(base)
        try:
            size = 0 if (is_dir or container) else path.stat().st_size
        except OSError:
            size = 0
        alt, _ = strip_release_number(base)
        games.append(Game(id=f"{folder}/{rel}", system=system, path=path, file_name=base,
                          title=title, tags=tags, size=size, is_dir=is_dir,
                          alt_names=[alt] if alt else []))
    games = group_discs(games)
    games.sort(key=lambda g: g.title.lower())
    return games


def scan_library(rom_dir: Path, hidden_systems=(), progress=None) -> dict:
    """Return {folder: [Game]} for every non-empty system folder."""
    lib = {}
    try:
        folders = sorted(e.name for e in os.scandir(rom_dir) if e.is_dir() and not e.name.startswith("."))
    except OSError:
        return lib
    hidden = {h.lower() for h in hidden_systems}
    for i, folder in enumerate(folders):
        if folder.lower() in hidden:
            continue
        if progress:
            progress(i + 1, len(folders), folder)
        games = scan_system(rom_dir, folder)
        if games:
            lib[folder] = games
    return lib


def ensure_rom_dir(rom_dir: Path, create_system_folders: bool = True) -> Path:
    """Create the roms folder (and EmuDeck-style system subfolders) if missing."""
    rom_dir.mkdir(parents=True, exist_ok=True)
    if create_system_folders:
        for f in ALL_FOLDERS:
            try:
                (rom_dir / f).mkdir(exist_ok=True)
            except OSError:
                pass
        readme = rom_dir / "systems.txt"
        if not readme.exists():
            try:
                lines = [f"{s:<18} {get_system(s).name}" for s in ALL_FOLDERS]
                readme.write_text("Put your games in the matching folder:\n\n" + "\n".join(lines) + "\n",
                                  encoding="utf-8")
            except OSError:
                pass
    return rom_dir
