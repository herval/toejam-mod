"""The Rick & Morty port's generators (no ROM needed).

Pose tests need out/sprites.json: cd ports/rick-and-morty && node dump_sprites.mjs out/sprites.json
"""
import os
import struct
import sys
import unittest

PORT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ports", "rick-and-morty")
sys.path.insert(0, PORT)
import boot  # noqa: E402
import music  # noqa: E402

SPRITES = os.path.join(PORT, "out", "sprites.json")


def parse(stream):
    """Walk one music track: returns (ticks of waiting, opcodes seen, loop target)."""
    ticks, ops, p = 0, set(), 0
    while True:
        op = stream[p]
        if op & 0x80:
            ticks += op & 0x7F
            p += 1
            continue
        ops.add(op)
        if op == 0x08:
            return ticks, ops, p + 3 + struct.unpack(">h", stream[p + 1:p + 3])[0]
        p += {0x01: 3, 0x02: 1, 0x04: 2, 0x0B: 1, 0x0C: 1}[op]


class Music(unittest.TestCase):
    def test_pitch(self):
        for midi in (40, 57, 69, 81):
            hi, lo = music.freq_bytes(midi)
            block, fnum = hi >> 3, ((hi & 7) << 8) | lo
            hz = fnum * music.FM_CLOCK / 144 / (1 << 20) * (1 << (block - 1))
            self.assertAlmostEqual(hz / (440 * 2 ** ((midi - 69) / 12)), 1, delta=0.003)

    def test_tracks_loop_in_time(self):
        for key in music.KEYS:
            for name, data in music.tracks(key).items():
                ticks, ops, target = parse(data)
                self.assertEqual(ticks, music.TOTAL, name)  # every voice loops on the same beat
                self.assertEqual(target, 0, name)
                self.assertTrue(ops <= {0x01, 0x02, 0x04, 0x08, 0x0B, 0x0C}, name)

    def test_patches_cover_every_song_slot(self):
        rom = bytes(0x100000)
        entries = music.patches(rom)
        table = {int(e["addr"], 16) for e in entries if "ptr" in e}
        for slot in list(range(6)) + list(range(7, 13)):
            self.assertIn(music.SONG_TABLE + slot * music.SLOT, table)


class Boot(unittest.TestCase):
    def test_logo(self):
        img = boot.render()
        self.assertEqual(img.size, (boot.COLS * 8, boot.ROWS * 8))
        lo, hi = img.getextrema()
        self.assertEqual((lo, hi), (0, 10))  # outline + 9 shine bands
        entries, tiles = boot.patches(bytes(0x100000))
        self.assertLessEqual(tiles, 0x400 // 2)  # stays clear of the font in VRAM
        cycle = next(e for e in entries if e.get("note", "").startswith("boot logo shine"))
        self.assertEqual(len(cycle["hex"]) // 4, boot.PALETTE_COUNT * 16)

    def test_green(self):
        self.assertEqual(boot.green(0x0E00), 0x00E0)  # blue -> green
        self.assertEqual(boot.green(0x000E), 0x000E)  # red stays


@unittest.skipUnless(os.path.exists(SPRITES), "run node dump_sprites.mjs out/sprites.json first")
class Poses(unittest.TestCase):
    def test_every_pose_renders(self):
        import poses
        for pose in ("run", "sneak", "teeter", "fall", "land", "pain", "leap", "dive", "climb", "throw",
                     "slingshot", "highfive", "covers", "read", "cheer", "hula", "shield", "swig"):
            for who in ("rick", "morty"):
                for view in ("down", "side", "up"):
                    art = poses.make(pose, who, view, 0)
                    self.assertGreater(art.img.getbbox()[2], 0, (pose, who, view))
                    self.assertLessEqual(max(art.w, art.h), 64, (pose, who, view))


if __name__ == "__main__":
    unittest.main()
