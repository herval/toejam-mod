#!/usr/bin/env python3
"""Refuse to publish game data: fails if git would commit a ROM or extracted assets.

  python3 tools/check_no_rom.py            # every tracked file
  python3 tools/check_no_rom.py --staged   # what's about to be committed (the pre-commit hook)

A Genesis ROM is recognized by its header ("SEGA" at 0x100), whatever its name.
Genesis ROMs use .md like Markdown, so names alone can't tell them apart.
"""
import hashlib
import re
import subprocess
import sys

REV02_SHA1 = "85e8d0a4fac591b25b77c35680ac4175976f251b"
# Folders that only ever hold extracted or built game data (see .gitignore).
GAME_DATA = re.compile(r"^(ports/[^/]+/)?(rom|assets|build)/|^examples/demo-assets/")


def git(*args):
    return subprocess.run(["git", *args], capture_output=True, check=True).stdout


def problem(path, data):
    if GAME_DATA.match(path):
        return "is in a folder that only holds extracted or built game data"
    if data[0x100:0x104] == b"SEGA":
        return "looks like a Genesis ROM (SEGA header at 0x100)"
    if hashlib.sha1(data).hexdigest() == REV02_SHA1:
        return "is the ToeJam & Earl ROM"
    return None


def main():
    staged = "--staged" in sys.argv[1:]
    if staged:
        paths = git("diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z").decode().split("\0")
    else:
        paths = git("ls-files", "-z").decode().split("\0")
    bad = []
    for path in filter(None, paths):
        try:
            data = git("show", ":" + path) if staged else open(path, "rb").read()
        except (OSError, subprocess.CalledProcessError):
            continue  # submodules and deleted files
        why = problem(path, data)
        if why:
            bad.append("  %s: %s" % (path, why))
    if bad:
        print("Not committing game data:\n" + "\n".join(bad), file=sys.stderr)
        print("Share .ips patches instead (see README.md).", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
