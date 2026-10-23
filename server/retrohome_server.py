#!/usr/bin/env python3
"""RetroHome Online - reference server.

A small, dependency-free implementation of the API in API.md, backed by SQLite.
Good for testing and for small groups. For a public deployment put it behind an
HTTPS reverse proxy (Caddy / nginx) - the RetroHome app refuses plain HTTP to
anything that isn't localhost or a private LAN address.

    python3 retrohome_server.py --port 8787 --db retrohome.db
"""
import argparse
import hashlib
import hmac
import json
import re
import secrets
import sqlite3
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

API = "/api/v1"
TOKEN_DAYS = 90
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
MAX_BODY = 4 * 1024 * 1024

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT UNIQUE NOT NULL COLLATE NOCASE,
    display_name TEXT NOT NULL,
    pw_hash TEXT NOT NULL,
    created REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created REAL NOT NULL,
    expires REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS stats (
    user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    level INTEGER DEFAULT 1, xp INTEGER DEFAULT 0, mythic INTEGER DEFAULT 0,
    platinum INTEGER DEFAULT 0, beaten INTEGER DEFAULT 0, ra_user TEXT DEFAULT '',
    updated REAL
);
CREATE TABLE IF NOT EXISTS library (
    user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    data TEXT NOT NULL, updated REAL
);
"""


def pw_hash(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 300_000)
    return f"pbkdf2_sha256$300000${salt.hex()}${dk.hex()}"


def pw_check(password: str, stored: str) -> bool:
    try:
        _, iters, salt, dk = stored.split("$")
        got = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(iters))
        return hmac.compare_digest(got.hex(), dk)
    except (ValueError, TypeError):
        return False


class Store:
    def __init__(self, path):
        self.path = path
        self.local = threading.local()
        with self.db() as c:
            c.executescript(SCHEMA)
        self.fail = {}            # email -> (count, last_ts) for login throttling
        self.fail_lock = threading.Lock()

    def db(self):
        c = getattr(self.local, "c", None)
        if c is None:
            c = sqlite3.connect(self.path)
            c.row_factory = sqlite3.Row
            c.execute("PRAGMA foreign_keys = ON")
            self.local.c = c
        return c

    def new_session(self, user_id):
        token = secrets.token_urlsafe(32)
        now = time.time()
        with self.db() as c:
            c.execute("INSERT INTO sessions VALUES (?,?,?,?)",
                      (hashlib.sha256(token.encode()).hexdigest(), user_id, now, now + TOKEN_DAYS * 86400))
            c.execute("DELETE FROM sessions WHERE expires < ?", (now,))
        return token

    def user_for_token(self, token):
        if not token:
            return None
        row = self.db().execute(
            "SELECT u.* FROM sessions s JOIN users u ON u.id = s.user_id WHERE s.token_hash=? AND s.expires>?",
            (hashlib.sha256(token.encode()).hexdigest(), time.time())).fetchone()
        return row


def user_json(u, stats=None):
    """"username" is the display name; the email is only ever sent to its owner."""
    out = {"id": u["id"], "username": u["display_name"], "display_name": u["display_name"],
           "email": u["email"], "created": u["created"]}
    if stats:
        out["stats"] = {k: stats[k] for k in ("level", "xp", "mythic", "platinum", "beaten", "ra_user")}
    return out


class Handler(BaseHTTPRequestHandler):
    store: Store = None
    server_version = "RetroHomeServer/1.0"

    def log_message(self, fmt, *args):
        print("%s %s" % (self.address_string(), fmt % args))

    # -------------------------------------------------------- helpers
    def send(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def err(self, code, msg):
        self.send(code, {"error": msg})

    def body(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n > MAX_BODY:
            raise ValueError("Request too large.")
        raw = self.rfile.read(n) if n else b"{}"
        data = json.loads(raw.decode() or "{}")
        if not isinstance(data, dict):
            raise ValueError("Expected a JSON object.")
        return data

    def auth(self):
        h = self.headers.get("Authorization", "")
        token = h[7:] if h.startswith("Bearer ") else ""
        u = self.store.user_for_token(token)
        if not u:
            self.err(401, "Not signed in.")
        return u, token

    # -------------------------------------------------------- routing
    def do_GET(self):
        self.route("GET")

    def do_POST(self):
        self.route("POST")

    def do_PUT(self):
        self.route("PUT")

    def route(self, method):
        url = urlparse(self.path)
        path = url.path.rstrip("/")
        if not path.startswith(API):
            return self.err(404, "Not found.")
        path = path[len(API):]
        try:
            fn = {
                ("GET", "/health"): self.health,
                ("POST", "/auth/register"): self.register,
                ("POST", "/auth/login"): self.login,
                ("POST", "/auth/logout"): self.logout,
                ("GET", "/me"): self.me,
                ("PUT", "/me/stats"): self.put_stats,
                ("PUT", "/me/name"): self.put_name,
                ("GET", "/me/library"): self.get_library,
                ("PUT", "/me/library"): self.put_library,
                ("GET", "/leaderboard"): lambda: self.leaderboard(parse_qs(url.query)),
            }.get((method, path))
            if not fn:
                return self.err(404, "Not found.")
            fn()
        except ValueError as e:
            self.err(400, str(e) or "Bad request.")
        except Exception as e:  # noqa: BLE001
            print("ERROR", repr(e))
            self.err(500, "Server error.")

    # -------------------------------------------------------- endpoints
    def health(self):
        self.send(200, {"ok": True, "name": "RetroHome Online", "version": 1})

    def register(self):
        d = self.body()
        email = str(d.get("email") or d.get("username") or "").strip().lower()
        password = str(d.get("password", ""))
        display = str(d.get("display_name") or "").strip()[:24] or email.split("@")[0][:24]
        if len(email) > 254 or not EMAIL_RE.match(email):
            return self.err(400, "Enter a valid email address.")
        if len(password) < 8:
            return self.err(400, "Passwords need at least 8 characters.")
        try:
            with self.store.db() as c:
                cur = c.execute("INSERT INTO users (email, display_name, pw_hash, created) VALUES (?,?,?,?)",
                                (email, display, pw_hash(password), time.time()))
                uid = cur.lastrowid
                c.execute("INSERT INTO stats (user_id, updated) VALUES (?,?)", (uid, time.time()))
        except sqlite3.IntegrityError:
            return self.err(409, "There's already an account with that email - sign in instead.")
        u = self.store.db().execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
        self.send(201, {"token": self.store.new_session(uid), "user": user_json(u)})

    def login(self):
        d = self.body()
        email = str(d.get("email") or d.get("username") or "").strip().lower()
        password = str(d.get("password", ""))
        key = email
        with self.store.fail_lock:
            n, last = self.store.fail.get(key, (0, 0))
        if n >= 5 and time.time() - last < 60 * min(30, 2 ** (n - 5)):
            return self.err(429, "Too many attempts - wait a bit and try again.")
        u = self.store.db().execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        if not u or not pw_check(password, u["pw_hash"]):
            with self.store.fail_lock:
                self.store.fail[key] = (n + 1, time.time())
            return self.err(401, "Wrong email or password.")
        with self.store.fail_lock:
            self.store.fail.pop(key, None)
        st = self.store.db().execute("SELECT * FROM stats WHERE user_id=?", (u["id"],)).fetchone()
        self.send(200, {"token": self.store.new_session(u["id"]), "user": user_json(u, st)})

    def logout(self):
        u, token = self.auth()
        if not u:
            return
        with self.store.db() as c:
            c.execute("DELETE FROM sessions WHERE token_hash=?", (hashlib.sha256(token.encode()).hexdigest(),))
        self.send(200, {"ok": True})

    def me(self):
        u, _ = self.auth()
        if not u:
            return
        st = self.store.db().execute("SELECT * FROM stats WHERE user_id=?", (u["id"],)).fetchone()
        self.send(200, {"user": user_json(u, st)})

    def put_name(self):
        u, _ = self.auth()
        if not u:
            return
        name = str(self.body().get("display_name") or "").strip()[:24]
        if not name:
            return self.err(400, "Enter a name.")
        with self.store.db() as c:
            c.execute("UPDATE users SET display_name=? WHERE id=?", (name, u["id"]))
        self.send(200, {"ok": True})

    def put_stats(self):
        u, _ = self.auth()
        if not u:
            return
        d = self.body()

        def num(k):
            v = int(d.get(k) or 0)
            if v < 0 or v > 10 ** 12:
                raise ValueError(f"Bad value for {k}.")
            return v
        with self.store.db() as c:
            c.execute("UPDATE stats SET level=?, xp=?, mythic=?, platinum=?, beaten=?, ra_user=?, updated=? "
                      "WHERE user_id=?", (num("level") or 1, num("xp"), num("mythic"), num("platinum"),
                                          num("beaten"), str(d.get("ra_user", ""))[:40], time.time(), u["id"]))
        self.send(200, {"ok": True})

    def get_library(self):
        u, _ = self.auth()
        if not u:
            return
        row = self.store.db().execute("SELECT data, updated FROM library WHERE user_id=?", (u["id"],)).fetchone()
        data = json.loads(row["data"]) if row else {"favourites": [], "history": {}, "fav_events": {}}
        data["updated"] = row["updated"] if row else 0
        self.send(200, data)

    def put_library(self):
        u, _ = self.auth()
        if not u:
            return
        d = self.body()
        data = {"favourites": list(d.get("favourites") or [])[:10000],
                "history": dict(d.get("history") or {}),
                "fav_events": dict(d.get("fav_events") or {})}
        with self.store.db() as c:
            c.execute("INSERT INTO library (user_id, data, updated) VALUES (?,?,?) "
                      "ON CONFLICT(user_id) DO UPDATE SET data=excluded.data, updated=excluded.updated",
                      (u["id"], json.dumps(data), time.time()))
        self.send(200, {"ok": True})

    def leaderboard(self, q):
        limit = max(1, min(200, int((q.get("limit") or ["50"])[0])))
        rows = self.store.db().execute(
            "SELECT u.display_name AS username, u.display_name, s.level, s.xp, s.mythic, s.platinum FROM stats s "
            "JOIN users u ON u.id = s.user_id ORDER BY s.xp DESC LIMIT ?", (limit,)).fetchall()
        self.send(200, {"entries": [dict(r) for r in rows]})


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8787)
    ap.add_argument("--db", default="retrohome.db")
    a = ap.parse_args()
    Handler.store = Store(a.db)
    srv = ThreadingHTTPServer((a.host, a.port), Handler)
    print(f"RetroHome Online listening on http://{a.host}:{a.port}{API}  (db: {a.db})")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
