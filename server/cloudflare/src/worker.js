// RetroHome Online on Cloudflare Workers + D1.
// Same API as server/retrohome_server.py (see server/API.md), plus /api/v1/me/data/<app> for other games.

const API = "/api/v1";
const TOKEN_DAYS = 90;
const USERNAME_RE = /^[A-Za-z0-9_.-]{3,24}$/;
const APP_RE = /^[A-Za-z0-9_.-]{1,40}$/;
const MAX_BODY = 4 * 1024 * 1024;          // library uploads
const MAX_APP_DATA = 1024 * 1024;          // 1 MB per game per player
// Password hashing has to fit the free plan's small CPU allowance per request, so it uses fewer
// PBKDF2 rounds than the Python server. Logins are throttled per username on top of that.
const PBKDF2_ITERS = 10000;

const enc = new TextEncoder();
const now = () => Date.now() / 1000;

class HttpError extends Error {
  constructor(status, message) { super(message); this.status = status; }
}

function json(status, obj) {
  return new Response(JSON.stringify(obj), {
    status,
    headers: { "Content-Type": "application/json", "Cache-Control": "no-store" },
  });
}

const hex = (buf) => [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, "0")).join("");
const unhex = (s) => new Uint8Array(s.match(/../g).map((h) => parseInt(h, 16)));

async function sha256hex(text) {
  return hex(await crypto.subtle.digest("SHA-256", enc.encode(text)));
}

async function pbkdf2(password, salt, iters) {
  const key = await crypto.subtle.importKey("raw", enc.encode(password), "PBKDF2", false, ["deriveBits"]);
  return hex(await crypto.subtle.deriveBits({ name: "PBKDF2", hash: "SHA-256", salt, iterations: iters }, key, 256));
}

async function pwHash(password) {
  const salt = crypto.getRandomValues(new Uint8Array(16));
  return `pbkdf2_sha256$${PBKDF2_ITERS}$${hex(salt)}$${await pbkdf2(password, salt, PBKDF2_ITERS)}`;
}

async function pwCheck(password, stored) {
  try {
    const [, iters, salt, dk] = stored.split("$");
    const n = parseInt(iters, 10);
    if (!n || n > 100000) return false;                       // Workers caps PBKDF2 at 100k rounds
    const got = await pbkdf2(password, unhex(salt), n);
    if (got.length !== dk.length) return false;
    let diff = 0;
    for (let i = 0; i < got.length; i++) diff |= got.charCodeAt(i) ^ dk.charCodeAt(i);
    return diff === 0;
  } catch {
    return false;
  }
}

function newToken() {
  const b = crypto.getRandomValues(new Uint8Array(32));
  return btoa(String.fromCharCode(...b)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

async function body(request, limit = MAX_BODY) {
  const text = await request.text();
  if (text.length > limit) throw new HttpError(413, "Request too large.");
  let data;
  try { data = text ? JSON.parse(text) : {}; } catch { throw new HttpError(400, "Expected JSON."); }
  if (!data || typeof data !== "object" || Array.isArray(data)) throw new HttpError(400, "Expected a JSON object.");
  return data;
}

function userJson(u, st) {
  const out = { id: u.id, username: u.username, display_name: u.display_name, created: u.created };
  if (st) {
    out.stats = { level: st.level, xp: st.xp, mythic: st.mythic, platinum: st.platinum, beaten: st.beaten,
                  ra_user: st.ra_user };
  }
  return out;
}

async function newSession(db, userId) {
  const token = newToken();
  const t = now();
  await db.batch([
    db.prepare("INSERT INTO sessions VALUES (?,?,?,?)").bind(await sha256hex(token), userId, t, t + TOKEN_DAYS * 86400),
    db.prepare("DELETE FROM sessions WHERE expires < ?").bind(t),
  ]);
  return token;
}

async function auth(request, db) {
  const h = request.headers.get("Authorization") || "";
  const token = h.startsWith("Bearer ") ? h.slice(7) : "";
  if (!token) throw new HttpError(401, "Not signed in.");
  const u = await db.prepare(
    "SELECT u.* FROM sessions s JOIN users u ON u.id = s.user_id WHERE s.token_hash=? AND s.expires>?"
  ).bind(await sha256hex(token), now()).first();
  if (!u) throw new HttpError(401, "Not signed in.");
  return { u, token };
}

function num(d, k) {
  const v = Math.trunc(Number(d[k] || 0));
  if (!Number.isFinite(v) || v < 0 || v > 1e12) throw new HttpError(400, `Bad value for ${k}.`);
  return v;
}

// ------------------------------------------------------------------ endpoints
const routes = {
  "GET /health": async () => json(200, { ok: true, name: "RetroHome Online", version: 1, host: "cloudflare" }),

  "POST /auth/register": async (req, db) => {
    const d = await body(req);
    const username = String(d.username || "").trim();
    const password = String(d.password || "");
    const display = (String(d.display_name || username).trim().slice(0, 24)) || username;
    if (!USERNAME_RE.test(username)) throw new HttpError(400, "Usernames are 3-24 letters, numbers, _ . or -");
    if (password.length < 8) throw new HttpError(400, "Passwords need at least 8 characters.");
    const exists = await db.prepare("SELECT id FROM users WHERE username=?").bind(username).first();
    if (exists) throw new HttpError(409, "That username is taken.");
    const t = now();
    const res = await db.prepare("INSERT INTO users (username, display_name, pw_hash, created) VALUES (?,?,?,?)")
      .bind(username, display, await pwHash(password), t).run();
    const uid = res.meta.last_row_id;
    await db.prepare("INSERT INTO stats (user_id, updated) VALUES (?,?)").bind(uid, t).run();
    const u = await db.prepare("SELECT * FROM users WHERE id=?").bind(uid).first();
    return json(201, { token: await newSession(db, uid), user: userJson(u) });
  },

  "POST /auth/login": async (req, db) => {
    const d = await body(req);
    const username = String(d.username || "").trim();
    const password = String(d.password || "");
    const f = await db.prepare("SELECT count, last FROM login_fails WHERE username=?").bind(username).first();
    const n = f ? f.count : 0;
    if (n >= 5 && now() - f.last < 60 * Math.min(30, 2 ** (n - 5))) {
      throw new HttpError(429, "Too many attempts - wait a bit and try again.");
    }
    const u = await db.prepare("SELECT * FROM users WHERE username=?").bind(username).first();
    if (!u || !(await pwCheck(password, u.pw_hash))) {
      await db.prepare("INSERT INTO login_fails (username, count, last) VALUES (?,1,?) " +
                       "ON CONFLICT(username) DO UPDATE SET count = count + 1, last = excluded.last")
        .bind(username.toLowerCase(), now()).run();
      throw new HttpError(401, "Wrong username or password.");
    }
    await db.prepare("DELETE FROM login_fails WHERE username=?").bind(username).run();
    const st = await db.prepare("SELECT * FROM stats WHERE user_id=?").bind(u.id).first();
    return json(200, { token: await newSession(db, u.id), user: userJson(u, st) });
  },

  "POST /auth/logout": async (req, db) => {
    const { token } = await auth(req, db);
    await db.prepare("DELETE FROM sessions WHERE token_hash=?").bind(await sha256hex(token)).run();
    return json(200, { ok: true });
  },

  "GET /me": async (req, db) => {
    const { u } = await auth(req, db);
    const st = await db.prepare("SELECT * FROM stats WHERE user_id=?").bind(u.id).first();
    return json(200, { user: userJson(u, st) });
  },

  "PUT /me/stats": async (req, db) => {
    const { u } = await auth(req, db);
    const d = await body(req);
    await db.prepare("UPDATE stats SET level=?, xp=?, mythic=?, platinum=?, beaten=?, ra_user=?, updated=? WHERE user_id=?")
      .bind(num(d, "level") || 1, num(d, "xp"), num(d, "mythic"), num(d, "platinum"), num(d, "beaten"),
            String(d.ra_user || "").slice(0, 40), now(), u.id).run();
    return json(200, { ok: true });
  },

  "GET /me/library": async (req, db) => {
    const { u } = await auth(req, db);
    const row = await db.prepare("SELECT data, updated FROM library WHERE user_id=?").bind(u.id).first();
    const data = row ? JSON.parse(row.data) : { favourites: [], history: {}, fav_events: {} };
    data.updated = row ? row.updated : 0;
    return json(200, data);
  },

  "PUT /me/library": async (req, db) => {
    const { u } = await auth(req, db);
    const d = await body(req);
    const obj = (v) => (v && typeof v === "object" && !Array.isArray(v) ? v : {});
    const data = { favourites: (Array.isArray(d.favourites) ? d.favourites : []).slice(0, 10000),
                   history: obj(d.history), fav_events: obj(d.fav_events) };
    await db.prepare("INSERT INTO library (user_id, data, updated) VALUES (?,?,?) " +
                     "ON CONFLICT(user_id) DO UPDATE SET data=excluded.data, updated=excluded.updated")
      .bind(u.id, JSON.stringify(data), now()).run();
    return json(200, { ok: true });
  },

  "GET /leaderboard": async (req, db, url) => {
    const limit = Math.max(1, Math.min(200, parseInt(url.searchParams.get("limit") || "50", 10) || 50));
    const { results } = await db.prepare(
      "SELECT u.username, u.display_name, s.level, s.xp, s.mythic, s.platinum FROM stats s " +
      "JOIN users u ON u.id = s.user_id ORDER BY s.xp DESC LIMIT ?").bind(limit).all();
    return json(200, { entries: results });
  },
};

// Other games: GET / PUT / DELETE /api/v1/me/data/<app> stores one JSON object per player per game.
async function appData(req, db, app) {
  if (!APP_RE.test(app)) throw new HttpError(400, "App names are 1-40 letters, numbers, _ . or -");
  const { u } = await auth(req, db);
  if (req.method === "GET") {
    const row = await db.prepare("SELECT data, updated FROM app_data WHERE user_id=? AND app=?").bind(u.id, app).first();
    return json(200, { app, data: row ? JSON.parse(row.data) : {}, updated: row ? row.updated : 0 });
  }
  if (req.method === "PUT") {
    const d = await body(req, MAX_APP_DATA);
    await db.prepare("INSERT INTO app_data (user_id, app, data, updated) VALUES (?,?,?,?) " +
                     "ON CONFLICT(user_id, app) DO UPDATE SET data=excluded.data, updated=excluded.updated")
      .bind(u.id, app, JSON.stringify(d.data ?? d), now()).run();
    return json(200, { ok: true });
  }
  if (req.method === "DELETE") {
    await db.prepare("DELETE FROM app_data WHERE user_id=? AND app=?").bind(u.id, app).run();
    return json(200, { ok: true });
  }
  throw new HttpError(405, "Method not allowed.");
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    let path = url.pathname.replace(/\/+$/, "");
    if (!path.startsWith(API)) return json(404, { error: "Not found." });
    path = path.slice(API.length);
    try {
      if (path.startsWith("/me/data/")) return await appData(request, env.DB, decodeURIComponent(path.slice(9)));
      const fn = routes[`${request.method} ${path}`];
      if (!fn) return json(404, { error: "Not found." });
      return await fn(request, env.DB, url);
    } catch (e) {
      if (e instanceof HttpError) return json(e.status, { error: e.message });
      console.error(e && e.stack || e);
      return json(500, { error: "Server error." });
    }
  },
};
