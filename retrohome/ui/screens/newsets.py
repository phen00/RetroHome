"""New achievement sets on RetroAchievements: see them, open their achievements, or get the game."""
from pathlib import Path

import pygame

from .. import gfx
from ..app import Screen
from .common import ago, draw_icon_slot, url_image


class NewSetsScreen(Screen):
    def __init__(self, app):
        super().__init__(app)
        self.sel = 0
        self.scroll = 0
        app.new_sets.refresh()

    def _items(self):
        return self.app.new_sets.list

    def _local(self, item):
        return next((g for g in self.app.library.all if g.ra_game_id == item["GameID"]), None)

    def _folder(self, item):
        from ...installer import folder_for_console
        return folder_for_console(item["ConsoleID"], Path(self.app.config["rom_dir"]))

    def on_action(self, a):
        items = self._items()
        if a == "b":
            self.app.pop()
        elif a in ("up", "down") and items:
            self.sel = max(0, min(len(items) - 1, self.sel + (1 if a == "down" else -1)))
        elif a == "y":
            self.app.new_sets.refresh(force=True)
            self.app.toast("Refreshing…")
        elif a == "a" and items:
            from .achievements import Achievements
            self.app.push(Achievements.for_ra_game(self.app, items[self.sel]))
        elif a == "x" and items:
            it = items[self.sel]
            game = self._local(it)
            if game:
                self.app.launch(game)
                return
            folder = self._folder(it)
            if not folder:
                self.app.dialog("No roms folder for this console",
                                f"RetroHome doesn't have an EmuDeck folder for {it['ConsoleName']}, so it wouldn't "
                                "know where to put the game.")
                return
            from .ralib import open_browser
            open_browser(self.app, {"ID": it["GameID"], "Title": it["Title"]}, folder, it["ConsoleName"])

    def draw(self, s):
        ns = self.app.new_sets
        gfx.blit_text(s, "New on RetroAchievements", (60, 30), 34, gfx.TEXT, True)
        gfx.blit_text(s, "Achievement sets added to the site most recently", (60, 74), 16, gfx.TEXT_DIM)
        items = self._items()
        if not items:
            msg = ns.error or ("Loading…" if ns.loading or not ns.loaded else "Nothing new right now.")
            gfx.blit_text(s, msg, (60, 130), 20, gfx.RED if ns.error else gfx.TEXT_FAINT)
            return
        y0, row_h = 118, 80
        visible = max(1, (gfx.H - 60 - y0) // row_h)
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
            draw_icon_slot(s, (r.x + 7, r.y + 7, 56, 56), url_image(self.app, it["icon"], 56, radius=8), 8)
            gfx.blit_text(s, it["Title"], (r.x + 80, r.y + 10), 20, gfx.TEXT, True, max_w=r.w - 420)
            sub = "  ·  ".join(b for b in (it["ConsoleName"], f"by {it['author']}" if it["author"] else "") if b)
            gfx.blit_text(s, sub, (r.x + 80, r.y + 38), 15, gfx.TEXT_DIM, max_w=r.w - 420)
            have = self._local(it) is not None
            gfx.blit_text(s, "In your library" if have else ("Get it with X" if self._folder(it) else
                                                              "No roms folder"),
                          (r.right - 24, r.y + 14), 15, gfx.GREEN if have else gfx.TEXT_FAINT, True,
                          anchor="topright")
            if it["added"]:
                gfx.blit_text(s, f"Added {ago(it['added'])}", (r.right - 24, r.y + 40), 14, gfx.TEXT_FAINT,
                              anchor="topright")

    def hints(self):
        items = self._items()
        h = []
        if items:
            have = self._local(items[min(self.sel, len(items) - 1)]) is not None
            h = [("a", "Achievements"), ("x", "Play" if have else "Get game")]
        return h + [("y", "Refresh"), ("b", "Back")]
