"""Game Library grid (all games in a category)."""
import pygame

from .. import gfx
from ..app import Screen
from .common import tile_surface

SIZE = 150
GAP = 22


class LibraryGrid(Screen):
    def __init__(self, app, cat_key="home", on_pick=None):
        super().__init__(app)
        self.cats = [c for c in app.library.categories(app.only_ra) if c[2]]
        keys = [c[0] for c in self.cats]
        self.cat_i = keys.index(cat_key) if cat_key in keys else 0
        self.sel = 0
        self.scroll = 0.0
        self.on_pick = on_pick
        self.letter_jump = ""

    @property
    def cols(self):
        return max(5, (gfx.W - 100 + GAP) // (SIZE + GAP))

    @property
    def games(self):
        return self.cats[self.cat_i][2] if self.cats else []

    def on_action(self, a):
        games = self.games
        n = len(games)
        if a == "b" or a == "select":
            self.app.pop()
            return
        if a in ("lb", "rb") and self.cats:
            self.cat_i = (self.cat_i + (1 if a == "rb" else -1)) % len(self.cats)
            self.sel = 0
            self.scroll = 0
            return
        if not n:
            return
        if a == "left":
            self.sel = max(0, self.sel - 1)
        elif a == "right":
            self.sel = min(n - 1, self.sel + 1)
        elif a == "up":
            self.sel = max(0, self.sel - self.cols) if self.sel >= self.cols else self.sel
        elif a == "down":
            self.sel = min(n - 1, self.sel + self.cols)
        elif a == "a":
            self.app.launch(games[self.sel])
        elif a == "x":
            # jump to next starting letter
            cur = games[self.sel].display_title[:1].upper()
            for i in range(self.sel + 1, n):
                if games[i].display_title[:1].upper() != cur:
                    self.sel = i
                    break
            else:
                self.sel = 0
        elif a == "y":
            g = games[self.sel]
            self.app.pop()
            if self.on_pick:
                self.on_pick(self.cats[self.cat_i][0], g)

    def update(self, dt):
        row = self.sel // self.cols
        target = max(0, row - 1) * (SIZE + GAP + 34)
        self.scroll += (target - self.scroll) * min(1, dt * 14)

    def draw(self, s):
        title = self.cats[self.cat_i][1] if self.cats else "Library"
        gfx.blit_text(s, "Game Library", (60, 30), 32, gfx.TEXT, True)
        gfx.blit_text(s, f"{title}  ·  {len(self.games)} games", (60, 74), 18, gfx.TEXT_DIM)
        # category strip
        x = gfx.W - 60
        prev_label = self.cats[(self.cat_i - 1) % len(self.cats)][1] if self.cats else ""
        next_label = self.cats[(self.cat_i + 1) % len(self.cats)][1] if self.cats else ""
        gfx.blit_text(s, f"◂ {prev_label}   |   {next_label} ▸", (x, 52), 16, gfx.TEXT_FAINT, anchor="midright")
        games = self.games
        grid_w = self.cols * SIZE + (self.cols - 1) * GAP
        x0 = (gfx.W - grid_w) // 2
        y0 = 120
        clip = pygame.Rect(0, y0 - 14, gfx.W, gfx.H - y0 - 40)
        s.set_clip(clip)
        row_h = SIZE + GAP + 34
        first_row = max(0, int(self.scroll // row_h))
        for row in range(first_row, first_row + 6):
            for col in range(self.cols):
                i = row * self.cols + col
                if i >= len(games):
                    break
                g = games[i]
                x = x0 + col * (SIZE + GAP)
                y = y0 + row * row_h - self.scroll
                if y > gfx.H:
                    break
                r = pygame.Rect(x, int(y), SIZE, SIZE)
                s.blit(tile_surface(self.app, g, SIZE), r)
                sel = i == self.sel
                if sel:
                    gfx.glow_border(s, r, 14, self.app.t)
                gfx.blit_text(s, g.display_title, (r.centerx, r.bottom + 8), 15,
                              gfx.TEXT if sel else gfx.TEXT_DIM, sel, max_w=SIZE + 10, anchor="midtop")
        s.set_clip(None)
        if not games:
            gfx.blit_text(s, "No games here.", (gfx.W // 2, gfx.H // 2), 22, gfx.TEXT_FAINT, anchor="center")

    def hints(self):
        return [("a", "Play"), ("x", "Next letter"), ("y", "Show on Home"), ("lb", "Prev"), ("rb", "Next"),
                ("b", "Back")]
