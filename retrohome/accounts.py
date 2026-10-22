"""User accounts: local profiles (optional PIN) and RetroHome Online sign-in.

The online side talks to a RetroHome server over a small JSON API (see server/API.md;
a runnable reference server is in server/retrohome_server.py). Passwords are only ever
sent to the server over HTTPS (plain HTTP is allowed for localhost / your own LAN while
testing) and are never stored on this device - only the session token is.
"""
import hashlib
import hmac
import ipaddress
import json
import secrets
import urllib.error
import urllib.parse
import urllib.request

from . import __version__
from .net import _ctx

API = "/api/v1"


# ---------------------------------------------------------------- local PINs
def hash_pin(pin: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", pin.encode(), salt, 200_000)
    return f"pbkdf2${salt.hex()}${dk.hex()}"


def check_pin(pin: str, stored: str) -> bool:
    try:
        _, salt, dk = stored.split("$")
    except ValueError:
        return False
    got = hashlib.pbkdf2_hmac("sha256", pin.encode(), bytes.fromhex(salt), 200_000)
    return hmac.compare_digest(got.hex(), dk)


# ---------------------------------------------------------------- online
class AccountError(Exception):
    pass


def _is_local_host(host: str) -> bool:
    if host in ("localhost",) or host.endswith(".local") or host.endswith(".lan"):
        return True
    try:
        ip = ipaddress.ip_address(host)
        return ip.is_private or ip.is_loopback
    except ValueError:
        return False


def normalise_server(url: str) -> str:
    url = url.strip().rstrip("/")
    if not url:
        raise AccountError("Enter a server address first.")
    if "://" not in url:
        host = url.split("/")[0].split(":")[0]
        url = ("http://" if _is_local_host(host) else "https://") + url
    p = urllib.parse.urlparse(url)
    if p.scheme not in ("http", "https") or not p.hostname:
        raise AccountError("That doesn't look like a server address.")
    if p.scheme == "http" and not _is_local_host(p.hostname):
        raise AccountError("Online servers must use https:// so your password stays private.")
    return url


class OnlineClient:
    def __init__(self, server_url: str, token: str = ""):
        self.server = normalise_server(server_url)
        self.token = token

    def _req(self, method, path, body=None, timeout=15):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.server + API + path, data=data, method=method)
        req.add_header("User-Agent", f"RetroHome/{__version__}")
        req.add_header("Accept", "application/json")
        if data is not None:
            req.add_header("Content-Type", "application/json")
        if self.token:
            req.add_header("Authorization", f"Bearer {self.token}")
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=_ctx) as r:
                raw = r.read()
        except urllib.error.HTTPError as e:
            try:
                msg = json.loads(e.read().decode()).get("error")
            except (ValueError, AttributeError, OSError):
                msg = None
            if e.code == 401:
                raise AccountError(msg or "Signed out - please sign in again.") from None
            raise AccountError(msg or f"Server error ({e.code}).") from None
        except OSError as e:
            raise AccountError(f"Can't reach the server ({getattr(e, 'reason', e)}).") from None
        try:
            return json.loads(raw.decode()) if raw else {}
        except ValueError:
            raise AccountError("The server sent something unexpected.") from None

    def health(self):
        return self._req("GET", "/health")

    def register(self, username, password, display_name=""):
        res = self._req("POST", "/auth/register", {"username": username, "password": password,
                                                   "display_name": display_name or username})
        self.token = res.get("token", "")
        return res

    def login(self, username, password):
        res = self._req("POST", "/auth/login", {"username": username, "password": password})
        self.token = res.get("token", "")
        return res

    def logout(self):
        try:
            self._req("POST", "/auth/logout", {})
        finally:
            self.token = ""

    def me(self):
        return self._req("GET", "/me")

    def push_stats(self, stats: dict):
        return self._req("PUT", "/me/stats", stats)

    def get_library(self):
        return self._req("GET", "/me/library")

    def put_library(self, data: dict):
        return self._req("PUT", "/me/library", data)

    def leaderboard(self, limit=50):
        return self._req("GET", f"/leaderboard?limit={int(limit)}")


def merge_library(local: dict, remote: dict) -> dict:
    """Merge two copies of a user's library data.

    favourites: union, then the newest add/remove event per game wins (so removals sync too)
    history:    newest 'last played', largest count / playtime
    """
    events = {}
    for src in (remote.get("fav_events") or {}, local.get("fav_events") or {}):
        for gid, ev in src.items():
            if gid not in events or ev[0] > events[gid][0]:
                events[gid] = list(ev)
    favs = list(dict.fromkeys((local.get("favourites") or []) + (remote.get("favourites") or [])))
    for gid, (_, on) in events.items():
        if on and gid not in favs:
            favs.append(gid)
        elif not on and gid in favs:
            favs.remove(gid)
    hist = {}
    for src in (remote.get("history") or {}, local.get("history") or {}):
        for gid, e in src.items():
            cur = hist.get(gid)
            if not cur:
                hist[gid] = dict(e)
            else:
                cur["last"] = max(cur.get("last", 0), e.get("last", 0))
                cur["count"] = max(cur.get("count", 0), e.get("count", 0))
                cur["playtime"] = max(cur.get("playtime", 0), e.get("playtime", 0))
    return {"favourites": favs, "history": hist, "fav_events": events}
