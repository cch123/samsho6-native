#!/usr/bin/env python3
"""Pin the tables, literals and texts of the arcade result scenes.

Win quote 135e30 (background 135438 / 135de0, portrait 136500 / 1366e0, quote texts of 1a3070),
VS result 136a60 (1370c8), challenger banner 125c68, name entry overlay 1c9ec8 / 1ca248 and the
unlock notice 1e5d88 (texts 584f20).
"""
import hashlib
import json
import shutil
import struct
from pathlib import Path
from inspect_iso import Elf
from extract_collision_tables import SOURCE_HASH

ROOT = Path(__file__).resolve().parents[2]
NAME = 'arcade_results.bin'
ROWS = (0x4c96f0, 0x4c97e0, 0x4c98d0, 0x4c99c0, 0x4c9ab0, 0x4ca050, 0x4c9ba0, 0x4c9c90, 0x4c9d80, 0x4c9e70, 0x4c9f60)
# Sheets the scenes bind: slot 4 (two backgrounds), slot 8 (win_NN), slot 5 (faces), slot 0xc (digits).
TEXTURES = ['menu_bg00_00.tex', 'menu_bg01_00.tex', 'menu_bg01_00.pal', 'char_face_1024.tex', 'char_face_1024.pal',
            'font_otherscene2_16.tex', 'obj0.pal', 'obj0_16.tex', 'change_base16.tex']
TEXTURES += [f'win_{i:02d}.{ext}' for i in range(49) if i != 43 for ext in ('tex', 'pal')]


def build(raw):
    elf = Elf(raw)
    def chunk(at, size):
        offset = elf.offset(at); return raw[offset:offset+size]
    words = lambda at, count: struct.unpack(f'<{count}i', chunk(at, 4*count))
    word = lambda at: struct.unpack('<I', chunk(at, 4))[0]
    floats = lambda at, count: struct.unpack(f'<{count}f', chunk(at, 4*count))
    record = lambda at: words(at, 6)   # u, v, w, h, +0x10 flags, texture slot
    def text(at):
        offset = elf.offset(at); return raw[offset:raw.index(0, offset)]
    # 135438: first row table and the literals; 135de0: the single picture record.
    assert word(0x135444) == 0x258c96f0 and word(0x135454) == 0x25ce1024 and word(0x135df0) == 0x2484a140
    # 1364a8 / 136500 / 1366e0 / 136930 / 1369b0 literals 5e1188..5e11e0.
    assert word(0x1364c8) == 0x25ef1188 and word(0x136a04) == 0x25ef11e0
    # 1a3070: table 50d550 (system byte 43d052 == 0) and 50d618.
    assert word(0x1a3098) == 0x25efd550 and word(0x1a3160) == 0x25efd618
    # 136a60 / 1370c8.
    assert word(0x136aa4) == 0x25ef1230 and word(0x13717c) == 0x26103c10 and word(0x1372c8) == 0x24843d18
    assert word(0x1373bc) == 0x25f73d30 and word(0x1373d4) == 0x25fe1360 and word(0x137618) == 0x25ce14c8
    # 125c68.
    assert word(0x125cc8) == 0x26105188 and word(0x125cc4) == 0x25effc18
    # 1e5df0 / 1e63c8 / 1e64a8.
    assert word(0x1e5fc4) == 0x26314f20 and word(0x1e63d4) == 0x25efca90 and word(0x1e653c) == 0x25ceca94

    data = bytearray(b'ARES'+struct.pack('<I', 1))
    layout = {}
    def put(name, blob):
        layout[name] = [len(data), len(blob)]; data.extend(blob)
    put('background_floats_5e1024', struct.pack('<6f', *floats(0x5e1024, 6))+struct.pack('<f', *floats(0x5e106c, 1)))
    rows = [[record(base+24*i) for i in range(10)] for base in ROWS]
    for row in rows:
        assert all(r[5] == 4 and r[2] == 83 for r in row), row
    put('background_rows', b''.join(struct.pack('<6i', *r) for row in rows for r in row))
    picture = record(0x4ca140); assert picture[5] == 4
    put('background_picture_4ca140', struct.pack('<6i', *picture))
    put('quote_floats_5e1188', struct.pack('<23f', *floats(0x5e1188, 23)))
    put('result_floats_5e1230', struct.pack('<7f', *floats(0x5e1230, 7)))
    put('result_floats_5e14b0', struct.pack('<6f', *floats(0x5e14b0, 6)))
    put('result_shake_5e14c8', struct.pack('<16i', *words(0x5e14c8, 16)))
    put('result_floats_5e1508', struct.pack('<5f', *floats(0x5e1508, 5)))
    digits = [record(0x4c3c10+24*i) for i in range(10)]
    label, mark = record(0x4c3d18), record(0x4c3d30)
    assert all(r[5] == 12 for r in digits+[label, mark])
    put('result_digits_4c3c10', b''.join(struct.pack('<6i', *r) for r in digits))
    # A streak of zero before frame 0x64 shows -1: digit -1 indexes the record in front of the table.
    put('result_digit_before_4c3bf8', struct.pack('<6i', *record(0x4c3bf8)))
    put('result_label_4c3d18', struct.pack('<6i', *label)); put('result_mark_4c3d30', struct.pack('<6i', *mark))
    # 5e1360: {slot, column, row} halfwords per character; the table ends where the debug strings start.
    faces = struct.unpack('<156h', chunk(0x5e1360, 312))
    assert all(faces[3*i] == 5 for i in range(52)), faces
    put('result_faces_5e1360', struct.pack('<156h', *faces))
    banner = [record(0x4c5188), record(0x4c51a0)]; assert all(r[5] == 1 for r in banner)
    put('banner_records_4c5188', b''.join(struct.pack('<6i', *r) for r in banner))
    put('banner_floats_5dfc18', struct.pack('<3f', *floats(0x5dfc18, 3)))
    entry_digits = [record(0x4c40d8+24*i) for i in range(10)]
    back, end = record(0x4c5350), record(0x4c5368)
    assert all(r[5] == 1 for r in entry_digits+[back, end])
    put('entry_digits_4c40d8', b''.join(struct.pack('<6i', *r) for r in entry_digits))
    put('entry_back_4c5350', struct.pack('<6i', *back)); put('entry_end_4c5368', struct.pack('<6i', *end))
    put('entry_floats_655770', struct.pack('<4f', *floats(0x655770, 4)))
    assert text(0x655748) == b'_' and text(0x655768) == b'NAME>'
    # 1c1528 (frame edges) submits at the depth 654d84.
    assert word(0x1c169c) == 0x24634d84
    put('unlock_floats_65ca90', struct.pack('<2f', *floats(0x65ca90, 2))+struct.pack('<f', *floats(0x654d84, 1)))
    notices = [text(at) for at in struct.unpack('<16I', chunk(0x584f20, 64))]
    blob = bytearray()
    for item in notices:
        blob.extend(struct.pack('<H', len(item))+item)
    put('unlock_texts_584f20', bytes(blob))
    # Quotes: 49 characters x 16 records of up to three lines (record +8, +c, +10).
    def quotes(table, characters=49):
        out = bytearray(); count = empty = 0
        for character in range(49):
            base = word(table+4*character)
            for q in range(16):
                lines = []
                if character != 43 and character < characters and base:
                    rec = word(base+0xd8+4*q)
                    # Unused indices hold a null record; 1a2870 stops at the first null line.
                    for i in range(3 if rec else 0):
                        ptr = word(rec+8+4*i)
                        if not ptr: break
                        lines.append(text(ptr))
                    assert all(lines), (character, q)
                    empty += not lines
                out.append(len(lines))
                for line in lines:
                    line.decode('cp932'); out.append(len(line)); out.extend(line); count += 1
        return bytes(out), (count, empty)
    japanese, lines = quotes(0x50d550)
    put('quotes_50d550', japanese)
    # 50d618 (system byte 43d052 != 0): English lines for characters 0..42 only; entry 43
    # is null and 44..48 lie past the table (match_ending.cpp rejects them as well).
    alternate, alternate_lines = quotes(0x50d618, 43)
    put('quotes_50d618', alternate)
    summary = dict(layout=layout, quote_lines=lines[0], null_quote_records=lines[1], alternate_quote_lines=alternate_lines[0],
                   unlock_texts=[t.decode('cp932') for t in notices],
                   quote_floats=list(floats(0x5e1188, 23)))
    return bytes(data), summary


def main():
    raw = (ROOT/'work/ss6/extracted/SLPS_255.59').read_bytes()
    assert hashlib.sha256(raw).hexdigest() == SOURCE_HASH
    data, summary = build(raw)
    resources = ROOT/'work/ss6/extracted/resources'
    target = resources/NAME
    target.write_bytes(data)
    assets = ROOT/'outputs/ss6-feasibility/native-viewer/assets'
    shutil.copyfile(target, assets/NAME)
    copied = []
    for name in TEXTURES:
        if not (assets/name).exists() or (assets/name).read_bytes() != (resources/name).read_bytes():
            shutil.copyfile(resources/name, assets/name); copied.append(name)
    report = dict(elf_sha256=SOURCE_HASH, asset=NAME, bytes=len(data), sha256=hashlib.sha256(data).hexdigest(),
                  textures={name: hashlib.sha256((assets/name).read_bytes()).hexdigest() for name in TEXTURES},
                  textures_copied_by_this_run=copied, **summary)
    (ROOT/'outputs/ss6-feasibility/arcade_results_tables.json').write_text(json.dumps(report, indent=2, ensure_ascii=False)+'\n')
    print(json.dumps({k: v for k, v in report.items() if k not in ('textures', 'layout', 'unlock_texts')}, indent=1))

if __name__ == '__main__':main()
