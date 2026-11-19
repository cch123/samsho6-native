#!/usr/bin/env python3
"""Check the empty-hand reversal's zero-length AID row and signed terminal step."""
from hashlib import sha256
import json
import subprocess
from mips_probe import idle_fixture, signed
from validate_nakoruru_capture import ASSETS, BUILD, ELF, PIN, ROOT

raw=ELF.read_bytes()
assert sha256(raw).hexdigest()==PIN
aid=(ASSETS/'aid_03.bin').read_bytes()
act=(ASSETS/'act_03.bin').read_bytes()
assert aid[0x1000+693]==0
p,body=idle_fixture(raw,aid,act)
p.write(body+0xc8,1,4);p.write(body+0x104,0x200,4)
p.run(0x120390,[body,0])
for fn in (0x11dda0,0x11de10,0x11e1c0):p.run(fn,[body])
seq=[];expected=[]
fields=[0x24,0x28,0x2c,0xc0,0x3c,0x38,0x104,0x108,0xc4,*range(0x4c,0x64,4),0x40,0x44]
def visit(command,fn,*args):
    p.run(fn,[body,*args])
    seq.append(command)
    expected.append([signed(p.read(body+i,4),32) if 0x4c<=i<0x64 else p.read(body+i,4) for i in fields]+[p.read(body+0xfe,2)])
initial_flags=[p.read(body+off,4) for off in (0x38,0x104,0x108)]
seq.append('flags '+' '.join(map(str,initial_flags)))
expected.append([p.read(body+i,4) for i in fields]+[p.read(body+0xfe,2)])
for delta in (128,256,512):
    visit('request 693 1',0x11d908,693,0,1)
    visit('commit',0x11d8e0)
    assert expected[-1][:2]==[693,0]
    for _ in range(100):
        p.write(body+0x30,delta,4);visit(f'animate {delta}',0x11d730);visit(f'move {delta}',0x11d6c8)
        if expected[-1][3]:break
    assert expected[-1][:2]==[693,0xffffffff]
    visit('request 685 1',0x11d908,685,0,1);visit('commit',0x11d8e0)
binary=BUILD/'ss6-player-object-probe'
output=subprocess.check_output([binary,ASSETS,'3'],input='\n'.join(seq)+'\n',text=True)
for op,row,values in zip(seq,output.splitlines(),expected,strict=True):
    got=list(map(int,row.split()))
    assert got==values,(op,got,values)
report=dict(status='passed',elf_sha256=PIN,probe_sha256=sha256(binary.read_bytes()).hexdigest(),
            states=len(seq),action=693,original_count=0,last_step=-1,next_action=685)
(ROOT/'outputs/ss6-feasibility/hanzo-sparse-action-validation.json').write_text(json.dumps(report,indent=2)+'\n')
print(report)
