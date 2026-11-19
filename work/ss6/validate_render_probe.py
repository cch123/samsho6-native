#!/usr/bin/env python3
"""Accumulator extensions guarded independently of the native renderer."""
import hashlib,itertools,json,random
from pathlib import Path
from mips_probe import Probe,signed
ROOT=Path(__file__).resolve().parents[2]
def main():
 raw=(ROOT/'work/ss6/extracted/SLPS_255.59').read_bytes();p=Probe(raw);at=0x1e00000;mask=(1<<64)-1;cases=instructions=0
 for value in [0,1,0xffffffff,0x8000000000000000,0xfedcba9876543210,mask]:
  p.write(at,(4<<21)|0x11,4);p.write(at+4,(2<<11)|0x10,4);p.write(at+8,0x03e00008,4);p.write(at+12,0,4)
  p.lo,p.lo1,p.hi1=11,22,33
  _,n=p.run(at,[value]);instructions+=n;assert p.hi==value and p.registers[2]==value and (p.lo,p.lo1,p.hi1)==(11,22,33);cases+=1
 for dest,a,b,seed in itertools.product([0,4,5,6],[-2147483648,-1,0,2147483647],[-2147483648,-1,0,2147483647],[0,0xffffffff,0x7fffffffffffffff,mask]):
  p.write(at,(0x1c<<26)|(4<<21)|(5<<16)|(dest<<11)|0x20,4);p.write(at+4,0x03e00008,4);p.write(at+8,0,4)
  p.lo,p.hi=0x123456789abcdef0,0xfedcba9876543210;p.lo1=seed&0xffffffff;p.hi1=seed>>32
  p.registers_high[dest]=0x76543210abcdef00
  _,n=p.run(at,[a,b]);instructions+=n;expected=(seed+a*b)&mask
  assert p.lo1==signed(expected,32)&mask and p.hi1==signed(expected>>32,32)&mask
  assert (p.lo,p.hi)==(0x123456789abcdef0,0xfedcba9876543210)
  if dest:assert p.registers[dest]==p.lo1 and p.registers_high[dest]==0x76543210abcdef00
  cases+=1
 rng=random.Random(0x117288);tints=0
 for flags,amount in itertools.product([0,1,2,3,7],[0,1,127,255,256]):
  for _ in range(20):
   color,target=rng.getrandbits(32),rng.getrandbits(32)
   for address,value in [(0x3ebf18,flags),(0x3ec730,target),(0x3ec734,amount)]:p.write(address,value,4)
   v,n=p.run(0x117288,[color]);instructions+=n
   expected=color if not(flags&2) else (color&0xff000000)|sum(((((color>>(8*i))&255)*(256-amount)+((target>>(8*i))&255)*amount)>>8)<<(8*i) for i in range(3))
   assert v&0xffffffff==expected;(tints:=tints+1)
 report=dict(status='passed',accumulator_cases=cases,whole_tint_cases=tints,original_instructions=instructions,probe_sha256=hashlib.sha256((ROOT/'work/ss6/mips_probe.py').read_bytes()).hexdigest(),scope='ScratchMTHI/MFHI full64-bit values and MADD1 signed32 modulo64 accumulators,rd aliases and upper-GPR/other-accumulator preservation. Whole unchanged117288 original color interpolation covers nestedMULT1/MADD1. No instruction or callee patches; no hardware/exception emulation.')
 (ROOT/'outputs/ss6-feasibility/render_probe_validation.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
