"""No game data in the repository (the same check the pre-commit hook runs)."""
import os
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import check_no_rom  # noqa: E402


class GameData(unittest.TestCase):
    def test_detects_roms_and_assets(self):
        rom = bytearray(0x400)
        rom[0x100:0x110] = b"SEGA GENESIS    "
        self.assertIsNotNone(check_no_rom.problem("notes.md", bytes(rom)))
        self.assertIsNotNone(check_no_rom.problem("assets/sprites/Spr_ToejamIdle.png", b"png"))
        self.assertIsNotNone(check_no_rom.problem("ports/rick-and-morty/build/x.ips", b"PATCH"))
        self.assertIsNone(check_no_rom.problem("README.md", b"# toejam-mod\n" * 40))
        self.assertIsNone(check_no_rom.problem("web/patches/rick-and-morty.ips", b"PATCH" + bytes(0x200)))

    @unittest.skipUnless(os.path.isdir(os.path.join(ROOT, ".git")), "not a git checkout")
    def test_tracked_files_are_clean(self):
        r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "check_no_rom.py")],
                           cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)


if __name__ == "__main__":
    unittest.main()
