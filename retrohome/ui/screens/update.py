"""'Update available' prompt and the download / install screen."""
import threading
import time

import pygame

from ... import __version__
from ... import updater
from .. import gfx
from ..app import Screen


def check_for_updates(app, manual=False):
    """Background check. Manual checks always report back; automatic ones only when there's news."""
    cfg = app.config

    def done(info):
        cfg.data["update_checked_at"] = time.time()
        cfg.save()
        if not info:
            if manual:
                app.toast(f"RetroHome {__version__} is up to date")
            return
        if not manual and cfg.get("skipped_update") == info["version"]:
            return
        app.pending_update = info
        if manual:
            app.push(UpdatePrompt(app, info))

    def fail(e):
        cfg.data["update_checked_at"] = time.time()     # offline: don't retry every minute
        if manual:
            app.dialog("Couldn't check for updates", str(e))
    app.tasks.submit(updater.check, callback=done, error=fail)


class UpdatePrompt(Screen):
    opaque = False

    def __init__(self, app, info):
        super().__init__(app)
        self.info = info
        self.options = [("Update now", self._update), ("Later", self._later), ("Skip this version", self._skip)]
        self.sel = 0
        self.scroll = 0

    def _update(self):
        if not updater.can_self_update():
            from ...paths import FROZEN
            why = ("RetroHome can update itself only from the release download, not when run from source."
                   if not FROZEN else "RetroHome's folder can't be written to (is it in Program Files?).")
            self.app.pop()
            self.app.dialog("Update manually", f"{why} Download version {self.info['version']} from "
                                               f"{self.info['page']}")
            return
        self.app.pop()
        self.app.push(Updating(self.app, self.info))

    def _later(self):
        self.app.pop()

    def _skip(self):
        self.app.config["skipped_update"] = self.info["version"]
        self.app.pop()
        self.app.toast(f"Skipped {self.info['version']} - Settings > Check for updates to get it later")

    def on_action(self, a):
        if a in ("left", "right"):
            self.sel = (self.sel + (1 if a == "right" else -1)) % len(self.options)
        elif a in ("up", "down"):
            self.scroll = max(0, self.scroll + (1 if a == "down" else -1))
        elif a == "a":
            self.options[self.sel][1]()
        elif a == "b":
            self._later()

    def draw(self, s):
        dim = gfx.layer((gfx.W, gfx.H))
        dim.fill((0, 0, 0, 185))
        s.blit(dim, (0, 0))
        bw, bh = 760, 520
        box = pygame.Rect(0, 0, bw, bh)
        box.center = (gfx.W // 2, gfx.H // 2)
        gfx.rrect(s, (22, 30, 56), box, 20)
        gfx.rrect(s, (255, 255, 255, 30), box, 20, 1)
        gfx.blit_text(s, "UPDATE AVAILABLE", (box.x + 36, box.y + 30), 15, gfx.ACCENT_HI, True)
        gfx.blit_text(s, f"RetroHome {self.info['version']}", (box.x + 36, box.y + 54), 32, gfx.TEXT, True)
        gfx.blit_text(s, f"You have {__version__}", (box.right - 36, box.y + 66), 16, gfx.TEXT_DIM, anchor="topright")
        # notes
        notes = self.info.get("notes") or "No release notes."
        lines = []
        for para in notes.replace("\r", "").split("\n"):
            para = para.strip().replace("**", "")
            if not para:
                continue
            bullet = para.startswith(("- ", "* "))
            text = para[2:] if bullet else para
            wrapped = gfx.wrap(text, 17, bw - 100, max_lines=6)
            for i, w in enumerate(wrapped):
                lines.append((("•  " if bullet and i == 0 else "    " if bullet else "") + w))
        area = pygame.Rect(box.x + 36, box.y + 112, bw - 72, bh - 210)
        per = area.h // 26
        self.scroll = min(self.scroll, max(0, len(lines) - per))
        y = area.y
        for ln in lines[self.scroll:self.scroll + per]:
            gfx.blit_text(s, ln, (area.x, y), 17, gfx.TEXT_DIM)
            y += 26
        if len(lines) > per:
            gfx.blit_text(s, "▲▼ more", (area.right, area.bottom - 4), 13, gfx.TEXT_FAINT, anchor="bottomright")
        if self.info.get("size"):
            gfx.blit_text(s, f"Download: {self.info['size'] / 1e6:.0f} MB · RetroHome restarts when it's done. "
                             "Your settings and progress are kept.", (box.x + 36, box.bottom - 90), 14, gfx.TEXT_FAINT,
                          max_w=bw - 72)
        x = box.right - 36
        for i in reversed(range(len(self.options))):
            label = self.options[i][0]
            tw = gfx.measure(label, 18, True)[0] + 44
            r = pygame.Rect(x - tw, box.bottom - 64, tw, 42)
            on = i == self.sel
            gfx.rrect(s, gfx.TEXT if on else (255, 255, 255, 28), r, 21)
            gfx.blit_text(s, label, r.center, 18, (10, 14, 30) if on else gfx.TEXT, True, anchor="center")
            x = r.x - 12

    def hints(self):
        return [("a", "Select"), ("b", "Later")]


class Updating(Screen):
    def __init__(self, app, info):
        super().__init__(app)
        self.info = info
        self.got, self.total = 0, int(info.get("size") or 0)
        self.state = "downloading"
        self.error = ""
        self.cancelled = False
        self.new_dir = None
        threading.Thread(target=self._work, daemon=True).start()

    def _work(self):
        try:
            self.new_dir = updater.download(self.info, progress=self._progress, cancel=lambda: self.cancelled)
            self.state = "ready"
        except updater.UpdateError as e:
            self.error = str(e)
            self.state = "error"
        except Exception as e:  # noqa: BLE001
            self.error = f"Update failed: {e}"
            self.state = "error"

    def _progress(self, got, total):
        self.got, self.total = got, total or self.total

    def update(self, dt):
        if self.state == "ready":
            self.state = "restarting"
            try:
                if updater.IS_WINDOWS:
                    updater.apply(self.new_dir)     # helper swaps the files after we exit, then reopens
                else:
                    self.app.restart_exe = updater.apply_in_place(self.new_dir)   # swapped already
            except Exception as e:  # noqa: BLE001
                self.error = f"Couldn't install the update: {e}"
                self.state = "error"
                return
            self.restart_at = time.time() + 0.8
        if self.state == "restarting" and time.time() >= getattr(self, "restart_at", 0):
            self.app.quit()          # Windows: the helper takes over. Linux: the app restarts in place

    def on_action(self, a):
        if a == "b" and self.state == "downloading":
            self.cancelled = True
            self.app.pop()
            self.app.toast("Update cancelled")
        elif a in ("a", "b") and self.state == "error":
            self.app.pop()

    def draw(self, s):
        cx, cy = gfx.W // 2, gfx.H // 2
        gfx.blit_text(s, f"Updating to RetroHome {self.info['version']}", (cx, cy - 80), 30, gfx.TEXT, True,
                      anchor="center")
        if self.state == "error":
            for i, ln in enumerate(gfx.wrap(self.error, 18, 800, max_lines=4)):
                gfx.blit_text(s, ln, (cx, cy - 20 + i * 26), 18, gfx.RED, anchor="center")
            gfx.blit_text(s, "Nothing was changed. You can try again from Settings > Check for updates.",
                          (cx, cy + 100), 15, gfx.TEXT_FAINT, anchor="center")
            return
        frac = self.got / self.total if self.total else 0
        gfx.progress_bar(s, (cx - 300, cy - 10, 600, 14), frac)
        if self.state == "downloading":
            msg = f"Downloading… {self.got / 1e6:.0f} / {self.total / 1e6:.0f} MB" if self.total else \
                f"Downloading… {self.got / 1e6:.0f} MB"
        else:
            msg = "Installing - RetroHome will close and reopen in a moment…"
        gfx.blit_text(s, msg, (cx, cy + 24), 17, gfx.TEXT_DIM, anchor="center")

    def hints(self):
        if self.state == "downloading":
            return [("b", "Cancel")]
        if self.state == "error":
            return [("a", "OK")]
        return []
