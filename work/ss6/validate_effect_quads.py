#!/usr/bin/env python3
"""Every admitted effect record against original projection/rotation slices."""
import hashlib,itertools,json,struct,subprocess
from pathlib import Path
from mips_probe import Probe
ROOT=Path(__file__).resolve().parents[2]
ASSETS=ROOT/'work/ss6/extracted/resources'
def bits(v):return struct.unpack('<I',struct.pack('<f',v))[0]
def main():
 raw=(ROOT/'work/ss6/extracted/SLPS_255.59').read_bytes();p=Probe(raw,finite_model=True)
 banks=[(1,'01HitFlash.bin',[*range(20),21]),(2,'02Guard.bin',range(10)),(3,'03etc.bin',range(6,26)),(4,'04tenso.bin',range(19)),(5,'Display.bin',range(32)),(6,'Display2.bin',range(6)),
        (7,'Display3.bin',list(range(18))+[24,25,26])]
 commands=[];expected=[];instructions=records=rotated=0;angles={}
 angle_units={0}
 for bank,name,actions in banks:
  data=(ASSETS/name).read_bytes()
  for action in actions:
   first=struct.unpack_from('<I',data,0x100+4*action)[0]
   for step in range(data[0x180+action]):
    rec=0x1a0+(first+step)*60
    if struct.unpack_from('<H',data,rec)[0]&8:
     degree=struct.unpack_from('<h',data,rec+0x22)[0]
     # C signed division truncates before either mirror flips the angle.
     units=(abs(degree)<<16)//360;angle_units.update([units&65535,(-units)&65535])
 for angle in sorted(angle_units):
  values=[]
  for fn in [0x10b4b8,0x10b4f8]:
   _,n=p.run(fn,[angle]);instructions+=n;values.append(p.floats[0])
  angles[str(angle)]=values
 for bank,name,actions in banks:
  data=(ASSETS/name).read_bytes();base=0x4a4810+(bank-1)*0x3da0;p.memory[base:base+len(data)]=data
  for action in actions:
   for step in range(data[0x180+action]):
    records+=1
    for mirror,scale in itertools.product([0,0x40000,0x80000,0xc0000],[1,0.75]):
     flags=mirror|(0 if bank<=3 else 0x100000);x,y,z=(280,0,0) if bank==1 else (280.125,80.25,-10) if bank<=3 else (320,240,-60)
     cx,cy,cw=320,120,384
     p.floats[12:15]=list(map(bits,[cx,cy,cw]));p.run(0x122ed8)
     o=0x1e00000;p.memory[o:o+0x140]=bytes(0x140)
     p.floats[12:16]=list(map(bits,[x,y,z,scale]));p.run(0x123330,[o,bank,action,flags])
     p.write(o+0x28,step,4);p.run(0x123400,[o])
     rec=p.run(0x1233a0,[o])[0]
     asset,pal=p.read(rec+4,2),p.read(rec+6,2);p.write(0x4c3510+asset*4,14,4)
     _,n=p.run(0x123840,[o],stop_before=(0x114ae8,),limit=20000);instructions+=n
     sp=p.registers[29]
     vertices=[struct.unpack_from('<5fI',p.memory,sp+i*24) for i in range(4)]
     assert all(v[5]==0xffffffff for v in vertices)
     u,v,w,h=struct.unpack_from('<4h',p.memory,rec+8)
     flipX=bool(p.read(rec,2)&0x8000)^bool(flags&0x80000)
     flipY=bool(p.read(rec,2)&0x4000)^bool(flags&0x40000)
     for i,vertex in enumerate(vertices):
      assert vertex[3]==(u+(w if bool(i&2)!=flipX else 0))/512
      assert vertex[4]==(v+(h if bool(i&1)!=flipY else 0))/512
     expected.append([bits(f) for vertex in vertices for f in vertex[:2]]+[u,v,w,h,asset,pal,int(flipX),int(flipY)])
     commands.append(f'quad {bank} {action} {step} {flags} {x} {y} {z} {scale} {cx} {cy} {cw}')
     rotated+=bool(p.read(rec,2)&8 and p.read(rec+0x22,2))
 binary=ROOT/'work/ss6/build-native/ss6-effect-probe'
 result=subprocess.run([str(binary),str(ASSETS)],input='\n'.join(commands)+'\n',capture_output=True,text=True,check=True)
 actual=[list(map(int,line.split())) for line in result.stdout.splitlines()]
 assert len(actual)==len(expected)
 for i,(a,e) in enumerate(zip(actual,expected)):
  assert a==e,(commands[i],[(j,hex(x),hex(y)) for j,(x,y) in enumerate(zip(a,e)) if x!=y])
 # The PS2-specific effects CLUT is loaded by1003dc..1003f0. It is
 # separate from the generic116478 palette arena used by character art.
 palette=(ASSETS/'effect_pal_data.bin').read_bytes();assert len(palette)==11*16*4
 p.memory[0x1237740:0x1237740+len(palette)]=palette
 for address,value in [(0x3ebf2c,1),(0x3ec734,0),(0x3ec738,0),(0x3ebf18,0)]:p.write(address,value,4)
 _,n=p.run(0x116588,limit=100000);instructions+=n
 assert p.memory[0x1237a00:0x1237a00+len(palette)]==palette
 report=dict(status='passed',records=records,quad_slices=len(commands),rotated_quad_slices=rotated,
  original_instructions=instructions,rotation_cos_sin_bits=angles,
  elf_sha256=hashlib.sha256(raw).hexdigest(),native_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
  palette_sha256=hashlib.sha256(palette).hexdigest(),
  scope=f'All{sum(len(actions) for _,_,actions in banks)} admitted effect actions, every record, four mirrors and two scales, including contact hit, guard, clash and world1/2/4/5/6/10/12/36 particles, including concentration, meditation and Rage Explosion. Unmodified123840 slices stop at114ae8 after original projection/trigonometry; compare all8 vertex coordinates bitwise and UV/asset/palette selection. Whole116588 verifies all176 PS2 effects CLUT colors with no global tint/fade. Finite FP model, not EE/GS hardware coverage or rasterization proof.')
 (ROOT/'outputs/ss6-feasibility/effect_quad_validation.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps(report,indent=2))
if __name__=='__main__':main()
