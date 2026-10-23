# RetroHome Online API (v1)

JSON over HTTPS. Authenticated calls send `Authorization: Bearer <token>`.
Errors return `{"error": "message"}` with a 4xx/5xx status.

| Method | Path | Auth | Body → Response |
|---|---|---|---|
| GET | `/api/v1/health` | – | → `{"ok": true, "name", "version"}` |
| POST | `/api/v1/auth/register` | – | `{"email", "password", "display_name"}` → 201 `{"token", "user"}` (409 email taken) |
| POST | `/api/v1/auth/login` | – | `{"email", "password"}` → `{"token", "user"}` (401 wrong details, 429 throttled) |
| POST | `/api/v1/auth/logout` | ✓ | `{}` → `{"ok": true}` (revokes the token) |
| GET | `/api/v1/me` | ✓ | → `{"user": {...,"stats": {...}}}` |
| PUT | `/api/v1/me/name` | ✓ | `{"display_name"}` → `{"ok": true}` |
| PUT | `/api/v1/me/stats` | ✓ | `{"level", "xp", "mythic", "platinum", "beaten", "ra_user"}` → `{"ok": true}` |
| GET | `/api/v1/me/library` | ✓ | → `{"favourites": [...], "history": {...}, "fav_events": {...}, "updated"}` |
| PUT | `/api/v1/me/library` | ✓ | `{"favourites", "history", "fav_events"}` → `{"ok": true}` |
| GET / PUT / DELETE | `/api/v1/me/data/<game>` | ✓ | `{"data": {...}}` (≤ 1 MB) → GET `{"app", "data", "updated"}` · Cloudflare server only |
| GET | `/api/v1/leaderboard?limit=50` | – | → `{"entries": [{"username", "display_name", "level", "xp", "mythic", "platinum"}]}` |

`user` objects: `{"id", "username", "display_name", "email", "created", "stats"?}`. Accounts are an
email + password; `username` is the display name (kept for older clients), and `email` is only ever
returned to its owner - the leaderboard shows names only.

`history` maps a game id (`"<system folder>/<path inside it>"`, e.g. `"psp/Metal Gear Solid.iso"`)
to `{"last": unix_time, "count": n, "playtime": seconds}`. `fav_events` maps a game id to
`[unix_time, is_favourite]` so removing a favourite on one device syncs to the others (newest wins). The app merges local and server
copies (union of favourites, newest/largest history values) before uploading.

Rules both servers enforce: a valid email (case-insensitive); passwords ≥ 8
characters, stored as PBKDF2-SHA256 (300k iterations); session tokens are random, stored
hashed, and expire after 90 days; repeated failed logins are throttled per username.

The RetroAchievements Web API key never leaves the device. Stats are self-reported by the
app; a production server that wants trusted leaderboards should recompute them server-side
from RetroAchievements using the linked `ra_user`.

Two implementations: `retrohome_server.py` (run it on any machine) and `cloudflare/` (free hosting on
Cloudflare Workers + D1; see `cloudflare/README.md`).
