"""Find emulators (EmuDeck on Steam Deck/Linux or Windows) and launch games.

Resolution order for a system:
  1. emulators.json overrides in the config folder (per system folder)
  2. the system's preference list from systems.py, first one installed wins

Override format (emulators.json):
{
  "retroarch": "C:/RetroArch/retroarch.exe",          # path to an emulator id
  "systems": {
    "snes": ["C:/Emus/bsnes/bsnes.exe", "{rom}"],      # full command for a system
    "psx":  "ra:pcsx_rearmed"                          # or just pick another emulator/core
  }
}
Placeholders: {rom} full path, {romname} file name without extension, {romdir} folder.
"""
import glob
import json
import os
import re
import shlex
import shutil
import subprocess
from pathlib import Path

from .paths import IS_LINUX, IS_MAC, IS_WINDOWS, config_dir

# Standalone emulators: launcher-script keywords (EmuDeck Linux), Windows exe globs
# (relative to EmuDeck's Emulators folder), Linux flatpak ids / binaries, and arguments.
STANDALONE = {
    "retroarch": dict(name="RetroArch", kw=["retroarch"], win=["RetroArch*/retroarch.exe", "RetroArch/retroarch.exe"],
                      flatpak="org.libretro.RetroArch", bin=["retroarch"], args=["{rom}"]),
    "dolphin": dict(name="Dolphin", kw=["dolphin"], win=["Dolphin*/Dolphin.exe"], flatpak="org.DolphinEmu.dolphin-emu",
                    bin=["dolphin-emu"], args=["-b", "-e", "{rom}"]),
    "primehack": dict(name="PrimeHack", kw=["primehack"], win=["primehack*/Dolphin.exe", "PrimeHack*/Dolphin.exe"],
                      flatpak="io.github.shiiion.primehack", bin=["primehack"], args=["-b", "-e", "{rom}"]),
    "pcsx2": dict(name="PCSX2", kw=["pcsx2"], win=["PCSX2*/pcsx2-qt*.exe", "pcsx2*/pcsx2*.exe"], flatpak="net.pcsx2.PCSX2",
                  bin=["pcsx2-qt"], args=["-batch", "-fullscreen", "--", "{rom}"]),
    "duckstation": dict(name="DuckStation", kw=["duckstation"], win=["duckstation*/duckstation-qt*.exe"],
                        flatpak="org.duckstation.DuckStation", bin=["duckstation-qt"], args=["-batch", "-fullscreen", "{rom}"]),
    "ppsspp": dict(name="PPSSPP", kw=["ppsspp"], win=["PPSSPP*/PPSSPPWindows64.exe"], flatpak="org.ppsspp.PPSSPP",
                   bin=["PPSSPPSDL", "ppsspp"], args=["{rom}"]),
    "rpcs3": dict(name="RPCS3", kw=["rpcs3"], win=["rpcs3*/rpcs3.exe"], flatpak="net.rpcs3.RPCS3", bin=["rpcs3"],
                  args=["--no-gui", "{rom}"]),
    "cemu": dict(name="Cemu", kw=["cemu"], win=["cemu*/Cemu.exe"], flatpak="info.cemu.Cemu", bin=["cemu", "Cemu"],
                 args=["-f", "-g", "{rom}"]),
    "eden": dict(name="Eden / Citron / Yuzu", kw=["eden", "citron", "yuzu", "sudachi"],
                 win=["eden*/eden.exe", "citron*/citron.exe", "yuzu*/yuzu.exe", "sudachi*/sudachi.exe"],
                 flatpak="", bin=["eden", "citron", "yuzu"], args=["-f", "-g", "{rom}"]),
    "ryujinx": dict(name="Ryujinx", kw=["ryujinx", "ryubing"], win=["Ryujinx*/Ryujinx.exe", "ryujinx*/Ryujinx*.exe"],
                    flatpak="org.ryujinx.Ryujinx", bin=["Ryujinx", "ryujinx"], args=["{rom}"]),
    "xemu": dict(name="xemu", kw=["xemu"], win=["xemu*/xemu.exe"], flatpak="app.xemu.xemu", bin=["xemu"],
                 args=["-full-screen", "-dvd_path", "{rom}"]),
    "xenia": dict(name="Xenia", kw=["xenia"], win=["xenia*/xenia_canary.exe", "xenia*/xenia.exe"], flatpak="",
                  bin=[], args=["{rom}"]),
    "vita3k": dict(name="Vita3K", kw=["vita3k"], win=["Vita3K*/Vita3K.exe"], flatpak="", bin=["Vita3K"], args=["{rom}"]),
    "shadps4": dict(name="shadPS4", kw=["shadps4"], win=["shadps4*/shadPS4*.exe"], flatpak="", bin=["shadps4"],
                    args=["-g", "{rom}"]),
    "melonds": dict(name="melonDS", kw=["melonds"], win=["melonDS*/melonDS.exe"], flatpak="net.kuribo64.melonDS",
                    bin=["melonDS"], args=["-f", "{rom}"]),
    "azahar": dict(name="Azahar / Lime3DS / Citra", kw=["azahar", "lime3ds", "citra"],
                   win=["azahar*/azahar.exe", "Azahar*/azahar*.exe", "lime3ds*/lime3ds*.exe", "citra*/citra-qt.exe"],
                   flatpak="org.azahar_emu.Azahar", bin=["azahar", "lime3ds", "citra-qt"], args=["{rom}"]),
    "flycast": dict(name="Flycast", kw=["flycast"], win=["flycast*/flycast.exe"], flatpak="org.flycast.Flycast",
                    bin=["flycast"], args=["{rom}"]),
    "supermodel": dict(name="Supermodel", kw=["supermodel"], win=["supermodel*/Supermodel.exe"],
                       flatpak="com.supermodel3.Supermodel", bin=["supermodel"], args=["-fullscreen", "{rom}"]),
    "model2": dict(name="Model 2 Emulator", kw=["model2", "model-2"], win=["model2*/EMULATOR.EXE", "model2*/emulator_multicpu.exe"],
                   flatpak="", bin=[], args=["{romname}"]),
    "rmg": dict(name="Rosalie's Mupen GUI", kw=["rmg"], win=["RMG*/RMG.exe"], flatpak="com.github.Rosalie241.RMG",
                bin=["RMG"], args=["--fullscreen", "{rom}"]),
    "scummvm": dict(name="ScummVM", kw=["scummvm"], win=["scummvm*/scummvm.exe", "ScummVM*/scummvm.exe"],
                    flatpak="org.scummvm.ScummVM", bin=["scummvm"], args=["{rom}"]),
}


class LaunchError(Exception):
    pass


def _flatpak_installed(app_id: str) -> bool:
    if not app_id or not shutil.which("flatpak"):
        return False
    for base in (Path.home() / ".local/share/flatpak/app", Path("/var/lib/flatpak/app")):
        if (base / app_id).is_dir():
            return True
    return False


class Emulators:
    def __init__(self, emulation_dir: Path):
        self.emulation_dir = Path(emulation_dir)
        self.override_path = config_dir() / "emulators.json"
        self.overrides = {}
        self._cache = {}
        self.reload()

    # ------------------------------------------------------------ setup
    def reload(self):
        self._cache.clear()
        self.__dict__.pop("_win_index", None)
        self.__dict__.pop("_ps1_paths", None)
        self.overrides = {}
        if not self.override_path.exists():
            self._write_template()
        try:
            with open(self.override_path, "r", encoding="utf-8") as f:
                self.overrides = json.load(f)
        except (OSError, ValueError):
            self.overrides = {}

    def set_emulators_dir(self, path):
        """Remember a manually chosen emulators folder ('' = automatic) in emulators.json."""
        data = dict(self.overrides)
        if path:
            data["emulators_dir"] = str(path)
        else:
            data.pop("emulators_dir", None)
        with open(self.override_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        self.reload()

    def _write_template(self):
        tmpl = {
            "_help": ("Leave empty to auto-detect EmuDeck emulators. Set an emulator id to a path to "
                      "override it, e.g. \"retroarch\": \"C:/RetroArch/retroarch.exe\". Under \"systems\" "
                      "you can force a system to another emulator (\"psx\": \"ra:pcsx_rearmed\") or a full "
                      "command ([\"/path/to/emu\", \"--fullscreen\", \"{rom}\"]). Placeholders: {rom} "
                      "{romname} {romdir}. Extra RetroArch core folder: \"retroarch_cores\"."),
            "systems": {},
        }
        try:
            with open(self.override_path, "w", encoding="utf-8") as f:
                json.dump(tmpl, f, indent=2)
        except OSError:
            pass

    # ------------------------------------------------------------ discovery
    def launcher_dirs(self):
        dirs = [self.emulation_dir / "tools" / "launchers", Path.home() / "Emulation" / "tools" / "launchers"]
        if IS_WINDOWS:
            dirs += [Path("C:/Emulation/tools/launchers")]
        out, seen = [], set()
        for d in dirs:
            try:
                key = str(d.resolve()).lower()
            except OSError:
                continue
            if d.is_dir() and key not in seen:
                seen.add(key)
                out.append(d)
        return out

    def windows_emu_roots(self):
        """(folder, search depth) pairs where Windows emulators may live, most likely first.

        EmuDeck for Windows installs into %USERPROFILE%\\emudeck\\EmulationStation-DE\\Emulators
        (older versions used %APPDATA%\\EmuDeck\\Emulators)."""
        home = Path(os.environ.get("USERPROFILE") or Path.home())
        roots = []
        if self.overrides.get("emulators_dir"):
            roots.append((Path(self.overrides["emulators_dir"]), 4))
        roots += [(home / "emudeck" / "EmulationStation-DE" / "Emulators", 3),
                 (home / "emudeck" / "Emulators", 3),
                 (home / "emudeck", 4)]
        appdata = os.environ.get("APPDATA")
        if appdata:
            roots += [(Path(appdata) / "EmuDeck" / "Emulators", 3), (Path(appdata) / "emudeck", 4)]
        for base in (self.emulation_dir, self.emulation_dir.parent):
            roots += [(base / "EmulationStation-DE" / "Emulators", 3), (base / "EmuDeck" / "Emulators", 3),
                      (base / "Emulators", 3), (base / "tools", 3)]
        roots.append((Path("C:/Emulators"), 3))
        for pf in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"):
            if os.environ.get(pf):
                roots.append((Path(os.environ[pf]), 2))
        seen, out = set(), []
        for r, depth in roots:
            try:
                key = str(r.resolve()).lower()
                if r.is_dir() and key not in seen:
                    seen.add(key)
                    out.append((r, depth))
            except OSError:
                pass
        return out

    def _exe_index(self, root, depth):
        """All .exe files under root (to `depth` levels), cached: [(lowercase rel parts, Path)]."""
        cache = self.__dict__.setdefault("_win_index", {})
        key = (str(root), depth)
        if key in cache:
            return cache[key]
        found = []

        def walk(d, level):
            try:
                entries = list(os.scandir(d))
            except OSError:
                return
            for e in entries:
                try:
                    if e.is_dir():
                        if level < depth and not e.name.startswith(".") and e.name.lower() not in (
                                "windowsapps", "common files", "windows defender", "microsoft", "packages"):
                            walk(e.path, level + 1)
                    elif e.name.lower().endswith(".exe"):
                        p = Path(e.path)
                        found.append(([x.lower() for x in p.relative_to(root).parts], p))
                except OSError:
                    continue
        walk(root, 1)
        cache[key] = found
        return found

    def _windows_launcher_paths(self):
        """EmuDeck for Windows writes Emulation\\tools\\launchers\\<emu>.ps1 containing
        $emulatorFile = "...\\retroarch.exe". Read those: they say exactly where EmuDeck put each one."""
        cache = self.__dict__.get("_ps1_paths")
        if cache is not None:
            return cache
        out = {}
        env = {k.lower(): v for k, v in os.environ.items()}
        for d in self.launcher_dirs():
            try:
                files = [f for f in d.iterdir() if f.suffix.lower() == ".ps1"]
            except OSError:
                continue
            for f in files:
                try:
                    text = f.read_text(encoding="utf-8", errors="ignore")
                except OSError:
                    continue
                m = re.search(r'\$emulatorFile\s*=\s*["\']([^"\']+)["\']', text)
                if not m:
                    continue
                raw = re.sub(r"\$env:([A-Za-z_][A-Za-z0-9_]*)", lambda mm: env.get(mm.group(1).lower(), mm.group(0)),
                             m.group(1))
                out[f.stem.lower()] = Path(raw)
        self.__dict__["_ps1_paths"] = out
        self.log(f"EmuDeck launchers: {len(out)} found in {[str(d) for d in self.launcher_dirs()]}")
        return out

    def _from_launchers(self, emu_id, spec):
        paths = self._windows_launcher_paths()
        for kw in spec["kw"]:
            for stem, path in paths.items():
                if kw not in stem or (emu_id == "dolphin" and "primehack" in stem):
                    continue
                try:
                    if path.is_file():
                        return path
                    # EmuDeck sometimes names the exe differently from its launcher; look beside it
                    if path.parent.is_dir():
                        exes = sorted(path.parent.glob("*.exe"))
                        for pat in spec["win"]:
                            exe_pat = pat.rpartition("/")[2].lower()
                            import fnmatch
                            hit = next((e for e in exes if fnmatch.fnmatch(e.name.lower(), exe_pat)), None)
                            if hit:
                                return hit
                except OSError:
                    continue
        return None

    def log(self, msg):
        self.__dict__.setdefault("search_log", []).append(msg)
        print("[emulators]", msg, flush=True)

    def diagnostics(self):
        """Human-readable summary of where emulators were looked for (Settings > Emulator setup)."""
        lines = []
        if IS_WINDOWS:
            lines.append(f"EmuDeck launchers: {len(self._windows_launcher_paths())} in "
                         f"{', '.join(str(d) for d in self.launcher_dirs()) or 'no launchers folder found'}")
            for root, depth in self.windows_emu_roots():
                n = len(self._exe_index(root, depth))
                lines.append(f"{root}: {n} programs")
        else:
            lines.append(f"Launchers: {', '.join(str(d) for d in self.launcher_dirs()) or 'none found'}")
        return lines

    def _find_windows_exe(self, emu_id, patterns):
        """Match patterns like 'PCSX2*/pcsx2-qt*.exe' at any depth (folder names may differ)."""
        import fnmatch
        for root, depth in self.windows_emu_roots():
            index = self._exe_index(root, depth)
            for pat in patterns:
                dir_pat, _, exe_pat = pat.lower().rpartition("/")
                for parts, path in index:
                    if not fnmatch.fnmatch(parts[-1], exe_pat):
                        continue
                    folders = parts[:-1]
                    if emu_id == "dolphin" and any("primehack" in f for f in folders):
                        continue
                    loose = self.overrides.get("emulators_dir") and Path(self.overrides["emulators_dir"]) == root
                    if dir_pat and not loose and not any(fnmatch.fnmatch(f, dir_pat) for f in folders):
                        continue
                    return path
        return None

    def find_launcher_script(self, keywords, exclude=()):
        exts = (".sh",) if not IS_WINDOWS else (".bat", ".cmd", ".ps1")
        for d in self.launcher_dirs():
            try:
                scripts = sorted(d.iterdir())
            except OSError:
                continue
            for kw in keywords:
                for s in scripts:
                    n = s.name.lower()
                    if s.suffix.lower() in exts and kw in n and not any(x in n for x in exclude):
                        return s
        return None

    def find_standalone(self, emu_id: str):
        """Return a base command list for a standalone emulator, or None."""
        if emu_id in self._cache:
            return self._cache[emu_id]
        spec = STANDALONE.get(emu_id)
        cmd = None
        ov = self.overrides.get(emu_id)
        if isinstance(ov, str) and ov:
            cmd = [ov] if Path(ov).exists() else shlex.split(ov)
        elif isinstance(ov, list) and ov:
            cmd = list(ov)
        elif spec:
            if IS_WINDOWS:
                hit = self._from_launchers(emu_id, spec) or self._find_windows_exe(emu_id, spec["win"])
                if hit:
                    cmd = [str(hit)]
                if not cmd:
                    for b in spec["bin"]:
                        w = shutil.which(b)
                        if w:
                            cmd = [w]
                            break
            else:
                exclude = ("primehack",) if emu_id == "dolphin" else ()
                script = self.find_launcher_script(spec["kw"], exclude)
                if script:
                    cmd = ["bash", str(script)] if IS_LINUX else [str(script)]
                elif _flatpak_installed(spec.get("flatpak")):
                    cmd = ["flatpak", "run", spec["flatpak"]]
                else:
                    for b in spec["bin"]:
                        w = shutil.which(b)
                        if w:
                            cmd = [w]
                            break
                    if not cmd:
                        # AppImages that EmuDeck drops into ~/Applications (or a folder chosen in Settings)
                        app_dirs = [Path.home() / "Applications", self.emulation_dir.parent / "Applications"]
                        if self.overrides.get("emulators_dir"):
                            app_dirs.insert(0, Path(self.overrides["emulators_dir"]))
                        for app_dir in app_dirs:
                            for kw in spec["kw"]:
                                hits = [h for h in glob.glob(str(app_dir / "*.AppImage")) if kw in Path(h).name.lower()]
                                if hits:
                                    cmd = [hits[0]]
                                    break
                            if cmd:
                                break
        self._cache[emu_id] = cmd
        self.log(f"{emu_id}: {cmd[0] if cmd else 'NOT FOUND'}")
        return cmd

    def retroarch_core_path(self, core: str):
        name = f"{core}_libretro" + (".dll" if IS_WINDOWS else ".dylib" if IS_MAC else ".so")
        dirs = []
        extra = self.overrides.get("retroarch_cores")
        if extra:
            dirs.append(Path(extra))
        ra = self.find_standalone("retroarch")
        if IS_WINDOWS:
            if ra:
                dirs.append(Path(ra[0]).parent / "cores")
        else:
            dirs += [Path.home() / ".var/app/org.libretro.RetroArch/config/retroarch/cores",
                     Path.home() / ".config/retroarch/cores",
                     Path.home() / ".local/share/Steam/steamapps/common/RetroArch/cores",
                     Path("/usr/lib/libretro"), Path("/usr/lib/x86_64-linux-gnu/libretro"),
                     Path("/usr/local/lib/libretro")]
            if ra and ra[0] not in ("bash", "flatpak"):
                dirs.append(Path(ra[0]).parent / "cores")
        for d in dirs:
            p = d / name
            if p.exists():
                return p
        return None

    # ------------------------------------------------------------ resolution
    def resolve(self, game, path=None):
        """Return (command list, emulator label) or raise LaunchError."""
        system = game.system
        path = Path(path) if path else game.path
        rom = str(path)
        subs = {"{rom}": rom, "{romname}": path.stem, "{romdir}": str(path.parent)}

        def fill(args):
            out = []
            for a in args:
                for k, v in subs.items():
                    a = a.replace(k, v)
                out.append(a)
            return out

        prefs = list(system.emus)
        sys_ov = (self.overrides.get("systems") or {}).get(system.folder)
        if isinstance(sys_ov, list) and sys_ov:
            if not any("{rom" in a for a in sys_ov):
                sys_ov = sys_ov + ["{rom}"]
            return fill(sys_ov), "custom"
        if isinstance(sys_ov, str) and sys_ov:
            prefs = [sys_ov] + prefs

        tried = []
        for pref in prefs:
            if pref == "native":
                return self._native_command(game), "native"
            if pref.startswith("ra:"):
                core = pref[3:]
                ra = self.find_standalone("retroarch")
                if not ra:
                    tried.append("RetroArch")
                    continue
                core_path = self.retroarch_core_path(core)
                if not core_path:
                    tried.append(f"RetroArch core '{core}'")
                    continue
                cmd = list(ra) + ["-f", "-L", str(core_path), rom]
                return cmd, f"RetroArch · {core}"
            spec = STANDALONE.get(pref)
            base = self.find_standalone(pref)
            if base and spec:
                return list(base) + fill(spec["args"]), spec["name"]
            tried.append(spec["name"] if spec else pref)
        if not prefs:
            raise LaunchError(f"No emulator is set up for {system.name}. "
                              f"Add one for \"{system.folder}\" in emulators.json.")
        raise LaunchError("Couldn't find " + ", ".join(dict.fromkeys(tried)) +
                          f" for {system.name}. RetroHome launches games through EmuDeck: make sure EmuDeck "
                          f"(emudeck.com) installed this emulator. If it did, choose its emulators folder in "
                          f"Settings > Emulators folder.")

    def _native_command(self, game):
        p = str(game.path)
        ext = game.path.suffix.lower()
        if IS_WINDOWS:
            return ["cmd", "/c", "start", "/wait", "", p]
        if ext == ".sh":
            return ["bash", p]
        if ext == ".desktop":
            return ["gio", "launch", p] if shutil.which("gio") else ["xdg-open", p]
        return [p]

    def launch(self, game, path=None):
        cmd, label = self.resolve(game, path)
        cwd = None
        first = cmd[0]
        if os.path.isabs(first) and os.path.exists(first):
            cwd = str(Path(first).parent)
        elif first == "bash" and len(cmd) > 1:
            cwd = str(Path(cmd[1]).parent)
        env = os.environ.copy()
        kwargs = {}
        if IS_WINDOWS:
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0) if first == "cmd" else 0
        try:
            proc = subprocess.Popen(cmd, cwd=cwd, env=env, stdin=subprocess.DEVNULL, **kwargs)
        except OSError as e:
            raise LaunchError(f"Failed to start {label}: {e}") from None
        return proc, label, cmd
