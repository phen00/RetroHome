"""Tiny HTTP helpers (stdlib only)."""
import json
import os
import ssl
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

from . import __version__

UA = f"RetroHome/{__version__} (+emulator frontend)"
_ctx = ssl.create_default_context()


class HttpError(OSError):
    def __init__(self, code, msg=""):
        super().__init__(f"HTTP {code} {msg}".strip())
        self.code = code


def get(url: str, timeout: float = 20) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_ctx) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        raise HttpError(e.code, e.reason) from None


def get_json(url: str, timeout: float = 30):
    return json.loads(get(url, timeout).decode("utf-8", "replace"))


IMAGE_MAGIC = (b"\x89PNG", b"\xff\xd8\xff", b"GIF8", b"RIFF")


def download_image(url: str, dest: Path, timeout: float = 20) -> bool:
    """Download an image to dest atomically. Returns False on 404 / non-image."""
    try:
        data = get(url, timeout)
    except HttpError as e:
        if e.code in (403, 404, 410):
            return False
        raise
    if not data.startswith(IMAGE_MAGIC):
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=dest.parent, suffix=".part")
    with os.fdopen(fd, "wb") as f:
        f.write(data)
    os.replace(tmp, dest)
    return True
