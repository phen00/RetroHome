"""RetroAchievements Web API client + library matching.

Needs a username and the *Web API key* from https://retroachievements.org/settings
"""
import json
import re
import threading
import time
import urllib.parse
from pathlib import Path

from . import net
from .paths import cache_dir
from .rahash import ra_hash

API = "https://retroachievements.org/API/"
MEDIA = "https://media.retroachievements.org"
SITE = "https://retroachievements.org"


class RAError(Exception):
    pass


def norm_title(t: str) -> str:
    t = t.lower()
    t = re.sub(r"~[^~]*~", "", t)                  # ~Hack~ ~Homebrew~ etc.
    t = re.sub(r"[\(\[][^\)\]]*[\)\]]", "", t)       # (USA) [!]
    t = re.sub(r"^(.*?),\s*(the|a|an)\b", r"\2 \1", t)
    t = t.replace("&", " and ").replace("é", "e")
    t = re.sub(r"\b(the|a|an)\b", " ", t)
    t = re.sub(r"[^a-z0-9]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


_ROMAN = {"ii": "2", "iii": "3", "iv": "4", "v": "5", "vi": "6", "vii": "7", "viii": "8", "ix": "9",
          "x": "10", "xi": "11", "xii": "12", "xiii": "13"}


def _loose(normed: str) -> str:
    words = [_ROMAN.get(w, w) for w in normed.split()]
    return "".join(words)


def badge_url(badge_name: str, locked=False) -> str:
    return f"{MEDIA}/Badge/{badge_name}{'_lock' if locked else ''}.png"


def media_url(path: str) -> str:
    if not path:
        return ""
    if path.startswith("http"):
        return path
    return MEDIA + (path if path.startswith("/") else "/" + path)


class RetroAchievements:
    def __init__(self, user: str, key: str):
        self.user = user.strip()
        self.key = key.strip()
        self.dir = cache_dir() / "ra"
        self.dir.mkdir(parents=True, exist_ok=True)
        self._lists = {}
        self._list_lock = threading.Lock()
        self._console_locks = {}
        self._hash_cache_path = self.dir / "hashes.json"
        self._hash_cache = self._load_json(self._hash_cache_path, {})
        self._hash_lock = threading.Lock()
        self._last_call = 0.0
        self._rate_lock = threading.Lock()

    # ------------------------------------------------------------ http
    def _call(self, endpoint: str, **params):
        params = {k: v for k, v in params.items() if v is not None}
        params["y"] = self.key
        url = API + endpoint + "?" + urllib.parse.urlencode(params)
        with self._rate_lock:  # be polite: ~5 requests/second max
            wait = 0.2 - (time.time() - self._last_call)
            if wait > 0:
                time.sleep(wait)
            self._last_call = time.time()
        try:
            data = net.get_json(url, timeout=40)
        except net.HttpError as e:
            if e.code in (401, 403):
                raise RAError("RetroAchievements rejected the username or Web API key.") from None
            if e.code == 429:
                raise RAError("RetroAchievements rate limit hit, try again shortly.") from None
            raise RAError(f"RetroAchievements error: {e}") from None
        except OSError as e:
            raise RAError(f"Can't reach RetroAchievements ({e}).") from None
        except ValueError:
            raise RAError("RetroAchievements sent an unexpected response.") from None
        if isinstance(data, dict) and data.get("Error") and len(data) <= 3:
            raise RAError(str(data.get("Error")))
        return data

    @staticmethod
    def _load_json(path: Path, default):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return default

    @staticmethod
    def _save_json(path: Path, data):
        tmp = path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f)
        tmp.replace(path)

    # ------------------------------------------------------------ user data
    def profile(self) -> dict:
        return self._call("API_GetUserProfile.php", u=self.user)

    def rank(self) -> dict:
        """{"Rank", "TotalRanked"} from the user summary (Rank is None for untracked users)."""
        res = self._call("API_GetUserSummary.php", u=self.user, g=0, a=0)
        if not isinstance(res, dict):
            return {}
        return {"Rank": res.get("Rank"), "TotalRanked": res.get("TotalRanked")}

    def recent_achievements(self, minutes=60 * 24 * 30) -> list:
        res = self._call("API_GetUserRecentAchievements.php", u=self.user, m=minutes)
        return res if isinstance(res, list) else []

    def completion_progress(self, count=100) -> list:
        res = self._call("API_GetUserCompletionProgress.php", u=self.user, c=count)
        return res.get("Results", []) if isinstance(res, dict) else []

    def completion_all(self, limit=5000) -> list:
        out, offset = [], 0
        while offset < limit:
            res = self._call("API_GetUserCompletionProgress.php", u=self.user, c=500, o=offset)
            batch = res.get("Results", []) if isinstance(res, dict) else []
            out += batch
            total = int(res.get("Total") or 0) if isinstance(res, dict) else 0
            offset += 500
            if len(batch) < 500 or offset >= total:
                break
        return out

    def consoles(self) -> list:
        """Active game systems on RetroAchievements (cached for a week)."""
        path = self.dir / "consoles.json"
        if path.exists() and time.time() - path.stat().st_mtime < 7 * 86400:
            data = self._load_json(path, None)
            if isinstance(data, list) and data:
                return data
        try:
            data = self._call("API_GetConsoleIDs.php", a=1, g=1)
        except RAError:
            data = self._load_json(path, [])
            if not data:
                raise
            return data
        data = [c for c in data if isinstance(c, dict) and c.get("IsGameSystem", True) and c.get("Active", True)]
        self._save_json(path, data)
        return data

    def games_for_console(self, console_id: int) -> list:
        """Every game with achievements on a console (shares the matcher's cache)."""
        return list(self.game_list(console_id).get("raw") or [])

    def game_info(self, game_id: int) -> dict:
        return self._call("API_GetGame.php", i=game_id)

    def game_progress(self, game_id: int) -> dict:
        return self._call("API_GetGameInfoAndUserProgress.php", u=self.user, g=game_id, a=1)

    def verify(self) -> dict:
        p = self.profile()
        if not isinstance(p, dict) or not p.get("User"):
            raise RAError("Couldn't load that RetroAchievements profile.")
        return p

    # ------------------------------------------------------------ matching
    def game_list(self, console_id: int) -> list:
        lock = self._console_locks.setdefault(console_id, threading.Lock())
        with lock:
            if console_id in self._lists:
                return self._lists[console_id]
            path = self.dir / f"games_{console_id}.json"
            data = None
            if path.exists() and time.time() - path.stat().st_mtime < 7 * 86400:
                data = self._load_json(path, None)
            if data is None:
                try:
                    data = self._call("API_GetGameList.php", i=console_id, f=1, h=1)
                    if isinstance(data, list):
                        self._save_json(path, data)
                except RAError:
                    data = self._load_json(path, [])  # stale cache beats nothing
            data = data if isinstance(data, list) else []
            idx_hash, idx_title = {}, {}
            for g in data:
                for h in g.get("Hashes") or []:
                    idx_hash[h.lower()] = g
                title = g.get("Title", "")
                if title.startswith("~") and not title.lower().startswith(("~homebrew~", "~prototype~", "~unlicensed~")):
                    continue  # skip hacks/test kits for title matching
                for part in title.split(" | "):
                    idx_title.setdefault(norm_title(part), g)
            entry = {"hash": idx_hash, "title": idx_title, "raw": data}
            self._lists[console_id] = entry
            return entry

    def match(self, game) -> dict:
        """Find the RA game entry for a scanned Game. Returns dict or None."""
        cid = game.system.ra
        if not cid:
            return None
        idx = self.game_list(cid)
        if not idx["hash"] and not idx["title"]:
            return None
        h = None
        if game.system.hash and not game.is_dir:
            try:
                st = game.path.stat()
                key = f"{game.path}|{st.st_size}|{int(st.st_mtime)}"
            except OSError:
                key = None
            with self._hash_lock:
                h = self._hash_cache.get(key) if key else None
            if h is None and key:
                h = ra_hash(game.system.hash, game.path) or ""
                with self._hash_lock:
                    self._hash_cache[key] = h
            if h and h in idx["hash"]:
                return idx["hash"][h]
        cands = [game.title, game.file_name, *game.alt_names]
        for cand in cands:
            g = idx["title"].get(norm_title(cand))
            if g:
                return g
        # Looser keys: drop punctuation entirely ("Metal Gear Solid - Peace Walker" vs
        # "Metal Gear Solid: Peace Walker") and roman/arabic numeral differences.
        loose = idx.get("loose")
        if loose is None:
            loose = idx["loose"] = {_loose(k): v for k, v in idx["title"].items()}
        for cand in cands:
            g = loose.get(_loose(norm_title(cand)))
            if g:
                return g
        return None

    def flush_hash_cache(self):
        with self._hash_lock:
            try:
                self._save_json(self._hash_cache_path, self._hash_cache)
            except OSError:
                pass
