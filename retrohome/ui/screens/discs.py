"""Disc picker for multi-disc games."""
import re
from pathlib import Path

from ...paths import cache_dir
from .. import gfx
from ..app import Screen
from .common import tile_surface


def make_m3u(game) -> Path:
    """Playlist of every disc so the emulator can swap discs in-game."""
    d = cache_dir() / "m3u"
    d.mkdir(parents=True, exist_ok=True)
    p = d / (re.sub(r'[<>:"/\\|?*]', "_", game.title)[:120] + ".m3u")
    p.write_text("\n".join(str(path) for _, path in game.discs) + "\n", encoding="utf-8")
    return p


class DiscPicker(Screen):
    opaque = False

    def __init__(self, app, game):
        super().__init__(app)
        self.game = game
        self.options = [("All discs", "Starts on disc 1 - change discs from the emulator's menu", "all")]
        self.options += [(label, path.name, i) for i, (label, path) in enumerate(game.discs)]
        last = (app.config["disc_choice"] or {}).get(game.id)
        self.sel = next((i for i, o in enumerate(self.options) if o[2] == last), 0)

    def on_action(self, a):
        n = len(self.options)
        if a == "up":
            self.sel = (self.sel - 1) % n
        elif a == "down":
            self.sel = (self.sel + 1) % n
        elif a == "b":
            self.app.pop()
        elif a == "a":
            choice = self.options[self.sel][2]
            prof = self.app.config.profile
            prof.setdefault("disc_choice", {})[self.game.id] = choice
            self.app.config.save()
            self.app.pop()
            path = make_m3u(self.game) if choice == "all" else self.game.discs[choice][1]
            self.app.launch(self.game, disc_path=path)

    def draw(self, s):
        dim = gfx.layer((gfx.W, gfx.H))
        dim.fill((0, 0, 0, 175))
        s.blit(dim, (0, 0))
        n = len(self.options)
        h = 150 + n * 66
        box = (gfx.W // 2 - 360, gfx.H // 2 - h // 2, 720, h)
        gfx.rrect(s, (24, 32, 58), box, 18)
        bx, by = box[0], box[1]
        s.blit(tile_surface(self.app, self.game, 80, 12), (bx + 30, by + 28))
        gfx.blit_text(s, "Choose a disc", (bx + 128, by + 34), 16, gfx.ACCENT_HI, True)
        gfx.blit_text(s, self.game.display_title, (bx + 128, by + 56), 28, gfx.TEXT, True, max_w=560)
        y = by + 130
        for i, (label, detail, _) in enumerate(self.options):
            r = (bx + 30, y, 660, 56)
            sel = i == self.sel
            gfx.rrect(s, gfx.PANEL_HI if sel else gfx.PANEL, r, 12)
            if sel:
                gfx.glow_border(s, r, 12, self.app.t)
            gfx.blit_text(s, label, (bx + 50, y + 8), 20, gfx.TEXT, True)
            gfx.blit_text(s, detail, (bx + 50, y + 33), 14, gfx.TEXT_DIM, max_w=620)
            y += 66

    def hints(self):
        return [("a", "Play"), ("b", "Cancel")]
