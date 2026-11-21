#!/usr/bin/env python3
"""Pin the COLOR EDIT tables: auxiliary palette banks, character order, preview poses, palette-cache slots."""
import hashlib
import json
import shutil
import struct
from pathlib import Path
from inspect_iso import Elf
from extract_collision_tables import SOURCE_HASH

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT/'work/ss6/extracted/resources/color_edit.bin'
PACKAGED = ROOT/'outputs/ss6-feasibility/native-viewer/assets/color_edit.bin'
AUX, ORDER, BIAS, SLOTS, PREVIEW, WEAPON_Y, SCALARS = 0x4ca9a8, 0x59cd20, 0x4caaac, 0x5dd5c8, 0x4ca278, 0x4ca9e0, 0x5e1d10
HELP = 0x4ee870

def main():
    raw = (ROOT/'work/ss6/extracted/SLPS_255.59').read_bytes()
    assert hashlib.sha256(raw).hexdigest() == SOURCE_HASH
    elf = Elf(raw)
    block = lambda at, size: raw[elf.offset(at):elf.offset(at)+size]
    word = lambda at: struct.unpack_from('<I', raw, elf.offset(at))[0]
    def text(at):
        if not at: return ''
        start = elf.offset(at)
        return raw[start:raw.index(b'\0', start)].decode('cp932')
    # 13be78 indexes 4ca9a8 by character; 13cbd8/13ca58 add the word 4caaac.
    # 115d40 and 13c880 are the consumers of the first and fourth tables.
    assert word(0x13be80) == 0x25efa9a8 and word(0x13c890) == 0x25efa278
    data = b'CEDT' + struct.pack('<I', 1)
    data += block(AUX, 52)                        # 13be78 has no bound; the save table stores 52 characters
    data += block(ORDER, 0x35) + b'\0'*3
    data += block(BIAS, 4) + block(SLOTS, 24*4) + block(PREVIEW, 51*0x24) + block(WEAPON_Y, 51*4) + block(SCALARS, 27*4)
    assert len(data) == 2364
    assert sorted(struct.unpack_from('<24I', data, 120)) == list(range(8, 32))
    OUT.write_bytes(data)
    shutil.copyfile(OUT, PACKAGED)
    help_rows, at, current = {}, HELP, None
    while raw[elf.offset(at)] != 0xff:
        ident, pointer = raw[elf.offset(at)], word(at+4)
        if ident != 0xfe: current = ident
        help_rows.setdefault(current, []).append(text(pointer))
        at += 8
    report = dict(elf_sha256=SOURCE_HASH, asset='color_edit.bin', bytes=len(data), sha256=hashlib.sha256(data).hexdigest(),
                  layout=dict(aux_bank=[8, 52], character_order=[60, 0x35], aux_bias=[116, 4], cache_slots=[120, 96],
                              preview=[216, 51*0x24], weapon_y=[2052, 204], scalars=[2256, 108]),
                  addresses={k: hex(v) for k, v in dict(aux_bank=AUX, character_order=ORDER, aux_bias=BIAS, cache_slots=SLOTS,
                                                         preview=PREVIEW, weapon_y=WEAPON_Y, scalars=SCALARS).items()},
                  strings=dict(colour_rows=[text(word(0x4ca228+4*i)) for i in range(5)],
                               copy_rows=[text(word(0x4ca240+4*i)) for i in range(2)],
                               character_names=[text(word(0x4d4bb0+4*i)) for i in range(50)],
                               dialog=text(0x5e1cb0), dialog_default=text(0x665240),
                               second_hint={'11': text(0x5f22f8), '12': text(0x5f2328), '13': text(0x5f2318)},
                               key_hint=dict(check=text(0x5e1d90), edit=text(0x5e1da0)),
                               help={hex(k): help_rows.get(k, []) for k in (0x21, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28)}))
    (ROOT/'outputs/ss6-feasibility/color_edit_tables.json').write_text(json.dumps(report, indent=2, ensure_ascii=False)+'\n')
    print(json.dumps({k: report[k] for k in ('asset', 'bytes', 'sha256')}))

if __name__ == '__main__':main()
