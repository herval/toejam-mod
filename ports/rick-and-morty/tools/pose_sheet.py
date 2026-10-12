#!/usr/bin/env python3
"""Contact sheet of every puppet pose, for checking poses.py by eye.

  python3 tools/pose_sheet.py poses.png
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from PIL import Image, ImageDraw
import poses
names = ["run", "sneak", "teeter", "fall", "land", "pain", "leap", "dive", "climb", "throw", "slingshot", "highfive",
         "covers", "read", "cheer", "hula", "shield", "swig"]
rows = []
for who in ("rick", "morty"):
    for view in ("down", "side"):
        arts = []
        for n in names:
            frames = 4 if n == "run" else 2
            arts += [poses.make(n, who, view, k) for k in range(frames if n in ("run", "teeter", "fall", "climb", "throw", "hula") else 1)]
        rows.append(("%s %s" % (who, view), arts))
S = 3
W = max(sum(a.w * S + 6 for a in r) for _, r in rows) + 100
H = sum(max(a.h for a in r) * S + 10 for _, r in rows)
card = Image.new("RGBA", (W, H), (34, 120, 40, 255)); d = ImageDraw.Draw(card); y = 0
for name, arts in rows:
    d.text((4, y + 4), name, fill=(255, 255, 255)); x = 100
    for a in arts:
        card.alpha_composite(a.img.resize((a.w * S, a.h * S), Image.NEAREST), (x, y + (max(b.h for b in arts) - a.h) * S)); x += a.w * S + 6
    y += max(a.h for a in arts) * S + 10
card.save(sys.argv[1]); print(card.size)
