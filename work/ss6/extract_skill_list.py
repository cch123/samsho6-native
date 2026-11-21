#!/usr/bin/env python3
"""Pin the SKILL LIST (command list) tables of SLPS-25559.

skill_list.bin is a tagged-section container in the format of
extract_console_gallery.py (u32 count, then {char tag[4]; u32 size; payload};
a string table payload is u32 count followed by {u16 length; bytes}). Every
text is the Shift_JIS byte string of the executable, verbatim, including the
two-letter ASCII control codes that 17e428 turns into glyph icons.

Sections
  CMNR  records of the common-command table 4caab0 (13cf88)
  CHRR  records of the per-character table 4cb190 (13cfc0)
        {s16 id; u8 type; u8 flags; u16 spirits; u16 text[3]}; id -1 continues
        the group opened by the last id >= 0; the -2 terminator is dropped
  TEXT  the strings the records index (index 0 is the empty string)
  CATS  4ceef8: the two category rows of the first list
  ROWS  4cef08: the ten rows of the common-command sub-list (20e8c0)
  COLR  4cef38: name colour {r,g,b} of types 0..6, then 4cef50: the two shadow
        colours (type 1, other types)
  BARC  4ee830: heading-bar gradient {r,g,b,r,g,b} of types 0..5 (17e0b0)
  ICON  4ee6b8: {s32 u,v,w,h} of the 51 icons addressable by 17e038 in
        texture slot 2e; w is the pen advance returned by 17df90
  LITS  5f2000 " ", 5f2008 "EXIT", 5e1e70 "" (the literals of 17e428/13d0d0)
  CNST  s32: 5e7dfc bar x, 5f201c small-glyph y offset, 5f2020 icon x offset,
        5f2024 EXIT y offset, 6648f4 / 6648f8 scroll-bar width / height
"""
import hashlib
import json
import shutil
import struct
from extract_console_gallery import Source, container, strings, ROOT, RESOURCES, PACKAGE
from extract_collision_tables import SOURCE_HASH

NAME = 'skill_list.bin'
COMMON, CHARACTER = 0x4caab0, 0x4cb190
CATEGORIES, COMMON_ROWS = 0x4ceef8, 0x4cef08
NAME_COLOURS, SHADOW_COLOURS, BAR_COLOURS, ICON_RECTS = 0x4cef38, 0x4cef50, 0x4ee830, 0x4ee6b8
LITERALS = (0x5f2000, 0x5f2008, 0x5e1e70)
FLOATS = (0x5e7dfc, 0x5f201c, 0x5f2020, 0x5f2024, 0x6648f4, 0x6648f8)
# Code words that tie the native transcription to this executable: the table
# bases loaded by 13cf88/13cfc0, the literals of 13d0d0 and the list tables.
CODE = {0x13cf88: 0x3c0f004d, 0x13cf8c: 0x85eeaab0, 0x13cfc0: 0x3c0f004d, 0x13cfc4: 0x85eeb190,
        0x13d2f8: 0x3c0d005e, 0x13d2fc: 0x25ad1e70, 0x20e8c4: 0x3c0f004d, 0x20e8f0: 0x25f4ef08,
        0x13d6f0: 0x3c05004d, 0x13d700: 0x24a5eef8}

def records(s, base):
    out = []
    while s.s16(base+0x14*len(out)) != -2:
        at = base+0x14*len(out)
        ident, kind, flags, spirits, pad = s.s16(at), s.u8(at+2), s.u8(at+3), s.u16(at+4), s.u16(at+6)
        texts = [s.word(at+8+4*i) for i in range(3)]
        assert ident >= -1 and pad == 0 and all(texts), hex(at)
        out.append((ident, kind, flags, spirits, [s.text(p) for p in texts]))
    assert out and out[0][0] >= 0
    return out

def build(s):
    for at, word in CODE.items(): assert s.word(at) == word, hex(at)
    tables = [records(s, COMMON), records(s, CHARACTER)]
    assert COMMON+0x14*(len(tables[0])+1) == CHARACTER and CHARACTER+0x14*(len(tables[1])+1) == CATEGORIES
    pool = {b'': 0}
    def index(text): return pool.setdefault(text, len(pool))
    packed = []
    for table in tables:
        data = b''
        for ident, kind, flags, spirits, texts in table:
            assert kind in (0, 1, 2, 3, 4, 5, 6) and spirits < 0x200
            data += struct.pack('<hBBH3H', ident, kind, flags, spirits, *[index(t) for t in texts])
        packed.append(data)
    assert len(pool) < 0x10000
    categories = [s.text(p) for p in s.pointers(CATEGORIES, 2)]
    rows = [s.text(p) for p in s.pointers(COMMON_ROWS, 10)]
    assert s.word(CATEGORIES+8) == 0 and s.word(COMMON_ROWS+40) == 0
    raw = lambda at, n: s.raw[s.at(at):s.at(at)+n]
    icons = b''
    for i in range(0x33):
        rect = s.word(ICON_RECTS+4*i)
        icons += raw(rect, 16)
    floats = [struct.unpack('<f', raw(a, 4))[0] for a in FLOATS]
    assert all(f == int(f) for f in floats)
    literals = [s.text(a) for a in LITERALS]
    assert literals == [b' ', b'EXIT', b'']
    sections = [('CMNR', packed[0]), ('CHRR', packed[1]),
                ('TEXT', strings(sorted(pool, key=pool.get))), ('CATS', strings(categories)), ('ROWS', strings(rows)),
                ('COLR', raw(NAME_COLOURS, 21)+raw(SHADOW_COLOURS, 6)), ('BARC', raw(BAR_COLOURS, 36)),
                ('ICON', icons), ('LITS', strings(literals)), ('CNST', struct.pack('<6i', *map(int, floats)))]
    detail = dict(common_records=len(tables[0]), character_records=len(tables[1]), texts=len(pool),
                  common_ids=[r[0] for r in tables[0] if r[0] >= 0], character_ids=[r[0] for r in tables[1] if r[0] >= 0],
                  constants=dict(zip(map(hex, FLOATS), map(int, floats))))
    return container(sections), detail

def main():
    s = Source()
    data, detail = build(s)
    (RESOURCES/NAME).write_bytes(data)
    shutil.copyfile(RESOURCES/NAME, PACKAGE/NAME)
    report = dict(elf_sha256=SOURCE_HASH, asset=NAME, bytes=len(data), sha256=hashlib.sha256(data).hexdigest(),
                  sources=dict(common=hex(COMMON), character=hex(CHARACTER), categories=hex(CATEGORIES),
                               common_rows=hex(COMMON_ROWS), name_colours=hex(NAME_COLOURS),
                               shadow_colours=hex(SHADOW_COLOURS), bar_colours=hex(BAR_COLOURS),
                               icon_rects=hex(ICON_RECTS), literals=[hex(a) for a in LITERALS]),
                  pinned_code={hex(k): hex(v) for k, v in CODE.items()}, **detail)
    (ROOT/'outputs/ss6-feasibility/skill_list_tables.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({k: v for k, v in report.items() if k not in ('pinned_code', 'sources')}, indent=2))

if __name__ == '__main__':main()
