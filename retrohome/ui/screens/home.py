"""Console-style home screen."""
import time

import pygame

from ...retroach import media_url
from .. import gfx
from ..app import Screen
from .common import (ago, badge, draw_icon_slot, fmt_int, fmt_playtime, tile_surface,
                     url_image)

TILE, BIG, GAP = 126, 184, 18
ROW_X, ROW_Y = 60, 92
INFO_Y = 300
TRACK_Y = 588
TRACK_H = 172


class Home(Screen):
    def __init__(self, app):
        super().__init__(app)
        self.cats = []
        self.cat_i = 0
        self.sel = {}           # cat key -> index
        self.focus = "row"      # chips | row | tracker
        self.track_i = 0
        self.cam = 0.0
        self.chip_cam = 0.0
        self.lib_version = -1
        self.hero = None        # (path, surface)
        self.hero_prev = None
        self.hero_fade = 1.0
        self.last_ra_poll = time.time()
        self.shot_game, self.shot_t, self.shot_i = None, 0.0, 0

    # ------------------------------------------------------------ data
    def _sync(self):
        lib = self.app.library
        key = (lib.version, self.app.ra.enabled, self.app.only_ra)
        if key == self.lib_version:
            return
        cur_key = self.cats[self.cat_i][0] if self.cats else "home"
        cur_game = self.cur_game()
        self.cats = lib.categories(self.app.only_ra)
        if self.app.ra.enabled:
            # the RA Library tab is always there, even with an empty library, so you can get games
            if not self.cats:
                self.cats = [("home", "Home", [])]
            self.cats.insert(1, ("ralib", "RA Library", []))
        self.lib_version = key
        keys = [c[0] for c in self.cats]
        self.cat_i = keys.index(cur_key) if cur_key in keys else 0
        if cur_game:
            games = self.cats[self.cat_i][2]
            for i, g in enumerate(games):
                if g.id == cur_game.id:
                    self.sel[cur_key] = i
                    break

    @property
    def games(self):
        return self.cats[self.cat_i][2] if self.cats else []

    @property
    def idx(self):
        key = self.cats[self.cat_i][0] if self.cats else "home"
        return min(self.sel.get(key, 0), len(self.games))   # == len -> "Library" tile

    @idx.setter
    def idx(self, v):
        key = self.cats[self.cat_i][0] if self.cats else "home"
        self.sel[key] = v

    def cur_game(self):
        g = self.games
        i = self.idx
        return g[i] if g and i < len(g) else None

    # ------------------------------------------------------------ input
    def on_action(self, a):
        if not self.cats:
            if a == "start":
                self._settings()
            elif a == "y":
                self.app.library.scan()
            return
        n = len(self.games) + 1  # + Library tile
        if a in ("lb", "rb"):
            self.cat_i = (self.cat_i + (1 if a == "rb" else -1)) % len(self.cats)
            self.cam = max(0, self.idx - 2) * (TILE + GAP)
            return
        if a == "start":
            self._settings()
            return
        if a == "select":
            self._open_grid()
            return
        if self.focus == "chips":
            if a == "left":
                self.cat_i = (self.cat_i - 1) % len(self.cats)
            elif a == "right":
                if self.cat_i == len(self.cats) - 1:
                    self.focus = "profile"          # past the last tab: your profile
                else:
                    self.cat_i += 1
            elif a in ("down", "a"):
                self.focus = "row"
        elif self.focus == "profile":
            if a == "left":
                self.focus = "chips"
            elif a == "down":
                self.focus = "row"
            elif a == "a":
                from .profile import Profile
                self.app.push(Profile(self.app))
        elif self.focus == "row":
            if a == "left":
                self.idx = max(0, self.idx - 1)
            elif a == "right":
                self.idx = min(n - 1, self.idx + 1)
            elif a == "up":
                self.focus = "chips"
            elif a == "down":
                self.focus = "tracker"
            elif a == "a":
                g = self.cur_game()
                if g:
                    self.app.launch(g)
                elif not self.games and not self.on_ralib and self._ralib_index() is not None:
                    self.cat_i = self._ralib_index()
                    self._open_grid()
                else:
                    self._open_grid()
            elif a == "y":
                g = self.cur_game()
                if g:
                    self._open_achievements(g)
                elif not self.app.library.all:
                    self.app.library.scan()
                    self.app.toast("Rescanning…")
            elif a == "x":
                g = self.cur_game()
                if g:
                    self.app.config.toggle_fav(g.id)
                    self.app.toast(("Added to" if self.app.config.is_fav(g.id) else "Removed from") + " Favourites")
                    self.app.library.version += 1
        elif self.focus == "tracker":
            if a == "left":
                self.track_i = max(0, self.track_i - 1)
            elif a == "right":
                self.track_i = min(2, self.track_i + 1)
            elif a == "up":
                self.focus = "row"
            elif a == "a":
                self._open_tracker()
            elif a == "y":
                self.app.ra.refresh(force=True)
                self.app.toast("Refreshing achievements…")

    def _settings(self):
        from .settings import Settings
        self.app.push(Settings(self.app))

    def _ralib_index(self):
        keys = [c[0] for c in self.cats]
        return keys.index("ralib") if "ralib" in keys else None

    @property
    def on_ralib(self):
        return bool(self.cats) and self.cats[self.cat_i][0] == "ralib"

    def _open_grid(self):
        if self.on_ralib:
            from .ralib import ConsoleList
            self.app.push(ConsoleList(self.app))
            return
        from .library_grid import LibraryGrid
        self.app.push(LibraryGrid(self.app, self.cats[self.cat_i][0] if self.cats else "home",
                                  on_pick=self._picked_from_grid))

    def _picked_from_grid(self, cat, game):
        keys = [c[0] for c in self.cats]
        self.cat_i = keys.index(cat) if isinstance(cat, str) and cat in keys else 0
        for i, g in enumerate(self.games):
            if g.id == game.id:
                self.idx = i
                break
        self.focus = "row"

    def _open_achievements(self, game):
        if not self.app.ra.enabled:
            from .setup import RASetup
            self.app.push(RASetup(self.app))
            return
        if not game.ra_game_id:
            msg = ("Still matching your library with RetroAchievements…" if self.app.ra.matching
                   else "RetroAchievements has no achievement set that matches this ROM. "
                        "Sets usually need specific ROM versions (No-Intro / Redump).")
            self.app.dialog(game.display_title, msg)
            return
        from .achievements import Achievements
        self.app.push(Achievements(self.app, game))

    def _open_tracker(self):
        if not self.app.ra.enabled:
            from .setup import RASetup
            self.app.push(RASetup(self.app))
            return
        if self.track_i == 0:
            from .tracker import Tracker
            self.app.push(Tracker(self.app, tab=1, on_pick=self._picked_from_grid))
        elif self.track_i == 1:
            from .newsets import NewSetsScreen
            self.app.push(NewSetsScreen(self.app))
        else:
            from .profile import FRIENDS, Profile
            self.app.push(Profile(self.app, tab=FRIENDS))
            self.app.friends.refresh(every=30)

    def on_game_closed(self, game):
        pass

    def on_resume(self):
        self._sync()

    def update(self, dt):
        self._sync()
        target = max(0, self.idx - 2) * (TILE + GAP)
        self.cam += (target - self.cam) * min(1, dt * 14)
        self.hero_fade = min(1.0, self.hero_fade + dt * 2.0)
        self.shot_t += dt
        if self.shot_t > self.SHOT_SECS:
            self.shot_t = 0.0
            self.shot_i += 1
        if self.app.ra.enabled and time.time() - self.last_ra_poll > 300:
            self.last_ra_poll = time.time()
            self.app.ra.refresh()
        if self.app.ra.enabled:
            self.app.friends.refresh(every=180)
            self.app.new_sets.refresh()

    # ------------------------------------------------------------ drawing
    def draw(self, s):
        self._draw_hero(s)
        self._draw_chips(s)
        self._draw_topright(s)
        if not self.cats or (not self.games and not self.on_ralib):
            self._draw_empty(s)
            return
        self._draw_row(s)
        self._draw_info(s)
        self._draw_tracker(s)
        status = self.app.library.scan_status or self.app.ra.match_status
        if status:
            gfx.blit_text(s, status, (ROW_X, gfx.H - 20), 15, gfx.TEXT_FAINT, anchor="midleft",
                          max_w=max(100, self.app.hints_left(self.hints()) - 40 - ROW_X))
        else:
            self._draw_xp_bar(s)

    SHOT_SECS = 7.0

    def _hero_source(self, g):
        """Image path for the background: rotate screenshots, fall back to blurred box art."""
        if not g or not self.app.artwork:
            return None, None
        shots = self.app.artwork.screenshots(g) if self.app.config["screenshot_backgrounds"] else []
        if g.id != self.shot_game:
            self.shot_game, self.shot_t, self.shot_i = g.id, 0.0, 0
        if shots:
            return shots[self.shot_i % len(shots)], "shot"
        art = self.app.artwork.get(g)
        return (art, "art") if art else (None, None)

    def _draw_hero(self, s):
        if self.hero and self.hero[1] and self.hero[1].get_size() != (gfx.W, gfx.H):
            self.hero = self.hero_prev = None     # window/screen shape changed
        g = self.cur_game()
        path, kind = self._hero_source(g)
        cur_path = self.hero[0] if self.hero else None
        if path != cur_path:
            surf = None
            if path:
                if kind == "shot":
                    surf = self.app.images.derive(("shot", gfx.W, gfx.H), path,
                                                  lambda im: gfx.blur(gfx.cover(im, gfx.W, gfx.H), 3))
                else:
                    surf = self.app.images.derive(("hero", gfx.W, gfx.H), path,
                                                  lambda im: gfx.blur(gfx.cover(im, gfx.W, gfx.H), 16))
                if surf is None:
                    path = cur_path  # not decoded yet, try next frame
            if path != cur_path:
                self.hero_prev = self.hero
                self.hero = (path, surf) if path else None
                self.hero_fade = 0.0
        if self.hero_prev and self.hero_prev[1] and self.hero_fade < 1:
            s.blit(self.hero_prev[1], (0, 0))
        if self.hero and self.hero[1]:
            img = self.hero[1]
            if self.hero_fade < 1:
                img = img.copy()
                img.set_alpha(int(255 * self.hero_fade))
            s.blit(img, (0, 0))
        shade = self.app.images.derived.get(("home_shade",))
        if shade is None:
            shade = gfx.vgradient((gfx.W, gfx.H), (4, 8, 20, 130), (4, 8, 20, 245))
            side = gfx.hgradient((gfx.W, gfx.H), (4, 8, 20, 170), (4, 8, 20, 10))
            shade.blit(side, (0, 0))
            self.app.images.derived[("home_shade",)] = shade
        s.blit(shade, (0, 0))

    def _draw_chips(self, s):
        x = 60 - self.chip_cam
        y = 28
        target = 0
        positions = []
        for i, (key, label, games) in enumerate(self.cats or [("home", "Home", [])]):
            w = gfx.measure(label, 18, True)[0] + 32
            positions.append((x, w))
            x += w + 10
        if positions:
            sx, sw = positions[min(self.cat_i, len(positions) - 1)]
            sx += self.chip_cam
            limit = self._topright_layout()[0].x - 30
            if sx + sw > limit:
                target = sx + sw - limit
            self.chip_cam += (target - self.chip_cam) * 0.25
        s.set_clip(pygame.Rect(40, 0, self._topright_layout()[0].x - 60, 80))
        for i, (key, label, games) in enumerate(self.cats or [("home", "Home", [])]):
            px, w = positions[i]
            r = pygame.Rect(px, y, w, 38)
            if r.right < 0 or r.x > gfx.W:
                continue
            active = i == self.cat_i
            if active:
                gfx.rrect(s, gfx.TEXT if self.focus == "chips" else (255, 255, 255, 60), r, 19)
                col = (10, 14, 30) if self.focus == "chips" else gfx.TEXT
            else:
                col = gfx.TEXT_DIM
            gfx.blit_text(s, label, r.center, 18, col, True, anchor="center")
        s.set_clip(None)

    def _topright_layout(self):
        """Right-hand block: [avatar name · pts · badge] [clock]. Returns (profile rect, clock x)."""
        ra = self.app.ra
        name = (ra.profile or {}).get("User") if ra.enabled and ra.profile else self.app.config["name"]
        clock_w = gfx.measure("00:00", 22, True)[0]
        text_w = gfx.measure(name or "", 17, True)[0]
        if ra.enabled and ra.profile:
            text_w = max(text_w, gfx.measure(f"{fmt_int(ra.profile.get('TotalPoints', 0))} pts", 14, True)[0])
        w = 8 + 36 + 10 + text_w + 16
        right = gfx.W - 40 - clock_w - 22
        return pygame.Rect(right - w, 24, w, 46), gfx.W - 40, name

    def _draw_topright(self, s):
        rect, clock_x, name = self._topright_layout()
        gfx.blit_text(s, time.strftime("%H:%M"), (clock_x, 47), 22, gfx.TEXT, True, anchor="midright")
        focused = self.focus == "profile"
        gfx.rrect(s, (255, 255, 255, 46) if focused else (255, 255, 255, 14), rect, 23)
        if focused:
            gfx.glow_border(s, rect, 23, self.app.t)
        ra = self.app.ra
        x = rect.x + 8
        if ra.enabled and ra.profile:
            av = url_image(self.app, media_url(ra.profile.get("UserPic", "")), 36, circle=True)
            draw_icon_slot(s, (x, rect.y + 5, 36, 36), av, 18)
            gfx.blit_text(s, name, (x + 46, rect.y + 4), 17, gfx.TEXT, True)
            gfx.blit_text(s, f"{fmt_int(ra.profile.get('TotalPoints', 0))} pts", (x + 46, rect.y + 25), 14,
                          gfx.GOLD, True)
        else:
            from .users import avatar
            avatar(self.app, s, self.app.config.profile, (x + 18, rect.centery), 36)
            gfx.blit_text(s, name, (x + 46, rect.centery), 17, gfx.TEXT, True, anchor="midleft")

    def _draw_empty(self, s):
        lib = self.app.library
        if lib.scanning:
            gfx.blit_text(s, lib.scan_status or "Scanning your games…", (gfx.W // 2, gfx.H // 2), 26, gfx.TEXT, anchor="center")
            return
        if lib.all and self.app.only_ra:
            ra = self.app.ra
            cy = gfx.H // 2
            if ra.matching or not ra.last_refresh:
                gfx.blit_text(s, "Finding your games that have achievements…", (gfx.W // 2, cy - 20), 28,
                              gfx.TEXT, True, anchor="center")
                gfx.blit_text(s, ra.match_status, (gfx.W // 2, cy + 20), 18, gfx.TEXT_DIM, anchor="center")
            else:
                gfx.blit_text(s, f"None of your {len(lib.all)} games matched a RetroAchievements set",
                              (gfx.W // 2, cy - 40), 28, gfx.TEXT, True, anchor="center", max_w=gfx.W - 120)
                gfx.blit_text(s, "Sets need specific ROM versions - check a game's Supported files in the RA Library "
                                 "(RB), or turn on Settings > Show games without achievements.",
                              (gfx.W // 2, cy + 6), 18, gfx.TEXT_DIM, anchor="center", max_w=gfx.W - 120)
            return
        if self._ralib_index() is not None:
            cx, cy = gfx.W // 2, gfx.H // 2 - 40
            gfx.blit_text(s, "No games yet", (cx, cy - 90), 36, gfx.TEXT, True, anchor="center")
            y = cy - 40
            for ln in gfx.wrap("Browse every game that has achievements and download one - it's unpacked "
                               "into the right folder automatically.", 20, 760, max_lines=3):
                gfx.blit_text(s, ln, (cx, y), 20, gfx.TEXT_DIM, anchor="center")
                y += 28
            btn = pygame.Rect(0, 0, 300, 54)
            btn.center = (cx, y + 44)
            gfx.rrect(s, gfx.TEXT, btn, 27)
            gfx.glow_border(s, btn, 27, self.app.t)
            gfx.blit_text(s, "Open RA Library", btn.center, 21, (10, 14, 30), True, anchor="center")
            folder = self.app.config["rom_dir"]
            y = btn.bottom + 34
            for ln in gfx.wrap(f"Already have games? Copy them into the console folders in {folder}, "
                               "then press Y to rescan.", 15, 760, max_lines=3):
                gfx.blit_text(s, ln, (cx, y), 15, gfx.TEXT_FAINT, anchor="center")
                y += 21
            return
        gfx.blit_text(s, "No games found yet", (gfx.W // 2, gfx.H // 2 - 50), 34, gfx.TEXT, True, anchor="center")
        gfx.blit_text(s, f"Put your ROMs in the system folders inside {self.app.config['rom_dir']}",
                      (gfx.W // 2, gfx.H // 2), 20, gfx.TEXT_DIM, anchor="center", max_w=1100)
        gfx.blit_text(s, "e.g. roms/snes, roms/gba, roms/psx — then press Y to rescan.",
                      (gfx.W // 2, gfx.H // 2 + 32), 20, gfx.TEXT_DIM, anchor="center")

    def hints(self):
        if not self.cats:
            return [("y", "Rescan"), ("start", "Settings")]
        if self.focus == "tracker":
            return [("a", "Open"), ("y", "Refresh"), ("start", "Settings")]
        if self.focus == "chips":
            return [("a", "Choose"), ("select", "Library"), ("start", "Settings")]
        if self.focus == "profile":
            return [("a", "Open profile"), ("start", "Settings")]
        g = self.cur_game()
        if not g:
            if not self.games and not self.on_ralib and self._ralib_index() is not None:
                return [("a", "Open RA Library"), ("y", "Rescan"), ("rb", "Next"), ("start", "Settings")]
            return [("a", "Browse RetroAchievements" if self.on_ralib else "Open Library"), ("lb", "Prev"),
                    ("rb", "Next"), ("start", "Settings")]
        return [("select", "Library"), ("start", "Settings")]   # Favourite / Achievements: next to Play

    def _game_hints(self, g):
        h = [("x", "Unfavourite" if self.app.config.is_fav(g.id) else "Favourite")]
        if self.app.ra.enabled:
            h.append(("y", "Achievements"))
        return h

    def _draw_row(self, s):
        games = self.games
        sel = self.idx
        first = max(0, int(self.cam // (TILE + GAP)) - 1)
        last = min(len(games), first + 12)
        for i in range(first, last + 1):
            x = ROW_X + i * (TILE + GAP) + (BIG - TILE if i > sel else 0) - self.cam
            if x > gfx.W:
                break
            size = BIG if i == sel else TILE
            if x + size < 0:
                continue
            r = pygame.Rect(int(x), ROW_Y, size, size)
            if i == len(games) and self.on_ralib:
                self._draw_ralib_card(s, r, i == sel)
            elif i == len(games):
                gfx.rrect(s, (255, 255, 255, 34), r, 14)
                cx, cy = r.center
                q = size // 6
                for ox in (-q - 4, 4):
                    for oy in (-q - 4, 4):
                        gfx.draw.rect(s, gfx.TEXT, (cx + ox, cy + oy, q, q), border_radius=4)
                if i == sel:
                    gfx.blit_text(s, "Game Library", (r.x, r.bottom + 14), 22, gfx.TEXT, True)
                    gfx.blit_text(s, f"{len(games)} games in {self.cats[self.cat_i][1]}", (r.x, r.bottom + 44),
                                  17, gfx.TEXT_DIM)
            else:
                g = games[i]
                tile = tile_surface(self.app, g, size)
                if i == sel:
                    sh = gfx.layer((size + 20, size + 20))
                    gfx.draw.rect(sh, (0, 0, 0, 110), sh.get_rect(), border_radius=22)
                    s.blit(sh, (r.x - 10, r.y + 4))
                s.blit(tile, r)
                if self.app.config.is_fav(g.id):
                    gfx.draw.circle(s, gfx.GOLD, (r.right - 14, r.y + 14), 6)
                award = self.app.ra.award_for(g)
                if award:
                    gfx.award_emblem(s, (r.x + 18, r.bottom - 18), award, 26 if i != sel else 32, self.app.t)
            if i == sel and self.focus == "row":
                gfx.glow_border(s, r, 14, self.app.t)

    def _draw_ralib_card(self, s, r, sel):
        gfx.rrect(s, gfx.ACCENT, r, 14)
        cx, cy = r.center
        gfx.award_emblem(s, (cx, cy - 8), "platinum", r.w // 2, self.app.t)
        gfx.blit_text(s, "RA", (cx, r.bottom - 22), r.w // 7, gfx.TEXT, True, anchor="center")
        if sel:
            gfx.blit_text(s, "RetroAchievements Library", (r.x, r.bottom + 14), 26, gfx.TEXT, True)
            gfx.blit_text(s, "Every console and every game with achievements. Pick one to open it in the "
                             "built-in browser; downloads are unpacked into the right roms folder.",
                          (r.x, r.bottom + 50), 17, gfx.TEXT_DIM, max_w=gfx.W - 2 * r.x)
            gfx.blit_text(s, "Only download games you're allowed to - e.g. your own dumps, homebrew or freeware.",
                          (r.x, r.bottom + 76), 15, gfx.TEXT_FAINT, max_w=gfx.W - 2 * r.x)

    def _draw_info(self, s):
        g = self.cur_game()
        if not g:
            return
        x, y = ROW_X, INFO_Y
        max_w = gfx.W - x - 60
        gfx.blit_text(s, g.system.name.upper(), (x, y), 15, gfx.ACCENT_HI, True, max_w=max_w)
        y += 24
        fs = 40
        while fs > 26 and gfx.measure(g.display_title, fs, True)[0] > max_w:
            fs -= 2
        gfx.blit_text(s, g.display_title, (x, y + (40 - fs) // 2), fs, gfx.TEXT, True, max_w=max_w)
        y += 46
        meta = []
        lp = self.app.config.last_played(g.id)
        meta.append(f"Last played {ago(lp)}" if lp else "Not played yet")
        pt = fmt_playtime(self.app.config.playtime(g.id))
        if pt:
            meta.append(pt)
        if g.discs:
            meta.append(f"{len(g.discs)} discs")
        if g.tags:
            meta.append(g.tags)
        gfx.blit_text(s, "  ·  ".join(meta), (x, y + 4), 17, gfx.TEXT_DIM, max_w=max_w)
        y += 34
        # Play button
        play = pygame.Rect(x, y, 150, 46)
        gfx.rrect(s, gfx.TEXT if self.focus == "row" else (255, 255, 255, 40), play, 23)
        gfx.draw.polygon(s, (10, 14, 30) if self.focus == "row" else gfx.TEXT,
                            [(play.x + 30, play.y + 14), (play.x + 30, play.y + 32), (play.x + 45, play.y + 23)])
        gfx.blit_text(s, "Play", (play.x + 58, play.centery), 20,
                      (10, 14, 30) if self.focus == "row" else gfx.TEXT, True, anchor="midleft")
        y += 58
        self._draw_game_ra(s, g, x, y, max_w)
        # the game's own actions sit next to its Play button (keeps the bottom-right short)
        if self.focus == "row":
            self.app.draw_hints(s, self._game_hints(g), left=play.right + 4, y=play.centery)

    def _draw_game_ra(self, s, g, x, y, max_w):
        ra = self.app.ra
        if not ra.enabled:
            gfx.blit_text(s, "Sign in to RetroAchievements in Settings to track achievements here.",
                          (x, y), 17, gfx.TEXT_FAINT, max_w=max_w)
            return
        if not g.system.ra:
            gfx.blit_text(s, "RetroAchievements doesn't support this system.", (x, y), 17, gfx.TEXT_FAINT)
            return
        if not g.ra_game_id:
            msg = "Looking for achievements…" if ra.matching else "No achievement set found for this ROM."
            gfx.blit_text(s, msg, (x, y), 17, gfx.TEXT_FAINT)
            return
        prog = ra.game_progress(g.ra_game_id)
        total = g.extra.get("ra_count", 0)
        if not prog:
            gfx.blit_text(s, f"{total} achievements · loading your progress…", (x, y), 17, gfx.TEXT_DIM)
            return
        total = int(prog.get("NumAchievements") or total or 0)
        got = int(prog.get("NumAwardedToUser") or 0)
        got_hc = int(prog.get("NumAwardedToUserHardcore") or 0)
        achs = list((prog.get("Achievements") or {}).values())
        pts_total = sum(int(a.get("Points", 0)) for a in achs)
        pts_got = sum(int(a.get("Points", 0)) for a in achs if a.get("DateEarned") or a.get("DateEarnedHardcore"))
        from ...progression import AWARD_INFO, award_from_ra
        award = award_from_ra(prog.get("HighestAwardKind") or "", got, got_hc, total)
        label = f"{got} / {total} achievements"
        if got_hc:
            label += f"  ({got_hc} hardcore)"
        trophy_col = gfx.GOLD if total and got >= total else gfx.TEXT
        pts = f"{pts_got} / {pts_total} pts"
        pts_w = gfx.measure(pts, 17)[0]
        t = gfx.blit_text(s, label, (x, y), 19, trophy_col, True, max_w=440 - pts_w - 16)
        gfx.blit_text(s, pts, (max(x + 440, t.right + 16 + pts_w), y + 1), 17, gfx.GOLD, anchor="topright")
        if award:
            info = AWARD_INFO[award]
            gfx.award_emblem(s, (x + 474, y + 18), award, 30, self.app.t)
            gfx.blit_text(s, info["name"], (x + 496, y + 7), 18, info["color"], True)
        gfx.progress_bar(s, (x, y + 30, 440, 8), got / total if total else 0, gfx.GOLD if got >= total > 0 else gfx.ACCENT_HI)
        # next achievements: locked first (by display order), then recently earned
        locked = sorted((a for a in achs if not (a.get("DateEarned") or a.get("DateEarnedHardcore"))),
                        key=lambda a: int(a.get("DisplayOrder") or 0))
        earned = sorted((a for a in achs if a.get("DateEarned") or a.get("DateEarnedHardcore")),
                        key=lambda a: a.get("DateEarnedHardcore") or a.get("DateEarned") or "", reverse=True)
        if locked:
            nxt = locked[0]
            gfx.blit_text(s, f"Next: {nxt.get('Title', '')} — {nxt.get('Description', '')}",
                          (x, y + 46), 15, gfx.TEXT_DIM, max_w=max_w)
        show = (locked[:8] + earned)[:8]
        bx = x
        by = y + 70
        size = max(28, min(48, TRACK_Y - 14 - by))
        for a in show:
            is_locked = a in locked
            img = badge(self.app, a.get("BadgeName", "00000"), size, locked=is_locked)
            draw_icon_slot(s, (bx, by, size, size), img, 6)
            bx += size + 8
            if bx + size > x + max_w:
                break

    CARDS = ["Continue hunting", "New on RetroAchievements", "Friends"]

    def _draw_tracker(self, s):
        ra = self.app.ra
        gap = 20
        w = (gfx.W - 2 * ROW_X - 2 * gap) / 3
        for i, title in enumerate(self.CARDS):
            r = pygame.Rect(int(ROW_X + i * (w + gap)), TRACK_Y, int(w), TRACK_H)
            sel = self.focus == "tracker" and self.track_i == i
            gfx.rrect(s, (12, 18, 38, 215), r, 16)
            gfx.rrect(s, (255, 255, 255, 18), r, 16, 1)
            if sel:
                gfx.glow_border(s, r, 16, self.app.t)
            gfx.blit_text(s, title, (r.x + 18, r.y + 14), 15, gfx.TEXT_DIM, True)
            inner = pygame.Rect(r.x + 18, r.y + 42, r.w - 36, r.h - 54)
            if not ra.enabled:
                if i == 0:
                    for k, ln in enumerate(gfx.wrap("Not signed in. Go down here and press A, or open Settings, "
                                                    "to connect your RetroAchievements account.", 16, inner.w,
                                                    max_lines=4)):
                        gfx.blit_text(s, ln, (inner.x, inner.y + k * 22), 16, gfx.TEXT_FAINT)
            elif ra.error and not ra.profile:
                if i == 0:
                    for k, ln in enumerate(gfx.wrap(ra.error, 16, inner.w, max_lines=4)):
                        gfx.blit_text(s, ln, (inner.x, inner.y + k * 22), 16, gfx.RED)
            elif not ra.profile and i == 0:
                gfx.blit_text(s, "Loading…", inner.topleft, 16, gfx.TEXT_FAINT)
            else:
                [self._card_hunting, self._card_new, self._card_friends][i](s, inner)

    def _card_new(self, s, r):
        ns = self.app.new_sets
        items = ns.list[:3]
        if not items:
            gfx.blit_text(s, ns.error or "Loading…", r.topleft, 15, gfx.RED if ns.error else gfx.TEXT_FAINT,
                          max_w=r.w)
            return
        have = {g.ra_game_id for g in self.app.library.all if g.ra_game_id}
        y = r.y
        for it in items:
            draw_icon_slot(s, (r.x, y, 32, 32), url_image(self.app, it["icon"], 32, radius=5), 5)
            right = ago(it["added"]) if it["added"] else ""
            if it["GameID"] in have:
                right = "In library"
            rw = gfx.measure(right, 13)[0] + 10 if right else 0
            gfx.blit_text(s, it["Title"], (r.x + 42, y - 1), 15, gfx.TEXT, True, max_w=r.w - 42 - rw)
            gfx.blit_text(s, it["ConsoleName"], (r.x + 42, y + 18), 13, gfx.TEXT_DIM, max_w=r.w - 42 - rw)
            if right:
                gfx.blit_text(s, right, (r.right, y + 1), 13, gfx.GREEN if right == "In library" else gfx.TEXT_FAINT,
                              anchor="topright")
            y += 38

    def _card_friends(self, s, r):
        fr = self.app.friends
        items = fr.list[:3]
        if not items:
            msg = (fr.error if fr.error else "Loading…" if not fr.loaded else
                   "Follow people on RetroAchievements to see what they're playing. Press A to add a friend.")
            for k, ln in enumerate(gfx.wrap(msg, 15, r.w, max_lines=4)):
                gfx.blit_text(s, ln, (r.x, r.y + k * 21), 15, gfx.RED if fr.error else gfx.TEXT_FAINT)
            return
        y = r.y
        for f in items:
            draw_icon_slot(s, (r.x, y, 32, 32), url_image(self.app, f["pic"], 32, circle=True), 16)
            if f["playing"]:
                gfx.draw.circle(s, (12, 18, 38), (r.x + 28, y + 28), 7)
                gfx.draw.circle(s, gfx.GREEN, (r.x + 28, y + 28), 5)
            gfx.blit_text(s, f["user"], (r.x + 42, y - 1), 15, gfx.TEXT, True, max_w=r.w - 42)
            if f["playing"]:
                line, col = (f"Playing {f['game']}" if f["game"] else "Playing now"), gfx.GREEN
            elif f["game"]:
                line, col = f"{f['game']}" + (f"  ·  {ago(f['last'])}" if f["last"] else ""), gfx.TEXT_DIM
            else:
                line, col = "Hasn't played anything yet", gfx.TEXT_FAINT
            gfx.blit_text(s, line, (r.x + 42, y + 18), 13, col, max_w=r.w - 42)
            y += 38

    def _draw_xp_bar(self, s):
        """Level + XP along the bottom. Fixed length: the bar ends where the Friends card begins."""
        prog = self.app.ra.prog
        if not prog:
            return
        y = gfx.H - 21
        gap = 20
        card_w = (gfx.W - 2 * ROW_X - 2 * gap) / 3
        bar_end = int(ROW_X + 2 * (card_w + gap)) - 24
        nums = f"{fmt_int(prog.into)} / {fmt_int(prog.need)} XP"
        nw = gfx.measure(nums, 14)[0]
        # the same length whatever is selected: leave room for the widest prompts the home screen shows
        sets = [self.hints(), [("a", "Open"), ("y", "Refresh"), ("start", "Settings")],
                [("a", "Choose"), ("select", "Library"), ("start", "Settings")],
                [("a", "Open profile"), ("start", "Settings")], [("select", "Library"), ("start", "Settings")]]
        limit = min(self.app.hints_left(h) for h in sets) - 30
        bar_end = min(bar_end, limit - 14 - nw)
        x = ROW_X
        gfx.level_badge(s, (x + 12, y), prog.level, 24, self.app.t, number=False)
        t = gfx.blit_text(s, f"Lv {prog.level}", (x + 32, y), 16, gfx.TEXT, True, anchor="midleft")
        x = t.right + 14
        if bar_end - x > 60:
            gfx.progress_bar(s, (x, y - 4, bar_end - x, 8), prog.frac, gfx.tier_bar_color(prog.level, self.app.t))
            x = bar_end + 14
        gfx.blit_text(s, nums, (x, y), 14, gfx.TEXT_DIM, anchor="midleft")

    def hunting(self):
        comp = [c for c in self.app.ra.completion
                if int(c.get("MaxPossible") or 0) and int(c.get("NumAwarded") or 0) < int(c.get("MaxPossible") or 0)]
        comp.sort(key=lambda c: c.get("MostRecentAwardedDate") or "", reverse=True)
        return comp

    def _card_hunting(self, s, r):
        comp = self.hunting()[:3]
        if not comp:
            gfx.blit_text(s, "Start a game with achievements!", r.topleft, 16, gfx.TEXT_FAINT)
            return
        y = r.y
        for c in comp:
            img = url_image(self.app, media_url(c.get("ImageIcon", "")), 32, radius=5)
            draw_icon_slot(s, (r.x, y, 32, 32), img, 5)
            got, mx = int(c.get("NumAwarded") or 0), int(c.get("MaxPossible") or 1)
            gfx.blit_text(s, c.get("Title", ""), (r.x + 42, y - 1), 15, gfx.TEXT, True, max_w=r.w - 110)
            gfx.blit_text(s, f"{got}/{mx}", (r.right, y), 14, gfx.TEXT_DIM, anchor="topright")
            gfx.progress_bar(s, (r.x + 42, y + 22, r.w - 42, 6), got / mx)
            y += 38
