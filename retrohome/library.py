"""Library + RetroAchievements state shared by the UI screens."""
import json
import time
from pathlib import Path

from . import progression
from .paths import cache_dir
from .retroach import RAError, RetroAchievements, media_url
from .scanner import scan_library


class Library:
    def __init__(self, config, tasks):
        self.config = config
        self.tasks = tasks
        self.by_system = {}
        self.all = []
        self.by_id = {}
        self.scanning = False
        self.scan_status = ""
        self.version = 0          # bumps when contents change

    def scan(self, on_done=None):
        if self.scanning:
            return
        self.scanning = True
        rom_dir = Path(self.config["rom_dir"])

        def progress(i, n, folder):
            self.scan_status = f"Scanning {folder} ({i}/{n})"

        def work():
            return scan_library(rom_dir, self.config["hidden_systems"], progress)

        def done(lib):
            self.by_system = lib
            self.all = sorted((g for gs in lib.values() for g in gs), key=lambda g: g.title.lower())
            self.by_id = {g.id: g for g in self.all}
            self.scanning = False
            self.scan_status = ""
            self.version += 1
            if on_done:
                on_done()

        def fail(e):
            self.scanning = False
            self.scan_status = f"Scan failed: {e}"
        self.tasks.submit(work, callback=done, error=fail)

    def visible(self, only_ra=False):
        """Games to show: only ones with a RetroAchievements set when only_ra is on."""
        return [g for g in self.all if g.ra_game_id] if only_ra else list(self.all)

    def categories(self, only_ra=False):
        """[(key, label, [games])] for the home screen chip bar."""
        shown = self.visible(only_ra)
        cats = []
        played = [g for g in shown if self.config.last_played(g.id)]
        played.sort(key=lambda g: -self.config.last_played(g.id))
        played_ids = {g.id for g in played}
        rest = [g for g in shown if g.id not in played_ids]
        if not shown:
            return cats
        cats.append(("home", "Home", played + rest))
        favs = [g for g in shown if self.config.is_fav(g.id)]
        if favs:
            cats.append(("favs", "Favourites", favs))
        by_sys = {}
        for g in shown:
            by_sys.setdefault(g.system.folder, []).append(g)
        for folder in sorted(by_sys, key=lambda f: by_sys[f][0].system.name.lower()):
            games = by_sys[folder]
            cats.append((folder, games[0].system.label, games))
        return cats


class RAState:
    """Profile, tracker data and per-game progress, fetched in the background."""

    def __init__(self, config, tasks, library):
        self.config = config
        self.tasks = tasks
        self.library = library
        self.client = None
        self.profile = None
        self.recent = []
        self.completion = []
        self.progress = {}        # ra game id -> dict
        self._progress_ts = {}
        self._pending = set()
        self.error = ""
        self.loading = False
        self.matching = False
        self.match_status = ""
        self.last_refresh = 0
        self.version = 0
        self._info = {}
        self.prog = None          # progression.Progress
        self.awards = {}          # ra game id -> award key
        self.events = []          # celebrations waiting to be shown
        self.on_progress = None   # callback after profile/progression refresh
        self._match_path = cache_dir() / "ra" / "matches.json"
        self._matches = None      # game id -> {"size", "m"}: remembered between sessions
        self.reconfigure()

    @property
    def enabled(self):
        return self.client is not None

    def reconfigure(self):
        if self.config.ra_enabled:
            self.client = RetroAchievements(self.config["ra_user"], self.config["ra_key"])
        else:
            self.client = None
        self.profile, self.recent, self.completion = None, [], []
        self.progress.clear()
        self.prog = None
        self.awards = {}
        self.events = []
        self.error = ""

    # ------------------------------------------------------------ tracker
    def refresh(self, force=False):
        if not self.client or self.loading:
            return
        if not force and time.time() - self.last_refresh < 120:
            return
        self.loading = True
        client = self.client

        def work():
            prof = client.profile()
            try:
                recent = client.recent_achievements()
            except RAError:
                recent = []
            try:
                comp = client.completion_all()
            except RAError:
                comp = []
            return prof, recent, comp

        def done(res):
            if client is not self.client:
                return
            self.profile, self.recent, self.completion = res
            self.recent.sort(key=lambda a: a.get("Date", ""), reverse=True)
            self._update_progression()
            if self.on_progress:
                self.on_progress()
            self.error = ""
            self.loading = False
            self.last_refresh = time.time()
            self.version += 1

        def fail(e):
            self.error = str(e)
            self.loading = False
            self.last_refresh = time.time()
            self.version += 1
        self.tasks.submit(work, callback=done, error=fail)

    def _update_progression(self):
        self.prog = progression.compute(self.profile, self.completion)
        awards, titles = {}, {}
        for c in self.completion:
            a = progression.award_from_ra(c.get("HighestAwardKind"), int(c.get("NumAwarded") or 0),
                                          int(c.get("NumAwardedHardcore") or 0), int(c.get("MaxPossible") or 0))
            if a:
                awards[int(c.get("GameID") or 0)] = a
                titles[int(c.get("GameID") or 0)] = c
        self.awards = awards
        # Celebrate anything new since the last snapshot we saved for this user.
        snap = self.config.get("ra_snapshot") or {}
        if snap.get("user") == self.client.user and snap.get("curve") == progression.CURVE_VERSION:
            old_awards = {int(k): v for k, v in (snap.get("awards") or {}).items()}
            for gid, a in awards.items():
                old = old_awards.get(gid, "")
                if progression.AWARD_INFO[a]["rank"] > progression.AWARD_INFO.get(old, {"rank": 0})["rank"] \
                        and a in (progression.AWARD_MYTHIC, progression.AWARD_PLATINUM):
                    c = titles[gid]
                    self.events.append(dict(kind="award", award=a, title=c.get("Title", ""),
                                            icon=media_url(c.get("ImageIcon", "")), size=c.get("MaxPossible", 0)))
            if self.prog.level > int(snap.get("level") or 0) > 0:
                self.events.append(dict(kind="level", old=int(snap["level"]), new=self.prog.level))
        self.config["ra_snapshot"] = {"user": self.client.user, "level": self.prog.level,
                                      "curve": progression.CURVE_VERSION,
                                      "awards": {str(k): v for k, v in awards.items()}}

    def award_for(self, game):
        return self.awards.get(game.ra_game_id, "") if game.ra_game_id else ""

    def game_progress(self, ra_id, force=False):
        """Return cached progress dict (or None) and fetch if stale."""
        if not self.client or not ra_id:
            return None
        ts = self._progress_ts.get(ra_id, 0)
        if (force or time.time() - ts > 600) and ra_id not in self._pending:
            self._pending.add(ra_id)
            client = self.client

            def done(data, rid=ra_id):
                self._pending.discard(rid)
                if isinstance(data, dict):
                    self.progress[rid] = data
                    self._progress_ts[rid] = time.time()
                    self._info.setdefault(rid, data)
                    self.version += 1

            def fail(e, rid=ra_id):
                self._pending.discard(rid)
                self._progress_ts[rid] = time.time() - 480  # retry in ~2 min
            self.tasks.submit(client.game_progress, ra_id, callback=done, error=fail)
        return self.progress.get(ra_id)

    # ------------------------------------------------------------ matching
    def _load_matches(self):
        if self._matches is None:
            try:
                with open(self._match_path, "r", encoding="utf-8") as f:
                    self._matches = json.load(f)
            except (OSError, ValueError):
                self._matches = {}
        return self._matches

    def _save_matches(self):
        try:
            self._match_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._match_path.with_suffix(".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self._matches or {}, f)
            tmp.replace(self._match_path)
        except OSError:
            pass

    def apply_cached_matches(self):
        """Instantly restore last session's matches (same file, same size)."""
        cache = self._load_matches()
        for g in self.library.all:
            e = cache.get(g.id)
            if e and not g.ra_game_id and e.get("size") == g.size:
                self._apply_match(g, e["m"], None, remember=False)

    def match_library(self, on_match=None):
        if not self.client or self.matching:
            return
        self.apply_cached_matches()
        self.matching = True
        client = self.client
        games = [g for g in self.library.all if g.system.ra and not g.ra_game_id]
        # recently played first so the home row lights up quickly
        games.sort(key=lambda g: -self.config.last_played(g.id))

        def work():
            for i, g in enumerate(games):
                if client is not self.client:
                    return
                self.match_status = f"Matching achievements {i + 1}/{len(games)}"
                try:
                    m = client.match(g)
                except RAError:
                    m = None
                except Exception:  # noqa: BLE001 - never let one bad file stop matching
                    m = None
                if m:
                    self.tasks.call_soon(self._apply_match, g, m, on_match)
                if i % 200 == 199:
                    client.flush_hash_cache()
            client.flush_hash_cache()

        def done(_):
            self.matching = False
            self.match_status = ""
            self.version += 1
            self.library.version += 1
            self._save_matches()

        def fail(e):
            self.matching = False
            self.match_status = ""
            self._save_matches()
        self.tasks.submit(work, callback=done, error=fail)

    def _apply_match(self, game, m, on_match, remember=True):
        if remember:
            keep = {k: m.get(k) for k in ("ID", "Title", "ImageIcon", "Points", "NumAchievements")}
            self._load_matches()[game.id] = {"size": game.size, "m": keep}
        game.ra_game_id = int(m.get("ID") or 0)
        game.ra_title = m.get("Title", "")
        game.extra["ra_icon"] = media_url(m.get("ImageIcon", ""))
        game.extra["ra_points"] = m.get("Points", 0)
        game.extra["ra_count"] = m.get("NumAchievements", 0)
        self.library.version += 1
        if on_match:
            on_match(game)

    def _game_info(self, game):
        """Worker-thread helper: cached API_GetGame for a matched game."""
        if not self.client or not game.ra_game_id:
            return None
        if game.ra_game_id not in self._info:
            prog = self.progress.get(game.ra_game_id)
            if prog and prog.get("ImageBoxArt"):
                self._info[game.ra_game_id] = prog
            else:
                try:
                    info = self.client.game_info(game.ra_game_id)
                except RAError:
                    return None
                self._info[game.ra_game_id] = info if isinstance(info, dict) else {}
        return self._info[game.ra_game_id]

    def boxart_for(self, game):
        info = self._game_info(game)
        return media_url(info.get("ImageBoxArt", "")) if info else None

    def images_for(self, game):
        info = self._game_info(game)
        if not info:
            return []
        return [media_url(info.get(k, "")) for k in ("ImageIngame", "ImageTitle") if info.get(k)]

    def library_completion(self, game):
        """Completion entry from the tracker list for a game, if present."""
        for c in self.completion:
            if c.get("GameID") == game.ra_game_id:
                return c
        return None
