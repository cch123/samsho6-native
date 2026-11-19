#!/usr/bin/env python3
"""Export stage-zero's fixed-camera projected strips over the Game Over task's lifetime."""
import hashlib
import struct
from character_tiles_oracle import ASSETS
from extract_versus_result_layout import canvas
FRAME_COUNT=336
def prepare():
 p=canvas()
 p.write(0x50e048,0x60000000,4);p.write(0x510ce8,p.read(0x652c4c,4),4)
 for slot,bank in [(4,32),(5,32),(6,48),(7,48)]:p.run(0x10add8,(slot,bank))
 for fn in (0x1a73e8,0x1a7668,0x1a74d0,0x1a7540):p.run(fn,limit=2000000)
 p.run(0x13847c,stop_before=[0x1384cc])
 p.write(0x46a908,256,4)
 return p

def capture(p):
 strips=[]
 def record(pc):
  if pc!=0x1149d0:return
  slot=p.registers[6]&255;pointer=p.registers[4]
  vertices=[struct.unpack_from('<5fI',p.memory,pointer+24*i) for i in range(p.registers[5])]
  assert 3<=len(vertices)<=128 and 4<=slot<=7 and p.read(0x3a9680+slot*40+16,4)==(32 if slot<6 else 48)
  z,color=vertices[0][2],vertices[0][5]
  assert all(v[2]==z and v[5]==color for v in vertices) and color in (0xffffffff,0x60000000)
  strips.append((z,slot,color,[(v[0],v[1],v[3],v[4]) for v in vertices]))
 p.run(0x114e80)
 p.run(0x1a7810,limit=1800000,observe=record)
 return sorted(strips,key=lambda strip:strip[0])

def extract():
 assert hashlib.sha256((ASSETS.parent/'SLPS_255.59').read_bytes()).hexdigest()=='72420e74e04d7ac39119d1b6ec7d70ed004fc98c5035fade96e87d05d4b9ffbf'
 p=prepare();index={};sequence=bytearray()
 for i in range(FRAME_COUNT):
  frame=capture(p);indices=[]
  for _,slot,color,vertices in frame:
   packed=struct.pack(f'<3I{4*len(vertices)}f',slot,color,len(vertices),*(n for v in vertices for n in v))
   indices.append(index.setdefault(packed,len(index)))
  sequence.extend(struct.pack(f'<{len(indices)+1}I',len(indices),*indices))
 result=ASSETS/'versus_draw_stage.bin'
 result.write_bytes(struct.pack('<4s3I',b'VSTG',1,FRAME_COUNT,len(index))+b''.join(index)+sequence)
 print(f'{FRAME_COUNT} stage visits, {len(index)} distinct strips, {result.stat().st_size} bytes at {result}')
if __name__=='__main__':extract()
