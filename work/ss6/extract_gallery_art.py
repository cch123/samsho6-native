#!/usr/bin/env python3
"""Collect the constants, icon rectangles and pictures drawn by the GALLERY MODE pages.

gallery_art.bin (little endian), in order:
  'GAR1'
  u32 n, n x float      constants in the order of FLOATS (index = position)
  u32 n, n x int32[4]   icon rectangles: pointer table 4ee6b8 followed to its
                        0x18-byte records {u, v, w, h, 0, slot}; entries below
                        0x33 are drawn from slot 2e, the others from slot 5 (17e038)
  u8[6]                 edge alphas 4ee868 of the soft bar 17eed8
  2 x {u16 n, bytes}    the strings 5f2000 " " and 5f2008 "EXIT" of 17e428

The 55 pictures gl_00..gl_54 are members of SAM_DATA.BIN (archive table of the
ELF, see extract_resources.py): gl_NN.tex is the 1024x1024 8-bit index plane the
game requests as "gl_%02d.pvr" (5f2038) and gl_NN.pal the 256 16-bit colours it
requests as "gl_%02d.pvp" (5f2048). They are copied unchanged, after comparing
each with the archive bytes on the disc.
"""
import hashlib
import json
import shutil
import struct
from pathlib import Path

from inspect_iso import Elf, Iso
from extract_resources import recover

ROOT=Path(__file__).resolve().parents[2]
ASSETS=ROOT/'work/ss6/extracted/resources'
PACKAGE=ROOT/'outputs/ss6-feasibility/native-viewer/assets'
MANIFEST=ROOT/'outputs/ss6-feasibility/gallery_art_tables.json'
ORIGINAL='72420e74e04d7ac39119d1b6ec7d70ed004fc98c5035fade96e87d05d4b9ffbf'
ISO_PATH=Path(json.loads((ROOT/'outputs/ss6-feasibility/iso_manifest.json').read_text())['source'])
OUT=ASSETS/'gallery_art.bin'
PICTURES=55

# name -> address; the C++ enum GalleryArt::Constant follows this order.
FLOATS=dict(
    CursorStep=0x5f1f08,           # 17c228
    BorderZ=0x5f1f10,              # 17c3d8
    FrameZ=0x5f1f1c,Five=0x5f1f20,Two=0x5f1f24,Ten=0x5f1f28,Seven=0x5f1f2c,Fourteen=0x5f1f30,  # 17c718
    One=0x5f1f34,Twenty=0x5f1f38,Twelve=0x5f1f3c,TwentyFour=0x5f1f40,Thirteen=0x5f1f44,TwentySix=0x5f1f48,
    SmallZ=0x5f1fcc,SmallW=0x5f1fd0,SmallVh=0x5f1fd4,SmallH=0x5f1fd8,SmallUw=0x5f1fdc,        # 17dc90
    LabelFront=0x5f1ff4,LabelMiddle=0x5f1ff8,LabelZ=0x5f1ffc,       # 17e228
    MarkupFront=0x5f2010,MarkupMiddle=0x5f2014,MarkupZ=0x5f2018,    # 17e428
    GlyphDrop=0x5f201c,IconInset=0x5f2020,ExitDrop=0x5f2024,
    PictureSpan=0x5f2054,                                           # 17eda0
    ScrollZ=0x5f2058,ScrollFour=0x5f205c,ScrollEight=0x5f2060,ScrollTwo=0x5f2064,ScrollTwelve=0x5f2068,ScrollSix=0x5f206c,  # 17f090
    BackdropZ=0x5f22b8,                                             # 1817f0
    KeysZ=0x5f2378,                                                 # 181c30
    TitleZ=0x5f23ac,TitleW=0x5f23b0,TitleH=0x5f23b4,TitleSpriteZ=0x5f23b8,  # 181e88
    MessageZ=0x5f3ef4,MessageW=0x5f3ef8,MessageH=0x5f3efc,          # 182118
    ScrollW=0x664864,SmallInset=0x66486c,RowInset=0x664870,         # 20ef38, 20f050, 20f1c8
    TopPlateX=0x6575e0,TopPlateY=0x6575e4,TopPlateZ=0x6575e8,TopRowsZ=0x657640,TopHelpZ=0x657644,  # 1d2620, 1d26d0, 1d27c8
    LyricTextZ=0x5e9990,LyricZ=0x5e9994,LyricBarX=0x5e9998,LyricBarW=0x5e999c,LyricBarH=0x5e99a0,LyricKeysX=0x5e99a4,  # 13dc98
    ViewerBackingZ=0x5e9aa8,ViewerPictureZ=0x5e9aac)                # 13edf0
ICONS=72


def extract():
    disc=Iso(ISO_PATH)
    data=disc.read('/SLPS_255.59')
    if hashlib.sha256(data).hexdigest()!=ORIGINAL:raise ValueError('Expected Japanese SLPS-25559')
    elf=Elf(data)
    def raw(addr,n):
        off=elf.offset(addr);return data[off:off+n]
    def words(addr,n,fmt='i'):return struct.unpack_from(f'<{n}{fmt}',data,elf.offset(addr))
    for addr,name in ((0x5f2038,'gl_%02d.pvr'),(0x5f2048,'gl_%02d.pvp')):
        if elf.cstring(addr)!=name:raise ValueError('Unexpected 17eda0 resource name')
    out=bytearray(b'GAR1')+struct.pack('<I',len(FLOATS))
    for addr in FLOATS.values():out+=raw(addr,4)
    pointers=words(0x4ee6b8,ICONS+1,'I')
    if 0x4c0000<=pointers[ICONS]<0x4d0000:raise ValueError('Icon pointer table is longer than expected')
    out+=struct.pack('<I',ICONS);icons=[]
    for n,pointer in enumerate(pointers[:ICONS]):
        rect=words(pointer,6)
        if rect[4]!=0 or rect[5]!=(6 if n<0x33 else 5):raise ValueError('Unexpected icon rectangle record')
        out+=struct.pack('<4i',*rect[:4]);icons.append(list(rect[:4]))
    alphas=raw(0x4ee868,6)
    if alphas!=bytes((16,32,64,128,160,192)):raise ValueError('Unexpected 17eed8 alpha table')
    out+=alphas
    for addr,text in ((0x5f2000,b' '),(0x5f2008,b'EXIT')):
        if elf.cstring(addr).encode()!=text:raise ValueError('Unexpected 17e428 literal')
        out+=struct.pack('<H',len(text))+text
    floats={k:struct.unpack('<f',raw(a,4))[0] for k,a in FLOATS.items()}
    # The pictures, compared with the archive members on the disc.
    archive=disc.by_path['/SAM_DATA.BIN']
    table={e['name']:e for e in recover(elf,archive['size'])}
    blob=disc.read('/SAM_DATA.BIN')
    pictures={}
    for i in range(PICTURES):
        for ext,size in (('tex',1024*1024),('pal',512)):
            name=f'gl_{i:02d}.{ext}';entry=table[name]
            member=blob[entry['offset']:entry['offset']+entry['size']]
            if len(member)!=size or (ASSETS/name).read_bytes()!=member:raise ValueError(f'{name} differs from the archive member')
            pictures[name]=hashlib.sha256(member).hexdigest()
    if f'gl_{PICTURES:02d}.tex' in table:raise ValueError('More pictures than expected')
    return bytes(out),dict(constants=floats,icons=icons,pictures=pictures)


def main():
    blob,info=extract()
    OUT.write_bytes(blob);PACKAGE.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(OUT,PACKAGE/OUT.name)
    copied=[]
    listing={f.name for f in PACKAGE.iterdir()}
    for name in info['pictures']:
        if name not in listing or (PACKAGE/name).stat().st_size!=(ASSETS/name).stat().st_size:
            shutil.copyfile(ASSETS/name,PACKAGE/name);copied.append(name)
    manifest=dict(elf_sha256=ORIGINAL,asset=OUT.name,bytes=len(blob),sha256=hashlib.sha256(blob).hexdigest(),
                  constant_addresses={k:hex(a) for k,a in FLOATS.items()},
                  texture_slot_5='gl_NN.tex + gl_NN.pal (1024x1024 indices, 256 16-bit colours at palette 0x300, bank 0x30); '
                                 'archive members of SAM_DATA.BIN requested as gl_%02d.pvr / gl_%02d.pvp by 17eda0',
                  pictures_copied_to_package=len(copied),**info)
    MANIFEST.write_text(json.dumps(manifest,indent=2,ensure_ascii=False)+'\n')
    print(f'{OUT} {len(blob)} bytes {manifest["sha256"]} pictures={len(info["pictures"])//2} copied={len(copied)}')


if __name__=='__main__':main()
