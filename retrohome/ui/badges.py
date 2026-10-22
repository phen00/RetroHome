"""Procedural level crests (see progression.tier_style for the rules).

Shapes are drawn on a 2x supersampled layer and scaled down for smooth edges, then the
text (level number, crest numeral) is added at native resolution. Results are cached.
"""
import math
from collections import OrderedDict

import pygame

from ..progression import roman, tier_style
from . import gfx

SS = 2
_cache = OrderedDict()

SHIELD = [(0, -0.86), (0.50, -0.76), (0.68, -0.52), (0.64, 0.10), (0.42, 0.50), (0, 0.78),
          (-0.42, 0.50), (-0.64, 0.10), (-0.68, -0.52), (-0.50, -0.76)]
METAL = (208, 213, 226)
METAL_DARK = (110, 116, 134)
INK = (16, 20, 34)


def _shade(c, f):
    return tuple(max(0, min(255, int(v * f))) for v in c[:3])


def _mix(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


class _Pen:
    """Draws in badge units (u = half the badge size) around the layer centre."""

    def __init__(self, layer, c, u):
        self.l, self.c, self.u = layer, c, u

    def p(self, x, y):
        return (self.c[0] + x * self.u, self.c[1] + y * self.u)

    def poly(self, color, pts, width=0):
        gfx.draw.polygon(self.l, color, [self.p(x, y) for x, y in pts], width)

    def circle(self, color, x, y, r, width=0):
        gfx.draw.circle(self.l, color, self.p(x, y), max(0.5, r * self.u), width)

    def ellipse(self, color, x, y, w, h):
        cx, cy = self.p(x, y)
        gfx.draw.ellipse(self.l, color, (cx - w * self.u / 2, cy - h * self.u / 2, w * self.u, h * self.u))


def _scaled(pts, s, oy=0.0):
    return [(x * s, y * s + oy) for x, y in pts]


def _feather(pen, bx, by, ang, length, width, light, dark):
    """A broad, slightly curved blade-feather pointing along `ang` (degrees)."""
    a = math.radians(ang)
    dx, dy = math.cos(a), math.sin(a)
    px, py = -dy, dx
    tip = (bx + dx * length, by + dy * length)
    mid = (bx + dx * length * 0.55, by + dy * length * 0.55)
    outer = [(bx + px * width, by + py * width),
             (mid[0] + px * width * 0.85, mid[1] + py * width * 0.85),
             tip,
             (mid[0] - px * width * 0.25, mid[1] - py * width * 0.25),
             (bx - px * width * 0.3, by - py * width * 0.3)]
    pen.poly(INK, _grow(outer, 0.035))
    pen.poly(dark, outer)
    pen.poly(light, [outer[0], outer[1], tip, mid])


def _grow(pts, d):
    cx = sum(p[0] for p in pts) / len(pts)
    cy = sum(p[1] for p in pts) / len(pts)
    out = []
    for x, y in pts:
        vx, vy = x - cx, y - cy
        n = math.hypot(vx, vy) or 1
        out.append((x + vx / n * d, y + vy / n * d))
    return out


def _wings(pen, st, big):
    rim = st["colors"][2]
    light, dark = _mix(METAL, (255, 255, 255), 0.25), METAL_DARK
    if big:
        spec = [(-172, 1.18, 0.20), (-152, 1.10, 0.19), (-132, 0.98, 0.18), (-113, 0.82, 0.16)]
    else:
        spec = [(-165, 0.92, 0.17), (-142, 0.84, 0.16), (-120, 0.72, 0.14)]
    for side in (-1, 1):
        for i, (ang, ln, w) in reversed(list(enumerate(spec))):
            a = ang if side < 0 else -180 - ang
            bx, by = side * (0.30 + 0.07 * i), -0.46 - 0.05 * i
            tint = _mix(light, rim, 0.18 + 0.1 * i)
            _feather(pen, bx, by, a, ln, w, tint, _mix(dark, rim, 0.25))


def _blades(pen, st):
    rim, bot = st["colors"][2], st["colors"][1]
    for side in (-1, 1):
        pts = [(side * 0.30, 0.22), (side * 1.06, 0.60), (side * 0.98, 0.74), (side * 0.30, 0.52)]
        pen.poly(INK, _grow(pts, 0.04))
        pen.poly(rim, pts)
        pen.poly(_shade(bot, 1.1), [(side * 0.30, 0.40), (side * 0.98, 0.70), (side * 0.30, 0.52)])


def _fins(pen, st):
    rim = st["colors"][2]
    for side in (-1, 1):
        pts = [(side * 0.60, -0.42), (side * 0.98, -0.14), (side * 0.60, 0.20)]
        pen.poly(INK, _grow(pts, 0.04))
        pen.poly(rim, pts)
        pen.poly(_shade(st["colors"][1], 1.0), [(side * 0.62, -0.28), (side * 0.84, -0.14), (side * 0.62, 0.06)])


def _laurel(pen, st):
    leaf, dark = st["colors"][4], st["colors"][1]
    for side in (-1, 1):
        for i in range(7):
            a = math.radians(205 + i * 20) if side < 0 else math.radians(-25 - i * 20)
            a = -a if side < 0 else a
            cx, cy = 0.98 * math.cos(math.radians(90 + side * (35 + i * 19))), 0.08 + 0.92 * math.sin(
                math.radians(90 + side * (35 + i * 19)))
            t = math.radians(90 + side * (35 + i * 19)) + math.pi / 2 * side
            dx, dy = math.cos(t) * 0.15, math.sin(t) * 0.15
            px, py = -dy * 0.45, dx * 0.45
            pts = [(cx - dx, cy - dy), (cx + px, cy + py), (cx + dx, cy + dy), (cx - px, cy - py)]
            pen.poly(INK, _grow(pts, 0.03))
            pen.poly(leaf if i % 2 else _mix(leaf, dark, 0.3), pts)


def _insignia(pen, step, col, cy=-0.04):
    edge = INK
    if step == 3:
        pts = []
        for i in range(10):
            a = math.radians(-90 + i * 36)
            r = 0.27 if i % 2 == 0 else 0.11
            pts.append((r * math.cos(a), cy + r * math.sin(a)))
        pen.poly(edge, _scaled(pts, 1.18, -cy * 0.18))
        pen.poly(col, pts)
        return
    n = step + 1
    gap = 0.15
    top = cy - (n - 1) * gap / 2 - 0.06
    for k in range(n):
        y0 = top + k * gap
        pts = [(-0.28, y0 + 0.12), (0, y0 - 0.06), (0.28, y0 + 0.12), (0.28, y0 + 0.21), (0, y0 + 0.03),
               (-0.28, y0 + 0.21)]
        pen.poly(edge, pts, 2)
        pen.poly(col, pts)


def _shapes(layer, size, st):
    box = layer.get_size()[0]
    pen = _Pen(layer, (box / 2, box / 2 - size * 0.04), size / 2)
    top, bot, rim, _, accent = st["colors"]
    if st["era"] >= 5 and st["gem_colour"]:
        g = st["gem_colour"]
        for r, a in ((1.22, 30), (1.0, 45)):
            pen.circle(g + (a,), 0, 0, r)
    if st["laurel"]:
        _laurel(pen, st)
    if st["frame"] >= 3:
        _wings(pen, st, st["frame"] >= 4)
    if st["frame"] >= 2:
        _blades(pen, st)
    if st["frame"] >= 1:
        _fins(pen, st)
    # shield: dark outline, rim, body, lit upper half
    pen.poly(INK, _scaled(SHIELD, 1.08))
    pen.poly(rim, SHIELD)
    body = _scaled(SHIELD, 0.86, -0.01)
    pen.poly(bot, body)
    upper = [p for p in body if p[1] <= -0.05] + [(0.55, -0.05), (-0.55, -0.05)]
    upper.sort(key=lambda p: math.atan2(p[1] + 0.3, p[0]))
    pen.poly(_mix(bot, top, 0.65), upper)
    # medallion
    pen.circle(INK, 0, -0.04, 0.47)
    pen.circle(_shade(rim, 0.9), 0, -0.04, 0.43)
    pen.circle(bot, 0, -0.04, 0.38)
    pen.circle(_mix(bot, top, 0.45), 0, -0.10, 0.30)
    _insignia(pen, st["step"], accent)
    if st["gem"]:
        g = st["gem_colour"]
        pts = [(0, -1.30), (0.30, -0.99), (0, -0.70), (-0.30, -0.99)]
        pen.poly(INK, _grow(pts, 0.06))
        pen.poly(_shade(g, 0.75), pts)
        pen.poly(g, [(0, -1.30), (0.30, -0.99), (0, -0.99), (-0.30, -0.99)])
    return pen


def render(level, size, number=True):
    key = (int(level), int(size), round(gfx.K, 4), number, gfx.W)
    lay = _cache.get(key)
    if lay is not None:
        _cache.move_to_end(key)
        return lay
    st = tier_style(level)
    box = size * 1.9
    rk = gfx.K * SS
    side = max(2, int(math.ceil(box * rk)))
    hi = gfx.Layer(pygame.Surface((side, side), pygame.SRCALPHA), rk)
    _shapes(hi, size, st)
    out_side = max(1, int(math.ceil(box * gfx.K)))
    lay = gfx.Layer(pygame.transform.smoothscale(hi.real, (out_side, out_side)), gfx.K)
    c = (box / 2, box / 2 - size * 0.04)
    u = size / 2
    if st["gem"] and size >= 34:
        num = roman(st["gem"])
        fs = max(6, int(size * 0.19 * min(1.0, 2.2 / max(1, len(num)))))
        gfx.blit_text(lay, num, (c[0], c[1] - 0.99 * u), fs, INK, True, anchor="center")
    if number:
        fs = max(9, int(size * 0.23))
        label = str(st["level"])
        tw, th = gfx.measure(label, fs, True)
        pw, ph = tw + fs * 0.9, fs * 1.25
        py = c[1] + 0.86 * u
        pill = pygame.Rect(0, 0, int(pw), int(ph))
        pill.center = (int(c[0]), int(py))
        gfx.draw.rect(lay, INK, pill, border_radius=int(ph / 2))
        gfx.draw.rect(lay, st["colors"][2], pill, max(1, int(size / 40)), border_radius=int(ph / 2))
        gfx.blit_text(lay, label, (c[0], py + 0.5), fs, st["colors"][3], True, anchor="center")
    _cache[key] = lay
    if len(_cache) > 300:
        _cache.popitem(last=False)
    return lay


def draw_badge(dst, center, level, size=48, number=True):
    lay = render(level, max(8, int(size)), number)
    w, h = lay.get_size()
    dst.blit(lay, (center[0] - w / 2, center[1] - h / 2))
