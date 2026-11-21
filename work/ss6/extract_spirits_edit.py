#!/usr/bin/env python3
"""Pin the SPIRITS EDIT option tables and the shared edit-scene widget strings."""
import hashlib
import json
import shutil
import struct
from pathlib import Path
from inspect_iso import Elf
from extract_collision_tables import SOURCE_HASH

ROOT = Path(__file__).resolve().parents[2]
RESOURCES = ROOT/'work/ss6/extracted/resources'
PACKAGED = ROOT/'outputs/ss6-feasibility/native-viewer/assets'
OPTIONS, CATEGORIES, SLOT_NAMES = 0x4d6e30, 0x4d6db0, 0x4ca250
HELP, ORDER, CHARACTER_NAMES = 0x4ee870, 0x59cd20, 0x4d4bb0

class Source:
    def __init__(self):
        self.raw = (ROOT/'work/ss6/extracted/SLPS_255.59').read_bytes()
        assert hashlib.sha256(self.raw).hexdigest() == SOURCE_HASH
        self.elf = Elf(self.raw)
    def bytes(self, at, n):
        o = self.elf.offset(at); return self.raw[o:o+n]
    def word(self, at): return struct.unpack('<I', self.bytes(at, 4))[0]
    def text(self, at):
        # Shift-JIS bytes are kept verbatim: the original sizes panels by strlen.
        o = self.elf.offset(at); return self.raw[o:self.raw.index(b'\0', o)]

def pack(strings):
    return b''.join(struct.pack('<H', len(s))+s for s in strings)

def spirits(s):
    """47 x {category, cost}; 16 category names; option names; slot names; panel strings."""
    table = s.bytes(OPTIONS, 47*12)
    options = [struct.unpack_from('<BbHII', table, 12*i) for i in range(47)]
    assert all(o[2] == 0 for o in options) and [o[0] for o in options] == sorted(o[0] for o in options)
    assert {o[0] for o in options} == set(range(16))
    categories = [struct.unpack('<II', s.bytes(CATEGORIES+8*i, 8)) for i in range(16)]
    strings = ([s.text(c[0]) for c in categories]+[s.text(c[1]) for c in categories]
               + [s.text(o[3]) for o in options]+[s.text(o[4]) for o in options]
               + [s.text(s.word(SLOT_NAMES+4*i)) for i in range(8)]
               # 20cd00 title, 20cd68 empty row, option panel title, 20dbc8 format.
               + [s.text(a) for a in (0x664770, 0x664778, 0x6647b8, 0x6647d8)])
    data = b'SPED'+b''.join(struct.pack('<Bb', o[0], o[1]) for o in options)+pack(strings)
    listing = [dict(index=i, category=o[0], cost=o[1], romaji=s.text(o[3]).decode('shift_jis'),
                    japanese=s.text(o[4]).decode('shift_jis')) for i, o in enumerate(options)]
    names = [dict(romaji=s.text(c[0]).decode('shift_jis'), japanese=s.text(c[1]).decode('shift_jis')) for c in categories]
    return data, listing, names

def widgets(s):
    """Help table rows in original order, character order and labels, list defaults."""
    rows = []
    while True:
        ident = s.bytes(HELP+8*len(rows), 1)[0]
        if ident == 0xff: break
        rows.append((ident, s.text(s.word(HELP+8*len(rows)+4))))
    assert len(rows) == 207
    order = s.bytes(ORDER, 0x35)
    # Pointer 49 of the 50-entry table is NULL (20e7f8 ignores it); no listed id uses it.
    assert s.word(CHARACTER_NAMES+4*49) == 0 and max(order[:0x31]) == 48
    names = [s.text(s.word(CHARACTER_NAMES+4*i)) for i in range(49)]
    # 20e570 title, 20e5d8 row default, 1821f8 fallback, then the EX labels
    # selected by 20eae0 for ids 50+: default, 73, 72, 75, 74.
    fixed = [s.text(a) for a in (0x6647e8, 0x6647f0, 0x5f3f00, 0x664800, 0x664810, 0x664820, 0x664838, 0x664850)]
    data = (b'EDWG'+struct.pack('<H', len(rows))+bytes(r[0] for r in rows)+pack([r[1] for r in rows])
            + order+pack(names)+pack(fixed))
    return data, len(rows)

def main():
    s = Source()
    report = dict(elf_sha256=SOURCE_HASH)
    spirit, listing, names = spirits(s)
    widget, help_rows = widgets(s)
    for name, data in (('spirits_edit.bin', spirit), ('edit_widgets.bin', widget)):
        (RESOURCES/name).write_bytes(data)
        if PACKAGED.is_dir(): shutil.copyfile(RESOURCES/name, PACKAGED/name)
        report[name] = dict(bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
    report.update(option_table=hex(OPTIONS), category_table=hex(CATEGORIES), slot_names=hex(SLOT_NAMES),
                  help_table=hex(HELP), help_rows=help_rows, character_order=hex(ORDER),
                  character_names=hex(CHARACTER_NAMES), encoding='Shift-JIS bytes, u16 length prefix',
                  categories=names, options=listing)
    (ROOT/'outputs/ss6-feasibility/spirits_edit_tables.json').write_text(json.dumps(report, indent=2, ensure_ascii=False)+'\n')
    print(json.dumps({k: v for k, v in report.items() if k not in ('options', 'categories')}, indent=2))

if __name__ == '__main__':main()
