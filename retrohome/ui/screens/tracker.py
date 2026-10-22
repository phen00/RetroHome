"""Full achievement tracker: recent unlocks and games in progress."""
import pygame

from ...retroach import media_url
from .. import gfx
from ..app import Screen
from .common import badge, draw_icon_slot, fmt_int, url_image

TABS = ["Recently unlocked", "In progress", "Completed"]


class Tracker(Screen):
    def __init__(self, app, tab=0, on_pick=None):
        super().__init__(app)
        self.tab = tab
        self.sel = 0
        self.scroll = 0
        self.on_pick = on_pick

    def _items(self):
        ra = self.app.ra
        if self.tab == 0:
            return ra.recent
        comp = ra.completion
        if self.tab == 1:
            items = [c for c in comp if int(c.get("MaxPossible") or 0) and
                     int(c.get("NumAwarded") or 0) < int(c.get("MaxPossible") or 0)]
        else:
            items = [c for c in comp if int(c.get("MaxPossible") or 0) and
                     int(c.get("NumAwarded") or 0) >= int(c.get("MaxPossible") or 0)]
        return sorted(items, key=lambda c: c.get("MostRecentAwardedDate") or "", reverse=True)

    def _find_local(self, ra_id):
        for g in self.app.library.all:
            if g.ra_game_id == ra_id:
                return g
        return None

    def on_action(self, a):
        items = self._items()
        n = len(items)
        if a == "b":
            self.app.pop()
        elif a in ("lb", "left"):
            self.tab = (self.tab - 1) % len(TABS)
            self.sel = self.scroll = 0
        elif a in ("rb", "right"):
            self.tab = (self.tab + 1) % len(TABS)
            self.sel = self.scroll = 0
        elif a == "up" and n:
            self.sel = max(0, self.sel - 1)
        elif a == "down" and n:
            self.sel = min(n - 1, self.sel + 1)
        elif a == "y":
            self.app.ra.refresh(force=True)
            self.app.toast("Refreshing…")
        elif a == "a" and n:
            from .achievements import Achievements
            self.app.push(Achievements.for_ra_game(self.app, items[self.sel]))
        elif a == "x" and n:
            g = self._find_local(items[self.sel].get("GameID"))
            if g is None:
                self.app.toast("That game isn't in your library")
                return
            self.app.pop()
            if self.on_pick:
                self.on_pick(0, g)

    def draw(self, s):
        ra = self.app.ra
        gfx.blit_text(s, "Achievement Tracker", (60, 40), 34, gfx.TEXT, True)
        if ra.profile:
            p = ra.profile
            av = url_image(self.app, media_url(p.get("UserPic", "")), 48, circle=True)
            draw_icon_slot(s, (gfx.W - 108, 34, 48, 48), av, 24)
            gfx.blit_text(s, p.get("User", ""), (gfx.W - 124, 38), 20, gfx.TEXT, True, anchor="topright")
            gfx.blit_text(s, f"{fmt_int(p.get('TotalPoints', 0))} pts", (gfx.W - 124, 64), 16, gfx.GOLD, anchor="topright")
        x = 60
        for i, t in enumerate(TABS):
            w = gfx.measure(t, 17, True)[0] + 30
            r = pygame.Rect(x, 100, w, 38)
            on = i == self.tab
            gfx.rrect(s, gfx.TEXT if on else (255, 255, 255, 28), r, 19)
            gfx.blit_text(s, t, r.center, 17, (10, 14, 30) if on else gfx.TEXT, True, anchor="center")
            x += w + 10
        items = self._items()
        if not items:
            msg = "Loading…" if ra.loading else ("Nothing here yet." if not ra.error else ra.error)
            gfx.blit_text(s, msg, (60, 180), 20, gfx.TEXT_FAINT)
            return
        self.sel = min(self.sel, len(items) - 1)
        y0, row_h = 160, 80
        visible = (gfx.H - 60 - y0) // row_h
        if self.sel < self.scroll:
            self.scroll = self.sel
        elif self.sel >= self.scroll + visible:
            self.scroll = self.sel - visible + 1
        for i in range(self.scroll, min(len(items), self.scroll + visible)):
            it = items[i]
            r = pygame.Rect(60, y0 + (i - self.scroll) * row_h, gfx.W - 120, row_h - 10)
            sel = i == self.sel
            gfx.rrect(s, gfx.PANEL_HI if sel else gfx.PANEL, r, 14)
            if sel:
                gfx.glow_border(s, r, 14, self.app.t)
            if self.tab == 0:
                img = badge(self.app, it.get("BadgeName", "00000"), 56)
                draw_icon_slot(s, (r.x + 7, r.y + 7, 56, 56), img, 8)
                gfx.blit_text(s, it.get("Title", ""), (r.x + 80, r.y + 8), 19, gfx.TEXT, True, max_w=r.w - 330)
                gfx.blit_text(s, it.get("Description", ""), (r.x + 80, r.y + 36), 15, gfx.TEXT_DIM, max_w=r.w - 330)
                gfx.blit_text(s, f"{it.get('Points', 0)} pts", (r.right - 20, r.y + 8), 17, gfx.GOLD, True, anchor="topright")
                hc = " · HC" if str(it.get("HardcoreMode")) in ("1", "True", "true") else ""
                gfx.blit_text(s, f"{it.get('GameTitle', '')}  ·  {str(it.get('Date', ''))[:16]}{hc}",
                              (r.right - 20, r.y + 38), 14, gfx.TEXT_DIM, anchor="topright", max_w=280)
            else:
                img = url_image(self.app, media_url(it.get("ImageIcon", "")), 56, radius=8)
                draw_icon_slot(s, (r.x + 7, r.y + 7, 56, 56), img, 8)
                got, mx = int(it.get("NumAwarded") or 0), int(it.get("MaxPossible") or 1)
                gfx.blit_text(s, it.get("Title", ""), (r.x + 80, r.y + 8), 19, gfx.TEXT, True, max_w=r.w - 330)
                gfx.blit_text(s, it.get("ConsoleName", ""), (r.x + 80, r.y + 36), 15, gfx.TEXT_DIM)
                gfx.blit_text(s, f"{got} / {mx}", (r.right - 20, r.y + 8), 17, gfx.TEXT, True, anchor="topright")
                gfx.progress_bar(s, (r.right - 220, r.y + 42, 200, 8), got / mx,
                                 gfx.GOLD if got >= mx else gfx.ACCENT_HI)
                if self._find_local(it.get("GameID")):
                    gfx.blit_text(s, "In your library", (r.right - 240, r.y + 37), 13, gfx.GREEN, anchor="topright")

    def hints(self):
        h = [("a", "Achievements")]
        items = self._items()
        if items and self._find_local(items[min(self.sel, len(items) - 1)].get("GameID")):
            h.append(("x", "Show in library"))
        return h + [("lb", "Prev tab"), ("rb", "Next tab"), ("y", "Refresh"), ("b", "Back")]
