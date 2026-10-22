"""Bits shared by several screens."""
import time

import pygame

from ...retroach import badge_url, media_url
from .. import gfx


def ago(ts):
    if not ts:
        return ""
    d = time.time() - ts
    if d < 90:
        return "just now"
    if d < 3600:
        return f"{int(d // 60)} min ago"
    if d < 86400:
        h = int(d // 3600)
        return f"{h} hour{'s' if h != 1 else ''} ago"
    days = int(d // 86400)
    if days < 30:
        return f"{days} day{'s' if days != 1 else ''} ago"
    return time.strftime("%d %b %Y", time.localtime(ts))


def fmt_playtime(secs):
    if not secs:
        return ""
    m = int(secs // 60)
    if m < 60:
        return f"{m} min played"
    return f"{m // 60}h {m % 60:02d}m played"


def fmt_int(n):
    try:
        return f"{int(n):,}"
    except (TypeError, ValueError):
        return "0"


def tile_surface(app, game, size, radius=14):
    """Square game tile: art fitted over a blurred copy of itself, or a placeholder."""
    art = app.artwork.get(game) if app.artwork else None
    if art:
        def make(im):
            base = gfx.blur(gfx.cover(im, size, size), 10)
            dark = gfx.layer((size, size))
            dark.fill((0, 0, 0, 90))
            base.blit(dark, (0, 0))
            fitted = gfx.fit(im, size - 12, size - 12)
            base.blit(fitted, fitted.get_rect(center=(size // 2, size // 2)))
            return gfx.round_corners(base, radius)
        s = app.images.derive(("tile", size, radius), art, make)
        if s:
            return s
    key = ("ph", size, radius, game.id, game.display_title)
    s = app.images.derived.get(key)
    if s is None:
        s = gfx.round_corners(gfx.placeholder(game, (size, size)), radius)
        app.images.derived[key] = s
    return s


def url_image(app, url, size, circle=False, radius=8, grey=False):
    """Remote image (RA badge/avatar/icon) scaled to size, or None while loading."""
    p = app.images.url_path(url)
    if not p:
        return None

    def make(im):
        out = gfx.scale_to(im, (size, size))
        if grey:
            out = gfx.grayscale(out)
        return gfx.round_corners(out, size // 2 if circle else radius)
    return app.images.derive(("url", size, circle, radius, grey), p, make)


def badge(app, badge_name, size, locked=False):
    return url_image(app, badge_url(badge_name, locked), size, radius=max(4, size // 8))


def draw_icon_slot(s, rect, img, radius=8):
    r = pygame.Rect(rect)
    if img:
        s.blit(img, r)
    else:
        gfx.rrect(s, (255, 255, 255, 22), r, radius)


__all__ = ["ago", "fmt_playtime", "fmt_int", "tile_surface", "url_image", "badge", "draw_icon_slot",
           "media_url"]
