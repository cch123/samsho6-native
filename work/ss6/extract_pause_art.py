#!/usr/bin/env python3
"""Collect the literals read by the drawing of the pause menu, KEY CONFIGURATION and SKILL LIST.

pause_art.bin (little endian):
  'PAR1'
  u32 n, n x float      constants in the order of FLOATS (index = position;
                        the C++ enum PauseArtTables::Constant follows it)
Every other table these draw routines read is already packaged by the logic
modules (pause_menu.bin, skill_list.bin, menu_widgets.bin) and by the window
library (gallery_art.bin, menu_canvas.bin).
"""
import hashlib
import json
import shutil
import struct
from pathlib import Path

from inspect_iso import Elf, Iso

ROOT=Path(__file__).resolve().parents[2]
ASSETS=ROOT/'work/ss6/extracted/resources'
PACKAGE=ROOT/'outputs/ss6-feasibility/native-viewer/assets'
MANIFEST=ROOT/'outputs/ss6-feasibility/pause_art_tables.json'
ORIGINAL='72420e74e04d7ac39119d1b6ec7d70ed004fc98c5035fade96e87d05d4b9ffbf'
ISO_PATH=Path(json.loads((ROOT/'outputs/ss6-feasibility/iso_manifest.json').read_text())['source'])
OUT=ASSETS/'pause_art.bin'

FLOATS=dict(
    CursorStep=0x5f1f08,                                   # 17c228
    TitleX=0x658b34,TitleY=0x658b38,TitleZ=0x658b3c,       # 1da918
    RowsZ=0x658be0,                                        # 1da9c0 (113828)
    HelpTextZ=0x658be4,HelpBarZ=0x658be8,                  # 1dab38
    BoxZ=0x658bec,                                         # 1daca8
    LegendBoxZ=0x658bf0,                                   # 1dae00
    EdgeZ=0x654d84,                                        # 1c1528
    KeyBoxW=0x665224,KeyBoxH=0x665228,KeyIconZ=0x66522c,KeyCursorW=0x665230,KeyCursorH=0x665234,  # 212478
    BracketZ=0x5f1fc4,BracketArm=0x5f1fc8,                 # 17d790
    SkillIconZ=0x5e7df4,SkillBarZ=0x5e7df8,SkillBarX=0x5e7dfc,   # 13d0d0, 13d548
    SkillDimZ=0x5e7e24,                                    # 13d680
    SkillScrollW=0x6648f4,SkillScrollH=0x6648f8)           # 210298


def extract():
    data=Iso(ISO_PATH).read('/SLPS_255.59')
    if hashlib.sha256(data).hexdigest()!=ORIGINAL:raise ValueError('Expected Japanese SLPS-25559')
    elf=Elf(data)
    out=bytearray(b'PAR1')+struct.pack('<I',len(FLOATS))
    values={}
    for name,addr in FLOATS.items():
        raw=data[elf.offset(addr):elf.offset(addr)+4];out+=raw;values[name]=struct.unpack('<f',raw)[0]
    return bytes(out),values


def main():
    blob,values=extract()
    OUT.write_bytes(blob);PACKAGE.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(OUT,PACKAGE/OUT.name)
    manifest=dict(elf_sha256=ORIGINAL,asset=OUT.name,bytes=len(blob),sha256=hashlib.sha256(blob).hexdigest(),
                  constant_addresses={k:hex(a) for k,a in FLOATS.items()},constants=values)
    MANIFEST.write_text(json.dumps(manifest,indent=2)+'\n')
    print(f'{OUT} {len(blob)} bytes {manifest["sha256"]}')


if __name__=='__main__':main()
