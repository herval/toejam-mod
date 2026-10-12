#!/usr/bin/env python3
"""Render sheets straight out of a built ROM (what the game will actually draw).
  python3 preview.py build/rick-and-morty.md out.png Spr_ToejamWalkDown Spr_EarlIdle ...
"""
import os
import sys

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", ".."))
import tjmod  # noqa: E402

rom = bytearray(open(sys.argv[1], "rb").read())
# Frame layout comes from the original ROM (a build can move sprite data around, which
# hides "~shared" frames from discovery); pixels and palettes come from the ROM given.
cat = tjmod.Catalog(tjmod.load_rom(tjmod.DEFAULT_ROM), tjmod.DEFAULT_CFG)
sheets = {n: (p, f) for n, p, f in cat.sheets}
names = sys.argv[3:]
rows = []
def live(f):
    """The frame as the built ROM has it: list entries may point at a moved header, and
    re-laid-out frames may have a different sprite count."""
    addr = f.addr
    refs = cat.list_refs.get(f.addr)
    if refs:
        addr = int.from_bytes(rom[refs[0]:refs[0] + 4], "big")
    if f.single:
        return tjmod.Frame(addr, [tjmod.Piece(addr, rom)], single=True)
    return tjmod.Frame(addr, [tjmod.Piece(addr + 4 + 10 * i, rom) for i in range(rom[addr])])


for n in names:
    pal, frames = sheets[n]
    frames = [live(f) for f in frames]
    rows.append((n, tjmod.render_sheet(frames, cat.palette(rom, pal)).convert("RGBA")))
W = max(170 + im.width * 3 for _, im in rows)
H = sum(im.height * 3 + 6 for _, im in rows)
card = Image.new("RGBA", (W, H), (34, 120, 40, 255))
d = ImageDraw.Draw(card)
y = 0
for n, im in rows:
    d.text((4, y + 4), n.replace("Spr_", ""), fill=(255, 255, 255))
    card.alpha_composite(im.resize((im.width * 3, im.height * 3), Image.NEAREST), (170, y))
    y += im.height * 3 + 6
card.save(sys.argv[2])
print(card.size)
