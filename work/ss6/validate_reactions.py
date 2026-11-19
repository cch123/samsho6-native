#!/usr/bin/env python3
"""Original whole light-reaction selection, timers and action enqueue."""
import hashlib
import itertools
import json
import subprocess
from pathlib import Path
from mips_probe import Probe,signed

ROOT=Path(__file__).resolve().parents[2]

def main():
    raw=(ROOT/'work/ss6/extracted/SLPS_255.59').read_bytes()
    p=Probe(raw)
    source,target,os,ot,ctx=0x1c00000,0x1c00f2c,0x1e00000,0x1e01000,0x1e02000
    p.write(0x4d3d08,source,4)
    commands,expected=[],[]
    for armed,crouch,alternate,table,previous,part,special,air,shield in itertools.product(
            [0,1],[0,1],[0,1],[0,2],[0,32,35,38,44,255],[0,1,2],[0,1],[0,1],[0,1]):
        p.memory[source:source+0x2000]=bytes(0x2000)
        p.memory[os:ctx+16]=bytes(ctx+16-os)
        flags=(0x1000 if armed else 0)|(8 if crouch else 0)|(0x02000000 if shield else 0)
        for actor,obj,slot in [(source,os,0),(target,ot,1)]:
            for off,v in [(0,obj),(0xa24,slot),(0x190,0xffffffff),(0xa3c,-1)]:p.write(actor+off,v,4)
            p.write(obj+0xcc,slot,4)
        p.write(source+0x194,1,4);p.write(source+0x23c,0x1000|(0x20 if air else 0),4)
        p.write(target+0x194,table,4);p.write(target+0x23c,flags,4)
        p.write(target+0x24c,alternate*2,1);p.write(target+0x255,previous,1)
        p.run(0x14d198,[target,os,0,10,part,special])
        result=[p.read(target+0x23c,4),signed(p.read(target+0x190,2),16),signed(p.read(target+0x192,2),16),
                p.read(target+0x18c,4),p.read(target+0x255,1),p.read(target+0x256,1),
                p.read(source+0x1b0,4),p.read(source+0x1b4,4),p.read(target+0x1b0,4),p.read(target+0x1b4,4)]
        assert p.read(target+0x258,4)==p.read(target+0x25c,4)==0
        # Invoke the original callback for the selected reaction group to
        # validate the armed/unarmed action, not a second table formula.
        state=p.read(target+0x255,1)
        p.write(ctx,target,4);p.write(ctx+4,source,4)
        p.run(0x1707b0,[ctx,(state-32)//3,(state-32)%3])
        result.append(p.read(target+0xa3c,4))
        commands.append(' '.join(map(str,[flags,alternate*2,previous,table,part,special,air])))
        expected.append(result)
    binary=ROOT/'work/ss6/build-native/ss6-reaction-probe'
    result=subprocess.run([str(binary),str(ROOT/'work/ss6/extracted/resources')],
                          input='\n'.join(commands)+'\n',text=True,capture_output=True,check=True)
    actual=[list(map(int,line.split())) for line in result.stdout.splitlines()]
    assert len(actual)==len(expected)
    for i,(a,e) in enumerate(zip(actual,expected)):assert a==e,(commands[i],a,e)
    report=dict(status='passed',cases=len(commands),elf_sha256=hashlib.sha256(raw).hexdigest(),
                native_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
                scope='Whole 0x14d198 + 0x1707b0 for rawtype10, resource00, ordinary source attack, grounded target; no instruction patches/hooks; no reaction callback playback or rendering')
    (ROOT/'outputs/ss6-feasibility/reaction_validation.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()
