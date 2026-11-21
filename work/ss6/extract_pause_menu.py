#!/usr/bin/env python3
"""Pin the pause-menu and key-configuration strings and the three button presets."""
import hashlib
import json
import shutil
import struct
from pathlib import Path
from inspect_iso import Elf
from mips_probe import Probe
from extract_collision_tables import SOURCE_HASH

ROOT = Path(__file__).resolve().parents[2]
RESOURCES = ROOT/'work/ss6/extracted/resources'
PACKAGE = ROOT/'outputs/ss6-feasibility/native-viewer/assets'
NAME = 'pause_menu.bin'
ITEMS, ITEMS5 = (0x658ba8, 6), (0x658bd0, 4)        # 1da9c0: row labels, ordinary and sub-mode 5
HELP, HELP5 = (0x582f68, 6), (0x582f98, 4)          # 1dac78 / 1dac90: {text, scroll flag} records
ASK = [0x656b58, 0x656b5c]                          # 1cf598: pointers to the two answers
PROMPTS = [0x656b78, 0x656b98, 0x656bb0]            # 1cf598: sub-mode 5, kind 0 (title), kind 1 (select)
ANSWER_X = 0x656b60                                 # 1cf598: x of the two answers
KEY_ROWS = (0x59cfb8, 10)                           # 212478: row labels
KEY_LEGEND, KEY_UNSET = 0x665208, 0x665220          # 212478: legend line and the unassigned marker
MASKS = 0x4eaac0
# Switch tables transcribed by the native port; pinned so that another ELF cannot pass silently.
JUMPS = {0x658998: [0x1da2ac, 0x1da274, 0x1da308, 0x1da324, 0x1da358, 0x1da398],   # 1da210 by old sub-mode
         0x658a18: [0x1da680, 0x1da690, 0x1da644, 0x1da748, 0x1da75c, 0x1da778]}   # 1da508 by cursor

def strings(items):
    return struct.pack('<I', len(items))+b''.join(struct.pack('<H', len(s))+s for s in items)

def container(sections):
    return struct.pack('<I', len(sections))+b''.join(tag.encode()+struct.pack('<I', len(d))+d for tag, d in sections)

def main():
    raw = (ROOT/'work/ss6/extracted/SLPS_255.59').read_bytes()
    assert hashlib.sha256(raw).hexdigest() == SOURCE_HASH
    elf = Elf(raw)
    word = lambda at: struct.unpack_from('<I', raw, elf.offset(at))[0]
    def text(at):
        o = elf.offset(at); return raw[o:raw.index(b'\0', o)]
    for at, cases in JUMPS.items():
        assert [word(at+4*i) for i in range(len(cases))] == cases, hex(at)
    table = lambda spec, stride=4: [text(word(spec[0]+stride*i)) for i in range(spec[1])]
    for base, n in (HELP, HELP5):
        # No help line scrolls: 1dab38 draws the second marquee copy only for flag 1.
        assert all(word(base+8*i+4) == 0 for i in range(n))
    # The presets are immediates of 178e50; execute it instead of transcribing them.
    p = Probe(raw)
    presets = []
    for preset in range(3):
        p.memory[MASKS:MASKS+0x40] = b'\xff'*0x40
        for player in range(2): p.run(0x178e50, (player, preset), limit=200)
        both = [[p.read(MASKS+0x20*player+4*i, 4) for i in range(8)] for player in range(2)]
        assert both[0] == both[1] and p.read(0x12d26b0, 1) == p.read(0x12d26b1, 1) == preset
        presets.append(both[0])
    sections = [('ITEM', strings(table(ITEMS))), ('ITM5', strings(table(ITEMS5))),
                ('HELP', strings(table(HELP, 8))), ('HLP5', strings(table(HELP5, 8))),
                ('ASK_', strings([text(word(a)) for a in ASK]+[text(a) for a in PROMPTS])),
                ('ASKX', struct.pack('<2i', word(ANSWER_X), word(ANSWER_X+4))),
                ('KEYS', strings(table(KEY_ROWS)+[text(KEY_LEGEND), text(KEY_UNSET)])),
                ('PRES', b''.join(struct.pack('<8I', *m) for m in presets))]
    data = container(sections)
    (RESOURCES/NAME).write_bytes(data)
    shutil.copyfile(RESOURCES/NAME, PACKAGE/NAME)
    report = dict(elf_sha256=SOURCE_HASH, asset=NAME, bytes=len(data), sha256=hashlib.sha256(data).hexdigest(),
                  sections={tag: len(d) for tag, d in sections},
                  sources=dict(items=hex(ITEMS[0]), items_submode5=hex(ITEMS5[0]), help=hex(HELP[0]),
                               help_submode5=hex(HELP5[0]), answers=[hex(a) for a in ASK],
                               prompts=[hex(a) for a in PROMPTS], answer_x=hex(ANSWER_X), key_rows=hex(KEY_ROWS[0]),
                               key_legend=hex(KEY_LEGEND), key_unset=hex(KEY_UNSET), presets='0x178e50 (executed)',
                               jump_tables=[hex(a) for a in JUMPS]),
                  presets=[[hex(v) for v in m] for m in presets],
                  items=[s.decode('shift_jis') for s in table(ITEMS)],
                  items_submode5=[s.decode('shift_jis') for s in table(ITEMS5)],
                  key_rows=[s.decode('shift_jis') for s in table(KEY_ROWS)])
    (ROOT/'outputs/ss6-feasibility/pause_menu_tables.json').write_text(json.dumps(report, indent=2, ensure_ascii=False)+'\n')
    print(json.dumps(report, indent=2, ensure_ascii=False))

if __name__ == '__main__':main()
