#!/usr/bin/env python3
"""Original coroutine slice + whole gauge early-return comparisons."""
import hashlib,itertools,json,subprocess
from pathlib import Path
from mips_probe import Probe,signed
ROOT=Path(__file__).resolve().parents[2]
def main():
 raw=(ROOT/'work/ss6/extracted/SLPS_255.59').read_bytes();p=Probe(raw)
 commands,expected=[],[]
 for remaining,delay,old in itertools.product([-1,0,1,39,40,60],[-1,0,1,2,3],[0,1]):
  for a,v in [(0x123a0ec,remaining),(0x123a0e8,delay),(0x123a0c4,0),(0x123a0c8,0),(0x46a940,old)]:p.write(a,v,4)
  p.registers[17]=0
  # Start and exit boundaries within the enclosing coroutine. All reached
  # callees (11f588/11f5a0) execute;140270 is never skipped then resumed.
  p.run(0x1390d8,stop_before=(0x139140,0x140270))
  commands.append(f'pause {remaining} {delay}')
  expected.append([signed(p.read(a,4),32) for a in [0x123a0ec,0x123a0e8,0x46a940]])
 pause_cases=len(commands);a,o,b=0x1c00000,0x1e00000,0x1d00000
 p.write(0x4d3d08,a,4);p.write(0x4d3d00,b,4)
 for state,paused in itertools.product(range(-1,11),range(2)):
  p.memory[a:a+0x2000]=bytes(0x2000);p.memory[o:o+0x200]=bytes(0x200)
  p.write(a,o,4);p.write(a+0x130,20,4);p.write(a+0x134,10000,4);p.write(a+0x138,25600,4)
  p.write(a+0x23c,0x1000,4);p.write(a+0xa30,200,4)
  p.write(b,state,4);p.write(b+8,0,4);p.write(0x46a940,paused,4)
  before=bytes(p.memory[a:a+0xf2c]);object_before=bytes(p.memory[o:o+0x200])
  p.run(0x11e760,[0]);active=p.read(a+0x130,4)!=20
  if not active:assert bytes(p.memory[a:a+0xf2c])==before and bytes(p.memory[o:o+0x200])==object_before
  commands.append(f'meters {state} {paused}');expected.append([int(active)])
 binary=ROOT/'work/ss6/build-native/ss6-round-rules-probe'
 run=subprocess.run([str(binary)],input='\n'.join(commands)+'\n',text=True,capture_output=True,check=True)
 actual=[list(map(int,row.split())) for row in run.stdout.splitlines()];assert len(actual)==len(expected)
 for c,g,w in zip(commands,actual,expected):assert g==w,(c,g,w)
 report=dict(status='passed',coroutine_slice_cases=pause_cases,whole_gauge_gate_cases=len(commands)-pause_cases,
  elf_sha256=hashlib.sha256(raw).hexdigest(),native_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
  scope='Unmodified1390d8 slice stops before139140 or140270, with complete reached11f588/11f5a0 callees. This is not a whole coroutine test. Whole11e760 resource00/system0 early-return gate with unchanged actor/object checks. Ordinary40+2KO pause only in battle fixture; match-ending60, other global pause reasons, UI and hardware cadence are excluded.')
 (ROOT/'outputs/ss6-feasibility/battle_pause_validation.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
