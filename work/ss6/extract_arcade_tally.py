#!/usr/bin/env python3
"""Pin the arcade score tables, the state-9 tally labels and the arcade HUD layout words."""
import hashlib
import json
import shutil
import struct
from pathlib import Path
from inspect_iso import Elf
from extract_collision_tables import SOURCE_HASH

ROOT = Path(__file__).resolve().parents[2]
NAME = 'arcade_tally.bin'
LABELS = [('FINISH', 0x6554c0), ('TIME', 0x6554c8), ('PERFECT', 0x6554d0), ('LIFE', 0x6554d8),
          ('RULE', 0x6554e0), ('STRAIGHT', 0x6554f8), ('TOTAL', 0x655508)]

def build(raw):
    elf = Elf(raw)
    def chunk(at, size):
        offset = elf.offset(at); return raw[offset:offset+size]
    words = lambda at, count: struct.unpack(f'<{count}i', chunk(at, 4*count))
    word = lambda at: struct.unpack('<I', chunk(at, 4))[0]
    # 1c97c0 indexes 655588 and 1c97f0 indexes 6555e8; both are reached only
    # through the seat gates 14e838 and 14e8d8.
    assert word(0x1c97c8) == 0x25ef5588 and word(0x1c97f8) == 0x25ef55e8
    assert word(0x14e8bc) == 0x08000000 | 0x1c97c0 >> 2 and word(0x14e914) == 0x08000000 | 0x1c97f0 >> 2
    award, finish = words(0x655588, 24), words(0x6555e8, 6)
    assert chunk(0x6554b8, 3) == b'%d\0'
    labels = []
    for name, at in LABELS:
        text = chunk(at, 24).split(b'\0')[0]
        if name != 'RULE': assert text.decode() == name
        labels.append(text)
    assert labels[4] == b'- - - - - - - - - -'
    # 1bc098: x = word[58224c + 4*mode], digit records 4c5ae8 (u, v, w, h, 0, texture slot).
    score_x = words(0x582250, 2)
    digits = [words(0x4c5ae8+24*i, 6) for i in range(10)]
    # 1c8bf8..1c95a0 build the panel from five 16x16 pieces and 30 float literals.
    pieces = [words(0x4c5110+24*i, 6) for i in range(5)]
    floats = struct.unpack('<30f', chunk(0x655510, 120))
    # Free-seat prompt: demo (x, y, records), demo latched, then per seat ordinary and latched.
    demo, demo_latched = words(0x654790, 3), words(0x6547a0, 3)
    seat, seat_latched = words(0x6547b0, 6), words(0x6547c8, 6)
    assert demo[2] == seat[2] == seat[5] == 0x4c3ec8 and demo_latched[2] == seat_latched[2] == seat_latched[5] == 0x4c3f10
    depth = struct.unpack('<3f', chunk(0x654778, 4)+chunk(0x6547ac, 4)+chunk(0x6547e0, 4))
    assert depth == (-600.0, -600.0, -600.0)
    prompt = [words(0x4c3ec8+24*i, 6) for i in range(3)]+[words(0x4c3f10, 6)]
    data = b'ATLY'+struct.pack('<I', 1)+struct.pack('<24i', *award)+struct.pack('<6i', *finish)
    data += b''.join(text.ljust(24, b'\0') for text in labels)
    data += struct.pack('<2i', *score_x)+b''.join(struct.pack('<6i', *r) for r in digits)
    data += b''.join(struct.pack('<6i', *r) for r in pieces)+struct.pack('<30f', *floats)
    data += struct.pack('<12i', *demo[:2], *demo_latched[:2], *seat[:2], *seat[3:5], *seat_latched[:2], *seat_latched[3:5])
    data += struct.pack('<f', depth[0])+b''.join(struct.pack('<6i', *r) for r in prompt)
    assert len(data) == 932
    layout = dict(award_655588=[8, 24], finish_6555e8=[104, 6], labels=[128, 7, 24], score_x_582250=[296, 2],
                  score_digits_4c5ae8=[304, 10, 6], panel_pieces_4c5110=[544, 5, 6], panel_floats_655510=[664, 30],
                  prompt_positions=[784, 12], prompt_depth=[832, 1], prompt_records=[836, 4, 6])
    return data, dict(award=list(award), finish=list(finish), labels=[t.decode() for t in labels],
                      score_x=list(score_x), layout=layout)

def main():
    raw = (ROOT/'work/ss6/extracted/SLPS_255.59').read_bytes()
    assert hashlib.sha256(raw).hexdigest() == SOURCE_HASH
    data, summary = build(raw)
    target = ROOT/'work/ss6/extracted/resources'/NAME
    target.write_bytes(data)
    shutil.copyfile(target, ROOT/'outputs/ss6-feasibility/native-viewer/assets'/NAME)
    report = dict(elf_sha256=SOURCE_HASH, asset=NAME, bytes=len(data), sha256=hashlib.sha256(data).hexdigest(),
                  gates=['0x14e838', '0x14e8d8'], adders=['0x1c97c0', '0x1c97f0'], **summary)
    (ROOT/'outputs/ss6-feasibility/arcade_tally_tables.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2))

if __name__ == '__main__':main()
