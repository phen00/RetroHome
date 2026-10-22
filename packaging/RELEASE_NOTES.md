# RetroHome 1.0.0

A console-style home screen for your emulated games: your EmuDeck library with box art and
screenshots, one-press launching, RetroAchievements tracking with levels, crests and Platinum /
Mythic awards, a post-game report, multiple users, and a RetroAchievements Library with a
built-in browser that files downloads into the right folder.

## Install

**Windows** – unzip `RetroHome-1.0.0-Windows-x64` anywhere and run `RetroHome\RetroHome.exe`.
(Windows may show "Windows protected your PC" because the app isn't code-signed:
click *More info → Run anyway*.)

**Steam Deck** – in Desktop Mode, extract `RetroHome-1.0.0-Linux-SteamDeck-x86_64.tar.gz`
(right-click → Extract), open the `RetroHome` folder, right-click `install-steamdeck.sh` →
*Run In Konsole*, then add **RetroHome** to Steam as a Non-Steam Game (the script explains how).

On first launch it asks for your ROM folder (EmuDeck's `Emulation/roms` is found automatically)
and your RetroAchievements username + Web API key.

## Where things are kept

* Settings and users: `%APPDATA%\RetroHome` (Windows), `~/.config/retrohome` (Linux)
* Picture and achievement caches: `%LOCALAPPDATA%\RetroHome\cache`, `~/.cache/retrohome`
* Log file (release builds): `retrohome.log` in the settings folder
