#!/usr/bin/env python3
"""Demo mod: green ToeJam (palette edit) + checkered shorts for Earl (pixel edit).

Copies ../assets to ./demo-assets and edits the copy, so your own assets stay untouched.
Then:  python3 tjmod.py --assets examples/demo-assets build --out build/demo.md --web web/mod.md
"""
import json
import os
import shutil

from PIL import Image

here = os.path.dirname(os.path.abspath(__file__))
src, dst = os.path.join(here, "..", "assets"), os.path.join(here, "demo-assets")
shutil.rmtree(dst, ignore_errors=True)
shutil.copytree(src, dst)

# 1. Palette: sprite palette line 3 holds ToeJam's reds. Make them greens.
pal_path = os.path.join(dst, "palettes.json")
pal = json.load(open(pal_path))
pal["098198"]["colors"][1:4] = ["#006000", "#00C000", "#40E040"]
json.dump(pal, open(pal_path, "w"), indent=1)

# 2. Pixels: Earl's bright-blue shorts (line 3, color 13 -> index 61) get a 2x2 white check.
# The check is anchored to each frame's origin, so a frame shared by two sheets gets the same pattern.
BLUE, WHITE = 3 * 16 + 13, 3 * 16 + 11
manifest = json.load(open(os.path.join(dst, "manifest.json")))
for name, info in manifest.items():
    if not name.startswith("Spr_Earl"):
        continue
    path = os.path.join(dst, "sprites", name + ".png")
    (cw, _), (ox, oy) = info["cell"], info["origin"]
    img = Image.open(path)
    px = img.load()
    for y in range(img.height):
        for x in range(img.width):
            fx, fy = x % cw - ox, y - oy
            if px[x, y] == BLUE and (fx // 2 + fy // 2) % 2:
                px[x, y] = WHITE
    img.save(path, transparency=img.info.get("transparency"))
print("demo assets written to", dst)
