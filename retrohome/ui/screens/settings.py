"""Settings menu."""
import os
from pathlib import Path

from ... import __version__
from .menu import Menu


class Settings(Menu):
    def __init__(self, app):
        super().__init__(app, "Settings", "", on_back=lambda: app.pop())
        self._build()

    def on_resume(self):
        self._build()

    def _build(self):
        app = self.app
        cfg = app.config
        lib = app.library
        ra_detail = f"Signed in as {cfg['ra_user']}" if cfg.ra_enabled else "Not signed in"
        n_games = len(lib.all)
        remote = cfg["remote"] or {}
        online = (f"Signed in as {remote.get('username')}" + (f" · {app.online_status}" if app.online_status else "")
                  if remote.get("token") else "Not signed in - sync your profile across devices")
        ww, wh = app.window_size()
        items = [
            ("Switch user", f"Signed in here as {cfg['name']}", self._switch),
            ("Account", "Rename, PIN, sign out, delete", self._account),
            ("RetroHome Online", online, self._online),
            ("RetroAchievements account", ra_detail, self._ra),
            ("Profile & trophies", "Level, XP, prestige styles, Platinum and Mythic awards", self._profile),
            ("ROM folder", cfg["rom_dir"] or "Not set", self._rom_dir),
            ("Rescan library", f"{n_games} games in {len(lib.by_system)} systems", self._rescan),
            ("Refresh achievements", "Re-download your profile and progress", self._refresh_ra),
            ("Retry missing pictures", "Look online again for box art and screenshots", self._retry_art),
            ("Window size", ("Fullscreen" if cfg["fullscreen"] else f"{ww} × {wh}") +
             "  ·  A: bigger, X: smaller  (or Ctrl + / Ctrl -, or drag the window edge)", self._bigger),
            ("Fullscreen", "On" if cfg["fullscreen"] else "Off  (F11 also toggles)", self._fullscreen),
            ("Show games without achievements", ("On - every game in your roms folder" if cfg["show_all_games"]
             else "Off - only games with a RetroAchievements set") +
             ("" if app.ra.enabled else " (applies once you sign in to RetroAchievements)"), self._toggle_all),
            ("Screenshot backgrounds", "On" if cfg["screenshot_backgrounds"] else "Off", self._toggle_shots),
            ("Ask who's playing at start-up", "On" if cfg["ask_user_on_start"] else "Off", self._toggle_ask),
            ("Browser for the RA Library", "Installed - A to reinstall/update" if self._browser_ok()
             else "Not installed - A to install (about 150-200 MB)", self._browser),
            ("Emulator setup", "Check which consoles are ready to play", self._emus),
            ("Emulators folder", (app.emus.overrides.get("emulators_dir") if app.emus else "") or
             "Automatic (finds EmuDeck's emulators)", self._emus_dir),
            ("Check for updates", f"You have RetroHome {__version__}", self._check_updates),
            ("Automatic update checks", "On - checks GitHub at start-up" if cfg["auto_update_check"] else "Off",
             self._toggle_updates),
            ("Quit RetroHome", "", self._quit),
        ]
        self.set_items(items)

    def on_action(self, a):
        if a == "x" and self.items and self.items[self.sel][0] == "Window size":
            self.app.step_window_size(-1)
            self._build()
            return
        super().on_action(a)

    def hints(self):
        h = super().hints()
        if self.items and self.items[self.sel][0] == "Window size":
            h = [("a", "Bigger"), ("x", "Smaller"), ("b", "Back")]
        return h

    @staticmethod
    def _browser_ok():
        from .ralib import browser_available
        return browser_available()

    def _browser(self):
        from ...paths import FROZEN
        if FROZEN:
            self.app.toast("The browser is built into this release" if self._browser_ok()
                           else "This release was built without the browser")
            return
        from .ralib import InstallBrowser
        self.app.push(InstallBrowser(self.app, lambda: None))

    def _switch(self):
        from .users import UserSelect
        self.app.push(UserSelect(self.app, switching=True))

    def _account(self):
        from .users import ManageUser
        if self.app.config.active_id:
            self.app.push(ManageUser(self.app, self.app.config.active_id))

    def _online(self):
        remote = self.app.config["remote"] or {}
        if remote.get("token"):
            self.app.sync_online(pull=True)
            self.app.toast("Syncing with RetroHome Online…")
            return
        from .users import OnlineSignIn
        self.app.push(OnlineSignIn(self.app))

    def _profile(self):
        from .profile import Profile
        self.app.push(Profile(self.app))

    def _bigger(self):
        self.app.step_window_size(1)
        self._build()

    def _toggle_all(self):
        self.app.config["show_all_games"] = not self.app.config["show_all_games"]
        self.app.library.version += 1
        self._build()

    def _check_updates(self):
        from .update import check_for_updates
        self.app.toast("Checking for updates…")
        check_for_updates(self.app, manual=True)

    def _toggle_updates(self):
        self.app.config["auto_update_check"] = not self.app.config["auto_update_check"]
        self._build()

    def _toggle_shots(self):
        self.app.config["screenshot_backgrounds"] = not self.app.config["screenshot_backgrounds"]
        self._build()

    def _toggle_ask(self):
        self.app.config["ask_user_on_start"] = not self.app.config["ask_user_on_start"]
        self._build()

    def _rom_dir(self):
        from .setup import Welcome
        self.app.push(Welcome(self.app, from_settings=True))

    def _rescan(self):
        self.app.pop()
        self.app.toast("Rescanning…")

        def done():
            self.app.ra.match_library(on_match=self.app._on_ra_match)
        self.app.library.scan(on_done=done)

    def _ra(self):
        from .setup import RASetup
        self.app.push(RASetup(self.app))

    def _refresh_ra(self):
        if not self.app.ra.enabled:
            self._ra()
            return
        self.app.ra.refresh(force=True)
        for g in self.app.library.all:
            if g.ra_game_id and g.ra_game_id in self.app.ra.progress:
                self.app.ra.game_progress(g.ra_game_id, force=True)
        self.app.toast("Refreshing achievements…")

    def _retry_art(self):
        art = self.app.artwork
        if not art:
            return
        n = 0
        for g in self.app.library.all:
            missing_art = art.state.get(g.id) is None and g.id in art.state
            missing_shots = art.shots.get(g.id) == []
            if missing_art or missing_shots:
                art.refresh(g)
                n += 1
        self.app.toast(f"Retrying pictures for {n} games")

    def _emus(self):
        emus = self.app.emus
        if emus is None:
            return
        emus.reload()
        from ...emulators import STANDALONE
        items = []
        found = []
        for emu_id, spec in STANDALONE.items():
            cmd = emus.find_standalone(emu_id)
            if cmd:
                found.append(spec["name"])
                where = cmd[1] if cmd[0] in ("bash", "flatpak") and len(cmd) > 1 else cmd[0]
                items.append((f"✓ {spec['name']}", str(where), None))
        systems = {g.system.folder: g for g in self.app.library.all}
        missing = []
        for folder, g in sorted(systems.items()):
            try:
                emus.resolve(g)
            except Exception as e:  # noqa: BLE001
                missing.append((f"✗ {g.system.name}", str(e), None))
        items = missing + items
        for line in emus.diagnostics():
            items.append(("Searched", line, None))
        sub = (f"Found {len(found)} emulators" + (f" · {len(missing)} of your consoles can't launch yet" if missing
                                                 else (" · all your consoles are ready" if systems else "")) +
               ". If EmuDeck's emulators aren't found, choose their folder in Settings > Emulators folder.")
        from .menu import Menu
        self.app.push(Menu(self.app, "Emulator setup", sub, items, on_back=self.app.pop))

    def _emus_dir(self):
        emus = self.app.emus
        if emus is None:
            return
        from .setup import FolderBrowser

        def picked(path):
            emus.set_emulators_dir(path)
            self._build()
            self._emus()

        def choose():
            home = Path(os.environ.get("USERPROFILE") or Path.home())
            start = next((p for p in (home / "emudeck" / "EmulationStation-DE" / "Emulators", home / "emudeck",
                                      Path.home() / "Applications", home) if p.is_dir()), home)
            self.app.push(FolderBrowser(self.app, picked, start=start, title="Select your emulators folder",
                                        check=None))

        def automatic():
            emus.set_emulators_dir("")
            self._build()
            self._emus()
        if emus.overrides.get("emulators_dir"):
            self.app.dialog("Emulators folder", f"Currently: {emus.overrides['emulators_dir']}",
                            [("Choose another", choose), ("Use automatic", automatic), ("Cancel", None)])
        else:
            choose()

    def _fullscreen(self):
        self.app.toggle_fullscreen()
        self._build()

    def _quit(self):
        self.app.dialog("Quit RetroHome?", "", [("Quit", self.app.quit), ("Cancel", None)])
