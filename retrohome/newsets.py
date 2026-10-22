"""Achievement sets recently added to RetroAchievements.

There's no "new sets" endpoint; the closest is the list of completed development claims. A claim
with SetType 0 is a brand-new set (1 = a revision of an existing one), ClaimType 0 the primary
developer (1 = a collaborator, which would repeat the game). Newest first.
"""
import time

from .friends import ra_time
from .retroach import RAError, media_url

REFRESH_EVERY = 3600
KEEP = 60


def sets_from_claims(claims: list) -> list:
    seen, out = set(), []
    for c in sorted(claims or [], key=lambda c: str(c.get("DoneTime") or c.get("Updated") or ""), reverse=True):
        gid = int(c.get("GameID") or 0)
        if not gid or gid in seen or int(c.get("SetType") or 0) != 0 or int(c.get("ClaimType") or 0) != 0:
            continue
        seen.add(gid)
        out.append(dict(GameID=gid, Title=c.get("GameTitle", ""), GameTitle=c.get("GameTitle", ""), ConsoleID=int(c.get("ConsoleID") or 0),
                        ConsoleName=c.get("ConsoleName", ""), ImageIcon=c.get("GameIcon", ""),
                        icon=media_url(c.get("GameIcon", "")), author=c.get("User", ""),
                        added=ra_time(c.get("DoneTime") or c.get("Updated"))))
        if len(out) >= KEEP:
            break
    return out


class NewSets:
    def __init__(self, ra, tasks):
        self.ra, self.tasks = ra, tasks
        self.list, self.loaded, self.loading, self.error = [], False, False, ""
        self.last_refresh = 0.0
        self.version = 0

    def refresh(self, force=False):
        client = self.ra.client
        if not client or self.loading or (not force and time.time() - self.last_refresh < REFRESH_EVERY):
            return
        self.loading = True

        def done(res):
            self.list, self.loaded, self.error = res, True, ""
            self._finish()

        def fail(e):
            self.error = str(e) if isinstance(e, RAError) else f"Couldn't load new sets ({e})"
            self._finish()
        self.tasks.submit(lambda: sets_from_claims(client.completed_claims()), callback=done, error=fail)

    def _finish(self):
        self.loading = False
        self.last_refresh = time.time()
        self.version += 1
