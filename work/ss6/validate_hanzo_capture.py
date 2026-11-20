#!/usr/bin/env python3
"""Compare Hattori Hanzō's paired victim entries with the Japanese game."""
import argparse
from concurrent.futures import ProcessPoolExecutor
from hashlib import sha256
import itertools
import json
from pathlib import Path
import subprocess
import tempfile

from validate_nakoruru_capture import ASSETS, BUILD, DRIVER, ELF, PIN, ROOT, compare


def phase_oracle(seat):
    from validate_weapon_handling import setup
    src,_=setup(seat,0)
    p=src.p;target,other=src.o,p.read(src.other,4)
    # The native trace uses the selected seat's resource slot to fetch ACTs.
    # Pair the actual banks just as the public console selection does.
    for index,character in ((seat,0),(1-seat,3)):
        act=(ASSETS/f'act_{character:02}.bin').read_bytes()
        aid=(ASSETS/f'aid_{character:02}.bin').read_bytes()
        base=0x1400000+0x100000*index
        p.memory[base:base+len(act)]=act
        p.memory[0x46a9b0+0x1800*index:0x46a9b0+0x1800*(index+1)]=aid
        p.write(0x4751b0+index*4,base,4)
        p.write(0x46a9a0+index*4,character,4)
    fields=[]
    for a,o,i in ((src.a,target,seat),(src.other,other,1-seat)):
        p.write(o+0xc,i,4);p.write(o+0x14,0 if i==seat else 3,4)
        p.write(a+0xa10,0 if i==seat else 3,4);p.write(a+0xa24,i,4)
        fields.extend((a+off,1 if off==0x19a else 4) for off in
                      (0x194,0x23c,0x248,0xa3c,0x1ac,0x20c,0x19a,*range(0x260,0x27c,4),*range(0x28c,0x2c0,4)))
        fields.extend((o+off,4) for off in (0x24,0x28,0xc0,0x3c,0x104,0x38,0x40,0x44,*range(0x4c,0x64,4)))
    ctx=0x1db0000;p.write(ctx,src.a,4);p.write(ctx+4,src.other,4)
    # Damage calculation has a separate oracle. Observe its exact call and
    # retain the live pre-callback health for an isolated pair-phase comparison.
    p.write(0x1413d8,0x03e00008,4);p.write(0x1413dc,0,4)
    return p,ctx,fields


def phases(job):
    from validate_hanzo_specials import pads
    exe,seat,state=job
    moves,_=pads(seat,state,'near')
    out=subprocess.check_output([exe,ASSETS],input=''.join(f'{a} {b}\n' for a,b in moves),text=True)
    p,ctx,fields=phase_oracle(1-seat)
    damage=[];visits=steps=0
    for line in out.splitlines():
        tick,*values=map(int,line.split());n=len(fields)
        assert len(values)==2*n
        for (ad,size),value in zip(fields,values[:n]):p.write(ad,value,size)
        p.write(ctx+8,values[0]//65536-80,4)
        _,count=p.run(0x165cc0,[ctx],observe=lambda pc:damage.append(p.registers[5]) if pc==0x1413d8 else None)
        visits+=1;steps+=count
        diff=[(i,hex(ad),hex(p.read(ad,size)),hex(v)) for i,((ad,size),v) in enumerate(zip(fields,values[n:]))
              if p.read(ad,size)!=v%2**(8*size)]
        assert not diff,(seat,state,tick,values[14],diff)
    assert visits>0
    expected={72:16,73:22,74:35,75:9,76:12,77:20,91:45}
    assert damage==([expected[state]] if state in expected else []),(seat,state,damage)
    return dict(seat=seat+1,state=state,visits=visits,instructions=steps,scripted_damage=damage)


def phase_trace(directory):
    exe=directory/'phase';obj=directory/'capture.o';flags=['c++','-std=c++20','-ffp-contract=off','-O2','-I',ROOT/'src']
    subprocess.run([*flags,'-DupdateFighterCapture=measuredCapture',
                    '-c',ROOT/'src/nakoruru_capture.cpp','-o',obj],check=True)
    subprocess.run([*flags,ROOT/'work/ss6/hanzo_capture_trace.cpp',obj,BUILD/'libss6-runtime.a','-o',exe],check=True)
    return exe


def main():
    cli=argparse.ArgumentParser()
    cli.add_argument('--sample',action='store_true')
    cli.add_argument('--phase',type=int)
    args=cli.parse_args()
    if args.phase:
        with tempfile.TemporaryDirectory() as td:print(phases((phase_trace(Path(td)),0,args.phase)))
        return
    slots=(0,1,2,3,4,5,6,7,16)
    specs=[(*s,0,2,3) for s in itertools.product(slots,(0,1),(0,1),range(4))]
    specs += [(slot,seat,1,(slot+seat)%4,mode,system,3) for slot in slots for seat in (0,1)
              for mode in (1,2,3,4,15,16,17) for system in ((1,2) if slot==5 else (2,))]
    if args.sample:specs=[(slot,0,1,0,0,2,3) for slot in slots]
    assert sha256(ELF.read_bytes()).hexdigest()==PIN
    with tempfile.TemporaryDirectory() as tmp:
        d=Path(tmp);cpp=d/'capture.cpp';exe=d/'capture';cpp.write_text(DRIVER)
        subprocess.run(['c++','-std=c++20','-ffp-contract=off','-I',ROOT/'src',cpp,BUILD/'libss6-runtime.a','-o',exe],check=True)
        rows=subprocess.check_output([exe,ASSETS,'3'],input=''.join(' '.join(map(str,s[:6]))+'\n' for s in specs),text=True).splitlines()
    with ProcessPoolExecutor(4) as pool:expected=list(pool.map(compare,specs))
    for spec,row,(values,_) in zip(specs,rows,expected,strict=True):
        actual=list(map(int,row.split()))
        assert actual==values,(spec,[(i,x,y) for i,(x,y) in enumerate(zip(actual,values,strict=True)) if x!=y])
    if args.sample:return
    with tempfile.TemporaryDirectory() as tmp,ProcessPoolExecutor(4) as pool:
        exe=phase_trace(Path(tmp))
        live=list(pool.map(phases,[(exe,side,state) for side in (0,1) for state in (72,73,74,75,76,77,78,91)]))
    report=dict(status='passed',elf_sha256=PIN,entries=len(specs),slots=slots,source=3,targets=[0,1,2,3],live_phases=live,
                runtime_sha256=sha256((BUILD/'libss6-runtime.a').read_bytes()).hexdigest(),
                original_instructions=sum(n for _,n in expected))
    (ROOT/'outputs/ss6-feasibility/hanzo-capture-validation.json').write_text(json.dumps(report,indent=2)+'\n')
    print(len(specs),'paired capture entries')

if __name__=='__main__':main()
