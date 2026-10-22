"""RetroHome levels, prestige styles and game awards.

XP is built from your RetroAchievements record so it can't be farmed locally:

  * every hardcore point            x10
  * every softcore point            x4
  * rarity bonus: RetroPoints above the plain points (RA's "True Ratio", which rises
    the fewer players own an achievement)                                    x6
  * per-game awards, scaled by the size of the set:
      Mythic   (100% in hardcore)    1500 + 60 per achievement
      Platinum (100% in softcore)     600 + 25 per achievement
      Beaten   (hardcore)             300 + 10 per achievement
      Beaten   (softcore)             120 +  4 per achievement

Level curve: total XP to reach level L is  10 * (L - 1) ** 1.9  (rounded). Early levels fly
by (a single 10-point hardcore achievement is ~100 XP, several levels at the start); each level
costs a little more than the last, forever. Roughly: a few thousand points -> level 100+,
~30k points -> 350, ~50k points -> 500, the top of RetroAchievements -> 2000+.

Badges: the level crest gets a new insignia every 5 levels, a new colour every 20 and a new
frame every 100 (see tier_style). Nothing resets - the number keeps climbing.
"""
from dataclasses import dataclass

LEVEL_EXP = 1.9
LEVEL_K = 10
CURVE_VERSION = 2     # bump when the curve changes so the jump isn't celebrated as a level-up
PRESTIGE_EVERY = 50

AWARD_MYTHIC = "mythic"
AWARD_PLATINUM = "platinum"
AWARD_BEATEN_HC = "beaten-hardcore"
AWARD_BEATEN = "beaten"

AWARD_INFO = {
    AWARD_MYTHIC: dict(name="Mythic", desc="Every achievement unlocked in hardcore", base=1500, per=60, rank=4,
                       color=(255, 92, 170), color2=(120, 210, 255)),
    AWARD_PLATINUM: dict(name="Platinum", desc="Every achievement unlocked", base=600, per=25, rank=3,
                         color=(210, 225, 240), color2=(140, 160, 190)),
    AWARD_BEATEN_HC: dict(name="Beaten", desc="Game beaten in hardcore", base=300, per=10, rank=2,
                          color=(240, 190, 60), color2=(170, 110, 30)),
    AWARD_BEATEN: dict(name="Beaten", desc="Game beaten", base=120, per=4, rank=1,
                       color=(200, 140, 80), color2=(120, 80, 40)),
}


def award_from_ra(kind: str, num_awarded=0, num_hc=0, total=0) -> str:
    """Map RetroAchievements award kinds (or raw counts) to a RetroHome award."""
    k = (kind or "").lower()
    if k == "mastered" or (total and num_hc >= total):
        return AWARD_MYTHIC
    if k == "completed" or (total and num_awarded >= total):
        return AWARD_PLATINUM
    if k == "beaten-hardcore":
        return AWARD_BEATEN_HC
    if k == "beaten-softcore":
        return AWARD_BEATEN
    return ""


def award_xp(award: str, set_size: int) -> int:
    info = AWARD_INFO.get(award)
    return info["base"] + info["per"] * max(0, int(set_size)) if info else 0


def xp_for_level(level: int) -> int:
    """Total XP needed to reach `level` (level 1 = 0 XP)."""
    return int(round(LEVEL_K * max(0, level - 1) ** LEVEL_EXP))


def level_for_xp(xp: int) -> int:
    lv = max(1, int((max(0, xp) / LEVEL_K) ** (1 / LEVEL_EXP)) + 1)
    while xp_for_level(lv + 1) <= xp:
        lv += 1
    while lv > 1 and xp_for_level(lv) > xp:
        lv -= 1
    return lv


@dataclass
class Progress:
    xp: int
    level: int
    into: int          # XP earned inside the current level
    need: int          # XP span of the current level
    breakdown: dict
    awards: dict       # award -> count

    @property
    def frac(self):
        return self.into / self.need if self.need else 0

    @property
    def prestige(self):
        return self.level // FRAME_EVERY


def compute(profile: dict, completion: list) -> Progress:
    p = profile or {}
    hc = int(p.get("TotalPoints") or 0)
    sc = int(p.get("TotalSoftcorePoints") or 0)
    true = int(p.get("TotalTruePoints") or 0)
    parts = {
        "Hardcore points": hc * 10,
        "Softcore points": sc * 4,
        "Rarity bonus": max(0, true - hc) * 6,
    }
    award_counts = {AWARD_MYTHIC: 0, AWARD_PLATINUM: 0, AWARD_BEATEN_HC: 0, AWARD_BEATEN: 0}
    award_xp_total = 0
    for c in completion or []:
        size = int(c.get("MaxPossible") or 0)
        a = award_from_ra(c.get("HighestAwardKind"), int(c.get("NumAwarded") or 0),
                          int(c.get("NumAwardedHardcore") or 0), size)
        if a:
            award_counts[a] += 1
            award_xp_total += award_xp(a, size)
    parts["Game awards"] = award_xp_total
    xp = sum(parts.values())
    lv = level_for_xp(xp)
    base = xp_for_level(lv)
    return Progress(xp, lv, xp - base, xp_for_level(lv + 1) - base, parts, award_counts)


# ---------------------------------------------------------------- badge styles
# A level badge is a crest built from three parts that upgrade at different speeds:
#   insignia  every  5 levels: one chevron, two, three, then a star
#   colour    every 20 levels: steel, emerald, sapphire, amethyst, amber (then repeats)
#   frame     every 100 levels: plain shield, side fins, lower blades, small wings, great wings,
#             then a numbered crest gem (I, II, III...) on top, laurels from level 1000
STEP_EVERY = 5
COLOUR_EVERY = 20
FRAME_EVERY = 100

# (fill top, fill bottom, rim, number, accent)
PALETTE = [
    ((160, 170, 190), (58, 64, 80), (210, 216, 230), (240, 244, 252), (230, 236, 250)),   # steel
    ((80, 215, 145), (14, 98, 62), (150, 245, 195), (235, 255, 245), (190, 255, 220)),    # emerald
    ((80, 160, 255), (18, 50, 150), (160, 210, 255), (235, 245, 255), (200, 230, 255)),   # sapphire
    ((195, 115, 255), (78, 28, 150), (228, 185, 255), (250, 240, 255), (240, 210, 255)),  # amethyst
    ((255, 185, 60), (168, 88, 10), (255, 230, 150), (255, 248, 230), (255, 240, 190)),   # amber
]
COLOUR_NAMES = ["Steel", "Emerald", "Sapphire", "Amethyst", "Amber"]
FRAME_NAMES = ["Shield", "Finned", "Bladed", "Winged", "Great Wings"]
GEM_COLOURS = [(120, 235, 120), (90, 225, 255), (205, 125, 255), (255, 165, 60), (255, 85, 95)]
INSIGNIA_NAMES = ["One chevron", "Two chevrons", "Three chevrons", "Star"]

PRESTIGE_EVERY = COLOUR_EVERY   # a "new look" happens at least this often


def roman(n: int) -> str:
    out = ""
    for v, sym in ((1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"), (90, "XC"), (50, "L"),
                   (40, "XL"), (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")):
        while n >= v:
            out += sym
            n -= v
    return out


def tier_style(level: int) -> dict:
    level = max(1, int(level))
    colour = (level // COLOUR_EVERY) % len(PALETTE)
    era = level // FRAME_EVERY
    step = (level % COLOUR_EVERY) // STEP_EVERY
    gem = era - 4 if era >= 5 else 0
    return dict(level=level, colour=colour, era=era, step=step, gem=gem,
                gem_colour=GEM_COLOURS[(gem - 1) % len(GEM_COLOURS)] if gem else None,
                frame=min(era, 4), laurel=era >= 10, colors=PALETTE[colour],
                tier=level // COLOUR_EVERY, prismatic=False, stars=0)


def style_name(level: int) -> str:
    st = tier_style(level)
    name = f"{COLOUR_NAMES[st['colour']]} {FRAME_NAMES[st['frame']]}"
    return name + (f" {roman(st['gem'])}" if st["gem"] else "")


def badge_change(old: int, new: int) -> str:
    """What visibly changed between two levels' badges ('' if nothing)."""
    a, b = tier_style(old), tier_style(new)
    if b["era"] != a["era"]:
        return "frame"
    if b["colour"] != a["colour"]:
        return "colour"
    if b["step"] != a["step"]:
        return "insignia"
    return ""


def achievement_xp(points: int, true_ratio: int, hardcore: bool) -> int:
    """XP one unlocked achievement is worth (same weights as compute())."""
    points, true_ratio = int(points or 0), int(true_ratio or 0)
    if hardcore:
        return points * 10 + max(0, true_ratio - points) * 6
    return points * 4
