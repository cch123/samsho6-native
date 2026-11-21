#!/usr/bin/env python3
"""Compare the shared menu drawing layer with the original submitters, emitters and chrome.

Every case runs the ORIGINAL routine in Probe, decodes the 128-byte submission queue
68c3c0, and requires (a) the same ordered primitive list from src/menu_canvas.cpp and
(b) the same 640x480 frame when the original packets are painted by the reference
painter below and the native list by MenuCanvas::rasterise.
"""
import argparse
import hashlib
import json
import math
import random
import struct
import subprocess
import tempfile
from fractions import Fraction
from pathlib import Path

import numpy as np
from character_tiles_oracle import ROOT,ASSETS
from extract_console_versus_art import prepare,PACKETS,GLYPH,ORIGINAL
from extract_versus_quotes import ISO_PATH,Iso
import extract_menu_canvas

REPORT=ROOT/'outputs/ss6-feasibility/menu_canvas_validation.json'
STUB=struct.pack('<II',0x03e00008,0x0000102d)
SCRATCH=0x1f00000
DRIVER=r'''
#include "menu_canvas.hpp"
#include <bit>
#include <cstdio>
#include <iostream>
#include <sstream>
using namespace ss6;
static std::string unhex(const std::string& s){std::string o;for(size_t i=0;i+1<s.size();i+=2)o.push_back(char(std::stoi(s.substr(i,2),nullptr,16)));return o;}
static float fb(uint32_t v){return std::bit_cast<float>(v);}
template<class T> static void put(const T& v){std::cout.write(reinterpret_cast<const char*>(&v),sizeof v);}
int main(int argc,char** argv){
 if(argc!=2)return 2;
 MenuCanvas canvas(argv[1]);MenuDrawList list;MenuChrome chrome;MenuBackdrop backdrop;GameRandom rng;
 std::vector<uint8_t> pixels(640*480*4),base(pixels.size());
 for(int y=0;y<480;++y)for(int x=0;x<640;++x){auto* p=base.data()+4*(640*y+x);p[0]=x+3*y;p[1]=x^y;p[2]=4*x+y;p[3]=255;}
 std::string line;
 while(std::getline(std::cin,line)){
  std::istringstream in(line);std::string op;in>>op;
  auto u=[&]{uint32_t v;in>>v;return v;};auto i=[&]{int v;in>>v;return v;};auto f=[&]{return fb(u());};
  auto s=[&]{std::string v;in>>v;return v=="-"?std::string():unhex(v);};
  if(op=="fade"){int en=i(),level=i();canvas.setFade(en,level,u());}
  else if(op=="bright")canvas.setBrightness(i());
  else if(op=="begin"){list.beginFrame();list.colour=u();list.blend=i();list.additive=false;list.textDepth=i();list.asciiDepth=f();list.cursor=f();list.cursorBase=f();}
  else if(op=="rect"){int x=i(),y=i(),w=i(),h=i();uint32_t c=u();canvas.rectangle(list,x,y,w,h,c,f());}
  else if(op=="sprite"){int slot=i();float a[9];for(auto& v:a)v=f();canvas.sprite(list,slot,a[0],a[1],a[2],a[3],a[4],a[5],a[6],a[7],a[8]);}
  else if(op=="desc"){MenuSheetRect r{i(),i(),i(),i()};int slot=i();unsigned flags=u();uint32_t c=u();int m=i();float a[5];for(auto& v:a)v=f();canvas.sprite(list,r,slot,flags,c,m,a[0],a[1],a[2],a[3],a[4]);}
  else if(op=="pic"){MenuSheetRect r{i(),i(),i(),i()};int slot=i();unsigned flags=u();uint32_t c=u();float a[3];for(auto& v:a)v=f();canvas.picture(list,r,slot,flags,c,a[0],a[1],a[2]);}
  else if(op=="ascii"){auto t=s();int x=i(),y=i();canvas.ascii(list,t,x,y,u());}
  else if(op=="t20"||op=="t24"){auto t=s();int a[6];for(auto& v:a)v=i();(op=="t20"?canvas.text20(list,t,a[0],a[1],a[2],a[3],a[4],a[5]):canvas.text24(list,t,a[0],a[1],a[2],a[3],a[4],a[5]));}
  else if(op=="marker"){auto t=s();int x=i(),y=i();canvas.marker(list,t,x,y,i());}
  else if(op=="dialog"){int c=i(),k=i();canvas.dialog(list,c,k,i());}
  else if(op=="chrome"){chrome.band=i();chrome.content=i();chrome.legend=i();chrome.variant=i();}
  else if(op=="helpstate"){chrome.helpX[0]=i();chrome.helpX[1]=i();chrome.helpDelay=i();}
  else if(op=="sethelp")chrome.setHelp(i());
  else if(op=="helptick"){int scroll=i(),length=i();chrome.helpPosition(scroll,length,0);if(scroll)chrome.helpPosition(true,length,1);}
  else if(op=="help"){auto t=s();int scroll=i();canvas.helpText(list,chrome,t,scroll,i());}
  else if(op=="frame"){int show=i(),page=i(),pages=i(),legend=i();canvas.frame(list,chrome,show,page,pages,legend);chrome.advance();}
  else if(op=="legend"){int kind=i(),x=i(),y=i();if(kind==0)canvas.legend(list,chrome,x,y);else if(kind==1)canvas.legendConfirm(list,chrome,x,y);else canvas.legendCancel(list,chrome,x,y);}
  else if(op=="page"){int x=i(),y=i(),page=i();canvas.pageIndicator(list,chrome,x,y,page,i());}
  else if(op=="banner"){int index=i();canvas.banner(list,canvas.banners()[index],i());}
  else if(op=="seed"){uint64_t lo=u();rng.librarySeed=lo|uint64_t(u())<<32;}
  else if(op=="enter"){chrome.enter(backdrop.enter(rng));}
  else if(op=="bg")canvas.background(list,backdrop,rng,chrome,i());
  else if(op=="bgpic")canvas.backgroundPicture(list,i());
  else if(op=="dump"){for(auto& sp:backdrop.sprites)put(sp);put(backdrop.previous);put(backdrop.next);std::cout.flush();}
  else if(op=="flush"){
   int paint=i();
   uint32_t n=uint32_t(list.records.size());put(n);
   for(auto& r:list.records){uint8_t head[6]={uint8_t(r.kind),uint8_t(r.font),r.slot,r.blend,uint8_t(r.additive),0};put(head);put(r.glyph);put(r.colour);put(r.z);
    float g[8]={r.x,r.y,r.w,r.h,r.u,r.v,r.uw,r.vh};put(g);put(r.corner);}
   uint32_t st[17]={list.colour,uint32_t(list.blend),uint32_t(list.depth),uint32_t(list.glyphs),uint32_t(list.textDepth),std::bit_cast<uint32_t>(list.cursor),
    uint32_t(chrome.helpX[0]),uint32_t(chrome.helpX[1]),uint32_t(chrome.helpDelay),uint32_t(rng.librarySeed),uint32_t(rng.librarySeed>>32),
    uint32_t(backdrop.target),uint32_t(backdrop.shown),uint32_t(backdrop.clock),uint32_t(chrome.band),uint32_t(chrome.content),uint32_t(chrome.legend)};put(st);
   if(paint){pixels=base;canvas.rasterise(list,pixels);std::cout.write(reinterpret_cast<const char*>(pixels.data()),pixels.size());}
   std::cout.flush();
  }
  else return 3;
 }
}
'''

def bits(value):return struct.unpack('<I',struct.pack('<f',value))[0]
def real(word):return struct.unpack('<f',struct.pack('<I',word&0xffffffff))[0]


class Oracle:
    """The original routines plus the decoded queue of one frame."""
    def __init__(self):
        p=self.p=prepare()
        iso=Iso(ISO_PATH)
        self.half=np.frombuffer(iso.read('/BIN/GOTH_H.BIN'),np.uint8).reshape(256,128)
        self.fonts={20:iso.read('/BIN/GOTH_20.BIN'),24:iso.read('/BIN/GOTH_24.BIN')}
        raw=(ASSETS/'PS2_menu_bg00_00.tex').read_bytes();addr=0x1e40000
        p.memory[addr:addr+len(raw)]=raw
        for o,v in [(0,addr),(4,1024),(8,1024),(12,19),(20,10),(24,10),(36,0)]:p.write(0x3a9680+4*40+o,v,4)
        # Disc access only: 1142d8 (texture by name) and 1163c0 (palette file).
        # The palette is then supplied exactly as 1ce478 uploads it: first
        # colour cleared, 116478(0x200, 0x100), bank 0x20 for slot 4.
        p.memory[0x1142d8:0x1142d8+8]=STUB;p.memory[0x1163c0:0x1163c0+8]=STUB
        self.palette()
        self.fade=(0,0,0);self.refresh()
        self.slots={};self.instructions=0
        for slot in (1,4,0x2e):
            self.reset();self.sprite(slot,0,0,0,8,8,0,0,8,8)
            tex=self.p.read(PACKETS+16,8);self.slots[tex&0x3fff,(tex>>37)&0x3fff]=slot
        assert len(self.slots)==3
        self.instructions=0;self.packets=0

    def palette(self):
        p=self.p;pal=(ASSETS/'PS2_menu_bg00_00.pal').read_bytes();addr=0x1410000
        p.memory[addr:addr+512]=pal;p.write(addr,0,2);p.write(0x439b68,0,4)
        p.run(0x116478,[0x200,0x100,addr],limit=150000);p.run(0x10add8,[4,0x20])

    def refresh(self):
        p=self.p;enabled,level,colour=self.fade
        for a,v in [(0x3ebf18,2 if enabled else 0),(0x3ec734,level),(0x3ec730,colour),(0x3ebf2c,1),(0x3ebf24,0)]:p.write(a,v,4)
        p.run(0x116588,limit=900000)
        font=(ASSETS/'obj0_16.tex').read_bytes()
        clut=np.frombuffer(font,np.uint8,1024,512*512).reshape(8,4,8,4)[:,[0,2,1,3]].reshape(256,4)
        self.tex={1:clut[np.frombuffer(font,np.uint8,512*512)].reshape(512,512,4),
                  4:np.frombuffer(p.memory,np.uint8,1024,0x11e7980+4*0x200).reshape(256,4)[
                      np.frombuffer(p.memory,np.uint8,1024*1024,p.read(0x3a9680+4*40,4))].reshape(1024,1024,4),
                  0x2e:np.frombuffer(p.memory,np.uint8,1024,0x1236f40).reshape(256,4)[
                      np.frombuffer((ASSETS/'ps2_common_icon.tex').read_bytes(),np.uint8)].reshape(512,512,4)}

    def reset(self,colour=0xffffffff,blend=1,text=0,ascii_depth=0.0,cursor=0.0,base=0.0):
        p=self.p
        for a in (0x345178,0x345180,0x378e08,0x3db8f8,0x348b10):p.write(a,0,4)
        p.run(0x114e80)
        for a,v in [(0x3db900,colour),(0x3db8fc,blend),(0x348a8c,text),(0x3d3aac,bits(ascii_depth)),
                    (0x12d3850,bits(cursor)),(0x4ee54c,bits(base))]:p.write(a,v,4)

    def call(self,fn,ints=(),floats=(),stack=(),limit=3000000):
        p=self.p
        for i,v in enumerate(floats):p.floats[12+i]=bits(v)
        for i,v in enumerate(stack):p.write(0x1fff000+8*i,v,4)
        result,n=p.run(fn,[v&0xffffffffffffffff for v in ints],limit=limit);self.instructions+=n
        return result

    def sprite(self,slot,x,y,z,w,h,u,v,uw,vh):
        self.call(0x113f98,[slot],[x,y,z,w,h,u,v,uw],[bits(vh)])

    def string(self,data,slot=0):
        at=SCRATCH+slot*0x400;self.p.memory[at:at+len(data)+1]=data+b'\0';return at

    def decode(self):
        """Queue entries in submission order as comparable tuples plus painter data."""
        p=self.p;out=[]
        count=p.read(0x345178,4);self.packets+=count
        for i in range(count):
            a=PACKETS+i*128
            q=struct.unpack_from('<16Q',p.memory,a);tag=q[0];kind=tag&0xfff
            assert tag>>12 in (1,2),hex(tag)
            if kind==0xff3:
                n=q[15];assert n in (3,4)
                pts=[];colours=set();depths=set()
                for j in range(n):
                    colour,xyz=q[1+2*j]&0xffffffff,q[2+2*j]
                    pts.append((((xyz&65535)-0x6c00)//16,(((xyz>>16)&65535)-0x7900)//8));colours.add(colour);depths.add(xyz>>32)
                    assert ((xyz&65535)-0x6c00)%16==0 and (((xyz>>16)&65535)-0x7900)%8==0
                assert len(colours)==len(depths)==1 and tag>>12==1
                colour=colours.pop();z=float(depths.pop())
                if n==4:
                    (x,y),(x1,y1)=pts[0],pts[3]
                    assert set(pts)=={(x,y),(x,y1),(x1,y),(x1,y1)}
                    out.append(dict(kind='flat',key=('flat',colour,bits(z),x,y,x1-x,y1-y),z=z,colour=colour,rect=(x,y,x1,y1)))
                else:
                    out.append(dict(kind='tri',key=('tri',colour,bits(z),*sum(pts,())),z=z,colour=colour,pts=pts))
            elif kind==0xff2:
                assert q[4]==4
                v=[struct.unpack_from('<5fI',p.memory,q[3]+24*j) for j in range(4)]
                colour=q[1]&0xffffffff
                assert len({w[5] for w in v})==1 and len({w[2] for w in v})==1,(hex(colour),[hex(w[5]) for w in v],hex(tag))
                slot=self.slots[q[2]&0x3fff,(q[2]>>37)&0x3fff];raw=tag>>12==2
                out.append(dict(kind='quad',key=('quad',slot,raw,colour,bits(v[0][2]),*[bits(c) for w in v for c in (w[0],w[1],w[3],w[4])]),
                                z=v[0][2],colour=colour,slot=slot,raw=raw,verts=v))
            elif kind==0xff1:
                assert tag>>12==1
                tex,uv0,xy0,uv1,xy1=q[2:7]
                xy=lambda w:(((w&65535)-0x6c00)//16,(((w>>16)&65535)-0x7900)//16)
                x,y=xy(xy0);r,b=xy(xy1);z=(xy0>>32)&0x7fffffff;u,v=((uv0&65535)-8)//16,((uv0>>16&65535)-8)//16
                assert uv1-uv0==16*(r-x)+16*(b-y)*65536 and (xy1>>32)&0x7fffffff==z and (tex>>37)&16383==0x3080
                base=tex&16383;w,h=r-x,b-y
                if base==0x3000:
                    font='half';cols=np.arange(u,u+w)
                    cell=(self.half[v:v+h,cols//2]>>(4*(cols%2)))&15
                else:
                    assert base==0x1a40 and w==h and w in (20,24) and u%24==0 and v%24==0
                    font=w;page=np.frombuffer(p.memory,np.uint8,512*256,GLYPH).reshape(512,256)
                    cols=np.arange(u,u+w);cell=(page[v:v+h,cols//2]>>(4*(cols%2)))&15
                out.append(dict(kind='glyph',key=('glyph',font,q[1]&0xffffffff,bits(float(z)),x,y,w,h,u,v,cell.tobytes()),
                                z=float(z),colour=q[1]&0xffffffff,rect=(x,y,r,b),cell=cell.copy()))
            else:raise AssertionError(hex(tag))
        return out


def native_keys(blob,oracle):
    keys=[]
    for kind,font,slot,blend,raw,_,glyph,colour,z,*g in struct.iter_unpack('<6BHIf16f',blob):
        x,y,w,h,u,v,uw,vh=g[:8];c=g[8:]
        if kind==0:keys.append(('flat',colour,bits(z),int(x),int(y),int(w),int(h)))
        elif kind==1:keys.append(('tri',colour,bits(z),*map(int,c[:6])))
        elif kind==2:
            corners=[(x,y,u,v),(x,y+h,u,v+vh),(x+w,y,u+uw,v),(x+w,y+h,u+uw,v+vh)]
            keys.append(('quad',slot,bool(raw),colour,bits(z),*[bits(np.float32(t)) for q in corners for t in q]))
        elif kind==3:
            uvs=[(u,v),(u,v+vh),(u+uw,v),(u+uw,v+vh)]
            keys.append(('quad',slot,bool(raw),colour,bits(z),*[bits(np.float32(t)) for i in range(4) for t in (c[2*i],c[2*i+1],*uvs[i])]))
        else:
            if font==1:
                cols=np.arange(int(u),int(u+w));cell=(oracle.half[int(v):int(v+h),cols//2]>>(4*(cols%2)))&15;name='half'
            else:
                size=20 if font==2 else 24
                step=220 if size==20 else 312;head=10 if size==20 else 12;pitch=size//2
                rows=np.frombuffer(oracle.fonts[size],np.uint8,pitch*size,glyph*step+head).reshape(size,pitch)
                cols=np.arange(size);cell=(rows[:,cols//2]>>(4*(cols%2)))&15;name=size
            keys.append(('glyph',name,colour,bits(z),int(x),int(y),int(w),int(h),int(u),int(v),cell.tobytes()))
    return keys


def blend(dst,src,alpha):
    dst[:]=np.clip(dst+((src-dst)*alpha)//128,0,255)

def paint(oracle,prims,frame):
    """Reference painter: ascending queue depth, submission order within a depth."""
    clut=np.frombuffer(oracle.p.memory,np.uint8,64,0x348a48).reshape(16,4).astype(np.int32)
    for q in sorted(prims,key=lambda item:item['z']):
        colour=q['colour'];mod=np.array([(colour>>k)&255 for k in (0,8,16,24)],np.int32)
        def textured(view,texels):
            source=np.minimum(255,texels.astype(np.int32)*mod//128)
            # Tag 2ff2 selects the GS ALPHA preset 348bc0 = 8000000029: Cd + Cs.
            if q.get('raw'):view[:]=np.minimum(255,view+source[...,:3])
            else:blend(view,source[...,:3],source[...,3:])
        if q['kind']=='flat':
            x,y,r,b=q['rect'];x,y,r,b=max(x,0),max(y,0),min(r,640),min(b,480)
            if r>x and b>y:
                view=frame[y:b,x:r,:3];blend(view,mod[:3],mod[3])
        elif q['kind']=='tri':
            pts=q['pts'];ys=[pt[1] for pt in pts]
            for y in range(max(0,min(ys)),min(480,max(ys))):
                xs=[]
                for (x0,y0),(x1,y1) in zip(pts,pts[1:]+pts[:1]):
                    if y0!=y1 and min(y0,y1)<=y<=max(y0,y1):xs.append(Fraction(x0)+Fraction((y-y0)*(x1-x0),y1-y0))
                if not xs:continue
                left,right=max(0,math.ceil(min(xs))),min(640,math.ceil(max(xs)))
                if right>left:
                    view=frame[y,left:right,:3];blend(view,mod[:3],mod[3])
        elif q['kind']=='glyph':
            x,y,r,b=q['rect'];cell=clut[q['cell']]
            cx,cy,cr,cb=max(x,0),max(y,0),min(r,640),min(b,480)
            if cr>cx and cb>cy:textured(frame[cy:cb,cx:cr,:3],cell[cy-y:cb-y,cx-x:cr-x])
        else:
            tex=oracle.tex[q['slot']];v=q['verts']
            (x0,y0,_,u0,v0,_),(xa,ya,_,ua,va,_),(xb,yb,_,ub,vb,_),(x3,y3,_,u3,v3,_)=v
            values=[c for w in v for c in (w[0],w[1],w[3],w[4])]
            aligned=x0==xa and y0==yb and (x3,y3)==(xb,ya) and u0==ua and v0==vb and all(c==int(c) for c in values)
            if aligned:
                x0,y0,x1,y1,u0,v0,u1,v1=map(int,(x0,y0,xb,ya,u0,v0,ub,va))
                if x0==x1 or y0==y1:continue
                px=np.arange(max(0,min(x0,x1)),min(640,max(x0,x1)));py=np.arange(max(0,min(y0,y1)),min(480,max(y0,y1)))
                if not len(px) or not len(py):continue
                # Texel under each pixel centre.
                us=u0+((2*px+1-2*x0)*(u1-u0))//(2*(x1-x0));vs=v0+((2*py+1-2*y0)*(v1-v0))//(2*(y1-y0))
                textured(frame[py[0]:py[-1]+1,px[0]:px[-1]+1,:3],tex[vs[:,None],us[None,:]])
            else:
                xs=[w[0] for w in v];ys=[w[1] for w in v]
                left,right=max(0,math.floor(min(xs))),min(639,math.ceil(max(xs)))
                top,bottom=max(0,math.floor(min(ys))),min(479,math.ceil(max(ys)))
                if right<left or bottom<top:continue
                ax,ay,bx,by=np.float64(xb)-x0,np.float64(yb)-y0,np.float64(xa)-x0,np.float64(ya)-y0
                det=ax*by-ay*bx
                if det==0:continue
                gy,gx=np.mgrid[top:bottom+1,left:right+1]
                dx=gx+0.5-np.float64(x0);dy=gy+0.5-np.float64(y0)
                s=(dx*by-dy*bx)/det;t=(ax*dy-ay*dx)/det
                inside=(s>=0)&(s<1)&(t>=0)&(t<1)
                tu=np.floor(np.float64(u0)+s*(np.float64(ub)-np.float64(u0))).astype(int)
                tv=np.floor(np.float64(v0)+t*(np.float64(va)-np.float64(v0))).astype(int)
                inside&=(tu>=0)&(tv>=0)&(tu<tex.shape[1])&(tv<tex.shape[0])
                if not inside.any():continue
                view=frame[top:bottom+1,left:right+1,:3];pixels=view[inside]
                textured(pixels,tex[tv[inside],tu[inside]]);view[inside]=pixels
    return frame


class Session:
    def __init__(self,proc,oracle):
        self.proc=proc;self.o=oracle;self.lines=[]
        y,x=np.mgrid[:480,:640];self.base=np.stack((x+3*y,x^y,4*x+y,np.full_like(x,255)),axis=-1).astype(np.uint8)
        self.frames=self.primitives=self.cases=0;self.kinds={}
    def send(self,*parts):self.lines.append(' '.join(str(int(v)) if isinstance(v,(bool,np.integer)) else str(v) for v in parts))
    def read(self,n):
        data=self.proc.stdout.read(n)
        if len(data)!=n:raise RuntimeError('Native driver stopped')
        return data
    def fade(self,enabled,level,colour):
        self.o.fade=(enabled,level,colour);self.o.refresh();self.send('fade',int(enabled),level,colour)
    def bright(self,value):
        self.o.p.write(0x43d064,value,4);self.send('bright',value)
    def begin(self,colour=0xffffffff,blend=1,text=0,ascii_depth=0.0,cursor=0.0,base=0.0):
        self.o.reset(colour,blend,text,ascii_depth,cursor,base)
        self.send('begin',colour,blend,text,bits(ascii_depth),bits(cursor),bits(base))
    def flush(self,label,paint_frame=True):
        o=self.o;p=o.p;prims=o.decode()
        self.send('flush',int(paint_frame));self.proc.stdin.write(('\n'.join(self.lines)+'\n').encode());self.proc.stdin.flush();self.lines=[]
        count=struct.unpack('<I',self.read(4))[0];blob=self.read(count*80);state=struct.unpack('<17I',self.read(68))
        native=native_keys(blob,o);expected=[q['key'] for q in prims]
        if native!=expected:
            for i,(a,b) in enumerate(zip(native,expected)):
                if a!=b:raise AssertionError((label,'primitive',i,a[:-1] if a[0]=='glyph' else a,b[:-1] if b[0]=='glyph' else b))
            raise AssertionError((label,'primitive count',len(native),len(expected)))
        reent=p.read(0x5d1bf8,4)
        original=(p.read(0x3db900,4),p.read(0x3db8fc,4),p.read(0x3db8f4,4),p.read(0x345180,4),p.read(0x348a8c,4),p.read(0x12d3850,4),
                  p.read(0x582b28,4),p.read(0x582b2c,4),p.read(0x582b30,4),p.read(reent+0xa8,4),p.read(reent+0xac,4),
                  p.read(0x584d60,4),p.read(0x584d64,4),p.read(0x584d68,4),p.read(0x582b34,4),p.read(0x582b38,4),p.read(0x582b3c,4))
        if state!=original:raise AssertionError((label,'state',state,original))
        for q in prims:self.kinds[q['kind']]=self.kinds.get(q['kind'],0)+1
        self.primitives+=len(prims);self.cases+=1
        if paint_frame:
            expected_frame=paint(o,prims,self.base.astype(np.int32)).astype(np.uint8)
            got=np.frombuffer(self.read(self.base.size),np.uint8).reshape(self.base.shape)
            if not np.array_equal(got,expected_frame):
                bad=np.any(got!=expected_frame,axis=-1);y,x=map(int,np.argwhere(bad)[0])
                raise AssertionError((label,'pixels',int(bad.sum()),x,y,got[y,x].tolist(),expected_frame[y,x].tolist()))
            self.frames+=1
        return prims
    def chrome(self,band,content,legend,variant=1,override=0):
        for a,v in [(0x582b34,band),(0x582b38,content),(0x582b3c,legend),(0x582b44,variant),(0x582b40,override)]:self.o.p.write(a,v,4)
        self.send('chrome',band,content,legend,variant)
    def seed(self,value):
        p=self.o.p;reent=p.read(0x5d1bf8,4);p.write(reent+0xa8,value,8);self.send('seed',value&0xffffffff,value>>32)
    def helpstate(self,x0,x1,delay):
        for a,v in [(0x582b28,x0),(0x582b2c,x1),(0x582b30,delay)]:self.o.p.write(a,v,4)
        self.send('helpstate',x0,x1,delay)


def help_tables(p):
    out=[]
    for table,count in ((0x582c40,5),(0x582d10,15),(0x582df8,4),(0x583000,6)):
        for i in range(count):
            ptr,scroll=p.read(table+8*i,4),p.read(table+8*i+4,4)
            end=p.memory.index(0,ptr);text=bytes(p.memory[ptr:end]);text.decode('cp932')
            assert scroll in (0,1);out.append((ptr,text,scroll))
    return out


def run(session,quick=False):
    o=session.o;p=o.p;rng=random.Random(20261121);counts={}
    import sys,time
    clock=[time.time()]
    def group(name,start):
        counts[name]=session.cases-start
        print(f'{name}: {counts[name]} cases, {time.time()-clock[0]:.1f}s',file=sys.stderr,flush=True);clock[0]=time.time()
    fades=[(False,0,0),(True,0,0xff000000),(True,100,0xffffffff),(True,175,0xff000000),(True,256,0xff000000),(True,75,0xff204080)]
    helps=help_tables(p)
    session.chrome(0,0,0);session.helpstate(0x10,0,0);session.seed(1)

    # 1145c0 flat rectangle.
    start=session.cases
    for index in range(16 if quick else 72):
        if index%12==0:
            session.fade(*fades[(index//12)%len(fades)]);session.bright((0x100,0x38,0xc0)[(index//12)%3])
        session.begin()
        for _ in range(6):
            x,y,w,h=rng.randint(-700,700),rng.randint(-500,500),rng.randint(0,700),rng.randint(0,500)
            colour=rng.getrandbits(32) if rng.random()<.8 else rng.choice((0xff000000,0xc0000000,0x80ffffff,0))
            z=float(rng.randint(-400,60))
            o.call(0x1145c0,[x,y,w,h,colour],[z]);session.send('rect',x,y,w,h,colour,bits(z))
        session.flush(('rectangle',index))
    group('rectangle_1145c0',start)

    # 113f98 direct, 117de8 and 117a00 over the three sheet slots.
    start=session.cases
    sizes={1:512,4:1024,0x2e:512}
    for index in range(12 if quick else 60):
        if index%10==0:
            session.fade(*fades[(index//10)%len(fades)]);session.bright((0x100,0x80,0x38)[(index//10)%3])
        session.begin(colour=rng.getrandbits(32),blend=rng.choice((0,1,1)))
        for n in range(5):
            slot=rng.choice((1,4,0x2e));size=sizes[slot]
            w,h=rng.randint(1,200),rng.randint(1,160);u,v=rng.randint(0,size-w-1),rng.randint(0,size-h-1)
            x,y,z=float(rng.randint(-150,700)),float(rng.randint(-120,520)),float(rng.randint(-380,40))
            mode=rng.randrange(3)
            if mode==0:
                o.sprite(slot,x,y,z,float(w),float(h),float(u),float(v),float(w),float(h))
                session.send('sprite',slot,*map(bits,(x,y,z,w,h,u,v,w,h)))
                continue
            desc=SCRATCH+0x2000+n*32
            for k,value in enumerate((u,v,w,h,0,slot)):p.write(desc+4*k,value,4)
            flags=(0x20 if slot==4 else 0)|rng.choice((0,0,0,0x200,0x100))
            colour=rng.choice((0,rng.getrandbits(32),0xffffffff,0x80ffffff))
            if mode==1:
                mirror=rng.randrange(2);sw,sh=(w,h) if rng.random()<.5 else (rng.randint(1,260),rng.randint(1,200))
                o.call(0x117de8,[desc,flags,colour,mirror],[x,y,z,float(sw),float(sh)])
                session.send('desc',u,v,w,h,slot,flags,colour,mirror,*map(bits,(x,y,z,sw,sh)))
            else:
                flags&=~0x300
                o.call(0x117a00,[desc,flags,colour],[x,y,z]);session.send('pic',u,v,w,h,slot,flags,colour,*map(bits,(x,y,z)))
        o.palette()
        session.flush(('sprite',index))
    group('sprite_113f98_117de8_117a00',start)

    # 1135e8 ASCII strings: the nine mode names of the ELF and synthetic lines.
    start=session.cases
    names=[];at=0x656860
    while at<0x656920:
        end=p.memory.index(0,at);text=bytes(p.memory[at:end])
        if text.endswith(b' MODE') and all(0x20<=c<0x7f for c in text):names.append(text)
        at=end+1
    assert b'ARCADE MODE' in names and len(names)>=5,names
    lines=names+[b'0123456789:;<=>?@[\\]^_`{|}~',b'LINE ONE\nline two\n  !"#$%&\'()*+,-./',bytes(range(0x20,0x7f)),b'A\x82\xa0B\x01C']
    for index,text in enumerate(lines):
        session.fade(*fades[index%len(fades)]);session.bright((0x100,0x60)[index%2])
        depth=float(rng.randint(-300,0));session.begin(ascii_depth=depth)
        x,y,colour=rng.randint(-20,420),rng.randint(-10,440),rng.choice((0x80ffffff,0xffffffff,rng.getrandbits(32)))
        o.call(0x1135e8,[o.string(text),x,y,colour]);session.send('ascii',text.hex(),x,y,colour)
        session.flush(('ascii',index))
    group('ascii_1135e8',start)

    # 10a460 / 109f08: every help text of the option pages, mixed widths.
    start=session.cases
    mixed=[b'Page 12/34 (OK) [x]',b'\x83\x76\x83\x8c\x83\x43 1P\x81\x5e2P 100%\n\x89\xfc\x8d\x73 ABC',bytes(range(0x21,0x7f)),
           '設定を初期値に戻します。'.encode('cp932'),'ａＢ１２　'.encode('cp932')]
    texts=[t for _,t,_ in helps]+mixed
    for index,text in enumerate(texts[:8] if quick else texts):
        if index%6==0:
            session.fade(*fades[(index//6)%len(fades)]);session.bright((0x100,0x38,0xa0)[(index//6)%3])
        for large in (0,1):
            session.begin(text=rng.randint(10000000,10040000))
            x,y=rng.randint(-60,300),rng.randint(-10,440)
            r,g,b,a=(255,255,255,255) if index%3==0 else [rng.randint(0,255) for _ in range(4)]
            o.call(0x109f08 if large else 0x10a460,[o.string(text),x,y,r,g,b,a])
            session.send('t24' if large else 't20',text.hex(),x,y,r,g,b,a)
            session.flush(('text',index,large))
    group('text_10a460_109f08',start)

    # 1cf8f8 edit highlight and 1cf598 dialog.
    start=session.cases
    session.fade(False,0,0);session.bright(0x100)
    for index in range(24 if quick else 96):
        if index%24==0:session.fade(*fades[(index//24)%len(fades)])
        text=texts[index%len(texts)][:rng.randint(0,12)]
        cursor,base=rng.choice((0.0,0.5,3.0)),rng.choice((0.0,-20.0,35.0))
        session.begin(cursor=cursor,base=base)
        x,y,frame=rng.randint(0,560),rng.randint(0,440),index if index<64 else rng.randint(-200,5000)
        o.call(0x1cf8f8,[o.string(text),x,y,frame]);session.send('marker',text.hex() or '-',x,y,frame)
        session.flush(('marker',index))
    group('marker_1cf8f8',start)
    start=session.cases
    mode_saved=p.read(0x4c38a8,4)
    for index,(cursor,kind,mode) in enumerate((c,k,m) for m in (2,5) for k in (0,1) for c in (0,1)):
        session.fade(*fades[index%len(fades)]);session.bright((0x100,0x70)[index%2])
        p.write(0x4c38a8,mode,4);session.begin()
        o.call(0x1cf598,[cursor,kind]);session.send('dialog',cursor,kind,int(mode==5))
        session.flush(('dialog',index))
    p.write(0x4c38a8,mode_saved,4)
    group('dialog_1cf598',start)

    # Frame bands, legends and page indicator for every counter value.
    start=session.cases
    session.fade(False,0,0);session.bright(0x100)
    for band in range(16):
        for legend,(show,page,pages) in zip((0,3,5),((0,0,0),(1,rng.randint(0,8),9),(1,rng.randint(9,98),99))):
            content=rng.randint(0,15)
            for routine in (0x1ce660,0x1ce878):
                session.chrome(band,content,legend);session.begin()
                o.call(routine,[show,page,pages]);session.send('frame',show,page,pages,int(routine==0x1ce660))
                session.flush(('frame',band,legend,routine))
    for index in range(6 if quick else 36):
        session.fade(*fades[index%len(fades)]);session.bright((0x100,0x38,0xd0)[index%3])
        session.chrome(rng.randint(0,15),rng.randint(0,15),index%6);session.begin(colour=rng.getrandbits(32))
        x,y=rng.randint(-40,60),rng.randint(0,430)
        for kind,routine in enumerate((0x1ced08,0x1cee68,0x1cefc8)):
            o.call(routine,[x,y+kind*24]);session.send('legend',kind,x,y+kind*24)
        page,pages=rng.randint(0,120),rng.randint(1,120)
        o.call(0x1cf2a8,[x,y-30,page,pages]);session.send('page',x,y-30,page,pages)
        session.flush(('legend',index))
    group('chrome_frame_legend_page',start)

    # Title plate 1cfdb0 and the help line 1cff40 with its marquee.
    start=session.cases
    assert [real(p.read(a,4)) for a in (0x656d38,0x656d3c,0x656d40,0x656dac)]==[16.0,28.0,-350.0,-350.0]
    session.fade(False,0,0);session.bright(0x100)
    for alpha in range(0,256,17):
        session.begin(colour=rng.getrandbits(32));o.call(0x1cfdb0,[alpha]);session.send('banner',0,alpha)
        session.flush(('banner',alpha))
    saved=bytes(p.memory[0x582c40:0x582c48])
    for index,(ptr,text,scroll) in enumerate(helps[:7] if quick else helps):
        # Data fixture: row 0 of the option top table points at each help
        # record in turn; 1cff40 itself is unchanged.
        p.write(0x582c40,ptr,4);p.write(0x582c44,scroll,4)
        length=o.call(0x1ceb90,[ptr]);assert length==len(text)
        o.call(0x1cebb0,[length]);session.send('sethelp',length)
        # Drawn frames: the 60-visit pause, the wrap of each copy and a few
        # positions between. The visits in between run only the original
        # marquee step 1ceb10 exactly as 1cff40 calls it.
        wrap0,wrap1=60+8+5*length,60+10*length
        steps=[0,1,2] if not scroll else sorted({0,1,2,58,59,60,61,*range(wrap0-2,wrap0+3),*range(wrap1-2,wrap1+3),
                                                 wrap0//2,(wrap0+wrap1)//2,wrap1+wrap0//2})
        frame=0
        for target in steps:
            while frame<target:
                o.call(0x1ceb10,[scroll,length,0])
                if scroll:o.call(0x1ceb10,[1,length,1])
                session.send('helptick',scroll,length);frame+=1
            alpha=rng.randint(0,255);session.begin()
            o.call(0x1cff40,[0,alpha]);session.send('help',text.hex(),scroll,alpha)
            session.flush(('help',index,frame));frame+=1
    p.memory[0x582c40:0x582c48]=saved
    group('banner_help',start)

    # Background picture and the overlay: 1ce478 state, then 1ce570 per frame.
    start=session.cases
    session.fade(False,0,0);session.bright(0x100)
    session.begin();o.call(0x1ce628);session.send('bgpic',0);session.flush(('picture',))
    seeds=[1,0x1234567890abcdef,0x0badc0ffee123457,0x7fffffff00000001]
    plan=[(seeds[0],0,260 if quick else 620),(seeds[1],0,60 if quick else 420),(seeds[2],0,40 if quick else 300),
          (seeds[3],1,30 if quick else 200),(seeds[1]^0x55,2,30 if quick else 200)]
    variants=set();overlay_frames=0
    for case,(seed,override,frames) in enumerate(plan):
        session.seed(seed)
        o.call(0x1ce478);o.palette();session.send('enter')
        variant=p.read(0x582b44,4);variants.add(variant)
        if override:p.write(0x582b40,override,4)
        session.flush(('enter',case),paint_frame=False)
        def compare_state(positions=True):
            # 1e1620 leaves +0/+4 unwritten; every sprite receives them on the first 1e1a20 visit.
            first=0 if positions else 8
            session.send('dump');session.proc.stdin.write(('\n'.join(session.lines)+'\n').encode());session.proc.stdin.flush();session.lines=[]
            blob=session.read(200*60+204*8)
            address=lambda node:0 if node<0 else (0x1342f90,0x1342fd8,0x1343020,0x1343068)[node-200] if node>=200 else 0x133fa70+node*0x44
            prev=struct.unpack_from('<204i',blob,12000);nxt=struct.unpack_from('<204i',blob,12000+816)
            for i in range(200):
                at=0x133fa70+i*0x44
                if bytes(p.memory[at+first:at+60])!=blob[i*60+first:i*60+60] or (p.read(at+0x3c,4),p.read(at+0x40,4))!=(address(prev[i]),address(nxt[i])):
                    raise AssertionError(('overlay sprite',case,i,struct.unpack('<8f7i',blob[i*60:i*60+60]),struct.unpack_from('<8f9i',p.memory,at)))
            for node in range(200,204):
                at=address(node);assert (p.read(at+0x3c,4),p.read(at+0x40,4))==(address(prev[node]),address(nxt[node]))
        compare_state(False)
        for frame in range(frames):
            if frame%50==0:
                session.fade(*fades[(frame//50)%len(fades)] if case==0 else fades[0])
                session.bright(0x100 if case else (0x100,0xa0,0x38)[(frame//50)%3])
            session.begin()
            o.call(0x1ce570);session.send('bg',override)
            shown=frame<24 or frame%7==0 or frame>=frames-4
            session.flush(('overlay',case,frame),paint_frame=shown);overlay_frames+=1
            if frame%40==0 or frame==frames-1:compare_state(not override)
    assert variants=={1,2},variants
    group('background_overlay',start)

    # Whole option-style pages: background, frame, title plate and help line together.
    start=session.cases
    session.seed(0x5eed5eed5eed5eed);o.call(0x1ce478);o.palette();session.send('enter');session.flush(('page enter',),paint_frame=False)
    ptr,text,scroll=next(h for h in helps if h[2]==1)
    p.write(0x582c40,ptr,4);p.write(0x582c44,scroll,4)
    o.call(0x1cebb0,[len(text)]);session.send('sethelp',len(text))
    for frame in range(24 if quick else 150):
        level=min(256,max(0,(frame-90)*25)) if frame>=90 else 0
        session.fade(frame>=90,level,0xffffffff if frame%2 else 0xff000000);session.bright(0x100 if frame<60 else 0xc0)
        session.begin()
        o.call(0x1ce570);session.send('bg',0)
        alpha=p.read(0x582b38,4)*17
        o.call(0x1ce660,[1,frame%12,12]);session.send('frame',1,frame%12,12,1)
        o.call(0x1cfdb0,[alpha]);session.send('banner',0,alpha)
        o.call(0x1cff40,[0,alpha]);session.send('help',text.hex(),scroll,alpha)
        session.flush(('page',frame))
    p.memory[0x582c40:0x582c48]=saved
    group('composed_pages',start)
    return counts,dict(help_strings=len(helps),overlay_updates=overlay_frames,fade_states=len(fades))


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--quick',action='store_true')
    ap.add_argument('--report',type=Path,default=REPORT)
    args=ap.parse_args()
    blob,_=extract_menu_canvas.extract()
    assert extract_menu_canvas.OUT.read_bytes()==blob,'run extract_menu_canvas.py first'
    oracle=Oracle()
    with tempfile.TemporaryDirectory() as tmp:
        cpp=Path(tmp)/'driver.cpp';cpp.write_text(DRIVER);exe=cpp.with_suffix('')
        subprocess.run(['c++','-std=c++20','-ffp-contract=off','-O2','-I',ROOT/'src',cpp,ROOT/'src/menu_canvas.cpp',
                        ROOT/'src/console_menu.cpp',ROOT/'src/game_random.cpp',ROOT/'src/scalar_float.cpp','-o',exe],check=True)
        with subprocess.Popen([exe,ASSETS],stdin=subprocess.PIPE,stdout=subprocess.PIPE) as proc:
            session=Session(proc,oracle)
            counts,extra=run(session,args.quick)
            proc.stdin.close();assert proc.wait()==0
    report=dict(status='passed',quick=args.quick,elf_sha256=ORIGINAL,cases=session.cases,cases_by_group=counts,
                identical_primitive_lists=session.cases,identical_640x480_frames=session.frames,
                original_queue_entries=session.primitives,entries_by_kind=session.kinds,
                original_instructions=oracle.instructions,**extra,
                asset_sha256=hashlib.sha256(blob).hexdigest(),
                resources={s:hashlib.sha256((ASSETS/s).read_bytes()).hexdigest() for s in extract_menu_canvas.TEXTURES},
                scope='Whole original 1145c0, 113f98, 117de8, 117a00, 1135e8, 10a460, 109f08, 1cf8f8, 1cf598, 1ce660, 1ce878, 1ced08, 1cee68, '
                      '1cefc8, 1cf2a8, 1cfdb0, 1cff40 (with 1ceb90/1cebb0/1ceb10), 1ce478, 1ce570 and 1ce628 including 114d88 depth, 117288/117318 '
                      'fade, 1149d0/114c10 colour conversion, the BRIGHT scaling of the queue builders, the 10a710/10a1c0 glyph cache and '
                      '116588 palette interpolation. Stubbed (disc IO only): 1142d8 texture load by name and 1163c0 palette file read; the '
                      'palette is supplied through the unmodified 116478/10add8. Primitive lists are compared entry by entry in submission '
                      'order with exact float bits; glyph entries compare the cached texel block. Frames are the queue painted in ascending '
                      'depth by the reference painter of this script (the queue-to-GS translation 106c08 and GS rasterisation are not '
                      'executed). Rotated overlay quads use an inverse-affine pixel-centre model and flat triangles a top-left rule on '
                      'integer samples on both sides; entries with tag 2ff2 (latch 348b10) use the additive ALPHA preset 348bc0. Character 7f (emitter 108e68) '
                      'is not ported.')
    args.report.write_text(json.dumps(report,indent=2)+'\n');print(report)

if __name__=='__main__':main()
