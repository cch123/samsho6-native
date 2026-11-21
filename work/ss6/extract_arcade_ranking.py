#!/usr/bin/env python3
"""Pin the ranking scene's (1e8850) draw tables, name glyph map and resident CLUTs."""
import hashlib
import json
import shutil
import struct
from pathlib import Path
from inspect_iso import Elf
from extract_collision_tables import SOURCE_HASH

ROOT=Path(__file__).resolve().parents[2]
RESOURCES=ROOT/'work/ss6/extracted/resources'
VIEWER=ROOT/'outputs/ss6-feasibility/native-viewer/assets'
OUTPUT='arcade_ranking.bin'
TEXTURES=('rank_obj.tex','map_main.tex','cloud_l.tex','cloud_r.tex','face.tex')
RECORDS=(0x4c7c18,58)       # {u, v, w, h, flags, slot}, 4c7c18..4c8170
CLOUDS=(0x4c81a0,0x4c81b8)
FLOATS=(0x6632c0,90)        # Bezier tables and literals of 1e8bb8..1ea7b8
SCALARS=(0x66357c,0x5df490,0x5df494)
MAP=0x5852a0                # {slot, u, v, uw, vh} of 1ea3d8
GLYPHS=0x585300             # SJIS pointers of 1ea578
FACES=52                    # pal_all holds 260 colour keys; 115d40 uses character*5

def glyph_map(raw,elf):
    word=lambda at:struct.unpack_from('<I',raw,elf.offset(at))[0]
    def text(at):
        o=elf.offset(at);return raw[o:raw.index(b'\0',o)]
    out=[]
    for c in range(256):
        s=c-256 if c>=128 else c
        if 0x41<=s<=0x5a:index=s-0x41
        elif 0x30<=s<=0x39:index=s-0x30+30
        elif 0x21<=s<=0x5f:
            index={0x2e:0x2a,0x21:0x28,0x2d:0x2c,0x3f:0x29,0x2f:0x2b,0x5f:0x2d}.get(s,s)
        else:index=None  # 1ea6e0 copies the full-width space at 6634f8
        if index is None:code=text(0x6634f8)
        else:
            pointer=word(GLYPHS+4*index)
            try:code=text(pointer)
            except ValueError:code=b''
        # Codes other than one SJIS character would overflow the 8-byte row
        # name; they are not produced by the name entry or the defaults.
        # Byte 0 terminates the name.
        out.append(code if c and len(code)==2 and code[0]>=0x81 else b'\0\0')
    return out

def palettes():
    import numpy as np
    from extract_console_ranking_art import setup
    p=setup()
    colours=lambda at,n:bytes(p.memory[at:at+4*n])
    tex=(RESOURCES/'rank_obj.tex').read_bytes()
    # The CLUT appended to rank_obj is uploaded as one 16x16 CSM1 block.
    rank=np.frombuffer(tex,np.uint8,1024,512*512).reshape(8,4,8,4)[:,[0,2,1,3]].reshape(256,4).tobytes()
    out=[rank,colours(0x1232880,256),colours(0x11e7980,16)]
    for char in range(FACES):
        # 115a00 empties the 24-entry CLUT cache; the main loop (111890 ->
        # 113aa8) releases its use marks every frame, so no face is evicted.
        p.run(0x114e80);p.write(0x439a40,0,4);p.run(0x115a00)
        bank,_=p.run(0x115d40,[char*5,31],limit=50000);assert bank<64,char;p.run(0x116588,limit=500000)
        out.append(colours(0x11e7980+64*bank,16))
    # 1ea578 in place: every supported byte becomes its two-byte code.
    return out,p

def main():
    raw=(ROOT/'work/ss6/extracted/SLPS_255.59').read_bytes()
    assert hashlib.sha256(raw).hexdigest()==SOURCE_HASH
    elf=Elf(raw)
    word=lambda at:struct.unpack_from('<I',raw,elf.offset(at))[0]
    # 1e8994..1e89b8: the scene entry binds the two cloud records to slots
    # 1e and 2b, where 1e8aa8 loads cloud_l and cloud_r.
    assert [word(a) for a in (0x1e8994,0x1e89a4,0x1e89a8,0x1e89b8)]==[0x240e001e,0xadee81b4,0x240d002b,0xaded81cc]
    records=[[word(RECORDS[0]+0x18*i+4*k) for k in range(6)] for i in range(RECORDS[1])]
    clouds=[[word(a+4*k) for k in range(6)] for a in CLOUDS]
    clouds[0][5]=0x1e;clouds[1][5]=0x2b
    floats=[word(FLOATS[0]+4*i) for i in range(FLOATS[1])]+[word(a) for a in SCALARS]
    maprect=[word(MAP+4*i) for i in range(5)]
    glyphs=glyph_map(raw,elf)
    pals,p=palettes()
    for c in range(256):
        if glyphs[c]==b'\0\0':continue
        p.memory[0x1fff000:0x1fff004]=bytes([c,0,0,0])
        p.run(0x1ea578,[0x1fff100,0x1fff000],limit=5000)
        assert bytes(p.memory[0x1fff100:0x1fff103])==glyphs[c]+b'\0',hex(c)
    data=bytearray(b'RNKA'+struct.pack('<I',1))
    for r in records+clouds:data+=struct.pack('<6i',*[v-(1<<32) if v>=1<<31 else v for v in r])
    data+=struct.pack(f'<{len(floats)}I',*floats)+struct.pack('<5I',*maprect)
    data+=b''.join(glyphs)
    for pal in pals:data+=pal
    (RESOURCES/OUTPUT).write_bytes(data)
    shutil.copyfile(RESOURCES/OUTPUT,VIEWER/OUTPUT)
    hashes={}
    for name in TEXTURES:
        shutil.copyfile(RESOURCES/name,VIEWER/name)
        hashes[name]=hashlib.sha256((RESOURCES/name).read_bytes()).hexdigest()
    report=dict(elf_sha256=SOURCE_HASH,asset=OUTPUT,bytes=len(data),sha256=hashlib.sha256(data).hexdigest(),
                records=f'{RECORDS[0]:#x} x {RECORDS[1]}',clouds=list(map(hex,CLOUDS)),floats=f'{FLOATS[0]:#x} x {FLOATS[1]}',
                scalars=list(map(hex,SCALARS)),map=hex(MAP),glyph_bytes=sum(g!=b'\0\0' for g in glyphs),
                faces=FACES,textures=hashes,
                scope='Static tables read from the pinned ELF; CLUTs are the resident values after the original '
                      '113980 / 115d40 / 116588 conversions in Probe; 1ea578 rechecked for every supported byte.')
    (ROOT/'outputs/ss6-feasibility/arcade_ranking_tables.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()
