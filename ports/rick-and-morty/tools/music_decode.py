#!/usr/bin/env python3
"""Decode ToeJam & Earl (REV02) music data from the ROM.

Usage: python3 tools/music_decode.py ../../rom/original.md [dump|songs|patches|track ADDR]
"""
import struct, sys

ROM = None
SONG_TABLE = 0x3D696
SONG_STRIDE = 0xE4      # 6 channel structs x 0x26
CH_STRIDE = 0x26
PATCH_TABLE = 0x3BC04
PATCH_SIZE = 0x26
INSTR_MAP = 0x3C350     # 16 bytes per song: cmd 0x04 idx -> patch #
SFX_PTRS = 0x3C430
NAMES = ["Toejam Jammin'", "Big Earl Bump", "Rapmaster Rocket Racket",
         "Funkotronic Beat", "Alien Break Down", "Toejam Slowjam", "(6: elevator/special)"]

def u8(a): return ROM[a]
def s16(a): return struct.unpack('>h', ROM[a:a+2])[0]
def u32(a): return struct.unpack('>I', ROM[a:a+4])[0]

def fnum_to_note(hi, lo):
    block = (hi >> 3) & 7
    fnum = ((hi & 7) << 8) | lo
    if fnum == 0:
        return None
    # YM2612 NTSC: f = fnum * 7670454/144 / 2^(21-block)
    import math
    f = fnum * (7670454 / 144) / (2 ** (21 - block))
    midi = 69 + 12 * math.log2(f / 440)
    names = ['C','C#','D','D#','E','F','F#','G','G#','A','A#','B']
    m = round(midi)
    return f"{names[m%12]}{m//12-1}{'%+.0fc' % ((midi-m)*100) if abs(midi-m)>0.15 else ''}"

def decode_track(addr, song=None, maxbytes=20000, verbose=True):
    """Decode a command stream. Returns (events, stats)."""
    a = addr
    out = []
    ticks = 0
    stats = dict(notes=0, ticks_to_end=None, bytes=0)
    end = addr + maxbytes
    while a < end:
        b = u8(a); a += 1
        if b & 0x80:
            n = b & 0x7F
            out.append(f"wait {n}")
            ticks += n
        elif b == 0x00:
            out.append("END"); break
        elif b == 0x01:
            hi, lo = u8(a), u8(a+1); a += 2
            out.append(f"NOTE_ON {hi:02X}{lo:02X} ({fnum_to_note(hi,lo)})")
            stats['notes'] += 1
        elif b == 0x02:
            out.append("KEY_OFF")
        elif b == 0x03:
            hi, lo = u8(a), u8(a+1); a += 2
            out.append(f"FREQ {hi:02X}{lo:02X} ({fnum_to_note(hi,lo)})")
        elif b == 0x04:
            idx = u8(a); a += 1
            patch = u8(INSTR_MAP + 16*song + idx) if song is not None and song < 7 else None
            out.append(f"INSTR idx {idx} -> patch {patch}")
        elif b == 0x05:
            cnt = (u8(a) << 8) | u8(a+1); a += 2
            out.append(f"LOOP_START count={cnt}")
        elif b == 0x06:
            off = s16(a); a += 2
            out.append(f"LOOP_END rel={off} -> {a+1+off:06X}")
        elif b == 0x07:
            if a & 1: a += 1
            p = u32(a); a += 4
            out.append(f"SET_TICK_CALLBACK {p:06X}")
        elif b == 0x08:
            off = s16(a); a += 2
            out.append(f"JUMP rel={off} -> {a+off:06X}")
            break
        elif b == 0x09: out.append("PCM scratch")
        elif b == 0x0A: out.append("PCM clap")
        elif b == 0x0B: out.append("PCM bass drum")
        elif b == 0x0C: out.append("PCM snare")
        else:
            out.append(f"NOP? {b:02X}")
    stats['ticks'] = ticks
    stats['bytes'] = a - addr
    stats['end'] = a
    return out, stats

def songs():
    a = SONG_TABLE
    s = 0
    while u8(a) != 0xFF or u8(a+1) != 0xFF:
        print(f"--- song slot {s} @ {a:06X} {NAMES[s] if s < len(NAMES) else ''}")
        for c in range(6):
            e = a + c*CH_STRIDE
            p0, p1 = u32(e), u32(e+4)
            ch, prio, ins = u8(e+0xC), u8(e+0xD), u8(e+0xE)
            info = ''
            if p1:
                ev, st = decode_track(p1, song=s % 7 if s < 7 else None, verbose=False)
                info = f"len={st['bytes']}B notes={st['notes']} ticks/pass={st['ticks']} last={ev[-1]}"
            print(f"  ch{c}: ptr={p1:06X} hwch={ch} prio={prio:02X} instr={ins:02X} {info}")
        a += SONG_STRIDE
        s += 1
        if s > 20: break
    print(f"table terminator FFFF at {a:06X}")

def patches(n=49):
    for i in range(n):
        p = PATCH_TABLE + i*PATCH_SIZE
        b = ROM[p:p+PATCH_SIZE]
        print(f"patch {i:2d} @{p:06X}: LFO={b[0]:02X} CH3MODE={b[1]:02X} FB/ALG={b[2]:02X} LR/AMS/FMS={b[3]:02X} ops={b[4:28].hex()} ch3f={b[28:36].hex()} keyon={b[36]:02X} keyoff={b[37]:02X}")
    print("instrument map rows (song*16 + idx):")
    for r in range(8):
        print(f"  row {r}: {ROM[INSTR_MAP+16*r:INSTR_MAP+16*r+16].hex(' ')}")

if __name__ == '__main__':
    ROM = open(sys.argv[1], 'rb').read()
    cmd = sys.argv[2] if len(sys.argv) > 2 else 'songs'
    if cmd == 'songs': songs()
    elif cmd == 'patches': patches()
    elif cmd == 'track':
        addr = int(sys.argv[3], 16); song = int(sys.argv[4]) if len(sys.argv) > 4 else None
        ev, st = decode_track(addr, song=song)
        print("\n".join(ev)); print(st)
