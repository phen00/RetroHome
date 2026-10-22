"""System definitions keyed by EmuDeck / ES-DE rom folder name.

Each system lists:
  name      display name
  ra        RetroAchievements console ID (0 = none)
  thumb     libretro-thumbnails system name (for box art), "" = none
  emus      emulator preference list: "ra:<core>" for a RetroArch core,
            or a standalone emulator id defined in emulators.py
  exts      accepted file extensions (None = anything not junk)
  hash      RetroAchievements hashing method (see rahash.py), "" = title match only
  color     tile colour for placeholder art
"""
from dataclasses import dataclass, field


@dataclass
class System:
    folder: str
    name: str
    ra: int = 0
    thumb: str = ""
    emus: list = field(default_factory=list)
    exts: tuple = None
    hash: str = ""
    color: tuple = (60, 70, 90)
    short: str = ""

    @property
    def label(self):
        return self.short or self.name


DISC = (".chd", ".cue", ".m3u", ".iso", ".gdi", ".cdi", ".ccd", ".pbp", ".cso", ".rvz",
        ".gcz", ".wbfs", ".ecm", ".mds", ".toc", ".img", ".zso", ".7z", ".zip")

_TABLE = []


def S(folders, name, ra=0, thumb="", emus=(), exts=None, hash="", color=(60, 70, 90), short=""):
    if isinstance(folders, str):
        folders = [folders]
    for f in folders:
        _TABLE.append(System(f, name, ra, thumb, list(emus), tuple(exts) if exts else None,
                             hash, color, short))


# ---------------- Nintendo ----------------
S(["nes", "famicom"], "Nintendo Entertainment System", 7, "Nintendo - Nintendo Entertainment System",
  ["ra:mesen", "ra:nestopia", "ra:fceumm"], [".nes", ".unf", ".unif", ".zip", ".7z"], "nes", (196, 40, 40), "NES")
S("fds", "Famicom Disk System", 7, "Nintendo - Family Computer Disk System",
  ["ra:mesen", "ra:fceumm"], [".fds", ".zip", ".7z"], "", (196, 40, 40), "FDS")
S(["snes", "sfc", "snesna", "sneshd"], "Super Nintendo", 3, "Nintendo - Super Nintendo Entertainment System",
  ["ra:snes9x", "ra:bsnes"], [".sfc", ".smc", ".fig", ".swc", ".bs", ".zip", ".7z"], "snes", (110, 80, 170), "SNES")
S("satellaview", "Satellaview", 3, "Nintendo - Satellaview", ["ra:snes9x"], [".bs", ".sfc", ".smc", ".zip", ".7z"], "snes", (110, 80, 170))
S("sufami", "Sufami Turbo", 3, "Nintendo - Sufami Turbo", ["ra:snes9x"], [".st", ".zip", ".7z"], "", (110, 80, 170))
S("n64", "Nintendo 64", 2, "Nintendo - Nintendo 64",
  ["ra:mupen64plus_next", "rmg", "ra:parallel_n64"], [".z64", ".n64", ".v64", ".zip", ".7z"], "n64", (40, 140, 70), "N64")
S("n64dd", "Nintendo 64DD", 2, "Nintendo - Nintendo 64DD", ["ra:mupen64plus_next"], [".ndd", ".zip", ".7z"], "", (40, 140, 70))
S("gb", "Game Boy", 4, "Nintendo - Game Boy", ["ra:gambatte", "ra:sameboy", "ra:mgba"], [".gb", ".zip", ".7z"], "plain", (120, 130, 60), "GB")
S("gbc", "Game Boy Color", 6, "Nintendo - Game Boy Color", ["ra:gambatte", "ra:sameboy", "ra:mgba"], [".gbc", ".gb", ".zip", ".7z"], "plain", (150, 60, 160), "GBC")
S("sgb", "Super Game Boy", 4, "Nintendo - Game Boy", ["ra:mgba", "ra:mesen-s"], [".gb", ".gbc", ".zip", ".7z"], "plain", (120, 130, 60), "SGB")
S("gba", "Game Boy Advance", 5, "Nintendo - Game Boy Advance", ["ra:mgba", "ra:vba_next"], [".gba", ".zip", ".7z"], "plain", (70, 60, 170), "GBA")
S("nds", "Nintendo DS", 18, "Nintendo - Nintendo DS", ["melonds", "ra:melondsds", "ra:melonds", "ra:desmume"], [".nds", ".zip", ".7z"], "", (150, 150, 160), "DS")
S("n3ds", "Nintendo 3DS", 62, "Nintendo - Nintendo 3DS", ["azahar", "ra:citra"], [".3ds", ".cci", ".cxi", ".3dsx", ".app", ".cia", ".zcci", ".zcxi", ".z3dsx"], "", (200, 40, 50), "3DS")
S("gc", "Nintendo GameCube", 16, "Nintendo - GameCube", ["dolphin", "ra:dolphin"], [".iso", ".rvz", ".gcz", ".gcm", ".ciso", ".dol", ".elf", ".m3u"], "", (90, 70, 160), "GameCube")
S("wii", "Nintendo Wii", 19, "Nintendo - Wii", ["dolphin", "ra:dolphin"], [".iso", ".rvz", ".wbfs", ".wad", ".gcz", ".ciso", ".dol", ".elf"], "", (60, 170, 210), "Wii")
S("primehack", "Metroid Prime (PrimeHack)", 0, "Nintendo - Wii", ["primehack"], [".iso", ".rvz", ".wbfs", ".gcz", ".ciso"], "", (200, 110, 30), "PrimeHack")
S("wiiu", "Nintendo Wii U", 20, "Nintendo - Wii U", ["cemu"], [".wua", ".wux", ".wud", ".rpx", ".elf"], "", (40, 140, 200), "Wii U")
S("switch", "Nintendo Switch", 0, "", ["eden", "ryujinx"], [".nsp", ".xci", ".nca", ".nro", ".nso"], "", (220, 50, 40), "Switch")
S("virtualboy", "Virtual Boy", 28, "Nintendo - Virtual Boy", ["ra:mednafen_vb"], [".vb", ".vboy", ".zip", ".7z"], "plain", (170, 20, 30), "VB")
S("pokemini", "Pokémon Mini", 24, "Nintendo - Pokemon Mini", ["ra:pokemini"], [".min", ".zip", ".7z"], "plain", (200, 160, 40), "Poké Mini")
S(["gameandwatch", "lcdgames"], "Game & Watch", 60, "Handheld Electronic Game", ["ra:gw"], [".mgw", ".zip", ".7z"], "", (180, 150, 90), "G&W")

# ---------------- Sony ----------------
S("psx", "PlayStation", 12, "Sony - PlayStation", ["duckstation", "ra:swanstation", "ra:mednafen_psx_hw", "ra:pcsx_rearmed"],
  [".chd", ".cue", ".m3u", ".pbp", ".iso", ".img", ".ecm", ".mds", ".ccd", ".exe", ".7z", ".zip"], "psx", (120, 120, 130), "PS1")
S("ps2", "PlayStation 2", 21, "Sony - PlayStation 2", ["pcsx2", "ra:pcsx2"], [".iso", ".chd", ".cso", ".zso", ".gz", ".bin", ".cue", ".m3u", ".elf"], "ps2", (30, 50, 140), "PS2")
S("ps3", "PlayStation 3", 0, "Sony - PlayStation 3", ["rpcs3"], [".ps3", ".pkg", ".iso", ".ps3dir"], "", (30, 30, 30), "PS3")
S("ps4", "PlayStation 4", 0, "", ["shadps4"], [".bin", ".pkg", ".elf"], "", (20, 60, 150), "PS4")
S("psp", "PlayStation Portable", 41, "Sony - PlayStation Portable", ["ppsspp", "ra:ppsspp"], [".iso", ".cso", ".chd", ".pbp", ".elf", ".prx"], "psp", (50, 50, 60), "PSP")
S("psvita", "PlayStation Vita", 0, "Sony - PlayStation Vita", ["vita3k"], [".vpk", ".psvita", ".zip"], "", (40, 70, 160), "Vita")

# ---------------- Sega ----------------
S(["genesis", "megadrive", "megadrivejp"], "Sega Genesis / Mega Drive", 1, "Sega - Mega Drive - Genesis",
  ["ra:genesis_plus_gx", "ra:picodrive"], [".md", ".gen", ".bin", ".smd", ".68k", ".sgd", ".zip", ".7z"], "plain", (30, 30, 30), "Genesis")
S("mastersystem", "Sega Master System", 11, "Sega - Master System - Mark III", ["ra:genesis_plus_gx", "ra:picodrive"],
  [".sms", ".bin", ".zip", ".7z"], "plain", (200, 40, 40), "SMS")
S("gamegear", "Sega Game Gear", 15, "Sega - Game Gear", ["ra:genesis_plus_gx"], [".gg", ".bin", ".zip", ".7z"], "plain", (40, 40, 50), "Game Gear")
S("sg-1000", "Sega SG-1000", 33, "Sega - SG-1000", ["ra:genesis_plus_gx", "ra:bluemsx"], [".sg", ".bin", ".zip", ".7z"], "plain", (60, 60, 60), "SG-1000")
S(["segacd", "megacd", "megacdjp"], "Sega CD / Mega-CD", 9, "Sega - Mega-CD - Sega CD", ["ra:genesis_plus_gx", "ra:picodrive"],
  [".chd", ".cue", ".m3u", ".iso", ".zip", ".7z"], "", (40, 40, 60), "Sega CD")
S(["sega32x", "sega32xjp", "sega32xna"], "Sega 32X", 10, "Sega - 32X", ["ra:picodrive"], [".32x", ".bin", ".zip", ".7z"], "plain", (160, 40, 40), "32X")
S(["saturn", "saturnjp"], "Sega Saturn", 39, "Sega - Saturn", ["ra:mednafen_saturn", "ra:yabasanshiro", "ra:kronos"],
  [".chd", ".cue", ".m3u", ".iso", ".ccd", ".mds", ".zip"], "", (60, 60, 80), "Saturn")
S("dreamcast", "Sega Dreamcast", 40, "Sega - Dreamcast", ["ra:flycast", "flycast"], [".chd", ".cdi", ".gdi", ".m3u", ".cue", ".zip", ".7z"], "", (230, 120, 30), "Dreamcast")
S(["naomi", "naomigd"], "Sega NAOMI", 0, "Sega - Naomi", ["ra:flycast", "flycast"], [".zip", ".7z", ".chd", ".lst", ".bin", ".dat"], "", (200, 100, 40), "NAOMI")
S("atomiswave", "Atomiswave", 0, "Atomiswave", ["ra:flycast", "flycast"], [".zip", ".7z", ".chd", ".lst"], "", (200, 100, 40))
S("model2", "Sega Model 2", 0, "", ["model2"], [".zip"], "", (40, 80, 160))
S("model3", "Sega Model 3", 0, "", ["supermodel"], [".zip"], "", (40, 80, 160))

# ---------------- Microsoft ----------------
S("xbox", "Xbox", 0, "Microsoft - Xbox", ["xemu"], [".iso", ".xiso"], "", (60, 140, 40), "Xbox")
S("xbox360", "Xbox 360", 0, "Microsoft - Xbox 360", ["xenia"], [".iso", ".xex", ".zar", ".god"], "", (100, 170, 40), "Xbox 360")
S(["msx", "msx1"], "MSX", 29, "Microsoft - MSX", ["ra:bluemsx", "ra:fmsx"], [".rom", ".mx1", ".mx2", ".dsk", ".cas", ".zip", ".7z", ".m3u"], "", (90, 90, 120))
S(["msx2", "msxturbor"], "MSX2", 29, "Microsoft - MSX2", ["ra:bluemsx", "ra:fmsx"], [".rom", ".mx2", ".dsk", ".cas", ".zip", ".7z", ".m3u"], "", (90, 90, 120))

# ---------------- Arcade ----------------
S(["arcade", "mame", "mame-advmame", "mame-mame4all", "mess"], "Arcade", 27, "MAME",
  ["ra:mame", "ra:mame2003_plus", "ra:fbneo"], [".zip", ".7z", ".chd"], "arcade", (220, 160, 30), "Arcade")
S(["fbneo", "fba"], "FinalBurn Neo", 27, "FBNeo - Arcade Games", ["ra:fbneo"], [".zip", ".7z"], "arcade", (220, 120, 30), "FBNeo")
S(["cps", "cps1", "cps2", "cps3"], "Capcom Play System", 27, "MAME", ["ra:fbneo", "ra:mame"], [".zip", ".7z"], "arcade", (40, 90, 200), "CPS")
S("neogeo", "Neo Geo", 27, "SNK - Neo Geo", ["ra:fbneo", "ra:mame"], [".zip", ".7z"], "arcade", (200, 160, 40), "Neo Geo")
S(["neogeocd", "neogeocdjp"], "Neo Geo CD", 56, "SNK - Neo Geo CD", ["ra:neocd"], [".chd", ".cue", ".m3u", ".zip"], "", (200, 160, 40), "Neo Geo CD")
S("daphne", "Daphne (Laserdisc)", 0, "", [], [".daphne", ".singe"], "", (100, 60, 30))

# ---------------- NEC ----------------
S(["pcengine", "tg16"], "PC Engine / TurboGrafx-16", 8, "NEC - PC Engine - TurboGrafx 16", ["ra:mednafen_pce_fast", "ra:mednafen_pce"],
  [".pce", ".sgx", ".zip", ".7z"], "pce", (200, 60, 40), "PC Engine")
S(["pcenginecd", "tg-cd"], "PC Engine CD", 76, "NEC - PC Engine CD - TurboGrafx-CD", ["ra:mednafen_pce_fast", "ra:mednafen_pce"],
  [".chd", ".cue", ".m3u", ".ccd", ".zip"], "", (200, 60, 40), "PCE CD")
S("supergrafx", "PC Engine SuperGrafx", 8, "NEC - PC Engine SuperGrafx", ["ra:mednafen_supergrafx"], [".pce", ".sgx", ".zip", ".7z"], "pce", (200, 60, 40), "SuperGrafx")
S("pcfx", "PC-FX", 49, "NEC - PC-FX", ["ra:mednafen_pcfx"], [".chd", ".cue", ".m3u", ".ccd"], "", (150, 60, 60), "PC-FX")
S("pc88", "NEC PC-8801", 47, "NEC - PC-8001 - PC-8801", ["ra:quasi88"], [".d88", ".u88", ".m3u", ".zip"], "", (90, 90, 90), "PC-88")
S("pc98", "NEC PC-9801", 48, "NEC - PC-98", ["ra:np2kai"], [".d98", ".hdi", ".fdi", ".hdm", ".m3u", ".zip"], "", (90, 90, 90), "PC-98")

# ---------------- Atari ----------------
S("atari2600", "Atari 2600", 25, "Atari - 2600", ["ra:stella", "ra:stella2014"], [".a26", ".bin", ".zip", ".7z"], "plain", (150, 90, 40), "2600")
S("atari5200", "Atari 5200", 50, "Atari - 5200", ["ra:a5200", "ra:atari800"], [".a52", ".bin", ".car", ".zip", ".7z"], "plain", (150, 90, 40), "5200")
S("atari7800", "Atari 7800", 51, "Atari - 7800", ["ra:prosystem"], [".a78", ".bin", ".zip", ".7z"], "7800", (150, 90, 40), "7800")
S("atari800", "Atari 800", 0, "Atari - 8-bit", ["ra:atari800"], [".atr", ".xex", ".xfd", ".car", ".rom", ".bin", ".zip"], "", (150, 90, 40))
S("atarixe", "Atari XE", 0, "Atari - 8-bit", ["ra:atari800"], [".atr", ".xex", ".xfd", ".car", ".rom", ".bin", ".zip"], "", (150, 90, 40))
S("atarilynx", "Atari Lynx", 13, "Atari - Lynx", ["ra:handy", "ra:mednafen_lynx"], [".lnx", ".o", ".zip", ".7z"], "lynx", (70, 70, 70), "Lynx")
S("atarijaguar", "Atari Jaguar", 17, "Atari - Jaguar", ["ra:virtualjaguar"], [".j64", ".jag", ".rom", ".abs", ".cof", ".bin", ".prg", ".zip", ".7z"], "plain", (160, 30, 30), "Jaguar")
S("atarijaguarcd", "Atari Jaguar CD", 77, "Atari - Jaguar", ["ra:virtualjaguar"], [".chd", ".cue", ".cdi"], "", (160, 30, 30), "Jaguar CD")
S("atarist", "Atari ST", 36, "Atari - ST", ["ra:hatari"], [".st", ".msa", ".stx", ".dim", ".ipf", ".m3u", ".zip"], "", (100, 100, 100), "Atari ST")

# ---------------- Computers ----------------
S("c64", "Commodore 64", 30, "Commodore - 64", ["ra:vice_x64sc", "ra:vice_x64"], [".d64", ".t64", ".tap", ".prg", ".crt", ".g64", ".m3u", ".zip", ".7z"], "", (110, 100, 70), "C64")
S("c16", "Commodore 16 / Plus4", 0, "Commodore - Plus-4", ["ra:vice_xplus4"], [".prg", ".d64", ".tap", ".zip"], "", (110, 100, 70), "C16")
S("vic20", "Commodore VIC-20", 34, "Commodore - VIC-20", ["ra:vice_xvic"], [".prg", ".d64", ".tap", ".crt", ".20", ".a0", ".zip"], "", (110, 100, 70), "VIC-20")
S(["amiga", "amiga600", "amiga1200"], "Commodore Amiga", 35, "Commodore - Amiga", ["ra:puae"], [".adf", ".adz", ".dms", ".ipf", ".hdf", ".lha", ".m3u", ".uae", ".zip"], "", (200, 90, 40), "Amiga")
S(["amigacd32", "cdtv"], "Amiga CD32", 0, "Commodore - CD32", ["ra:puae"], [".chd", ".cue", ".iso", ".m3u"], "", (200, 90, 40), "CD32")
S(["amstradcpc", "gx4000"], "Amstrad CPC", 37, "Amstrad - CPC", ["ra:cap32"], [".dsk", ".sna", ".cdt", ".cpr", ".m3u", ".zip"], "", (60, 120, 60), "CPC")
S("zxspectrum", "ZX Spectrum", 59, "Sinclair - ZX Spectrum", ["ra:fuse"], [".tzx", ".tap", ".z80", ".sna", ".dsk", ".scl", ".trd", ".zip"], "", (40, 40, 40), "Spectrum")
S("zx81", "ZX81", 31, "Sinclair - ZX 81", ["ra:81"], [".p", ".tzx", ".t81", ".zip"], "", (40, 40, 40), "ZX81")
S(["apple2", "apple2gs"], "Apple II", 38, "", [], [".dsk", ".do", ".po", ".nib", ".woz", ".2mg", ".zip"], "", (90, 130, 60), "Apple II")
S("dos", "MS-DOS", 26, "DOS", ["ra:dosbox_pure"], [".zip", ".dosz", ".exe", ".com", ".bat", ".conf", ".iso", ".cue", ".m3u"], "", (40, 40, 40), "DOS")
S("x68000", "Sharp X68000", 52, "Sharp - X68000", ["ra:px68k"], [".dim", ".xdf", ".hdf", ".2hd", ".m3u", ".zip"], "", (80, 80, 90), "X68000")
S("x1", "Sharp X1", 64, "Sharp - X1", ["ra:x1"], [".dx1", ".2d", ".2hd", ".tfd", ".d88", ".88d", ".hdm", ".xdf", ".dup", ".cmd", ".zip"], "", (80, 80, 90), "X1")
S("to8", "Thomson TO8", 66, "Thomson - MOTO", ["ra:theodore"], [".fd", ".sap", ".k7", ".m7", ".m5", ".rom", ".zip"], "", (80, 80, 90))
S("moto", "Thomson MO/TO", 0, "Thomson - MOTO", ["ra:theodore"], [".fd", ".sap", ".k7", ".m7", ".m5", ".rom", ".zip"], "", (80, 80, 90))
S("samcoupe", "SAM Coupé", 0, "", ["ra:simcp"], [".dsk", ".mgt", ".sbt", ".sad", ".zip"], "", (80, 80, 90))
S("fmtowns", "FM Towns", 58, "", [], [".chd", ".cue", ".iso", ".m3u"], "", (80, 80, 90))
S("scummvm", "ScummVM", 0, "ScummVM", ["ra:scummvm", "scummvm"], [".scummvm", ".svm"], "", (70, 120, 70), "ScummVM")

# ---------------- Other consoles & handhelds ----------------
S("3do", "3DO", 43, "The 3DO Company - 3DO", ["ra:opera"], [".chd", ".cue", ".iso", ".m3u"], "", (150, 30, 30), "3DO")
S("cdimono1", "Philips CD-i", 42, "Philips - CD-i", ["ra:same_cdi"], [".chd", ".cue", ".iso"], "", (60, 60, 120), "CD-i")
S(["ngp"], "Neo Geo Pocket", 14, "SNK - Neo Geo Pocket", ["ra:mednafen_ngp"], [".ngp", ".zip", ".7z"], "plain", (60, 60, 80), "NGP")
S(["ngpc"], "Neo Geo Pocket Color", 14, "SNK - Neo Geo Pocket Color", ["ra:mednafen_ngp"], [".ngc", ".ngp", ".zip", ".7z"], "plain", (60, 60, 80), "NGPC")
S("wonderswan", "WonderSwan", 53, "Bandai - WonderSwan", ["ra:mednafen_wswan"], [".ws", ".zip", ".7z"], "plain", (90, 90, 110), "WonderSwan")
S("wonderswancolor", "WonderSwan Color", 53, "Bandai - WonderSwan Color", ["ra:mednafen_wswan"], [".wsc", ".ws", ".zip", ".7z"], "plain", (90, 90, 110), "WSC")
S("colecovision", "ColecoVision", 44, "Coleco - ColecoVision", ["ra:gearcoleco", "ra:bluemsx"], [".col", ".rom", ".bin", ".zip", ".7z"], "plain", (60, 60, 60), "Coleco")
S("intellivision", "Intellivision", 45, "Mattel - Intellivision", ["ra:freeintv"], [".int", ".bin", ".rom", ".zip", ".7z"], "plain", (120, 90, 50), "Intellivision")
S("vectrex", "Vectrex", 46, "GCE - Vectrex", ["ra:vecx"], [".vec", ".gam", ".bin", ".zip", ".7z"], "plain", (40, 40, 40), "Vectrex")
S(["odyssey2", "videopac"], "Magnavox Odyssey²", 23, "Magnavox - Odyssey2", ["ra:o2em"], [".bin", ".zip", ".7z"], "plain", (60, 60, 60), "Odyssey²")
S("channelf", "Fairchild Channel F", 57, "Fairchild - Channel F", ["ra:freechaf"], [".bin", ".chf", ".zip"], "plain", (120, 90, 50), "Channel F")
S("arcadia", "Emerson Arcadia 2001", 73, "Emerson - Arcadia 2001", ["ra:mame"], [".bin", ".zip"], "plain", (80, 80, 80))
S("supervision", "Watara Supervision", 63, "Watara - Supervision", ["ra:potator"], [".sv", ".bin", ".zip"], "plain", (80, 80, 80), "Supervision")
S("megaduck", "Mega Duck", 69, "Welback - Mega Duck", ["ra:sameduck"], [".bin", ".zip"], "plain", (80, 80, 80), "Mega Duck")
S("crvision", "VTech CreatiVision", 0, "VTech - CreatiVision", ["ra:mame"], [".bin", ".rom", ".zip"], "", (80, 80, 80))
S("vsmile", "VTech V.Smile", 0, "VTech - V.Smile", ["ra:mame"], [".bin", ".zip"], "", (80, 80, 80))
S("gamecom", "Tiger Game.com", 0, "Tiger - Game.com", ["ra:mame"], [".bin", ".tgc", ".zip"], "", (80, 80, 80))
S("pv1000", "Casio PV-1000", 0, "Casio - PV-1000", ["ra:mame"], [".bin", ".zip"], "", (80, 80, 80))
S("arduboy", "Arduboy", 71, "Arduboy Inc - Arduboy", ["ra:arduous"], [".hex", ".zip"], "plain", (40, 40, 40))
S("uzebox", "Uzebox", 80, "Uzebox", ["ra:uzem"], [".uze"], "plain", (40, 40, 40))
S("wasm4", "WASM-4", 72, "WASM-4", ["ra:wasm4"], [".wasm"], "plain", (40, 40, 40))
S("tic80", "TIC-80", 65, "TIC-80", ["ra:tic80"], [".tic"], "plain", (40, 40, 40))
S("pico8", "PICO-8", 0, "", ["ra:retro8"], [".p8", ".png"], "", (40, 40, 40), "PICO-8")
S("chailove", "ChaiLove", 0, "ChaiLove", ["ra:chailove"], [".chai", ".chailove"], "", (40, 40, 40))
S("lutro", "Lutro", 0, "Lutro", ["ra:lutro"], [".lutro", ".lua"], "", (40, 40, 40))
S("easyrpg", "EasyRPG", 0, "", ["ra:easyrpg"], [".easyrpg", ".ldb", ".zip"], "", (40, 40, 40))
S("openbor", "OpenBOR", 0, "", [], [".pak"], "", (40, 40, 40))
S("solarus", "Solarus", 0, "", [], [".solarus"], "", (40, 40, 40))
S("cavestory", "Cave Story", 0, "", ["ra:nxengine"], [".exe"], "", (60, 40, 30))
S("doom", "DOOM", 0, "DOOM", ["ra:prboom"], [".wad", ".iwad", ".pwad"], "", (120, 30, 30), "DOOM")
S("quake", "Quake", 0, "", ["ra:tyrquake"], [".pak"], "", (90, 60, 40))
S("ports", "Ports", 0, "", ["native"], [".sh", ".exe", ".bat", ".lnk", ".url", ".desktop"], "", (60, 60, 60))
S("pc", "PC", 0, "", ["native"], [".sh", ".exe", ".bat", ".lnk", ".url", ".desktop"], "", (60, 60, 60))

BY_FOLDER = {s.folder: s for s in _TABLE}


def get_system(folder: str) -> System:
    """Return the System for a folder; unknown folders get a generic entry."""
    key = folder.lower()
    if key in BY_FOLDER:
        return BY_FOLDER[key]
    return System(key, folder, 0, "", [], None, "", (70, 70, 80), folder)


ALL_FOLDERS = list(BY_FOLDER.keys())
