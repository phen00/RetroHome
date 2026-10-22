"""Your profile: XP and level, tracked play time, achievements per game, trophies and level crests."""
import pygame

from ...progression import (AWARD_MYTHIC, AWARD_PLATINUM, AWARD_INFO, award_from_ra)
from ...retroach import media_url
from .. import gfx
from ..app import Screen
from .common import ago, draw_icon_slot, fmt_int, tile_surface, url_image

TABS = ["Overview", "Played games", "Trophy case", "Friends"]
FRIENDS = 3
RECENT = 5


def fmt_hours(secs):
    secs = int(secs or 0)
    h, m = secs // 3600, (secs % 3600) // 60
    if h:
        return f"{h}h {m:02d}m"
    return f"{m}m" if m else ("<1m" if secs else "0m")


class Profile(Screen):
    def __init__(self, app, tab=0):
        super().__init__(app)
        self.tab = tab
        self.sel = 0
        self.scroll = 0

    # ------------------------------------------------------------ data
    def _recent(self):
        rows = self._played()
        rows.sort(key=lambda r: -(r[2].get("last") or 0))
        return rows[:RECENT]

    def _played(self):
        """[(game or None, game_id, history entry)] sorted by play time."""
        hist = self.app.config.profile.get("history", {}) or {}
        lib = self.app.library.by_id
        rows = [(lib.get(gid), gid, e) for gid, e in hist.items() if e.get("count") or e.get("playtime")]
        rows.sort(key=lambda r: (-(r[2].get("playtime") or 0), -(r[2].get("last") or 0)))
        return rows

    def _ra_for(self, game):
        """(got, total, award) for a library game from RetroAchievements data, or None."""
        if not game or not game.ra_game_id:
            return None
        ra = self.app.ra
        prog = ra.progress.get(game.ra_game_id)
        if prog:
            achs = list((prog.get("Achievements") or {}).values())
            got = sum(1 for a in achs if a.get("DateEarned") or a.get("DateEarnedHardcore"))
            hc = sum(1 for a in achs if a.get("DateEarnedHardcore"))
            return got, len(achs), award_from_ra(prog.get("HighestAwardKind") or "", got, hc, len(achs))
        c = ra.library_completion(game)
        if c:
            total = int(c.get("MaxPossible") or 0)
            got = int(c.get("NumAwarded") or 0)
            return got, total, award_from_ra(c.get("HighestAwardKind"), got, int(c.get("NumAwardedHardcore") or 0),
                                             total)
        return 0, int(game.extra.get("ra_count") or 0), ""

    def _trophies(self):
        out = []
        for c in self.app.ra.completion:
            a = award_from_ra(c.get("HighestAwardKind"), int(c.get("NumAwarded") or 0),
                              int(c.get("NumAwardedHardcore") or 0), int(c.get("MaxPossible") or 0))
            if a:
                out.append((AWARD_INFO[a]["rank"], c.get("HighestAwardDate") or c.get("MostRecentAwardedDate") or "",
                            a, c))
        out.sort(key=lambda x: x[1], reverse=True)
        out.sort(key=lambda x: -x[0])
        return out

    def _rows(self):
        return self._recent() if self.tab == 0 else self._played() if self.tab == 1 else []

    def _list_len(self):
        if self.tab == FRIENDS:
            return len(self.app.friends.list) + 1     # first row: "Add a friend"
        return len(self._rows()) if self.tab in (0, 1) else len(self._trophies())

    def update(self, dt):
        if self.tab == FRIENDS:
            self.app.friends.refresh(every=60)      # keep "playing now" fresh while you look

    # ------------------------------------------------------------ friends
    def _add_friend(self):
        if not self.app.ra.enabled:
            self.app.toast("Sign in to RetroAchievements first (Settings)")
            return
        from .keyboard import Keyboard

        def entered(name):
            name = (name or "").strip()
            if name:
                from urllib.parse import quote
                from .ralib import open_page
                open_page(self.app, f"https://retroachievements.org/user/{quote(name)}", f"Add {name}")
        self.app.push(Keyboard(self.app, "Friend's RetroAchievements username", "", entered,
                               hint="Their page opens - press Follow there (sign in to RA the first time)"))

    def _friend_action(self, a):
        if self.sel == 0:
            if a == "a":
                self._add_friend()
            return
        fl = self.app.friends.list
        if self.sel - 1 >= len(fl):
            return
        f = fl[self.sel - 1]
        if not f["game_id"]:
            return
        if a == "a":
            from .achievements import Achievements
            self.app.push(Achievements.for_ra_game(self.app, {"GameID": f["game_id"], "GameTitle": f["game"],
                                                              "ConsoleName": f["console"], "ImageIcon": ""}))
        elif a == "x":
            game = next((g for g in self.app.library.all if g.ra_game_id == f["game_id"]), None)
            if game:
                self.app.launch(game)
            else:
                self.app.toast(f"{f['game']} isn't in your library")

    # ------------------------------------------------------------ input
    def on_action(self, a):
        if a == "b":
            self.app.pop()
        elif a in ("lb", "rb", "left", "right"):
            self.tab = (self.tab + (1 if a in ("rb", "right") else -1)) % len(TABS)
            self.sel = self.scroll = 0
            if self.tab == FRIENDS:
                self.app.friends.refresh(every=30)
        elif a in ("up", "down"):
            n = self._list_len()
            self.sel = max(0, min(max(0, n - 1), self.sel + (1 if a == "down" else -1)))
        elif a == "y":
            self.app.ra.refresh(force=True)
            if self.tab == FRIENDS:
                self.app.friends.refresh(force=True)
            self.app.toast("Refreshing…")
        elif self.tab == FRIENDS and a in ("a", "x"):
            self._friend_action(a)
        elif a in ("a", "x") and self.tab in (0, 1):
            rows = self._rows()
            if not rows:
                return
            game = rows[min(self.sel, len(rows) - 1)][0]
            if game is None:
                self.app.toast("That game isn't in your library any more")
            elif a == "x":
                self.app.launch(game)
            elif game.ra_game_id and self.app.ra.enabled:
                from .achievements import Achievements
                self.app.push(Achievements(self.app, game))
            else:
                self.app.toast("No RetroAchievements set for this game")
        elif a == "a" and self.tab == 2:
            items = self._trophies()
            if items:
                from .achievements import Achievements
                self.app.push(Achievements.for_ra_game(self.app, items[min(self.sel, len(items) - 1)][3]))

    # ------------------------------------------------------------ drawing
    def draw(self, s):
        ra = self.app.ra
        cfg = self.app.config
        x = 60
        name = (ra.profile or {}).get("User") or cfg["name"]
        gfx.blit_text(s, name, (x, 30), 34, gfx.TEXT, True)
        sub = f"RetroAchievements: {cfg['ra_user']}" if cfg["ra_user"] else "RetroAchievements not linked"
        remote = cfg["remote"] or {}
        if remote.get("token"):
            sub += f"   ·   Online as {remote.get('username')}" + \
                (f" ({self.app.online_status})" if self.app.online_status else "")
        gfx.blit_text(s, sub, (x, 74), 16, gfx.TEXT_DIM, max_w=gfx.W - 120)
        tx = x
        for i, t in enumerate(TABS):
            w = gfx.measure(t, 17, True)[0] + 30
            r = pygame.Rect(tx, 106, w, 38)
            on = i == self.tab
            gfx.rrect(s, gfx.TEXT if on else (255, 255, 255, 28), r, 19)
            gfx.blit_text(s, t, r.center, 17, (10, 14, 30) if on else gfx.TEXT, True, anchor="center")
            tx += w + 10
        [self._overview, self._played_tab, self._trophy_case, self._friends_tab][self.tab](s)

    # ------------------------------------------------------------ overview
    def _shelf(self):
        """Mythic first, then Platinum, newest first within each."""
        items = [t for t in self._trophies() if t[2] in (AWARD_MYTHIC, AWARD_PLATINUM)]
        return items

    def _overview(self, s):
        ra = self.app.ra
        p = ra.prog
        played = self._played()
        total_secs = sum(e.get("playtime", 0) for _, _, e in played)
        unlocked = sum(int(c.get("NumAwarded") or 0) for c in ra.completion)
        # ---- level card
        card = pygame.Rect(60, 166, gfx.W - 120, 150)
        gfx.rrect(s, (255, 255, 255, 14), card, 18)
        if p:
            gfx.level_badge(s, (card.x + 92, card.centery - 2), p.level, 104, self.app.t)
            x = card.x + 190
            bw = card.right - 30 - x
            gfx.blit_text(s, f"Level {p.level}", (x, card.y + 18), 32, gfx.TEXT, True)
            gfx.blit_text(s, f"{fmt_int(p.xp)} XP", (card.right - 30, card.y + 28), 16, gfx.TEXT_DIM,
                          anchor="topright")
            gfx.progress_bar(s, (x, card.y + 64, bw, 12), p.frac, gfx.tier_bar_color(p.level))
            gfx.blit_text(s, f"{fmt_int(p.need - p.into)} XP to level {p.level + 1}", (x, card.y + 84), 15,
                          gfx.TEXT_DIM)
            chips = [(fmt_hours(total_secs), "played"), (str(len(played)), "games")]
            cx = x
            for val, label in chips:
                vw = gfx.measure(val, 16, True)[0]
                lw = gfx.measure(label, 14)[0]
                pill = pygame.Rect(cx, card.y + 110, vw + lw + 34, 28)
                gfx.rrect(s, (255, 255, 255, 20), pill, 14)
                gfx.blit_text(s, val, (pill.x + 14, pill.centery), 16, gfx.TEXT, True, anchor="midleft")
                gfx.blit_text(s, label, (pill.x + 20 + vw, pill.centery + 1), 14, gfx.TEXT_DIM, anchor="midleft")
                cx = pill.right + 10
        else:
            msg = "Link RetroAchievements in Settings to start levelling up." if not ra.enabled else (
                ra.error or "Loading your level…")
            gfx.blit_text(s, msg, (card.x + 30, card.y + 40), 20, gfx.TEXT_FAINT)
            gfx.blit_text(s, f"{fmt_hours(total_secs)} played in RetroHome  ·  {len(played)} games",
                          (card.x + 30, card.y + 76), 16, gfx.TEXT_DIM)
        # ---- RetroAchievements numbers
        top = card.bottom + 18
        if ra.profile:
            top = self._ra_stats(s, pygame.Rect(60, top, gfx.W - 120, 74), ra.profile, unlocked) + 18
        # ---- bottom: recently played (left) + trophy shelf (right)
        gap = 20
        right_w = int((gfx.W - 120 - gap) * 0.40)
        left = pygame.Rect(60, top, gfx.W - 120 - gap - right_w, gfx.H - 56 - top)
        shelf = pygame.Rect(left.right + gap, top, right_w, left.h)
        gfx.rrect(s, (255, 255, 255, 14), left, 18)
        gfx.rrect(s, (255, 255, 255, 14), shelf, 18)
        gfx.blit_text(s, "Recently played", (left.x + 22, left.y + 16), 18, gfx.TEXT, True)
        rows = self._recent()
        if not rows:
            gfx.blit_text(s, "Games you launch from RetroHome show up here.", (left.x + 22, left.y + 56), 16,
                          gfx.TEXT_FAINT)
        else:
            y = left.y + 50
            row_h = 62
            for i, (game, gid, e) in enumerate(rows):
                if y + row_h > left.bottom - 6:
                    break
                r = pygame.Rect(left.x + 10, y, left.w - 20, row_h - 6)
                self._game_row(s, r, game, gid, e, i == self.sel, compact=True)
                y += row_h
        self._draw_shelf(s, shelf)

    def _ra_stats(self, s, box, prof, unlocked):
        """Row of stat tiles: points, softcore points, RetroPoints, achievements, site rank."""
        rank, ranked = prof.get("Rank"), prof.get("TotalRanked")
        tiles = [(fmt_int(prof.get("TotalPoints") or 0), "Points", gfx.GOLD),
                 (fmt_int(prof.get("TotalSoftcorePoints") or 0), "Softcore points", gfx.TEXT),
                 (fmt_int(prof.get("TotalTruePoints") or 0), "RetroPoints", gfx.ACCENT_HI),
                 (fmt_int(unlocked), "Achievements", gfx.TEXT),
                 (f"#{fmt_int(rank)}" if rank else "–",
                  f"Site rank of {fmt_int(ranked)}" if rank and ranked else "Site rank", gfx.TEXT)]
        gap = 14
        w = (box.w - gap * (len(tiles) - 1)) / len(tiles)
        for i, (val, label, col) in enumerate(tiles):
            r = pygame.Rect(int(box.x + i * (w + gap)), box.y, int(w), box.h)
            gfx.rrect(s, (255, 255, 255, 14), r, 16)
            gfx.blit_text(s, val, (r.x + 20, r.y + 12), 26, col, True, max_w=r.w - 30)
            gfx.blit_text(s, label, (r.x + 20, r.y + 46), 14, gfx.TEXT_DIM, max_w=r.w - 30)
        return box.bottom

    def _draw_shelf(self, s, box):
        items = self._shelf()
        mythic = sum(1 for t in items if t[2] == AWARD_MYTHIC)
        plat = len(items) - mythic
        gfx.blit_text(s, "Trophy shelf", (box.x + 22, box.y + 16), 18, gfx.TEXT, True)
        gfx.blit_text(s, f"{mythic} Mythic  ·  {plat} Platinum", (box.right - 22, box.y + 19), 14, gfx.TEXT_DIM,
                      anchor="topright")
        if not items:
            gfx.blit_text(s, "Beat a game to put it on the shelf.", (box.x + 22, box.y + 56), 15,
                          gfx.TEXT_FAINT, max_w=box.w - 44)
            return
        size, gap = 64, 14
        cols = max(1, (box.w - 44 + gap) // (size + gap))
        rows = max(1, (box.h - 70 + gap) // (size + gap))
        cap = cols * rows
        show = items[:cap - 1] if len(items) > cap else items
        for i, (_, _, award, c) in enumerate(show):
            col, row = i % cols, i // cols
            x = box.x + 22 + col * (size + gap)
            y = box.y + 52 + row * (size + gap)
            icon = url_image(self.app, media_url(c.get("ImageIcon", "")), size, radius=12)
            draw_icon_slot(s, (x, y, size, size), icon, 12)
            ring = AWARD_INFO[award]["color"]
            gfx.draw.rect(s, ring, (x - 2, y - 2, size + 4, size + 4), 2, border_radius=14)
            gfx.award_emblem(s, (x + size - 4, y + 4), award, 26, self.app.t)
        if len(items) > len(show):
            i = len(show)
            x = box.x + 22 + (i % cols) * (size + gap)
            y = box.y + 52 + (i // cols) * (size + gap)
            gfx.rrect(s, (255, 255, 255, 22), (x, y, size, size), 12)
            gfx.blit_text(s, f"+{len(items) - len(show)}", (x + size / 2, y + size / 2), 20, gfx.TEXT, True,
                          anchor="center")

    # ------------------------------------------------------------ rows
    def _game_row(self, s, r, game, gid, e, sel, compact=False):
        gfx.rrect(s, gfx.PANEL_HI if sel else (255, 255, 255, 10), r, 12)
        if sel:
            gfx.glow_border(s, r, 12, self.app.t)
        ts = r.h - 12
        if game:
            s.blit(tile_surface(self.app, game, ts, 8), (r.x + 6, r.y + 6))
            title, system = game.display_title, game.system.label
        else:
            draw_icon_slot(s, (r.x + 6, r.y + 6, ts, ts), None, 8)
            title, system = gid.split("/", 1)[-1], gid.split("/", 1)[0]
        info = self._ra_for(game)
        ach_w = 170
        tx = r.x + ts + 20
        text_w = r.right - tx - ach_w - (24 if compact else 130)
        gfx.blit_text(s, title, (tx, r.y + r.h / 2 - 20), 17, gfx.TEXT, True, max_w=text_w)
        bits = [system]
        if compact:
            bits.append(fmt_hours(e.get("playtime", 0)))
        else:
            n = e.get("count", 0)
            bits.append(f"{n} session{'s' if n != 1 else ''}")
        if e.get("last"):
            bits.append(ago(e["last"]))
        gfx.blit_text(s, "  ·  ".join(bits), (tx, r.y + r.h / 2 + 2), 14, gfx.TEXT_DIM, max_w=text_w)
        ax = r.right - ach_w - (16 if compact else 130)
        if info and info[1]:
            got, tot, award = info
            gfx.blit_text(s, f"{got} / {tot}", (ax, r.y + r.h / 2 - 18), 15, gfx.GOLD if got else gfx.TEXT_DIM, True)
            gfx.progress_bar(s, (ax, r.y + r.h / 2 + 6, ach_w - 34, 6), got / tot,
                             gfx.GOLD if got == tot else gfx.ACCENT_HI)
            if award:
                gfx.award_emblem(s, (ax + ach_w - 14, r.y + r.h / 2 - 8), award, 24, self.app.t)
        elif self.app.ra.enabled:
            gfx.blit_text(s, "No set", (ax, r.centery), 14, gfx.TEXT_FAINT, anchor="midleft")
        if not compact:
            gfx.blit_text(s, fmt_hours(e.get("playtime", 0)), (r.right - 20, r.centery), 20, gfx.TEXT, True,
                          anchor="midright")

    def _scroll_rows(self, n, y0, row_h):
        visible = max(1, (gfx.H - 60 - y0) // row_h)
        self.sel = min(self.sel, max(0, n - 1))
        if self.sel < self.scroll:
            self.scroll = self.sel
        elif self.sel >= self.scroll + visible:
            self.scroll = self.sel - visible + 1
        return range(self.scroll, min(n, self.scroll + visible))

    def _played_tab(self, s):
        rows = self._played()
        total = sum(e.get("playtime", 0) for _, _, e in rows)
        gfx.blit_text(s, f"{len(rows)} games  ·  {fmt_hours(total)} played in RetroHome", (60, 160), 16,
                      gfx.TEXT_DIM)
        if not rows:
            gfx.blit_text(s, "Play something! Time is recorded from launch until the emulator closes.",
                          (60, 200), 18, gfx.TEXT_FAINT)
            return
        y0, row_h = 192, 72
        for i in self._scroll_rows(len(rows), y0, row_h):
            game, gid, e = rows[i]
            r = pygame.Rect(60, y0 + (i - self.scroll) * row_h, gfx.W - 120, row_h - 8)
            self._game_row(s, r, game, gid, e, i == self.sel)

    def _trophy_case(self, s):
        items = self._trophies()
        if not items:
            gfx.blit_text(s, "Beat a game to earn your first Platinum.", (60, 180), 20, gfx.TEXT_FAINT)
            return
        y0, row_h = 166, 80
        for i in self._scroll_rows(len(items), y0, row_h):
            _, date, award, c = items[i]
            r = pygame.Rect(60, y0 + (i - self.scroll) * row_h, gfx.W - 120, row_h - 10)
            sel = i == self.sel
            gfx.rrect(s, gfx.PANEL_HI if sel else gfx.PANEL, r, 14)
            if sel:
                gfx.glow_border(s, r, 14, self.app.t)
            icon = url_image(self.app, media_url(c.get("ImageIcon", "")), 56, radius=8)
            draw_icon_slot(s, (r.x + 7, r.y + 7, 56, 56), icon, 8)
            gfx.blit_text(s, c.get("Title", ""), (r.x + 80, r.y + 10), 20, gfx.TEXT, True, max_w=r.w - 420)
            gfx.blit_text(s, "  ·  ".join(b for b in (c.get("ConsoleName") or "",
                                                      f"{c.get('MaxPossible', 0)} achievements") if b),
                          (r.x + 80, r.y + 38), 15, gfx.TEXT_DIM)
            info = AWARD_INFO[award]
            gfx.award_emblem(s, (r.right - 200, r.centery), award, 36, self.app.t)
            gfx.blit_text(s, info["name"], (r.right - 176, r.y + 14), 19, info["color"], True)
            gfx.blit_text(s, str(date)[:10], (r.right - 176, r.y + 40), 14, gfx.TEXT_FAINT)

    def _friends_tab(self, s):
        fr = self.app.friends
        n_play = len(fr.playing)
        if not self.app.ra.enabled:
            gfx.blit_text(s, "Sign in to RetroAchievements in Settings to see your friends.", (60, 180), 20,
                          gfx.TEXT_FAINT)
            return
        status = ("Loading…" if fr.loading and not fr.loaded else fr.error if fr.error and not fr.loaded else
                  f"{len(fr.list)} following  ·  {n_play} playing now")
        gfx.blit_text(s, status, (60, 160), 16, gfx.RED if fr.error and not fr.loaded else gfx.TEXT_DIM)
        gfx.blit_text(s, "Friends are the people you follow on RetroAchievements", (gfx.W - 60, 160), 14,
                      gfx.TEXT_FAINT, anchor="topright")
        y0, row_h = 192, 84
        for i in self._scroll_rows(len(fr.list) + 1, y0, row_h):
            r = pygame.Rect(60, y0 + (i - self.scroll) * row_h, gfx.W - 120, row_h - 10)
            sel = i == self.sel
            gfx.rrect(s, gfx.PANEL_HI if sel else gfx.PANEL, r, 14)
            if sel:
                gfx.glow_border(s, r, 14, self.app.t)
            if i == 0:
                gfx.rrect(s, (255, 255, 255, 24), (r.x + 9, r.y + 9, 56, 56), 28)
                gfx.blit_text(s, "+", (r.x + 37, r.y + 35), 34, gfx.TEXT, True, anchor="center")
                gfx.blit_text(s, "Add a friend", (r.x + 84, r.y + 12), 20, gfx.TEXT, True)
                gfx.blit_text(s, "Type their RetroAchievements username, then press Follow on their page",
                              (r.x + 84, r.y + 40), 15, gfx.TEXT_DIM, max_w=r.w - 110)
                continue
            self._friend_row(s, r, fr.list[i - 1])
        if fr.loaded and not fr.list:
            gfx.blit_text(s, "You're not following anyone yet.", (60, y0 + row_h + 20), 18, gfx.TEXT_FAINT)

    def _friend_row(self, s, r, f):
        av = url_image(self.app, f["pic"], 56, circle=True)
        draw_icon_slot(s, (r.x + 9, r.y + 9, 56, 56), av, 28)
        if f["playing"]:
            gfx.draw.circle(s, (12, 18, 34), (r.x + 58, r.y + 58), 10)
            gfx.draw.circle(s, gfx.GREEN, (r.x + 58, r.y + 58), 7)
        tx = r.x + 84
        icon_w = 64 if f["game"] else 0
        name_w = gfx.blit_text(s, f["user"], (tx, r.y + 10), 20, gfx.TEXT, True, max_w=360).w
        x = tx + name_w + 12
        if f["follows_me"]:
            tag = "Friends"
            tw = gfx.measure(tag, 12, True)[0] + 16
            gfx.rrect(s, (255, 255, 255, 26), (x, r.y + 13, tw, 20), 10)
            gfx.blit_text(s, tag, (x + tw / 2, r.y + 23), 12, gfx.TEXT_DIM, True, anchor="center")
        gfx.blit_text(s, f"{fmt_int(f['points'])} pts", (r.right - 24 - icon_w - (14 if icon_w else 0), r.y + 12), 15,
                      gfx.GOLD, True, anchor="topright")
        line_w = r.right - tx - icon_w - 40
        if f["playing"]:
            what = f"Playing {f['game']}" + (f"  ·  {f['console']}" if f["console"] else "") if f["game"] else "Playing now"
            gfx.blit_text(s, what, (tx, r.y + 38), 15, gfx.GREEN, True, max_w=line_w)
            if f["presence"] and f["presence"] != f["game"]:
                gfx.blit_text(s, f["presence"], (tx, r.y + 56), 13, gfx.TEXT_DIM, max_w=line_w)
        elif f["game"]:
            when = f"  ·  {ago(f['last'])}" if f["last"] else ""
            gfx.blit_text(s, f"Last played {f['game']}{when}", (tx, r.y + 40), 15, gfx.TEXT_DIM, max_w=line_w)
        else:
            gfx.blit_text(s, "Hasn't played anything yet", (tx, r.y + 40), 15, gfx.TEXT_FAINT)
        if f["game"]:
            icon = url_image(self.app, f["icon"], 56, radius=8)
            draw_icon_slot(s, (r.right - 9 - 56, r.y + 9, 56, 56), icon, 8)

    def hints(self):
        h = []
        if self.tab == FRIENDS:
            fl = self.app.friends.list
            if self.sel == 0:
                h = [("a", "Add friend")]
            elif self.sel - 1 < len(fl) and fl[self.sel - 1]["game_id"]:
                h = [("a", "Their game"), ("x", "Play it")]
        elif self.tab in (0, 1) and self._rows():
            h = [("a", "Achievements"), ("x", "Play")]
        elif self.tab == 2:
            h = [("a", "Achievements")]
        return h + [("lb", "Prev tab"), ("rb", "Next tab"), ("y", "Refresh"), ("b", "Back")]


__all__ = ["Profile"]
