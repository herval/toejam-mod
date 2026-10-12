"""Variations on a Schwifty Jam sprite for ToeJam & Earl's special animations.

Each function takes an `Art` (RGBA image + feet anchor) and returns a new one.
Colors are picked from the port's sprite palette so they survive quantization.
"""
from PIL import Image

WHITE, GREY, DARK, BLACK = (224, 224, 224, 255), (160, 160, 160, 255), (64, 64, 64, 255), (0, 0, 0, 255)


class Art:
    def __init__(self, img, ax, ay):
        self.img, self.ax, self.ay = img, ax, ay
        self.w, self.h = img.size

    @classmethod
    def of(cls, spr):
        return cls(spr.img, spr.ax, spr.ay)


def _luma(p):
    return 0.3 * p[0] + 0.59 * p[1] + 0.11 * p[2]


def _recolor(art, fn):
    img = art.img.copy()
    px = img.load()
    for y in range(img.height):
        for x in range(img.width):
            if px[x, y][3] >= 128:
                px[x, y] = fn(px[x, y])
    return Art(img, art.ax, art.ay)


def ghost(art):
    """Pale see-through-looking version (losing a life)."""
    return _recolor(art, lambda p: WHITE if _luma(p) > 150 else GREY if _luma(p) > 60 else DARK)


def xray(art):
    """Electrocuted: white outline on a black body, like the original skeleton flash."""
    return _recolor(art, lambda p: WHITE if _luma(p) < 50 else BLACK)


def sleep(art):
    """Lying down, head to the left."""
    img = art.img.transpose(Image.Transpose.ROTATE_90)
    return Art(img, img.width // 2, img.height - 1)


def flat(art):
    """Flattened pancake."""
    w, h = round(art.w * 1.4), max(4, round(art.h * 0.42))
    return Art(art.img.resize((w, h), Image.NEAREST), w // 2, h - 1)


def _outlined(rows, colors):
    """Tiny pixel grid -> RGBA with a 1px black outline."""
    h, w = len(rows), max(len(r) for r in rows)
    img = Image.new("RGBA", (w + 2, h + 2))
    px = img.load()
    for y, row in enumerate(rows):
        for x, ch in enumerate(row):
            if ch in colors:
                px[x + 1, y + 1] = colors[ch]
    out = img.copy()
    opx = out.load()
    for y in range(img.height):
        for x in range(img.width):
            if px[x, y][3]:
                continue
            if any(0 <= x + dx < img.width and 0 <= y + dy < img.height and px[x + dx, y + dy][3]
                   for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))):
                opx[x, y] = BLACK
    return out


WING_UP = ["......w", "....www", "..wwwwg", "wwwwwg.", ".wwwg.."]
WING_DOWN = ["wwwg...", "wwwwwg.", ".wwwwwg", "...wwww", ".....ww"]


def wings(art, frame):
    """Little white wings flapping behind the shoulders."""
    shape = _outlined(WING_UP if frame % 2 == 0 else WING_DOWN, {"w": WHITE, "g": GREY})
    pad = shape.width - 2
    img = Image.new("RGBA", (art.w + pad * 2, art.h))
    y = round(art.h * 0.42) - shape.height // 2
    img.alpha_composite(shape.transpose(Image.Transpose.FLIP_LEFT_RIGHT), (0, y))
    img.alpha_composite(shape, (art.w + pad * 2 - shape.width, y))
    img.alpha_composite(art.img, (pad, 0))
    return Art(img, art.ax + pad, art.ay)


COIL_LONG = ["gggg.", ".dddd", "gggg.", ".dddd", "gggg."]
COIL_SHORT = ["gggg.", ".dddd", "gggg."]


def springs(art, frame):
    """Spring shoes: a coil under each foot, compressed on alternate frames."""
    coil = _outlined(COIL_LONG if frame % 2 == 0 else COIL_SHORT, {"g": GREY, "d": DARK})
    img = Image.new("RGBA", (art.w, art.h + coil.height - 2))
    img.alpha_composite(art.img, (0, 0))
    for cx in (art.ax - 3, art.ax + 3):
        img.alpha_composite(coil, (max(0, min(art.w - coil.width, cx - coil.width // 2)), art.h - 2))
    return Art(img, art.ax, img.height - 1)


BOOT = ["rrrr.", "rRRRr", ".g.g."]
RED, DARK_RED = (224, 0, 0, 255), (64, 32, 0, 255)


def skates(art, frame):
    """Rocket skates: a red boot under each foot."""
    boot = _outlined(BOOT, {"r": RED, "R": DARK_RED, "g": GREY})
    img = Image.new("RGBA", (art.w + 2, art.h + boot.height - 3))
    img.alpha_composite(art.img, (1, 0))
    for cx in (art.ax - 2, art.ax + 4):
        img.alpha_composite(boot, (max(0, min(img.width - boot.width, cx - boot.width // 2)), art.h - 3))
    return Art(img, art.ax + 1, img.height - 1)


SHADOW_MARK = (255, 0, 255, 255)  # build_port paints this with the shadow operator


def hidden(art):
    """Invisible Boogeyman: a shimmering checkerboard of shadow, the shape of the creature."""
    img = Image.new("RGBA", art.img.size)
    src, dst = art.img.load(), img.load()
    for y in range(img.height):
        for x in range(img.width):
            if src[x, y][3] >= 128 and (x + y) % 2 == 0:
                dst[x, y] = SHADOW_MARK
    return Art(img, art.ax, art.ay)
