"""Drawing helpers: theme, fonts, cached text, images and shapes.

Resolution independence: every screen lays out in a fixed 1280x800 logical space, but all
drawing goes through `Layer` objects that hold a real surface at K times that size (K = the
display's pixel density relative to 1280x800). Text, shapes and images are rasterised at the
real resolution, so the UI is sharp on a 1440p/4K monitor and identical on a Steam Deck (K=1).
"""
import math
import threading
from collections import OrderedDict
from pathlib import Path

import pygame

from .. import net
from ..paths import cache_dir

W, H = 1280, 800
K = 1.0          # real pixels per logical pixel (set by the app from the window size)

# ---- theme -------------------------------------------------------------
BG = (6, 10, 24)
BG2 = (14, 22, 48)
PANEL = (255, 255, 255, 18)
PANEL_HI = (255, 255, 255, 34)
TEXT = (240, 243, 250)
TEXT_DIM = (165, 175, 195)
TEXT_FAINT = (110, 120, 140)
ACCENT = (0, 112, 209)
ACCENT_HI = (64, 160, 255)
GOLD = (240, 190, 60)
GREEN = (70, 200, 120)
RED = (230, 80, 80)


# ---- scaled surfaces ---------------------------------------------------
def _sp(p, k):
    return (int(round(p[0] * k)), int(round(p[1] * k)))


def _srect(r, k):
    r = pygame.Rect(r) if not isinstance(r, pygame.Rect) else r
    x0, y0 = int(round(r.x * k)), int(round(r.y * k))
    x1, y1 = int(round((r.x + r.w) * k)), int(round((r.y + r.h) * k))
    return pygame.Rect(x0, y0, max(0, x1 - x0), max(0, y1 - y0))


class Layer:
    """A surface addressed in logical pixels but stored at real resolution."""
    __slots__ = ("real", "k")

    def __init__(self, real, k=None):
        self.real = real
        self.k = K if k is None else k

    # size in logical pixels
    def get_size(self):
        w, h = self.real.get_size()
        return (int(round(w / self.k)), int(round(h / self.k)))

    def get_width(self):
        return self.get_size()[0]

    def get_height(self):
        return self.get_size()[1]

    def get_rect(self, **kw):
        r = pygame.Rect((0, 0), self.get_size())
        for key, v in kw.items():
            setattr(r, key, v)
        return r

    def blit(self, src, dest, area=None, special_flags=0):
        pos = _sp((dest[0], dest[1]), self.k)
        if isinstance(src, Layer):
            surf = src.real
            if abs(src.k - self.k) > 1e-6:   # stale layer from an old scale: resize it
                w, h = src.get_size()
                surf = pygame.transform.smoothscale(surf, _sp((w, h), self.k))
        else:                                # raw surface: treat as logical size
            w, h = src.get_size()
            surf = pygame.transform.smoothscale(src, (max(1, int(w * self.k)), max(1, int(h * self.k)))) \
                if self.k != 1 else src
        return self.real.blit(surf, pos, special_flags=special_flags)

    def fill(self, color, rect=None):
        self.real.fill(color, _srect(rect, self.k) if rect is not None else None)

    def set_clip(self, rect):
        self.real.set_clip(None if rect is None else _srect(rect, self.k))

    def set_alpha(self, a):
        self.real.set_alpha(a)

    def copy(self):
        return Layer(self.real.copy(), self.k)

    def convert_alpha(self):
        return self


def layer(size, alpha=True):
    w, h = size
    real = pygame.Surface((max(1, int(math.ceil(w * K))), max(1, int(math.ceil(h * K)))),
                          pygame.SRCALPHA if alpha else 0)
    return Layer(real, K)


def _target(dst):
    return (dst.real, dst.k) if isinstance(dst, Layer) else (dst, 1.0)


def _w(width, k):
    return 0 if not width else max(1, int(round(width * k)))


class _Draw:
    """pygame.draw with logical coordinates (works on Layers and plain surfaces)."""

    @staticmethod
    def rect(dst, color, rect, width=0, border_radius=0):
        t, k = _target(dst)
        return pygame.draw.rect(t, color, _srect(rect, k), _w(width, k),
                                border_radius=int(round(border_radius * k)))

    @staticmethod
    def circle(dst, color, center, radius, width=0):
        t, k = _target(dst)
        return pygame.draw.circle(t, color, _sp(center, k), max(1, int(round(radius * k))), _w(width, k))

    @staticmethod
    def polygon(dst, color, points, width=0):
        t, k = _target(dst)
        return pygame.draw.polygon(t, color, [(p[0] * k, p[1] * k) for p in points], _w(width, k))

    @staticmethod
    def line(dst, color, a, b, width=1):
        t, k = _target(dst)
        return pygame.draw.line(t, color, _sp(a, k), _sp(b, k), _w(width, k))

    @staticmethod
    def ellipse(dst, color, rect, width=0):
        t, k = _target(dst)
        return pygame.draw.ellipse(t, color, _srect(rect, k), _w(width, k))


draw = _Draw()


# ---- fonts -------------------------------------------------------------
_FONT_NAMES = ["Inter", "Segoe UI", "SF Pro Display", "Noto Sans", "Cantarell", "Ubuntu",
               "DejaVu Sans", "Liberation Sans", "Arial"]
_fonts = {}
_font_name = None


def font(size, bold=False):
    """Real-resolution font for a logical size."""
    global _font_name
    key = (size, bold, K)
    f = _fonts.get(key)
    if f:
        return f
    if _font_name is None:
        _font_name = ""
        avail = set(pygame.font.get_fonts())
        for n in _FONT_NAMES:
            k = n.lower().replace(" ", "")
            if k in avail:
                _font_name = k
                break
    px = max(6, int(round(size * K)))
    try:
        f = pygame.font.SysFont(_font_name, px, bold=bold) if _font_name else pygame.font.Font(None, int(px * 1.3))
    except Exception:  # noqa: BLE001
        f = pygame.font.Font(None, int(px * 1.3))
        f.set_bold(bold)
    _fonts[key] = f
    return f


def measure(s, size=20, bold=False):
    """(width, height) of text in logical pixels."""
    w, h = font(size, bold).size(s)
    return (int(math.ceil(w / K)), int(math.ceil(h / K)))


_text_cache = OrderedDict()


def text(s, size=20, color=TEXT, bold=False, max_w=None):
    """Rendered text Layer (cached). Truncates with an ellipsis to max_w (logical px)."""
    key = (s, size, color, bold, max_w)
    surf = _text_cache.get(key)
    if surf is not None:
        _text_cache.move_to_end(key)
        return surf
    s2 = s
    if max_w and measure(s2, size, bold)[0] > max_w:
        while s2 and measure(s2 + "…", size, bold)[0] > max_w:
            s2 = s2[:-1]
        s2 = s2.rstrip() + "…"
    surf = Layer(font(size, bold).render(s2, True, color), K)
    _text_cache[key] = surf
    if len(_text_cache) > 2000:
        _text_cache.popitem(last=False)
    return surf


def blit_text(dst, s, pos, size=20, color=TEXT, bold=False, max_w=None, anchor="topleft"):
    surf = text(s, size, color, bold, max_w)
    r = surf.get_rect(**{anchor: pos})
    dst.blit(surf, r)
    return r


def wrap(s, size, max_w, bold=False, max_lines=3):
    words, lines, cur = s.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if measure(t, size, bold)[0] <= max_w:
            cur = t
        else:
            if cur:
                lines.append(cur)
            cur = w
        if len(lines) == max_lines:
            break
    if cur and len(lines) < max_lines:
        lines.append(cur)
    if len(lines) == max_lines and " ".join(lines) != " ".join(words):
        last = lines[-1]
        while last and measure(last + "…", size, bold)[0] > max_w:
            last = last[:-1]
        lines[-1] = last + "…"
    return lines


def set_view(k, w=None, h=None):
    """Set real-pixel density and logical canvas size; drops everything rendered for the old one."""
    global K, W, H
    w = W if w is None else int(w)
    h = H if h is None else int(h)
    if abs(k - K) < 1e-6 and (w, h) == (W, H):
        return False
    K, W, H = k, w, h
    _fonts.clear()
    _text_cache.clear()
    return True


def set_scale(k):
    return set_view(k)


# ---- shapes ------------------------------------------------------------
def rrect(dst, color, rect, radius=12, width=0):
    rect = pygame.Rect(rect)
    if len(color) == 4 and color[3] < 255:
        s = layer(rect.size)
        draw.rect(s, color, s.get_rect(), width, border_radius=radius)
        dst.blit(s, rect.topleft)
    else:
        draw.rect(dst, color, rect, width, border_radius=radius)


def glow_border(dst, rect, radius=14, t=0.0):
    rect = pygame.Rect(rect)
    pulse = 0.65 + 0.35 * math.sin(t * 3.0)
    c = (int(255 * pulse), int(255 * pulse), 255)
    draw.rect(dst, c, rect.inflate(8, 8), 3, border_radius=radius + 4)


def progress_bar(dst, rect, frac, fg=ACCENT_HI, bg=(255, 255, 255, 40), radius=None):
    rect = pygame.Rect(rect)
    radius = rect.h // 2 if radius is None else radius
    rrect(dst, bg, rect, radius)
    frac = max(0.0, min(1.0, frac))
    if frac > 0:
        w = max(rect.h, int(rect.w * frac))
        rrect(dst, fg, (rect.x, rect.y, w, rect.h), radius)


def _grad(size, a, b, vertical):
    w, h = size
    rw, rh = max(1, int(math.ceil(w * K))), max(1, int(math.ceil(h * K)))
    n = rh if vertical else rw
    s = pygame.Surface((1, n) if vertical else (n, 1), pygame.SRCALPHA)
    for i in range(n):
        t = i / max(1, n - 1)
        c = tuple(int(a[j] + (b[j] - a[j]) * t) for j in range(len(a)))
        s.set_at((0, i) if vertical else (i, 0), c)
    return Layer(pygame.transform.scale(s, (rw, rh)), K)


def vgradient(size, top, bottom):
    return _grad(size, top, bottom, True)


def hgradient(size, left, right):
    return _grad(size, left, right, False)


def _real(surf):
    return surf.real if isinstance(surf, Layer) else surf


def _logical_size(surf):
    return surf.get_size()


def round_corners(surf, radius):
    real = _real(surf).convert_alpha()
    k = surf.k if isinstance(surf, Layer) else K
    mask = pygame.Surface(real.get_size(), pygame.SRCALPHA)
    pygame.draw.rect(mask, (255, 255, 255, 255), mask.get_rect(), border_radius=int(round(radius * k)))
    out = real.copy()
    out.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
    return Layer(out, k)


def scale_to(surf, size):
    """Any image (raw or Layer) scaled to a logical size."""
    real = _real(surf)
    rw, rh = max(1, int(round(size[0] * K))), max(1, int(round(size[1] * K)))
    return Layer(pygame.transform.smoothscale(real, (rw, rh)), K)


def grayscale(surf):
    real = _real(surf)
    if hasattr(pygame.transform, "grayscale"):
        real = pygame.transform.grayscale(real)
    return Layer(real, surf.k if isinstance(surf, Layer) else K)


def fit(surf, box_w, box_h):
    w, h = _logical_size(surf)
    s = min(box_w / w, box_h / h)
    return scale_to(surf, (max(1, w * s), max(1, h * s)))


def cover(surf, box_w, box_h):
    w, h = _logical_size(surf)
    s = max(box_w / w, box_h / h)
    scaled = scale_to(surf, (max(1, w * s), max(1, h * s)))
    out = layer((box_w, box_h))
    out.blit(scaled, scaled.get_rect(center=(box_w / 2, box_h / 2)).topleft)
    return out


def blur(surf, factor=14):
    real = _real(surf)
    k = surf.k if isinstance(surf, Layer) else K
    w, h = real.get_size()
    f = max(2, int(factor * k))
    small = pygame.transform.smoothscale(real, (max(1, w // f), max(1, h // f)))
    small = pygame.transform.smoothscale(small, (max(1, w // max(1, f // 2)), max(1, h // max(1, f // 2))))
    return Layer(pygame.transform.smoothscale(small, (w, h)), k)


# ---- images ------------------------------------------------------------
class Images:
    """Loads image files (and remote URLs via a disk cache) into surfaces."""

    def __init__(self, tasks):
        self.tasks = tasks
        self.raw = OrderedDict()       # path -> Surface
        self.derived = OrderedDict()   # key -> Surface
        self.url_state = {}            # url -> Path | None | "pending"
        self.url_dir = cache_dir() / "web"
        self.url_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self.loads_this_frame = 0

    def clear_scaled(self):
        """Forget everything rendered for a previous display scale."""
        self.derived.clear()

    def new_frame(self):
        self.loads_this_frame = 0

    def load(self, path):
        if path is None:
            return None
        key = str(path)
        s = self.raw.get(key)
        if s is not None:
            self.raw.move_to_end(key)
            return s
        if self.loads_this_frame >= 4:   # spread decoding over frames
            return None
        self.loads_this_frame += 1
        try:
            s = pygame.image.load(key).convert_alpha()
        except (pygame.error, OSError, ValueError):
            s = False
        self.raw[key] = s
        if len(self.raw) > 400:
            self.raw.popitem(last=False)
        return s or None

    def derive(self, key, path, make):
        """Cached transformed version of an image: make(surface) -> surface."""
        k = (key, str(path))
        s = self.derived.get(k)
        if s is not None:
            self.derived.move_to_end(k)
            return s
        base = self.load(path)
        if base is None:
            return None
        s = make(base)
        self.derived[k] = s
        if len(self.derived) > 600:
            self.derived.popitem(last=False)
        return s

    def url_path(self, url):
        """Local path for a remote image, downloading in the background."""
        if not url:
            return None
        st = self.url_state.get(url)
        if isinstance(st, Path):
            return st
        if st is not None:
            return None
        import hashlib
        p = self.url_dir / (hashlib.md5(url.encode()).hexdigest() + Path(url.split("?")[0]).suffix[:5])
        if p.exists():
            self.url_state[url] = p
            return p
        self.url_state[url] = "pending"

        def work():
            return p if net.download_image(url, p) else None

        def done(res):
            self.url_state[url] = res if res else False

        def fail(_):
            self.url_state.pop(url, None)   # allow retry later
        self.tasks.submit(work, callback=done, error=fail)
        return None


def placeholder(game, size):
    """Generated tile when no box art exists."""
    w, h = size
    c = game.system.color
    top = tuple(min(255, int(v * 1.25) + 20) for v in c) + (255,)
    bot = tuple(int(v * 0.45) for v in c) + (255,)
    s = vgradient((w, h), top, bot)
    lines = wrap(game.display_title, max(14, w // 9), w - 20, bold=True, max_lines=4)
    fs = max(14, w // 9)
    y = h // 2 - len(lines) * (fs + 4) // 2
    for ln in lines:
        blit_text(s, ln, (w // 2, y), fs, TEXT, True, anchor="midtop")
        y += fs + 4
    blit_text(s, game.system.label, (w // 2, h - 10), max(11, w // 14), (255, 255, 255), False,
              max_w=w - 12, anchor="midbottom")
    return s


# ---- level badges & award emblems -------------------------------------------
def _hexagon(cx, cy, r):
    return [(cx + r * math.cos(math.radians(60 * i - 90)), cy + r * math.sin(math.radians(60 * i - 90)))
            for i in range(6)]


def _hue(t, s=0.75, v=1.0):
    import colorsys
    r, g, b = colorsys.hsv_to_rgb(t % 1.0, s, v)
    return (int(r * 255), int(g * 255), int(b * 255))


def level_badge(dst, center, level, size=48, t=0.0, number=True):
    """Level crest: insignia every 5 levels, colour every 20, frame every 100 (see badges.py)."""
    from .badges import draw_badge
    draw_badge(dst, center, level, size, number)


def award_emblem(dst, center, award, size=28, t=0.0):
    """Small emblem for a game award (Mythic / Platinum / Beaten)."""
    from ..progression import AWARD_INFO, AWARD_MYTHIC
    info = AWARD_INFO.get(award)
    if not info:
        return
    cx, cy = center
    r = size / 2
    c1, c2 = info["color"], info["color2"]
    if award == AWARD_MYTHIC:
        c1 = _hue(t * 0.2 + 0.85, 0.55, 1.0)
        c2 = _hue(t * 0.2 + 0.35, 0.6, 0.9)
    pts = []
    for i in range(10):  # star-ish medal
        ang = math.radians(-90 + i * 36)
        rr = r if i % 2 == 0 else r * 0.62
        pts.append((cx + rr * math.cos(ang), cy + rr * math.sin(ang)))
    draw.circle(dst, c2, (cx, cy), int(r * 0.98))
    draw.polygon(dst, c1, pts)
    draw.circle(dst, (255, 255, 255), (cx, cy), max(2, int(r * 0.22)))


def tier_bar_color(level, t=0.0):
    from ..progression import tier_style
    return tier_style(level)["colors"][2]
