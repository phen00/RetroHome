-- RetroHome Online database (Cloudflare D1). The Worker creates these itself on first use (src/worker.js
-- carries a copy); running this file by hand is optional and safe to repeat.
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
CREATE INDEX IF NOT EXISTS sessions_user ON sessions(user_id);
CREATE TABLE IF NOT EXISTS stats (
    user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    level INTEGER DEFAULT 1, xp INTEGER DEFAULT 0, mythic INTEGER DEFAULT 0,
    platinum INTEGER DEFAULT 0, beaten INTEGER DEFAULT 0, ra_user TEXT DEFAULT '',
    updated REAL
);
CREATE INDEX IF NOT EXISTS stats_xp ON stats(xp DESC);
CREATE TABLE IF NOT EXISTS library (
    user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    data TEXT NOT NULL, updated REAL
);
-- per-user data for other apps/games: one JSON document per (user, app)
CREATE TABLE IF NOT EXISTS app_data (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    app TEXT NOT NULL,
    data TEXT NOT NULL,
    updated REAL,
    PRIMARY KEY (user_id, app)
);
-- failed logins per email, for throttling
CREATE TABLE IF NOT EXISTS login_fails (
    email TEXT PRIMARY KEY COLLATE NOCASE,
    count INTEGER NOT NULL,
    last REAL NOT NULL
);
