#!/usr/bin/env python3
"""Pin the sheet records and literals of the Continue / Game Over draw routines and the score digits."""
import hashlib
import json
import shutil
import struct
from pathlib import Path
from inspect_iso import Elf
from extract_collision_tables import SOURCE_HASH

ROOT = Path(__file__).resolve().parents[2]
NAME = 'arcade_art.bin'
# Textures the module reads; all are already packaged by earlier slices.
TEXTURES = ('obj0_16.tex', 'obj2_16.tex', 'font_coin.tex', 'font_otherscene16.tex', 'obj0.pal')

def build(raw):
    elf = Elf(raw)
    def chunk(at, size):
        offset = elf.offset(at); return raw[offset:offset+size]
    words = lambda at, count: struct.unpack(f'<{count}i', chunk(at, 4*count))
    word = lambda at: struct.unpack('<I', chunk(at, 4))[0]
    floats = lambda at, count: struct.unpack(f'<{count}f', chunk(at, 4*count))
    record = lambda at: words(at, 6)   # u, v, w, h, +0x10, texture slot
    # 137d40 (title), 137db8 (counter): record bases and the first literal of each routine.
    assert word(0x137d5c) == 0x24843bc8 and word(0x137e44) == 0x26ae3ad8 and word(0x137d4c) == 0x25ef1618
    # 138ba8 (text), 138c70 (title), 138b50 / 138e18 (flat rectangles).
    assert word(0x138c0c) == 0x24843be0 and word(0x138cbc) == 0x26703bf8
    assert word(0x138b70) == 0x25ef18a8 and word(0x138dc4) == 0x25ef18c8 and word(0x138e54) == 0x25ef190c
    # 1bc098 passes 4c5ae8 to 1ba768, which indexes it with (value / 10^i) % 10.
    assert word(0x1bc0a8) == 0x258c5ae8
    continue_title = record(0x4c3bc8)
    continue_digits = [record(0x4c3ad8+24*i) for i in range(10)]
    continue_floats = floats(0x5e1618, 11)
    over_text, over_title = record(0x4c3be0), record(0x4c3bf8)
    over_floats = floats(0x5e18a8, 7)
    over_shake = words(0x5e18c8, 16)
    over_tail = floats(0x5e1908, 7)
    # A negative score divides toward zero, so 1ba768 indexes the nine records in
    # front of the digit table (digit -9 .. -1).
    negative = [record(0x4c5ae8+24*i) for i in range(-9, 0)]
    for r in [continue_title, over_text, over_title]+continue_digits: assert r[5] == 12 and r[4] == 0, r
    assert all(r[5] == 10 for r in negative), negative
    assert len({(r[2], r[3]) for r in continue_digits}) == 1
    data = b'AART'+struct.pack('<I', 1)
    data += struct.pack('<6i', *continue_title)+b''.join(struct.pack('<6i', *r) for r in continue_digits)
    data += struct.pack('<11f', *continue_floats)
    data += struct.pack('<6i', *over_text)+struct.pack('<6i', *over_title)+struct.pack('<7f', *over_floats)
    data += struct.pack('<16i', *over_shake)+struct.pack('<7f', *over_tail)
    data += b''.join(struct.pack('<6i', *r) for r in negative)
    assert len(data) == 700
    layout = dict(continue_title_4c3bc8=[8, 6], continue_digits_4c3ad8=[32, 10, 6], continue_floats_5e1618=[272, 11],
                  game_over_text_4c3be0=[316, 6], game_over_title_4c3bf8=[340, 6], game_over_floats_5e18a8=[364, 7],
                  game_over_shake_5e18c8=[392, 16], game_over_floats_5e1908=[456, 7], score_negative_digits_4c5a10=[484, 9, 6])
    return data, dict(layout=layout, continue_floats=list(continue_floats), game_over_floats=list(over_floats)+list(over_tail),
                      game_over_shake=list(over_shake))

def main():
    raw = (ROOT/'work/ss6/extracted/SLPS_255.59').read_bytes()
    assert hashlib.sha256(raw).hexdigest() == SOURCE_HASH
    data, summary = build(raw)
    target = ROOT/'work/ss6/extracted/resources'/NAME
    target.write_bytes(data)
    assets = ROOT/'outputs/ss6-feasibility/native-viewer/assets'
    shutil.copyfile(target, assets/NAME)
    report = dict(elf_sha256=SOURCE_HASH, asset=NAME, bytes=len(data), sha256=hashlib.sha256(data).hexdigest(),
                  textures={name: hashlib.sha256((assets/name).read_bytes()).hexdigest() for name in TEXTURES}, **summary)
    (ROOT/'outputs/ss6-feasibility/arcade_art_tables.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2))

if __name__ == '__main__':main()
