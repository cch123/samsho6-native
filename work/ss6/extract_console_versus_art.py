#!/usr/bin/env python3
"""Extract the Japanese console VS menu's individual GS glyphs/icons and original placement."""
import hashlib
import struct
import numpy as np
from character_tiles_oracle import ASSETS
from extract_versus_result_layout import canvas
from extract_versus_quotes import ISO_PATH, Iso, ORIGINAL

OUT=ASSETS/'console_versus_art.bin'
GLYPH=0x1d40000
PACKETS=0x68c3c0
def prepare():
    iso=Iso(ISO_PATH)
    assert hashlib.sha256(iso.read('/SLPS_255.59')).hexdigest()==ORIGINAL
    p=canvas()
    for a,v in [(0x3ec73c,0),(0x32ce08,1),(0x3a9c20,GLYPH),(0x43d064,256)]:p.write(a,v,4)
    for size,addr in [(20,0xff1040),(24,0x106b840)]:
        data=iso.read(f'/BIN/GOTH_{size}.BIN');p.memory[addr:addr+len(data)]=data
    for slot,name,append in [(1,'obj0_16',1),(46,'ps2_common_icon',0)]:
        data=(ASSETS/(name+'.tex')).read_bytes();base=0x1cc0000+slot*0x5000
        p.memory[base:base+len(data)]=data
        for off,value in [(0,base),(4,512),(8,512),(12,19),(20,9),(24,9),(36,append)]:
            p.write(0x3a9680+slot*40+off,value,4)
    icon=(ASSETS/'ps2_common_icon.pal').read_bytes()
    p.memory[0x1236740:0x1236740+len(icon)]=icon
    p.run(0x116588,limit=500000)
    p.run(0x1cebb0,[52])
    p.write(0x582b3c,5,4)
    return p

def atlas(p):
    raw=np.frombuffer((ASSETS/'obj0_16.tex').read_bytes(),np.uint8)
    # The resource attached to slot 1 appends its CLUT in one 16x16 upload.
    clut=raw[-1024:].reshape(8,4,8,4)[:,[0,2,1,3],:,:].reshape(256,4)
    labels=clut[raw[:512*512]].reshape(512,512,4)
    # 109630 uploads the icon CLUT in 8x2 strips so its indices are linear.
    icons=np.frombuffer((ASSETS/'ps2_common_icon.tex').read_bytes(),np.uint8)
    palette=np.frombuffer(p.memory,np.uint8,1024,0x1236f40).reshape(256,4)
    assert palette[:,3].max()>0
    return {(0x1a40,0x3119):labels,(0x318d,0x3111):palette[icons].reshape(512,512,4)}

def capture(p,fn,args):
    for a in (0x345178,0x345180,0x378e08,0x3db8f8):p.write(a,0,4)
    p.run(0x114e80)  # The scheduler resets both per-frame depth counters.
    p.run(fn,args,limit=1200000)
    return decode(p)

def decode(p):
    count=p.read(0x345178,4)
    result=[]
    for i in range(count):
        a=PACKETS+i*128
        prim,color,tex,u0,xy0,u1,xy1=struct.unpack_from('<7Q',p.memory,a)
        if prim==0x1ff3:
            verts=[p.read(a+16+j*16,8) for j in range(4)]
            xy=lambda q:(((q&65535)-0x6c00)//16,(((q>>16)&65535)-0x7900)//8)
            x,y=xy(verts[0]);r,b=xy(verts[3]);z=verts[0]>>32
            result.append((z,(x,y,r,b),color&0xffffffff,None))
        elif prim==0x1ff2:
            verts=[struct.unpack_from('<5fI',p.memory,u0+24*j) for j in range(4)]
            assert xy0==4
            x,y,z,ul,vt,_=verts[0];r,b,_,ur,vb,_=verts[3]
            assert all(value==int(value) for value in (x,y,r,b,ul,vt,ur,vb))
            assert (r-x,b-y)==(ur-ul,vb-vt)
            result.append((int(z),tuple(map(int,(x,y,r,b))),color&0xffffffff,
                          (tex&16383,(tex>>37)&16383,*map(int,(ul,vt)))))
        elif prim==0x1ff1:
            # Font sprites use the font cache's 1/2 texel UV bias. Match its
            # logical pixel origin separately from the half-height flat quads.
            xy=lambda q:(((q&65535)-p.read(0x32ce14,4))//16,(((q>>16)&65535)-p.read(0x32ce18,4))//16)
            x,y=xy(xy0);r,b=xy(xy1);z=(xy0>>32)&0x7fffffff
            assert (tex>>37)&16383==0x3080 and u1-u0==16*(r-x)+16*(b-y)*65536
            result.append((z,(x,y,r,b),color&0xffffffff,('glyph',(u0&65535)//16,(u0>>16&65535)//16)))
        else:raise ValueError(hex(prim))
    return sorted(result,key=lambda command:command[0])

def pixels(p,atlases,q):
    _,(x,y,r,b),color,src=q
    if src is None:return None
    if src[0]=='glyph':
        _,u,v=src
        packed=np.frombuffer(p.memory,np.uint8,512*256,GLYPH).reshape(512,256)
        xs=np.arange(u,u+r-x)
        indices=(packed[v:v+b-y,xs//2]>>(4*(xs%2)))&15
        rgba=np.frombuffer(p.memory,np.uint8,64,0x348a48).reshape(16,4)[indices]
    else:
        base,bank,u,v=src
        rgba=atlases[base,bank][v:v+b-y,u:u+r-x]
    # Source RGB modulation is invariant within a menu display list. Fade
    # alpha varies by frame, so keep the intrinsic texel alpha independent.
    mod=np.array([(color>>(c*8))&255 for c in range(3)],int)
    out=rgba.copy();out[:,:,:3]=np.minimum(255,rgba[:,:,:3].astype(int)*mod//128)
    return out

def extract():
    p=prepare();atlases=atlas(p);sprites={};lists=[]
    def group(fn,args):
        group=[]
        for q in capture(p,fn,args):
            if q[3] is None:continue
            assert q[2]>>24==128
            img=pixels(p,atlases,q);x,y,r,b=q[1]
            key=(r-x,b-y,img.tobytes())
            group.append((sprites.setdefault(key,len(sprites)),x,y))
        lists.append(group)
    for i in range(3):
        group(0x1db630,[i,255]);group(0x1db708,[i,255])
    group(0x1db980,[192])
    for kind in (1,0):
        for choice in (0,1):group(0x1cf598,[choice,kind])
    assert len(lists)==11
    # Four successive border calls advance a single triangular color cycle.
    # Preserve the actual rounded shade of each edge at every phase.
    p.write(0x582fd0,0,4);p.write(0x582fd4,0,4)
    shades=[]
    for frame in range(60):
        edges=[q for q in capture(p,0x1db850,[192]) if ((q[2]>>16)&255)==0]
        assert len(edges)==4
        shades.extend((q[2]>>8)&255 for q in edges)
    assert p.read(0x582fd0,4)==0 and p.read(0x582fd4,4)==0
    data=bytearray(struct.pack('<4sHH',b'CVM1',len(sprites),len(lists))+bytes(shades))
    for w,h,rgba in sprites:
        data.extend(struct.pack('<HH',w,h));data.extend(rgba)
    for group in lists:
        data.extend(struct.pack('<H',len(group)))
        for ref in group:data.extend(struct.pack('<Hhh',*ref))
    return data
if __name__=='__main__':
    data=extract();OUT.write_bytes(data);print(OUT,len(data))
