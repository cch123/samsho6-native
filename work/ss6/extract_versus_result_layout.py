#!/usr/bin/env python3
"""Extract the original VS-next background tile records and finite portrait timeline."""
import hashlib
import struct
from character_tiles_oracle import ASSETS, fixture, begin

LAYOUT=ASSETS/'versus_result_layout.bin'
def canvas():
 p=fixture();begin(p)
 p.write(0x3ec73c,1,4)  # Stop hardware submission after computing clipped game vertices.
 p.write(0x4ca1ac,0,4)
 return p

def calls(p,fn,*args):
 sprites=[];desc=[]
 def trace(pc):
  if pc==0x1149d0:
   start=p.registers[4];slot=p.registers[6]&255
   v=[struct.unpack_from('<5fI',p.memory,start+i*24) for i in range(4)]
   sprites.append((slot,v))
  elif pc==0x114c10:
   v=[struct.unpack_from('<fffI',p.memory,p.registers[4]+i*16) for i in range(4)]
   sprites.append((0,v))
  elif pc==0x117de8:
   desc.append((struct.unpack_from('<6I',p.memory,p.registers[4]),int(p.float_value(12)),int(p.float_value(13))))
 p.run(fn,args,limit=1000000,observe=trace)
 return sprites,desc

def extract():
 assert hashlib.sha256((ASSETS.parent/'SLPS_255.59').read_bytes()).hexdigest()=='72420e74e04d7ac39119d1b6ec7d70ed004fc98c5035fade96e87d05d4b9ffbf'
 p=canvas();rows=calls(p,0x135438,0)[1];assert len(rows)==110
 data=bytearray(b'VSAR\x01\0\0\0')
 for i,(d,x,y) in enumerate(rows):
  u,v,w,h,flags,slot=d;assert slot==4 and w==83 and x==(i%10)*83
  data.extend(struct.pack('<6H',u,v,w,h,flags,y))
 for winner in (0,1):
  p.write(0x4c3810,winner,4)
  for tick in range(61):
   calls(p,0x136480,tick);calls(p,0x136500,tick);out=calls(p,0x1366e0,tick)[0]
   assert len(out)<=2
   data.extend(struct.pack('<I',len(out)))
   for i in range(2):
    if i<len(out):
     slot,verts=out[i];assert slot==8
     # Keep all four projected vertices. The left portrait slice stores its
     # source picture rotated by a quarter turn in the bottom of win_00.
     for x,y,z,u,v,c in verts:
      assert c==0xffffffff
      data.extend(struct.pack('<4f',x,y,u*512,v*512))
    else:data.extend(bytes(64))
 LAYOUT.write_bytes(data)
 return LAYOUT
if __name__=='__main__':print(extract())
