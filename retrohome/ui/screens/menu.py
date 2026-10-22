"""Generic vertical menu screen used by setup and settings."""
import pygame

from .. import gfx
from ..app import Screen


class Menu(Screen):
    def __init__(self, app, title, subtitle="", items=(), on_back=None, step=""):
        super().__init__(app)
        self.title = title
        self.subtitle = subtitle
        self.items = list(items)      # (label, detail, callback)
        self.sel = 0
        self.scroll = 0
        self.on_back = on_back
        self.step = step

    def set_items(self, items):
        self.items = list(items)
        self.sel = min(self.sel, max(0, len(self.items) - 1))

    def on_action(self, a):
        if not self.items:
            if a == "b" and self.on_back:
                self.on_back()
            return
        if a == "up":
            self.sel = (self.sel - 1) % len(self.items)
        elif a == "down":
            self.sel = (self.sel + 1) % len(self.items)
        elif a == "a":
            cb = self.items[self.sel][2]
            if cb:
                cb()
        elif a == "b" and self.on_back:
            self.on_back()

    def draw(self, s):
        x = 120
        if self.step:
            gfx.blit_text(s, self.step, (x, 70), 18, gfx.ACCENT_HI, True)
        gfx.blit_text(s, self.title, (x, 100), 40, gfx.TEXT, True, max_w=gfx.W - 240)
        y = 162
        if self.subtitle:
            for ln in gfx.wrap(self.subtitle, 20, gfx.W - 240, max_lines=4):
                gfx.blit_text(s, ln, (x, y), 20, gfx.TEXT_DIM)
                y += 28
        y += 24
        row_h = 74
        visible = max(1, (gfx.H - 90 - y) // row_h)
        if self.sel < self.scroll:
            self.scroll = self.sel
        elif self.sel >= self.scroll + visible:
            self.scroll = self.sel - visible + 1
        for i in range(self.scroll, min(len(self.items), self.scroll + visible)):
            label, detail, _ = self.items[i]
            r = pygame.Rect(x, y, gfx.W - 240, row_h - 10)
            sel = i == self.sel
            gfx.rrect(s, gfx.PANEL_HI if sel else gfx.PANEL, r, 14)
            if sel:
                gfx.glow_border(s, r, 14, self.app.t)
            if detail:
                gfx.blit_text(s, label, (r.x + 24, r.y + 10), 22, gfx.TEXT, True, max_w=r.w - 48)
                gfx.blit_text(s, detail, (r.x + 24, r.y + 38), 16, gfx.TEXT_DIM, max_w=r.w - 48)
            else:
                gfx.blit_text(s, label, (r.x + 24, r.centery), 22, gfx.TEXT, True, max_w=r.w - 48, anchor="midleft")
            y += row_h
        if self.scroll > 0:
            gfx.blit_text(s, "▲", (gfx.W // 2, 205), 16, gfx.TEXT_FAINT, anchor="center")
        if self.scroll + visible < len(self.items):
            gfx.blit_text(s, "▼", (gfx.W // 2, gfx.H - 70), 16, gfx.TEXT_FAINT, anchor="center")

    def hints(self):
        h = [("a", "Select")]
        if self.on_back:
            h.append(("b", "Back"))
        return h
