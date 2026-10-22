"""Persistent settings (config.json): global settings plus per-user profiles.

Keys in PROFILE_KEYS live inside the active user's profile; everything else is global.
"""
import json
import secrets
import threading
import time

from .paths import config_dir

GLOBAL_DEFAULTS = {
    "rom_dir": "",
    "fullscreen": True,
    "window_size": [1280, 800],
    "hidden_systems": ["cloud", "remoteplay", "android", "steam", "epic", "lutris",
                       "kodi", "moonlight", "desktop"],
    "emulation_dir": "",          # optional override for the EmuDeck "Emulation" folder
    "server_url": "",             # RetroHome Online server (empty = not configured)
    "ask_user_on_start": True,
    "active_profile": "",
    "screenshot_backgrounds": True,
    "show_all_games": False,      # False: only games with a RetroAchievements set (when signed in)
    "auto_update_check": True,    # look for a new release on GitHub at start-up
    "skipped_update": "",
    "friend_alerts": True,        # notify when someone you follow on RetroAchievements starts playing
}
PROFILE_DEFAULTS = {
    "name": "Player",
    "color": [0, 112, 209],
    "pin": "",                    # pbkdf2 hash or empty
    "ra_user": "",
    "ra_key": "",
    "favourites": [],
    "history": {},                # game_id -> {"last": ts, "count": n, "playtime": seconds}
    "ra_snapshot": {},
    "remote": {},
    "disc_choice": {},
    "fav_events": {},             # game_id -> [timestamp, is_favourite] (for syncing removals)            # game_id -> "all" or disc index                 # {"server", "username", "token", "user_id"} when signed in online
    "created": 0,
}
PROFILE_KEYS = set(PROFILE_DEFAULTS)
COLORS = [[0, 112, 209], [214, 60, 90], [40, 170, 110], [230, 150, 30], [140, 80, 220], [30, 160, 190],
          [200, 80, 40], [110, 120, 140]]


class Config:
    def __init__(self):
        self.path = config_dir() / "config.json"
        self._lock = threading.Lock()
        self.data = dict(GLOBAL_DEFAULTS)
        self.data["profiles"] = {}
        if self.path.exists():
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    self.data.update(json.load(f))
            except (OSError, ValueError):
                pass
        self._migrate()

    def _migrate(self):
        """v1 kept user data at the top level; move it into a first profile."""
        if self.data.get("profiles"):
            return
        legacy = {k: self.data.pop(k) for k in list(self.data) if k in PROFILE_KEYS}
        if legacy.get("ra_user") or legacy.get("history") or legacy.get("favourites"):
            pid = self.new_profile(legacy.get("ra_user") or "Player 1", save=False)
            self.data["profiles"][pid].update(legacy)
            self.data["active_profile"] = pid
            self.save()

    # ------------------------------------------------------------ access
    @property
    def profile(self) -> dict:
        pid = self.data.get("active_profile")
        p = self.data.get("profiles", {}).get(pid)
        if p is None:
            return dict(PROFILE_DEFAULTS)   # nobody signed in: read-only defaults
        return p

    def _src(self, k):
        return self.profile if k in PROFILE_KEYS else self.data

    def __getitem__(self, k):
        src = self._src(k)
        if k in src:
            return src[k]
        return PROFILE_DEFAULTS.get(k) if k in PROFILE_KEYS else GLOBAL_DEFAULTS.get(k)

    def __setitem__(self, k, v):
        self._src(k)[k] = v
        self.save()

    def get(self, k, default=None):
        v = self[k]
        return default if v is None else v

    def save(self):
        with self._lock:
            tmp = self.path.with_suffix(".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2)
            tmp.replace(self.path)

    # ------------------------------------------------------------ profiles
    @property
    def profiles(self) -> dict:
        return self.data.setdefault("profiles", {})

    @property
    def active_id(self) -> str:
        pid = self.data.get("active_profile", "")
        return pid if pid in self.profiles else ""

    def new_profile(self, name: str, save=True) -> str:
        pid = "u" + secrets.token_hex(4)
        p = json.loads(json.dumps(PROFILE_DEFAULTS))
        p["name"] = name.strip()[:24] or "Player"
        p["color"] = COLORS[len(self.profiles) % len(COLORS)]
        p["created"] = time.time()
        self.profiles[pid] = p
        if save:
            self.save()
        return pid

    def set_active(self, pid: str):
        self.data["active_profile"] = pid
        self.save()

    def delete_profile(self, pid: str):
        self.profiles.pop(pid, None)
        if self.data.get("active_profile") == pid:
            self.data["active_profile"] = ""
        self.save()

    # ------------------------------------------------------------ history
    def record_play(self, game_id: str, seconds: float):
        h = self.profile.setdefault("history", {})
        e = h.setdefault(game_id, {"last": 0, "count": 0, "playtime": 0})
        e["last"] = time.time()
        e["count"] = e.get("count", 0) + 1
        e["playtime"] = e.get("playtime", 0) + max(0, int(seconds))
        self.save()

    def last_played(self, game_id: str) -> float:
        return self.profile.get("history", {}).get(game_id, {}).get("last", 0)

    def playtime(self, game_id: str) -> int:
        return self.profile.get("history", {}).get(game_id, {}).get("playtime", 0)

    def is_fav(self, game_id: str) -> bool:
        return game_id in self.profile.get("favourites", [])

    def toggle_fav(self, game_id: str):
        favs = self.profile.setdefault("favourites", [])
        on = game_id not in favs
        if on:
            favs.append(game_id)
        else:
            favs.remove(game_id)
        self.profile.setdefault("fav_events", {})[game_id] = [time.time(), on]
        self.save()

    @property
    def ra_enabled(self) -> bool:
        p = self.profile
        return bool(p.get("ra_user") and p.get("ra_key"))

    @property
    def emulation_dir(self):
        from pathlib import Path
        if self.data.get("emulation_dir"):
            return Path(self.data["emulation_dir"])
        rd = self.data.get("rom_dir")
        return Path(rd).parent if rd else Path.home() / "Emulation"
