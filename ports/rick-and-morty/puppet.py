"""Posable Rick and Morty, built from Schwifty Jam's own body grids.

Schwifty Jam only draws walk cycles. Here the head and torso come straight from its grids
(arms removed), and arms and legs are drawn per pose: raised arms for falling,
windmilling arms for teetering, spinning "wheel" legs for running, and so on. Then the
same rim-light and selective-outline passes as pix.js, so new frames match the old ones.

    render("rick", "side", arms=(160,), legs=Legs("wheel", phase=2), lean=0.3)
"""
import math
from dataclasses import dataclass, field

from PIL import Image

import rmsprites

RAW = rmsprites.load_raw()
PAL, OUT = RAW["PAL"], RAW["OUT"]


def _rgb(h):
    return tuple(int(h[k:k + 2], 16) for k in (1, 3, 5))


def _mix(a, b, t):
    A, B = _rgb(a), _rgb(b)
    return "#%02x%02x%02x" % tuple(round(x + (y - x) * t) for x, y in zip(A, B))


# Where things are in each grid (columns/rows as authored in pix.js).
SPEC = {
    "rick": {
        "grid": RAW["RICK"], "legs": RAW["RICK"]["legs"],
        "sleeve": ("c", "C"), "hand": "s", "arm_len": 6, "arm_w": 2,
        "down": {"torso": (14, 20), "arm_cols": (0, 1, 13, 14), "shoulders": ((1, 15), (13, 15))},
        "up": {"torso": (14, 20), "arm_cols": (0, 1, 13, 14), "shoulders": ((1, 15), (13, 15))},
        # side view: the near arm is the darker coat column; paint it over with coat
        "side": {"erase": {(6, y): "c" for y in range(16, 21)} | {(7, 20): "c"}, "shoulder": (6, 15)},
        "mouth": (7, 10), "eyes": ((5, 6), (9, 6)), "side_mouth": (11, 10), "side_eyes": ((8, 6), (12, 6)),
    },
    "morty": {
        "grid": RAW["MORTY"], "legs": RAW["MORTY"]["legs"],
        "sleeve": ("y", "Y"), "hand": "s", "arm_len": 5, "arm_w": 2,
        "down": {"torso": (14, 18), "arm_cols": (0, 12), "shoulders": ((0, 14), (12, 14))},
        "up": {"torso": (14, 18), "arm_cols": (0, 12), "shoulders": ((0, 14), (12, 14))},
        "side": {"erase": {(6, 15): "y", (6, 16): "y", (6, 17): "y", (7, 17): "y"}, "shoulder": (6, 14)},
        "mouth": (6, 10), "eyes": ((3, 7), (9, 7)), "side_mouth": (8, 10), "side_eyes": ((8, 7), (12, 7)),
    },
}


@dataclass
class Legs:
    mode: str = "stand"   # stand | walk | spread | crouch | dangle | tuck | wheel | blur
    phase: int = 0        # animation step for walk/wheel/blur
    spread: float = 0.0   # extra outward slant for spread/dangle


@dataclass
class Face:
    mouth: str = None     # "open" (O), "grit" (teeth), None = as drawn
    eyes: str = None      # "shut", "wide", None


class _Canvas:
    def __init__(self):
        self.px = {}

    def put(self, x, y, c):
        self.px[(x, y)] = c

    def rect(self, x, y, w, h, c):
        for j in range(h):
            for i in range(w):
                self.put(x + i, y + j, c)

    def limb(self, x0, y0, angle, length, width, color, shade, tip=None, tip_size=2, side=1):
        """A straight limb from (x0, y0). angle: 0 = down, 90 = outward (side=-1 is left)."""
        a = math.radians(angle)
        dx, dy = math.sin(a) * side, math.cos(a)
        ex = ey = 0
        for t in range(length + 1):
            x, y = round(x0 + dx * t), round(y0 + dy * t)
            for k in range(width):
                # thicken across the limb direction
                ox, oy = (k, 0) if abs(dy) >= abs(dx) else (0, k)
                self.put(x + ox, y + oy, shade if k == width - 1 else color)
            ex, ey = x, y
        if tip:
            self.rect(ex - (tip_size // 2 if abs(dx) < abs(dy) else 0), ey, tip_size, tip_size, tip)
        return ex, ey


def _rim(px, lift=0.14, drop=0.14):
    out = dict(px)
    for (x, y), c in px.items():
        if (x, y - 1) not in px or (x - 1, y) not in px:
            out[(x, y)] = _mix(c, "#ffffff", lift)
        elif (x, y + 1) not in px or (x + 1, y) not in px:
            out[(x, y)] = _mix(c, "#1a1030", drop)
    return out


def _outline(px):
    out = dict(px)
    xs = [x for x, _ in px]
    ys = [y for _, y in px]
    for y in range(min(ys) - 1, max(ys) + 2):
        for x in range(min(xs) - 1, max(xs) + 2):
            if (x, y) in px:
                continue
            n = [px.get(p) for p in ((x, y - 1), (x - 1, y), (x + 1, y), (x, y + 1))]
            n = [c for c in n if c]
            if not n:
                continue
            below = (x, y - 1) in px and (x, y + 1) not in px
            out[(x, y)] = OUT if below else _mix(n[0], OUT, 0.72)
    return out


def _to_art(px, foot_x):
    xs = [x for x, _ in px]
    ys = [y for _, y in px]
    x0, y0 = min(xs), min(ys)
    img = Image.new("RGBA", (max(xs) - x0 + 1, max(ys) - y0 + 1))
    for (x, y), c in px.items():
        img.putpixel((x - x0, y - y0), _rgb(c) + (255,))
    import fx
    return fx.Art(img, foot_x - x0, max(ys) - y0)


def render(who, view, arms=None, legs=Legs(), face=Face(), bob=0, lean=0.0, squash=1.0, prop=None):
    """One posed frame as an fx.Art (feet anchor).

    arms: None keeps the drawn arms; else angles in degrees (0 = hanging, 90 = out,
    180 = straight up). down/up views take (left, right); side takes (near,) or (near, far).
    """
    spec = SPEC[who]
    grid_key = "side" if view == "side" else view
    rows = spec["grid"][grid_key]
    L = spec["legs"]
    v = spec[grid_key]
    pc, ps = PAL[L["pants"][0]], PAL[L["pants"][1]]
    shoe = PAL[L["shoe"]]
    sleeve, sleeve_shade = PAL[spec["sleeve"][0]], PAL[spec["sleeve"][1]]
    hand = PAL[spec["hand"]]
    body_h = len(rows)
    hip = body_h + bob
    cv = _Canvas()

    # legs first (behind the body)
    lw, ln = L["lw"], L["len"]
    if view != "side":
        for i, lx in enumerate(L["front"]):
            side = -1 if i == 0 else 1
            if legs.mode in ("stand", "walk"):
                lift = 2 if legs.mode == "walk" and ((legs.phase % 4 == 1 and i == 0) or (legs.phase % 4 == 3 and i == 1)) else 0
                length = ln - lift + (0 if bob else 1)
                cv.rect(lx, hip, lw, length, pc)
                cv.rect(lx + lw - 1, hip, 1, length, ps)
                cv.rect(lx + (-1 if i == 0 else 0), hip + length, lw + 1, 1, shoe)
            elif legs.mode in ("spread", "dangle", "crouch", "tuck"):
                slant = {"spread": 0.9, "dangle": 0.35, "crouch": 0.6, "tuck": 0.2}[legs.mode] + legs.spread
                length = {"spread": ln + 1, "dangle": ln + 2, "crouch": max(2, ln - 1), "tuck": max(1, ln - 2)}[legs.mode]
                for r in range(length):
                    off = round(side * r * slant)
                    cv.rect(lx + off, hip + r, lw, 1, pc)
                    cv.put(lx + off + lw - 1, hip + r, ps)
                off = round(side * length * slant)
                if legs.mode == "dangle":
                    cv.rect(lx + off, hip + length, lw, 1, shoe)  # toes pointing down
                else:
                    cv.rect(lx + off + (-1 if i == 0 else 0), hip + length, lw + 1, 1, shoe)
            elif legs.mode == "blur":
                # legs pumping too fast to see: ghost positions, then the current one
                for k in range(3):
                    lift = (legs.phase + k + i * 2) % 4
                    ghost = _mix(pc, "#ffffff", 0.45)
                    cv.rect(lx, hip, lw, max(1, ln + 1 - lift), ghost)
                lift = (legs.phase + i * 2) % 4
                cv.rect(lx, hip, lw, ln + 1 - lift, pc)
                cv.rect(lx + lw - 1, hip, 1, ln + 1 - lift, ps)
                cv.rect(lx + (-1 if i == 0 else 0), hip + ln + 1 - lift, lw + 1, 1, shoe)
    else:
        hx = L["side"]
        if legs.mode == "wheel":
            # cartoon running: feet whirling in a blur under the hips, two legs caught mid-spin
            radius = ln + 3
            blur = _mix(shoe, "#ffffff", 0.5) if shoe != PAL["W"] else _mix(shoe, pc, 0.35)
            cy = hip + 2  # the whirl's centre sits a little below the hips
            for k in range(10):
                a = math.radians(k * 36 + legs.phase * 18)
                cv.rect(hx + 1 + round(math.sin(a) * radius), cy + round(math.cos(a) * radius * 0.8), 2, 1, blur)
            for j, col in ((0, ps), (1, pc)):
                ang = legs.phase * 45 + 22 + j * 180  # never dead horizontal
                a = math.radians(ang)
                fx_, fy = hx + 1 + round(math.sin(a) * radius), cy + round(math.cos(a) * radius * 0.8)
                # thigh from the hip to the foot on the whirl
                steps = max(abs(fx_ - hx - 1), abs(fy - hip)) or 1
                for t in range(steps + 1):
                    x = round(hx + 1 + (fx_ - hx - 1) * t / steps)
                    y = round(hip + (fy - hip) * t / steps)
                    cv.rect(x, y, 2, 1, col)
                cv.rect(fx_ - 1, fy, 3, 2, shoe)
        else:
            swing = {"stand": 0, "walk": (25, 0, -25, 0)[legs.phase % 4], "spread": 30, "dangle": 12,
                     "crouch": 35, "tuck": 50}.get(legs.mode, 0) + legs.spread * 30
            length = {"crouch": max(2, ln), "tuck": max(2, ln - 1), "dangle": ln + 2}.get(legs.mode, ln + 1)
            for sgn, col in ((-1, ps), (1, pc)):
                cv.limb(hx + 1, hip, sgn * swing, length, lw - 1, col, ps, tip=shoe, side=1)

    # head and torso from the grid, arms removed when we redraw them
    erase = set()
    paint = {}
    if arms is not None:
        if view != "side":
            t0, t1 = v["torso"]
            erase = {(c, r) for c in v["arm_cols"] for r in range(t0, t1 + 1)}
        else:
            paint = v["erase"]
    for y, row in enumerate(rows):
        for x, ch in enumerate(row):
            if ch in ". " or (x, y) in erase:
                continue
            ch = paint.get((x, y), ch)
            cv.put(x, y + bob, PAL.get(ch, "#ff00ff"))

    # face tweaks
    if face.mouth == "open":
        mx, my = spec["side_mouth"] if view == "side" else spec["mouth"]
        if view != "up":
            cv.rect(mx - 1, my + bob, 3, 2, PAL["m"])
            cv.put(mx, my + bob + 1, OUT)
    if face.eyes == "shut" and view != "up":
        eyes = spec["side_eyes"] if view == "side" else spec["eyes"]
        for ex, ey in eyes:
            cv.rect(ex - 1, ey + bob, 3, 2, PAL["s"])
            cv.rect(ex - 1, ey + bob + 1, 3, 1, OUT)

    # arms on top
    if arms is not None:
        aw, al = spec["arm_w"], spec["arm_len"]
        if view != "side":
            angles = arms if len(arms) == 2 else (arms[0], arms[0])
            for i, (sx, sy) in enumerate(v["shoulders"]):
                side = -1 if i == 0 else 1
                cv.limb(sx - (aw - 1 if side < 0 else 0), sy + bob, angles[i], al, aw, sleeve, sleeve_shade,
                        tip=hand, side=side)
        else:
            sx, sy = v["shoulder"]
            if len(arms) > 1:  # far arm, behind-ish and darker
                cv.limb(sx - 1, sy + bob, arms[1], al, aw, sleeve_shade, sleeve_shade, tip=hand, side=1)
            cv.limb(sx, sy + bob, arms[0], al, aw, sleeve, sleeve_shade, tip=hand, side=1)

    if prop == "book" and view != "up":
        bx = (L["front"][0] + L["front"][1]) // 2 - 1 if view != "side" else v["shoulder"][0] + 4
        by = body_h - 9 + bob
        cv.rect(bx, by, 7, 5, PAL["R"])          # red cover
        cv.rect(bx + 1, by + 1, 5, 3, PAL["W"])  # pages
    elif prop == "flask" and view != "up":
        fx_, fy = (spec["mouth"][0] + 3, spec["mouth"][1] + 1) if view != "side" else (spec["side_mouth"][0] + 2, spec["side_mouth"][1])
        cv.rect(fx_, fy + bob, 3, 4, PAL["x"])
        cv.put(fx_ + 1, fy + bob - 1, PAL["X"])
    px = cv.px
    if lean:
        # lean by shearing: rows above the hips slide sideways
        px = {(x + round((hip - y) * lean), y) if y < hip else (x, y): c for (x, y), c in px.items()}
    if squash != 1.0:
        top = min(y for _, y in px)
        bottom = max(y for _, y in px)
        px = {(x, bottom - round((bottom - y) * squash)): c for (x, y), c in sorted(px.items(), key=lambda kv: kv[0][1])}
    px = _outline(_rim(px))
    foot_x = (L["front"][0] + L["front"][1] + L["lw"]) // 2 if view != "side" else L["side"] + 1
    return _to_art(px, foot_x)
