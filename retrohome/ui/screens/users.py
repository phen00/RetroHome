"""Who's playing? (user select), user management and RetroHome Online sign-in."""
import math

import pygame

from ...accounts import AccountError, OnlineClient, check_pin, hash_pin, online_server
from ...retroach import MEDIA
from .. import gfx
from ..app import Screen
from .common import url_image
from .keyboard import Keyboard
from .menu import Menu

CARD_W, CARD_H, GAP = 200, 270, 28


def avatar(app, s, prof, center, size):
    cx, cy = center
    img = None
    if prof.get("ra_user"):
        img = url_image(app, f"{MEDIA}/UserPic/{prof['ra_user']}.png", size, circle=True)
    if img:
        s.blit(img, img.get_rect(center=center))
        return
    col = tuple(prof.get("color") or (0, 112, 209))
    gfx.draw.circle(s, col, center, size // 2)
    initial = (prof.get("name") or "?")[:1].upper()
    gfx.blit_text(s, initial, (cx, cy + 2), int(size * 0.5), gfx.TEXT, True, anchor="center")


def after_sign_in(app, pid, new_user=False):
    """Shared tail of every sign-in: activate; new users are offered RetroAchievements linking."""
    app.activate_profile(pid)
    if new_user and not app.config.ra_enabled and app.config["rom_dir"]:
        from .setup import RASetup
        app.push(RASetup(app, first_run=True))


class UserSelect(Screen):
    def __init__(self, app, first_run=False, switching=False):
        super().__init__(app)
        self.first_run = first_run
        self.switching = switching
        self.sel = 0
        pids = list(app.config.profiles)
        if app.config.active_id in pids:
            self.sel = pids.index(app.config.active_id)
        self.cam = 0.0

    def _entries(self):
        out = [("user", pid) for pid in self.app.config.profiles]
        out.append(("add", None))
        from ...accounts import online_server
        if online_server():
            out.append(("online", None))
        return out

    def on_action(self, a):
        ents = self._entries()
        n = len(ents)
        if a == "left":
            self.sel = max(0, self.sel - 1)
        elif a == "right":
            self.sel = min(n - 1, self.sel + 1)
        elif a == "a":
            kind, pid = ents[self.sel]
            if kind == "user":
                self._choose(pid)
            elif kind == "add":
                self._add_user()
            else:
                self.app.push(OnlineSignIn(self.app))
        elif a == "y":
            kind, pid = ents[self.sel]
            if kind == "user":
                self.app.push(ManageUser(self.app, pid))
        elif a == "b":
            if self.switching:
                self.app.pop()
            else:
                self.app.dialog("Quit RetroHome?", "", [("Quit", self.app.quit), ("Cancel", None)])

    def _choose(self, pid):
        prof = self.app.config.profiles[pid]
        if prof.get("pin"):
            def entered(v):
                if check_pin(v, prof["pin"]):
                    after_sign_in(self.app, pid)
                else:
                    self.app.toast("Wrong PIN")
            self.app.push(Keyboard(self.app, f"PIN for {prof.get('name')}", "", entered, secret=True))
        else:
            after_sign_in(self.app, pid)

    def _add_user(self):
        def named(name):
            if not name:
                return
            pid = self.app.config.new_profile(name)

            def no_pin():
                after_sign_in(self.app, pid, new_user=True)

            def with_pin():
                def set_pin(v):
                    if len(v) >= 4:
                        self.app.config.profiles[pid]["pin"] = hash_pin(v)
                        self.app.config.save()
                    else:
                        self.app.toast("PIN not set (needs 4+ characters)")
                    after_sign_in(self.app, pid, new_user=True)
                self.app.push(Keyboard(self.app, "Choose a PIN (4+ characters)", "", set_pin, secret=True))
            self.app.dialog(f"Welcome, {name}!", "Protect this user with a PIN? (You can change this later.)",
                            [("No PIN", no_pin), ("Set a PIN", with_pin)], on_cancel=no_pin)
        self.app.push(Keyboard(self.app, "What should we call you?", "", named))

    def update(self, dt):
        n = len(self._entries())
        total = n * CARD_W + (n - 1) * GAP
        if total <= gfx.W - 120:
            target = -(gfx.W - total) / 2
        else:
            target = self.sel * (CARD_W + GAP) - (gfx.W / 2 - CARD_W / 2)
            target = max(-60, min(total - gfx.W + 60, target))
        self.cam += (target - self.cam) * min(1, dt * 12)

    def draw(self, s):
        title = "Create your user" if self.first_run and not self.app.config.profiles else "Who's playing?"
        gfx.blit_text(s, title, (gfx.W // 2, 120), 42, gfx.TEXT, True, anchor="center")
        if self.app.config.profiles:
            gfx.blit_text(s, "Choose a user, or add someone new.", (gfx.W // 2, 170), 20, gfx.TEXT_DIM, anchor="center")
        y = 250
        for i, (kind, pid) in enumerate(self._entries()):
            x = i * (CARD_W + GAP) - self.cam
            r = pygame.Rect(int(x), y, CARD_W, CARD_H)
            if r.right < 0 or r.x > gfx.W:
                continue
            sel = i == self.sel
            gfx.rrect(s, gfx.PANEL_HI if sel else gfx.PANEL, r, 22)
            if sel:
                gfx.glow_border(s, r, 22, self.app.t)
            c = (r.centerx, r.y + 95)
            if kind == "user":
                prof = self.app.config.profiles[pid]
                avatar(self.app, s, prof, c, 120)
                gfx.blit_text(s, prof.get("name", ""), (r.centerx, r.y + 178), 22, gfx.TEXT, True,
                              max_w=CARD_W - 20, anchor="midtop")
                lv = int((prof.get("ra_snapshot") or {}).get("level") or 0)
                tags = []
                if prof.get("remote", {}).get("token"):
                    tags.append("Online")
                if prof.get("pin"):
                    tags.append("PIN")
                if prof.get("ra_user"):
                    tags.append("RA")
                gfx.blit_text(s, " · ".join(tags), (r.centerx, r.y + 210), 14, gfx.TEXT_DIM, anchor="midtop")
                if lv:
                    gfx.level_badge(s, (r.right - 34, r.y + 34), lv, 40, self.app.t)
            elif kind == "add":
                gfx.draw.circle(s, (90, 100, 130), c, 60, 3)
                gfx.draw.line(s, gfx.TEXT, (c[0] - 24, c[1]), (c[0] + 24, c[1]), 5)
                gfx.draw.line(s, gfx.TEXT, (c[0], c[1] - 24), (c[0], c[1] + 24), 5)
                gfx.blit_text(s, "Add user", (r.centerx, r.y + 178), 22, gfx.TEXT, True, anchor="midtop")
                gfx.blit_text(s, "Play offline", (r.centerx, r.y + 210), 14, gfx.TEXT_DIM, anchor="midtop")
            else:
                gfx.draw.circle(s, gfx.ACCENT, c, 60)
                gfx.draw.circle(s, gfx.TEXT, c, 34, 2)
                gfx.draw.ellipse(s, gfx.TEXT, (c[0] - 15, c[1] - 34, 30, 68), 2)
                gfx.draw.line(s, gfx.TEXT, (c[0] - 34, c[1]), (c[0] + 34, c[1]), 2)
                gfx.blit_text(s, "Sign in with email", (r.centerx, r.y + 178), 22, gfx.TEXT, True, anchor="midtop")
                gfx.blit_text(s, "RetroHome account", (r.centerx, r.y + 210), 14, gfx.TEXT_DIM, anchor="midtop")
        bob = 4 * math.sin(self.app.t * 2)
        gfx.blit_text(s, "RetroHome", (gfx.W // 2, gfx.H - 90 + bob), 16, gfx.TEXT_FAINT, True, anchor="center")

    def hints(self):
        h = [("a", "Select")]
        ents = self._entries()
        if ents and ents[min(self.sel, len(ents) - 1)][0] == "user":
            h.append(("y", "Manage"))
        h.append(("b", "Back" if self.switching else "Quit"))
        return h


class ManageUser(Menu):
    def __init__(self, app, pid):
        self.pid = pid
        super().__init__(app, "", on_back=lambda: app.pop())
        self._build()

    @property
    def prof(self):
        return self.app.config.profiles.get(self.pid, {})

    def _build(self):
        p = self.prof
        self.title = p.get("name", "User")
        remote = p.get("remote") or {}
        items = [
            ("Rename", p.get("name", ""), self._rename),
            ("Remove PIN" if p.get("pin") else "Set a PIN", "Ask for a PIN when choosing this user", self._pin),
        ]
        if remote.get("token"):
            items.append(("Sign out of your RetroHome account", remote.get("email") or remote.get("username") or "",
                          self._sign_out))
        items.append(("Delete this user", "Removes their favourites, history and linked accounts here",
                      self._delete))
        self.set_items(items)

    def _rename(self):
        def done(v):
            if v:
                self.prof["name"] = v[:24]
                self.app.config.save()
                self._build()
                remote = self.prof.get("remote") or {}
                if remote.get("token") and online_server():     # friends see the new name too
                    client = OnlineClient(online_server(), remote["token"])
                    self.app.tasks.submit(lambda: client.set_name(v[:24]), error=lambda e: None)
        self.app.push(Keyboard(self.app, "Name", self.prof.get("name", ""), done))

    def _pin(self):
        if self.prof.get("pin"):
            self.prof["pin"] = ""
            self.app.config.save()
            self.app.toast("PIN removed")
            self._build()
            return

        def done(v):
            if len(v) < 4:
                self.app.toast("PINs need at least 4 characters")
                return
            self.prof["pin"] = hash_pin(v)
            self.app.config.save()
            self.app.toast("PIN set")
            self._build()
        self.app.push(Keyboard(self.app, "New PIN (4+ characters)", "", done, secret=True))

    def _sign_out(self):
        remote = self.prof.get("remote") or {}

        def work():
            try:
                OnlineClient(online_server() or remote["server"], remote["token"]).logout()
            except (AccountError, KeyError):
                pass
        self.app.tasks.submit(work)
        self.prof["remote"] = {}
        self.app.config.save()
        if self.app.config.active_id == self.pid:
            self.app.online = None
        self.app.toast("Signed out of RetroHome Online")
        self._build()

    def _delete(self):
        def really():
            active = self.app.config.active_id == self.pid
            self.app.config.delete_profile(self.pid)
            self.app.pop()
            if active:
                self.app.online = None
                self.app.ra.reconfigure()
                self.app.stack = [UserSelect(self.app, first_run=not self.app.config.profiles)]
        self.app.dialog(f"Delete {self.prof.get('name')}?", "This can't be undone.",
                        [("Delete", really), ("Cancel", None)])


class OnlineSignIn(Menu):
    """RetroHome account: just an email and a password. The server is built in (accounts.online_server)."""

    def __init__(self, app, prompt=False, attach=None):
        self.prompt = prompt          # shown by itself after choosing a user: offers "Not now"
        self.attach = attach          # local profile to link the account to (None: find or create one)
        self.email = ""
        self.password = ""
        self.status = ""
        self.busy = False
        super().__init__(
            app, "RetroHome account",
            "Create a free account with your email and a password to keep your level, awards, favourites "
            "and play time safe, and in sync on all your devices." +
            (" You can also do this later in Settings." if prompt else ""),
            on_back=self._later if prompt else (lambda: app.pop()))
        self._build()

    def _build(self):
        items = [
            ("Email", self.email or "Not set", lambda: self._edit("Your email address", "email")),
            ("Password", "•" * len(self.password) if self.password else "Not set - 8 or more characters",
             lambda: self._edit("Password (8 or more characters)", "password", True)),
            ("Create account", self.status or "New to RetroHome", lambda: self._go(True)),
            ("Sign in", "I already have an account", lambda: self._go(False)),
        ]
        items.append(("Not now", "", self._later) if self.prompt else ("Back", "", self.app.pop))
        self.set_items(items)

    def _later(self):
        if self.prompt and self.attach in self.app.config.profiles:
            self.app.config.profiles[self.attach]["online_prompted"] = True
            self.app.config.save()
        self.app.pop()

    def _edit(self, title, field, secret=False):
        def done(v):
            setattr(self, field, v.strip() if field == "email" else v)
            self.status = ""
            self._build()
        self.app.push(Keyboard(self.app, title, getattr(self, field), done, secret=secret))

    def _go(self, create):
        from ...accounts import EMAIL_RE, online_server
        if self.busy:
            return
        server = online_server()
        self.status = ""
        if not server:
            self.status = "RetroHome Online isn't available in this version"
        elif not EMAIL_RE.match(self.email):
            self.status = "Enter your email address first"
        elif len(self.password) < 8:
            self.status = "Passwords need at least 8 characters"
        if self.status:
            self._build()
            return
        self.busy = True
        self.status = "Creating your account…" if create else "Signing in…"
        self._build()
        client = OnlineClient(server)
        email, pw = self.email.lower(), self.password
        cfg = self.app.config
        name = (cfg.profiles.get(self.attach) or {}).get("name") or email.split("@")[0]

        def work():
            return client.register(email, pw, name) if create else client.login(email, pw)

        def ok(res):
            self.busy = False
            self.password = ""
            u = res.get("user") or {}
            pid = next((k for k, p in cfg.profiles.items()
                        if str((p.get("remote") or {}).get("email", "")).lower() == email), None)
            if pid is None and self.attach in cfg.profiles and not (cfg.profiles[self.attach].get("remote") or {}).get("token"):
                pid = self.attach
            is_new = pid is None
            if is_new:
                pid = cfg.new_profile(u.get("display_name") or name)
            cfg.profiles[pid]["remote"] = {"server": server, "email": email, "username": u.get("display_name") or name,
                                           "user_id": u.get("id"), "token": client.token}
            cfg.profiles[pid]["online_prompted"] = True
            cfg.save()
            self.app.toast("Account created - you're all set" if create else f"Signed in as {email}")
            after_sign_in(self.app, pid, new_user=is_new)

        def bad(e):
            self.busy = False
            self.status = str(e)
            self._build()
        self.app.tasks.submit(work, callback=ok, error=bad)
