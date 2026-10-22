"""First-run setup: ROM folder and RetroAchievements sign-in."""
import os
import string
from pathlib import Path

import pygame

from ...paths import IS_WINDOWS, default_new_rom_dir, default_rom_dir_candidates
from ...retroach import RAError, RetroAchievements
from ...scanner import ensure_rom_dir
from ...systems import ALL_FOLDERS
from .. import gfx
from ..app import Screen
from .keyboard import Keyboard
from .menu import Menu


def _count_system_folders(p: Path) -> int:
    try:
        names = {e.name.lower() for e in os.scandir(p) if e.is_dir()}
    except OSError:
        return 0
    return len(names & set(ALL_FOLDERS))


def choose_rom_dir(app, path: Path, then):
    """Validate/create the folder, save it, then call then()."""
    path = Path(path)

    def save():
        app.config["rom_dir"] = str(path)
        then()

    def create():
        try:
            ensure_rom_dir(path)
        except OSError as e:
            app.dialog("Couldn't create folder", str(e))
            return
        app.toast(f"Created {path}")
        save()

    if not path.exists():
        app.dialog("Create ROM folder?",
                   f"{path} doesn't exist yet. Create it with a sub-folder for each system "
                   f"(nes, snes, psx, ...) like EmuDeck does?",
                   [("Create", create), ("Cancel", None)])
        return
    if _count_system_folders(path) == 0:
        app.dialog("No system folders found",
                   f"{path} has no system folders (nes, snes, gba, ...). Create them here, "
                   f"or use the folder as it is?",
                   [("Create folders", create), ("Use as is", save), ("Cancel", None)])
        return
    save()


class Welcome(Menu):
    def __init__(self, app, from_settings=False):
        self.from_settings = from_settings
        super().__init__(
            app,
            "Choose your ROM folder" if from_settings else "Welcome to RetroHome",
            "RetroHome needs EmuDeck (emudeck.com): EmuDeck installs the emulators that launch your "
            "games. Point RetroHome at the Emulation/roms folder EmuDeck made.",
            on_back=(lambda: app.pop()) if from_settings else None,
            step="" if from_settings else "FIRST-TIME SETUP",
        )
        items = []
        for c in default_rom_dir_candidates():
            n = _count_system_folders(c)
            items.append((f"Use {c}", f"Found {n} system folders" if n else "Folder exists",
                          lambda c=c: choose_rom_dir(app, c, self._next)))
        items.append(("Browse for a folder…", "Pick any folder with the controller",
                      lambda: app.push(FolderBrowser(app, self._picked))))
        new = default_new_rom_dir()
        if not new.exists():
            items.append(("Create a new ROM folder", str(new),
                          lambda: choose_rom_dir(app, new, self._next)))
        if not from_settings:
            items.append(("Quit", "", app.quit))
        self.set_items(items)

    def _picked(self, path):
        choose_rom_dir(self.app, path, self._next)

    def _next(self):
        if self.from_settings:
            self.app.open_library()
            self.app.toast("ROM folder changed")
            return
        cfg = self.app.config
        if not cfg.profiles:
            from .users import UserSelect
            self.app.stack = [UserSelect(self.app, first_run=True)]
        elif cfg.active_id:
            self.app.activate_profile(cfg.active_id)
        else:
            from .users import UserSelect
            self.app.stack = [UserSelect(self.app)]


class FolderBrowser(Screen):
    def __init__(self, app, on_pick, start=None, title="Select ROM folder", check=_count_system_folders):
        super().__init__(app)
        self.on_pick = on_pick
        self.title = title
        self.check = check
        start = Path(start) if start else (Path(app.config["rom_dir"]) if app.config["rom_dir"] else Path.home())
        while not start.exists() and start != start.parent:
            start = start.parent
        self.path = start if start.exists() else None
        self.sel = 0
        self.scroll = 0
        self.entries = []
        self._load()

    def _roots(self):
        if IS_WINDOWS:
            out = []
            for L in string.ascii_uppercase:
                p = Path(f"{L}:/")
                try:
                    if p.exists():
                        out.append((f"{L}:\\", p))
                except OSError:
                    pass
            out.append(("Home", Path.home()))
            return out
        out = [("Home", Path.home()), ("/ (root)", Path("/"))]
        for m in (Path("/run/media"), Path("/media"), Path("/mnt")):
            if m.is_dir():
                out.append((f"{m}  (SD cards & drives)", m))
        return out

    def _load(self):
        if self.path is None:
            self.entries = self._roots()
        else:
            self.entries = [("..  Up one level", None)]
            try:
                dirs = sorted((e.name for e in os.scandir(self.path) if e.is_dir() and not e.name.startswith(".")),
                              key=str.lower)
            except OSError:
                dirs = []
            self.entries += [(d, self.path / d) for d in dirs]
        self.sel = 0
        self.scroll = 0

    def _up(self):
        if self.path is None:
            return
        parent = self.path.parent
        self.path = None if parent == self.path else parent
        self._load()

    def on_action(self, a):
        n = len(self.entries)
        if a == "up" and n:
            self.sel = (self.sel - 1) % n
        elif a == "down" and n:
            self.sel = (self.sel + 1) % n
        elif a == "lb":
            self.sel = max(0, self.sel - 8)
        elif a == "rb":
            self.sel = min(n - 1, self.sel + 8)
        elif a == "a" and n:
            label, p = self.entries[self.sel]
            if p is None:
                self._up()
            else:
                self.path = p
                self._load()
        elif a == "b":
            if self.path is None:
                self.app.pop()
            else:
                self._up()
        elif a == "x" and self.path is not None:
            p = self.path
            self.app.pop()
            self.on_pick(p)
        elif a == "y" and self.path is not None:
            def made(name):
                if not name:
                    return
                try:
                    (self.path / name).mkdir(exist_ok=True)
                    self.path = self.path / name
                    self._load()
                except OSError as e:
                    self.app.dialog("Couldn't create folder", str(e))
            self.app.push(Keyboard(self.app, "New folder name", "roms", made))
        elif a == "select":
            self.app.pop()

    def draw(self, s):
        gfx.blit_text(s, self.title, (120, 60), 36, gfx.TEXT, True)
        cur = str(self.path) if self.path else "This computer"
        gfx.blit_text(s, cur, (120, 112), 20, gfx.ACCENT_HI, max_w=gfx.W - 240)
        if self.path and self.check:
            n = self.check(self.path)
            if n:
                gfx.blit_text(s, f"✓ Looks like a ROM folder ({n} systems) — press X to use it",
                              (120, 140), 18, gfx.GREEN)
        elif self.path:
            gfx.blit_text(s, "Open the folder, then press X to use it", (120, 140), 18, gfx.TEXT_DIM)
        y0, row_h = 180, 52
        visible = (gfx.H - 80 - y0) // row_h
        if self.sel < self.scroll:
            self.scroll = self.sel
        elif self.sel >= self.scroll + visible:
            self.scroll = self.sel - visible + 1
        for i in range(self.scroll, min(len(self.entries), self.scroll + visible)):
            label, _ = self.entries[i]
            r = pygame.Rect(120, y0 + (i - self.scroll) * row_h, gfx.W - 240, row_h - 8)
            sel = i == self.sel
            gfx.rrect(s, gfx.PANEL_HI if sel else gfx.PANEL, r, 10)
            if sel:
                gfx.glow_border(s, r, 10, self.app.t)
            icon = "↑" if self.entries[i][1] is None else "▸"
            gfx.blit_text(s, f"{icon}  {label}", (r.x + 18, r.centery), 20, gfx.TEXT, max_w=r.w - 36, anchor="midleft")
        if not self.entries:
            gfx.blit_text(s, "(empty)", (120, y0), 20, gfx.TEXT_FAINT)

    def hints(self):
        h = [("a", "Open"), ("b", "Up")]
        if self.path is not None:
            h += [("x", "Use this folder"), ("y", "New folder")]
        return h


class RASetup(Menu):
    def __init__(self, app, first_run=False):
        self.first_run = first_run
        self.user = app.config["ra_user"] or ""
        self.key = app.config["ra_key"] or ""
        self.status = ""
        self.busy = False
        super().__init__(
            app, "RetroAchievements",
            "Sign in to track achievements on the home screen. Easiest: Sign in with password - "
            "RetroHome opens retroachievements.org and picks up your Web API key for you. Or type your "
            "username and Web API key (retroachievements.org → Settings → Keys). Also sign in to "
            "RetroAchievements inside RetroArch / your emulators so they can unlock.",
            on_back=self._back, step="LINK YOUR ACCOUNT" if first_run else "")
        self._build()

    def _back(self):
        if self.first_run:
            self.app.open_library()
        else:
            self.app.pop()

    def _build(self):
        masked = (self.key[:4] + "•" * max(0, len(self.key) - 4)) if self.key else "Not set"
        items = [
            ("Sign in with password", "Opens retroachievements.org - sign in there and RetroHome finds your key",
             self._password_sign_in),
            ("Username", self.user or "Not set", lambda: self.app.push(
                Keyboard(self.app, "RetroAchievements username", self.user, self._set_user))),
            ("Web API key", masked, lambda: self.app.push(
                Keyboard(self.app, "Web API key", self.key, self._set_key, secret=True,
                         hint="retroachievements.org → Settings → Keys → Web API Key"))),
            ("Sign in", self.status or "Checks your details and saves them", self._verify),
        ]
        if self.app.config.ra_enabled:
            items.append(("Sign out", "Remove saved RetroAchievements details", self._sign_out))
        items.append(("Skip for now" if self.first_run else "Back", "", self._back))
        self.set_items(items)

    def _password_sign_in(self):
        from ...rakey import SETTINGS_URL
        from .ralib import open_page

        def closed(results):
            found = next((r for r in reversed(results or []) if r.get("status") == "ra_key"), None)
            if not found:
                self.status = "No key found - sign in on the page, or type your key below"
                self._build()
                return
            self.key = found["key"]
            self.user = found.get("user") or self.user
            if self.user:
                self._verify()
            else:
                self._build()
                self.app.push(Keyboard(self.app, "RetroAchievements username", "",
                                       lambda v: (self._set_user(v), self._verify())))
        open_page(self.app, SETTINGS_URL, "Sign in to RetroAchievements", ["--grab-ra-key"], closed)
        top = self.app.top
        if type(top).__name__ == "BrowserOpen":
            top.sub = "Sign in on the page. RetroHome picks up your Web API key and signs you in."

    def _set_user(self, v):
        self.user = v
        self._build()

    def _set_key(self, v):
        self.key = v.replace(" ", "")
        self._build()

    def _verify(self):
        if self.busy:
            return
        if not self.user or not self.key:
            self.status = "Enter both your username and Web API key first"
            self._build()
            return
        self.busy = True
        self.status = "Checking…"
        self._build()
        client = RetroAchievements(self.user, self.key)

        def ok(profile):
            self.busy = False
            self.app.config.profile["ra_user"] = profile.get("User") or self.user
            self.app.config["ra_key"] = self.key
            self.app.toast(f"Signed in as {profile.get('User', self.user)}")
            if self.first_run:
                self.app.open_library()
            else:
                self.app.pop()
                self.app.ra.reconfigure()
                self.app.ra.refresh(force=True)
                self.app.ra.match_library(on_match=self.app._on_ra_match)

        def bad(e):
            self.busy = False
            self.status = str(e) if isinstance(e, RAError) else f"Error: {e}"
            self._build()
        self.app.tasks.submit(client.verify, callback=ok, error=bad)

    def _sign_out(self):
        self.app.config.profile["ra_user"] = ""
        self.app.config["ra_key"] = ""
        self.user = self.key = ""
        self.app.ra.reconfigure()
        for g in self.app.library.all:
            g.ra_game_id = 0
            g.ra_title = ""
        self.app.library.version += 1
        self.status = ""
        self._build()
