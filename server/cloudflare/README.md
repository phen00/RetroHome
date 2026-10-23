# RetroHome Online on Cloudflare (free)

**Live at `https://retrohome-online.retrohome.workers.dev`**: Worker `retrohome-online`, D1 database
`retrohome` (Western Europe), on the RetroHome Cloudflare account. RetroHome has this address built
in (`retrohome/accounts.py`, `BUILTIN_SERVER`). The Worker creates its own tables on first use.

Runs the RetroHome Online server on Cloudflare's free plan: a **Worker** (the program that answers
RetroHome) and a **D1** database (Cloudflare's SQLite database that stores the accounts). No server
to rent or keep switched on. Same API as `../retrohome_server.py` (see `../API.md`), plus
`/api/v1/me/data/<app>` for storing other games' data.

## Setup (about 15 minutes)

You need a free Cloudflare account (https://dash.cloudflare.com/sign-up) and Node.js LTS
(https://nodejs.org). Open a terminal in this folder (`server/cloudflare`), then:

1. `npm install` (installs Cloudflare's `wrangler` tool into this folder)
2. `npx wrangler login` (a browser window opens; press **Allow**)
3. `npx wrangler d1 create retrohome`, then copy the `database_id` it prints into `wrangler.toml`
   in place of the one there (only when setting up a new server)
4. Optional: `npx wrangler d1 execute retrohome --remote --file=schema.sql` (the Worker creates the
   tables itself on first use anyway)
5. `npx wrangler deploy` (prints your address, e.g. `https://retrohome-online.<you>.workers.dev`)
6. Check it: open `https://retrohome-online.<you>.workers.dev/api/v1/health` in a browser. You should
   see `{"ok":true,...}`

Then put that address in `BUILTIN_SERVER` in `retrohome/accounts.py` and release a new version.
Players never enter an address: they just create an account with their email and a password.

## Later

- **Update the server:** get the new files, then `npx wrangler deploy` again. Run step 4 again too
  when the release notes say the database changed (it only adds what's missing).
- **Back up the data:** `npx wrangler d1 export retrohome --remote --output=backup.sql`
- **Watch it live (errors, requests):** `npx wrangler tail`

## Other games

Each signed-in player can store one JSON object per game:

    GET    /api/v1/me/data/<game>              -> {"app", "data": {...}, "updated"}
    PUT    /api/v1/me/data/<game>   {"data": {...}}   (up to 1 MB)
    DELETE /api/v1/me/data/<game>

with the same `Authorization: Bearer <token>` header RetroHome uses (from `/api/v1/auth/login`).

## Notes

- Free plan: 100,000 requests/day, 5 GB of D1 storage, 5 million rows read and 100,000 written per
  day. Going over a daily limit pauses the database until midnight UTC; nothing is lost.
- Passwords are hashed with PBKDF2-SHA256 at 10,000 rounds (the free plan allows very little CPU
  time per request) and logins are throttled after 5 wrong attempts per username.
