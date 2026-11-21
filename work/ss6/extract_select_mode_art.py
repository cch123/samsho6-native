#!/usr/bin/env python3
"""Extract the character select display lists that depend on the mode word.

The two-seat lists of extract_character_select_art.py were taken with g_GameData+0 = 3.
12a418 and its callees test the mode word again while drawing: ARCADE seat 1 (mode 2) and
SURVIVAL seat 1 (0xc) use the right-hand single-seat layout, ARCADE adds the Kuroko hint
frame and button (12d860), SURVIVAL the record frame (12d410), and PRACTICE (9/10) shows
a different label on the seat its pad drives second. 128a68 draws a fixed glyph pair in
place of the countdown digits in submodes 2 and 3. Text (10a460/109f08) and the single
seat's fighter object are not part of these lists.
"""
from concurrent.futures import ProcessPoolExecutor
import hashlib
import json
import shutil
import struct
from pathlib import Path

from character_tiles_oracle import ASSETS
from extract_character_select_art import CELLS,LIMITS,QUAD,capture,setup
from extract_versus_quotes import ORIGINAL

OUT=ASSETS/'character_select_mode_art.bin'
ROOT=Path(__file__).resolve().parents[2]
PACKAGE=ROOT/'outputs/ss6-feasibility/native-viewer/assets'
MANIFEST=ROOT/'outputs/ss6-feasibility/character_select_mode_art.json'
# (mode word, submode word, seat): the page family index is the position in this table.
FAMILIES=((1,1,0),(2,1,1),(11,4,0),(12,4,1),(9,3,0),(9,3,1),(10,3,0),(10,3,1))
PHASES={1:range(1,8),2:range(1,8),11:range(1,8),12:range(1,8),9:range(1,12),10:range(1,12)}

def one(args):
    family,cell,phase=args;mode,submode,side=FAMILIES[family];p=setup()
    p.write(0x4c3808,mode,4);p.write(0x4c38a8,submode,4)
    # Same tagging as the two-seat extractor: sampled cell indices instead of characters.
    for i in range(CELLS):
        p.write(0x4c8370+200*side+4*i,i,4);p.write(0x4c82a8+4*i,i,4)
        struct.pack_into('<3h',p.memory,0x5e0530+6*i,5,i%12,i//12)
    p.write(0x4c82a0+4*side,cell,4)
    return [(family,cell,phase,t,capture(p,0x12a418,(side,phase,t,int(phase in (2,5)),0),True))
            for t in range(LIMITS[phase]+1)]

def extract():
    assert hashlib.sha256((ASSETS.parent/'SLPS_255.59').read_bytes()).hexdigest()==ORIGINAL
    tasks=[(f,c,ph) for f,(mode,_,_) in enumerate(FAMILIES) for c in range(6) for ph in PHASES[mode]]
    pool={};lists={};frames={}
    def intern(records):
        ix=tuple(pool.setdefault(QUAD.pack(*r),len(pool)) for r in records)
        return lists.setdefault(ix,len(lists))
    with ProcessPoolExecutor(max_workers=6) as ex:
        for batch in ex.map(one,tasks):
            for family,cell,phase,t,data in batch:frames[family,cell,phase,t]=intern(data)
    # 128be8: submodes 2/3 never show digits.
    p=setup();p.write(0x4c38a8,3,4);p.write(0x4c8280,0,4);p.write(0x4c8288,1739,4)
    stopped=intern(capture(p,0x128a68,[]))
    p.write(0x4c38a8,2,4);assert intern(capture(p,0x128a68,[]))==stopped
    data=bytearray(struct.pack('<4sIII',b'CSM1',len(pool),len(lists),len(frames)))
    for q in pool:data.extend(q)
    for indices in lists:
        data.extend(struct.pack('<H',len(indices)))
        for i in indices:data.extend(struct.pack('<I',i))
    for (f,c,ph,t),idx in frames.items():data.extend(struct.pack('<4BI',f,c,ph,t,idx))
    data.extend(struct.pack('<I',stopped))
    return data,dict(quads=len(pool),lists=len(lists),pages=len(frames))

if __name__=='__main__':
    data,counts=extract();OUT.write_bytes(data);shutil.copyfile(OUT,PACKAGE/OUT.name)
    MANIFEST.write_text(json.dumps(dict(asset=OUT.name,bytes=len(data),sha256=hashlib.sha256(data).hexdigest(),elf_sha256=ORIGINAL,
        families=[dict(index=i,mode=m,submode=s,seat=seat) for i,(m,s,seat) in enumerate(FAMILIES)],**counts,
        source='12a418 sprite/flat submissions per (family, cursor row, phase, count) and the 128a68 stopped-countdown list (submodes 2/3)'),indent=2)+'\n')
    print(OUT,len(data),counts)
