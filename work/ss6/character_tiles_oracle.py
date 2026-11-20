"""Original character renderer with real palette allocation and tile copies.

All reached callees execute. The initialized ordinary memory arenas are not
PS2 hardware/GS emulation; callers can observe108910 before packet creation.
"""
import struct
from pathlib import Path
from mips_probe import Probe
from round_entry_oracle import buffered_stdout
ROOT=Path(__file__).resolve().parents[2];ASSETS=ROOT/'work/ss6/extracted/resources'
ATLAS=0x1800000
bits=lambda v:struct.unpack('<I',struct.pack('<f',v))[0]
def fixture(resources=(0,0,51)):
 p=Probe((ROOT/'work/ss6/extracted/SLPS_255.59').read_bytes(),finite_model=True);buffered_stdout(p)
 # The original addresses each bank through its pointer table, so these
 # fixture arenas are free choices. Default bases stay fixed; a bank larger
 # than its stride (Mina's chr/map/act) moves only the following slots.
 limits={'chr':ATLAS,'map':0x1400000,'act':0x1c30000,'pil':0x1a00000}
 ends={}
 for slot,res in enumerate(resources):
  for name,base,pointer in [('idx',0x46f1b0+slot*0x2000,None),('chr',0x1400000+slot*0x180000,0x4751f8),('map',0x1300000+slot*0x50000,0x475210),('aid',0x46a9b0+slot*0x1800,None),('act',0x1b00000+slot*0x80000,0x4751b0),('pil',0x1900000+slot*0x50000,0x4751c8)]:
   d=(ASSETS/f'{name}_{res:02}.bin').read_bytes()
   if name in limits:
    base=max(base,(ends.get(name,0)+0xffff)&~0xffff)
    if base+len(d)>limits[name]:
     # Two oversized banks (a Mina mirror) cannot share one region. Use the
     # separate overflow arena, which no default layout touches.
     base=(ends.get('overflow',0x1d40000)+0xffff)&~0xffff;ends['overflow']=base+len(d)
     assert ends['overflow']<=0x1e00000,(name,resources,hex(ends['overflow']))
    else:ends[name]=base+len(d)
   p.memory[base:base+len(d)]=d
   if pointer:p.write(pointer+slot*4,base,4)
  p.write(0x46a9a0+slot*4,res,4)
 d=(ASSETS/'pal_all.bin').read_bytes();p.memory[0x3f8a40:0x3f8a40+len(d)]=d
 for i in range(24):
  for at,v in [(0x439a48,-1),(0x439aa8,0),(0x439b08,0)]:p.write(at+i*4,v,4)
 for at,v in [(0x3ec73c,0),(0x3aa098,ATLAS),(0x439b68,0),(0x43d064,256),(0x3ebf2c,1)]:p.write(at,v,4)
 p.run(0x114cb8,limit=100000) #actual1024 group UV table
 return p

def begin(p,seed=0,count=0,zcount=0):
 #Original retained atlas bytes, seeded to expose unexpected overwrites.
 p.memory[ATLAS:ATLAS+131072]=bytes((i*17+seed)%256 for i in range(131072))
 for at,v in [(0x3eb910,count),(0x3db8f8,zcount),(0x3a8e10,0),(0x34517c,0),(0x345150,0),(0x345158,0),(0x439a40,0)]:p.write(at,v,4)
 p.memory[0x43cfc8:0x43cfc8+128]=bytes(128)
 p.memory[0x1a00000:0x1a10000]=bytes(65536)
 #Reset the bounded diagnostic FILE between batches, preserving real libc.
 reent=p.read(0x5d1bf8,4);file=p.read(reent+8,4);p.write(file,0x1a00000,4);p.write(file+8,65536,4)
