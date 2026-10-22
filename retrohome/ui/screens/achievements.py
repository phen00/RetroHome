"""Per-game achievement list."""
import pygame

from ...retroach import media_url
from .. import gfx
from ..app import Screen
from .common import badge, draw_icon_slot, tile_surface, url_image

FILTERS = ["All", "Locked", "Unlocked"]


class Achievements(Screen):
    def __init__(self, app, game=None, ra_id=0, title="", console="", icon=""):
        super().__init__(app)
        self.game = game
        self.ra_id = game.ra_game_id if game else int(ra_id or 0)
        if game is None:   # a RetroAchievements game: use the library copy if we have one
            game = next((g for g in app.library.all if g.ra_game_id == self.ra_id), None)
            self.game = game
        self.title = game.display_title if game else title
        self.console = game.system.name if game else console
        self.icon = icon
        self.sel = 0
        self.scroll = 0
        self.filter = 0
        app.ra.game_progress(self.ra_id, force=True)

    @classmethod
    def for_ra_game(cls, app, entry):
        """From a RetroAchievements list entry (completion progress / recent unlock)."""
        return cls(app, ra_id=entry.get("GameID"), title=entry.get("Title") if "MaxPossible" in entry
                   else entry.get("GameTitle", ""), console=entry.get("ConsoleName", ""),
                   icon=media_url(entry.get("ImageIcon") or entry.get("GameIcon") or ""))

    def _items(self, prog):
        achs = list((prog.get("Achievements") or {}).values())

        def earned(a):
            return a.get("DateEarnedHardcore") or a.get("DateEarned")
        achs.sort(key=lambda a: (0 if earned(a) else 1, int(a.get("DisplayOrder") or 0)) if self.filter == 0
                  else int(a.get("DisplayOrder") or 0))
        if self.filter == 1:
            achs = [a for a in achs if not earned(a)]
        elif self.filter == 2:
            achs = [a for a in achs if earned(a)]
            achs.sort(key=lambda a: earned(a), reverse=True)
        return achs

    def on_action(self, a):
        prog = self.app.ra.progress.get(self.ra_id)
        n = len(self._items(prog)) if prog else 0
        if a == "b":
            self.app.pop()
        elif a == "up" and n:
            self.sel = max(0, self.sel - 1)
        elif a == "down" and n:
            self.sel = min(n - 1, self.sel + 1)
        elif a == "lb":
            self.sel = max(0, self.sel - 6)
        elif a == "rb":
            self.sel = min(max(0, n - 1), self.sel + 6)
        elif a == "y":
            self.filter = (self.filter + 1) % len(FILTERS)
            self.sel = self.scroll = 0
        elif a == "x":
            self.app.ra.game_progress(self.ra_id, force=True)
            self.app.toast("Refreshing…")
        elif a == "a" and self.game:
            self.app.launch(self.game)

    def draw(self, s):
        prog = self.app.ra.progress.get(self.ra_id)
        icon_url = media_url(prog.get("ImageIcon", "")) if prog else self.icon
        icon = url_image(self.app, icon_url, 96, radius=12)
        if icon is None and self.game:
            icon = tile_surface(self.app, self.game, 96, 12)
        draw_icon_slot(s, (60, 40, 96, 96), icon, 12)
        tx = 180
        title = self.title or (prog or {}).get("Title", "")
        console = self.console or (prog or {}).get("ConsoleName", "")
        gfx.blit_text(s, title, (tx, 44), 32, gfx.TEXT, True, max_w=gfx.W - tx - 60)
        gfx.blit_text(s, console + ("" if self.game else "  ·  not in your library"), (tx, 86), 17, gfx.TEXT_DIM)
        if not prog:
            gfx.blit_text(s, "Loading achievements…", (60, 200), 22, gfx.TEXT_DIM)
            return
        achs_all = list((prog.get("Achievements") or {}).values())
        total = len(achs_all)
        got = sum(1 for a in achs_all if a.get("DateEarned") or a.get("DateEarnedHardcore"))
        pts_total = sum(int(a.get("Points", 0)) for a in achs_all)
        pts_got = sum(int(a.get("Points", 0)) for a in achs_all if a.get("DateEarned") or a.get("DateEarnedHardcore"))
        gfx.blit_text(s, f"{got} / {total} unlocked  ·  {pts_got} / {pts_total} points",
                      (tx, 112), 17, gfx.GOLD, True)
        gfx.progress_bar(s, (tx, 140, 500, 8), got / total if total else 0,
                         gfx.GOLD if total and got == total else gfx.ACCENT_HI)
        # filter tabs
        fx = gfx.W - 60
        for i in reversed(range(len(FILTERS))):
            label = FILTERS[i]
            w = gfx.measure(label, 16, True)[0] + 28
            r = pygame.Rect(fx - w, 104, w, 34)
            on = i == self.filter
            gfx.rrect(s, gfx.TEXT if on else (255, 255, 255, 28), r, 17)
            gfx.blit_text(s, label, r.center, 16, (10, 14, 30) if on else gfx.TEXT, True, anchor="center")
            fx = r.x - 8
        items = self._items(prog)
        if not items:
            gfx.blit_text(s, "Nothing here.", (60, 200), 20, gfx.TEXT_FAINT)
            return
        self.sel = min(self.sel, len(items) - 1)
        y0, row_h = 180, 88
        visible = (gfx.H - 60 - y0) // row_h
        if self.sel < self.scroll:
            self.scroll = self.sel
        elif self.sel >= self.scroll + visible:
            self.scroll = self.sel - visible + 1
        players = int(prog.get("NumDistinctPlayers") or 0)
        for i in range(self.scroll, min(len(items), self.scroll + visible)):
            a = items[i]
            r = pygame.Rect(60, y0 + (i - self.scroll) * row_h, gfx.W - 120, row_h - 10)
            sel = i == self.sel
            gfx.rrect(s, gfx.PANEL_HI if sel else gfx.PANEL, r, 14)
            if sel:
                gfx.glow_border(s, r, 14, self.app.t)
            earned = a.get("DateEarnedHardcore") or a.get("DateEarned")
            img = badge(self.app, a.get("BadgeName", "00000"), 64, locked=not earned)
            draw_icon_slot(s, (r.x + 8, r.y + 7, 64, 64), img, 8)
            col = gfx.TEXT if earned else gfx.TEXT_DIM
            gfx.blit_text(s, a.get("Title", ""), (r.x + 88, r.y + 12), 20, col, True, max_w=r.w - 330)
            gfx.blit_text(s, a.get("Description", ""), (r.x + 88, r.y + 42), 16, gfx.TEXT_DIM, max_w=r.w - 330)
            gfx.blit_text(s, f"{a.get('Points', 0)} pts", (r.right - 20, r.y + 12), 18, gfx.GOLD, True, anchor="topright")
            if earned:
                hc = " · Hardcore" if a.get("DateEarnedHardcore") else ""
                gfx.blit_text(s, f"Unlocked {str(earned)[:10]}{hc}", (r.right - 20, r.y + 44), 14, gfx.GREEN,
                              anchor="topright")
            elif players:
                pct = 100 * int(a.get("NumAwarded") or 0) / players
                gfx.blit_text(s, f"{pct:.1f}% of players", (r.right - 20, r.y + 44), 14, gfx.TEXT_FAINT,
                              anchor="topright")

    def hints(self):
        h = [("a", "Play")] if self.game else []
        return h + [("y", "Filter"), ("x", "Refresh"), ("b", "Back")]
