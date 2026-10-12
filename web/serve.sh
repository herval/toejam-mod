#!/bin/sh
# Serve the web player locally (the ROM must come over http, not file://).
# If rom/original.md exists, it's offered as rom.md, so the mods are one click away.
cd "$(dirname "$0")" || exit 1
[ -f ../rom/original.md ] && [ ! -e rom.md ] && ln -s ../rom/original.md rom.md
echo "ToeJam & Earl mod player → http://localhost:${1:-8077}"
exec python3 -m http.server "${1:-8077}" --bind 127.0.0.1
