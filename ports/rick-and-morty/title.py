"""Title screen logo: "SCHWIFTY JAM" in place of the ToeJam & Earl logo.

The title's logo is plane B: 271 tiles at ROM 0x2C59A (tile 0 there is blank) placed by a
raw 40x25 map at 0x2BDC8. The game adds 0x8244 to each map word (priority + VRAM tile 580),
so a word is: tile number (0 = blank) | palette line << 13 | hflip 0x800 | vflip 0x1000.
The funky yellow pattern behind it is plane A and stays.
"""
import math
import os
import struct

from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
FONT = os.path.join(HERE, "vendor", "PressStart2P-Regular.ttf")

MAP_ADDR, TILES_ADDR, MAX_TILES = 0x2BDC8, 0x2C59A, 271
COLS, ROWS = 40, 25
LINE = 1  # PaletteTitleScreen line 1: #40E040 light green, #00A000 dark green, black, white
LIGHT, DARK, BLACK, WHITE = 3, 14, 15, 1


def _word_mask(text, size, wave, phase=0.0):
    """Letters of a word as a 1-bit mask, each bobbing on a sine wave."""
    font = ImageFont.truetype(FONT, size)
    w = size * len(text) + 4
    h = size + 2 * wave + 4
    mask = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(mask)
    for i, ch in enumerate(text):
        dy = round(math.sin(i * 0.9 + phase) * wave)
        d.text((i * size, wave + dy), ch, font=font, fill=255)
    return mask.point(lambda v: 255 if v >= 128 else 0)


def render():
    """The logo as a 320x200 image of palette-line indices (0 = see-through)."""
    canvas = Image.new("L", (COLS * 8, ROWS * 8), 0)  # pixel values are color indices

    def stamp(mask, x, y, extrude):
        # black outline around (letters + 3D extrusion), dark green extrusion, light green face
        solid = Image.new("L", (mask.width + extrude + 4, mask.height + extrude + 4), 0)
        for k in range(extrude + 1):
            solid.paste(255, (2 + k, 2 + k), mask)
        outline = solid.filter(ImageFilter.MaxFilter(3))
        layer = Image.new("L", solid.size, 0)
        layer.paste(BLACK, (0, 0), outline)
        for k in range(1, extrude + 1):
            layer.paste(DARK, (2 + k, 2 + k), mask)
        layer.paste(LIGHT, (2, 2), mask)
        canvas.paste(layer, (x, y), layer.point(lambda v: 255 if v else 0))

    top = _word_mask("SCHWIFTY", 32, 4)
    stamp(top, (canvas.width - top.width - 4) // 2, 28, 4)
    jam = _word_mask("JAM", 48, 5, phase=1.3)
    stamp(jam, (canvas.width - jam.width - 5) // 2, 92, 5)

    # subtitle: white on a black outline
    sub = _word_mask("RICK & MORTY EDITION", 8, 0)
    solid = Image.new("L", (sub.width + 4, sub.height + 4), 0)
    solid.paste(255, (2, 2), sub)
    layer = Image.new("L", solid.size, 0)
    layer.paste(BLACK, (0, 0), solid.filter(ImageFilter.MaxFilter(3)))
    layer.paste(WHITE, (2, 2), sub)
    canvas.paste(layer, ((canvas.width - layer.width) // 2, 168), layer.point(lambda v: 255 if v else 0))
    return canvas


def _tile(img, cx, cy):
    px = img.load()
    return tuple(px[cx * 8 + x, cy * 8 + y] for y in range(8) for x in range(8))


def _flips(t):
    rows = [t[y * 8:(y + 1) * 8] for y in range(8)]
    h = tuple(v for r in rows for v in reversed(r))
    v = tuple(x for r in reversed(rows) for x in r)
    hv = tuple(x for r in reversed(rows) for x in reversed(r))
    return {0: t, 0x800: h, 0x1000: v, 0x1800: hv}


def build_patches(img=None):
    """[(addr, bytes)] for the tile data and the map. Raises if the logo needs too many tiles."""
    img = img or render()
    tiles, index, words = [], {}, []
    for cy in range(ROWS):
        for cx in range(COLS):
            t = _tile(img, cx, cy)
            if not any(t):
                words.append(0)
                continue
            for flag, variant in _flips(t).items():
                if variant in index:
                    words.append(index[variant] | (LINE << 13) | flag)
                    break
            else:
                tiles.append(t)
                index[t] = len(tiles)  # tile 0 is the blank one
                words.append(index[t] | (LINE << 13))
    if len(tiles) > MAX_TILES:
        raise ValueError("logo needs %d tiles, only %d fit" % (len(tiles), MAX_TILES))
    data = bytearray(32 * MAX_TILES)
    for k, t in enumerate(tiles):
        for i in range(32):
            data[k * 32 + i] = (t[i * 2] << 4) | t[i * 2 + 1]
    return [(TILES_ADDR + 32, bytes(data)), (MAP_ADDR, struct.pack(">%dH" % len(words), *words))], len(tiles)


# The attract cycle's other picture: big ToeJam & Earl, also a plane-B image. 209 tiles
# (tile 0 blank) at 0x2ECEC and a raw 40x17 map at 0x2E79A for screen rows 4-20, using
# title palette lines 2 (Earl) and 3 (ToeJam) - which the port turns into Rick's and
# Morty's palettes (bigcast.py).
CAST_MAP_ADDR, CAST_TILES_ADDR, CAST_MAX_TILES, CAST_ROWS = 0x2E79A, 0x2ECEC, 208, 17


def build_cast_patches(rick, morty, lines, nearest_index):
    """rick/morty: big RGBA images. Returns ([(addr, bytes)], tiles used)."""
    w, h = COLS * 8, CAST_ROWS * 8
    layers = []
    for img, cx, line in ((rick, 112, 2), (morty, 214, 3)):
        idx = Image.new("L", (w, h), 0)
        px, src = idx.load(), img.load()
        x0, y0 = cx - img.width // 2, h - img.height - 4
        for y in range(img.height):
            for x in range(img.width):
                c = src[x, y]
                if c[3] >= 128 and 0 <= x0 + x < w and 0 <= y0 + y < h:
                    px[x0 + x, y0 + y] = nearest_index(c[:3], lines[line], range(1, 16))
        layers.append((idx, line))
    tiles, index, words = [], {}, []
    for cy in range(CAST_ROWS):
        for cx in range(COLS):
            word = 0
            for idx, line in layers:
                t = _tile(idx, cx, cy)
                if not any(t):
                    continue
                if word:
                    raise ValueError("Rick and Morty overlap in map cell %d,%d" % (cx, cy))
                for flag, variant in _flips(t).items():
                    if variant in index:
                        word = index[variant] | (line << 13) | flag
                        break
                else:
                    tiles.append(t)
                    index[t] = len(tiles)
                    word = index[t] | (line << 13)
            words.append(word)
    if len(tiles) > CAST_MAX_TILES:
        raise ValueError("cast picture needs %d tiles, only %d fit" % (len(tiles), CAST_MAX_TILES))
    data = bytearray(32 * CAST_MAX_TILES)
    for k, t in enumerate(tiles):
        for i in range(32):
            data[k * 32 + i] = (t[i * 2] << 4) | t[i * 2 + 1]
    return [(CAST_TILES_ADDR + 32, bytes(data)), (CAST_MAP_ADDR, struct.pack(">%dH" % len(words), *words))], len(tiles)
