# Changelog

## 1.0.14 — 2026-10-22
- Fixed games not starting on the Steam Deck ("The emulator closed straight away… exit code 127"):
  emulators were picking up libraries bundled with RetroHome instead of SteamOS's own
- When an emulator closes straight away, the message now includes what it printed, and its full
  output is saved to `emulator.log`

## 1.0.13 — 2026-10-22
- Fixed the built-in browser opening behind RetroHome in Steam Deck Desktop Mode: RetroHome now
  steps out of the way while the browser is open and comes back when it closes
- B on RetroHome's "Browser open" screen closes the browser, so it can't get stuck. If the browser
  hasn't appeared after a while, RetroHome says so
- Fixed the built-in browser crashing in Steam Deck Gaming Mode ("Could not initialize GLX",
  exit code -6, even in compatibility mode). The browser no longer inherits Steam's overlay, and
  if it still crashes RetroHome tries other graphics setups, down to fully software drawing, and
  remembers the one that works (separately for Gaming Mode and Desktop Mode)
- **Settings → Browser graphics** replaces "Browser compatibility mode": Automatic, or pick a setup

## 1.0.12 — 2026-10-22
- Fixed updates not installing on the Steam Deck when RetroHome is launched from Steam: the
  update now installs while RetroHome is still open and it restarts straight into the new version

## 1.0.11 — 2026-10-22
- Fixed the built-in browser crashing on the Steam Deck ("exit code -6"), which also stopped
  **Sign in with password** and the RA Library from working
- If the browser still crashes when it opens, RetroHome reopens it in compatibility mode (no GPU
  acceleration) and keeps using that. It can also be turned on in **Settings → Browser
  compatibility mode**
- **Settings → Browser for the RA Library** now opens a test page in release builds, and the error
  message shows where the browser's log is instead of suggesting a reinstall
- RetroHome now remembers windowed mode on the Steam Deck too

## 1.0.10 — 2026-10-22
- Fixed signing in, achievements, pictures and updates on the Steam Deck failing with
  "CERTIFICATE_VERIFY_FAILED"
- **Sign in with password:** opens retroachievements.org in the built-in browser; sign in there
  and RetroHome picks up your Web API key and signs you in, so you don't have to copy it
- Fixed achievements not loading again after switching RetroAchievements account until RetroHome
  was restarted

## 1.0.9 — 2026-10-22
- The XP bar along the bottom of the home screen is now always the same length
- Favourite and Achievements now sit next to the Play button; the bottom right only shows
  Library and Settings while a game is selected
- Removed the large cover picture on the right of the home screen and the level badge next to
  your name (your level is in the XP bar)

## 1.0.8 — 2026-10-22
- New row of cards on the home screen: **Continue hunting**, **New on RetroAchievements** (the
  newest achievement sets on the site; A shows a set's achievements, X gets the game or plays it if you
  have it) and **Friends** (who's playing; opens your friends list)
- Your level and XP now sit in a bar along the bottom of the home screen
- Smaller button prompts at the bottom right
- Fixed the achievement count overlapping the points on the home screen

## 1.0.7 — 2026-10-22
- **Friends:** a new Friends tab on your profile shows the people you follow on RetroAchievements
  and what they're playing right now (or last played). **Add a friend** opens their RA page so you
  can follow them. A on a friend opens their game's achievements, X plays it if you have it
- RetroHome tells you when a friend starts playing (turn off in **Settings → Friend notifications**)
- **Played games** now lists every game in your RetroAchievements history, not just the ones
  started from RetroHome, newest first. Hours are still counted for games started from RetroHome
- RetroHome now checks for updates every time it starts (it used to wait 6 hours between checks)

## 1.0.6 — 2026-10-22
- **Platinum is now the award for beating a game** (hardcore or softcore). The separate Beaten
  award is gone; games you'd already beaten count as Platinum
- Your profile's Overview now shows your RetroAchievements points, softcore points, RetroPoints,
  achievements unlocked and site rank

## 1.0.5 — 2026-10-22
- **Automatic updates:** RetroHome now checks GitHub for new versions at start-up, shows what's
  changed and can download and install the update itself (RetroHome restarts; settings and
  progress are kept). Check any time in **Settings → Check for updates**, or turn automatic checks
  off in Settings
- At most three notifications are shown at once

## 1.0.4 — 2026-10-22
- If an emulator's folder exists but the program is missing (for example when EmuDeck's RetroArch
  download didn't finish), RetroHome now says so and tells you to reinstall it in EmuDeck, instead
  of "Couldn't find…"

## 1.0.3 — 2026-10-22
- Emulators are now found through EmuDeck's own launcher scripts, so RetroHome launches games
  wherever EmuDeck installed them
- **Settings → Emulator setup** now lists every emulator found, which consoles can't launch yet
  and why, and where RetroHome looked

## 1.0.2 — 2026-10-22
- Fixed games not launching with recent EmuDeck versions on Windows ("Couldn't find RetroArch…"):
  RetroHome now finds emulators in EmuDeck's current install folder
- Added **Settings → Emulators folder** to choose the emulators folder by hand
- Start (Options on PlayStation, + on Switch) or the Home/PS button now closes the browser,
  including on controllers the browser couldn't read before
- Button prompts now match your controller: Xbox, Xbox 360, PS4, PS5, Switch Pro, Stadia and Steam Deck
- Improved controller support in the browser for PlayStation, Switch and Stadia controllers

## 1.0.1 — 2026-10-22
- Fixed the RA Library tab missing when you have no games yet; the empty home screen now has
  an **Open RA Library** button
- The RA Library tab now appears straight after signing in to RetroAchievements
- Clearer messages explaining that EmuDeck is required

## 1.0.0 — 2026-10-22
- First release
