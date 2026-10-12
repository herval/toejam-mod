"""HUD bits for the port: player names in the status bar, and the little portraits."""
from PIL import Image

# 5x6 capitals in the status bar's style ("9" = the HUD's yellow).
GLYPHS = {
    "M": ["9...9", "99.99", "9.9.9", "9...9", "9...9", "9...9"],
    "O": [".999.", "9...9", "9...9", "9...9", "9...9", ".999."],
    "R": ["9999.", "9...9", "9999.", "9.9..", "9..9.", "9...9"],
    "T": ["99999", "..9..", "..9..", "..9..", "..9..", "..9.."],
    "Y": ["9...9", "9...9", ".9.9.", "..9..", "..9..", "..9.."],
    "I": ["999", ".9.", ".9.", ".9.", ".9.", "999"],
    "C": [".9999", "9....", "9....", "9....", "9....", ".9999"],
    "K": ["9...9", "9..9.", "999..", "9..9.", "9...9", "9...9"],
}
YELLOW, BACKGROUND = 9, 15  # palette line 0 indices used by the status bar text


def write_word(img, tiles, word, width):
    """Draw `word` across `tiles` (in screen order) of a 16-tiles-wide tile sheet, clearing `width` columns."""
    px = img.load()

    def put(x, y, v):
        t = tiles[x // 8]
        px[(t % 16) * 8 + x % 8, (t // 16) * 8 + y] = v

    for x in range(width):
        for y in range(8):
            put(x, y, BACKGROUND)
    x = 1
    for ch in word:
        g = GLYPHS[ch]
        for gy, row in enumerate(g):
            for gx, c in enumerate(row):
                if c == "9":
                    put(x + gx, 1 + gy, YELLOW)
        x += len(g[0]) + 1


def head_icon(spr, w, h):
    """Top of a standing sprite (head and collar), centred in a w x h icon."""
    x0 = max(0, (spr.w - w) // 2)
    crop = spr.img.crop((x0, 0, x0 + min(w, spr.w), h))
    icon = Image.new("RGBA", (w, h))
    icon.alpha_composite(crop, ((w - crop.width) // 2, 0))
    return icon
