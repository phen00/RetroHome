# RetroHome – full guide

A console-style home screen for your emulated games. It reads an EmuDeck-style `Emulation/roms`
folder, shows your games in a row with box art pulled from the internet, launches the right
emulator for each one, and has a RetroAchievements tracker built into the home screen.
Works with a gamepad (Steam Deck, Xbox, PlayStation, Switch Pro pads), a keyboard, or both.

## Release builds (exe / Steam Deck)

Ready-to-run builds need no Python on the player's machine. Two ways to make them:

**On your PC (Windows):** double-click `packaging\build_windows.bat`. It sets up a private build
environment, downloads what it needs and produces, in `dist\`:
`RetroHome\RetroHome.exe`, `RetroHome-<version>-Windows-x64.zip` and, if WinRAR is installed,
a `.rar` too. Python 3.12 from python.org is recommended for building (very new Pythons such as
3.15 may not be supported by PyInstaller yet; the script picks 3.12/3.13/3.11 automatically if
installed alongside).

**On the Steam Deck / Linux:** in Desktop Mode run `bash packaging/build_linux.sh` in Konsole →
`dist/RetroHome-<version>-Linux-SteamDeck-x86_64.tar.gz`, which contains `install-steamdeck.sh`.

**Automatically on GitHub:** push the project to a GitHub repository, then push a tag
(`git tag v1.0.0 && git push --tags`) or press *Run workflow* on the Actions tab. GitHub builds both
versions and attaches them to a Release (`.github/workflows/release.yml`).

Release builds include the RA Library browser, so they're large (~250 MB unpacked).
Each release's description is that version's section of `CHANGELOG.md` - add a `## x.y.z` section
before publishing a release.

## Run it (from source)

**Windows** – install Python 3.10+ from python.org (tick *Add to PATH*), then double-click
`RetroHome.bat`. The first run installs its one dependency (pygame-ce) into a `.venv` folder.

**Steam Deck** – copy the RetroHome folder somewhere (e.g. `~/Applications/RetroHome`), then in
Desktop Mode:
1. Right-click `RetroHome.sh` → Properties → Permissions → tick *Is executable*.
2. Double-click it once to finish setup (it installs pygame-ce; needs internet).
3. In Steam: *Games → Add a Non-Steam Game*, browse to `RetroHome.sh`, add it.
4. In Game Mode, open it from your library. Set its controller layout to *Gamepad* if Steam
   picks something else.

Any platform: `python -m pip install pygame-ce` then `python run.py`.

## First run

1. **ROM folder** – it finds existing `Emulation/roms` folders (internal storage, SD card, any
   drive letter on Windows). You can browse to another folder with the controller, or have it
   create a new one with EmuDeck's per-system sub-folders (`nes`, `snes`, `psx`, …).
2. **RetroAchievements** – enter your username and your **Web API key** (retroachievements.org →
   Settings → Keys). This is read-only and used for the tracker; you still sign in to
   RetroAchievements inside RetroArch / your emulators so they can actually unlock achievements.
   You can skip this and do it later in Settings.

## Users and accounts

At start-up RetroHome asks **Who's playing?** Each user has their own RetroAchievements link,
favourites, play history and level. Users can have a PIN (press **Y** on a user to rename,
set/remove a PIN or delete them). *Settings → Switch user* changes user without restarting.

**RetroHome Online** (optional) keeps a user's favourites, play history, level and awards in sync
across devices and puts them on a shared leaderboard. It needs a RetroHome server: run the
reference one in `server/` on any PC or a cheap VPS:

```
python3 server/retrohome_server.py --port 8787 --db retrohome.db
```

Then *Sign in online* on the user screen, enter the server address (`192.168.1.20:8787` on your
own network, or an `https://` address on the internet), and create an account. Plain `http://`
is only allowed for your own network; public servers must use HTTPS (put the reference server
behind Caddy or nginx). The API is documented in `server/API.md`, so a bigger server can replace
the reference one later without changing the app. Your RetroAchievements key never leaves the
device.

## Levels and awards

Your RetroHome level comes from your RetroAchievements record — points, how rare your
achievements are, and the games you beat or complete.

Your level shows as a **crest** that keeps evolving as you level up — new insignia, colours and
frames along the way (no spoilers here). Nothing resets.

Game awards, shown on tiles, the game info and the trophy case:

* **Mythic** – every achievement in hardcore (RetroAchievements "Mastered")
* **Platinum** – every achievement (softcore "Completed")
* **Beaten** – the game's beaten condition (hardcore or softcore)

Earning a Mythic/Platinum plays a celebration after the session report. Open your profile by moving right past the last tab on the home bar (your name is highlighted),
or from the RetroAchievements card (move down, press A). The overview shows your XP bar and
your most recently played games with their hours and achievements; *Played games* lists every
game RetroHome has timed; left/right or LB/RB switch
tabs, and A on a trophy opens that game's achievement list. In the achievement tracker, A opens
a game's achievement list (even for games not in your library) and X jumps to it in your library.

## Window size and sharpness

RetroHome draws everything at your screen's real resolution and fits the layout to its shape:
16:10 (Steam Deck), 16:9, ultrawide 21:9 and 4:3 all fill the screen with no black bars, and
text stays sharp on 1440p/4K. Drag the window edge, use **Ctrl +** / **Ctrl −**, or
*Settings → Window size* (A bigger, X smaller). F11 toggles fullscreen.

## After you play

Closing a game shows a **session report**: every achievement you unlocked (with its XP), the
points earned, your progress in that game, any new Platinum/Mythic award, and your XP bar
filling up — ticking through each level-up as it goes. Press A to skip the animation, A again
to continue.

## Controls

Button names on screen match your controller (Xbox, Xbox 360, PS4, PS5, Switch Pro, Stadia,
Steam Deck). The table uses Xbox positions: A = bottom button (✕ on PlayStation).


| Pad | Keyboard | Home screen |
|---|---|---|
| D-pad / left stick | Arrows / WASD | Move (hold to scroll fast) |
| A | Enter / Space | Play |
| B | Esc | Back |
| X | X | Favourite |
| Y | Y | Achievements for this game |
| LB / RB | Q / E | Previous / next category |
| Select / View / Back / Share / Create / − | Tab | Game Library grid |
| Start / Menu / Options / + | M / F1 | Settings |
| | F11 | Toggle fullscreen |

Move **up** to reach the category bar, **down** to reach the achievement tracker cards.

## How games are launched

RetroHome auto-detects EmuDeck's emulators:

* **Steam Deck / Linux** – EmuDeck's launcher scripts in `Emulation/tools/launchers/`, falling back
  to Flatpaks, AppImages in `~/Applications`, or anything on your PATH. RetroArch cores are found in
  the RetroArch Flatpak's `cores` folder.
* **Windows** – EmuDeck's `%USERPROFILE%\emudeck\EmulationStation-DE\Emulators\…` (older versions:
  `%APPDATA%\EmuDeck\Emulators\…`), and Program Files. If your emulators are somewhere else, pick the
  folder in *Settings → Emulators folder* for RetroArch, Dolphin, PCSX2,
  DuckStation, PPSSPP, RPCS3, Cemu, Ryujinx/Eden/Citron, xemu, Xenia, melonDS, Azahar, etc.

Each system uses EmuDeck's defaults (e.g. NES → RetroArch Mesen, PS1 → DuckStation, PS2 → PCSX2,
GameCube/Wii → Dolphin). To change anything, edit `emulators.json` (Settings → *Emulator setup*
shows the path and which systems are ready):

```json
{
  "retroarch": "C:/RetroArch/retroarch.exe",
  "retroarch_cores": "C:/RetroArch/cores",
  "systems": {
    "psx": "ra:pcsx_rearmed",
    "snes": ["C:/Emus/bsnes/bsnes.exe", "--fullscreen", "{rom}"]
  }
}
```

Placeholders: `{rom}` (full path), `{romname}` (file name without extension), `{romdir}`.

## Only games with achievements

When you're signed in to RetroAchievements, RetroHome shows only the games that have an
achievement set (matches are remembered, so they appear instantly on the next launch). Turn on
*Settings → Show games without achievements* to see everything, e.g. PS3 or Switch games.

## Multi-disc games

Games split into `(Disc 1)`, `(Disc 2)`… files show up once. Pressing Play asks which disc to
start, or **All discs**, which starts disc 1 with every disc loaded so you can swap from the
emulator's menu (RetroArch, DuckStation and most others support this). It remembers your last
choice. Games that already have an `.m3u` playlist work the same as before.

## RetroAchievements Library

The **RA Library** tab (second on the home bar when you're signed in to RetroAchievements) lists
every console RetroAchievements supports, then every game with achievements on it, marking the
ones already in your library and your progress. On a game: **A** opens it in RetroHome's browser,
**X** shows its achievements, **Y** filters (all / not in library / in library), left/right
jump between letters.

The browser opens on the game's RetroAchievements page; *Supported files* (or X on the pad)
shows the exact ROM versions that work with its achievements. Anything you download is
unpacked automatically (zip, 7z, rar, tar) and filed into the right `roms/<system>` folder —
disc images keep their tracks together in one sub-folder, and every disc of a game goes in the
same folder. Close the browser and your library rescans. Only download games you're entitled to
(your own dumps, homebrew, freeware).

The browser is an optional ~150–200 MB component (Qt WebEngine) installed the first time you
use it, or from Settings. It only uses prebuilt packages, so no compiler is needed. .7z and .rar
files are opened with 7-Zip if you have it, otherwise with the `tar` built into Windows 10/11 and
SteamOS (very new RAR5 archives may need 7-Zip on Windows). Gamepad: left stick moves the pointer, A clicks, right stick/D-pad scroll, LB/RB back and
forward, Y address bar (opens the Steam keyboard on the Deck), **Start** (Options on PlayStation) or the
Home/PS button closes the browser.

## Box art and backgrounds

While you browse, the background slowly rotates through screenshots and title screens of the
selected game (from libretro-thumbnails, RetroAchievements, and any media you scraped with
ES-DE). Turn this off in Settings to get the blurred box art instead.

Box art is looked up in this order, then cached:
1. Media you already scraped with EmuDeck / ES-DE (`Emulation/tools/downloaded_media/<system>/covers`).
2. libretro-thumbnails by exact file name (works best with No-Intro / Redump names), then a fuzzy
   match against that system's thumbnail list.
3. RetroAchievements box art for games matched to an achievement set.

Games with no art get a generated tile. *Settings → Retry missing box art* tries again.

## Achievements

Games are matched to RetroAchievements by ROM hash (cartridge systems, plus PSP, PS2 and PS1
discs in .iso / .cso / .bin / .cue / .m3u / .pbp, using the same rules as RetroArch) or by title
(everything else, including .chd). Numbered file names like `2239 - Metal Gear Solid - Peace
Walker (Europe)` are handled. The home screen shows, for the selected game, your progress, points,
badges of what's next and the next achievement's description; plus tracker cards for your profile,
recently unlocked achievements and games you're partway through. Progress refreshes automatically
when you close a game.

## Files

* Settings: `%APPDATA%\RetroHome\config.json` or `~/.config/retrohome/config.json`
  (your RA key is stored here in plain text).
* Cache (art, RA game lists): `%LOCALAPPDATA%\RetroHome\cache` or `~/.cache/retrohome`.
* Steam Deck log: `retrohome.log` next to `RetroHome.sh`.
