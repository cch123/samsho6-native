#!/usr/bin/env python3
"""Guard instruction-runner extensions needed by original effect scheduling."""
import hashlib,itertools,json,struct,random
from pathlib import Path
from mips_probe import Probe
ROOT=Path(__file__).resolve().parents[2]
def main():
 raw=(ROOT/'work/ss6/extracted/SLPS_255.59').read_bytes();p=Probe(raw)
 cases=instructions=0;address=0x1c00000
 for alignment,size,byte in itertools.product(range(16),[0,1,7,8,15,16,31,32,33,63,64,65,704],[0,1,127,128,255]):
  start=address+32+alignment
  p.memory[address:address+1024]=b'\xa5'*1024
  p.registers_high[8]=0x123456789abcdef0
  result,n=p.run(0x315f38,[start,byte,size],limit=20000);instructions+=n
  assert result==start
  assert p.memory[address:start]==b'\xa5'*(start-address)
  assert p.memory[start:start+size]==bytes([byte])*size
  assert p.memory[start+size:address+1024]==b'\xa5'*(address+1024-start-size)
  cases+=1
 # Synthetic scratch instructions check JALR delay/link semantics, including
 # rs==rd. The game's code and its instruction image remain untouched.
 for source,destination in [(4,5),(5,5),(4,31),(31,31)]:
  target=address+64;p.write(address,(source<<21)|(destination<<11)|9,4)
  p.write(address+4,0x24020007,4) # delay slot: v0=7
  p.write(address+8,(6<<21)|8,4);p.write(address+12,0,4)
  p.write(target,0x24030009,4)
  p.write(target+4,(destination<<21)|8,4);p.write(target+8,0,4)
  p.put(source,target);p.put(6,0x1ffff00)
  #run owns ra, so rs31 is set by the first scratch instruction instead.
  begin=address
  if source==31:
   p.write(address-4,(4<<21)|(31<<11)|0x2d,4);p.put(4,target);begin=address-4
  _,n=p.run(begin);instructions+=n
  assert p.registers[2:4]==[7,9] and p.registers[destination]==address+8
  cases+=1
 #MSUB preserves ACC. Exact mode stays strict; finite mode is explicit.
 for finite in [False,True]:
  q=Probe(raw,finite_model=finite)
  q.write(address,(0x11<<26)|(16<<21)|(2<<16)|(1<<11)|(3<<6)|0x1d,4)
  q.write(address+4,0x03e00008,4);q.write(address+8,0,4)
  q.float_acc=0x41200000;q.put_exact_float(1,2);q.put_exact_float(2,3)
  q.run(address);assert q.floats[3]==0x40800000 and q.float_acc==0x41200000
  cases+=1
 # The original compiler's64-bit multiply helper exercises both HI/LO
 # pairs, MADD, PMFHL.LW and aliased PCPYUD, rather than testing only
 # individual implementations against copies of their own formulas.
 rng=random.Random(0x30ede0);mask=(1<<64)-1
 edges=[0,1,0x7fffffff,0x80000000,0xffffffff,1<<32,(1<<63)-1,1<<63,mask]
 products=list(itertools.product(edges,repeat=2))+[(rng.getrandbits(64),rng.getrandbits(64)) for _ in range(512)]
 for a,b in products:
  _,n=p.run(0x30ede0,[a,b]);instructions+=n
  assert p.registers[2]==a*b&mask,(a,b,p.registers[2])
  cases+=1
 #The original vector strlen consumes LQ/PSUBB/PAND/PNOR together. Include
 #high-bit bytes and01 immediately after00 to catch cross-lane borrow bugs.
 strlen_cases=0
 for alignment,size in itertools.product(range(16),[0,1,7,8,15,16,17,31,32,63,64,65,127,255]):
  start=address+64+alignment
  data=bytes([1,128,255,127,2,254,129])*40
  p.memory[address:address+512]=b'\x01'*512;p.memory[start:start+size]=data[:size];p.write(start+size,0,1)
  result,n=p.run(0x318358,[start],limit=20000);instructions+=n
  assert result==size,(alignment,size,result)
  strlen_cases+=1;cases+=1
 #DSRLV shifts the low64 bits only; rd==rs/rt must read the old operands.
 shift_cases=0
 for dest,amount,value in itertools.product([2,4,5],[0,1,31,32,63,64,127],[0,1,0x8000000000000000,0xffffffffffffffff]):
  p.write(address,(4<<21)|(5<<16)|(dest<<11)|0x16,4)
  p.write(address+4,0x03e00008,4);p.write(address+8,0,4)
  p.registers_high[dest]=0x123456789abcdef0
  _,n=p.run(address,[amount,value]);instructions+=n
  assert p.registers[dest]==value>>(amount&63) and p.registers_high[dest]==0x123456789abcdef0
  shift_cases+=1;cases+=1
 # Exercise the newly reached libc path with a real string-backed FILE;
 # no printf, formatter or callee is replaced by an assumed return value.
 from round_entry_oracle import fixture
 q,_,_,_=fixture();reent=q.read(0x5d1bf8,4);file=q.read(reent+8,4)
 formats=[('%d',0,'0'),('%d',-1,'-1'),('%d',-2147483648,'-2147483648'),
          ('%u',0xffffffff,'4294967295'),('%08x',0x89abcdef,'89abcdef'),
          ('%04d',7,'0007'),('round=%d\n',10,'round=10\n')]
 for fmt,value,expected in formats:
  data=fmt.encode()+b'\0';q.memory[address:address+len(data)]=data
  q.write(file,0x1a00000,4);q.write(file+8,65536,4)
  _,n=q.run(0x316140,[address,value],limit=100000);instructions+=n
  end=q.read(file,4)
  assert bytes(q.memory[0x1a00000:end])==expected.encode(),(fmt,value)
  assert q.registers[2]==len(expected)
  cases+=1
 from knockdown_oracle import fixture as down_fixture
 q,_,_,_=down_fixture();reent=q.read(0x5d1bf8,4);file=q.read(reent+8,4)
 float_formats=[('%.1f',-100.0,'-100.0'),('%.1f',0.0,'0.0'),('%.2f',1.0,'1.00'),
                ('%.6f',0.125,'0.125000'),('%+.2f',1.25,'+1.25'),('%.0f',12345.0,'12345')]
 for fmt,value,expected in float_formats:
  data=fmt.encode()+b'\0';q.memory[address:address+len(data)]=data
  q.write(file,0x1a00000,4);q.write(file+8,65536,4)
  _,n=q.run(0x316140,[address,struct.unpack('<Q',struct.pack('<d',value))[0]],limit=500000);instructions+=n
  assert bytes(q.memory[0x1a00000:q.read(file,4)])==expected.encode(),(fmt,value)
  assert q.registers[2]==len(expected);cases+=1
 report=dict(status='passed',cases=cases,original_memset_cases=16*13*5,original_instructions=instructions,
  elf_sha256=hashlib.sha256(raw).hexdigest(),
  original_multiply_cases=len(products),original_printf_cases=len(formats),original_strlen_cases=strlen_cases,
  dsrlv_cases=shift_cases,original_float_printf_cases=len(float_formats),
  scope='Whole315f38 byte fills at every16-byte alignment and lengths around8/16/32/64-byte boundaries, with nonzero sentinels and nonzero prior GPR upper halves. Whole30ede0 modulo64-bit products, edge and random operands; whole316140 signed/unsigned decimal/hex/width formatting with initialized string-backed FILE. Scratch JALR delay/link/alias checks and exact/finite MSUB ACC-preservation checks; no patched original instructions. Not a complete EE emulator; DIVU by zero remains rejected.',
  instruction_reference=['https://github.com/PCSX2/pcsx2/blob/master/pcsx2/R5900OpcodeImpl.cpp','https://github.com/PCSX2/pcsx2/blob/master/pcsx2/MMI.cpp'])
 (ROOT/'outputs/ss6-feasibility/probe_extension_validation.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps(report,indent=2))
if __name__=='__main__':main()
