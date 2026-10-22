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

# Where Linux distributions keep their trusted certificates (SteamOS/Arch, Debian/Ubuntu, Fedora, ...)
SYSTEM_CA_FILES = ("/etc/ssl/certs/ca-certificates.crt", "/etc/pki/tls/certs/ca-bundle.crt",
                   "/etc/ssl/cert.pem", "/etc/ssl/ca-bundle.pem", "/etc/pki/ca-trust/extracted/pem/tls-ca-bundle.pem")


def make_context() -> ssl.SSLContext:
    """HTTPS context that works in the release builds too.

    A PyInstaller build carries the OpenSSL of the machine that built it, which looks for
    certificates where *that* machine kept them - on a Steam Deck there's nothing there, so every
    HTTPS request failed with CERTIFICATE_VERIFY_FAILED. Add certifi's bundle (shipped with the
    build) and the system's own bundle so verification always has something to check against.
    """
    ctx = ssl.create_default_context()
    extra = []
    try:
        import certifi
        extra.append(certifi.where())
    except ImportError:
        pass
    extra += [p for p in SYSTEM_CA_FILES if os.path.isfile(p)]
    if os.environ.get("SSL_CERT_FILE"):
        extra.append(os.environ["SSL_CERT_FILE"])
    for path in extra:
        try:
            ctx.load_verify_locations(cafile=path)
        except (OSError, ssl.SSLError):
            pass
    return ctx


_ctx = make_context()


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
