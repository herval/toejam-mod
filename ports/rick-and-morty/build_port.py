#!/usr/bin/env python3
"""Rick & Morty port of ToeJam & Earl, using Schwifty Jam's sprites.

  node dump_sprites.mjs out/sprites.json     # once, or whenever vendor/schwifty-pix.js changes
  python3 build_port.py                      # -> build/rick-and-morty.md (+ .ips), copied to ../../web/

Steps: fresh extract of the original assets, new sprite palette, Schwifty Jam art
composited into the cast's animation sheets, then `tjmod build --requantize`
(everything still original keeps its look under the new palette).
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, ROOT)
import tjmod  # noqa: E402
import rmsprites  # noqa: E402
import fx  # noqa: E402
import hud  # noqa: E402
import title  # noqa: E402
import bigcast  # noqa: E402
import poses  # noqa: E402
import boot  # noqa: E402
import music  # noqa: E402
import script  # noqa: E402

ASSETS = os.path.join(HERE, "assets")
OUT = os.path.join(HERE, "build", "rick-and-morty.md")
WEB = os.path.join(ROOT, "web", "mod.md")  # local build for the web player (not committed)
WEB_PATCH = os.path.join(ROOT, "web", "patches", "rick-and-morty.ips")  # what the published player applies

# Sprite palette line 3 (PaletteDefault), shared by the players and most Earthlings.
# Keeps black/white/greys/reds/dark brown; trades oranges and pure blues for the R&M cast.
# Colors 14 and 15 are not colors at all: the game runs the VDP in shadow/highlight mode,
# where line 3 color 14 brightens and color 15 darkens whatever is underneath (that's how
# the see-through ground shadows work). They stay as they are, and characters never use them.
LINE3 = "098198"
LINE3_COLORS = [
    "#000000",  # 0  transparent
    "#60A040",  # 1  green: Gromflomites, Terry's stripes (was dark red)
    "#E00000",  # 2  red (kept)
    "#E0C0A0",  # 3  skin               (was light red)
    "#402000",  # 4  dark brown (kept)
    "#804020",  # 5  brown: Morty's hair, Rick's pants
    "#E0E040",  # 6  Morty yellow       (was orange)
    "#C0A080",  # 7  skin shade         (was Earl's orange skin)
    "#000000",  # 8  black: outlines (kept)
    "#404040",  # 9  dark grey (kept)
    "#A0A0A0",  # 10 grey: lab coat shade (kept)
    "#E0E0E0",  # 11 white (kept)
    "#A0E0E0",  # 12 Rick's hair, shirt (was navy)
    "#4080C0",  # 13 blue: Rick's hair shade, Morty's jeans (was pure blue)
    "#E0E0E0",  # 14 highlight operator (kept)
    "#000000",  # 15 shadow operator (kept)
]
SHADOW_INDEX = 3 * 16 + 15  # line 3, color 15: the shadow operator
# Colors each palette line may lend to new art: no shadow/highlight operators on line 3,
# and not line 1's 10-13, which the game cycles to animate water.
ALLOWED = {0: range(1, 16), 1: (1, 2, 3, 4, 5, 6, 7, 8, 9, 14, 15), 2: range(1, 16), 3: range(1, 14)}

# ToeJam's sheets get Morty, Earl's get Rick (matches Schwifty Jam: Morty quick, Rick tough;
# and the HUD name slots: MORTY in TOEJAM's 6 letters, RICK in EARL's 4).
CAST = {"Toejam": "morty", "Earl": "rick"}
SHADOW_W = {"morty": 16, "rick": 18, "cronen": 18, "grom": 12, "dog": 18, "terry": 14, "poopy": 12, "meeseeks": 10}
# Palette line each cast member is drawn with (players: line 3, which they share with most
# Earthlings). Hardware sprites switch to it automatically.
LINE_OF = {"morty": 3, "rick": 3, "cronen": 2, "grom": 3, "dog": 3, "terry": 3, "poopy": 3, "meeseeks": 3}
ANCHOR_X = 1  # the original sprites centre their feet/shadow about here


@dataclass
class Motion:
    facing: str = "down"     # which Schwifty Jam walk cycle: down / up / right
    frames: str = "still"    # "cycle" through the 4 walk frames, or hold the "still" standing frame
    fx: str = None           # a variation from fx.py
    pose: str = None         # a posed frame from poses.py instead of the walk cycle
    fit: str = "feet"        # "feet": stand on the shadow; "top": hang from the top of the box (innertube)
    keep_lines: tuple = ()   # palette lines whose pieces are props to keep (innertube, exhaust)
    keep_sheet: str = None   # ...or pieces whose data belongs to this sheet (the Zzz over a sleeper)
    drop_colors: tuple = ()  # colors removed from kept props (e.g. Earl's arms painted on the tube)
    crop_y: int = None       # hide the character this many rows below the top of the props (in the tube)
    shadow: bool = True



def dirs(name, **kw):
    """WalkDown/WalkUp/WalkRight-style triples."""
    return {name + d.capitalize(): Motion(facing=d, **kw) for d in ("down", "up", "right")}


# Order matters: a frame shared by several animations takes its art from the first one listed.
MOTIONS = {
    "Idle": Motion(),
    **dirs("Walk", frames="cycle"),
    **dirs("Sneak", frames="cycle", pose="sneak"),
    **dirs("Hitops", frames="cycle", pose="run"),
    **dirs("Lean", frames="cycle", pose="teeter"),
    **dirs("Pain", pose="pain"),
    **dirs("Land", pose="land"),
    **dirs("Fall", shadow=False, pose="fall"),
    **dirs("Leap", shadow=False, pose="leap"),
    **dirs("Dive", shadow=False, pose="dive"),
    **dirs("TomatoThrow", frames="cycle", pose="throw"),
    **dirs("SlingShot", pose="slingshot"),
    **dirs("SpringShoes", frames="cycle", fx="springs", shadow=False),
    **dirs("Wings", frames="cycle", fx="wings", shadow=False),
    **dirs("Innertube", fit="top", keep_lines=(2,), drop_colors=((128, 32, 0), (224, 96, 0)), crop_y=9,
           shadow=False),
    **dirs("RocketSkates", frames="cycle", fx="skates", keep_lines=(2,), shadow=False),
    **dirs("RocketSkatesHold", fx="skates", shadow=False),
    "Climb": Motion(facing="up", frames="cycle", shadow=False, pose="climb"),
    "Zap": Motion(fx="xray"),
    "Ghost": Motion(frames="cycle", fx="ghost", shadow=False),
    "Flattened": Motion(fx="flat"),
    "Sleep": Motion(fx="sleep"),
    "Snooze": Motion(fx="sleep"),  # napping on his back (resources-extra.cfg)
    "Hula": Motion(frames="cycle", pose="hula"),
    "DropPants": Motion(frames="cycle", pose="swig"),
    "TomatoRain": Motion(pose="shield"),
    "ExtraLife": Motion(pose="cheer"), "ExtraLive": Motion(pose="cheer"),
    "CoverEars": Motion(pose="covers"), "HighFive": Motion(frames="cycle", pose="highfive"), "Read": Motion(pose="read"),
    "DrinkLemonade": Motion(),
}
EXTRA = {
    "Spr_DecoyToejam": ("morty", Motion()), "Spr_DecoyEarl": ("rick", Motion()),
    # "Jam Out" mode and the ending
    "Spr_JamoutToejam": ("morty", Motion(frames="cycle")), "Spr_JamoutEarl": ("rick", Motion(frames="cycle")),
    "Spr_FunkotronToejamFootTap": ("morty", Motion(frames="cycle")), "Spr_FunkotronToejamIdle": ("morty", Motion()),
    "Spr_FunkotronEarlFootTap": ("rick", Motion(frames="cycle")), "Spr_FunkotronEarlIdle": ("rick", Motion()),
}
TUBE = MOTIONS["InnertubeDown"]                      # bobbing in the innertube
SNOOZE = Motion(fx="sleep", keep_sheet="Spr_SleepZzz")  # asleep on the ground, Zzz kept
SPLASH = Motion(keep_lines=(2,), shadow=False)          # hitting the water

# Earthlings -> Schwifty Jam creatures, matching roles in both games. Creatures only have
# side views, so every direction uses them.
WALK = Motion(facing="right", frames="cycle")
STILL = Motion(facing="right")
CREATURES = {
    "Devil": ("cronen", {"IdleBounce": WALK, "IdleHop": WALK, "MoveDown": WALK, "MoveUp": WALK,
                         "MoveRight": WALK, "Sleep": STILL}),
    "Dentist": ("grom", {"MoveDown": WALK, "MoveUp": WALK, "MoveRight": WALK, "StabUp": WALK,
                         "StabRight": WALK, "GloatRight": WALK, "Sleep": STILL}),
    "Shopper": ("dog", {"MoveUp": WALK, "MoveDown": WALK, "MoveRight": WALK, "ShoutRight": WALK,
                        "Idle": WALK, "Sleep": STILL}),
    "Boogieman": ("terry", {"HiddenWalkRight": Motion(facing="right", frames="cycle", fx="hidden", shadow=False),
                            "HiddenWalkUp": Motion(facing="right", frames="cycle", fx="hidden", shadow=False),
                            "BoogieRight": WALK, "BoogieDown": WALK, "BoogieUp": WALK, "Dance": WALK}),
    "Wiseman": ("poopy", {"Think": WALK, "WalkRight": WALK}),
    "Wahine": ("meeseeks", {"Move": WALK, "Idle": WALK}),  # the friendly hula dancer
}


def targets(sheets):
    for motion_name, motion in MOTIONS.items():
        for who, cast in CAST.items():
            sheet = "Spr_%s%s" % (who, motion_name)
            if sheet in sheets:
                yield sheet, cast, motion
    for sheet, (cast, motion) in EXTRA.items():
        yield sheet, cast, motion
    for who, (cast, motions) in CREATURES.items():
        for name, motion in motions.items():
            if "Spr_%s%s" % (who, name) in sheets:
                yield "Spr_%s%s" % (who, name), cast, motion


def piece_mask(frame, keep=lambda p: True):
    """Set of (x, y) frame coordinates covered by the hardware sprites `keep` selects."""
    cover = set()
    for p in frame.pieces:
        if keep(p):
            cover.update((x, y) for y in range(p.y, p.y + p.h * 8) for x in range(p.x, p.x + p.w * 8))
    return cover


def guess_cast(frame, lines):
    """ToeJam is red, Earl orange: decide who an unlabelled frame shows."""
    red = orange = 0
    for p in frame.pieces:
        if p.pal != 3:
            continue
        for row in p.pixels():
            for c in row:
                red += c in (1, 2, 3)
                orange += c in (4, 5, 6, 7, 12, 13)
    return "morty" if red > orange else "rick"


def place(art, mask, motion):
    """Where to draw `art`. The build re-lays out each frame's hardware sprites around the
    new art, so nothing has to squeeze into the original boxes any more."""
    xs = [x for x, _ in mask]
    ys = [y for _, y in mask]
    if motion.fit == "top":
        cx = ANCHOR_X if min(xs) <= ANCHOR_X <= max(xs) else (min(xs) + max(xs)) // 2
        top = min(y for x, y in mask if abs(x - cx) <= 4)
        return art.img, cx - art.ax, top, 0
    # Feet on the origin, where the game's own frames put them; inline copies drawn away
    # from their origin (intro, ending) go at the bottom middle of their old boxes instead.
    near = min(xs) - 8 <= ANCHOR_X <= max(xs) + 8 and min(ys) - 8 <= 0 <= max(ys) + 8
    ax0, ay0 = (ANCHOR_X, 0) if near else ((min(xs) + max(xs)) // 2, max(ys) - 2)
    return art.img, ax0 - art.ax, ay0 - art.ay, 0


def paste_clip(dst, src, x, y):
    """alpha_composite that tolerates sources hanging off the top/left edge."""
    left, top = max(0, -x), max(0, -y)
    if left >= src.width or top >= src.height:
        return
    dst.alpha_composite(src.crop((left, top, src.width, src.height)), (x + left, y + top))


def nearest_index(rgb, line, allowed=ALLOWED[3]):
    best, idx = None, allowed[0]
    for i in allowed:
        d = sum((a - b) ** 2 for a, b in zip(rgb, line[i]))
        if best is None or d < best:
            best, idx = d, i
    return idx


MARK = (255, 0, 255, 255)  # stands for "shadow" while compositing


def paint_sheet(path, frames, entry, plan, art_for, lines, old_line3, data_of):
    """Write an indexed sheet (index = line*16 + color) for these frames.

    Players only go on palette-line-3 pieces (the only line with their colors); kept props
    keep their exact original pixels underneath; everything else is cleared. Creatures use
    every piece, drawn in their own line (the pieces switch to it).
    """
    ox, oy = entry["origin"]
    cw, ch = entry["cell"]
    # Start from the extracted sheet so frames we don't paint stay as they were; its
    # line-3 pixels are remapped to the new palette explicitly (the sheet carries the new
    # colors, so an unchanged index would read as a deliberate pick).
    sheet = Image.open(path)
    spx = sheet.load()
    table = tjmod.remap_table(old_line3, lines[3])
    for y in range(sheet.height):
        for x in range(sheet.width):
            if spx[x, y] // 16 == 3:
                spx[x, y] = 48 + table[spx[x, y] % 16]
    sheet.putpalette([v for line in lines for rgb in line for v in rgb])
    clipped_total = 0
    for i, f in enumerate(frames):
        if f.addr not in plan:
            continue  # not ours to paint; leave the frame as it was
        for y in range(ch):
            for x in range(cw):
                spx[i * cw + x, y] = 0
        cast, motion, _ = plan[f.addr]
        art = art_for(f)
        line = LINE_OF[cast]
        kept = data_of.get(motion.keep_sheet, set())

        def is_prop(p):
            return p.pal in motion.keep_lines or p.data_addr in kept

        player = cast in CAST.values()
        body = piece_mask(f, lambda p: not is_prop(p) and (p.pal == 3 or not player))

        # props first: their own pixels, exact indices
        if motion.keep_lines or kept:
            for p in reversed(f.pieces):
                if not is_prop(p):
                    continue
                for yy, row in enumerate(p.pixels()):
                    for xx, c in enumerate(row):
                        cx, cy = p.x + xx + ox, p.y + yy + oy
                        if c and 0 <= cx < cw and 0 <= cy < ch and lines[p.pal][c] not in motion.drop_colors:
                            spx[i * cw + cx, cy] = p.pal * 16 + c

        if not body:
            continue  # nothing but props in this frame (e.g. a splash on its own)
        img, x, y, clipped = place(art, body, motion)
        clipped_total += clipped

        # sitting in something: hide the character below the props' top edge (+crop_y rows)
        crop_row = None
        if motion.crop_y is not None:
            centre = x + art.ax + ox
            tops = [cy for cy in range(ch) for cx in range(max(0, centre - 6), min(cw, centre + 7))
                    if spx[i * cw + cx, cy] % 16 and spx[i * cw + cx, cy] // 16 in motion.keep_lines]
            crop_row = (min(tops) if tops else oy) + motion.crop_y

        # then the character (and its shadow) on top
        char = Image.new("RGBA", (cw, ch))
        if motion.shadow:
            sw = SHADOW_W[cast]
            shadow = Image.new("RGBA", (sw, 5))
            ImageDraw.Draw(shadow).ellipse((0, 0, sw - 1, 4), fill=MARK)
            # under the feet, which may have moved to fit the boxes
            paste_clip(char, shadow, x + art.ax - sw // 2 + ox, y + img.height - 3 + oy)
        paste_clip(char, img, x + ox, y + oy)
        cpx = char.load()
        for cy in range(ch):
            for cx in range(cw):
                c = cpx[cx, cy]
                fx_, fy_ = cx - ox, cy - oy
                if c[3] < 128 or (crop_row is not None and cy > crop_row):
                    continue
                if c == MARK:
                    if line == 3:
                        spx[i * cw + cx, cy] = SHADOW_INDEX
                    elif (cx + cy) % 2 == 0:  # no shadow operator off line 3: dither in black
                        spx[i * cw + cx, cy] = line * 16 + nearest_index((0, 0, 0), lines[line], ALLOWED[line])
                else:
                    spx[i * cw + cx, cy] = line * 16 + nearest_index(c[:3], lines[line], ALLOWED[line])
    sheet.save(path)
    return clipped_total, [f.addr for f in frames if f.addr in plan]


def make_art(lib, cast, motion, index):
    if motion.pose and cast in ("rick", "morty"):
        base = poses.make(motion.pose, cast, motion.facing, index)
        if motion.fx in ("wings", "springs", "skates"):
            return getattr(fx, motion.fx)(base, index)
        return getattr(fx, motion.fx)(base) if motion.fx else base
    walk = lib[cast][motion.facing]
    if motion.fx == "hidden":
        return fx.hidden(fx.Art.of(walk[index % len(walk)]))
    base = fx.Art.of(walk[index % len(walk)] if motion.frames == "cycle" else walk[0])
    if motion.fx in ("wings", "springs", "skates"):
        return getattr(fx, motion.fx)(base, index)
    if motion.fx:
        return getattr(fx, motion.fx)(base)
    return base


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-web", action="store_true", help="don't copy the build to the web player (web/mod.md, web/patches/)")
    args = ap.parse_args()

    shutil.rmtree(ASSETS, ignore_errors=True)
    subprocess.run([sys.executable, os.path.join(ROOT, "tjmod.py"), "--assets", ASSETS, "extract"], check=True)

    pal_path = os.path.join(ASSETS, "palettes.json")
    pal = json.load(open(pal_path))
    pal[LINE3]["colors"] = LINE3_COLORS
    pal[bigcast.TITLE_LINE2]["colors"] = bigcast.TITLE_LINE2_COLORS
    pal[bigcast.TITLE_LINE3]["colors"] = bigcast.TITLE_LINE3_COLORS
    json.dump(pal, open(pal_path, "w"), indent=1)

    rom = tjmod.load_rom(tjmod.DEFAULT_ROM)
    cat = tjmod.Catalog(rom, tjmod.DEFAULT_CFG)
    new_line3 = [tuple(int(h[k:k + 2], 16) for k in (1, 3, 5)) for h in LINE3_COLORS]
    sheets = {name: (pal_name, frames) for name, pal_name, frames in cat.sheets}
    manifest = json.load(open(os.path.join(ASSETS, "manifest.json")))
    lib = rmsprites.load()

    # Who and what each frame shows. Some frames appear in several animations (walk-right
    # ends on the front/back standing frames used for turning); a frame takes its art from
    # the first animation listed that uses it, so it looks the same everywhere.
    plan = {}

    def assign(f, cast, motion, i):
        if f.addr not in plan:
            plan[f.addr] = (cast, motion, i)

    todo = list(targets(sheets))
    for sheet, cast, motion in todo:
        for i, f in enumerate(sheets[sheet][1]):
            assign(f, cast, motion, i)
    # Inline copies of those frames (intro, ending, innertube idling, sleeping): see
    # tjmod's "~shared" sheets. Paint them like the animation they borrow from.
    by_sheet = {sheet: (cast, motion) for sheet, cast, motion in todo}
    default_lines = cat.palette(rom, "PaletteDefault")
    extra = []
    for name, (pal_name, frames) in sheets.items():
        if name.endswith("~shared"):
            src = name[: -len("~shared")]
        elif name.startswith("Spr_ToejamDiveSplash"):
            src = name
        else:
            continue
        for i, f in enumerate(frames):
            if src == "Spr_SleepZzz":
                assign(f, guess_cast(f, default_lines), SNOOZE, i)
            elif src.startswith("Spr_ToejamDiveSplash"):
                assign(f, guess_cast(f, default_lines), SPLASH, i)
            elif src in by_sheet:
                cast, motion = by_sheet[src]
                if any(p.pal == 2 for p in f.pieces) and src.endswith("Idle"):
                    motion = TUBE
                assign(f, cast, motion, i)
        extra.append(name)

    art = {addr: make_art(lib, cast, motion, i) for addr, (cast, motion, i) in plan.items()}
    data_of = {name: {p.data_addr for f in frames for p in f.pieces} for name, (_, frames) in sheets.items()}

    report = []
    relaid = {"sheets": [], "frames": [], "min_tiles": 24}
    for sheet in [t[0] for t in todo] + extra:
        pal_name, frames = sheets[sheet]
        clipped, painted = paint_sheet(os.path.join(ASSETS, "sprites", sheet + ".png"), frames, manifest[sheet], plan,
                              lambda f: art[f.addr], cat.palette(rom, pal_name)[:3] + [new_line3],
                              cat.palette(rom, pal_name)[3], data_of)
        report.append((sheet, len(frames), clipped))
        if painted:
            relaid["sheets"].append(sheet)
            relaid["frames"] += ["%06X" % a for a in painted]
    print("Painted %d animations" % len(report), flush=True)

    # HUD: names in the status bar ("TOEJAM IS A" -> "MORTY IS A", "EARL IS A" -> "RICK IS A")
    path = os.path.join(ASSETS, "images", "ImgTextBase.png")
    img = Image.open(path)
    hud.write_word(img, [31, 32, 33, 34, 35], "MORTY", 34)  # TOEJAM runs into tile 35's first column
    hud.write_word(img, [38, 39, 40], "RICK", 24)
    img.save(path, transparency=0)

    # HUD portraits: Spr_ActionIcons frames 0 and 1. The rest of that sheet keeps its
    # look under the new palette (its line-3 pixels are remapped explicitly).
    pal_name, frames = sheets["Spr_ActionIcons"]
    old_lines = cat.palette(rom, pal_name)
    path = os.path.join(ASSETS, "sprites", "Spr_ActionIcons.png")
    img = Image.open(path)
    px = img.load()
    table = tjmod.remap_table(old_lines[3], new_line3)
    for y in range(img.height):
        for x in range(img.width):
            if px[x, y] // 16 == 3:
                px[x, y] = 48 + table[px[x, y] % 16]
    ox, oy = manifest["Spr_ActionIcons"]["origin"]
    cw = manifest["Spr_ActionIcons"]["cell"][0]
    for i, cast in ((0, "morty"), (1, "rick")):
        p = frames[i].pieces[0]
        icon = hud.head_icon(lib[cast]["down"][0], p.w * 8, p.h * 8)
        for yy in range(p.h * 8):
            for xx in range(p.w * 8):
                c = icon.getpixel((xx, yy))
                px[i * cw + p.x + ox + xx, p.y + oy + yy] = 48 + nearest_index(c[:3], new_line3) if c[3] >= 128 else 0
    img.putpalette([v for line in old_lines[:3] + [new_line3] for rgb in line for v in rgb])
    img.save(path)

    # Big Rick & Morty on the title and in the intro story
    pal_name, frames = sheets[bigcast.SHEET]
    hexrgb = lambda h: tuple(int(h[k:k + 2], 16) for k in (1, 3, 5))
    title_lines = cat.palette(rom, pal_name)[:2] + [[hexrgb(h) for h in bigcast.TITLE_LINE2_COLORS],
                                                     [hexrgb(h) for h in bigcast.TITLE_LINE3_COLORS]]
    path = os.path.join(ASSETS, "sprites", bigcast.SHEET + ".png")
    img = Image.open(path)
    img.putpalette([v for line in title_lines for rgb in line for v in rgb])
    bigcast.paint(img, frames, manifest[bigcast.SHEET], lib, title_lines, nearest_index)
    img.save(path)
    relaid["sheets"].append(bigcast.SHEET)
    relaid["frames"] += ["%06X" % f.addr for f in frames]
    json.dump(relaid, open(os.path.join(ASSETS, "relayout.json"), "w"))

    # Title screen: "SCHWIFTY JAM" logo (tile data + tile map, as raw patches)
    patches, n = title.build_patches()
    # ...and the attract cycle's big-cast picture, with the same 3x Rick & Morty
    big = {c: bigcast.scale3x(lib[c]["down"][0].img) for c in ("rick", "morty")}
    cast_patches, m = title.build_cast_patches(big["rick"], big["morty"], title_lines, nearest_index)
    boot_patches, b = boot.patches(rom)
    music_patches = music.patches(rom)
    json.dump([{"addr": "%06X" % a, "hex": data.hex(), "note": "title screens"} for a, data in patches + cast_patches]
              + boot_patches + music_patches, open(os.path.join(ASSETS, "patches.json"), "w"))
    print("Boot logo (HERVALICIO.US): %d tiles; music: Schwifty Jam groove in %d keys" % (b, len(music.KEYS)), flush=True)
    print("Title logo: %d tiles; big-cast picture: %d tiles" % (n, m), flush=True)

    # Text: ranks, presents, names, the intro story...
    path = os.path.join(ASSETS, "text.json")
    text = json.load(open(path))
    by_addr = {e["addr"]: e for e in text}
    hud_ranks = ["0A9FB8", "0A9FBF", "0A9FC5", "0A9FCB", "0A9FD2", "0A9FD7", "0A9FDB", "0A9FE1", "0A9FE7", "0A9FEC"]
    plain_ranks = ["0AA01A", "0AA021", "0AA027", "0AA032", "0AA039", "0AA03E", "0AA042", "0AA048", "0AA052"]
    for a, name in zip(hud_ranks, script.RANKS_HUD):
        by_addr[a]["text"] = name
    for a, name in zip(plain_ranks, script.RANKS_PLAIN):
        by_addr[a]["text"] = name
    replaced = 0
    for e in text:
        new = script.PRESENTS.get(e["text"]) or script.LINES.get(e["text"])
        if new is not None and e["addr"] not in hud_ranks + plain_ranks:
            e["text"] = new
            replaced += 1
    json.dump(text, open(path, "w"), indent=1)
    print("Rewrote %d text strings (+ %d ranks)" % (replaced, len(hud_ranks) + len(plain_ranks)), flush=True)
    # Strings only reachable PC-relatively can't be moved; they must fit where they are.
    for e in text:
        a = int(e["addr"], 16)
        old = rom[a:rom.index(b"\0", a)]
        if len(e["text"]) > len(old) and not tjmod.find_refs(rom, a):
            sys.exit("text %r is longer than %r and can't be moved; shorten it in script.py" % (e["text"], old.decode()))

    cmd = [sys.executable, os.path.join(ROOT, "tjmod.py"), "--assets", ASSETS, "build", "--requantize", "--out", OUT]
    if not args.no_web:
        cmd += ["--web", WEB]
    subprocess.run(cmd, check=True)
    if not args.no_web:
        os.makedirs(os.path.dirname(WEB_PATCH), exist_ok=True)
        shutil.copyfile(os.path.splitext(OUT)[0] + ".ips", WEB_PATCH)
        print("Copied the patch to %s" % os.path.relpath(WEB_PATCH, ROOT))


if __name__ == "__main__":
    main()
