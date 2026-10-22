# RetroHome Online API (v1)

JSON over HTTPS. Authenticated calls send `Authorization: Bearer <token>`.
Errors return `{"error": "message"}` with a 4xx/5xx status.

| Method | Path | Auth | Body → Response |
|---|---|---|---|
| GET | `/api/v1/health` | – | → `{"ok": true, "name", "version"}` |
| POST | `/api/v1/auth/register` | – | `{"username", "password", "display_name"}` → 201 `{"token", "user"}` |
| POST | `/api/v1/auth/login` | – | `{"username", "password"}` → `{"token", "user"}` (401 wrong details, 429 throttled) |
| POST | `/api/v1/auth/logout` | ✓ | `{}` → `{"ok": true}` (revokes the token) |
| GET | `/api/v1/me` | ✓ | → `{"user": {...,"stats": {...}}}` |
| PUT | `/api/v1/me/stats` | ✓ | `{"level", "xp", "mythic", "platinum", "beaten", "ra_user"}` → `{"ok": true}` |
| GET | `/api/v1/me/library` | ✓ | → `{"favourites": [...], "history": {...}, "fav_events": {...}, "updated"}` |
| PUT | `/api/v1/me/library` | ✓ | `{"favourites", "history", "fav_events"}` → `{"ok": true}` |
| GET | `/api/v1/leaderboard?limit=50` | – | → `{"entries": [{"username", "display_name", "level", "xp", "mythic", "platinum"}]}` |

`user` objects: `{"id", "username", "display_name", "created", "stats"?}`.

`history` maps a game id (`"<system folder>/<path inside it>"`, e.g. `"psp/Metal Gear Solid.iso"`)
to `{"last": unix_time, "count": n, "playtime": seconds}`. `fav_events` maps a game id to
`[unix_time, is_favourite]` so removing a favourite on one device syncs to the others (newest wins). The app merges local and server
copies (union of favourites, newest/largest history values) before uploading.

Rules the reference server enforces: usernames 3–24 of `A-Z a-z 0-9 _ . -`; passwords ≥ 8
characters, stored as PBKDF2-SHA256 (300k iterations); session tokens are random, stored
hashed, and expire after 90 days; repeated failed logins are throttled per username.

The RetroAchievements Web API key never leaves the device. Stats are self-reported by the
app; a production server that wants trusted leaderboards should recompute them server-side
from RetroAchievements using the linked `ra_user`.
