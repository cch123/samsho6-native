#!/usr/bin/env python3
"""Pin the tables read by the PRACTICE MODE draw routines (src/practice_art.cpp).

practice_art.bin (little endian), in order:
  'PAR1'
  u32 n, n x {u32 address, f32 value}   float constants loaded through lui/addiu + lwc1 by
                                        2109b0, 2118a0, 17f790 (dim plane), 13a280 (see FLOATS)
  u8[16]                                key-history icon numbers 4ca210[15] (index = bit of the
                                        history word; 17e038 icon number), one pad byte
The integer coordinates of these routines are instruction immediates; the manifest records the
hash of each transcribed routine (CODE) under the pinned executable hash.
Strings come from practice_mode.bin (extract_practice_mode.py) and edit_art.bin.
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
MANIFEST = ROOT/'outputs/ss6-feasibility/practice_art_tables.json'
ORIGINAL = '72420e74e04d7ac39119d1b6ec7d70ed004fc98c5035fade96e87d05d4b9ffbf'
OUT = RESOURCES/'practice_art.bin'

FLOATS = (
    0x5e1aac,                                   # 13a280 depth base of the key history (17c250)
    0x5e1ab0, 0x5e1ab4, 0x5e1ab8,               # 13a280 icon layer, neutral icon y, box layer
    0x5f20b0,                                   # 17f790 dim plane layer
    0x664dac, 0x664db0, 0x664db4, 0x664db8,     # 2109b0 window size, arrow size
    0x664ef0, 0x664ef4, 0x664ef8,               # 2118a0 depth base, window size
    0x664efc, 0x664f00,                         # 2118a0 arrow size
)
ICONS = 0x4ca210
# Routines whose immediates src/practice_art.cpp transcribes: (start, end).
CODE = dict(menu_2109b0=(0x2109b0, 0x211058), gauge_2118a0=(0x2118a0, 0x211c00), dialog_2129d0=(0x2129d0, 0x212b10),
            displays_13a280=(0x13a280, 0x13a6c0), clock_141dd0=(0x141dd0, 0x141f18), window_tail_17f8d0=(0x17f8d0, 0x17fa40))


def extract():
    data = (ROOT/'work/ss6/extracted/SLPS_255.59').read_bytes()
    if hashlib.sha256(data).hexdigest() != ORIGINAL: raise ValueError('Expected Japanese SLPS-25559')
    elf = Elf(data)
    def raw(at, n):
        o = elf.offset(at); return data[o:o+n]
    out = bytearray(b'PAR1')
    out += struct.pack('<I', len(FLOATS))
    for at in FLOATS: out += struct.pack('<I', at)+raw(at, 4)
    icons = raw(ICONS, 15)
    out += icons+b'\0'
    code = {name: hashlib.sha256(raw(a, b-a)).hexdigest() for name, (a, b) in CODE.items()}
    info = dict(floats={hex(at): struct.unpack('<f', raw(at, 4))[0] for at in FLOATS}, key_icons=list(icons),
                code_ranges={name: [hex(a), hex(b)] for name, (a, b) in CODE.items()}, code_sha256=code)
    return bytes(out), info


def main():
    blob, info = extract()
    OUT.write_bytes(blob); PACKAGED.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(OUT, PACKAGED/OUT.name)
    manifest = dict(elf_sha256=ORIGINAL, asset=OUT.name, bytes=len(blob), sha256=hashlib.sha256(blob).hexdigest(), **info)
    MANIFEST.write_text(json.dumps(manifest, indent=2)+'\n')
    print(f'{OUT} {len(blob)} bytes {manifest["sha256"]}')


if __name__ == '__main__': main()
