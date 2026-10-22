"""Main loop, screen stack and shared UI pieces."""
import os
import sys
import time
import traceback
from pathlib import Path

os.environ.setdefault("SDL_VIDEO_MINIMIZE_ON_FOCUS_LOSS", "0")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
# Read controllers even while another window (the built-in browser) has focus. Screens only act on
# that background input when they opt in (BrowserOpen does, to close the browser with Start).
os.environ.setdefault("SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS", "1")

import pygame  # noqa: E402

from .. import APP_NAME  # noqa: E402
from ..artwork import Artwork  # noqa: E402
from ..config import Config  # noqa: E402
from ..emulators import Emulators, LaunchError  # noqa: E402
from ..library import Library, RAState  # noqa: E402
from ..paths import is_steam_deck  # noqa: E402
from ..tasks import Tasks  # noqa: E402
from . import gfx  # noqa: E402
from .input import Input  # noqa: E402


HINT_TEXT = 15     # button-prompt text size (bottom right)


class Screen:
    opaque = True

    def __init__(self, app):
        self.app = app

    def on_action(self, a):
        pass

    def on_event(self, e):
        pass

    def update(self, dt):
        pass

    def draw(self, s):
        pass

    def hints(self):
        return [("a", "Select"), ("b", "Back")]

    def on_resume(self):
        pass


# ------------------------------------------------------------------ dialog
class Dialog(Screen):
    opaque = False

    def __init__(self, app, title, body="", options=(("OK", None),), on_cancel=None):
        super().__init__(app)
        self.title = title
        self.body = body
        self.options = list(options)
        self.sel = 0
        self.on_cancel = on_cancel

    def on_action(self, a):
        if a in ("left", "up"):
            self.sel = (self.sel - 1) % len(self.options)
        elif a in ("right", "down"):
            self.sel = (self.sel + 1) % len(self.options)
        elif a == "a":
            cb = self.options[self.sel][1]
            self.app.pop()
            if cb:
                cb()
        elif a == "b":
            self.app.pop()
            if self.on_cancel:
                self.on_cancel()

    def draw(self, s):
        dim = gfx.layer((gfx.W, gfx.H))
        dim.fill((0, 0, 0, 170))
        s.blit(dim, (0, 0))
        lines = gfx.wrap(self.body, 20, 600, max_lines=8) if self.body else []
        h = 130 + len(lines) * 28 + 70
        box = pygame.Rect(0, 0, 680, h)
        box.center = (gfx.W // 2, gfx.H // 2)
        gfx.rrect(s, (24, 32, 58), box, 18)
        gfx.rrect(s, (255, 255, 255, 30), box, 18, 1)
        gfx.blit_text(s, self.title, (box.x + 40, box.y + 34), 28, gfx.TEXT, True, max_w=600)
        y = box.y + 86
        for ln in lines:
            gfx.blit_text(s, ln, (box.x + 40, y), 20, gfx.TEXT_DIM)
            y += 28
        bx = box.right - 40
        for i in reversed(range(len(self.options))):
            label = self.options[i][0]
            tw = gfx.measure(label, 20, True)[0] + 48
            r = pygame.Rect(bx - tw, box.bottom - 70, tw, 44)
            sel = i == self.sel
            gfx.rrect(s, gfx.TEXT if sel else (255, 255, 255, 28), r, 22)
            gfx.blit_text(s, label, r.center, 20, (10, 14, 30) if sel else gfx.TEXT, True, anchor="center")
            bx = r.x - 14

    def hints(self):
        return [("a", "Select"), ("b", "Cancel")]


# ------------------------------------------------------------------ playing overlay
class Playing(Screen):
    def __init__(self, app, game, proc, label):
        super().__init__(app)
        self.game, self.proc, self.label = game, proc, label
        self.started = time.time()

    def update(self, dt):
        if self.proc.poll() is not None:
            self.app.game_finished(self.game, time.time() - self.started, self.proc.returncode)

    def on_action(self, a):
        pass

    def draw(self, s):
        s.fill(gfx.BG)
        art = self.app.artwork.get(self.game, fetch=False)
        if art:
            bg = self.app.images.derive(("blurbg", gfx.W, gfx.H), art, lambda im: gfx.blur(gfx.cover(im, gfx.W, gfx.H)))
            if bg:
                s.blit(bg, (0, 0))
                shade = gfx.layer((gfx.W, gfx.H))
                shade.fill((0, 0, 0, 150))
                s.blit(shade, (0, 0))
        mins = int(time.time() - self.started) // 60
        gfx.blit_text(s, "Now playing", (gfx.W // 2, gfx.H // 2 - 70), 22, gfx.TEXT_DIM, anchor="center")
        gfx.blit_text(s, self.game.display_title, (gfx.W // 2, gfx.H // 2 - 20), 40, gfx.TEXT, True, max_w=1100, anchor="center")
        gfx.blit_text(s, f"{self.game.system.name}  ·  {self.label}  ·  {mins} min",
                      (gfx.W // 2, gfx.H // 2 + 30), 20, gfx.TEXT_DIM, anchor="center")
        gfx.blit_text(s, "Close the emulator to return here.", (gfx.W // 2, gfx.H // 2 + 90), 18, gfx.TEXT_FAINT, anchor="center")

    def hints(self):
        return []


# ------------------------------------------------------------------ app
class App:
    def __init__(self):
        pygame.init()
        self.config = Config()
        pygame.display.set_caption(APP_NAME)
        try:
            from ..paths import resource
            pygame.display.set_icon(pygame.image.load(str(resource("assets", "icon.png"))))
        except Exception:  # noqa: BLE001
            pass
        self.display = None
        self.canvas = None
        self._open_display(fullscreen=bool(self.config["fullscreen"] or is_steam_deck()))
        pygame.mouse.set_visible(False)
        self.clock = pygame.time.Clock()
        self.tasks = Tasks()
        self.input = Input()
        self.images = gfx.Images(self.tasks)
        self.stack = []
        self.toasts = []
        self.t = 0.0
        self.running = True
        self.library = Library(self.config, self.tasks)
        self.ra = RAState(self.config, self.tasks, self.library)
        self.ra.on_progress = lambda: self.sync_online()
        from ..friends import Friends
        self.friends = Friends(self.ra, self.tasks)
        from ..newsets import NewSets
        self.new_sets = NewSets(self.ra, self.tasks)
        self.emus = None
        self.artwork = None
        self.playing = None
        self.pending_update = None  # release info when a newer version is on GitHub
        self._update_checked = False
        self.online = None        # accounts.OnlineClient for the signed-in user, if any
        self.online_status = ""

    # ------------------------------------------------------------ window size
    WINDOW_SIZES = [(1280, 800), (1440, 900), (1600, 1000), (1920, 1200), (2240, 1400), (2560, 1600)]

    def _open_display(self, fullscreen, size=None):
        """Open the window at its real pixel size; the UI is rendered natively into it."""
        if fullscreen:
            self.display = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
        else:
            w, h = size or self.config["window_size"]
            mw, mh = self.max_window_size()
            sc = min(1.0, mw / w, mh / h)
            self.display = pygame.display.set_mode((max(640, int(w * sc)), max(400, int(h * sc))),
                                                   pygame.RESIZABLE)
        self._layout()

    def _layout(self):
        """Fit the logical canvas to the window at native resolution.

        The layout is 800 logical px tall (1280 wide on a 16:10 Deck). Wider screens get a wider
        logical canvas (16:9 -> 1422, 21:9 -> 1867) and narrower ones a taller one, so the UI
        fills the screen instead of being letterboxed. Extreme shapes are clamped and centred.
        """
        self.display = pygame.display.get_surface() or self.display
        rw, rh = self.display.get_size()
        aspect = max(1.25, min(2.4, rw / max(1, rh)))
        if aspect >= 1.6:
            lw, lh = int(round(800 * aspect)), 800
        else:
            lw, lh = 1280, int(round(1280 / aspect))
        k = max(0.25, min(rw / lw, rh / lh))
        cw, ch = min(rw, int(round(lw * k))), min(rh, int(round(lh * k)))
        rect = pygame.Rect((rw - cw) // 2, (rh - ch) // 2, cw, ch)
        if gfx.set_view(k, lw, lh) and getattr(self, "images", None):
            self.images.clear_scaled()
        self.canvas = gfx.Layer(self.display.subsurface(rect), k)
        self.bg = gfx.vgradient((gfx.W, gfx.H), gfx.BG2 + (255,), gfx.BG + (255,))

    def window_size(self):
        return tuple(self.display.get_size()) if self.display else tuple(self.config["window_size"])

    def max_window_size(self):
        try:
            dw, dh = pygame.display.get_desktop_sizes()[0]
            return dw - 40, dh - 80
        except Exception:  # noqa: BLE001
            return 3840, 2160

    def set_window_size(self, w, h, save=True):
        self._open_display(False, (w, h))
        if save:
            self.config["window_size"] = list(self.window_size())
        return True

    def step_window_size(self, delta):
        """Next/previous preset size (Ctrl + / Ctrl -, or Settings > Window size)."""
        if self.config["fullscreen"]:
            self.config["fullscreen"] = False
        cur = self.window_size()
        mw, mh = self.max_window_size()
        sizes = []
        for w, h in self.WINDOW_SIZES:          # presets that fit this screen, without duplicates
            sc = min(1.0, mw / w, mh / h)
            fitted = (int(w * sc), int(h * sc))
            if fitted not in sizes:
                sizes.append(fitted)
        idx = min(range(len(sizes)), key=lambda i: abs(sizes[i][0] - cur[0]))
        idx = max(0, min(len(sizes) - 1, idx + delta))
        self.set_window_size(*sizes[idx])
        w, h = self.window_size()
        self.toast(f"Window {w}×{h}")

    # ------------------------------------------------------------ stack
    def push(self, screen):
        self.stack.append(screen)
        self.input.reset()

    def pop(self):
        if self.stack:
            self.stack.pop()
        self.input.reset()
        if self.stack:
            self.stack[-1].on_resume()

    def replace(self, screen):
        if self.stack:
            self.stack.pop()
        self.push(screen)

    @property
    def top(self):
        return self.stack[-1] if self.stack else None

    def toast(self, msg, secs=3.5):
        self.toasts = [t for t in self.toasts if t[0] != msg]    # no duplicates
        self.toasts.append([msg, secs])
        self.toasts = self.toasts[-3:]                          # at most three on screen

    def dialog(self, title, body="", options=(("OK", None),), on_cancel=None):
        self.push(Dialog(self, title, body, options, on_cancel))

    # ------------------------------------------------------------ library lifecycle
    def open_library(self):
        """(Re)build services for the configured ROM folder and go home."""
        rom_dir = Path(self.config["rom_dir"])
        self.emus = Emulators(self.config.emulation_dir)
        self.artwork = Artwork(self.config.emulation_dir, rom_dir, self.tasks, ra_boxart=self.ra.boxart_for,
                               ra_images=self.ra.images_for)
        self.ra.reconfigure()
        from .screens.home import Home
        self.stack = [Home(self)]

        def scanned():
            self.ra.match_library(on_match=self._on_ra_match)
            self.ra.refresh(force=True)
        self.library.scan(on_done=scanned)
        if not self._update_checked:
            self._update_checked = True
            from ..updater import should_auto_check
            if should_auto_check(self.config):
                from .screens.update import check_for_updates
                check_for_updates(self)

    @property
    def only_ra(self):
        """Show only games that have a RetroAchievements set (when signed in)."""
        return self.ra.enabled and not self.config["show_all_games"]

    # ------------------------------------------------------------ users
    def activate_profile(self, pid):
        """Switch to a user and go to their home screen (or finish their setup)."""
        self.config.set_active(pid)
        self.ra.reconfigure()
        self.online = None
        self.online_status = ""
        remote = self.config["remote"] or {}
        if remote.get("token") and remote.get("server"):
            from ..accounts import OnlineClient
            try:
                self.online = OnlineClient(remote["server"], remote["token"])
                self.sync_online(pull=True)
            except Exception as e:  # noqa: BLE001
                self.online_status = str(e)
        from .screens.setup import Welcome
        if not (self.config["rom_dir"] and Path(self.config["rom_dir"]).is_dir()):
            self.stack = [Welcome(self)]
            return
        self.open_library()

    def sync_online(self, pull=False):
        """Upload level/awards and merge favourites + play history with the server."""
        client = self.online
        if not client:
            return
        from ..accounts import AccountError, merge_library
        prof = self.config.profile
        prog = self.ra.prog
        stats = None
        if prog:
            a = prog.awards
            stats = {"level": prog.level, "xp": prog.xp, "mythic": a.get("mythic", 0),
                     "platinum": a.get("platinum", 0),
                     "ra_user": self.config["ra_user"]}
        lock = self.__dict__.setdefault("_sync_lock", __import__("threading").Lock())

        def work():
            with lock:   # one sync at a time, each working from the latest local state
                local = {"favourites": list(prof.get("favourites", [])), "history": dict(prof.get("history", {})), "fav_events": dict(prof.get("fav_events", {}))}
                merged = merge_library(local, client.get_library())
                client.put_library(merged)
                if stats:
                    client.push_stats(stats)
                return merged

        def done(merged):
            if self.online is not client:
                return
            now = {"favourites": list(prof.get("favourites", [])), "history": dict(prof.get("history", {})), "fav_events": dict(prof.get("fav_events", {}))}
            both = merge_library(now, merged)   # never drop a change made while syncing
            prof["favourites"] = both["favourites"]
            prof["history"] = both["history"]
            prof["fav_events"] = both["fav_events"]
            self.config.save()
            self.library.version += 1
            self.online_status = "Synced"

        def fail(e):
            self.online_status = str(e) if isinstance(e, AccountError) else f"Sync failed: {e}"
        self.tasks.submit(work, callback=done, error=fail)

    def _on_ra_match(self, game):
        # games whose art failed may now have RetroAchievements box art
        if self.artwork and self.artwork.state.get(game.id) is None and game.id in self.artwork.state:
            self.artwork.refresh(game)

    def launch(self, game, disc_path=None):
        if self.playing:
            return
        if game.discs and disc_path is None:
            from .screens.discs import DiscPicker
            self.push(DiscPicker(self, game))
            return
        try:
            proc, label, cmd = self.emus.launch(game, disc_path)
        except LaunchError as e:
            self.dialog("Can't start game", str(e))
            return
        print("Launching:", " ".join(cmd), flush=True)
        from .screens.report import snapshot
        self.session = snapshot(self, game)
        self.playing = Playing(self, game, proc, label)
        self.input.enabled = False
        self.push(self.playing)

    def game_finished(self, game, seconds, code):
        self.playing = None
        self.pop()
        self.input.enabled = True
        self.input.reset()
        pygame.event.clear()
        self.config.record_play(game.id, seconds)
        self.library.version += 1
        if seconds < 3 and code not in (0, None):
            self.dialog("The emulator closed straight away",
                        f"It exited with code {code}. Check the emulator works on its own, or set its "
                        f"command in emulators.json (Settings shows where).")
        if self.ra.enabled:
            self.ra.refresh(force=True)
            if game.ra_game_id:
                self.ra.game_progress(game.ra_game_id, force=True)
            crashed = seconds < 3 and code not in (0, None)
            session = getattr(self, "session", None)
            if session and session["game"] is game and not crashed and game.ra_game_id:
                from .screens.report import Report
                self.push(Report(self, session, seconds))
        elif seconds >= 60:
            self.toast(f"Played {int(seconds // 60)} min")
        self.session = None
        if self.top and hasattr(self.top, "on_game_closed"):
            self.top.on_game_closed(game)
        self.sync_online()

    def toggle_fullscreen(self):
        self.config["fullscreen"] = not self.config["fullscreen"]
        self._open_display(self.config["fullscreen"])

    def quit(self):
        self.running = False

    # ------------------------------------------------------------ drawing helpers
    def hints_left(self, hints):
        """x where the button hints (drawn from the bottom-right) begin."""
        from ..padstyle import label
        kb = self.input.last_device == "keyboard"
        keys = {"a": "Enter", "b": "Esc", "x": "X", "y": "Y", "lb": "Q", "rb": "E", "start": "M",
                "select": "Tab", "guide": "Esc"}
        x = gfx.W - 36
        for btn, text in hints or []:
            x -= gfx.measure(text, HINT_TEXT)[0] + 10
            cap = keys.get(btn, btn) if kb else label(self.input.pad_family, btn)
            x -= (gfx.measure(cap, 12, True)[0] + 14 + 22) if (kb or btn not in ("a", "b", "x", "y")) else 44
        return x

    def draw_hints(self, s, hints, left=None, y=None):
        """Button prompts, right-aligned at the bottom right - or starting at `left` (centred on y)."""
        if not hints:
            return
        from ..padstyle import FACE_COLORS, label
        kb = self.input.last_device == "keyboard"
        fam = self.input.pad_family
        keys = {"a": "Enter", "b": "Esc", "x": "X", "y": "Y", "lb": "Q", "rb": "E", "start": "M",
                "select": "Tab", "guide": "Esc"}
        x = gfx.W - 36
        if left is not None:
            x = left + (gfx.W - 36 - self.hints_left(hints))
        y = gfx.H - 22 if y is None else y
        for btn, text in reversed(hints):
            lw = gfx.measure(text, HINT_TEXT)[0]
            x -= lw
            gfx.blit_text(s, text, (x, y), HINT_TEXT, gfx.TEXT_DIM, anchor="midleft")
            x -= 10
            cap = keys.get(btn, btn) if kb else label(fam, btn)
            if kb or btn not in ("a", "b", "x", "y"):
                tw = gfx.measure(cap, 12, True)[0] + 14
                r = pygame.Rect(x - tw, y - 10, tw, 20)
                gfx.rrect(s, (255, 255, 255, 40), r, 6)
                gfx.blit_text(s, cap, r.center, 12, gfx.TEXT, True, anchor="center")
                x = r.x - 22
                continue
            cx = x - 11
            if cap in FACE_COLORS["shapes"]:          # PlayStation: draw the symbol
                gfx.draw.circle(s, (34, 38, 52), (cx, y), 11)
                col = FACE_COLORS["shapes"][cap]
                if cap == "cross":
                    gfx.draw.line(s, col, (cx - 5, y - 5), (cx + 5, y + 5), 3)
                    gfx.draw.line(s, col, (cx - 5, y + 5), (cx + 5, y - 5), 3)
                elif cap == "circle":
                    gfx.draw.circle(s, col, (cx, y), 6, 2)
                elif cap == "square":
                    gfx.draw.rect(s, col, (cx - 5, y - 5, 10, 10), 2)
                else:
                    gfx.draw.polygon(s, col, [(cx, y - 6), (cx + 6, y + 4), (cx - 6, y + 4)], 2)
            else:
                col = (FACE_COLORS["nintendo"] if fam == "nintendo" else FACE_COLORS["letters"])[btn]
                gfx.draw.circle(s, col, (cx, y), 11)
                gfx.blit_text(s, cap, (cx, y + 1), 13, (12, 14, 24), True, anchor="center")
            x -= 22 + 22

    def draw_toasts(self, s, dt):
        y = 24
        for t in self.toasts:
            t[1] -= dt
            alpha = max(0, min(1, t[1] / 0.4))
            surf = gfx.text(t[0], 18, gfx.TEXT, max_w=520)
            r = pygame.Rect(0, 0, surf.get_width() + 40, 46)
            r.topright = (gfx.W - 24, y)
            box = gfx.layer(r.size)
            gfx.draw.rect(box, (30, 40, 70, int(235 * alpha)), box.get_rect(), border_radius=12)
            surf2 = surf.copy()
            surf2.set_alpha(int(255 * alpha))
            box.blit(surf2, surf2.get_rect(center=(r.w // 2, r.h // 2)))
            s.blit(box, r)
            y += 56
        self.toasts = [t for t in self.toasts if t[1] > 0]

    # ------------------------------------------------------------ loop
    def run(self):
        self.start()
        self.loop()

    def start(self):
        from .screens.setup import Welcome
        from .screens.users import UserSelect
        profiles = self.config.profiles
        if not (self.config["rom_dir"] and Path(self.config["rom_dir"]).is_dir()):
            self.push(Welcome(self))
        elif not profiles:
            self.push(UserSelect(self, first_run=True))
        else:
            pid = self.config.active_id or next(iter(profiles))
            only = len(profiles) == 1 and not profiles[pid].get("pin")
            if only and not self.config["ask_user_on_start"]:
                self.activate_profile(pid)
            else:
                self.push(UserSelect(self))

    def loop(self):
        while self.running:
            fps = 10 if self.playing else 60
            dt = self.clock.tick(fps) / 1000.0
            self.t += dt
            self.images.new_frame()
            self.tasks.pump()
            for e in pygame.event.get():
                if e.type == pygame.QUIT:
                    self.running = False
                    break
                if e.type in (pygame.VIDEORESIZE, getattr(pygame, "WINDOWSIZECHANGED", -1)):
                    if not self.config["fullscreen"]:
                        self._layout()
                        self.config.data["window_size"] = list(self.window_size())
                    continue
                if e.type == pygame.KEYDOWN and e.key == pygame.K_F11:
                    self.toggle_fullscreen()
                    continue
                if e.type == pygame.KEYDOWN and (e.mod & pygame.KMOD_CTRL) and e.key in (
                        pygame.K_EQUALS, pygame.K_PLUS, pygame.K_KP_PLUS, pygame.K_MINUS, pygame.K_KP_MINUS):
                    self.step_window_size(1 if e.key in (pygame.K_EQUALS, pygame.K_PLUS, pygame.K_KP_PLUS) else -1)
                    continue
                actions = self.input.process(e)
                top = self.top
                if top is None:
                    continue
                if actions and not pygame.key.get_focused() and not getattr(top, "background_input", False):
                    continue    # another window is focused: ignore stray controller presses
                try:
                    top.on_event(e)
                    for a in actions:
                        if self.top is top:
                            top.on_action(a)
                except Exception:  # noqa: BLE001
                    traceback.print_exc()
            self._maybe_celebrate()
            self._watch_friends()
            self._watch_updates()
            top = self.top
            if top:
                try:
                    for a in self.input.update(dt):
                        top.on_action(a)
                    top.update(dt)
                except Exception:  # noqa: BLE001
                    traceback.print_exc()
            self.render(dt)
        self.tasks.shutdown()
        pygame.quit()

    def _watch_updates(self):
        if not self._update_checked or self.playing or self.pending_update or self.t - getattr(
                self, "_upd_poll", -1e9) < 60:
            return
        self._upd_poll = self.t
        from ..updater import should_auto_check
        if should_auto_check(self.config, at_launch=False):
            from .screens.update import check_for_updates
            check_for_updates(self)

    def _watch_friends(self):
        """Every few minutes, see who started playing (people you follow on RetroAchievements)."""
        f = self.friends
        if self.playing or not self.ra.enabled or not self.stack:
            return
        if self.config["friend_alerts"]:
            f.refresh(every=180)
        while f.started:
            x = f.started.pop(0)
            self.toast(f"{x['user']} started playing {x['game']}" if x["game"] else f"{x['user']} is playing",
                       secs=6)

    def _maybe_celebrate(self):
        if self.pending_update and not self.playing:
            from .screens.home import Home
            if isinstance(self.top, Home):
                from .screens.update import UpdatePrompt
                info, self.pending_update = self.pending_update, None
                self.push(UpdatePrompt(self, info))
                return
        if not self.ra.events or self.playing:
            return
        from .screens.home import Home
        if not isinstance(self.top, Home):
            return
        from .screens.celebrate import Celebrate
        self.push(Celebrate(self, self.ra.events.pop(0)))
        self.sync_online()

    def render(self, dt):
        self.display.fill(gfx.BG)
        s = self.canvas
        s.blit(self.bg, (0, 0))
        start = 0
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i].opaque:
                start = i
                break
        for scr in self.stack[start:]:
            try:
                scr.draw(s)
            except Exception:  # noqa: BLE001
                traceback.print_exc()
        if self.top:
            self.draw_hints(s, self.top.hints())
        self.draw_toasts(s, dt)
        pygame.display.flip()


def main():
    try:
        App().run()
    except KeyboardInterrupt:
        pass
    sys.exit(0)
