#!/usr/bin/env python3
"""Whole1453a8 choices plus explicitly bounded local final-result bookkeeping."""
import collections
import hashlib
import itertools
import json
import random
import struct
import subprocess
from pathlib import Path
from extract_collision_tables import SOURCE_HASH
from mips_probe import Probe, signed

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT/'work/ss6/extracted/resources'
BINARY = ROOT/'work/ss6/build-native/ss6-match-ending-probe'


def main():
    raw = (ROOT/'work/ss6/extracted/SLPS_255.59').read_bytes()
    assert hashlib.sha256(raw).hexdigest() == SOURCE_HASH
    data = (ASSETS/'ending_choices.bin').read_bytes()
    valid = lambda v,c:bool(struct.unpack_from('<I', data, (v*49+c)*68)[0])
    p = Probe(raw)
    b, a, m = 0x1b00000, 0x1c00000, 0x1d00000
    for at,value in [(0x4d3d00,b),(0x4d3d08,a),(0x4d3d04,m),(0x4c3808,3),(0x123a168,0),(0x3d2e7c,0)]:p.write(at,value,4)
    for i in range(2):
        p.write(b+0x24c+i*4,a+i*0xf2c,4)
        p.write(a+i*0xf2c+0xa24,i,4)
    commands, expected, labels = [], [], []
    counts = collections.Counter();instructions=0
    rng = random.Random(0x1453a8)

    def run(pc,args=(),stop=()):
        nonlocal instructions
        value,n=p.run(pc,args,stop_before=stop,limit=100000)
        instructions+=n;counts[('prefix' if stop else 'whole')+hex(pc)]+=1
        return signed(value,32)

    def case(op,winner,result,version,rows,label):
        parameter,stage,old_result=[signed(rng.getrandbits(32),32) for _ in range(3)]
        flags,metadata,continuation,endflag=[rng.getrandbits(32) for _ in range(4)]
        config=[winner,result,parameter,version,stage,old_result,flags,metadata,continuation,endflag]
        for at,value in [(0x4c3810,winner),(b+0x28,result),(b+0x2c,parameter),(0x4c3830,stage),
                         (0x4c3894,old_result),(0x1239090,flags),(m+4,metadata),(0x4c3834,continuation),(0x4c38ac,endflag)]:p.write(at,value,4)
        p.write(0x43d052,version,1)
        for i,row in enumerate(rows):
            char,system,hp,wins,required,outcome,other=row
            for off,value in [(0xa14,char),(0x10c,system),(0xa30,hp)]:p.write(a+i*0xf2c+off,value,4)
            for off,value in [(0x28,wins),(0x2c,required),(0x1c,outcome),(0x20,other)]:p.write(b+0x254+i*0x108+off,value,4)
            config+=row
        if op==0:ret=run(0x1453a8,[b])
        else:
            #145118 reaches its genuine139f20 call boundary. The logger
            #inside139f20 remains outside this prefix; never patch/resume it.
            run(0x145118,[b],(0x139f20,))
            #The no-profile139f20 branch has only11c208's state mutation.
            #Verify that whole helper independently; diagnostics hook is null.
            run(0x11c208);ret=0
        out=[ret,signed(p.read(0x4c3810,4),32),signed(p.read(b+0x28,4),32),signed(p.read(b+0x2c,4),32),version,
             signed(p.read(0x4c3830,4),32),signed(p.read(0x4c3894,4),32),p.read(0x1239090,4),metadata,
             p.read(0x4c3834,4),p.read(0x4c38ac,4)]
        for i in range(2):
            out += [p.read(a+i*0xf2c+0xa14,4),p.read(a+i*0xf2c+0x10c,4),signed(p.read(a+i*0xf2c+0xa30,4),32)]
            out += [signed(p.read(b+0x254+i*0x108+off,4),32) for off in [0x28,0x2c,0x1c,0x20]]
        commands.append(' '.join(map(str,[op,*config])));expected.append(out);labels.append(label)

    for version,character,choice in itertools.product([0,1],range(52),range(16)):
        if character<49 and not valid(version,character):continue
        p.write(0x43d052,version,1)
        value=run(0x1a3070,[character,2,choice])
        commands.append(f'2 {character} {choice} {version}');expected.append([int(value!=0)]);labels.append(('presence',version,character,choice))
    for version,system,hit,other,life,same in itertools.product([0,1],range(9),[-1,0,1,2,3,4,5],[-1,0,1],[99,100],[False,True]):
        rows=[[0,system,life,2,2,hit,other],[0 if same else 1,0,0,0,2,-1,-1]]
        case(0,0,0,version,rows,('matrix',version,system,hit,other,life,same))
    for op in [0,1]:
        for n in range(1024):
            version=rng.randrange(2);chars=[c for c in range(49) if valid(version,c)]
            rows=[[rng.choice(chars),rng.randrange(9),rng.choice([-1,0,99,100,200]),rng.randrange(4),rng.randrange(1,4),rng.choice([-1,0,1,2,3,4,5]),rng.choice([-1,0,1,2])] for _ in range(2)]
            case(op,rng.choice([-1,0,1]),rng.randrange(4),version,rows,('random',op,n))
    native=subprocess.run([str(BINARY),str(ASSETS)],input='\n'.join(commands)+'\n',text=True,capture_output=True)
    assert native.returncode==0,(native.returncode,native.stderr)
    actual=[list(map(int,line.split())) for line in native.stdout.splitlines()]
    assert len(actual)==len(expected)
    for i,(got,want) in enumerate(zip(actual,expected)):assert got==want,(i,labels[i],got,want)
    report=dict(status='passed',snapshots=len(expected),original_functions=dict(counts),original_instructions=instructions,
                native_sha256=hashlib.sha256(BINARY.read_bytes()).hexdigest(),elf_sha256=SOURCE_HASH,
                asset_sha256=hashlib.sha256(data).hexdigest(),
                scope='Whole unmodified1453a8 and1a3070 group2 presence, systems0..8 and both file-backed character-version tables. ExactHP100 threshold, same-character fallback, outcomes, time-result/dual-winner preservation, parameter2c and missing-special fallback. Final bookkeeping uses145118 prefix stopping at139f20, plus independent whole11c208 under null diagnostic hook; no whole139f20/145118 or profile persistence claim. All reached callees intact. Actor data are boundary fixtures, not animation/full matches. Unresolved alternate-character table rows explicitly excluded/rejected.')
    (ROOT/'outputs/ss6-feasibility/match_ending_validation.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
