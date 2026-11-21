#!/usr/bin/env python3
"""Pin the arcade schedule, VS win-limit and name-entry tables of SLPS-25559."""
import hashlib
import json
import shutil
import struct
from pathlib import Path
from inspect_iso import Elf
from extract_collision_tables import SOURCE_HASH

ROOT = Path(__file__).resolve().parents[2]
NAME = 'arcade_run.bin'
OPPONENTS, STAGES, BOSSES, INTRUDER, LIMITS = 0x4edf70, 0x4ee508, 0x4ee520, 0x4ee530, 0x5dfb30
GLYPHS, NAMES, FILTER = 0x582998, 0x582458, 0x3bd950

def tables():
    raw = (ROOT/'work/ss6/extracted/SLPS_255.59').read_bytes()
    assert hashlib.sha256(raw).hexdigest() == SOURCE_HASH
    elf = Elf(raw)
    words = lambda at, n: struct.unpack_from(f'<{n}i', raw, elf.offset(at))
    halves = lambda at, n: struct.unpack_from(f'<{n}h', raw, elf.offset(at))
    def text(at):
        start = elf.offset(at); value = raw[start:raw.index(b'\0', start)]
        assert len(value) <= 3 and value.isascii(), value
        return value
    strings = lambda at, n: [text(p) for p in struct.unpack_from(f'<{n}I', raw, elf.offset(at))]
    # 17a748 scans 0x33 rows of 14 halfwords; 17a548 indexes 4ee530 with the
    # stage index before its 1..6 range test, so the eighth halfword is kept.
    rows = halves(OPPONENTS, 0x33*14)
    glyphs, names = strings(GLYPHS, 45), strings(NAMES, 52)
    assert glyphs[0] == b'A' and glyphs[43:] == [b'<-', b'END'] and names[0] == b'HAO'
    # 110bf8 walks a pointer list terminated by an empty string.
    banned = []
    while True:
        word = text(words(FILTER+4*len(banned), 1)[0] & 0xffffffff)
        if not word: break
        banned.append(word)
    pad = lambda value: value.ljust(4, b'\0')
    data = struct.pack(f'<{len(rows)}h', *rows)
    data += struct.pack('<5i4i8h4i', *words(STAGES, 5), *words(BOSSES, 4), *halves(INTRUDER, 8), *words(LIMITS, 4))
    data += b''.join(map(pad, glyphs))+b''.join(map(pad, names))
    data += struct.pack('<I', len(banned))+b''.join(map(pad, banned))
    return data, dict(opponent_rows=0x33, glyphs=len(glyphs), names=len(names), banned=len(banned))

def main():
    data, counts = tables()
    out = ROOT/'work/ss6/extracted/resources'/NAME
    out.write_bytes(data)
    shutil.copyfile(out, ROOT/'outputs/ss6-feasibility/native-viewer/assets'/NAME)
    report = dict(elf_sha256=SOURCE_HASH, asset=NAME, bytes=len(data), sha256=hashlib.sha256(data).hexdigest(),
                  sources={'opponent_rows': hex(OPPONENTS), 'random_stages': hex(STAGES), 'bosses': hex(BOSSES),
                           'intruder_thresholds': hex(INTRUDER), 'versus_win_limits': hex(LIMITS),
                           'name_glyphs': hex(GLYPHS), 'default_names': hex(NAMES), 'name_filter': hex(FILTER)},
                  layout=['0x33*14 i16 opponent rows', '5 i32 stages', '4 i32 bosses', '8 i16 intruder thresholds',
                          '4 i32 VS win limits', '45*4 glyph strings', '52*4 default names',
                          'u32 count + count*4 filtered names'], **counts)
    (ROOT/'outputs/ss6-feasibility/arcade_run_tables.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2))

if __name__ == '__main__':main()
