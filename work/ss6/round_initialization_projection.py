"""Extended round-entry projection; original functions are never patched."""
import struct
from mips_probe import signed
from validate_input_features import HELD,PRESSED
from validate_object_pools import TASKS,OBJECTS,handle,digest

CONTROL=[0x88,0x8c,0xbc,0xc4,0xcc,0xd8,0xe4,0xe8]
DATA=[0x240,0xa50,4,0xf10,0x128,0x130,0x134,0x138,0xb4,0xb8,0xc0,0xc8,*CONTROL]

def align_initial_fixture(p,a,o):
 #The existing ground fixture uses149008 for its initial baseline. Match
 #the new native fields' explicit constructor values BEFORE the tested
 #round entry; do not retain that setup call's RNG/control/history outputs.
 for off in [*CONTROL,*range(0xc,0x34,4),*range(0x38,0x60,4),0xa50,0xf10]:p.write(a+off,0,4)
 p.memory[a+0xf14:a+0xf2b]=bytes(23)
 p.write(a+4,0,4);p.write(a+0x2c0,-1,4);p.write(o+0x70,0x3f800000,4)
 p.write(0x443150,0,4);p.write(0x3d2e80,1,4);p.write(p.read(0x5d1bf8,4)+0xa8,1,8)

def reset_storage(p,a,b,player,run):
 run(0x112570)
 p.memory[OBJECTS:OBJECTS+256*320]=bytes(256*320);run(0x11e290)
 registry=b+0x29c+player*0x108;p.memory[registry:registry+192]=bytes(192)
 p.memory[a+0xa5c:a+0xf10]=bytes(0xf10-0xa5c)

def seed_data(p,a,data):
 for off,value in zip(DATA,data[:20]):p.write(a+off,value,4)
 for index,base in [(20,0xc),(30,0x38)]:
  for i,value in enumerate(data[index:index+10]):p.write(a+base+4*i,value,4)
 p.memory[a+0xf14:a+0xf2b]=bytes(data[40:63])
 mode,game,library=data[63:]
 p.write(0x443150,mode,4);p.write(0x3d2e80,game,4);p.write(p.read(0x5d1bf8,4)+0xa8,library,8)

def snapshot(p,a,o,b,player,images):
 rd=lambda off:p.read(a+off,4)
 values=[signed(rd(0xa3c),32),signed(p.read(o+0xc4,4),32),p.read(o+0x8c,4),p.read(o+0x20,4)]
 values += [signed(rd(off),32) for off in [0xa30,0xa34,0xa38]]
 values += [rd(off) for off in [0x240,0xa2c,0xa50,4,0xf10]]
 values += [signed(rd(off),32) for off in [0x120,0x124,0x128,0x130,0x134,0x138]]
 values += [rd(off) for off in [0xb4,0xb8,0xc0,0xc8,*CONTROL,*range(0xc,0x34,4),*range(0x38,0x60,4)]]
 values += list(p.memory[a+0xf14:a+0xf2b])
 values += [signed(p.read(0x443150,4),32),p.read(0x3d2e80,4),p.read(p.read(0x5d1bf8,4)+0xa8,8)]
 values += [p.read(o+off,4) for off in [0xc,0x30,0x70,0x48,0x64,0x68,0x6c,0xec,0xf0]]
 values += [p.read(a+0xa5c,1),*struct.unpack_from('<300I',p.memory,a+0xa60)]
 th=lambda ptr:handle(ptr,TASKS,52);oh=lambda ptr:handle(ptr,OBJECTS,320)
 values += [th(p.read(b+0x29c+player*0x108+i*4,4)) for i in range(48)]+images
 tasks=list(struct.unpack_from('<3328I',p.memory,TASKS));objects=list(struct.unpack_from('<20480I',p.memory,OBJECTS))
 for i in range(256):
  tasks[i*13+3]=th(tasks[i*13+3]);tasks[i*13+7]=oh(tasks[i*13+7])
  row=objects[i*80:(i+1)*80]
  row[1]=th(row[1]);row[78]=oh(row[78])
  if row[0x118//4]:
   assert row[0x118//4]==a,hex(row[0x118//4]);row[0x118//4]=player+1
  if row[0xbc//4]:row[0xbc//4]=row[0xbc//4]-0x1700000+1
  objects[i*80:(i+1)*80]=row
 values += [th(p.read(0x1232844,4)),oh(p.read(0x46a900,4)),p.read(0x46a904,4),digest(tasks),digest(objects)]
 owner=a+0x2c4
 values += [signed(p.read(owner+0x5bc,4),32),signed(p.read(owner+0x5c0,4),32),1]
 values += list(p.memory[owner+0x428:owner+0x448])
 for special,count in [(False,31),(True,32)]:
  for i in range(count):
   values += [signed(p.read(owner+(0x644 if special else 0x4c4)+i*2,2),16),p.read(owner+(0x5c4 if special else 0x448)+i*4,4)]
 values += [signed(rd(0x2c0),32),*struct.unpack_from('<600H',p.memory,HELD),*struct.unpack_from('<600H',p.memory,PRESSED)]
 values += [signed(p.read(address,4),32) for address in [0x585224,0x58524c]]
 return values
