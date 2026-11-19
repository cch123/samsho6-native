"""Resident resource00, initialized effect/task pools and real buffered libc."""
from round_entry_oracle import fixture as round_fixture,buffered_stdout,ROOT
from mips_probe import signed
ASSETS=ROOT/'work/ss6/extracted/resources'
ACTOR=0x1c00000;OTHER=ACTOR+0xf2c;CTX=0x1e02000;OTHER_OBJECT=0x1e01000

def fixture():
 p,a,o,b=round_fixture();p.finite_model=True
 p.memory[a:a+0x2000]=bytes(0x2000);p.memory[o:o+0x200]=bytes(0x200)
 p.write(a,o,4);p.write(OTHER,OTHER_OBJECT,4);p.write(CTX,a,4);p.write(CTX+4,OTHER,4)
 p.write(OTHER+0xa24,1,4);p.write(b+0x250,OTHER,4)
 p.write(a+0xa3c,-1,4);p.write(a+0x190,-1,4);p.write(a+0x194,2|(64<<16),4)
 p.write(a+0x23c,0x1000,4);p.write(a+0x1ac,256,4)
 p.write(o+0xc8,1,4);p.write(o+0x104,0x200,4)
 for fn in [0x120390,0x11dda0,0x11de10,0x11e1c0]:p.run(fn,[o,0],limit=200000)
 p.write(o+0x104,0x200,4) #same explicit muted initial flags as the native fixture
 initialize_effects(p)
 return p,a,o,b

def initialize_effects(p):
 #Shared with composed input tests: keep their live actor/body state while
 #providing the same real allocator and libc environment for170fa0.
 data=(ASSETS/'01HitFlash.bin').read_bytes();p.memory[0x4a4810:0x4a4810+len(data)]=data
 for i in range(32):p.write(0x4c3510+i*4,i+1,4)
 for i in range(100):p.write(0x1d00000+i*0x140+0x138,0x1d00000+(i+1)*0x140 if i<99 else 0,4)
 p.write(0x46a900,0x1d00000,4);p.write(0x46a904,100,4)
 p.write(0x345188,0,4);p.write(0x443150,0,4);p.write(0x3d2e80,1,4)
 p.write(p.read(0x5d1bf8,4)+0xa8,1,8)
 #The effect logger formats floats through newlib dtoa. Supply initialized
 #Bigint free lists, just as a warmed libc owns them; _Balloc/_Bfree and the
 #formatter still execute. No malloc-lock/kernel call is patched or skipped.
 reent=p.read(0x5d1bf8,4);free=0x1a20000;node=0x1a21000
 p.write(reent+0x4c,free,4)
 for k in range(9):
  size=20+4*(1<<k);size=(size+15)&~15
  p.write(free+k*4,node,4)
  for i in range(16):
   p.write(node,node+size if i<15 else 0,4);p.write(node+4,k,4);p.write(node+8,1<<k,4);node+=size
if __name__=='__main__':
 p,a,o,b=fixture()
 def call(fn,args=()):return p.run(fn,args,limit=500000)
 call(0x171418,[CTX,2]);call(0x149918,[a]);call(0x11d8e0,[o])
 for tick in range(300):
  p.write(o+0x30,256,4);call(0x11d730,[o]);call(0x11d6c8,[o]);call(0x168aa0,[CTX]);callback=p.read(a+0x260,4)
  call(callback,[CTX]);call(0x149918,[a]);call(0x11d8e0,[o])
  if callback!=p.read(a+0x260,4):print(tick+1,hex(callback),hex(p.read(a+0x260,4)),p.read(o+0x24,4),p.read(o+0x28,4))
  if p.read(a+0x190,2)!=65535:print('request',tick+1,hex(p.read(a+0x190,4)));break
 print('effect allocations',100-p.read(0x46a904,4))
