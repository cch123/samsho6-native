#!/usr/bin/env python3
"""Extract independent, reusable display lists for the six-spirit Japanese VS screen."""
from concurrent.futures import ProcessPoolExecutor
from functools import cache
import hashlib
import struct
from extract_character_select_art import setup, QUAD, ASSETS
from extract_versus_quotes import Iso, ISO_PATH, ORIGINAL

OUT=ASSETS/'spirit_select_art.bin'
BASE={1:10,2:69,3:9,4:9,5:5,14:0}
PROMPT={13:69,17:5}
STAGE={20:30,22:29,23:29,24:5,25:0}
LABELS=0x4c96c0

@cache
def prepare():
    p=setup()
    for side in (0,1):
        for i,v in enumerate((6,0,1,2,3,4,5,0,0,0,5,0,0)):
            p.write(0x4c8d18+side*52+4*i,v,4)
    return p

def commands(p,fn,args,overlay=False):
    p.run(0x114e80);result=[];inbase=False
    def hit(pc):
        nonlocal inbase
        if pc==0x132a10:inbase=True
        if pc in (0x132eb8,0x132ce8,0x134268,0x1344f0,0x134948,0x134018):inbase=False
        if (overlay and inbase) or pc not in (0x1149d0,0x114c10,0x109f08):return
        start=p.registers[4]
        if pc==0x109f08:
            stage=tuple(struct.unpack_from('<11I',p.memory,LABELS)).index(start)
            length=(p.memory.index(0,start)-start)//2*24;x,y=p.registers[5:7]
            # Font packets use an exact Z from 348a8c, independent of the
            # ordered subdivision assigned to sprite submits by 114d88.
            z=p.read(0x348a8c,4);color=(p.registers[10]&255)<<24|0xffffff
            result.append((int(z),x,y,x+length,y+24,0,stage*24,length,(stage+1)*24,63,0,0,1,color));return
        if pc==0x114c10:
            vs=[struct.unpack_from('<fffI',p.memory,start+16*i) for i in range(4)]
            slot=0;u=v=ur=vb=0
        else:
            slot=p.registers[6]&255;w=1024 if slot==5 else 512
            vs=[struct.unpack_from('<5fI',p.memory,start+24*i) for i in range(4)]
            u,v,ur,vb=[a*w for a in (*vs[0][3:5],*vs[3][3:5])]
            assert p.registers[7]&255==1
        x,y,z=vs[0][:3];r,b=vs[3][:2]
        assert vs[1][:2]==(x,b) and vs[2][:2]==(r,y) and len({a[-1] for a in vs})==1
        # Round sprites resolve to whole logical pixels including quad clipping.
        coords=(x,y,r,b,u,v,ur,vb)
        assert all(float(a).is_integer() for a in coords),(hex(fn),coords)
        # 114d88 gives each layer an independent starting Z in multiples of
        # 100; only the original order within a layer is needed when rejoining.
        # Strip the frame allocation counter, which also increments once per
        # stage label. Keep this counter independently of the filtered group.
        result.append((int(z),*map(int,coords),slot,0,0,1,vs[0][-1]))
    p.run(fn,args,observe=hit,limit=600000)
    return result

def batch(task):
    group,choice,ph=task;p=prepare()
    if group<2:
        p.write(0x4c8d18+52*group+40,choice,4);limit=BASE[ph]
        return [((group,choice,ph,t),commands(p,0x1309a8,[group,ph,t])) for t in range(limit+1)]
    if group<4:
        p.write(0x4c3828,choice,4);limit=PROMPT[ph];side=group-2
        return [((group,choice,ph,t),commands(p,0x1309a8,[side,ph,t],True)) for t in range(limit+1)]
    p.write(0x4c8d80,choice,4)
    return [((group,choice,ph,t),commands(p,0x1309a8,[0,ph,t],True)) for t in range(STAGE[ph]+1)]

def label_atlas(p):
    font=Iso(ISO_PATH).read('/BIN/GOTH_24.BIN')
    pixels=bytearray(512*24*11)
    for j,ptr in enumerate(struct.unpack_from('<11I',p.memory,LABELS)):
        codes=bytes(p.memory[ptr:p.memory.index(0,ptr)])
        assert len(codes)%2==0 and len(codes)*12<=512
        for i,(hi,lo) in enumerate(zip(codes[::2],codes[1::2])):
            addr=(hi-(0x40 if hi>=0xa0 else 0)-0x81)*192+lo-0x40
            start=p.read(0x3aa168+4*addr,4)*312+12
            for y in range(24):
                for x in range(24):
                    pixels[(j*24+y)*512+i*24+x]=(font[start+y*12+x//2]>>(4*(x%2)))&15
    return bytes(p.memory[0x348a48:0x348a88])+pixels

def extract():
    assert hashlib.sha256((ASSETS.parent/'SLPS_255.59').read_bytes()).hexdigest()==ORIGINAL
    tasks=[(s,c,ph) for s in range(2) for c in range(6) for ph in BASE]
    tasks += [(s,c,ph) for s in (2,3) for c in range(2) for ph in PROMPT]
    tasks += [(4,c,ph) for c in range(11) for ph in STAGE]
    quads={};lists={};frames={}
    with ProcessPoolExecutor(max_workers=5) as ex:
        for batch_result in ex.map(batch,tasks):
            for key,records in batch_result:
                ids=[]
                for (d,*rest) in records:
                    # Stage glyphs keep their exact (non-incrementing) Z.
                    # For sprites the original per-frame counter is restored
                    # at the consumer after combining both player submissions.
                    if rest[8]!=63:d=d//100*100
                    ids.append(quads.setdefault(QUAD.pack(d,*rest),len(quads)))
                frames[key]=lists.setdefault(tuple(ids),len(lists))
    data=bytearray(struct.pack('<4sIII',b'SS01',len(quads),len(lists),len(frames)))
    for q in quads:data.extend(q)
    for q in lists:
        data.extend(struct.pack('<H',len(q)))
        for i in q:data.extend(struct.pack('<I',i))
    for k,v in frames.items():data.extend(struct.pack('<4BI',*k,v))
    data.extend(label_atlas(prepare()))
    return data

if __name__=='__main__':
    output=extract();OUT.write_bytes(output);print(OUT,len(output))
