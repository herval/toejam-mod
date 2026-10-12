"""tjmod's codecs and patch writer, on synthetic data (no ROM needed).

  python3 -m unittest discover tests
"""
import os
import pathlib
import random
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import tjmod  # noqa: E402

NODE = shutil.which("node")


def tiles(rng, n):
    """Sprite-like data: runs of transparency and solid color, some noise."""
    out = bytearray()
    while len(out) < n:
        kind = rng.random()
        if kind < 0.3:
            out += b"\x00" * rng.randint(1, 80)
        elif kind < 0.45:
            out += b"\xFF" * rng.randint(1, 80)
        elif kind < 0.7:
            out += bytes([rng.randrange(256)]) * rng.randint(1, 70)
        elif kind < 0.8:
            v = rng.randrange(256)
            out += bytes(v if k % 2 == 0 else tjmod.swapnib(v) for k in range(rng.randint(2, 40)))
        else:
            out += bytes(rng.randrange(256) for _ in range(rng.randint(1, 70)))
    return bytes(out[:n])


def apply_ips(orig, patch):
    """Independent reference IPS reader."""
    assert patch[:5] == b"PATCH"
    out, p = bytearray(orig), 5
    while patch[p:p + 3] != b"EOF":
        off = int.from_bytes(patch[p:p + 3], "big")
        size = int.from_bytes(patch[p + 3:p + 5], "big")
        p += 5
        if size:
            chunk = patch[p:p + size]
            p += size
        else:
            count, value = struct.unpack(">HB", patch[p:p + 3])
            chunk = bytes([value]) * count
            p += 3
        if off + len(chunk) > len(out):
            out += bytes(off + len(chunk) - len(out))
        out[off:off + len(chunk)] = chunk
    return bytes(out)


class Codec(unittest.TestCase):
    def test_token_semantics(self):
        # 0x02: copy 2 | 0xBD: 3 zeros (0xC0 - t) | 0xFE 12: 2 x 0x12 | 0x42: 2 x 0xFF
        stream = bytes([0x02, 0xAB, 0xCD, 0xBD, 0xFE, 0x12, 0x42])
        raw, zlen = tjmod.decompress(stream, 0, 9, 0)
        self.assertEqual(raw, bytes([0xAB, 0xCD, 0, 0, 0, 0x12, 0x12, 0xFF, 0xFF]))
        self.assertEqual(zlen, 8)  # rounded up to even
        # interleaved: 0x63 v alternates v / swapped nibbles
        self.assertEqual(tjmod._decode_stream(bytes([0x63, 0x1F]), 0, 3, True)[0], bytes([0x1F, 0xF1, 0x1F]))

    def test_round_trip(self):
        rng = random.Random(1991)
        for flags in (0, tjmod.FLAG_INTERLEAVED, tjmod.FLAG_UNCOMPRESSED):
            for _ in range(40):
                raw = tiles(rng, 32 * rng.randint(1, 16))
                packed = tjmod.compress(raw, flags)
                back, zlen = tjmod.decompress(packed + b"\x00", 0, len(raw), flags)
                self.assertEqual(back, raw)
                self.assertLessEqual(len(packed), zlen)

    def test_compression_helps(self):
        raw = b"\x00" * 200 + b"\x11" * 56
        self.assertLess(len(tjmod.compress(raw, 0)), 10)


class Sprites(unittest.TestCase):
    def test_piece_pixels_round_trip(self):
        rng = random.Random(7)
        w, h = 3, 2
        data = bytes(rng.randrange(256) for _ in range(w * h * 32))
        rom = bytearray(16) + data
        rom[0:10] = struct.pack(">BBbbbBI", w, h, -12, -16, 0, tjmod.FLAG_UNCOMPRESSED | 3, 16)
        p = tjmod.Piece(0, rom)
        self.assertEqual((p.w, p.h, p.x, p.y, p.pal), (3, 2, -12, -16, 3))
        px = p.pixels()
        self.assertEqual((len(px[0]), len(px)), (24, 16))
        self.assertEqual(p.encode(px), data)
        # tiles are column-major: the second tile is below the first
        self.assertEqual(px[8][0], data[32] >> 4)

    def test_colors(self):
        for c in range(0, 0x1000, 2):
            if c & 0x111:
                continue
            self.assertEqual(tjmod.rgb_to_cram(tjmod.cram_to_rgb(c)), c)


class Ips(unittest.TestCase):
    def write(self, orig, new):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "t.ips")
            tjmod.write_ips(orig, new, path)
            return pathlib.Path(path).read_bytes()

    def test_identical(self):
        rom = bytes(range(256)) * 64
        self.assertEqual(self.write(rom, rom), b"PATCHEOF")

    def test_edits_runs_and_growth(self):
        rng = random.Random(42)
        orig = bytes(rng.randrange(256) for _ in range(1 << 16))
        new = bytearray(orig)
        new[0:4] = b"\x01\x02\x03\x04"           # at offset 0
        new[100:200] = b"\xAA" * 100              # RLE record
        new[5000:5010] = bytes(range(10))         # literal record
        new += b"\xFF" * 70000 + b"tail"          # growth past 64 KB, records longer than 0xFFFF
        patch = self.write(orig, bytes(new))
        self.assertEqual(apply_ips(orig, patch), bytes(new))
        self.assertLess(len(patch), 200)

    def test_eof_offset(self):
        # A record starting at 0x454F46 would read as "EOF"; the writer must start one byte early.
        orig = bytes(0x454F46 + 16)
        new = bytearray(orig)
        new[0x454F46] = 1
        patch = self.write(orig, bytes(new))
        self.assertEqual(apply_ips(orig, patch), bytes(new))  # a stray "EOF" would end the patch early


@unittest.skipUnless(NODE, "node not installed")
class WebPlayer(unittest.TestCase):
    """The browser-side patcher (web/rom-tools.js) agrees with tjmod's IPS writer."""

    def node(self, script, *args):
        js = ("import * as t from %r;\nimport fs from 'node:fs';\nconst a = process.argv.slice(1);\n%s"
              % (pathlib.Path(ROOT, "web", "rom-tools.js").as_uri(), script))
        return subprocess.run([NODE, "--input-type=module", "-e", js, *args], capture_output=True, text=True, check=True)

    def test_apply_ips(self):
        rng = random.Random(3)
        orig = bytes(rng.randrange(256) for _ in range(300000))
        new = bytearray(orig)
        for _ in range(50):
            a, n = rng.randrange(len(new) - 300), rng.randint(1, 300)
            new[a:a + n] = tiles(rng, n)
        new = bytes(new) + bytes(rng.randrange(4) for _ in range(90000))
        with tempfile.TemporaryDirectory() as d:
            paths = [os.path.join(d, n) for n in ("orig", "t.ips", "out")]
            pathlib.Path(paths[0]).write_bytes(orig)
            tjmod.write_ips(orig, new, paths[1])
            self.node("fs.writeFileSync(a[2], t.applyIps(new Uint8Array(fs.readFileSync(a[0])), "
                      "new Uint8Array(fs.readFileSync(a[1]))));", *paths)
            self.assertEqual(pathlib.Path(paths[2]).read_bytes(), new)

    def test_unzip_and_sha1(self):
        rng = random.Random(5)
        rom = tiles(rng, 1 << 18)
        with tempfile.TemporaryDirectory() as d:
            for method in (zipfile.ZIP_DEFLATED, zipfile.ZIP_STORED):
                z = os.path.join(d, "rom.zip")
                with zipfile.ZipFile(z, "w", method) as f:
                    f.writestr("readme.txt", "not this one")
                    f.writestr("Game (World).md", rom)
                out = os.path.join(d, "out")
                self.node("const r = await t.unzip(new Uint8Array(fs.readFileSync(a[0]))); fs.writeFileSync(a[1], r);"
                          "console.log(await t.sha1(r));", z, out)
                self.assertEqual(pathlib.Path(out).read_bytes(), rom)
            plain = self.node("console.log((await t.unzip(new Uint8Array([1, 2, 3]))).length, await t.sha1(new Uint8Array()))")
            self.assertEqual(plain.stdout.split(), ["3", "da39a3ee5e6b4b0d3255bfef95601890afd80709"])


if __name__ == "__main__":
    unittest.main()
