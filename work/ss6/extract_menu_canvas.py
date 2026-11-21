#!/usr/bin/env python3
"""Collect the original tables, strings and fonts used by the shared menu drawing layer.

menu_canvas.bin (little endian), in order:
  'MCV1'
  7 x int32[11]   band alpha 582b48, top y/h 582b78/582ba8, middle y/h 656be0/656c10,
                  bottom y/h 582bd8/582c08 (1ce660)
  3 x {int32[4] x, float z}   legend tables 656ac0, 656ad8, 656af0 (1ced08/1cee68/1cefc8)
  12 + 9 + 6 x int32[4]       sheet rectangles 4c7510 (icons), 4c7660 (banners; index 8 is
                              the gallery plate 4c7720), 4c7960 (overlay frames)
  int32[6]        background descriptor 582b10
  float[29]       depth and geometry constants (see FLOATS)
  10 x {u16 n, bytes}         strings (see STRINGS, then the two dialog options 656b58)
  int32[2]        dialog option x 656b60
  u8[64]          text CLUT 348a48
  360 x {u32 cos, u32 sin}    10b4b8 / 10b4f8 at degree*182 (1e2048)
  u8[32768]       GOTH_H.BIN: the 256x256 PSMT4 half-width sheet uploaded to 3000 by 1003f4
  u16[8064]       glyph index table 3aa168 (42 lead rows x 192)
  u32 count, count x u8[200] GOTH_20 rows, count x u8[288] GOTH_24 rows
"""
import hashlib
import json
import shutil
import struct
from pathlib import Path

from inspect_iso import Elf, Iso
from mips_probe import Probe

ROOT=Path(__file__).resolve().parents[2]
ASSETS=ROOT/'work/ss6/extracted/resources'
PACKAGE=ROOT/'outputs/ss6-feasibility/native-viewer/assets'
MANIFEST=ROOT/'outputs/ss6-feasibility/menu_canvas_tables.json'
ORIGINAL='72420e74e04d7ac39119d1b6ec7d70ed004fc98c5035fade96e87d05d4b9ffbf'
ISO_PATH=Path(json.loads((ROOT/'outputs/ss6-feasibility/iso_manifest.json').read_text())['source'])
OUT=ASSETS/'menu_canvas.bin'

BANDS=(0x582b48,0x582b78,0x582ba8,0x656be0,0x656c10,0x582bd8,0x582c08)
LEGENDS=(0x656ac0,0x656ad8,0x656af0)
# 0,1 legend text z; 2,3 page indicator z; 4,5 background z (1ce570, 1ce628);
# 6..17 overlay 65ae58..65ae84; 18,19 marker size 656c44; 20 depth-cursor step 5f1f08;
# 21..25 marker 5f1fe0..5f1ff0; 26,27 dialog z 656bd4, 656bd8; 28 overlay texel inset 65ae88.
FLOATS=(0x656b10,0x656b24,0x656b34,0x656b44,0x656aa0,0x656aa4,
        *range(0x65ae58,0x65ae88,4),0x656c44,0x656c48,0x5f1f08,
        0x5f1fe0,0x5f1fe4,0x5f1fe8,0x5f1fec,0x5f1ff0,0x656bd4,0x656bd8,0x65ae88)
STRINGS=dict(confirm=0x656b08,cancel=0x656b18,page=0x656b38,number=0x656b28,slash=0x656b30,
             neogeo=0x656b78,reselect=0x656bb0,title=0x656b98)
# Disc textures behind the three sheet slots this layer draws from. 1ce478 binds
# "PS2_menu_bg00_00.pvr"/".pvp" to slot 4; the archive stores them as .tex/.pal.
TEXTURES=('PS2_menu_bg00_00.tex','PS2_menu_bg00_00.pal','ps2_common_icon.tex','ps2_common_icon.pal','obj0_16.tex')


def extract():
    disc=Iso(ISO_PATH)
    data=disc.read('/SLPS_255.59')
    if hashlib.sha256(data).hexdigest()!=ORIGINAL:raise ValueError('Expected Japanese SLPS-25559')
    elf=Elf(data)
    def raw(addr,n):
        off=elf.offset(addr);return data[off:off+n]
    def words(addr,n,fmt='i'):return struct.unpack_from(f'<{n}{fmt}',data,elf.offset(addr))
    def text(addr):
        off=elf.offset(addr);return data[off:data.index(0,off)]
    for name,path in (('PS2_menu_bg00_00.pvr',0x656a70),('PS2_menu_bg00_00.pvp',0x656a88)):
        if elf.cstring(path)!=name:raise ValueError('Unexpected 1ce478 background resource')
    for addr,name in ((0x5d4620,'GOTH_20'),(0x5d4640,'GOTH_24'),(0x5d4660,'GOTH_H')):
        if elf.cstring(addr)!=rf'cdrom0:\BIN\{name}.BIN;1':raise ValueError('Unexpected 109e20 font source')
    out=bytearray(b'MCV1')
    for addr in BANDS:out+=raw(addr,44)
    for addr in LEGENDS:out+=raw(addr,20)
    for addr,count in ((0x4c7510,12),(0x4c7660,9),(0x4c7960,6)):
        for i in range(count):
            rect=words(addr+24*i,6)
            if rect[4:]!=(0,6):raise ValueError('Unexpected sheet rectangle record')
            out+=struct.pack('<4i',*rect[:4])
    if words(0x582b10,6)!=(0,0,640,448,0,4):raise ValueError('Unexpected background descriptor')
    out+=raw(0x582b10,24)
    for addr in FLOATS:out+=raw(addr,4)
    yes,no=words(0x656b58,2,'I')
    strings=[text(a) for a in STRINGS.values()]+[text(yes),text(no)]
    # The legend routines keep their names from the first row of the option
    # page: 1cf178 prints 656b08 and 1cf210 prints 656b18.
    for s in strings:
        s.decode('cp932');out+=struct.pack('<H',len(s))+s
    out+=raw(0x656b60,8)
    clut=raw(0x348a48,64)
    if any(clut[4*i:4*i+3]!=b'\xff\xff\xff' for i in range(16)):raise ValueError('Unexpected text CLUT')
    out+=clut
    p=Probe(data,finite_model=True);instructions=0
    for degree in range(360):
        for fn in (0x10b4b8,0x10b4f8):
            _,n=p.run(fn,[degree*0xb6]);instructions+=n;out+=struct.pack('<I',p.floats[0])
    half=disc.read('/BIN/GOTH_H.BIN')
    if len(half)!=32768:raise ValueError('Unexpected GOTH_H.BIN size')
    out+=half
    index=words(0x3aa168,42*192,'I')
    small=disc.read('/BIN/GOTH_20.BIN');large=disc.read('/BIN/GOTH_24.BIN')
    count=len(small)//220
    if len(small)!=count*220 or len(large)!=count*312 or max(index)!=count-1:
        raise ValueError('Glyph index table does not match the font files')
    out+=struct.pack(f'<{len(index)}H',*index)+struct.pack('<I',count)
    # 10a82c copies 20 rows of 10 bytes from +0xa; 10a2ec copies 24 rows of 12 from +0xc.
    for i in range(count):out+=small[i*220+10:i*220+210]
    for i in range(count):out+=large[i*312+12:i*312+300]
    fonts={n:hashlib.sha256(d).hexdigest() for n,d in (('GOTH_H.BIN',half),('GOTH_20.BIN',small),('GOTH_24.BIN',large))}
    return bytes(out),dict(glyph_records=count,index_entries=len(index),trig_instructions=instructions,
                           strings={k:s.decode('cp932') for k,s in zip([*STRINGS,'yes','no'],strings)},fonts=fonts)


def main():
    blob,info=extract()
    OUT.write_bytes(blob);PACKAGE.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(OUT,PACKAGE/OUT.name)
    copied=[]
    resources={}
    listing={f.name for f in PACKAGE.iterdir()}
    for name in TEXTURES:
        source=ASSETS/name;resources[name]=hashlib.sha256(source.read_bytes()).hexdigest()
        # The archive names differ only by case from other entries on a
        # case-insensitive volume, so compare the directory listing itself.
        if name not in listing:
            shutil.copyfile(source,PACKAGE/name);copied.append(name)
    manifest=dict(elf_sha256=ORIGINAL,asset=OUT.name,bytes=len(blob),sha256=hashlib.sha256(blob).hexdigest(),
                  texture_slots={'1':'obj0_16.tex (512x512 indices + embedded 16x16 CLUT)',
                                 '4':'PS2_menu_bg00_00.tex + PS2_menu_bg00_00.pal (1024x1024, 16-bit CLUT at palette 0x200; NOT menu_bg00_00.tex)',
                                 '46':'ps2_common_icon.tex + ps2_common_icon.pal (512x512, TBP 318d, CBP 3111)'},
                  textures=resources,textures_copied_to_package=copied,**info)
    MANIFEST.write_text(json.dumps(manifest,indent=2,ensure_ascii=False)+'\n')
    print(f'{OUT} {len(blob)} bytes {manifest["sha256"]} copied={copied}')


if __name__=='__main__':main()
