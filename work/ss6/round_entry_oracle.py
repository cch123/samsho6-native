"""Original resource00 round entry fixture with buffered, real libc logging."""
from pathlib import Path
from mips_probe import idle_fixture
ROOT=Path(__file__).resolve().parents[2]
def buffered_stdout(p):
 # Supply a real initialized string-backed FILE, not a patched logger.
 r=p.read(0x5d1bf8,4);f=p.read(r+8,4);p.write(r+0x38,1,4)
 for off,v,n in [(0,0x1a00000,4),(8,65536,4),(12,0x208,2),(16,0x1a00000,4),(20,65536,4)]:p.write(f+off,v,n)
def fixture(player=0,character=0):
 assets=ROOT/'work/ss6/extracted/resources'
 p,o=idle_fixture((ROOT/'work/ss6/extracted/SLPS_255.59').read_bytes(),
                 (assets/f'aid_{character:02}.bin').read_bytes(),(assets/f'act_{character:02}.bin').read_bytes())
 a,b=0x1c00000+player*0xf2c,0x1b00000
 p.write(0x46a9a0,character,4)
 for off in (0x114,0xa10,0xa14):p.write(a+off,character,4)
 for off in (0x14,0x18):p.write(o+off,character,4)
 p.write(a,o,4);p.write(0x4d3d08,0x1c00000,4);p.write(0x4d3d00,b,4);p.write(b+0x24c+player*4,a,4)
 p.write(0x4c3808,3,4);p.write(a+0xa24,player,4)
 p.write(b+0x13c,3,4) # explicit no-time-limit fixture,1407d0 returns-1
 p.write(a+0xa3c,-1,4);p.write(a+0x194,41<<16,4)
 p.write(o+0xcc,player,4);p.write(o+0x104,0x200,4);p.write(o+0xc8,1,4)
 p.run(0x120390,[o,495]);p.run(0x11e290);p.run(0x112570);p.run(0x146e88,[b+0x14c,64])
 # Supply an initialized string-backed FILE. Original printf/vfprintf and
 # copying functions execute unchanged; this avoids PS2 host I/O, not the
 # logger call or its formatter. Buffer ownership is an explicit fixture.
 buffered_stdout(p)
 return p,a,o,b
if __name__=='__main__':
 p,a,o,b=fixture()
 print(p.run(0x149008,[a,0],limit=100000))
 print('actor',[(hex(off),hex(p.read(a+off,4))) for off in [0x194,0x23c,0x244,0x248,0x260,0xa30,0xa34]])
 print('body',[(hex(off),hex(p.read(o+off,4))) for off in [0x24,0x28,0xc4,0x38,0x104,0x108]])
 print('log',bytes(p.memory[0x1a00000:0x1a00080]).split(b'\0')[0])
