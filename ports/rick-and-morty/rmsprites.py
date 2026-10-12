"""Schwifty Jam sprites (dumped by dump_sprites.mjs) as PIL images."""
import base64
import json
import os

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))


class Spr:
    def __init__(self, d):
        self.w, self.h, self.ax, self.ay = d["w"], d["h"], d["ax"], d["ay"]
        self.img = Image.frombytes("RGBA", (self.w, self.h), base64.b64decode(d["rgba"]))


def _wrap(v):
    if isinstance(v, list):
        return [Spr(s) for s in v]
    if "rgba" in v:
        return Spr(v)
    return {k: _wrap(s) for k, s in v.items() if s is not None}


def load(path=os.path.join(HERE, "out", "sprites.json")):
    return {k: _wrap(v) for k, v in json.load(open(path)).items() if not k.startswith("__")}


def load_raw(path=os.path.join(HERE, "out", "sprites.json")):
    """Schwifty Jam's source grids and palette (PAL, OUT, RICK, MORTY)."""
    return json.load(open(path))["__raw"]
