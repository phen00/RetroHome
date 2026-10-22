"""Find a user's RetroAchievements Web API key on their RA settings page.

RetroAchievements' achievement data is only available with the Web API key - a password can't be
used for it. "Sign in with password" therefore opens retroachievements.org in the built-in
browser; once you're signed in, RetroHome reads the key (and your username) from the settings
page, or from the clipboard if you press its copy button. The pair is verified against the API
before it's saved, so a wrong guess here can't sign anyone in with bad details.
"""
import re

SETTINGS_URL = "https://retroachievements.org/settings"
KEY_RE = re.compile(r"\b[A-Za-z0-9]{32}\b")
_KEY_PROPS = re.compile(r'"(?:webApiKey|apiKey|APIKey|webAPIKey|ApiKey)"\s*:\s*"([A-Za-z0-9]{32})"')
_USER_PROPS = re.compile(r'"(?:displayName|username|User|userName)"\s*:\s*"([A-Za-z0-9_.\-]{2,32})"')


def find_key(html: str = "", text: str = "", values=()) -> str:
    """The Web API key from the page: page data first, then form fields, then text near the label."""
    html = (html or "").replace("&quot;", '"')
    m = _KEY_PROPS.search(html)
    if m:
        return m.group(1)
    for v in values or ():
        v = (v or "").strip()
        if KEY_RE.fullmatch(v):
            return v
    t = text or ""
    i = t.lower().find("web api key")
    if i >= 0:
        m = KEY_RE.search(t, i, i + 400)
        if m:
            return m.group(0)
    return ""


def find_user(html: str = "") -> str:
    html = (html or "").replace("&quot;", '"')
    a = html.find('"auth"')                 # Inertia's shared props: {"auth": {"user": {...}}}
    m = _USER_PROPS.search(html, a if a >= 0 else 0)
    return m.group(1) if m else ""


def key_from_clipboard(text: str) -> str:
    t = (text or "").strip()
    return t if KEY_RE.fullmatch(t) else ""
