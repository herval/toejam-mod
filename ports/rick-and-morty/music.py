"""Schwifty Jam's groove as ToeJam & Earl music.

ToeJam & Earl's music is a plain frame-timed sequencer (0x3ED6E, one tick per VBlank),
so new songs are just new command streams:
    0x80|n wait n ticks   0x01 hi lo key-on at a YM2612 block/F-number   0x02 key-off
    0x04 i instrument = map[0x3C350 + 16*slot + i]   0x08 rel16 jump back (loop)
    0x0B / 0x0C PCM kick / snare through the Z80 sample driver
The song table (0x3D696) has 15 slots of six 0x26-byte channel structs; slots 0-5 are
the level songs (level n plays slot (n-1) mod 6), 7-12 their "breakdowns" (also Jam
Out's backing tracks). Format decoded with a byte-identical round trip of all 42
original tracks; the groove is game.js lines 94-114 (104 BPM, 128 sixteenth steps).

All new tracks go to the expansion area; the song table and instrument rows are patched
to point at them, so the original music data stays where it was.
"""
import struct

FM_CLOCK = 7670454  # NTSC YM2612
SONG_TABLE, SLOT, CHANNEL = 0x3D696, 0xE4, 0x26
INSTRUMENT_ROWS = 0x3C350  # 16 bytes per slot

# Patch numbers from the original songs: 4 = bass (slot 0 ch0, slot 1 ch4),
# 2 = melodic lead (slot 0 ch3, notes 53-70), 8 = chord voice (slot 0 ch4/5).
BASS_PATCH, LEAD_PATCH, CHORD_PATCH = 4, 2, 8
KEYS = [0, 5, -2, 3, -4, 7]  # transposition per level song, for some variety

# Schwifty Jam (game.js): bass, Em7/D7 stabs, a lead in alternate blocks, kick + snare
BASS = [40, 0, 40, 52, 0, 43, 0, 45, 40, 0, 47, 0, 45, 43, 40, 38,
        40, 0, 40, 52, 0, 43, 0, 45, 47, 0, 50, 0, 52, 50, 47, 45]
CHORDS = [[64, 67, 71, 74], [62, 66, 69, 72]]
LEAD = [0] * 16 + [76, 0, 0, 79, 0, 0, 76, 0, 74, 0, 71, 0, 0, 0, 0, 0]
BPM, STEPS = 104, 128
STEP = 3600 / BPM / 4  # ticks per sixteenth at 60 Hz


def _tick(k):
    return round(k * STEP)


TOTAL = _tick(STEPS)


def freq_bytes(midi):
    """MIDI note -> YM2612 block/F-number bytes (F-number in the 0x400-0x7FF sweet spot)."""
    f = 440 * 2 ** ((midi - 69) / 12)
    for block in range(1, 8):
        fnum = round(f * 144 * (1 << 20) / FM_CLOCK / (1 << (block - 1)))
        if 0x400 <= fnum < 0x800 or block == 7:
            return bytes([(block << 3) | (fnum >> 8), fnum & 0xFF])


def _waits(n):
    out = bytearray()
    while n > 0:
        k = min(n, 127)
        out.append(0x80 | k)
        n -= k
    return out


def _stream(events, instrument=None):
    """[(tick, "note", midi, length) | (tick, "pcm", "kick"|"snare")] -> a looping track."""
    out = bytearray()
    if instrument is not None:
        out += bytes([0x04, instrument])
    t = 0
    for ev in events:
        if ev[0] > t:
            out += _waits(ev[0] - t)
            t = ev[0]
        if ev[1] == "note":
            out += b"\x01" + freq_bytes(ev[2]) + _waits(ev[3]) + b"\x02"
            t += ev[3]
        else:
            out.append({"kick": 0x0B, "snare": 0x0C}[ev[2]])
    assert t <= TOTAL
    out += _waits(TOTAL - t)
    out += b"\x08" + struct.pack(">h", -(len(out) + 3))  # jump back to the start
    return bytes(out)


def _mono(events):
    """One note at a time per FM channel: cut each note a tick before the next."""
    out = []
    for j, e in enumerate(events):
        nxt = events[j + 1][0] if j + 1 < len(events) else TOTAL
        out.append((e[0], e[1], e[2], max(1, min(e[3], nxt - e[0] - 1))))
    return out


def tracks(transpose):
    bass, lead, chords, drums = [], [], [[], [], []], []
    for k in range(STEPS):
        i, block = k % 32, k // 32
        if BASS[i]:
            bass.append((_tick(k), "note", BASS[i] + (5 if block == 3 else 0) + transpose, max(1, round(STEP * 0.85))))
        if i % 8 == 0 or i % 16 == 10:
            drums.append((_tick(k), "pcm", "kick"))
        elif i % 8 == 4:
            drums.append((_tick(k), "pcm", "snare"))
        if i % 8 == 6 or i % 16 == 3:
            for v, n in enumerate(CHORDS[block % 2][1:]):  # the bass has the root
                chords[v].append((_tick(k), "note", n + transpose, max(1, round(STEP * 0.7))))
        if LEAD[i] and block % 2 == 1:
            lead.append((_tick(k), "note", LEAD[i] + transpose, round(STEP * 2.4)))
    return {
        "bass": _stream(_mono(bass), 0),
        "lead": _stream(_mono(lead), 1),
        "chord0": _stream(_mono(chords[0]), 2),
        "chord1": _stream(_mono(chords[1]), 2),
        "chord2": _stream(_mono(chords[2]), 2),
        "drums": _stream(drums),
    }


def patches(rom):
    """tjmod patch entries: new tracks + song table pointers + instrument rows."""
    out = []
    row = bytes([BASS_PATCH, LEAD_PATCH, CHORD_PATCH]) + bytes(13)
    for song, key in enumerate(KEYS):
        t = tracks(key)
        for name, data in t.items():
            out.append({"label": "song%d_%s" % (song, name), "hex": data.hex()})
        # level song: bass, lead, three chord voices, PCM drums
        # breakdown (between loops, and Jam Out's backing): no lead, one chord voice less
        for slot, layout in ((song, ["bass", "lead", "chord0", "chord1", "chord2", "drums"]),
                             (song + 7, ["bass", None, "chord0", "chord1", None, "drums"])):
            for ch, name in enumerate(layout):
                e = SONG_TABLE + slot * SLOT + ch * CHANNEL
                if name:
                    out += [{"addr": "%06X" % e, "ptr": "song%d_%s" % (song, name)},
                            {"addr": "%06X" % (e + 4), "ptr": "song%d_%s" % (song, name)}]
                else:
                    out.append({"addr": "%06X" % e, "hex": "00" * 8, "note": "channel off"})
            out.append({"addr": "%06X" % (INSTRUMENT_ROWS + 16 * slot), "hex": row.hex(), "note": "instruments"})
    return out
