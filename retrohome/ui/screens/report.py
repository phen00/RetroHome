"""Post-game session report: achievements earned, XP bar filling up, level-ups."""
import math
import time
from datetime import datetime, timezone

from ...progression import (AWARD_INFO, achievement_xp, award_from_ra, level_for_xp, xp_for_level)
from ...retroach import media_url
from .. import gfx
from ..app import Screen
from .common import badge, draw_icon_slot, fmt_int, tile_surface, url_image

WAIT_LIMIT = 25.0      # seconds to wait for RetroAchievements before showing what we have
REVEAL_EVERY = 0.28
MAX_ROWS = 6


def _earned(a):
    return a.get("DateEarnedHardcore") or a.get("DateEarned")


def snapshot(app, game):
    """Captured when a game launches, so the report can diff against it."""
    ra = app.ra
    prog = ra.progress.get(game.ra_game_id) if game.ra_game_id else None
    before = None
    if prog:
        before = {str(a.get("ID")) for a in (prog.get("Achievements") or {}).values() if _earned(a)}
    return dict(game=game, start=time.time(), start_utc=datetime.now(timezone.utc),
                xp=ra.prog.xp if ra.prog else None, level=ra.prog.level if ra.prog else None,
                award=ra.award_for(game), earned_before=before)


class Report(Screen):
    def __init__(self, app, session, seconds):
        super().__init__(app)
        self.s = session
        self.game = session["game"]
        self.seconds = seconds
        self.closed_at = time.time()
        self.ready = False
        self.t = 0.0
        self.gained = []          # [(achievement dict, xp, hardcore)]
        self.flash = -10.0
        self.shown_level = 0

    # ------------------------------------------------------------ data
    def _check_ready(self):
        ra = self.app.ra
        gid = self.game.ra_game_id
        refreshed = ra.last_refresh >= self.closed_at and not ra.loading
        prog_done = (not gid) or ra._progress_ts.get(gid, 0) >= self.closed_at
        if (refreshed and prog_done) or time.time() - self.closed_at > WAIT_LIMIT:
            self._build()

    def _build(self):
        ra = self.app.ra
        gid = self.game.ra_game_id
        prog = ra.progress.get(gid) if gid else None
        achs = list((prog or {}).get("Achievements", {}).values())
        before = self.s["earned_before"]
        gained = []
        if before is not None:
            gained = [a for a in achs if _earned(a) and str(a.get("ID")) not in before]
        else:   # we had no snapshot: use recent unlocks for this game since launch
            since = self.s["start_utc"].timestamp() - 120
            ids = set()
            for r in ra.recent:
                if r.get("GameID") != gid:
                    continue
                try:
                    ts = datetime.strptime(str(r.get("Date"))[:19], "%Y-%m-%d %H:%M:%S") \
                        .replace(tzinfo=timezone.utc).timestamp()
                except ValueError:
                    continue
                if ts >= since:
                    ids.add(str(r.get("AchievementID")))
            gained = [a for a in achs if str(a.get("ID")) in ids]
        gained.sort(key=lambda a: _earned(a) or "")
        self.gained = []
        for a in gained:
            hc = bool(a.get("DateEarnedHardcore"))
            self.gained.append((a, achievement_xp(a.get("Points"), a.get("TrueRatio"), hc), hc))
        ach_xp = sum(x for _, x, _ in self.gained)
        self.xp_after = ra.prog.xp if ra.prog else (self.s["xp"] or 0) + ach_xp
        self.xp_before = self.s["xp"] if self.s["xp"] is not None else max(0, self.xp_after - ach_xp)
        self.xp_before = min(self.xp_before, self.xp_after)
        self.points = sum(int(a.get("Points") or 0) for a, _, _ in self.gained)
        total = len(achs)
        got = sum(1 for a in achs if _earned(a))
        got_hc = sum(1 for a in achs if a.get("DateEarnedHardcore"))
        self.progress = (got, total)
        self.award = award_from_ra((prog or {}).get("HighestAwardKind") or "", got, got_hc, total) if total else ""
        self.new_award = self.award if self.award and AWARD_INFO[self.award]["rank"] > \
            AWARD_INFO.get(self.s["award"], {"rank": 0})["rank"] else ""
        self.bonus_xp = max(0, (self.xp_after - self.xp_before) - ach_xp)
        self.level_before = level_for_xp(self.xp_before)
        self.level_after = level_for_xp(self.xp_after)
        self.shown_level = self.level_before
        # this screen shows level-ups itself; award celebrations still play afterwards
        ra.events[:] = [e for e in ra.events if e.get("kind") != "level"]
        self.bar_start = 0.6 + REVEAL_EVERY * min(len(self.gained), MAX_ROWS)
        self.bar_len = min(4.5, 1.4 + 0.7 * (self.level_after - self.level_before)) if self.xp_after > self.xp_before else 0.0
        self.ready = True
        self.t = 0.0

    # ------------------------------------------------------------ animation
    def _xp_now(self):
        if not self.ready:
            return 0
        if self.bar_len <= 0:
            return self.xp_after
        f = max(0.0, min(1.0, (self.t - self.bar_start) / self.bar_len))
        f = 1 - (1 - f) ** 3     # ease out
        return int(self.xp_before + (self.xp_after - self.xp_before) * f)

    @property
    def done(self):
        return self.ready and self.t >= self.bar_start + self.bar_len

    def update(self, dt):
        if not self.ready:
            self._check_ready()
            return
        self.t += dt
        lv = level_for_xp(self._xp_now())
        if lv > self.shown_level:
            self.shown_level = lv
            self.flash = self.t

    def on_action(self, a):
        if a == "a" and self.ready and not self.done:
            self.t = self.bar_start + self.bar_len + 0.01   # skip animation
            self.shown_level = self.level_after
            return
        if a in ("a", "b"):
            if not self.ready:
                self._build()
                self.t = 999
                self.shown_level = self.level_after
                return
            self.app.pop()

    # ------------------------------------------------------------ drawing
    def draw(self, s):
        g = self.game
        art = self.app.artwork.get(g, fetch=False) if self.app.artwork else None
        if art:
            bg = self.app.images.derive(("blurbg", gfx.W, gfx.H), art, lambda im: gfx.blur(gfx.cover(im, gfx.W, gfx.H)))
            if bg:
                s.blit(bg, (0, 0))
        shade = gfx.layer((gfx.W, gfx.H))
        shade.fill((4, 8, 20, 215))
        s.blit(shade, (0, 0))
        s.blit(tile_surface(self.app, g, 96, 14), (60, 40))
        gfx.blit_text(s, "SESSION COMPLETE", (176, 44), 16, gfx.ACCENT_HI, True)
        gfx.blit_text(s, g.display_title, (176, 66), 36, gfx.TEXT, True, max_w=gfx.W - 240)
        mins = max(1, int(self.seconds // 60)) if self.seconds >= 30 else 0
        played = f"Played {mins} min" if mins else "Played under a minute"
        gfx.blit_text(s, f"{played}  ·  {g.system.name}", (176, 112), 18, gfx.TEXT_DIM)
        if not self.ready:
            dots = "." * (1 + int(self.app.t * 2) % 3)
            gfx.blit_text(s, f"Checking RetroAchievements{dots}", (gfx.W // 2, 380), 24, gfx.TEXT_DIM, anchor="center")
            return
        self._draw_achievements(s)
        self._draw_stats(s)
        self._draw_xp(s)

    def _draw_achievements(self, s):
        x, y = 60, 172
        n = len(self.gained)
        gfx.blit_text(s, f"Achievements unlocked ({n})" if n else "Achievements unlocked", (x, y), 20, gfx.TEXT, True)
        y += 38
        if not n:
            gfx.blit_text(s, "Nothing new this session - next time!", (x, y + 6), 18, gfx.TEXT_FAINT)
            return
        for i, (a, xp, hc) in enumerate(self.gained[:MAX_ROWS]):
            appear = (self.t - 0.4 - i * REVEAL_EVERY) / 0.25
            if appear <= 0:
                break
            off = int(40 * (1 - min(1, appear)))
            r = (x + off, y, 680, 58)
            gfx.rrect(s, (255, 255, 255, 22), r, 12)
            img = badge(self.app, a.get("BadgeName", "00000"), 46)
            draw_icon_slot(s, (x + off + 6, y + 6, 46, 46), img, 6)
            gfx.blit_text(s, a.get("Title", ""), (x + off + 64, y + 7), 18, gfx.TEXT, True, max_w=440)
            gfx.blit_text(s, a.get("Description", ""), (x + off + 64, y + 32), 14, gfx.TEXT_DIM, max_w=440)
            gfx.blit_text(s, f"+{fmt_int(xp)} XP", (x + off + 668, y + 8), 17, gfx.GOLD, True, anchor="topright")
            gfx.blit_text(s, f"{a.get('Points', 0)} pts" + (" · HC" if hc else ""), (x + off + 668, y + 32), 14,
                          gfx.TEXT_DIM, anchor="topright")
            y += 66
        if n > MAX_ROWS and self.t > 0.4 + MAX_ROWS * REVEAL_EVERY:
            gfx.blit_text(s, f"+ {n - MAX_ROWS} more", (x, y + 2), 16, gfx.TEXT_DIM, True)

    def _draw_stats(self, s):
        x, y, w = 780, 172, 440
        rows = [("Achievement points", f"+{self.points}"),
                ("XP from achievements", f"+{fmt_int(sum(x for _, x, _ in self.gained))}")]
        if self.bonus_xp:
            rows.append(("Award bonus XP", f"+{fmt_int(self.bonus_xp)}"))
        for label, val in rows:
            gfx.rrect(s, (255, 255, 255, 18), (x, y, w, 50), 12)
            gfx.blit_text(s, label, (x + 18, y + 25), 17, gfx.TEXT_DIM, anchor="midleft")
            gfx.blit_text(s, val, (x + w - 18, y + 25), 20, gfx.GOLD, True, anchor="midright")
            y += 58
        got, total = self.progress
        gfx.rrect(s, (255, 255, 255, 18), (x, y, w, 74), 12)
        gfx.blit_text(s, "Game progress", (x + 18, y + 12), 17, gfx.TEXT_DIM)
        gfx.blit_text(s, f"{got} / {total}", (x + w - 18, y + 12), 17, gfx.TEXT, True, anchor="topright")
        gfx.progress_bar(s, (x + 18, y + 46, w - 36, 9), got / total if total else 0,
                         gfx.GOLD if total and got == total else gfx.ACCENT_HI)
        y += 82
        if self.new_award:
            info = AWARD_INFO[self.new_award]
            gfx.rrect(s, (255, 255, 255, 26), (x, y, w, 64), 12)
            gfx.award_emblem(s, (x + 36, y + 32), self.new_award, 40, self.app.t)
            gfx.blit_text(s, f"{info['name']} earned!", (x + 68, y + 10), 21, info["color"], True)
            gfx.blit_text(s, info["desc"], (x + 68, y + 38), 14, gfx.TEXT_DIM)

    def _draw_xp(self, s):
        xp = self._xp_now()
        lv = level_for_xp(xp)
        base, nxt = xp_for_level(lv), xp_for_level(lv + 1)
        y = 650
        flash = max(0.0, 1 - (self.t - self.flash) / 1.2)
        pulse = 1 + 0.25 * flash * abs(math.sin((self.t - self.flash) * 9))
        gfx.level_badge(s, (120, y + 40), lv, int(84 * pulse), self.app.t)
        bx, bw = 200, gfx.W - 260
        gfx.blit_text(s, f"Level {lv}", (bx, y), 24, gfx.TEXT, True)
        gfx.blit_text(s, f"{fmt_int(xp - base)} / {fmt_int(nxt - base)} XP", (bx + bw, y + 4), 17, gfx.TEXT_DIM,
                      anchor="topright")
        gfx.progress_bar(s, (bx, y + 40, bw, 18), (xp - base) / max(1, nxt - base), gfx.tier_bar_color(lv, self.app.t))
        gained = xp - self.xp_before
        if gained > 0:
            gfx.blit_text(s, f"+{fmt_int(gained)} XP", (bx, y + 66), 20, gfx.GOLD, True)
        if flash > 0 and self.shown_level > self.level_before:
            gfx.blit_text(s, "LEVEL UP!", (bx + bw // 2, y + 8), int(26 + 10 * flash), gfx.GOLD, True, anchor="midtop")
        elif self.done and self.level_after > self.level_before:
            gfx.blit_text(s, f"Level {self.level_before}  →  {self.level_after}", (bx + bw // 2, y + 6), 20,
                          gfx.GOLD, True, anchor="midtop")

    def hints(self):
        if not self.ready:
            return [("a", "Skip")]
        return [("a", "Skip" if not self.done else "Continue")]


__all__ = ["Report", "snapshot", "media_url", "url_image"]
