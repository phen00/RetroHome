"""Friends = the people you follow on RetroAchievements, with what they're playing right now.

RetroAchievements has no "add friend" API: you follow people on their RA profile page (RetroHome
opens it in the built-in browser). "Playing now" comes from rich presence, which the emulator
sends to RA every couple of minutes while a game runs; if it was updated in the last few minutes
the person is playing.
"""
import calendar
import time

from .retroach import RAError, media_url

PLAYING_WINDOW = 6 * 60     # rich presence newer than this = playing now
MAX_FRIENDS = 100           # summaries fetched per refresh (each is one API call)


def ra_time(s) -> float:
    """RetroAchievements timestamps ("2026-10-22 18:05:04" or ISO "2026-10-22T18:05:04+00:00") are UTC."""
    t = str(s or "")[:19].replace("T", " ")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return float(calendar.timegm(time.strptime(t, fmt)))
        except ValueError:
            pass
    return 0.0


def friend_from(follow: dict, summ: dict, now=None) -> dict:
    now = now or time.time()
    last = summ.get("LastGame") or {}
    recent = (summ.get("RecentlyPlayed") or [{}])[0] or {}
    presence_at = ra_time(summ.get("RichPresenceMsgDate"))
    played_at = max(presence_at, ra_time(recent.get("LastPlayed")))
    return dict(
        user=summ.get("User") or follow.get("User", ""),
        pic=media_url(summ.get("UserPic") or f"/UserPic/{follow.get('User', '')}.png"),
        points=int(summ.get("TotalPoints") or follow.get("Points") or 0),
        follows_me=bool(follow.get("IsFollowingMe")),
        playing=bool(presence_at) and now - presence_at < PLAYING_WINDOW,
        presence=(summ.get("RichPresenceMsg") or "").strip(),
        game_id=int(summ.get("LastGameID") or last.get("ID") or 0),
        game=last.get("Title") or recent.get("Title") or "",
        console=last.get("ConsoleName") or recent.get("ConsoleName") or "",
        icon=media_url(last.get("ImageIcon") or recent.get("ImageIcon") or ""),
        last=played_at,
    )


class Friends:
    def __init__(self, ra, tasks):
        self.ra = ra            # library.RAState (for the signed-in client)
        self.tasks = tasks
        self.list = []
        self.loading = False
        self.loaded = False
        self.error = ""
        self.last_refresh = 0.0
        self.version = 0
        self.started = []       # friends who just started playing (for notifications)
        self._client = None

    def _reset_if_user_changed(self):
        if self.ra.client is not self._client:
            self._client = self.ra.client
            self.list, self.loaded, self.error, self.started = [], False, "", []
            self.last_refresh = 0.0
            self.version += 1

    @property
    def playing(self):
        return [f for f in self.list if f["playing"]]

    def refresh(self, force=False, every=120):
        self._reset_if_user_changed()
        client = self.ra.client
        if not client or self.loading or (not force and time.time() - self.last_refresh < every):
            return
        self.loading = True

        def work():
            now = time.time()
            out = []
            for f in client.following()[:MAX_FRIENDS]:
                try:
                    out.append(friend_from(f, client.summary(f.get("ULID") or f.get("User", "")), now))
                except RAError:
                    out.append(friend_from(f, {}, now))
            out.sort(key=lambda f: (not f["playing"], -f["last"], f["user"].lower()))
            return out

        def done(res):
            if client is not self.ra.client:    # signed-in user changed meanwhile: drop it, fetch again
                self.loading = False
                return
            before = {f["user"]: f for f in self.list}
            if self.loaded:     # nothing to announce on the first load
                self.started += [f for f in res if f["playing"] and not before.get(f["user"], {}).get("playing")]
            self.list, self.loaded, self.error = res, True, ""
            self._finish()

        def fail(e):
            if client is not self.ra.client:
                self.loading = False
                return
            self.error = str(e)
            self._finish()
        self.tasks.submit(work, callback=done, error=fail)

    def _finish(self):
        self.loading = False
        self.last_refresh = time.time()
        self.version += 1
