"""Full-screen celebration for Mythic / Platinum awards and level-ups."""
import math


from ...progression import AWARD_INFO, AWARD_MYTHIC, award_xp, badge_change, style_name, tier_style
from .. import gfx
from ..app import Screen
from .common import draw_icon_slot, url_image


class Celebrate(Screen):
    opaque = False

    def __init__(self, app, event):
        super().__init__(app)
        self.ev = event
        self.t = 0.0

    def update(self, dt):
        self.t += dt
        if self.t > 9:
            self.app.pop()

    def on_action(self, a):
        if a in ("a", "b") and self.t > 0.6:
            self.app.pop()

    def _rays(self, s, center, color, n=18):
        surf = gfx.layer((gfx.W, gfx.H))
        cx, cy = center
        rot = self.t * 0.25
        for i in range(n):
            a0 = rot + i * 2 * math.pi / n
            a1 = a0 + math.pi / n * 0.6
            pts = [(cx, cy), (cx + 1400 * math.cos(a0), cy + 1400 * math.sin(a0)),
                   (cx + 1400 * math.cos(a1), cy + 1400 * math.sin(a1))]
            gfx.draw.polygon(surf, color + (26,), pts)
        s.blit(surf, (0, 0))

    def draw(self, s):
        appear = min(1.0, self.t / 0.5)
        dim = gfx.layer((gfx.W, gfx.H))
        dim.fill((2, 4, 12, int(225 * appear)))
        s.blit(dim, (0, 0))
        center = (gfx.W // 2, 300)
        ev = self.ev
        if ev["kind"] == "award":
            info = AWARD_INFO[ev["award"]]
            col = gfx._hue(self.t * 0.2 + 0.85, 0.5, 1.0) if ev["award"] == AWARD_MYTHIC else info["color"]
            self._rays(s, center, col)
            pop = 1 + 0.15 * math.sin(min(1, self.t * 2) * math.pi)
            gfx.award_emblem(s, center, ev["award"], int(190 * pop * appear) or 1, self.app.t)
            gfx.blit_text(s, info["name"].upper(), (gfx.W // 2, 455), 64, col, True, anchor="center")
            gfx.blit_text(s, info["desc"], (gfx.W // 2, 510), 22, gfx.TEXT_DIM, anchor="center")
            icon = url_image(self.app, ev.get("icon"), 56, radius=10)
            tw = gfx.measure(ev["title"], 28, True)[0]
            x = gfx.W // 2 - (tw + 72) // 2
            draw_icon_slot(s, (x, 550, 56, 56), icon, 10)
            gfx.blit_text(s, ev["title"], (x + 72, 578), 28, gfx.TEXT, True, anchor="midleft", max_w=900)
            gfx.blit_text(s, f"+{award_xp(ev['award'], ev.get('size', 0)):,} XP", (gfx.W // 2, 650), 24, gfx.GOLD,
                          True, anchor="center")
        else:
            st = tier_style(ev["new"])
            self._rays(s, center, st["colors"][2])
            gfx.level_badge(s, center, ev["new"], int(170 * appear) or 1, self.app.t)
            gfx.blit_text(s, "LEVEL UP", (gfx.W // 2, 455), 60, gfx.TEXT, True, anchor="center")
            change = badge_change(ev["old"], ev["new"])
            sub = {"frame": f"New frame unlocked: {style_name(ev['new'])}!",
                   "colour": f"New colour unlocked: {style_name(ev['new'])}!",
                   "insignia": "New insignia unlocked!"}.get(change, f"Level {ev['old']}  →  {ev['new']}")
            gfx.blit_text(s, sub, (gfx.W // 2, 510), 24, st["colors"][2] if change else gfx.TEXT_DIM, True,
                          anchor="center")

    def hints(self):
        return [("a", "Nice!")]
