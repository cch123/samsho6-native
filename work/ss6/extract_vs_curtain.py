#!/usr/bin/env python3
"""Capture the Japanese transition's 33 slot-3 sprite lists (before GS submission)."""
import hashlib
import struct
from character_tiles_oracle import ASSETS
from extract_versus_result_layout import canvas

LAYOUT=ASSETS/'vs_curtain.bin'
TASK,OLD,NEW=0x1c50000,0x1c40000,0x1c40010
STATE=0x1239da0

def timeline():
    p=canvas();slot=0x3a9680+3*40
    assert p.memory[0x5dd538:0x5dd538+18].split(b'\0')[0]==b'change_base16.pvr'
    assert hashlib.sha256((ASSETS.parent/'SLPS_255.59').read_bytes()).hexdigest()=='72420e74e04d7ac39119d1b6ec7d70ed004fc98c5035fade96e87d05d4b9ffbf'
    p.write(0x1239d98,TASK,4);p.write(0x4c38a8,2,4)
    # The previous/new scene and audio queue are the three external endpoints.
    # The entire transition dispatcher and every drawing callback execute.
    for fn in (OLD,NEW,0x1e7b70):
        p.write(fn,0x03e00008,4);p.write(fn+4,0,4)
    for off,v in [(4,512),(8,512),(12,19),(20,9),(24,9),(36,1)]:p.write(slot+off,v,4)
    p.run(0x1252f0,[3,0,OLD,NEW]);assert p.read(TASK+4,4)==0x10
    for tick in range(33):
        p.run(0x114e80);sprites=[];events=[]
        phase=p.read(STATE+4,4);age=p.read(STATE+8,4)
        def visit(pc):
            if pc==0x1149d0:
                verts=[struct.unpack_from('<5fI',p.memory,p.registers[4]+j*24) for j in range(4)]
                sprites.append((p.registers[6]&255,verts))
            elif pc in (OLD,NEW):events.append('old' if pc==OLD else 'new')
            elif pc==0x1e7b70:events.append((p.registers[4]&0xffffffff,p.registers[5]))
        p.run(0x1251d0,[TASK],observe=visit,limit=1000000)
        assert (phase,age)==((1,tick) if tick<15 else (2,tick-15) if tick<18 else (3,tick-18))
        assert events==([(0xffffffff,15)] if tick==15 else ['old','new'] if tick==17 else [])
        yield sprites
    assert p.read(STATE+4,4)==0 and p.read(TASK+4,4)==17

def extract():
    data=bytearray(b'CVD1')
    for sprites in timeline():
        data.extend(struct.pack('B',len(sprites)))
        for slot,quad in sorted(sprites,key=lambda item:item[1][0][2]):
            pts=[(x,y,u*512,v*512) for x,y,z,u,v,col in quad]
            assert slot==3 and all(col==0xffffffff for *_,col in quad)
            (x,y,u,v),(x2,y2,u2,v2),(x3,y3,u3,v3),(r,b,eu,ev)=pts
            assert (x2,y2,u2,v2)==(x,b,u,ev) and (x3,y3,u3,v3)==(r,y,eu,v)
            assert abs(r-x)==eu-u and b-y==ev-v and all(n==int(n) for pt in pts for n in pt)
            data.extend(struct.pack('<8h',*map(int,(x,y,r,b,u,v,eu,ev))))
    LAYOUT.write_bytes(data)
    return LAYOUT
if __name__=='__main__':print(extract())
