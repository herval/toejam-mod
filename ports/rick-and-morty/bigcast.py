"""Big Rick & Morty for the title and intro scenes (Spr_TitleBigPlayers).

Big Earl (palette line 2) and big ToeJam (line 3) are each a body frame plus overlay
frames (head turns, blinks, mouths, arms) drawn at the same origin. A 3x Rick/Morty is
laid over each character's area and every frame takes the pixels under its own boxes.
The title palette has no skin tones, so title lines 2 and 3 get R&M palettes.
"""
from PIL import Image

SHEET = "Spr_TitleBigPlayers"
SCALE = 3

TITLE_LINE2 = "098378"  # PaletteTitleScreen line 2 (big Earl only)
TITLE_LINE2_COLORS = ["#000000", "#000000", "#A0E0E0", "#4080C0", "#E0C0A0", "#C0A080", "#E0E0E0", "#A0A0A0",
                      "#606060", "#804020", "#402000", "#602020", "#E0E040", "#202020", "#400000", "#E00000"]
TITLE_LINE3 = "0983D8"  # PaletteTitleScreen line 3 (big ToeJam; also the intro crash scene)
TITLE_LINE3_COLORS = ["#000000", "#000000", "#804020", "#402000", "#E0C0A0", "#C0A080", "#E0E040", "#C0A020",
                      "#4060C0", "#204080", "#E0E0E0", "#A0A0A0", "#606060", "#E00000", "#E06000", "#602000"]


def scale3x(img):
    """AdvMAME3x / Scale3x: 3x pixel-art upscale that keeps edges crisp but rounds corners."""
    w, h = img.size
    src = img.load()
    out = Image.new("RGBA", (w * 3, h * 3))
    dst = out.load()

    def p(x, y):
        x = min(max(x, 0), w - 1)
        y = min(max(y, 0), h - 1)
        return src[x, y]

    for y in range(h):
        for x in range(w):
            A, B, C = p(x - 1, y - 1), p(x, y - 1), p(x + 1, y - 1)
            D, E, F = p(x - 1, y), p(x, y), p(x + 1, y)
            G, H, I = p(x - 1, y + 1), p(x, y + 1), p(x + 1, y + 1)
            if B != H and D != F:
                e = [D if D == B else E,
                     B if (D == B and E != C) or (B == F and E != A) else E,
                     F if B == F else E,
                     D if (D == B and E != G) or (D == H and E != A) else E,
                     E,
                     F if (B == F and E != I) or (H == F and E != C) else E,
                     D if D == H else E,
                     H if (D == H and E != I) or (H == F and E != G) else E,
                     F if H == F else E]
            else:
                e = [E] * 9
            for k, v in enumerate(e):
                dst[x * 3 + k % 3, y * 3 + k // 3] = v
    return out


def plan(frames):
    """{frame addr: cast} and per-cast frame lists: line-2 frames are Earl's, line-3 ToeJam's."""
    who = {}
    for f in frames:
        lines = {p.pal for p in f.pieces}
        who[f.addr] = "rick" if lines == {2} else "morty"
    return who


def paint(sheet_img, frames, entry, lib, lines, nearest_index):
    """Paint the big cast into the (indexed) sheet image in place."""
    ox, oy = entry["origin"]
    cw, ch = entry["cell"]
    px = sheet_img.load()
    who = plan(frames)
    for cast in ("rick", "morty"):
        mine = [f for f in frames if who[f.addr] == cast]
        body = max(mine, key=lambda f: len(f.pieces))
        boxes = [(p.x, p.y, p.w * 8, p.h * 8) for p in body.pieces]
        x0 = min(b[0] for b in boxes)
        x1 = max(b[0] + b[2] for b in boxes)
        y1 = max(b[1] + b[3] for b in boxes)
        big = scale3x(lib[cast]["down"][0].img)
        # feet on the bottom of the body, centred on it
        left = (x0 + x1) // 2 - big.width // 2
        top = y1 - big.height
        line = 2 if cast == "rick" else 3
        src = big.load()
        for i, f in enumerate(frames):
            if who[f.addr] != cast:
                continue
            for y in range(ch):
                for x in range(cw):
                    px[i * cw + x, y] = 0
            # The body frame carries the whole character (the build fits new sprite boxes
            # around it); overlay frames (head turns, blinks) repeat what's under their boxes.
            if f is body:
                area = [(xx, yy) for yy in range(top, top + big.height) for xx in range(left, left + big.width)]
            else:
                area = [(xx, yy) for p in f.pieces
                        for yy in range(p.y, p.y + p.h * 8) for xx in range(p.x, p.x + p.w * 8)]
            for xx, yy in area:
                sx, sy = xx - left, yy - top
                cx, cy = xx + ox, yy + oy
                if 0 <= sx < big.width and 0 <= sy < big.height and 0 <= cx < cw and 0 <= cy < ch:
                    c = src[sx, sy]
                    if c[3] >= 128:
                        px[i * cw + cx, cy] = line * 16 + nearest_index(c[:3], lines[line], range(1, 16))
    return who
