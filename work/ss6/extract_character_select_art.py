#!/usr/bin/env python3
"""Extract parameterized character select display lists from the Japanese menu.

The native port presents the fully unlocked select screen: unlock bytes 0x43d06e+c for
c = 40..48 are 0 (the network "original" setting 1d9258), so 1281e0 chooses the 8x6
layout of 48 cells whose 8th column is 41,44,45,47,46,40 and cell 36 is Purple Nakoruru.
"""
from concurrent.futures import ProcessPoolExecutor
from functools import cache
import hashlib
import struct
from character_tiles_oracle import ASSETS
from extract_versus_result_layout import canvas
from extract_versus_quotes import ORIGINAL

OUT=ASSETS/'character_select_art.bin'
QUAD=struct.Struct('<i8h4BI')
FACES=(0x12a91c,0x12ae1c,0x12b4b0,0x12ba1c)
NAME=(0x12c340,0x12c3bc,0x12c580,0x12c5fc)
NAMES=(0x12c3bc,0x12c5fc)
LIMITS=(0,59,69,9,9,14,9,5,14,14,0,14)
CELLS=48

@cache
def setup():
    p=canvas();p.run(0x1113e8,[0x43d058]);p.write(0x4c3808,3,4)
    for c in range(40,49):p.write(0x43d06e+c,0,1)  # every hidden character unlocked
    # The startup helper prints the roster to its debugging terminal. Stub
    # only that printf and stop where the task is registered; neither draws.
    p.write(0x323050,0x03e00008,4);p.write(0x323054,0,4)
    for i,v in enumerate((8,6,9,CELLS)):p.write(0x4c8838+4*i,v,4)
    for side in (0,1):p.run(0x128c78,[side],stop_before=(0x1129c8,),limit=500000)
    return p

def capture(p,fn,args,tags=False):
    p.run(0x114e80);out=[];caller=0
    def observe(pc):
        nonlocal caller
        if pc==0x113f98:caller=p.registers[31]-8
        if pc not in (0x1149d0,0x114c10):return
        start=p.registers[4];slot=p.registers[6]&255 if pc==0x1149d0 else 0
        if slot:
            w=1024 if slot==5 else 512
            vs=[struct.unpack_from('<5fI',p.memory,start+24*i) for i in range(4)]
            x,y,z,u,v,color=vs[0];r,b,_,ur,vb,_=vs[3]
            assert vs[1][:2]==(x,b) and vs[2][:2]==(r,y) and vs[1][3:5]==(u,vb) and vs[2][3:5]==(ur,v)
            u,v,ur,vb=[a*w for a in (u,v,ur,vb)];blend=p.registers[7]&255
        else:
            vs=[struct.unpack_from('<fffI',p.memory,start+16*i) for i in range(4)]
            x,y,z,color=vs[0];r,b=vs[3][:2];u=v=ur=vb=0;blend=1
        vals=[x,y,r,b,u,v,ur,vb];assert all(float(a).is_integer() for a in vals),(hex(caller),vals)
        x,y,r,b,u,v,ur,vb=map(int,vals);kind=ref=0
        if tags and slot==5 and caller in FACES:
            kind=1;ref=u//85+12*(v//66);assert ref in range(CELLS),(hex(caller),ref,u,v)
            ur-=u;vb-=v;u=v=0
        elif tags and slot==5 and caller in NAME:
            kind=3 if caller in NAMES else 2
            if kind==3:
                cell=p.read(0x4c82a0+4*args[0],4)
                nx,ny=struct.unpack_from('<2i',p.memory,0x4c8878+24*cell)
                u-=nx;v-=ny;ur-=nx;vb-=ny
        out.append((int(z)-len(out),x,y,r,b,u,v,ur,vb,slot,kind,ref,blend,color))
    p.run(fn,args,observe=observe,limit=600000)
    return out

def one(args):
    side,cell,phase=args;p=setup()
    # Tag the sampled cell indices. Moving by a whole column only rotates
    # the faces; the runtime uses the original character-to-atlas table.
    for i in range(CELLS):
        p.write(0x4c8370+200*side+4*i,i,4);p.write(0x4c82a8+4*i,i,4)
        struct.pack_into('<3h',p.memory,0x5e0530+6*i,5,i%12,i//12)
    p.write(0x4c82a0+4*side,cell,4)
    return [(side,cell,phase,t,capture(p,0x12a418,(side,phase,t,int(phase in (2,5)),0),True))
            for t in range(LIMITS[phase]+1)]

def extract():
    assert hashlib.sha256((ASSETS.parent/'SLPS_255.59').read_bytes()).hexdigest()==ORIGINAL
    p=setup();faces=[struct.unpack_from('<3h',p.memory,0x5e0530+6*i) for i in range(54)]
    names=[struct.unpack_from('<4i',p.memory,0x4c8878+24*i) for i in range(49)]
    assert all(s==5 for s,_,_ in faces) and all(w==177 and h==19 for _,_,w,h in names)
    tasks=[(s,c,ph) for s in range(2) for c in range(6) for ph in range(1,12)]
    pool={};lists={};frames={}
    def intern(records):
        ix=tuple(pool.setdefault(QUAD.pack(*r),len(pool)) for r in records)
        return lists.setdefault(ix,len(lists))
    with ProcessPoolExecutor(max_workers=5) as ex:
        for batch in ex.map(one,tasks):
            for side,cell,phase,t,data in batch:frames[side,cell,phase,t]=intern(data)
    header=[]
    for sec in range(31):
        p.write(0x4c8280,0,4);p.write(0x4c8288,sec*60,4)
        header.append(intern(capture(p,0x128a68,[])))
    data=bytearray(struct.pack('<4sIII',b'CS01',len(pool),len(lists),len(frames)))
    for s,x,y in faces:data.extend(struct.pack('<2H',85*x,66*y))
    for x,y,_,_ in names:data.extend(struct.pack('<2H',x,y))
    for q in pool:data.extend(q)
    for indices in lists:
        data.extend(struct.pack('<H',len(indices)))
        for i in indices:data.extend(struct.pack('<I',i))
    for (s,c,ph,t),idx in frames.items():data.extend(struct.pack('<4BI',s,c,ph,t,idx))
    data.extend(struct.pack('<31I',*header));return data

if __name__=='__main__':
    data=extract();OUT.write_bytes(data);print(OUT,len(data))
