"""On-screen keyboard (gamepad friendly, physical typing works too)."""
import pygame

from .. import gfx
from ..app import Screen

ROWS_LOWER = ["1234567890", "qwertyuiop", "asdfghjkl-", "zxcvbnm_.@"]
ROWS_UPPER = ["!#$%&*()+=", "QWERTYUIOP", "ASDFGHJKL/", "ZXCVBNM:,?"]
SPECIAL = ["Shift", "Space", "Delete", "Done"]


class Keyboard(Screen):
    opaque = False

    def __init__(self, app, title, value="", on_done=None, secret=False, hint=""):
        super().__init__(app)
        self.title = title
        self.value = value
        self.on_done = on_done
        self.secret = secret
        self.hint = hint
        self.shift = False
        self.r, self.c = 1, 0
        self.reveal = not secret
        app.input.text_mode = True
        pygame.key.start_text_input()

    def _rows(self):
        return ROWS_UPPER if self.shift else ROWS_LOWER

    def _close(self, ok):
        self.app.input.text_mode = False
        pygame.key.stop_text_input()
        self.app.pop()
        if ok and self.on_done:
            self.on_done(self.value.strip())

    def on_event(self, e):
        if e.type == pygame.TEXTINPUT:
            self.value += e.text
        elif e.type == pygame.KEYDOWN:
            if e.key == pygame.K_BACKSPACE:
                self.value = self.value[:-1]
            elif e.key == pygame.K_v and (e.mod & pygame.KMOD_CTRL):
                try:
                    clip = pygame.scrap.get_text() if hasattr(pygame.scrap, "get_text") else ""
                    if clip:
                        self.value += clip.strip()
                except Exception:  # noqa: BLE001
                    pass

    def on_action(self, a):
        rows = self._rows()
        nrows = len(rows) + 1
        if a == "up":
            self.r = (self.r - 1) % nrows
        elif a == "down":
            self.r = (self.r + 1) % nrows
        elif a in ("left", "right"):
            d = -1 if a == "left" else 1
            width = len(SPECIAL) if self.r == len(rows) else len(rows[self.r])
            self.c = (self.c + d) % width
        elif a == "a" and self.app.input.last_device == "keyboard":
            self._close(True)   # Enter on a physical keyboard finishes
        elif a == "a":
            if self.r == len(rows):
                k = SPECIAL[self.c]
                if k == "Shift":
                    self.shift = not self.shift
                elif k == "Space":
                    self.value += " "
                elif k == "Delete":
                    self.value = self.value[:-1]
                elif k == "Done":
                    self._close(True)
            else:
                self.value += rows[self.r][self.c]
        elif a == "b":
            if self.app.input.last_device == "pad" and self.value:
                self.value = self.value[:-1]
            else:
                self._close(False)
        elif a == "x":
            self.shift = not self.shift
        elif a == "y":
            self.reveal = not self.reveal
        elif a == "start":
            self._close(True)
        elif a == "select":
            self._close(False)
        if self.r == len(rows):
            self.c = min(self.c, len(SPECIAL) - 1)
        else:
            self.c = min(self.c, len(rows[self.r]) - 1)

    def draw(self, s):
        dim = gfx.layer((gfx.W, gfx.H))
        dim.fill((0, 0, 0, 200))
        s.blit(dim, (0, 0))
        gfx.blit_text(s, self.title, (gfx.W // 2, 90), 30, gfx.TEXT, True, anchor="center")
        if self.hint:
            gfx.blit_text(s, self.hint, (gfx.W // 2, 128), 18, gfx.TEXT_DIM, anchor="center", max_w=1000)
        field = pygame.Rect(140, 160, gfx.W - 280, 64)
        gfx.rrect(s, (255, 255, 255, 30), field, 14)
        shown = self.value if self.reveal else "•" * len(self.value)
        caret = "|" if int(self.app.t * 2) % 2 == 0 else " "
        surf = gfx.text(shown + caret, 26, gfx.TEXT)
        inner = field.inflate(-40, 0)
        tx = inner.x if surf.get_width() <= inner.w else inner.right - surf.get_width()
        s.set_clip(inner)
        s.blit(surf, (tx, field.centery - surf.get_height() // 2))
        s.set_clip(None)
        rows = self._rows()
        key_w, key_h, gap = 84, 70, 10
        y0 = 270
        for ri, row in enumerate(rows):
            total = len(row) * key_w + (len(row) - 1) * gap
            x = (gfx.W - total) // 2
            for ci, ch in enumerate(row):
                r = pygame.Rect(x + ci * (key_w + gap), y0 + ri * (key_h + gap), key_w, key_h)
                sel = (ri, ci) == (self.r, self.c)
                gfx.rrect(s, gfx.TEXT if sel else (255, 255, 255, 26), r, 12)
                gfx.blit_text(s, ch, r.center, 28, (10, 14, 30) if sel else gfx.TEXT, True, anchor="center")
        # special row
        widths = [180, 380, 180, 180]
        total = sum(widths) + gap * 3
        x = (gfx.W - total) // 2
        y = y0 + len(rows) * (key_h + gap)
        for ci, (k, w) in enumerate(zip(SPECIAL, widths)):
            r = pygame.Rect(x, y, w, key_h)
            sel = (len(rows), ci) == (self.r, self.c)
            col = gfx.TEXT if sel else ((0, 112, 209, 200) if k == "Done" else (255, 255, 255, 26))
            if k == "Shift" and self.shift and not sel:
                col = (255, 255, 255, 70)
            gfx.rrect(s, col, r, 12)
            gfx.blit_text(s, k, r.center, 22, (10, 14, 30) if sel else gfx.TEXT, True, anchor="center")
            x += w + gap

    def hints(self):
        h = [("a", "Type"), ("b", "Delete"), ("x", "Shift")]
        if self.secret:
            h.append(("y", "Show/Hide"))
        h.append(("start", "Done"))
        return h
