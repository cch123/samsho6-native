#!/usr/bin/env python3
"""Recover the Japanese factory ranking screen's original draw lists and sampled palettes."""
from concurrent.futures import ProcessPoolExecutor
from functools import lru_cache
import struct
import numpy as np
from character_tiles_oracle import ASSETS
from extract_console_versus_art import prepare,PACKETS,GLYPH
from validate_console_attract_ranking import RANK

OUTPUT=ASSETS/'console_ranking_art.bin'
LENGTHS=(1,540,60,360,60,360,65,2,240,60,19*72+361,2)

def unpack4(buf,w):
    packed=np.frombuffer(buf,np.uint8).reshape(-1,w//2)
    indices=np.empty((len(packed),w),np.uint8)
    indices[:,::2]=packed&15;indices[:,1::2]=packed>>4
    return indices

def setup():
    p=prepare()
    p.run(0x1c51b0,[0x5797ec]);p.run(0x1b8c98)
    p.run(0x315f38,[RANK,0,0x264]);p.put(21,RANK)
    p.run(0x1e88c0,limit=50000,stop_before=(0x1e898c,))
    assert [p.read(RANK+4+24*i,4) for i in range(5)]==list(range(5,0,-1))
    assert [p.read(RANK+124+24*i,4) for i in range(20)]==list(range(200000,0,-10000))
    p.write(0x4c81b4,30,4);p.write(0x4c81cc,43,4);p.write(0x3a9680+8*40+36,1,4)
    # Original map conversion after the disc read, before the hardware upload.
    raw=(ASSETS/'map_main.pal').read_bytes();p.memory[0x1fff210:0x1fff410]=raw;p.put(2,512)
    p.run(0x113980,stop_before=(0x1139ec,))
    blank=bytearray((ASSETS/'obj0.pal').read_bytes())
    for at in range(0,len(blank),32):blank[at:at+2]=bytes(2)
    p.memory[0x1e60000:0x1e60000+len(blank)]=blank;p.write(0x439b68,0,4)
    p.run(0x116478,[0,128,0x1e60000]);p.run(0x10a920,[0x43ab70,128]);p.run(0x116588,limit=500000)
    return p

def materials(p):
    def palette(addr,n):return bytes(p.memory[addr:addr+n*4])
    raw=(ASSETS/'rank_obj.tex').read_bytes()
    resident=np.frombuffer(raw,np.uint8,1024,512*512).reshape(8,4,8,4)[:,[0,2,1,3]].reshape(256,4)
    mats={8:(512,512,resident.tobytes(),raw[:512*512]),
          41:(1024,1024,palette(0x1232880,256),(ASSETS/'map_main.tex').read_bytes())}
    for slot,name in [(30,'cloud_l'),(43,'cloud_r')]:
        # Both clouds use the resident bank zero (3081), even after the optical loads.
        mats[slot]=(512,512,palette(0x11e7980,16),unpack4((ASSETS/(name+'.tex')).read_bytes(),512).tobytes())
    face=unpack4((ASSETS/'face.tex').read_bytes(),512)
    for char in range(20):
        p.run(0x114e80);p.write(0x439a40,0,4)
        bank,_=p.run(0x115d40,[char*5,31],limit=50000);p.run(0x116588,limit=500000)
        x,y=char%8*64,char//8*64
        mats[100+char]=(64,64,palette(0x11e7980+64*bank,16),face[y:y+64,x:x+64].tobytes())
    return mats

def capture(p,phase,tick,first=None):
    if phase in (0,1,5,11):return []
    if phase==7:
        # Continue after the two optical texture loads. The trailing opaque
        # rectangle is submitted by the original phase-7 callback itself.
        entry=0x1e9174;p.write(0x1fff008,0x1ffff00,8)
    else:entry=0x1e8b38
    if first is None:first=max(0,19-max(0,tick-1)//72) if phase==10 else 0
    for off,value in ((0x258,phase),(0x25c,first),(0x260,tick)):p.write(RANK+off,value,4)
    p.run(0x114e80)
    for a in (0x345178,0x345180,0x378e08,0x3ec73c,0x439a40):p.write(a,0,4)
    cloud_slots=[];last_slot=0
    def observe(pc):
        nonlocal last_slot
        if pc==0x1149d0:last_slot=p.registers[6]&255
        if pc==0x108464 and last_slot in (30,43):cloud_slots.append(last_slot)
    p.run(entry,limit=350000,observe=observe if phase==8 else None,
          stop_before=(0x115a00,) if phase==6 and tick==64 else ())
    clouds=iter(cloud_slots);result=[]
    for i in range(p.read(0x345178,4)):
        a=PACKETS+128*i;kind,col,tex,ptr,n,u1,xy1=struct.unpack_from('<7Q',p.memory,a);color=col&0xffffffff
        if kind==0x1ff3:
            verts=[p.read(a+16+16*j,8) for j in (0,3)]
            (x,y),(r,b)=[(((q&65535)-0x6c00)//16,(((q>>16)&65535)-0x7900)//8) for q in verts]
            z=verts[0]>>32;key=0;u=v=ur=vb=0
        elif kind==0x1ff2:
            page=(tex>>37)&16383;assert n==4
            x,y,z,u,v,_=struct.unpack_from('<5fI',p.memory,ptr)
            r,b,_,ur,vb,_=struct.unpack_from('<5fI',p.memory,ptr+72)
            if page==0x3119:key=8
            elif page==0x3101:key=41
            elif phase==8 and page==0x3081:key=next(clouds)
            else:
                assert (tex>>20)&63==20 and 0x3081<=page<0x30c1,(phase,tick,hex(page))
                char=int(u)//64+8*(int(v)//64);assert 0<=char<20
                key=100+char;du,dv=char%8*64,char//8*64;u-=du;ur-=du;v-=dv;vb-=dv
        elif kind==0x1ff1:
            assert (tex>>37)&16383==0x3080
            (x,y),(r,b)=[(((q&65535)-p.read(0x32ce14,4))//16,(((q>>16)&65535)-p.read(0x32ce18,4))//16) for q in (n,xy1)]
            z=(n>>32)&0x7fffffff;u=(ptr&65535)//16;v=(ptr>>16&65535)//16
            assert u1-ptr==(r-x)*16+(b-y)*16*65536 and not u%2
            image=b''.join(p.memory[GLYPH+(v+j)*256+u//2:GLYPH+(v+j)*256+u//2+(r-x)//2] for j in range(b-y))
            key=(r-x,b-y,image);u=v=0;ur=r-x;vb=b-y
        else:raise ValueError(hex(kind))
        values=(x,y,r,b,u,v,ur,vb)
        assert all(int(v)==v for v in values),(phase,tick,key,values)
        result.append((z,(key,*map(int,values),color)))
    return [q for _,q in sorted(result,key=lambda q:q[0])]

@lru_cache(maxsize=1)
def worker_source():return setup()

def batch(group):
    phase,start,end=group;p=worker_source()
    return phase,start,[capture(p,phase,t) for t in range(start,end)]

def extract():
    p=setup();mats=materials(p)
    frame_ids=[[] for _ in LENGTHS];indices={};unique=[];lists={};frames=[]
    groups=[(ph,start,min(start+32,n)) for ph,n in enumerate(LENGTHS) for start in range(0,n,32)]
    with ProcessPoolExecutor(max_workers=4) as pool:
        for ph,offset,group in pool.map(batch,groups):
            assert offset==len(frame_ids[ph])
            for draw in group:
                ids=[]
                for q in draw:
                    key=q[0]
                    if isinstance(key,tuple) and key not in mats:
                        w,h,mask=key;mats[key]=(w,h,bytes(p.memory[0x348a48:0x348a88]),unpack4(mask,w).tobytes())
                    if q not in indices:indices[q]=len(unique);unique.append(q)
                    ids.append(indices[q])
                seq=tuple(ids)
                if seq not in lists:lists[seq]=len(frames);frames.append(seq)
                frame_ids[ph].append(lists[seq])
    lookup={key:i+1 for i,key in enumerate(mats)};lookup[0]=0
    data=bytearray(struct.pack('<4sIIII',b'RNK1',len(mats),len(unique),len(frames),len(LENGTHS)))
    for w,h,pal,img in mats.values():data+=struct.pack('<3H',w,h,len(pal)//4)+pal+img
    for key,*sides,col in unique:data+=struct.pack('<B8hI',lookup[key],*sides,col)
    for seq in frames:data+=struct.pack('<H',len(seq))+struct.pack(f'<{len(seq)}I',*seq)
    for seq in frame_ids:data+=struct.pack('<H',len(seq))+struct.pack(f'<{len(seq)}H',*seq)
    return data

if __name__=='__main__':
    data=extract();OUTPUT.write_bytes(data);print(OUTPUT,len(data))
