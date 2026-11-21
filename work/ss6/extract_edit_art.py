#!/usr/bin/env python3
"""Pin the tables read by the SPIRITS EDIT / COLOR EDIT draw routines (src/edit_art.cpp).

edit_art.bin (little endian), in order:
  'EAR1'
  u32 n, n x {u32 address, f32 value}   float constants of 17c228..17eed8, 181c30..182118,
                                        20c038..20fb58, 20d2e8, 20d9f8, 2129d0 (see FLOATS)
  f64[2]                                tab slant factors 5f1f80, 5f1f88 (17ce58)
  u32 n, n x int32[5]                   icon rectangles through pointer table 4ee6b8
                                        {u, v, w, h, slot}; 17e038 index
  17 x int32[4]                         title plates 4c7660 (181e88), slot 2e
  int32[5]                              summary plate 4c9120 {u, v, w, h, slot} (17eac8)
  u8[8]                                 shade alphas 4ee868 (17eed8), two pad bytes
  u32                                   initial text colour word 4ee548
  int32[5]                              colour-row button icons 59cd58 (20f360)
  u32 n, n x {u16 length, bytes}        strings (see STRINGS), Shift_JIS as stored
"""
import hashlib
import json
import shutil
import struct
from pathlib import Path

from inspect_iso import Elf

ROOT = Path(__file__).resolve().parents[2]
RESOURCES = ROOT/'work/ss6/extracted/resources'
PACKAGED = ROOT/'outputs/ss6-feasibility/native-viewer/assets'
MANIFEST = ROOT/'outputs/ss6-feasibility/edit_art_tables.json'
ORIGINAL = '72420e74e04d7ac39119d1b6ec7d70ed004fc98c5035fade96e87d05d4b9ffbf'
OUT = RESOURCES/'edit_art.bin'

# Every float the ported routines load through lui/addiu + lwc1.
FLOATS = (
    0x5f1f08,                                   # 17c228 depth step
    0x5f1f0c,                                   # 17c260 unit size
    0x5f1f10, 0x5f1f14, 0x5f1f18,               # 17c3d8 / 17c560 layer, half
    *range(0x5f1f1c, 0x5f1f4c, 4),              # 17c718 layer and insets
    *range(0x5f1f4c, 0x5f1f80, 4),              # 17cb50 insets, layer, half
    0x5f1f90,                                   # 17ce58 layer
    *range(0x5f1f94, 0x5f1fc4, 4),              # 17d370
    0x5f1fc4, 0x5f1fc8,                         # 17d790
    *range(0x5f1fe0, 0x5f1ff4, 4),              # 17dd88
    0x5f1ff4, 0x5f1ff8, 0x5f1ffc,               # 17e228 layers
    *range(0x5f2010, 0x5f2028, 4),              # 17e428
    0x5f2028, 0x5f202c,                         # 17eac8
    *range(0x5f2058, 0x5f2070, 4),              # 17f090
    0x5f22b8, 0x5f2378,                         # 1817f0, 181c30
    *range(0x5f23ac, 0x5f23bc, 4),              # 181e88
    0x5f3ef4, 0x5f3ef8, 0x5f3efc,               # 182118
    *range(0x6646f4, 0x664720, 4),              # 20c038 / 20c1a0
    0x6647ac, 0x6647b0, 0x6647b4,               # 20d2e8
    *range(0x6647c4, 0x6647d4, 4),              # 20d9f8
    0x664864, 0x664870,                         # 20ef38 scroll bar width, 20f1c8 text inset
    *range(0x664874, 0x664884, 4),              # 20f360
    *range(0x66488c, 0x6648a0, 4),              # 20f680
    *range(0x6648b4, 0x6648f0, 4),              # 20fb58
    0x665268,                                   # 2129d0
)
STRINGS = dict(keys_default=0x5f22c0, keys_restore=0x5f22e0, keys_reset=0x5f22f8, keys_cancel=0x5f2318, keys_copy=0x5f2328,
               keys_select=0x5e1d90, keys_select_confirm=0x5e1da0, space=0x5f2000, exit=0x5f2008,
               cost='%2d', refund='+%d', one_digit=' %d', two_digits='%d',
               dialog_default=0x665240, yes=0x665258, no=0x665260, reset_question=0x5e1cb0)
FORMATS = dict(cost=0x664788, refund=0x6647a8, one_digit=0x6648a8, two_digits=0x6648b0)


def extract():
    data = (ROOT/'work/ss6/extracted/SLPS_255.59').read_bytes()
    if hashlib.sha256(data).hexdigest() != ORIGINAL: raise ValueError('Expected Japanese SLPS-25559')
    elf = Elf(data)
    def raw(at, n):
        o = elf.offset(at); return data[o:o+n]
    def words(at, n, fmt='i'): return struct.unpack(f'<{n}{fmt}', raw(at, 4*n))
    def text(at):
        o = elf.offset(at); return data[o:data.index(0, o)]
    out = bytearray(b'EAR1')
    out += struct.pack('<I', len(FLOATS))
    for at in FLOATS: out += struct.pack('<I', at)+raw(at, 4)
    slant = struct.unpack('<2d', raw(0x5f1f80, 16))
    out += raw(0x5f1f80, 16)
    icons = []
    for n in range(0x5e):
        rect = words(words(0x4ee6b8+4*n, 1, 'I')[0], 6)
        # 17e038 selects slot 2e below 33 and slot 5 from 33; the record's own slot word is 6 or 5.
        if rect[4] != 0 or rect[5] != (6 if n < 0x33 else 5): raise ValueError('Unexpected icon record')
        icons.append((*rect[:4], 0x2e if n < 0x33 else 5))
    out += struct.pack('<I', len(icons))+b''.join(struct.pack('<5i', *r) for r in icons)
    for i in range(17):
        rect = words(0x4c7660+24*i, 6)
        if rect[4:] != (0, 6): raise ValueError('Unexpected title record')
        out += struct.pack('<4i', *rect[:4])
    plate = words(0x4c9120, 6)
    if plate[4:] != (0, 5): raise ValueError('Unexpected summary plate')
    out += struct.pack('<5i', *plate[:4], 5)
    out += raw(0x4ee868, 8)
    if raw(0x4ee868, 8)[6:] != b'\0\0': raise ValueError('Unexpected shade table')
    out += raw(0x4ee548, 4)
    out += raw(0x59cd58, 20)
    strings = []
    for name, at in STRINGS.items():
        s = text(FORMATS[name]) if name in FORMATS else text(at)
        if name in FORMATS and s.decode('ascii') != at: raise ValueError('Unexpected number format')
        s.decode('cp932'); strings.append(s)
    colour_rows = [text(a) for a in words(0x4ca228, 5, 'I')]
    copy_rows = [text(a) for a in words(0x4ca240, 2, 'I')]
    if words(0x4ca248, 1, 'I')[0] != 0: raise ValueError('Copy menu is not NULL terminated')
    strings += colour_rows+copy_rows
    out += struct.pack('<I', len(strings))+b''.join(struct.pack('<H', len(s))+s for s in strings)
    info = dict(floats=len(FLOATS), slant=slant, icons=len(icons),
                strings={k: s.decode('cp932') for k, s in zip(STRINGS, strings)},
                colour_rows=[s.decode('cp932') for s in colour_rows], copy_rows=[s.decode('cp932') for s in copy_rows])
    return bytes(out), info


def main():
    blob, info = extract()
    OUT.write_bytes(blob); PACKAGED.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(OUT, PACKAGED/OUT.name)
    copied = []
    listing = {f.name for f in PACKAGED.iterdir()}
    textures = {}
    # Texture slot 5 of both scenes is "ps2_gage_1_2_3_all.pvr"/".pvp" (12f050, CLUT bank 0x300).
    for name in ('ps2_gage_1_2_3_all.tex', 'ps2_gage_1_2_3_all.pal'):
        source = RESOURCES/name; textures[name] = hashlib.sha256(source.read_bytes()).hexdigest()
        if name not in listing:
            shutil.copyfile(source, PACKAGED/name); copied.append(name)
    manifest = dict(elf_sha256=ORIGINAL, asset=OUT.name, bytes=len(blob), sha256=hashlib.sha256(blob).hexdigest(),
                    textures=textures, textures_copied_to_package=copied, **info)
    MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False)+'\n')
    print(f'{OUT} {len(blob)} bytes {manifest["sha256"]} copied={copied}')


if __name__ == '__main__': main()
