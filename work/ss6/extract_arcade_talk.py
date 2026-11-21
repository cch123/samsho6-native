#!/usr/bin/env python3
"""Pin the tables, literals and Shift-JIS texts of the arcade opening (1c60c8), the stage
dialogue (1c5290) and the pre-final demo (1c6cc0), plus the glyph rows their texts use.

arcade_talk.bin layout (little endian):
  'ATLK', u32 version
  f32[14]  60a050..60a084   portrait backings / portrait quads / balloon depths
  f32[10]  655398..6553bc   opening camera (entry) and 1c6a68 camera
  f32[5]   655350..655360   dialogue camera
  i32[2]   655378, 65537c   dialogue object actions
  f32[5]   655380..655390   pan start, flash depth, pan step, pan limit, pan x
  f32[5]   6553c8..6553d8   pre-final camera
  f32[29]  655420..655490   pre-final literals
  i32[4][6] sheet records 4c66a0, 4c67d8, 4c67f0, 4c6808 {u, v, w, h, +10, slot}
  i32[6][9] balloon records 4eeef8 {slot, x, y, u, v, w, h, text x, text y}
  u64[45]  the double returned by the C library routine 30bd00 for the 45 steps of 1c7a30
  u32 count, count x {u16 length, bytes}             string pool (Shift-JIS, verbatim)
  u32 count, count x {i32 balloon, i32 string[4]}    message lists (0x18-byte records; -1 = null)
  2 x {u32 count, i32 string[count]}                 opening lines 4efc10 (5) / 4ff6f0 (7)
  2 x {49 x {i32 group0, i32 list[6][4]}, i32 kind[5][4]}   tables 50d550 + 50d828 / 50d618 + 50d840
  u32 count, count x {u16 record, u8[288]}           GOTH_24 rows of the texts (no text holds a
                                                     single-byte character other than none at all)
"""
import hashlib
import json
import shutil
import struct
from pathlib import Path

from inspect_iso import Elf
from extract_collision_tables import SOURCE_HASH
from extract_versus_quotes import ISO_PATH, Iso
from mips_probe import Probe
from finite_float import arithmetic, rounded

ROOT = Path(__file__).resolve().parents[2]
NAME = 'arcade_talk.bin'
PORTRAITS = [n for n in range(49) if n != 43]
TEXTURES = tuple(f'demo_{n:02d}.{ext}' for n in PORTRAITS for ext in ('tex', 'pal'))+(
    'hukidasi.tex', 'hukidasi2.tex', 'moji4.tex', 'moji5.tex', 'demo_mga.tex', 'demo_mga.pal')
RESIDENT = ('obj0.pal',)


def build(raw, iso=None):
    elf = Elf(raw)
    def chunk(at, size):
        offset = elf.offset(at); return raw[offset:offset+size]
    words = lambda at, count: struct.unpack(f'<{count}i', chunk(at, 4*count))
    word = lambda at: struct.unpack('<I', chunk(at, 4))[0]
    def text(at):
        offset = elf.offset(at); return raw[offset:raw.index(0, offset)]
    # Anchors: the instructions that name each table.
    assert word(0x1c6244) == 0x25f1fc10 and word(0x1c62d0) == 0x25f1f6f0          # 1c6208: 4efc10 / 4ff6f0
    assert word(0x1a3098) == 0x25efd550 and word(0x1a3160) == 0x25efd618          # 1a3070: 50d550 / 50d618
    assert word(0x1a31f4) == 0x25efd828 and word(0x1a3218) == 0x25efd840          # 1a31e0: 50d828 / 50d840
    assert word(0x1a2724) == 0x25efeef8 and word(0x1a22b4) == 0x25efa050          # 1a26b0: 4eeef8; 1a22a8: 60a050
    assert word(0x1c6f64) == 0x25f066a0 and word(0x1c6f74) == 0x25d267d8          # 1c6e58: 4c66a0 / 4c67d8
    assert word(0x1c7900) == 0x261067f0 and word(0x1c7918) == 0x26716808          # 1c7848: 4c67f0 / 4c6808
    for at, name in ((0x6553e0, 'demo_mga.pvr'), (0x6553f0, 'moji4.pvr'), (0x655400, 'moji5.pvr'), (0x655410, 'demo_mga.pvp'),
                     (0x5f3f78, 'hukidasi.pvr'), (0x5f3f88, 'hukidasi2.pvr')):
        if name: assert elf.cstring(at) == name, (hex(at), elf.cstring(at))
    assert elf.cstring(0x60a030) == 'demo_%02d.pvr' and elf.cstring(0x60a040) == 'demo_%02d.pvp'
    assert words(0x4c6804, 1) == (5,) and words(0x4c66b4, 1) == (12,) and words(0x4c67ec, 1) == (13,)

    out = bytearray(b'ATLK'+struct.pack('<I', 1))
    out += chunk(0x60a050, 56)+chunk(0x655398, 40)+chunk(0x655350, 20)+chunk(0x655378, 8)+chunk(0x655380, 20)
    out += chunk(0x6553c8, 20)+chunk(0x655420, 116)
    records = [words(at, 6) for at in (0x4c66a0, 0x4c67d8, 0x4c67f0, 0x4c6808)]
    for r in records: out += struct.pack('<6i', *r)
    balloons = [words(0x4eeef8+0x24*k, 9) for k in range(6)]
    assert [b[0] for b in balloons[1:]] == [0x1f, 0x1f, 0x1f, 0x20, 0x20]
    for b in balloons: out += struct.pack('<9i', *b)

    # 1c7a30: argument = f20 - n * f23 / f22 * f21 in single precision (655484..655490), widened
    # by 310be0 and passed to 30bd00. The 45 results are pinned by executing the original routine.
    pi, steps, half, quarter = struct.unpack('<4I', chunk(0x655484, 16))
    assert struct.unpack('<f', struct.pack('<I', steps))[0] == 45.0 and word(0x1c7a68) == 0x2a0f002d
    probe = Probe(raw, finite_model=True); sine = []; instructions = 0
    for n in range(1, 46):
        # EE single-precision operations in the finite model of the project (finite_float.py).
        argument = arithmetic('sub', quarter, arithmetic('mul', arithmetic('div', arithmetic('mul', rounded(n), pi), steps), half))
        probe.floats[12] = argument
        wide, count = probe.run(0x310be0, [], limit=10000); instructions += count
        value, count = probe.run(0x30bd00, [wide], limit=200000); instructions += count
        sine.append(value & 0xffffffffffffffff)
    values = [struct.unpack('<d', struct.pack('<Q', v))[0] for v in sine]
    # cos(2 degrees) at the first step; the last argument is the single-precision residue of pi/2 - pi/2.
    assert abs(values[0]-0.9993908270190958) < 1e-9 and 0 < values[-1] < 1e-6 and values == sorted(values, reverse=True)
    out += struct.pack('<45Q', *sine)

    strings = {}; pool = []
    def string(at):
        if at == 0: return -1
        if at not in strings:
            data = text(at); data.decode('cp932'); strings[at] = len(pool); pool.append(data)
        return strings[at]
    lists = {}; rows = []
    def message(at):
        if at == 0: return -1
        if at not in lists:
            balloon, _, *pointers = struct.unpack('<2i4I', chunk(at, 24))
            lists[at] = len(rows); rows.append((balloon, *[string(p) for p in pointers]))
        return lists[at]
    opening = [[string(p) for p in struct.unpack(f'<{n}I', chunk(at, 4*n))] for at, n in ((0x4efc10, 5), (0x4ff6f0, 7))]
    versions = []
    for table, kinds in ((0x50d550, 0x50d828), (0x50d618, 0x50d840)):
        characters = []
        for character in range(49):
            block = word(table+4*character)
            # 1a3070 returns 0 for character 43. Rows 43..48 of the alternate table 50d618 are not
            # pointers (0, 0xc, 2, 0x19, 0x1f, 0x24): the original would dereference them.
            if character == 43 or block < 0x4e0000:
                assert character == 43 or (table == 0x50d618 and character > 43)
                characters.append([-1]*25); continue
            row = [message(word(block))]
            for group in range(3, 9):
                base = word(block+0x118+4*(group-3))
                # Reachable records only: group 4 (stage 4, post-fight) has three pages; groups 7 and 8
                # are indexed by the boss kind 0..3 (1c5dc0).
                row += [message(base+0x18*n) if base and not (group == 4 and n == 3) else -1 for n in range(4)]
            characters.append(row)
        # 1a31e0: kinds 0..3 pages 0..2 (stage 6 pre-fight), kind 4 pages 0..2 (pre-final demo).
        kind_rows = [[message(word(kinds+4*k)+0x18*page) if page < 3 else -1 for page in range(4)] for k in range(5)]
        versions.append((characters, kind_rows))
    out += struct.pack('<I', len(pool))
    for data in pool: out += struct.pack('<H', len(data))+data
    out += struct.pack('<I', len(rows))
    for row in rows: out += struct.pack('<5i', *row)
    for line in opening: out += struct.pack('<I', len(line))+struct.pack(f'<{len(line)}i', *line)
    for characters, kind_rows in versions:
        for row in characters: out += struct.pack('<25i', *row)
        for row in kind_rows: out += struct.pack('<4i', *row)

    # Glyph rows: 1131d8 -> 10a1c0 looks the two-byte code up in 3aa168 and copies 24 rows of
    # 12 bytes from GOTH_24.BIN (+0xc of a 312-byte record), as extract_menu_canvas.py does.
    iso = iso or Iso(ISO_PATH)
    half_sheet = iso.read('/BIN/GOTH_H.BIN'); large = iso.read('/BIN/GOTH_24.BIN')
    assert len(half_sheet) == 32768
    index = struct.unpack(f'<{42*192}I', chunk(0x3aa168, 4*42*192))
    used = set(); single = set()
    for data in pool:
        i = 0
        while i < len(data):
            ch = data[i]
            if ch < 0x80:
                assert ch == 0x20, (hex(ch), data)   # 1130f8 -> 10a010 half-width path
                single.add(ch); i += 1; continue
            trail = data[i+1]; lead = (ch-0x40 if ch >= 0xa0 else ch)-0x81
            used.add(index[lead*192+trail-0x40]); i += 2
    assert not single
    out += struct.pack('<I', len(used))
    for record in sorted(used): out += struct.pack('<H', record)+large[record*312+12:record*312+300]
    summary = dict(strings=len(pool), message_lists=len(rows), glyph_rows=len(used), single_byte_characters=sorted(chr(c) for c in single),
                   sine_instructions=instructions, opening_lines=[[pool[i].decode('cp932') for i in line] for line in opening],
                   sheet_records=[list(r) for r in records], balloons=[list(b) for b in balloons],
                   fonts={n: hashlib.sha256(d).hexdigest() for n, d in (('GOTH_H.BIN', half_sheet), ('GOTH_24.BIN', large))})
    return bytes(out), summary


def main():
    raw = (ROOT/'work/ss6/extracted/SLPS_255.59').read_bytes()
    assert hashlib.sha256(raw).hexdigest() == SOURCE_HASH
    data, summary = build(raw)
    resources = ROOT/'work/ss6/extracted/resources'; assets = ROOT/'outputs/ss6-feasibility/native-viewer/assets'
    (resources/NAME).write_bytes(data); shutil.copyfile(resources/NAME, assets/NAME)
    for name in TEXTURES: shutil.copyfile(resources/name, assets/name)
    report = dict(elf_sha256=SOURCE_HASH, asset=NAME, bytes=len(data), sha256=hashlib.sha256(data).hexdigest(),
                  textures={name: hashlib.sha256((assets/name).read_bytes()).hexdigest() for name in TEXTURES+RESIDENT}, **summary)
    (ROOT/'outputs/ss6-feasibility/arcade_talk_tables.json').write_text(json.dumps(report, indent=2, ensure_ascii=False)+'\n')
    print(json.dumps({k: v for k, v in report.items() if k != 'textures'}, indent=2, ensure_ascii=False)[:3000])

if __name__ == '__main__': main()
