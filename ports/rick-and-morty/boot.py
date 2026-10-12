"""Boot screen: "HERVALICIO.US" where the shimmering SEGA logo was.

The Sega screen (loc_0003A4E4) copies 49 logo tiles from SplashSegaLogo (0x928EC) to VRAM 0
and lays a 12x4 map (0x9288C, words E001..E030: priority, line 3) on plane A at 0xA51C.
Its shine is palette cycling: 20 line-3 palettes at 0x92F0C stepped every 3 frames, with
color 1 the outline and colors 2-10 diagonal bands. The new logo is wider (26x4), so the
tile count, data pointer, width, map pointer and position operands in that routine are
patched, and the tiles + map go to the expansion area.
"""
import os

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
FONT = os.path.join(HERE, "vendor", "PressStart2P-Regular.ttf")
TEXT = "HERVALICIO.US"
COLS, ROWS = 26, 4
PALETTES, PALETTE_COUNT = 0x92F0C, 20

# operands inside loc_0003A4E4 (verified against the REV 02 bytes)
TILE_WORDS = 0x3A534   # PEA.w  word count (0x0310 = 49 tiles)
TILES_PTR = 0x3A538    # PEA.l  SplashSegaLogo
COLS_OP = 0x3A54C      # PEA.w  map width (0x000C)
MAP_PTR = 0x3A550      # PEA.l  0x9288C
POS_OP = 0x3A556       # MOVE.l #0x0000A51C (plane A, row 10, col 14)


def render():
    """208x32 image of palette indices: 1 = outline, 2..10 = shine bands."""
    w, h = COLS * 8, ROWS * 8
    font = ImageFont.truetype(FONT, 16)
    mask = Image.new("L", (w, 16), 0)
    ImageDraw.Draw(mask).text((0, 0), TEXT, font=font, fill=255)
    mask = mask.point(lambda v: 255 if v >= 128 else 0).resize((w, 32), Image.NEAREST)  # 2x taller
    m = mask.load()
    img = Image.new("L", (w, h), 0)
    px = img.load()
    for y in range(h):
        for x in range(w):
            if m[x, y]:
                # diagonal bands across each 16px letter, like the SEGA logo's
                px[x, y] = 2 + min(8, ((x % 16) + y // 4) // 2)
    for y in range(h):
        for x in range(w):
            if not m[x, y] and any(0 <= x + dx < w and 0 <= y + dy < h and m[x + dx, y + dy]
                                   for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))):
                px[x, y] = 1
    return img


def green(word):
    """Sega-blue shine -> portal green: swap the blue and green nibbles of a CRAM word."""
    b, g, r = (word >> 8) & 0xE, (word >> 4) & 0xE, word & 0xE
    return (g << 8) | (b << 4) | r


def patches(rom):
    """tjmod patch entries for the new boot logo."""
    img = render()
    px = img.load()
    tiles, index, words = [bytes(32)], {bytes(32): 0}, []
    for ty in range(ROWS):
        for tx in range(COLS):
            data = bytearray(32)
            for y in range(8):
                for x in range(0, 8, 2):
                    data[y * 4 + x // 2] = (px[tx * 8 + x, ty * 8 + y] << 4) | px[tx * 8 + x + 1, ty * 8 + y]
            data = bytes(data)
            if data not in index:
                index[data] = len(tiles)
                tiles.append(data)
            words.append(0xE000 | index[data])
    col = (40 - COLS) // 2
    pos = 0xA000 + (10 * 64 + col) * 2
    cycle = bytearray()
    for k in range(PALETTE_COUNT * 16):
        w = int.from_bytes(rom[PALETTES + 2 * k:PALETTES + 2 * k + 2], "big")
        cycle += green(w).to_bytes(2, "big")
    return [
        {"label": "boot_tiles", "hex": b"".join(tiles).hex()},
        {"label": "boot_map", "hex": b"".join(w.to_bytes(2, "big") for w in words).hex()},
        {"addr": "%06X" % TILE_WORDS, "hex": (len(tiles) * 16).to_bytes(2, "big").hex(), "note": "boot logo tiles"},
        {"addr": "%06X" % TILES_PTR, "ptr": "boot_tiles"},
        {"addr": "%06X" % COLS_OP, "hex": COLS.to_bytes(2, "big").hex(), "note": "boot logo width"},
        {"addr": "%06X" % MAP_PTR, "ptr": "boot_map"},
        {"addr": "%06X" % POS_OP, "hex": pos.to_bytes(4, "big").hex(), "note": "boot logo position"},
        {"addr": "%06X" % PALETTES, "hex": bytes(cycle).hex(), "note": "boot logo shine, in green"},
    ], len(tiles)
