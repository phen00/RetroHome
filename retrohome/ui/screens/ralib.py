"""RetroAchievements Library: every console, every game with achievements, get games via the browser."""
import importlib.util
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import pygame

from ...installer import folder_for_console
from ...paths import FROZEN, cache_dir
from ...retroach import RAError, media_url
from ...systems import get_system
from .. import gfx
from ..app import Screen
from .common import draw_icon_slot, fmt_int, url_image

BROWSER_PACKAGES = ["PyQt6", "PyQt6-WebEngine"]     # required (prebuilt wheels for every Python 3.9+)
OPTIONAL_PACKAGES = ["py7zr"]                          # nicer .7z support; skipped if it can't install
GAME_PAGE = "https://retroachievements.org/game/{id}"
HASH_PAGE = "https://retroachievements.org/game/{id}/hashes"


def browser_available() -> bool:
    try:
        return importlib.util.find_spec("PyQt6.QtWebEngineWidgets") is not None
    except (ImportError, ValueError):
        return False


# ---------------------------------------------------------------- consoles
class ConsoleList(Screen):
    CW, CH, GAP = 216, 150, 18

    @property
    def COLS(self):
        return max(4, (gfx.W - 100 + self.GAP) // (self.CW + self.GAP))

    def __init__(self, app):
        super().__init__(app)
        self.consoles = None
        self.error = ""
        self.sel = 0
        self.scroll = 0.0
        client = app.ra.client
        if not client:
            self.error = "Link your RetroAchievements account in Settings first."
            return

        def done(res):
            local = {}
            for g in app.library.all:
                if g.system.ra:
                    local[g.system.ra] = local.get(g.system.ra, 0) + 1
            for c in res:
                c["_local"] = local.get(int(c.get("ID") or 0), 0)
                c["_folder"] = folder_for_console(int(c.get("ID") or 0), Path(app.config["rom_dir"]))
            self.consoles = sorted(res, key=lambda c: (c["_folder"] is None, c.get("Name", "").lower()))

        def fail(e):
            self.error = str(e)
        app.tasks.submit(client.consoles, callback=done, error=fail)

    def on_action(self, a):
        if a == "b":
            self.app.pop()
            return
        if not self.consoles:
            return
        n = len(self.consoles)
        step = {"left": -1, "right": 1, "up": -self.COLS, "down": self.COLS, "lb": -self.COLS * 3,
                "rb": self.COLS * 3}.get(a)
        if step:
            self.sel = max(0, min(n - 1, self.sel + step))
        elif a == "a":
            self.app.push(GameList(self.app, self.consoles[self.sel]))

    def update(self, dt):
        row = self.sel // self.COLS
        target = max(0, row - 1) * (self.CH + self.GAP)
        self.scroll += (target - self.scroll) * min(1, dt * 14)

    def draw(self, s):
        gfx.blit_text(s, "RetroAchievements Library", (60, 34), 34, gfx.TEXT, True)
        gfx.blit_text(s, "Pick a console to see every game that has achievements.", (60, 80), 18, gfx.TEXT_DIM)
        if self.error:
            gfx.blit_text(s, self.error, (60, 140), 20, gfx.RED, max_w=gfx.W - 120)
            return
        if self.consoles is None:
            gfx.blit_text(s, "Loading consoles…", (60, 140), 20, gfx.TEXT_FAINT)
            return
        x0 = (gfx.W - (self.COLS * self.CW + (self.COLS - 1) * self.GAP)) // 2
        y0 = 126
        s.set_clip(pygame.Rect(0, y0 - 12, gfx.W, gfx.H - y0 - 40))
        for i, c in enumerate(self.consoles):
            row, col = divmod(i, self.COLS)
            x = x0 + col * (self.CW + self.GAP)
            y = y0 + row * (self.CH + self.GAP) - self.scroll
            if y > gfx.H or y + self.CH < y0 - 20:
                continue
            r = pygame.Rect(x, int(y), self.CW, self.CH)
            sel = i == self.sel
            gfx.rrect(s, gfx.PANEL_HI if sel else gfx.PANEL, r, 16)
            if sel:
                gfx.glow_border(s, r, 16, self.app.t)
            icon = url_image(self.app, c.get("IconURL", ""), 56, radius=6)
            draw_icon_slot(s, (r.centerx - 28, r.y + 16, 56, 56), icon, 8)
            dim = c["_folder"] is None
            gfx.blit_text(s, c.get("Name", ""), (r.centerx, r.y + 84), 17, gfx.TEXT_FAINT if dim else gfx.TEXT, True,
                          max_w=self.CW - 16, anchor="midtop")
            sub = "No matching roms folder" if dim else (f"{c['_local']} in your library" if c["_local"]
                                                          else f"roms/{c['_folder']}")
            gfx.blit_text(s, sub, (r.centerx, r.y + 110), 13, gfx.TEXT_FAINT if dim else gfx.TEXT_DIM,
                          max_w=self.CW - 16, anchor="midtop")
        s.set_clip(None)

    def hints(self):
        return [("a", "Open"), ("lb", "Page up"), ("rb", "Page down"), ("b", "Back")]


# ---------------------------------------------------------------- games on a console
FILTERS = ["All games", "Not in my library", "In my library"]


class GameList(Screen):
    def __init__(self, app, console):
        super().__init__(app)
        self.console = console
        self.cid = int(console.get("ID") or 0)
        self.folder = console.get("_folder")
        self.games = None
        self.error = ""
        self.sel = 0
        self.scroll = 0
        self.filter = 0
        client = app.ra.client

        def done(res):
            def key(g):
                t = g.get("Title", "")
                return (t.startswith("~"), t.lower())
            self.games = sorted(res, key=key)

        def fail(e):
            self.error = str(e) if isinstance(e, RAError) else f"Error: {e}"
        app.tasks.submit(client.games_for_console, self.cid, callback=done, error=fail)

    def _local_ids(self):
        return {g.ra_game_id for g in self.app.library.all if g.ra_game_id}

    def _items(self):
        if not self.games:
            return []
        if self.filter == 0:
            return self.games
        have = self._local_ids()
        want = self.filter == 2
        return [g for g in self.games if (int(g.get("ID") or 0) in have) == want]

    def on_action(self, a):
        if a == "b":
            self.app.pop()
            return
        items = self._items()
        n = len(items)
        if a == "y":
            self.filter = (self.filter + 1) % len(FILTERS)
            self.sel = self.scroll = 0
        elif not n:
            return
        elif a in ("up", "down", "lb", "rb"):
            step = {"up": -1, "down": 1, "lb": -10, "rb": 10}[a]
            self.sel = max(0, min(n - 1, self.sel + step))
        elif a == "right":   # next letter
            cur = items[self.sel].get("Title", "")[:1].upper()
            for i in range(self.sel + 1, n):
                if items[i].get("Title", "")[:1].upper() != cur:
                    self.sel = i
                    break
        elif a == "left":
            cur = items[self.sel].get("Title", "")[:1].upper()
            i = self.sel - 1
            while i > 0 and items[i].get("Title", "")[:1].upper() == cur:
                i -= 1
            first = items[i].get("Title", "")[:1].upper()
            while i > 0 and items[i - 1].get("Title", "")[:1].upper() == first:
                i -= 1
            self.sel = max(0, i)
        elif a == "x":
            from .achievements import Achievements
            g = items[self.sel]
            self.app.push(Achievements(self.app, ra_id=g.get("ID"), title=g.get("Title", ""),
                                       console=self.console.get("Name", ""), icon=media_url(g.get("ImageIcon", ""))))
        elif a == "a":
            g = items[self.sel]
            if not self.folder:
                self.app.dialog("No roms folder for this console",
                                f"RetroHome doesn't have an EmuDeck folder for {self.console.get('Name')}, so it "
                                "wouldn't know where to put the game.")
                return
            open_browser(self.app, g, self.folder, self.console.get("Name", ""))

    def draw(self, s):
        c = self.console
        icon = url_image(self.app, c.get("IconURL", ""), 56, radius=6)
        draw_icon_slot(s, (60, 30, 56, 56), icon, 8)
        gfx.blit_text(s, c.get("Name", ""), (132, 30), 32, gfx.TEXT, True)
        sub = f"Games go to roms/{self.folder}" if self.folder else "No matching roms folder"
        gfx.blit_text(s, sub, (132, 72), 16, gfx.TEXT_DIM)
        fx = gfx.W - 60
        for i in reversed(range(len(FILTERS))):
            label = FILTERS[i]
            w = gfx.measure(label, 15, True)[0] + 26
            r = (fx - w, 46, w, 32)
            on = i == self.filter
            gfx.rrect(s, gfx.TEXT if on else (255, 255, 255, 28), r, 16)
            gfx.blit_text(s, label, (fx - w // 2, 62), 15, (10, 14, 30) if on else gfx.TEXT, True, anchor="center")
            fx -= w + 8
        if self.error:
            gfx.blit_text(s, self.error, (60, 130), 20, gfx.RED, max_w=gfx.W - 120)
            return
        if self.games is None:
            gfx.blit_text(s, "Loading games…", (60, 130), 20, gfx.TEXT_FAINT)
            return
        items = self._items()
        if not items:
            gfx.blit_text(s, "No games here.", (60, 130), 20, gfx.TEXT_FAINT)
            return
        gfx.blit_text(s, f"{len(items)} games", (60, 104), 15, gfx.TEXT_FAINT)
        self.sel = min(self.sel, len(items) - 1)
        y0, row_h = 130, 64
        visible = (gfx.H - 60 - y0) // row_h
        if self.sel < self.scroll:
            self.scroll = self.sel
        elif self.sel >= self.scroll + visible:
            self.scroll = self.sel - visible + 1
        have = self._local_ids()
        progress = {int(p.get("GameID") or 0): p for p in self.app.ra.completion}
        for i in range(self.scroll, min(len(items), self.scroll + visible)):
            g = items[i]
            gid = int(g.get("ID") or 0)
            r = pygame.Rect(60, y0 + (i - self.scroll) * row_h, gfx.W - 120, row_h - 8)
            sel = i == self.sel
            gfx.rrect(s, gfx.PANEL_HI if sel else gfx.PANEL, r, 12)
            if sel:
                gfx.glow_border(s, r, 12, self.app.t)
            ic = url_image(self.app, media_url(g.get("ImageIcon", "")), 44, radius=6)
            draw_icon_slot(s, (r.x + 6, r.y + 6, 44, 44), ic, 6)
            gfx.blit_text(s, g.get("Title", ""), (r.x + 64, r.y + 7), 18, gfx.TEXT, True, max_w=r.w - 420)
            gfx.blit_text(s, f"{g.get('NumAchievements', 0)} achievements  ·  {fmt_int(g.get('Points', 0))} points",
                          (r.x + 64, r.y + 31), 14, gfx.TEXT_DIM)
            p = progress.get(gid)
            if p and int(p.get("MaxPossible") or 0):
                got, mx = int(p.get("NumAwarded") or 0), int(p.get("MaxPossible") or 1)
                gfx.progress_bar(s, (r.right - 330, r.y + 34, 140, 6), got / mx)
                gfx.blit_text(s, f"{got}/{mx}", (r.right - 330, r.y + 12), 13, gfx.TEXT_DIM)
            if gid in have:
                gfx.blit_text(s, "✓ In your library", (r.right - 18, r.centery), 15, gfx.GREEN, True, anchor="midright")

    def hints(self):
        return [("a", "Get game"), ("x", "Achievements"), ("y", "Filter"), ("lb", "Page up"), ("rb", "Page down"),
                ("b", "Back")]


# ---------------------------------------------------------------- browser hosting
def open_browser(app, game_entry, folder, console_name):
    gid = int(game_entry.get("ID") or 0)
    if not browser_available() and FROZEN:
        app.dialog("Browser not included",
                   "This copy of RetroHome was built without the web browser component. Download the full "
                   "release, or build it with PyQt6-WebEngine installed.")
        return
    if not browser_available():
        app.dialog("Install the RetroHome browser?",
                   "Getting games uses a small built-in web browser (Qt WebEngine). It's a one-time "
                   "download of roughly 150-200 MB. Install it now?",
                   [("Install", lambda: app.push(InstallBrowser(app, lambda: open_browser(
                       app, game_entry, folder, console_name)))), ("Not now", None)])
        return
    _start_browser(app, ["--url", GAME_PAGE.format(id=gid), "--home", GAME_PAGE.format(id=gid),
                         "--hashes", HASH_PAGE.format(id=gid), "--folder", folder],
                   game_entry.get("Title", ""), folder)


def open_page(app, url, title):
    """Open any web page (e.g. a RetroAchievements profile) in the built-in browser; no ROM downloads."""
    if not browser_available():
        if FROZEN:
            app.dialog("Browser not included", "This copy of RetroHome was built without the web browser. "
                       f"Open {url} in your own browser instead.")
        else:
            app.dialog("Install the RetroHome browser?", "This needs the built-in browser (about 150-200 MB). "
                       "Install it now?", [("Install", lambda: app.push(InstallBrowser(
                           app, lambda: open_page(app, url, title)))), ("Not now", None)])
        return
    _start_browser(app, ["--url", url, "--home", url], title, "")


def _start_browser(app, args, title, folder):
    report = cache_dir() / f"browser-report-{os.getpid()}-{int(time.time())}.json"
    root = Path(__file__).resolve().parents[3]   # project folder containing the retrohome package
    launcher = [sys.executable, "--browser"] if FROZEN else [sys.executable, "-m", "retrohome.browser"]
    cmd = [*launcher, *args, "--rom-dir", str(app.config["rom_dir"]), "--report", str(report), "--title", title]
    if app.config["fullscreen"]:
        cmd.append("--fullscreen")
    cmd += ["--pad-family", app.input.pad_family]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(root) + os.pathsep + env.get("PYTHONPATH", "")
    try:
        proc = subprocess.Popen(cmd, cwd=None if FROZEN else str(root), env=env, stdin=subprocess.DEVNULL)
    except OSError as e:
        app.dialog("Couldn't open the browser", str(e))
        return
    app.push(BrowserOpen(app, proc, report, title, folder))


class BrowserOpen(Screen):
    background_input = True     # see Start/Home presses even while the browser window has focus

    def __init__(self, app, proc, report, title, folder):
        super().__init__(app)
        self.proc, self.report, self.title, self.folder = proc, Path(report), title, folder
        self.results = []
        self.last_read = 0
        self.closing = False

    @property
    def close_flag(self):
        return self.report.with_suffix(".close")

    def on_action(self, a):
        # Start / Options / Menu / + or the Home (PS / Xbox) button closes the browser
        if a in ("start", "guide") and not self.closing:
            self.closing = True
            try:
                self.close_flag.write_text("close")
            except OSError:
                pass
            self.close_requested = time.time()

    def _read(self):
        try:
            self.results = json.loads(self.report.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass

    def update(self, dt):
        if time.time() - self.last_read > 1:
            self.last_read = time.time()
            self._read()
        code = self.proc.poll()
        if code is None:
            # the browser closes itself on the flag; if it's stuck, end it
            if self.closing and time.time() - getattr(self, "close_requested", time.time()) > 150:
                self.proc.terminate()
            return
        self._read()
        try:
            self.close_flag.unlink()
        except OSError:
            pass
        try:
            self.report.unlink()
        except OSError:
            pass
        app = self.app
        app.input.reset()
        pygame.event.clear()
        app.pop()
        added = sum(len(r.get("files", [])) for r in self.results if r.get("status") == "ok")
        errors = [r["message"] for r in self.results if r.get("status") == "error"]
        if not self.folder:     # a profile page: pick up anyone just followed
            app.friends.refresh(force=True)
        if added:
            app.toast(f"Added {added} file(s) to {self.folder} - rescanning")

            def rescanned():
                app.ra.match_library(on_match=app._on_ra_match)
            app.library.scan(on_done=rescanned)
        if errors:
            app.dialog("Some downloads weren't added", " · ".join(errors[:4]))
        if code not in (0, None) and not self.results:
            app.dialog("The browser closed unexpectedly",
                       f"Exit code {code}. If this keeps happening, reinstall the browser from Settings.")

    def draw(self, s):
        gfx.blit_text(s, "Browser open", (gfx.W // 2, gfx.H // 2 - 80), 22, gfx.TEXT_DIM, anchor="center")
        gfx.blit_text(s, self.title, (gfx.W // 2, gfx.H // 2 - 36), 36, gfx.TEXT, True, max_w=1100, anchor="center")
        sub = (f"Downloads are unpacked into roms/{get_system(self.folder).folder} automatically." if self.folder
               else "Press Follow on their page to add them as a friend.")
        gfx.blit_text(s, sub, (gfx.W // 2, gfx.H // 2 + 10), 18, gfx.TEXT_DIM, anchor="center")
        y = gfx.H // 2 + 60
        for r in self.results[-5:]:
            col = gfx.GREEN if r.get("status") == "ok" else gfx.GOLD
            gfx.blit_text(s, r.get("message", ""), (gfx.W // 2, y), 17, col, anchor="center", max_w=1000)
            y += 26
        from ...padstyle import text_label
        msg = ("Closing the browser…" if self.closing else
               f"Press {text_label(self.app.input.pad_family, 'start')} on your controller, or close the "
               "browser window, to come back.")
        gfx.blit_text(s, msg, (gfx.W // 2, gfx.H - 90), 16, gfx.TEXT_FAINT, anchor="center")

    def hints(self):
        return []


class InstallBrowser(Screen):
    """pip-installs the browser component into this Python environment."""

    def __init__(self, app, then):
        super().__init__(app)
        self.then = then
        self.lines = []
        self.done = False
        self.ok = False
        threading.Thread(target=self._work, daemon=True).start()

    def _pip(self, packages, required):
        # --only-binary: never try to compile anything (that needs Visual C++ on Windows)
        cmd = [sys.executable, "-m", "pip", "install", "--upgrade", "--only-binary", ":all:",
               "--disable-pip-version-check", *packages]
        kw = {"creationflags": 0x08000000} if sys.platform.startswith("win") else {}
        try:
            p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                 encoding="utf-8", errors="replace", **kw)
            for line in p.stdout:
                line = line.strip()
                if line:
                    self.lines.append(line[:140])
                    self.lines = self.lines[-12:]
            ok = p.wait() == 0
        except OSError as e:
            self.lines.append(str(e))
            ok = False
        if not ok and not required:
            self.lines.append(f"(optional {', '.join(packages)} skipped - .7z files will use 7-Zip/tar instead)")
        return ok

    def _work(self):
        self.ok = self._pip(BROWSER_PACKAGES, True)
        if self.ok:
            self._pip(OPTIONAL_PACKAGES, False)
        importlib.invalidate_caches()
        self.done = True

    def update(self, dt):
        if self.done and self.ok and browser_available():
            self.app.pop()
            self.app.toast("Browser installed")
            self.then()

    def on_action(self, a):
        if a in ("a", "b") and self.done:
            self.app.pop()

    def draw(self, s):
        gfx.blit_text(s, "Installing the browser…" if not self.done else
                      ("Installed" if self.ok else "Install failed"), (60, 60), 32, gfx.TEXT, True)
        gfx.blit_text(s, "Downloading Qt WebEngine with pip. This can take a few minutes.", (60, 108), 18, gfx.TEXT_DIM)
        y = 160
        for ln in self.lines:
            gfx.blit_text(s, ln, (60, y), 14, gfx.TEXT_FAINT, max_w=gfx.W - 120)
            y += 22
        if self.done and not self.ok:
            ver = f"{sys.version_info.major}.{sys.version_info.minor}"
            for i, ln in enumerate([
                    "Check your internet connection and try again from Settings.",
                    f"If it says no matching distribution: PyQt6-WebEngine may not support Python {ver} yet -",
                    "installing Python 3.13 from python.org and re-running RetroHome.bat will fix it."]):
                gfx.blit_text(s, ln, (60, y + 20 + i * 26), 16, gfx.GOLD, max_w=gfx.W - 120)

    def hints(self):
        return [("b", "Close")] if self.done else []
