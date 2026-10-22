"""RetroAchievements-compatible ROM hashes for cartridge systems.

Matches rcheevos' rc_hash rules for the common cases; disc-based systems are
matched by title instead (their hashing needs full disc parsing).
"""
import hashlib
import zipfile
from pathlib import Path

MAX_SIZE = 64 * 1024 * 1024


def _read(path: Path):
    if path.suffix.lower() == ".zip":
        try:
            with zipfile.ZipFile(path) as z:
                members = [m for m in z.infolist() if not m.is_dir()
                           and not m.filename.lower().endswith((".txt", ".nfo", ".diz"))]
                if len(members) != 1 or members[0].file_size > MAX_SIZE:
                    return None
                return z.read(members[0])
        except (OSError, zipfile.BadZipFile, RuntimeError):
            return None
    if path.suffix.lower() == ".7z":
        return None
    try:
        if path.stat().st_size > MAX_SIZE:
            return None
        return path.read_bytes()
    except OSError:
        return None


def _n64_normalise(data: bytes) -> bytes:
    if len(data) < 4:
        return data
    head = data[:4]
    if head == b"\x80\x37\x12\x40":          # .z64 big endian
        return data
    if head == b"\x37\x80\x40\x12":          # .v64 byte-swapped
        b = bytearray(data)
        b[0::2], b[1::2] = data[1::2], data[0::2]
        return bytes(b)
    if head == b"\x40\x12\x37\x80":          # .n64 little endian
        b = bytearray(len(data))
        b[0::4], b[1::4], b[2::4], b[3::4] = data[3::4], data[2::4], data[1::4], data[0::4]
        return bytes(b)
    return data


def ra_hash(method: str, path: Path):
    """Return an md5 hex string or None if this method/file can't be hashed."""
    if not method:
        return None
    if method in ("psp", "ps2", "psx"):
        from .dischash import disc_hash
        return disc_hash(method, path)
    if method == "arcade":
        # Arcade hashes are the md5 of the file name without extension.
        return hashlib.md5(path.stem.encode("utf-8")).hexdigest()
    data = _read(path)
    if data is None:
        return None
    if method == "nes":
        if data[:4] == b"NES\x1a":
            data = data[16:]
        elif data[:4] == b"FDS\x1a":
            data = data[16:]
    elif method == "snes":
        if len(data) % 0x2000 == 512:
            data = data[512:]
    elif method == "lynx":
        if data[:5] == b"LYNX\x00":
            data = data[64:]
    elif method == "7800":
        if data[1:10] == b"ATARI7800":
            data = data[128:]
    elif method == "pce":
        if len(data) % 0x20000 == 512:
            data = data[512:]
    elif method == "n64":
        data = _n64_normalise(data)
    return hashlib.md5(data).hexdigest()
