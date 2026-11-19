#!/usr/bin/env python3
"""Whole original life/KO and timer helper comparisons; no FP approximation."""
import hashlib
import json
import random
import struct
import subprocess
from pathlib import Path
from mips_probe import Probe,signed

ROOT=Path(__file__).resolve().parents[2]

def main():
    raw=(ROOT/'work/ss6/extracted/SLPS_255.59').read_bytes()
    p=Probe(raw)
    actor,obj=0x1e00000,0x1e01000
    commands,expected=[],[]
    rng=random.Random(151968)
    for _ in range(2048):
        life,maximum,damage=[rng.randrange(0,301) for _ in range(3)]
        action=rng.choice([-1,0,185,407,408,409,410,411,412])
        flags=rng.randrange(2**32)
        conditions=rng.randrange(2**32)
        y=rng.choice([-4.5,0,0.5,10])
        training=rng.randrange(2)
        timer=rng.randrange(0,10000)
        p.memory[actor:actor+0x2000]=bytes(0x2000)
        p.write(actor,obj,4)
        for off,v in [(0xa30,life),(0xa34,maximum),(0xa38,damage),(0xa3c,action),
                      (0x23c,flags),(0x160,conditions),(0x220,timer)]:p.write(actor+off,v,4)
        p.write(obj+0x44,struct.unpack('<I',struct.pack('<f',y))[0],4)
        p.write(0x123a0c0,training,1)
        p.run(0x151968,[actor])
        commands.append('life '+' '.join(map(str,[life,maximum,damage,action,flags,conditions,y,training,timer])))
        expected.append([p.read(actor+off,4) for off in [0xa30,0xa38,0x23c,0x220]])
    life_count=len(commands)
    for op,addr in [('decrease',0x14d010),('increase',0x14d038),('contact',0x1520a0)]:
        for _ in range(1024):
            delta=rng.choice([0,1,128,256,300,512,65535,0x7fffffff])
            first=rng.choice([0,1,255,256,257,512,rng.randrange(-2**31,2**31)])
            second=rng.randrange(-2**31,2**31)
            for i,v in enumerate([delta,first,second]):p.write(actor+0x1ac+4*i,v,4)
            value,_=p.run(addr,[actor if op=='contact' else actor+0x1ac,0])
            commands.append(' '.join(map(str,[op,delta,first,second])))
            expected.append([signed(value,32),signed(p.read(actor+0x1b0,4),32),signed(p.read(actor+0x1b4,4),32)])
    binary=ROOT/'work/ss6/build-native/ss6-actor-state-probe'
    result=subprocess.run([str(binary)],input='\n'.join(commands)+'\n',capture_output=True,text=True,check=True)
    actual=[list(map(int,line.split())) for line in result.stdout.splitlines()]
    assert len(actual)==len(expected)
    for i,(a,e) in enumerate(zip(actual,expected)):assert a==e,(commands[i],a,e)
    report=dict(status='passed',life_cases=life_count,timer_cases=len(commands)-life_count,
                elf_sha256=hashlib.sha256(raw).hexdigest(),native_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
                scope='Whole 0x151968 ordinary nonnegative damage; 0x14d010/0x14d038/0x1520a0; no instruction patches/hooks; no round scheduler or healing-effect path')
    (ROOT/'outputs/ss6-feasibility/actor_state_validation.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()
