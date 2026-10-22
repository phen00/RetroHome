"""Controller families and the names printed on their buttons.

Actions use Xbox-style positions (a = bottom face button, b = right, x = left, y = top,
start = the right-hand centre button, select = the left-hand one, guide = home/PS button).
"""

FAMILIES = ("xbox", "xbox360", "playstation", "ps5", "nintendo", "stadia", "steam")


def family_from_name(name: str) -> str:
    n = (name or "").lower()
    if any(k in n for k in ("dualsense", "ps5", "playstation 5")):
        return "ps5"
    if "xbox" in n or "xinput" in n or "x-box" in n:
        return "xbox360" if "360" in n else "xbox"
    if any(k in n for k in ("ps4", "ps3", "dualshock", "playstation", "sony")) or n.strip() == "wireless controller":
        return "playstation"     # a PS4 pad on its own often reports just "Wireless Controller"
    if "stadia" in n:
        return "stadia"
    if any(k in n for k in ("nintendo", "switch", "pro controller", "joy-con", "joycon")):
        return "nintendo"
    if "360" in n:
        return "xbox360"
    if any(k in n for k in ("steam deck", "steam controller", "valve")):
        return "steam"
    return "xbox"   # Xbox One / Series and anything unknown (XInput)


# label for each action, per family. Face buttons on PlayStation are drawn as shapes.
LABELS = {
    "xbox": dict(a="A", b="B", x="X", y="Y", lb="LB", rb="RB", start="Start", select="View"),
    "xbox360": dict(a="A", b="B", x="X", y="Y", lb="LB", rb="RB", start="Start", select="Back"),
    "playstation": dict(a="cross", b="circle", x="square", y="triangle", lb="L1", rb="R1", start="Options",
                        select="Share"),
    "ps5": dict(a="cross", b="circle", x="square", y="triangle", lb="L1", rb="R1", start="Options",
                select="Create"),
    "nintendo": dict(a="B", b="A", x="Y", y="X", lb="L", rb="R", start="+", select="−"),
    "stadia": dict(a="A", b="B", x="X", y="Y", lb="L1", rb="R1", start="Menu", select="Options"),
    "steam": dict(a="A", b="B", x="X", y="Y", lb="L1", rb="R1", start="Menu", select="View"),
}

# colours for round face-button glyphs
FACE_COLORS = {
    "letters": {"a": (80, 200, 120), "b": (230, 90, 90), "x": (80, 150, 240), "y": (240, 200, 70)},
    "nintendo": {"a": (200, 200, 210), "b": (200, 200, 210), "x": (200, 200, 210), "y": (200, 200, 210)},
    "shapes": {"cross": (124, 178, 232), "circle": (255, 102, 102), "square": (255, 105, 248),
               "triangle": (64, 226, 160)},
}


def label(family: str, action: str) -> str:
    return LABELS.get(family, LABELS["xbox"]).get(action, action.upper())


def text_label(family: str, action: str) -> str:
    """Plain-text name, for places that can't draw shapes (e.g. the browser's hint bar)."""
    lab = label(family, action)
    return {"cross": "✕", "circle": "○", "square": "□", "triangle": "△"}.get(lab, lab)
