"""Box art and background screenshots: local scraped media first, then the internet.

Box art order:
  1. Already-scraped media (EmuDeck/ES-DE downloaded_media, or roms/<system>/media)
  2. libretro-thumbnails exact name match (No-Intro / Redump file names)
  3. libretro-thumbnails fuzzy match against that system's thumbnail index
  4. RetroAchievements box art (when the game is matched to RA)

Screenshots (rotated behind the selected game):
  local screenshots/titlescreens/fanart, libretro Named_Snaps + Named_Titles,
  and RetroAchievements' in-game and title images.
"""
import html
import json
import re
import threading
import time
import urllib.parse
from pathlib import Path

from . import net
from .paths import cache_dir

THUMBS = "https://thumbnails.libretro.com"
IMG_EXT = (".png", ".jpg", ".jpeg", ".webp")
RETRY_AFTER = 3 * 86400
CACHE_VERSION = "2"     # bump to discard negative "not found" markers after matching fixes


def libretro_safe(name: str) -> str:
    return re.sub(r'[&*/:`<>?\\|"]', "_", name)


def _norm(s: str) -> str:
    s = s.lower()
    s = re.sub(r"^\d{4}\s*-\s+", "", s)
    s = re.sub(r"[\(\[][^\)\]]*[\)\]]", "", s)
    s = re.sub(r"^(.*?),\s*(the|a|an)\b", r"\2 \1", s)
    s = s.replace("&", "and")
    s = re.sub(r"\b(the|a|an)\b", " ", s)
    return re.sub(r"[^a-z0-9]+", "", s)


def _regions(s: str) -> set:
    return {r.strip().lower() for grp in re.findall(r"\(([^)]*)\)", s) for r in grp.split(",")}


def _safe(name: str) -> str:
    return re.sub(r'[<>:"/\\|?*]', "_", name)[:150]


class Artwork:
    def __init__(self, emulation_dir: Path, rom_dir: Path, tasks, ra_boxart=None, ra_images=None):
        self.emulation_dir = Path(emulation_dir)
        self.rom_dir = Path(rom_dir)
        self.tasks = tasks
        self.ra_boxart = ra_boxart     # callable(game) -> url or None (runs in worker)
        self.ra_images = ra_images     # callable(game) -> [urls] (runs in worker)
        self.dir = cache_dir() / "art"
        self.shot_dir = cache_dir() / "shots"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.shot_dir.mkdir(parents=True, exist_ok=True)
        self._migrate()
        self.state = {}                # game.id -> Path | None | "pending"
        self.shots = {}                # game.id -> [Path] | "pending"
        self._indexes = {}
        self._index_locks = {}
        self._listeners = []

    def _migrate(self):
        marker = self.dir / ".version"
        try:
            if marker.exists() and marker.read_text().strip() == CACHE_VERSION:
                return
            for neg in list(self.dir.rglob("*.none")) + list(self.shot_dir.rglob("*.none")):
                neg.unlink(missing_ok=True)
            marker.write_text(CACHE_VERSION)
        except OSError:
            pass

    def on_ready(self, fn):
        self._listeners.append(fn)

    # ------------------------------------------------------------ box art
    def get(self, game, fetch=True):
        """Return a local image path, or None (and start fetching in the background)."""
        st = self.state.get(game.id)
        if isinstance(st, Path):
            return st
        if st == "pending" or (st is None and game.id in self.state):
            return None
        local = self._local(game, self._local_cover_dirs(game))
        cp = self._cache_path(game)
        if not local and cp.exists():
            local = cp
        if local:
            self.state[game.id] = local
            return local
        if not fetch:
            return None
        self.state[game.id] = "pending"
        self.tasks.submit(self._fetch, game, callback=lambda p, g=game: self._done(g, p),
                          error=lambda e, g=game: self.state.pop(g.id, None))
        return None

    def refresh(self, game):
        cp = self._cache_path(game)
        for p in (cp, cp.with_suffix(".none")):
            try:
                p.unlink()
            except OSError:
                pass
        self.state.pop(game.id, None)
        self.shots.pop(game.id, None)
        try:
            (self.shot_dir / game.system.folder / (_safe(game.file_name) + ".none")).unlink()
        except OSError:
            pass
        self.get(game)

    def _done(self, game, path):
        self.state[game.id] = path
        if path:
            for fn in self._listeners:
                fn(game, path)

    def _cache_path(self, game) -> Path:
        return self.dir / game.system.folder / (_safe(game.file_name) + ".png")

    def _local_cover_dirs(self, game):
        f = game.system.folder
        dm = self.emulation_dir / "tools" / "downloaded_media" / f
        return [dm / "covers", dm / "box2dfront",
                Path.home() / "ES-DE" / "downloaded_media" / f / "covers",
                self.rom_dir / f / "media" / "covers", self.rom_dir / f / "media" / "box2dfront",
                self.rom_dir / f / "media" / "images", self.rom_dir / f / "images"]

    def _local_shot_dirs(self, game):
        f = game.system.folder
        out = []
        for base in (self.emulation_dir / "tools" / "downloaded_media" / f,
                     Path.home() / "ES-DE" / "downloaded_media" / f, self.rom_dir / f / "media"):
            out += [base / "screenshots", base / "titlescreens", base / "fanart"]
        return out

    def _local(self, game, folders, many=False):
        names = [game.file_name, *game.alt_names]
        found = []
        for folder in folders:
            if not folder.is_dir():
                continue
            for n in names:
                for ext in IMG_EXT:
                    p = folder / (n + ext)
                    if p.exists():
                        if not many:
                            return p
                        found.append(p)
                        break
        return found if many else None

    def _fetch(self, game):
        dest = self._cache_path(game)
        neg = dest.with_suffix(".none")
        if neg.exists() and time.time() - neg.stat().st_mtime < RETRY_AFTER:
            return None
        try:
            if self._libretro(game, "Named_Boxarts", dest):
                return dest
            if self.ra_boxart:
                url = self.ra_boxart(game)
                if url and net.download_image(url, dest):
                    return dest
        except OSError:
            return None  # offline: don't write a negative marker, retry next launch
        dest.parent.mkdir(parents=True, exist_ok=True)
        neg.touch()
        return None

    def _libretro(self, game, kind, dest) -> bool:
        thumb_sys = game.system.thumb
        if not thumb_sys:
            return False
        names = [game.file_name, *game.alt_names]
        for n in names:                       # exact
            if net.download_image(self._thumb_url(thumb_sys, n, kind), dest):
                return True
        for n in names:                       # fuzzy
            best = self._fuzzy(thumb_sys, n, kind)
            if best and net.download_image(self._thumb_url(thumb_sys, best, kind), dest):
                return True
        return False

    # ------------------------------------------------------------ screenshots
    def screenshots(self, game):
        """Local paths of background screenshots available now (fetches the rest once)."""
        st = self.shots.get(game.id)
        if isinstance(st, list):
            return st
        if st == "pending":
            return []
        local = self._local(game, self._local_shot_dirs(game), many=True)
        folder = self.shot_dir / game.system.folder
        cached = sorted(folder.glob(_safe(game.file_name) + "__*.png")) if folder.is_dir() else []
        have = local + cached
        if have or (folder / (_safe(game.file_name) + ".none")).exists():
            self.shots[game.id] = have
            return have
        self.shots[game.id] = "pending"
        self.tasks.submit(self._fetch_shots, game, callback=lambda r, g=game: self.shots.__setitem__(g.id, r),
                          error=lambda e, g=game: self.shots.pop(g.id, None))
        return []

    def _fetch_shots(self, game):
        folder = self.shot_dir / game.system.folder
        base = _safe(game.file_name)
        out = []
        try:
            for i, kind in enumerate(("Named_Snaps", "Named_Titles")):
                dest = folder / f"{base}__lr{i}.png"
                if self._libretro(game, kind, dest):
                    out.append(dest)
            if self.ra_images:
                for i, url in enumerate(self.ra_images(game) or []):
                    dest = folder / f"{base}__ra{i}.png"
                    if url and net.download_image(url, dest):
                        out.append(dest)
        except OSError:
            return out
        if not out:
            folder.mkdir(parents=True, exist_ok=True)
            (folder / (base + ".none")).touch()
        return out

    # ------------------------------------------------------------ libretro index
    @staticmethod
    def _thumb_url(thumb_sys, name, kind="Named_Boxarts"):
        return f"{THUMBS}/{urllib.parse.quote(thumb_sys)}/{kind}/{urllib.parse.quote(libretro_safe(name))}.png"

    def _index(self, thumb_sys, kind="Named_Boxarts"):
        key = (thumb_sys, kind)
        lock = self._index_locks.setdefault(key, threading.Lock())
        with lock:
            if key in self._indexes:
                return self._indexes[key]
            p = self.dir / "_index" / (libretro_safe(thumb_sys) + ("" if kind == "Named_Boxarts" else "." + kind) + ".json")
            names = None
            if p.exists() and time.time() - p.stat().st_mtime < 30 * 86400:
                try:
                    names = json.loads(p.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    names = None
            if names is None:
                try:
                    page = net.get(f"{THUMBS}/{urllib.parse.quote(thumb_sys)}/{kind}/", timeout=40)
                    text = page.decode("utf-8", "replace")
                    names = [html.unescape(urllib.parse.unquote(m))[:-4]
                             for m in re.findall(r'href="([^"]+\.png)"', text)]
                    p.parent.mkdir(parents=True, exist_ok=True)
                    p.write_text(json.dumps(names), encoding="utf-8")
                except OSError:
                    names = []
            idx = {}
            for n in names:
                idx.setdefault(_norm(n), []).append(n)
            self._indexes[key] = idx
            return idx

    def _fuzzy(self, thumb_sys, file_name, kind="Named_Boxarts"):
        idx = self._index(thumb_sys, kind)
        key = _norm(file_name)
        cands = idx.get(key)
        if not cands:
            base = _norm(re.split(r"\s[-:]\s", re.sub(r"[\(\[].*", "", re.sub(r"^\d{4}\s*-\s+", "", file_name)))[0])
            cands = idx.get(base) if base and len(base) > 3 else None
        if not cands:
            return None
        want = _regions(file_name) or {"usa"}
        pref = ["usa", "world", "europe", "japan"]

        def score(n):
            r = _regions(n)
            s = len(r & want) * 10
            for i, p in enumerate(pref):
                if p in r:
                    s += (len(pref) - i)
                    break
            return s - len(n) * 0.01
        return max(cands, key=score)
