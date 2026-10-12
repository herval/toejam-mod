#!/usr/bin/env python3
"""ToeJam & Earl (Genesis, REV 02) asset round-tripper.

  extract  ROM -> assets/ (sprites/*.png, images/*.png, sounds/*.wav, palettes.json)
  build    assets/ -> patched ROM (+ IPS patch), only touching what you changed

Sprite and palette locations come from the community disassembly
(https://github.com/bstreiff/tje-disasm, resources.cfg).
"""

import argparse
import configparser
import hashlib
import json
import os
import shutil
import struct
import sys
import wave
from collections import defaultdict

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_ROM = os.path.join(HERE, "rom", "original.md")
DEFAULT_CFG = os.path.join(HERE, "tje-disasm", "resources.cfg")  # git submodule
# Text strings are found via the disassembly's .asciz list (in ROM order).
DEFAULT_ASSETS = os.path.join(HERE, "assets")
EXTRA_CFG = os.path.join(HERE, "resources-extra.cfg")  # sprites found by `scan` that resources.cfg lacks
DEFAULT_OUT = os.path.join(HERE, "build", "toejam-mod.md")
REV02_SHA1 = "85e8d0a4fac591b25b77c35680ac4175976f251b"

FLAG_INTERLEAVED = 0x80
FLAG_UNCOMPRESSED = 0x40
COLOR_TOLERANCE = 12  # editors sometimes nudge colors; ignore tiny drift
# PCM playback rate: the Z80 driver spends ~412 cycles per sample (+ bank access
# waits) at 3.58 MHz; the game itself budgets 138 samples per 60 Hz frame.
SAMPLE_RATE = 8600
# Display palettes for the raw tile images (a best guess; only affects how they look).
IMAGE_PALETTES = {
    "ImgSegaLogo": ("PaletteSpaceScreen", 3),
    "ImgTJAELogo": ("PaletteTitleScreen", 1),
    "ImgLevelNumbers": ("PaletteDefault", 2),
    "ImgStarfieldLarge": ("PaletteSpaceScreen", 0),
    "ImgStarfieldSmall": ("PaletteSpaceScreen", 0),
}
IMAGE_COLUMNS = 16  # tiles per row in exported tile sheets

# ---------------------------------------------------------------- compression
#
# Two RLE flavours, decoded by the game's 68k routines (see tje-disasm/tools/rle.py).
# Token bytes:
#   01-3F  copy the next N bytes
#   40-7F  plain:       N x 0xFF            (N = t & 0x3F)
#   40-5F  interleaved: N x 0xFF            (N = t & 0x1F)
#   60-7F  interleaved: N bytes alternating v, swapnibbles(v)  (N = t & 0x1F)
#   80-BF  N x 0x00                         (N = 0xC0 - t, 1..64)
#   C0-FF  N x v                            (N = 0x100 - t, 1..64)
# "Interleaved" splits the data into 4 byte-planes (offset 0,1,2,3 mod 4) and
# encodes each plane on its own.


def swapnib(v):
    return ((v << 4) & 0xF0) | (v >> 4)


def _decode_stream(rom, pos, count, interleaved):
    """Decode `count` bytes of one stream. Returns (bytes, new_pos)."""
    out = bytearray()
    while len(out) < count:
        t = rom[pos]
        pos += 1
        if 0x01 <= t <= 0x3F:
            out += rom[pos:pos + t]
            pos += t
        elif t >= 0xC0:
            out += bytes([rom[pos]]) * (0x100 - t)
            pos += 1
        elif t >= 0x80:
            out += b"\x00" * (0xC0 - t)
        elif t == 0:
            raise ValueError("zero token at %06X" % (pos - 1))
        elif not interleaved:
            out += b"\xFF" * (t & 0x3F)
        elif t < 0x60:
            out += b"\xFF" * (t & 0x1F)
        else:
            v = rom[pos]
            pos += 1
            out += bytes(v if k % 2 == 0 else swapnib(v) for k in range(t & 0x1F))
    if len(out) != count:
        raise ValueError("stream overran its length")
    return bytes(out), pos


def decompress(rom, addr, size, flags):
    """Returns (raw tile bytes, compressed length rounded up to even)."""
    if flags & FLAG_UNCOMPRESSED:
        return bytes(rom[addr:addr + size]), size
    if flags & FLAG_INTERLEAVED:
        planes, pos = [], addr
        for _ in range(4):
            plane, pos = _decode_stream(rom, pos, size // 4, True)
            planes.append(plane)
        raw = bytearray(size)
        for s in range(4):
            raw[s::4] = planes[s]
    else:
        raw, pos = _decode_stream(rom, addr, size, False)
    zlen = pos - addr
    return bytes(raw), zlen + (zlen & 1)


def _encode_stream(data, interleaved):
    """Smallest token stream for `data` (dynamic programming over all parses)."""
    n = len(data)
    max_ff = 31 if interleaved else 63
    # run lengths starting at each index
    same = [0] * (n + 1)
    alt = [0] * (n + 1)
    for i in range(n - 1, -1, -1):
        same[i] = same[i + 1] + 1 if i + 1 < n and data[i + 1] == data[i] else 1
        if interleaved:
            alt[i] = alt[i + 1] + 1 if i + 1 < n and data[i + 1] == swapnib(data[i]) else 1
    INF = float("inf")
    cost = [INF] * (n + 1)
    choice = [None] * (n + 1)
    cost[n] = 0
    for i in range(n - 1, -1, -1):
        best, pick = INF, None
        v = data[i]
        run = same[i]
        if v == 0:
            lim = min(run, 64)
        elif v == 0xFF:
            lim = min(run, max_ff)
        else:
            lim = min(run, 64)
        one = 1 if v in (0, 0xFF) else 2
        for L in range(1, lim + 1):
            c = one + cost[i + L]
            if c < best:
                best, pick = c, ("run", L)
        if v == 0xFF and run > max_ff:
            # 0xFF can also use the generic value-run token for longer runs
            for L in range(max_ff + 1, min(run, 64) + 1):
                c = 2 + cost[i + L]
                if c < best:
                    best, pick = c, ("vrun", L)
        if interleaved and alt[i] >= 2:
            for L in range(2, min(alt[i], 31) + 1):
                c = 2 + cost[i + L]
                if c < best:
                    best, pick = c, ("alt", L)
        for L in range(1, min(63, n - i) + 1):
            c = 1 + L + cost[i + L]
            if c < best:
                best, pick = c, ("lit", L)
        cost[i], choice[i] = best, pick

    out = bytearray()
    i = 0
    while i < n:
        kind, L = choice[i]
        v = data[i]
        if kind == "lit":
            out.append(L)
            out += data[i:i + L]
        elif kind == "alt":
            out += bytes([0x60 | L, v])
        elif kind == "run" and v == 0:
            out.append(0xC0 - L)
        elif kind == "run" and v == 0xFF:
            out.append(0x40 | L)
        else:
            out += bytes([0x100 - L, v])
        i += L
    return bytes(out)


def compress(raw, flags):
    if flags & FLAG_UNCOMPRESSED:
        return bytes(raw)
    if flags & FLAG_INTERLEAVED:
        return b"".join(_encode_stream(raw[s::4], True) for s in range(4))
    return _encode_stream(raw, False)


# ---------------------------------------------------------------- ROM model


class Piece:
    """One hardware sprite: up to 4x4 tiles, column-major, 4bpp."""

    def __init__(self, hdr_addr, rom):
        self.hdr_addr = hdr_addr
        (self.w, self.h, self.x, self.y, self.z, self.flags, self.data_addr) = struct.unpack(
            ">BBbbbBI", rom[hdr_addr:hdr_addr + 10])
        self.size = self.w * self.h * 32
        self.raw, self.zlen = decompress(rom, self.data_addr, self.size, self.flags)

    @property
    def pal(self):
        return self.flags & 3

    def pixels(self, raw=None):
        """Dict-free 2D list [y][x] of color indices."""
        raw = self.raw if raw is None else raw
        W, H = self.w * 8, self.h * 8
        px = [[0] * W for _ in range(H)]
        for b, v in enumerate(raw):
            tile, inner = divmod(b, 32)
            tx, ty = divmod(tile, self.h)
            row, col = divmod(inner, 4)
            x, y = tx * 8 + col * 2, ty * 8 + row
            px[y][x] = v >> 4
            px[y][x + 1] = v & 15
        return px

    def encode(self, px):
        raw = bytearray(self.size)
        for b in range(self.size):
            tile, inner = divmod(b, 32)
            tx, ty = divmod(tile, self.h)
            row, col = divmod(inner, 4)
            x, y = tx * 8 + col * 2, ty * 8 + row
            raw[b] = (px[y][x] << 4) | px[y][x + 1]
        return bytes(raw)


class Frame:
    """A metasprite: a list of pieces drawn around a shared origin."""

    def __init__(self, addr, pieces, single=False):
        self.addr = addr
        self.pieces = pieces
        self.single = single  # a lone sprite header (SPRITE_LIST entry), no count byte

    def bounds(self):
        xs = [p.x for p in self.pieces] + [p.x + p.w * 8 for p in self.pieces]
        ys = [p.y for p in self.pieces] + [p.y + p.h * 8 for p in self.pieces]
        return min(xs), min(ys), max(xs), max(ys)


def load_rom(path):
    if not os.path.exists(path):
        sys.exit("No ROM at %s. Put your ToeJam & Earl REV 02 ROM there (or pass --rom)." % path)
    rom = bytearray(open(path, "rb").read())
    sha = hashlib.sha1(rom).hexdigest()
    if sha != REV02_SHA1:
        sys.exit("ROM SHA-1 %s is not ToeJam & Earl REV 02 (%s)." % (sha, REV02_SHA1))
    return rom


def cram_to_rgb(c):
    return ((c & 0x00E) << 4, (c & 0x0E0), (c & 0xE00) >> 4)


def rgb_to_cram(rgb):
    r, g, b = (min(7, (v + 16) // 32) for v in rgb[:3])
    return (b << 9) | (g << 5) | (r << 1)


def read_line(rom, addr):
    return [cram_to_rgb(c) for c in struct.unpack(">16H", rom[addr:addr + 32])]


class Catalog:
    """Everything resources.cfg tells us, resolved against a ROM."""

    def __init__(self, rom, cfg_path):
        cfg = configparser.ConfigParser()
        if not cfg.read(cfg_path):
            sys.exit("Can't read %s (run `git submodule update --init` to fetch the disassembly)." % cfg_path)
        cfg.read(EXTRA_CFG)
        self.palette_sets = {}   # name -> [addr x4]
        self.list_refs = defaultdict(list)  # frame addr -> ROM offsets of list entries pointing at it
        self.sheets = []         # (name, palette set name, [Frame])
        self.images = []         # (name, addr, length): uncompressed 4bpp tiles
        self.sounds = []         # (name, addr, length): u16 sample count + unsigned 8-bit PCM
        frames = {}
        for name in cfg.sections():
            sec = cfg[name]
            kind = sec["kind"]
            if kind == "PALETTE":
                self.palette_sets[name] = [int(sec["address%d" % i], 0) for i in range(4)]
            elif kind in ("RAW_IMAGE", "PCM_AUDIO"):
                entry = (name, int(sec["address"], 0), int(sec["length"], 0))
                (self.images if kind == "RAW_IMAGE" else self.sounds).append(entry)
            elif kind in ("METASPRITE_LIST", "SPRITE_LIST"):
                addr, length = int(sec["address"], 0), int(sec["length"], 0)
                ptrs = struct.unpack(">%dI" % (length // 4), rom[addr:addr + length])
                for k, p in enumerate(ptrs):
                    if addr + 4 * k not in self.list_refs[p]:
                        self.list_refs[p].append(addr + 4 * k)
                seen, sheet = set(), []
                for p in ptrs:
                    if p in seen:
                        continue
                    seen.add(p)
                    if p not in frames:
                        if kind == "SPRITE_LIST":
                            frames[p] = Frame(p, [Piece(p, rom)], single=True)
                        else:
                            count = rom[p]
                            frames[p] = Frame(p, [Piece(p + 4 + i * 10, rom) for i in range(count)])
                    sheet.append(frames[p])
                self.sheets.append((name, sec.get("palette", "PaletteDefault"), sheet))
        self.frames = frames
        self._find_shared(rom)

    def _find_shared(self, rom):
        """Metasprites the catalog doesn't list but that reuse catalogued sprite data.

        The game embeds some frames inline (intro, ending, sleeping poses...). Each is
        rebuilt from its piece headers and published as a "<source sheet>~shared" sheet,
        so edits never leak into it and it can be edited like its source.
        """
        known_hdrs = {p.hdr_addr for f in self.frames.values() for p in f.pieces}
        source = {}
        for name, _, frames in self.sheets:
            for f in frames:
                for p in f.pieces:
                    source.setdefault(p.data_addr, name)

        def piece_ok(h):
            try:
                w, hh, _, _, _, fl, d = struct.unpack(">BBbbbBI", rom[h:h + 10])
                if not (1 <= w <= 4 and 1 <= hh <= 4) or fl & ~0xC3 or not (0x200 <= d < len(rom)):
                    return False
                decompress(rom, d, w * hh * 32, fl)
                return True
            except Exception:
                return False

        shared = {}
        for d, name in source.items():
            needle = struct.pack(">I", d)
            i = rom.find(needle)
            while i >= 0:
                h = i - 6
                i = rom.find(needle, i + 1)
                if h in known_hdrs or not piece_ok(h):
                    continue
                for k in range(8):  # where does this metasprite start?
                    start = h - 4 - 10 * k
                    n = rom[start]
                    if k < n <= 8 and all(piece_ok(start + 4 + 10 * j) for j in range(n)):
                        if start not in self.frames and start not in shared:
                            shared[start] = (name, Frame(start, [Piece(start + 4 + 10 * j, rom) for j in range(n)]))
                        break
        groups = {}
        for start, (name, frame) in sorted(shared.items()):
            if any(p.hdr_addr in known_hdrs for p in frame.pieces):
                continue  # overlaps a catalogued frame; not a separate metasprite
            groups.setdefault(name, []).append(frame)
            self.frames[start] = frame
        pal_of = {n: pal for n, pal, _ in self.sheets}
        for name, frames in groups.items():
            self.sheets.append((name + "~shared", pal_of[name], frames))

    def palette(self, rom, set_name):
        return [read_line(rom, a) for a in self.palette_sets[set_name]]


# ---------------------------------------------------------------- sheets
#
# One PNG per animation. Frames sit side by side in equal cells that share the
# animation's origin, so they line up when flipped through. The PNG is indexed
# with 64 colors: palette line L, color C is index L*16+C (C=0 is transparent).
# Overlapping pieces: piece 0 is drawn on top.


def sheet_layout(frames):
    b = [f.bounds() for f in frames]
    x0, y0 = min(v[0] for v in b), min(v[1] for v in b)
    x1, y1 = max(v[2] for v in b), max(v[3] for v in b)
    return x0, y0, x1 - x0, y1 - y0


def render_sheet(frames, lines):
    """Indexed 64-color image of all frames, laid out by sheet_layout()."""
    ox, oy, cw, ch = sheet_layout(frames)
    img = Image.new("P", (cw * len(frames), ch), 0)
    flat = []
    for line in lines:
        for rgb in line:
            flat += list(rgb)
    img.putpalette(flat)
    img.info["transparency"] = bytes([0 if i % 16 == 0 else 255 for i in range(64)])
    px = img.load()
    for fi, f in enumerate(frames):
        for p in reversed(f.pieces):
            pix = p.pixels()
            for yy in range(p.h * 8):
                for xx in range(p.w * 8):
                    c = pix[yy][xx]
                    if c:
                        px[fi * cw + p.x - ox + xx, p.y - oy + yy] = p.pal * 16 + c
    return img


def nearest(rgb, line):
    best, idx = None, 1
    for i in range(1, 16):
        r, g, b = line[i]
        d = (r - rgb[0]) ** 2 + (g - rgb[1]) ** 2 + (b - rgb[2]) ** 2
        if best is None or d < best:
            best, idx = d, i
    return idx, best


# ---------------------------------------------------------------- tile images
#
# Raw 4bpp tiles (font, HUD, logos), shown IMAGE_COLUMNS tiles wide in ROM order.


def render_tiles(data, line):
    tiles = len(data) // 32
    rows = (tiles + IMAGE_COLUMNS - 1) // IMAGE_COLUMNS
    img = Image.new("P", (IMAGE_COLUMNS * 8, rows * 8), 0)
    img.putpalette([v for rgb in line for v in rgb])
    img.info["transparency"] = 0
    px = img.load()
    for b, v in enumerate(data):
        t, inner = divmod(b, 32)
        row, col = divmod(inner, 4)
        x, y = (t % IMAGE_COLUMNS) * 8 + col * 2, (t // IMAGE_COLUMNS) * 8 + row
        px[x, y], px[x + 1, y] = v >> 4, v & 15
    return img


def apply_tiles(data, line, img, warnings, name):
    """Diff an edited tile sheet against the original; returns new bytes (same length)."""
    original = render_tiles(data, line).convert("RGBA")
    edited = img.convert("RGBA")
    if edited.size != original.size:
        warnings.append("%s: size is %dx%d, expected %dx%d; skipped" % ((name,) + edited.size + original.size))
        return data
    op, ep = original.load(), edited.load()
    out = bytearray(data)
    for b in range(len(data)):
        t, inner = divmod(b, 32)
        row, col = divmod(inner, 4)
        x, y = (t % IMAGE_COLUMNS) * 8 + col * 2, (t // IMAGE_COLUMNS) * 8 + row
        nib = [data[b] >> 4, data[b] & 15]
        for k in (0, 1):
            a, e = op[x + k, y], ep[x + k, y]
            if (a[3] < 128) == (e[3] < 128) and (a[3] < 128 or max(abs(a[i] - e[i]) for i in range(3)) <= COLOR_TOLERANCE):
                continue
            nib[k] = 0 if e[3] < 128 else nearest(e, line)[0]
        out[b] = (nib[0] << 4) | nib[1]
    return bytes(out)


# ---------------------------------------------------------------- sounds


def sound_samples(rom, addr, length):
    count = struct.unpack(">H", rom[addr:addr + 2])[0]
    return bytes(rom[addr + 2:addr + 2 + min(count, length - 2)])


def write_wav(path, samples):
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(1)  # 8-bit WAV is unsigned, same as the game
        w.setframerate(SAMPLE_RATE)
        w.writeframes(samples)


def read_wav(path):
    """Any 8/16/24/32-bit PCM WAV -> unsigned 8-bit mono at SAMPLE_RATE."""
    try:
        with wave.open(path, "rb") as w:
            ch, width, rate = w.getnchannels(), w.getsampwidth(), w.getframerate()
            data = w.readframes(w.getnframes())
    except wave.Error as e:
        sys.exit("%s: %s (save it as a 16-bit or 8-bit PCM WAV)" % (path, e))
    if width == 1:
        vals = [(b - 128) / 128 for b in data]
    else:
        scale = float(1 << (8 * width - 1))
        vals = [int.from_bytes(data[i:i + width], "little", signed=True) / scale
                for i in range(0, len(data), width)]
    mono = [sum(vals[i:i + ch]) / ch for i in range(0, len(vals), ch)]
    if rate != SAMPLE_RATE and mono:
        n = max(1, round(len(mono) * SAMPLE_RATE / rate))
        step = (len(mono) - 1) / max(1, n - 1)
        out = []
        for j in range(n):
            pos = j * step
            i = int(pos)
            frac = pos - i
            nxt = mono[min(i + 1, len(mono) - 1)]
            out.append(mono[i] * (1 - frac) + nxt * frac)
        mono = out
    return bytes(max(0, min(255, round(v * 128 + 128))) for v in mono)


def find_refs(rom, addr):
    """Even offsets holding `addr` as a big-endian long (sound table entries and code immediates)."""
    needle, refs, i = struct.pack(">I", addr), [], rom.find(struct.pack(">I", addr))
    while i != -1:
        if i % 2 == 0:
            refs.append(i)
        i = rom.find(needle, i + 1)
    return refs


# ---------------------------------------------------------------- text


def _c_unescape(s):
    out, i = bytearray(), 0
    while i < len(s):
        ch = s[i]
        if ch != "\\":
            out += ch.encode("latin-1")
            i += 1
            continue
        nxt = s[i + 1]
        if nxt in "01234567":
            j = i + 1
            while j < len(s) and j < i + 4 and s[j] in "01234567":
                j += 1
            out.append(int(s[i + 1:j], 8))
            i = j
        else:
            out += {"n": b"\n", "t": b"\t", "\\": b"\\", '"': b'"', "'": b"'"}[nxt]
            i += 2
    return bytes(out)


def find_strings(rom, cfg_path):
    """[(addr, bytes)] for every .asciz string in the disassembly, located in ROM order."""
    import re
    src = os.path.join(os.path.dirname(os.path.abspath(cfg_path)), "src", "main.S")
    if not os.path.exists(src):
        return []
    found, pos = [], 0x200
    for line in open(src, encoding="latin-1"):
        m = re.search(r'\.asciz\s+"((?:[^"\\]|\\.)*)"', line)
        if not m:
            continue
        data = _c_unescape(m.group(1))
        i = rom.find(data + b"\0", pos)
        if i < 0:
            continue
        found.append((i, data))
        pos = i + len(data) + 1
    return found


# ---------------------------------------------------------------- commands


def cmd_extract(args):
    rom = load_rom(args.rom)
    cat = Catalog(rom, args.cfg)
    sprite_dir = os.path.join(args.assets, "sprites")
    guide_dir = os.path.join(args.assets, "guides")
    os.makedirs(sprite_dir, exist_ok=True)
    os.makedirs(guide_dir, exist_ok=True)
    manifest = {}
    for name, pal_name, frames in cat.sheets:
        img = render_sheet(frames, cat.palette(rom, pal_name))
        img.save(os.path.join(sprite_dir, name + ".png"), transparency=img.info["transparency"])
        ox, oy, cw, ch = sheet_layout(frames)
        manifest[name] = {"frames": len(frames), "cell": [cw, ch], "origin": [-ox, -oy], "palette": pal_name}
        # Guide: where the hardware sprites are. Only pixels inside a box can be drawn.
        guide = img.convert("RGBA")
        draw = ImageDraw.Draw(guide)
        for fi, f in enumerate(frames):
            for p in f.pieces:
                x, y = fi * cw + p.x - ox, p.y - oy
                draw.rectangle((x, y, x + p.w * 8 - 1, y + p.h * 8 - 1), outline=(0, 255, 200, 160))
        guide.save(os.path.join(guide_dir, name + ".png"))

    palettes = {}
    for set_name, addrs in cat.palette_sets.items():
        for line_no, a in enumerate(addrs):
            key = "%06X" % a
            entry = palettes.setdefault(key, {"used_as": [], "colors": ["#%02X%02X%02X" % c for c in read_line(rom, a)]})
            entry["used_as"].append("%s line %d" % (set_name, line_no))
    with open(os.path.join(args.assets, "palettes.json"), "w") as f:
        json.dump(palettes, f, indent=1)

    image_dir = os.path.join(args.assets, "images")
    os.makedirs(image_dir, exist_ok=True)
    for name, addr, length in cat.images:
        set_name, line_no = IMAGE_PALETTES.get(name, ("PaletteDefault", 0))
        img = render_tiles(rom[addr:addr + length], cat.palette(rom, set_name)[line_no])
        img.save(os.path.join(image_dir, name + ".png"), transparency=0)
        manifest[name] = {"tiles": length // 32, "palette": "%s line %d" % (set_name, line_no)}

    strings = find_strings(rom, args.cfg)
    if strings:
        with open(os.path.join(args.assets, "text.json"), "w") as f:
            json.dump([{"addr": "%06X" % a, "text": d.decode("latin-1")} for a, d in strings], f, indent=1)

    sound_dir = os.path.join(args.assets, "sounds")
    os.makedirs(sound_dir, exist_ok=True)
    for name, addr, length in cat.sounds:
        samples = sound_samples(rom, addr, length)
        write_wav(os.path.join(sound_dir, name + ".wav"), samples)
        manifest[name] = {"samples": len(samples), "seconds": round(len(samples) / SAMPLE_RATE, 2)}
    with open(os.path.join(args.assets, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=1)

    # A swatch card, handy as an editor palette reference.
    card = Image.new("RGB", (16 * 12, len(palettes) * 12), (40, 40, 40))
    for row, (key, entry) in enumerate(palettes.items()):
        for i, hexcol in enumerate(entry["colors"]):
            rgb = tuple(int(hexcol[k:k + 2], 16) for k in (1, 3, 5))
            card.paste(rgb, (i * 12, row * 12, i * 12 + 11, row * 12 + 11))
    card.save(os.path.join(args.assets, "palettes.png"))
    print("Extracted %d animations (%d frames), %d tile images, %d sounds, %d text strings and %d palette lines to %s"
          % (len(cat.sheets), sum(len(s[2]) for s in cat.sheets), len(cat.images), len(cat.sounds),
             len(strings), len(palettes), args.assets))


def remap_table(old, new):
    """Old palette index -> closest index in the new line (keeping the index when it is as good)."""
    table = [0]
    for i in range(1, 16):
        idx, d = nearest(old[i], new)
        if sum((a - b) ** 2 for a, b in zip(old[i], new[i])) <= d:
            idx = i
        table.append(idx)
    return table


def remap_raw(raw, table):
    return bytes((table[v >> 4] << 4) | table[v & 15] for v in raw)


def encode_tiles(pix, w, h):
    """{(x, y): color} for a w x h tile sprite -> raw 4bpp data, tiles column-major."""
    raw = bytearray(w * h * 32)
    for (x, y), c in pix.items():
        tile = (x // 8) * h + y // 8
        b = tile * 32 + (y % 8) * 4 + (x % 8) // 2
        raw[b] |= c << 4 if x % 2 == 0 else c
    return bytes(raw)


def layout_pieces(pixels, budget, max_pieces=99):
    """Cover {(x, y): palette index} with hardware sprites (<= 32x32, one palette line each).

    Tries every 8x8 offset of the 32px block grid and keeps the layout with the fewest
    tiles. Returns [(line, x, y, w, h, {(dx, dy): color})] or None if over `budget` tiles.
    """
    by_line = defaultdict(dict)
    for (x, y), v in pixels.items():
        by_line[v // 16][(x, y)] = v % 16

    def blobs(px, gap=3):
        """Groups of pixels at most `gap` apart (a body and the Zzz floating over it)."""
        left, groups = set(px), []
        while left:
            todo, group = [left.pop()], set()
            while todo:
                x, y = todo.pop()
                group.add((x, y))
                near = [(x + dx, y + dy) for dx in range(-gap, gap + 1) for dy in range(-gap, gap + 1)]
                for q in near:
                    if q in left:
                        left.remove(q)
                        todo.append(q)
            groups.append({q: px[q] for q in group})
        return groups

    def cover(line, px):
        """Best 32px-grid cover of one group of pixels: (tiles, pieces)."""
        best = None
        for gx in range(0, 32, 8):
            for gy in range(0, 32, 8):
                x0 = min(x for x, _ in px) - gx
                y0 = min(y for _, y in px) - gy
                blocks = defaultdict(dict)
                for (x, y), c in px.items():
                    blocks[((x - x0) // 32, (y - y0) // 32)][(x, y)] = c
                pieces, tiles = [], 0
                for sub in blocks.values():
                    sx0, sy0 = min(x for x, _ in sub), min(y for _, y in sub)
                    w = (max(x for x, _ in sub) - sx0) // 8 + 1
                    h = (max(y for _, y in sub) - sy0) // 8 + 1
                    pieces.append((line, sx0, sy0, w, h, {(x - sx0, y - sy0): c for (x, y), c in sub.items()}))
                    tiles += w * h
                if best is None or (tiles + 3 * len(pieces)) < (best[0] + 3 * len(best[1])):
                    best = (tiles, pieces)
        return best

    def boxes(line, sub):
        sx0, sy0 = min(x for x, _ in sub), min(y for _, y in sub)
        w = (max(x for x, _ in sub) - sx0) // 8 + 1
        h = (max(y for _, y in sub) - sy0) // 8 + 1
        return w * h, (line, sx0, sy0, w, h, {(x - sx0, y - sy0): c for (x, y), c in sub.items()})

    def bands(line, px):
        """Finer search: horizontal bands at any 1px offset, each with its own column split."""
        best = None
        ymin = min(y for _, y in px)
        for gy in range(32):
            rows = defaultdict(dict)
            for (x, y), c in px.items():
                rows[(y - ymin + gy) // 32][(x, y)] = c
            tiles, pieces = 0, []
            for band in rows.values():
                xmin = min(x for x, _ in band)
                pick = None
                for gx in range(32):
                    cols = defaultdict(dict)
                    for (x, y), c in band.items():
                        cols[(x - xmin + gx) // 32][(x, y)] = c
                    got = [boxes(line, sub) for sub in cols.values()]
                    t = sum(g[0] for g in got)
                    if pick is None or (len(got), t) < (len(pick[1]), pick[0]):
                        pick = (t, [g[1] for g in got])
                tiles += pick[0]
                pieces += pick[1]
            if best is None or (len(pieces), tiles) < (len(best[1]), best[0]):
                best = (tiles, pieces)
        return best

    # Either cover each palette line as one group, or each separate blob on its own;
    # keep whichever needs fewer tiles/sprites (within the sprite limit).
    candidates = []
    for split in (False, True):
        pieces, tiles = [], 0
        for line, px in sorted(by_line.items()):
            for group in (blobs(px) if split else [px]):
                t, ps = cover(line, group)
                tiles += t
                pieces += ps
        candidates.append((tiles, pieces))
    if all(len(p) > max_pieces for _, p in candidates):
        pieces, tiles = [], 0
        for line, px in sorted(by_line.items()):
            t, ps = bands(line, px)
            tiles += t
            pieces += ps
        candidates.append((tiles, pieces))
    best = None
    for tiles, pieces in candidates:
        cost = (tiles + 3 * len(pieces), tiles)
        if tiles <= budget and len(pieces) <= max_pieces and (best is None or cost < best[0]):
            best = (cost, pieces)
    if best is None:
        return None
    if any(not (-128 <= x <= 127 and -128 <= y <= 127) for _, x, y, _, _, _ in best[1]):
        return None
    return best[1]


def apply_sheet(frames, lines, new_lines, img, warnings, name, base, relayout=None, only=None,
                growable=lambda addr: False, notes=None):
    """Diff an edited sheet against its original render (old palette `lines`).

    Changed pixels snap to the final palette (`new_lines`). An indexed PNG that keeps the
    exported 64-color layout is taken literally instead: index L*16+C is color C of line L
    (so e.g. 63 paints the game's shadow operator). If every opaque pixel of a hardware
    sprite is repainted from one other palette line, the sprite switches to that line.
    Pieces start from `base` (e.g. requantized data) when present.

    With `relayout` (a minimum tile budget), changed frames of an indexed sheet get brand
    new hardware sprites fitted to the art instead of keeping the old boxes.
    Returns ({(frame addr, piece idx): new raw}, {(frame addr, piece idx): new palette line},
    {frame addr: [new pieces]}).
    """
    original_p = render_sheet(frames, lines)
    original = original_p.convert("RGBA")
    edited = img.convert("RGBA")
    indexed = img.mode == "P" and len(img.getpalette() or []) >= 64 * 3
    if indexed:
        oi, ei = original_p.load(), img.load()
        epal = img.getpalette()
    if edited.size != original.size:
        warnings.append("%s: size is %dx%d, expected %dx%d; skipped" % ((name,) + edited.size + original.size))
        return {}, {}, {}
    ox, oy, cw, ch = sheet_layout(frames)
    op, ep = original.load(), edited.load()
    result, repal, layouts = {}, {}, {}
    notes = notes if notes is not None else []
    outside = far = 0
    for fi, f in enumerate(frames):
        if relayout is not None and indexed and (only is None or f.addr in only):
            cells = [(cx, cy) for cy in range(ch) for cx in range(cw)]
            if any(oi[fi * cw + cx, cy] != ei[fi * cw + cx, cy] for cx, cy in cells):
                pixels = {(cx + ox, cy + oy): ei[fi * cw + cx, cy] for cx, cy in cells if ei[fi * cw + cx, cy] % 16}
                budget = max(sum(p.w * p.h for p in f.pieces), relayout)
                # A lone sprite stays one sprite; a frame nothing points at can't grow
                # (its header can't move), so it keeps its sprite count.
                max_pieces = 1 if f.single else (99 if growable(f.addr) else len(f.pieces))
                pieces = layout_pieces(pixels, budget, max_pieces) if pixels else None
                if pieces:
                    layouts[f.addr] = pieces
                    continue
                notes.append("%s: frame %06X kept its old boxes (%s)" % (
                    name, f.addr, "empty" if not pixels else "no layout in %d tiles / %d sprites" % (budget, max_pieces)))
        pix = [p.pixels(base.get((f.addr, i))) for i, p in enumerate(f.pieces)]
        touched = set()
        pals = [p.pal for p in f.pieces]
        if indexed:
            for i, p in enumerate(f.pieces):
                used, kept = set(), False
                for y in range(p.y, p.y + p.h * 8):
                    for x in range(p.x, p.x + p.w * 8):
                        cx, cy = x - ox, y - oy
                        if not (0 <= cx < cw and 0 <= cy < ch):
                            continue
                        a_i, b_i = oi[fi * cw + cx, cy], ei[fi * cw + cx, cy]
                        if b_i % 16 == 0:
                            continue
                        if a_i == b_i and tuple(epal[b_i * 3:b_i * 3 + 3]) == lines[a_i // 16][a_i % 16]:
                            kept = True
                        used.add(b_i // 16)
                if len(used) == 1 and not kept and next(iter(used)) != p.pal:
                    pals[i] = next(iter(used))
                    repal[(f.addr, i)] = pals[i]
                    touched.add(i)
        for cy in range(ch):
            for cx in range(cw):
                if indexed:
                    a_i, b_i = oi[fi * cw + cx, cy], ei[fi * cw + cx, cy]
                    b = tuple(epal[b_i * 3:b_i * 3 + 3])
                    if a_i % 16 == 0 and b_i % 16 == 0:
                        continue
                    # Same index *and* same color as exported means untouched; the same index
                    # under a recolored palette entry is a deliberate pick of the new color.
                    if a_i == b_i and b == lines[a_i // 16][a_i % 16]:
                        continue
                    b_clear = b_i % 16 == 0
                else:
                    a, b = op[fi * cw + cx, cy], ep[fi * cw + cx, cy]
                    a_clear, b_clear = a[3] < 128, b[3] < 128
                    if a_clear and b_clear:
                        continue
                    if a_clear == b_clear and max(abs(a[k] - b[k]) for k in range(3)) <= COLOR_TOLERANCE:
                        continue
                x, y = cx + ox, cy + oy
                covering = [i for i, p in enumerate(f.pieces)
                            if p.x <= x < p.x + p.w * 8 and p.y <= y < p.y + p.h * 8]
                if not covering:
                    outside += 1
                    continue
                # The pixel goes into the piece(s) whose palette line matches it best;
                # the other pieces under it turn transparent there. Either way it shows
                # the same, whichever piece the hardware draws on top.
                picks = {}
                for i in covering:
                    pal = pals[i]
                    if b_clear:
                        picks[i] = (0, 0)
                    elif indexed and b_i // 16 == pal:
                        picks[i] = (b_i % 16, 0)
                    else:
                        picks[i] = nearest(b, new_lines[pal])
                best = min(d for _, d in picks.values())
                if best > 3 * 40 ** 2:
                    far += 1
                for i, (c, d) in picks.items():
                    p = f.pieces[i]
                    pix[i][y - p.y][x - p.x] = c if d == best else 0
                    touched.add(i)
        for i in touched:
            result[(f.addr, i)] = f.pieces[i].encode(pix[i])
    if outside:
        warnings.append("%s: %d edited pixels fall outside any sprite piece and were dropped" % (name, outside))
    if far:
        warnings.append("%s: %d pixels had no close color in their palette line (snapped to nearest)" % (name, far))
    return result, repal, layouts


def write_ips(orig, new, path):
    """IPS patch from orig to new (handles growth; long same-byte runs become RLE records)."""
    out = bytearray(b"PATCH")

    def record(off, chunk):
        out.extend(struct.pack(">I", off)[1:] + struct.pack(">H", len(chunk)) + chunk)

    def rle(off, count, value):
        out.extend(struct.pack(">I", off)[1:] + b"\x00\x00" + struct.pack(">HB", count, value))

    def same(i):
        return i < len(orig) and orig[i] == new[i]

    i, n = 0, len(new)
    while i < n:
        if same(i):
            i += 1
            continue
        start = i - 1 if i == 0x454F46 else i  # an offset that reads "EOF" ends the patch
        end = i
        while end < n and not same(end):
            end += 1
        pos = start
        while pos < end:
            run = 1
            while pos + run < end and new[pos + run] == new[pos] and run < 0xFFFF:
                run += 1
            if run >= 9 and pos != 0x454F46:
                rle(pos, run, new[pos])
                pos += run
                continue
            lit_end = pos + 1
            while lit_end < end and lit_end - pos < 0xFFFF:
                r = 1
                while lit_end + r < end and new[lit_end + r] == new[lit_end] and r < 9:
                    r += 1
                if r >= 9:
                    break
                lit_end += 1
            record(pos, new[pos:lit_end])
            pos = lit_end
        i = end
    out += b"EOF"
    with open(path, "wb") as f:
        f.write(out)


def cmd_build(args):
    orig = load_rom(args.rom)
    rom = bytearray(orig)
    cat = Catalog(orig, args.cfg)
    warnings = []

    # 1. Palettes
    pal_path = os.path.join(args.assets, "palettes.json")
    pal_changes = 0
    changed_lines = set()
    if os.path.exists(pal_path):
        for key, entry in json.load(open(pal_path)).items():
            a = int(key, 16)
            for i, hexcol in enumerate(entry["colors"]):
                rgb = tuple(int(hexcol.lstrip("#")[k:k + 2], 16) for k in (0, 2, 4))
                word = rgb_to_cram(rgb)
                old = struct.unpack(">H", orig[a + i * 2:a + i * 2 + 2])[0]
                # Some ROM words carry unused bits; only count a real color change.
                if word != rgb_to_cram(cram_to_rgb(old)):
                    rom[a + i * 2:a + i * 2 + 2] = struct.pack(">H", word)
                    pal_changes += 1
                    changed_lines.add(a)

    # Optionally keep untouched sprites looking the same under changed palette lines.
    base = {}
    if args.requantize and changed_lines:
        frame_set = {}
        for _, pal_name, frames in cat.sheets:
            for f in frames:
                frame_set.setdefault(f.addr, pal_name)
        tables = {a: remap_table(read_line(orig, a), read_line(rom, a)) for a in changed_lines}
        for f in cat.frames.values():
            line_addrs = cat.palette_sets[frame_set[f.addr]]
            for i, p in enumerate(f.pieces):
                table = tables.get(line_addrs[p.pal])
                if table:
                    raw = remap_raw(p.raw, table)
                    if raw != p.raw:
                        base[(f.addr, i)] = raw

    alloc_ptr = len(rom)

    def allocate(blob, uncompressed=False):
        """Append to the expansion area (ROM grows 1 -> 2 -> 4 MB as needed)."""
        nonlocal rom, alloc_ptr
        alloc_ptr += alloc_ptr & 1
        if uncompressed and (alloc_ptr >> 17) != ((alloc_ptr + len(blob) - 1) >> 17):
            alloc_ptr = ((alloc_ptr >> 17) + 1) << 17  # DMA can't cross a 128 KB boundary
        while alloc_ptr + len(blob) > len(rom):
            if len(rom) >= 0x400000:
                sys.exit("Out of ROM space (4 MB max).")
            rom += b"\xFF" * len(rom)
        addr = alloc_ptr
        rom[addr:addr + len(blob)] = blob
        alloc_ptr += len(blob)
        return addr

    # 2. Sprites: collect per-piece edits, resolving frames that appear in several sheets.
    sheet_edits = {}
    line_changes = {}
    layouts = {}
    layout_notes = []
    edited_sheets = []
    relayout_path = os.path.join(args.assets, "relayout.json")
    # {"sheets": [...], "min_tiles": 24, "frames": ["0B1072", ...] (optional: only these)}
    relayout = json.load(open(relayout_path)) if os.path.exists(relayout_path) else {"sheets": []}
    only = {int(a, 16) for a in relayout["frames"]} if "frames" in relayout else None
    for name, pal_name, frames in cat.sheets:
        path = os.path.join(args.assets, "sprites", name + ".png")
        if not os.path.exists(path):
            continue
        changes, repal, lay = apply_sheet(frames, cat.palette(orig, pal_name), cat.palette(rom, pal_name),
                                          Image.open(path), warnings, name, base,
                                          relayout.get("min_tiles", 0) if name in relayout["sheets"] else None, only,
                                          lambda addr: bool(cat.list_refs.get(addr)), layout_notes)
        layouts.update(lay)
        if lay:
            edited_sheets.append(name)
        changes = {k: v for k, v in changes.items() if v != base.get(k)}
        line_changes.update(repal)
        if changes or repal:
            edited_sheets.append(name)
        for k, raw in changes.items():
            if k in sheet_edits and sheet_edits[k] != raw:
                warnings.append("%s: frame %06X is also edited in another sheet differently; using %s's version"
                                % (name, k[0], name))
            sheet_edits[k] = raw
    edits = dict(base)
    edits.update(sheet_edits)

    # 3. Group every piece by the data block it points at, then decide who keeps the block.
    users = defaultdict(list)  # data addr -> [(frame addr, piece idx, Piece)]
    for f in cat.frames.values():
        if f.addr in layouts:
            continue  # gets all-new sprites below
        for i, p in enumerate(f.pieces):
            users[p.data_addr].append((f.addr, i, p))

    relocated = inplace = 0
    for data_addr, plist in users.items():
        groups = defaultdict(list)
        for faddr, i, p in plist:
            groups[edits.get((faddr, i), p.raw)].append((faddr, i, p))
        if len(groups) == 1 and next(iter(groups)) == plist[0][2].raw:
            continue
        sample = plist[0][2]
        keeper = sample.raw if sample.raw in groups else max(groups, key=lambda r: len(groups[r]))
        for raw, members in groups.items():
            if raw == sample.raw:
                continue
            blob = compress(raw, sample.flags)
            check, _ = decompress(blob, 0, sample.size, sample.flags)
            assert check == raw, "compressor round-trip failed"
            if raw == keeper and len(blob) <= sample.zlen and not args.force_relocate:
                rom[data_addr:data_addr + len(blob)] = blob
                inplace += 1
                continue
            new_addr = allocate(blob, sample.flags & FLAG_UNCOMPRESSED)
            relocated += 1
            for faddr, i, p in members:
                rom[p.hdr_addr + 6:p.hdr_addr + 10] = struct.pack(">I", new_addr)

    # Re-laid-out frames: new sprite data, new piece headers (in place when they fit,
    # otherwise a new metasprite that the animation lists point to).
    moved_frames = 0
    for faddr, pieces in layouts.items():
        f = cat.frames[faddr]
        comp = f.pieces[0].flags & 0xC0
        z = f.pieces[0].z
        entries = []
        for line, x, y, w, h, pix in pieces:
            raw = encode_tiles(pix, w, h)
            blob = compress(raw, comp)
            data = allocate(blob, comp & FLAG_UNCOMPRESSED)
            entries.append(struct.pack(">BBbbbBI", w, h, x, y, z, comp | line, data))
        if f.single:
            rom[faddr:faddr + 10] = entries[0]
        elif len(entries) <= len(f.pieces):
            rom[faddr] = len(entries)
            rom[faddr + 4:faddr + 4 + 10 * len(entries)] = b"".join(entries)
        elif cat.list_refs.get(faddr):
            new = allocate(bytes([len(entries)]) + bytes(orig[faddr + 1:faddr + 4]) + b"".join(entries))
            for r in cat.list_refs[faddr]:
                rom[r:r + 4] = struct.pack(">I", new)
            moved_frames += 1
        else:
            raise AssertionError("frame %06X can't grow" % faddr)

    # Hardware sprites repainted from another palette line switch to it (flags bits 0-1).
    for (faddr, i), line in line_changes.items():
        p = cat.frames[faddr].pieces[i]
        rom[p.hdr_addr + 5] = (rom[p.hdr_addr + 5] & 0xFC) | line

    # Frames are shared between some animations; say where else an edit shows up.
    edited_frames = {faddr for faddr, _ in sheet_edits} | {faddr for faddr, _ in line_changes} | set(layouts)
    for name, _, frames in cat.sheets:
        if name not in edited_sheets and any(f.addr in edited_frames for f in frames):
            print("note: %s shares frames with an edited sheet, so it changes too" % name)

    # 3b. Tile images: fixed size, rewritten in place.
    edited_images = []
    for name, addr, length in cat.images:
        path = os.path.join(args.assets, "images", name + ".png")
        if not os.path.exists(path):
            continue
        set_name, line_no = IMAGE_PALETTES.get(name, ("PaletteDefault", 0))
        old = bytes(orig[addr:addr + length])
        new = apply_tiles(old, cat.palette(orig, set_name)[line_no], Image.open(path), warnings, name)
        if new != old:
            rom[addr:addr + length] = new
            edited_images.append(name)

    # 3c. Sounds: in place if they fit, otherwise moved and every pointer to them updated.
    edited_sounds = []
    for name, addr, length in cat.sounds:
        path = os.path.join(args.assets, "sounds", name + ".wav")
        if not os.path.exists(path):
            continue
        old = sound_samples(orig, addr, length)
        new = read_wav(path)
        if new == old:
            continue
        if len(new) > 0xFFFF:
            warnings.append("%s: %.1f s is too long (max %.1f s); truncated"
                            % (name, len(new) / SAMPLE_RATE, 0xFFFF / SAMPLE_RATE))
            new = new[:0xFFFF]
        blob = struct.pack(">H", len(new)) + new
        if len(blob) <= length:
            rom[addr:addr + len(blob)] = blob
            edited_sounds.append(name)
            continue
        refs = find_refs(orig, addr)
        if not refs:
            warnings.append("%s: longer than the original and no pointers to it were found; skipped" % name)
            continue
        new_addr = allocate(blob)
        for r in refs:
            rom[r:r + 4] = struct.pack(">I", new_addr)
        edited_sounds.append(name + " (moved, %d pointers)" % len(refs))

    # 3d. Text: in place when it fits, otherwise moved and every pointer to it updated.
    edited_text = 0
    text_path = os.path.join(args.assets, "text.json")
    if os.path.exists(text_path):
        for entry in json.load(open(text_path)):
            a = int(entry["addr"], 16)
            end = orig.index(b"\0", a)
            old, new = bytes(orig[a:end]), entry["text"].encode("latin-1")
            if new == old:
                continue
            if len(new) <= len(old):
                rom[a:end + 1] = new + b"\0" * (len(old) - len(new) + 1)
            else:
                refs = find_refs(orig, a)
                if not refs:
                    warnings.append("text %06X %r: longer than the original and nothing points at it; truncated"
                                    % (a, entry["text"]))
                    rom[a:end + 1] = new[:len(old)] + b"\0"
                else:
                    new_addr = allocate(new + b"\0")
                    for r in refs:
                        rom[r:r + 4] = struct.pack(">I", new_addr)
            edited_text += 1

    # 3e. Raw patches for anything without a nicer format (e.g. a title-screen tile map):
    #     {"addr": "02BDC8", "hex": "..."}   overwrite bytes
    #     {"label": "logo", "hex": "..."}    new data in the expansion area...
    #     {"addr": "03A538", "ptr": "logo"}  ...and a 32-bit pointer to it
    patches = 0
    patch_path = os.path.join(args.assets, "patches.json")
    if os.path.exists(patch_path):
        entries = json.load(open(patch_path))
        labels = {e["label"]: allocate(bytes.fromhex(e["hex"])) for e in entries if "label" in e}
        for entry in entries:
            if "label" in entry:
                continue
            a = int(entry["addr"], 16)
            data = struct.pack(">I", labels[entry["ptr"]]) if "ptr" in entry else bytes.fromhex(entry["hex"])
            if a < 0x200 or a + len(data) > len(orig):
                sys.exit("patch at %06X (%d bytes) is outside the game's code/data" % (a, len(data)))
            rom[a:a + len(data)] = data
            patches += 1
        patches += len(labels)

    # 4. Header: ROM end address and checksum.
    rom[0x1A4:0x1A8] = struct.pack(">I", len(rom) - 1)
    words = struct.unpack(">%dH" % ((len(rom) - 0x200) // 2), rom[0x200:])
    rom[0x18E:0x190] = struct.pack(">H", sum(words) & 0xFFFF)

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "wb") as f:
        f.write(rom)
    write_ips(orig, rom, os.path.splitext(args.out)[0] + ".ips")
    for w in warnings:
        print("warning:", w)
    shown = ", ".join(edited_sheets[:12]) + (", ... (%d in all)" % len(edited_sheets) if len(edited_sheets) > 12 else "")
    print("Edited sheets: %s" % (shown or "none"))
    print("Edited images: %s" % (", ".join(edited_images) or "none"))
    print("Edited sounds: %s" % (", ".join(edited_sounds) or "none"))
    print("Edited text strings: %d" % edited_text)
    if patches:
        print("Raw patches applied: %d" % patches)
    print("Palette entries changed: %d%s; sprite blocks rewritten in place: %d, relocated: %d"
          % (pal_changes, " (%d sprite pieces requantized)" % len(base) if base else "", inplace, relocated))
    if layouts:
        print("Frames re-laid out with new sprite boxes: %d (%d moved to fit more sprites); %d kept their old boxes"
              % (len(layouts), moved_frames, len(layout_notes)))
        for n in layout_notes:
            print("  note:", n)
    print("Wrote %s (%d KB) and %s" % (args.out, len(rom) // 1024, os.path.splitext(args.out)[0] + ".ips"))
    if args.web:
        shutil.copyfile(args.out, args.web)
        print("Copied to %s" % args.web)


def cmd_scan(args):
    """List sprite animations that neither resources.cfg nor resources-extra.cfg knows about."""
    rom = load_rom(args.rom)
    cat = Catalog(rom, args.cfg)
    cfg = configparser.ConfigParser()
    cfg.read([args.cfg, EXTRA_CFG])
    known_lists = [(int(cfg[s]["address"], 0), int(cfg[s]["length"], 0)) for s in cfg.sections()
                   if cfg[s]["kind"] in ("METASPRITE_LIST", "SPRITE_LIST")]
    cache = {}

    def valid(a):
        if a not in cache:
            try:
                n = rom[a]
                ok = 1 <= n <= 8
                for i in range(n if ok else 0):
                    w, h, _, _, _, fl, d = struct.unpack(">BBbbbBI", rom[a + 4 + i * 10:a + 14 + i * 10])
                    if not (1 <= w <= 4 and 1 <= h <= 4) or fl & ~0xC3 or not (0x200 <= d < len(rom)) \
                            or abs(d - a) > 0x3000:
                        ok = False
                        break
                    decompress(rom, d, w * h * 32, fl)
            except Exception:
                ok = False
            cache[a] = ok
        return cache[a]

    runs, cur = [], []
    for off in range(0x200, len(rom) - 3, 2):
        v = struct.unpack(">I", rom[off:off + 4])[0]
        if 0x200 <= v < len(rom) and valid(v):
            if cur and off == cur[-1][0] + 4:
                cur.append((off, v))
            else:
                if cur:
                    runs.append(cur)
                cur = [(off, v)]
    if cur:
        runs.append(cur)
    found = 0
    for run in runs:
        start = run[0][0]
        if any(a <= start < a + n for a, n in known_lists) or all(v in cat.frames for _, v in run):
            continue
        found += 1
        print("[Spr_Unknown%06X]\nkind=METASPRITE_LIST\naddress=0x%08X\nlength=%d\n" % (start, start, len(run) * 4))
    print("; %d uncatalogued animation lists" % found)


def cmd_selftest(args):
    """Every sprite must survive decode -> encode -> decode, and our encoder should not lose to the original."""
    rom = load_rom(args.rom)
    cat = Catalog(rom, args.cfg)
    seen, bigger, total_old, total_new = set(), 0, 0, 0
    for f in cat.frames.values():
        for p in f.pieces:
            if p.data_addr in seen:
                continue
            seen.add(p.data_addr)
            assert p.encode(p.pixels()) == p.raw, "pixel codec mismatch at %06X" % p.data_addr
            blob = compress(p.raw, p.flags)
            back, _ = decompress(blob, 0, p.size, p.flags)
            assert back == p.raw, "compression round-trip failed at %06X" % p.data_addr
            total_old += p.zlen
            total_new += len(blob) + (len(blob) & 1)
            bigger += len(blob) > p.zlen
    print("%d sprite blocks OK. Original %d bytes, re-encoded %d bytes; %d blocks came out larger."
          % (len(seen), total_old, total_new, bigger))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rom", default=DEFAULT_ROM, help="original REV 02 ROM (default: rom/original.md)")
    ap.add_argument("--cfg", default=DEFAULT_CFG, help="tje-disasm resources.cfg")
    ap.add_argument("--assets", default=DEFAULT_ASSETS)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("extract")
    b = sub.add_parser("build")
    b.add_argument("--out", default=DEFAULT_OUT)
    b.add_argument("--web", help="also copy the built ROM here (e.g. web/mod.md, which the web player loads)")
    b.add_argument("--force-relocate", action="store_true", help="testing: move every edited sprite to the expansion area")
    b.add_argument("--requantize", action="store_true",
                   help="when a palette line changes, remap untouched sprites on it to their closest new colors")
    sub.add_parser("selftest")
    sub.add_parser("scan", help="find sprite animations missing from the catalog (prints cfg sections)")
    args = ap.parse_args()
    {"extract": cmd_extract, "build": cmd_build, "selftest": cmd_selftest, "scan": cmd_scan}[args.cmd](args)


if __name__ == "__main__":
    main()
