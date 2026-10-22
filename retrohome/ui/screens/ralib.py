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


def open_page(app, url, title, extra=(), on_close=None):
    """Open any web page (e.g. a RetroAchievements profile) in the built-in browser; no ROM downloads.
    on_close(results) gets the browser's report when it closes."""
    if not browser_available():
        if FROZEN:
            app.dialog("Browser not included", "This copy of RetroHome was built without the web browser. "
                       f"Open {url} in your own browser instead.")
        else:
            app.dialog("Install the RetroHome browser?", "This needs the built-in browser (about 150-200 MB). "
                       "Install it now?", [("Install", lambda: app.push(InstallBrowser(
                           app, lambda: open_page(app, url, title, extra, on_close)))), ("Not now", None)])
        return
    _start_browser(app, ["--url", url, "--home", url, *extra], title, "", on_close)


NO_GPU = "--disable-gpu --disable-gpu-compositing --disable-gpu-sandbox --no-sandbox"

# Graphics setups for the browser, tried in this order until one opens a window. The first that
# works is remembered (config "browser_mode"). SteamOS Gaming Mode (gamescope) in particular can
# abort Qt with "Could not initialize GLX" (exit code -6).
BROWSER_MODES = [
    ("normal", {}),
    ("no-gpu", {"QTWEBENGINE_CHROMIUM_FLAGS": NO_GPU, "QTWEBENGINE_DISABLE_SANDBOX": "1",
                "QT_XCB_GL_INTEGRATION": "xcb_egl"}),
    # no OpenGL anywhere (Qt Quick's software renderer) - works even where GLX is broken
    ("software", {"QTWEBENGINE_CHROMIUM_FLAGS": NO_GPU, "QTWEBENGINE_DISABLE_SANDBOX": "1",
                  "QT_XCB_GL_INTEGRATION": "none", "QT_QUICK_BACKEND": "software"}),
    ("wayland", {"QTWEBENGINE_CHROMIUM_FLAGS": NO_GPU, "QTWEBENGINE_DISABLE_SANDBOX": "1",
                 "QT_QPA_PLATFORM": "wayland"}),
]
MODE_NAMES = {"normal": "Normal", "no-gpu": "No GPU acceleration", "software": "Software drawing",
              "wayland": "Wayland"}


def browser_modes():
    """Modes worth trying on this system, in order."""
    return [m for m in BROWSER_MODES if m[0] != "wayland" or os.environ.get("WAYLAND_DISPLAY")]


def session_kind() -> str:
    """Steam Deck Gaming Mode (gamescope) and a normal desktop may need different setups."""
    from ..app import App
    return "gaming" if App._in_gamescope() else "desktop"


def saved_mode(app) -> str:
    m = app.config["browser_mode"]
    return (m or {}).get(session_kind(), "") if isinstance(m, dict) else ""


def save_mode(app, mode):
    m = app.config["browser_mode"]
    m = dict(m) if isinstance(m, dict) else {}
    if mode:
        m[session_kind()] = mode
    else:
        m.pop(session_kind(), None)
    app.config["browser_mode"] = m


def browser_log() -> Path:
    return cache_dir() / "browser.log"


def _clean_env():
    """Our environment minus what Steam adds to everything a game starts: its overlay (LD_PRELOAD,
    which hooks the very OpenGL calls the browser needs) and its runtime library paths."""
    env = os.environ.copy()
    pre = [p for p in env.get("LD_PRELOAD", "").replace(":", " ").split() if "gameoverlayrenderer" not in p]
    if pre:
        env["LD_PRELOAD"] = " ".join(pre)
    else:
        env.pop("LD_PRELOAD", None)
    lib = [p for p in env.get("LD_LIBRARY_PATH", "").split(":")
           if p and "steam-runtime" not in p and "ubuntu12_" not in p and "steamrt" not in p]
    if lib:
        env["LD_LIBRARY_PATH"] = ":".join(lib)
    else:
        env.pop("LD_LIBRARY_PATH", None)
    for k in ("QTWEBENGINE_CHROMIUM_FLAGS", "QTWEBENGINE_DISABLE_SANDBOX", "QT_XCB_GL_INTEGRATION",
              "LIBGL_ALWAYS_SOFTWARE", "QT_QPA_PLATFORM", "QT_QUICK_BACKEND"):
        env.pop(k, None)
    return env


def _browser_env(mode: str):
    root = Path(__file__).resolve().parents[3]   # project folder containing the retrohome package
    env = _clean_env()
    env["PYTHONPATH"] = str(root) + os.pathsep + env.get("PYTHONPATH", "")
    env.update(dict(BROWSER_MODES)[mode] if mode in dict(BROWSER_MODES) else {})
    return env


def _launch_browser(app, cmd, mode):
    root = Path(__file__).resolve().parents[3]
    try:
        log = open(browser_log(), "w", encoding="utf-8", errors="replace")
    except OSError:
        log = subprocess.DEVNULL
    try:
        return subprocess.Popen(cmd, cwd=None if FROZEN else str(root), env=_browser_env(mode),
                                stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT)
    finally:
        if log is not subprocess.DEVNULL:
            log.close()      # the child has its own copy


def _start_browser(app, args, title, folder, on_close=None):
    report = cache_dir() / f"browser-report-{os.getpid()}-{int(time.time())}.json"
    launcher = [sys.executable, "--browser"] if FROZEN else [sys.executable, "-m", "retrohome.browser"]
    cmd = [*launcher, *args, "--rom-dir", str(app.config["rom_dir"]), "--report", str(report), "--title", title]
    if app.config["fullscreen"]:
        cmd.append("--fullscreen")
    cmd += ["--pad-family", app.input.pad_family]
    modes = [m for m, _ in browser_modes()]
    saved = saved_mode(app)
    if saved in modes:          # the setup that worked last time first, then the others
        modes = [saved] + [m for m in modes if m != saved]
    start = 0
    try:
        proc = _launch_browser(app, cmd, modes[start])
    except OSError as e:
        app.dialog("Couldn't open the browser", str(e))
        return
    scr = BrowserOpen(app, proc, report, title, folder, on_close)
    scr.cmd, scr.modes, scr.mode_i = cmd, modes, start
    app.push(scr)


def _last_log_line():
    try:
        lines = [ln.strip() for ln in browser_log().read_text(encoding="utf-8", errors="replace").splitlines()]
    except OSError:
        return ""
    noise = ("Detected locale", "Qt depends on", "If this causes", "for more information")
    useful = [ln for ln in lines if ln and not ln.startswith(noise)]
    fatal = [ln for ln in useful if "FATAL" in ln or "Fatal" in ln or "Check failed" in ln or "Could not" in ln]
    return (fatal or useful or [""])[-1][-220:]


class BrowserOpen(Screen):
    background_input = True     # see Start/Home presses even while the browser window has focus

    def __init__(self, app, proc, report, title, folder, on_close=None):
        super().__init__(app)
        self.proc, self.report, self.title, self.folder = proc, Path(report), title, folder
        self.on_close = on_close
        self.cmd, self.modes, self.mode_i = None, ["normal"], 0
        self.started = time.time()
        self.results = []
        self.last_read = 0
        self.closing = False
        self.ready = False
        self.minimized = False

    @property
    def close_flag(self):
        return self.report.with_suffix(".close")

    @property
    def ready_flag(self):
        return self.report.with_suffix(".ready")

    def on_action(self, a):
        # Start / Options / Menu / + or the Home (PS / Xbox) button closes the browser; so does B here
        # (RetroHome's own screen), so it can't get stuck if the browser window never shows up
        if a == "b" and self.ready and not pygame.key.get_focused():
            return          # B in the browser window is "back a page", not "close"
        if a in ("start", "guide", "b") and not self.closing:
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
            if not self.ready and self.ready_flag.exists():
                self.ready = True
                if not self.minimized and not self.closing:
                    self.minimized = self.app.minimize_window()   # get out of the browser's way
        code = self.proc.poll()
        mode = self.modes[self.mode_i]
        if code is None and self.ready and saved_mode(self.app) != mode and time.time() - self.started > 5:
            save_mode(self.app, mode)        # this setup works here: start with it next time
        if code not in (0, None) and not self.ready and not self.results and not self.closing and self.cmd \
                and self.mode_i + 1 < len(self.modes):
            # crashed before its window appeared (e.g. exit code -6): try the next graphics setup
            try:
                self.mode_i += 1
                self.proc = _launch_browser(self.app, self.cmd, self.modes[self.mode_i])
                self.started = time.time()
                self.app.toast(f"The browser crashed - trying again ({MODE_NAMES[self.modes[self.mode_i]]})")
                return
            except OSError:
                pass
        if code is None:
            # the browser closes itself on the flag; if it doesn't, end it
            waited = time.time() - getattr(self, "close_requested", time.time()) if self.closing else 0
            if waited > 8:
                self.proc.kill()
            elif waited > 4:
                self.proc.terminate()
            return
        for f in (self.ready_flag,):
            try:
                f.unlink()
            except OSError:
                pass
        if self.minimized:
            self.app.restore_window()
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
        if self.on_close:
            self.on_close(self.results)
        elif not self.folder:     # a profile page: pick up anyone just followed
            app.friends.refresh(force=True)
        if added:
            app.toast(f"Added {added} file(s) to {self.folder} - rescanning")

            def rescanned():
                app.ra.match_library(on_match=app._on_ra_match)
            app.library.scan(on_done=rescanned)
        if errors:
            app.dialog("Some downloads weren't added", " · ".join(errors[:4]))
        if code not in (0, None) and not self.results and not self.closing:
            last = _last_log_line()
            fix = ("Reinstall it from Settings > Browser for the RA Library." if not FROZEN else
                   "Please send the log file to the developer.")
            app.dialog("The browser closed unexpectedly",
                       f"Exit code {code}" + (f" (tried {len(self.modes)} graphics setups)" if self.mode_i else "")
                       + f". {fix} "
                       f"Log: {browser_log()}" + (f"  ·  Last message: {last}" if last else ""))

    def draw(self, s):
        gfx.blit_text(s, "Browser open", (gfx.W // 2, gfx.H // 2 - 80), 22, gfx.TEXT_DIM, anchor="center")
        gfx.blit_text(s, self.title, (gfx.W // 2, gfx.H // 2 - 36), 36, gfx.TEXT, True, max_w=1100, anchor="center")
        sub = getattr(self, "sub", None) or (
            f"Downloads are unpacked into roms/{get_system(self.folder).folder} automatically." if self.folder
            else "Press Follow on their page to add them as a friend.")
        gfx.blit_text(s, sub, (gfx.W // 2, gfx.H // 2 + 10), 18, gfx.TEXT_DIM, anchor="center")
        y = gfx.H // 2 + 60
        for r in self.results[-5:]:
            col = gfx.GREEN if r.get("status") == "ok" else gfx.GOLD
            gfx.blit_text(s, r.get("message", ""), (gfx.W // 2, y), 17, col, anchor="center", max_w=1000)
            y += 26
        from ...padstyle import text_label
        start = text_label(self.app.input.pad_family, 'start')
        if self.closing:
            msg = "Closing the browser…"
        elif not self.ready and time.time() - self.started > 15:
            msg = "The browser hasn't appeared. Press B to stop it and come back."
        elif not self.ready:
            msg = "Opening the browser…"
        else:
            msg = f"Press {start} on your controller, or close the browser window, to come back."
        gfx.blit_text(s, msg, (gfx.W // 2, gfx.H - 90), 16, gfx.TEXT_FAINT, anchor="center")

    def hints(self):
        return [] if self.closing else [("b", "Close browser")]


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
