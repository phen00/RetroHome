"""RetroAchievements disc hashes for PSP, PS2 and PS1 (mirrors rcheevos' hash_disc.c).

Supports .iso, .cso (PSP compressed ISO), raw .bin / .img (2352-byte sectors), .cue and .m3u
(first disc), and .pbp (PSP, whole-file hash). CHD isn't supported; those fall back to title
matching.
"""
import hashlib
import re
import struct
import zlib
from pathlib import Path

MAX_BUFFER = 64 * 1024 * 1024
SYNC = b"\x00" + b"\xff" * 10 + b"\x00"


class DiscError(Exception):
    pass


class _Disc:
    """Reads 2048-byte logical sectors from an image."""

    def __init__(self, path: Path):
        self.f = open(path, "rb")
        self.cso = None
        head = self.f.read(16)
        if head[:4] == b"CISO":
            self._open_cso(head)
            self.raw, self.offset = 2048, 0
        elif head[:12] == SYNC:
            mode = head[15]
            self.raw, self.offset = 2352, (24 if mode == 2 else 16)
        else:
            self.raw, self.offset = 2048, 0

    def _open_cso(self, head):
        self.f.seek(0)
        hdr = self.f.read(24)
        _, hsize, total, bsize, ver, align = struct.unpack("<4sIQIBB", hdr[:22])
        if bsize != 2048:
            raise DiscError("unsupported CSO block size")
        n = total // bsize + 1
        self.f.seek(24)
        self.cso_index = struct.unpack(f"<{n}I", self.f.read(4 * n))
        self.cso_align = align
        self.cso = True

    def close(self):
        self.f.close()

    def sector(self, lba: int) -> bytes:
        if self.cso:
            i0, i1 = self.cso_index[lba], self.cso_index[lba + 1]
            plain = bool(i0 & 0x80000000)
            p0 = (i0 & 0x7FFFFFFF) << self.cso_align
            p1 = (i1 & 0x7FFFFFFF) << self.cso_align
            self.f.seek(p0)
            data = self.f.read(max(2048, p1 - p0) if plain else p1 - p0)
            return data[:2048] if plain else zlib.decompress(data, -15)[:2048]
        self.f.seek(lba * self.raw + self.offset)
        d = self.f.read(2048)
        if len(d) < 2048:
            raise DiscError("read past end of disc")
        return d

    def read(self, lba: int, size: int) -> bytes:
        size = min(size, MAX_BUFFER)
        out = bytearray()
        while len(out) < size:
            out += self.sector(lba)
            lba += 1
        return bytes(out[:size])

    def find(self, path: str):
        """Return (lba, size) for a path like 'PSP_GAME\\SYSDIR\\EBOOT.BIN', or None."""
        pvd = self.sector(16)
        if pvd[1:6] != b"CD001":
            raise DiscError("not an ISO9660 disc")
        lba, size = struct.unpack_from("<I", pvd, 158)[0], struct.unpack_from("<I", pvd, 166)[0]
        parts = [p for p in re.split(r"[\\/]", path) if p]
        for depth, want in enumerate(parts):
            want = want.upper()
            found = None
            data = self.read(lba, min(size, 1024 * 1024))
            pos = 0
            while pos < len(data):
                ln = data[pos]
                if ln == 0:  # records don't cross sectors; jump to next one
                    pos = (pos // 2048 + 1) * 2048
                    continue
                rec = data[pos:pos + ln]
                nlen = rec[32]
                name = rec[33:33 + nlen].decode("ascii", "ignore").upper().split(";")[0]
                if name == want:
                    found = (struct.unpack_from("<I", rec, 2)[0], struct.unpack_from("<I", rec, 10)[0])
                    break
                pos += ln
            if not found:
                return None
            lba, size = found
        return lba, size


def _first_image(path: Path) -> Path:
    ext = path.suffix.lower()
    try:
        text = path.read_text(encoding="utf-8", errors="ignore") if ext in (".cue", ".m3u") else ""
    except OSError:
        return path
    if ext == ".m3u":
        for line in text.splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                return _first_image(path.parent / line)
    if ext == ".cue":
        m = re.search(r'FILE\s+"?([^"\r\n]+?)"?\s+BINARY', text, re.I)
        if m:
            return path.parent / m.group(1)
    return path


def _boot_exe(disc: _Disc, key: str, prefix: str):
    loc = disc.find("SYSTEM.CNF")
    if not loc:
        return None
    text = disc.read(loc[0], min(loc[1], 2047)).decode("ascii", "ignore")
    for line in text.splitlines():
        m = re.match(rf"\s*{key}\s*=\s*(.*)", line)
        if not m:
            continue
        val = m.group(1).strip()
        if val.lower().startswith(prefix):
            val = val[len(prefix):]
        val = val.lstrip("\\")
        name = re.split(r"[\s;]", val)[0][:63]
        if name:
            return name
    return None


def disc_hash(method: str, path: Path):
    path = _first_image(Path(path))
    ext = path.suffix.lower()
    if ext in (".chd", ".7z", ".zip", ".zso", ".rvz", ".ecm"):
        return None
    if method == "psp" and ext == ".pbp":
        h = hashlib.md5()
        with open(path, "rb") as f:
            h.update(f.read(MAX_BUFFER))
        return h.hexdigest()
    try:
        disc = _Disc(path)
    except (OSError, DiscError, struct.error):
        return None
    try:
        h = hashlib.md5()
        if method == "psp":
            sfo = disc.find("PSP_GAME\\PARAM.SFO")
            boot = disc.find("PSP_GAME\\SYSDIR\\EBOOT.BIN")
            if not sfo or not boot:
                return None
            h.update(disc.read(*sfo))
            h.update(disc.read(*boot))
            return h.hexdigest()
        if method in ("ps2", "psx"):
            key, prefix = ("BOOT2", "cdrom0:") if method == "ps2" else ("BOOT", "cdrom:")
            name = _boot_exe(disc, key, prefix)
            if not name and method == "psx":
                name = "PSX.EXE"
            if not name:
                return None
            loc = disc.find(name)
            if not loc:
                return None
            lba, size = loc
            if method == "psx":
                first = disc.sector(lba)
                if first[:7] == b"PS-X EX":
                    size = struct.unpack_from("<I", first, 28)[0] + 2048
            h.update(name.encode("ascii", "ignore"))
            h.update(disc.read(lba, size))
            return h.hexdigest()
    except (OSError, DiscError, struct.error, zlib.error, IndexError):
        return None
    finally:
        disc.close()
    return None
