#!/usr/bin/env python3
"""Compare native damage with original functions under an explicit FP model.

The instruction stream is untouched and calls are not intercepted. This
validates the formula port under the chosen model, NOT EE hardware rounding.
"""
import hashlib
import json
import random
import subprocess
from pathlib import Path
from finite_float import arithmetic
from mips_probe import Probe, signed
from extract_collision_tables import SOURCE_HASH

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'outputs/ss6-feasibility'

def main():
    raw=(ROOT/'work/ss6/extracted/SLPS_255.59').read_bytes()
    assert hashlib.sha256(raw).hexdigest()==SOURCE_HASH
    binary=ROOT/'work/ss6/build-native/ss6-damage-probe'
    rng=random.Random(25559)
    commands,expected=[],[]
    # A rational implementation and a native integer-significand
    # implementation exercise different failure modes and rounding paths.
    edges=[0,0x80000000,0x3f800000,0xbf800000,0x3f7fffff,0x3f800001,
           0x3c23d70a,0x3f000000,0x4b7fffff,0xcb7fffff,0x3e800000,0x40490fdb]
    pairs=[(a,b) for a in edges for b in edges]
    pairs += [(rng.randrange(2)<<31|rng.randrange(85,170)<<23|rng.randrange(1<<23),
               rng.randrange(2)<<31|rng.randrange(85,170)<<23|rng.randrange(1<<23)) for _ in range(2048)]
    for op in ['add','sub','mul','div']:
        for a,b in pairs:
            if op=='div' and not b&0x7fffffff: continue
            commands.append(f'{op} {a} {b}')
            expected.append([arithmetic(op,a,b)])
    scalar_count=len(commands)
    probe=Probe(raw,finite_model=True)
    source,target=0x1e00000,0x1e01000
    max_steps=0
    cases=[]
    for life in [0,1,19,20,39,40,99,100,180,199,200]:
        for current in [0,1,256,12800,23040,25600,28160]:
            for mode in [0,0x10,1,2]:
                cases.append((5,mode,current,25600,0,1,life,0,1))
    for _ in range(768):
        cases.append((rng.randrange(0,201),rng.choice([0,0x10,1,2]),rng.randrange(0,31000),
                      rng.choice([23040,25600,28160]),rng.randrange(4),rng.randrange(2),
                      rng.randrange(0,201),rng.randrange(-30,101),rng.randrange(2)))
    baseline=len(cases)
    # Both seats can select either fighter and an independent spirit. Exercise
    # every pairing while varying rage, weapon flags and life boundary buckets.
    combinations=[(c,s,d,t) for c in (0,1) for d in (0,1) for s in range(6) for t in range(6)]
    for match in combinations*5:
        cases.append((rng.choice([5,9,21,65]),rng.choice([0,1,2,16,17]),rng.randrange(1,28161),
                      25600,rng.randrange(4),rng.randrange(2),rng.choice([0,19,20,199,200]),0,rng.randrange(2)))
    for index,row in enumerate(cases):
        ids=(0,0,0,0) if index<baseline else combinations[(index-baseline)%len(combinations)]
        auxiliary,mode,current,maximum,rage,armed,life,adjust,target_armed=row
        probe.memory[source:source+0x2000]=bytes(0x2000)
        for offset,v in [(0xa10,ids[0]),(0x10c,ids[1]),(0x134,current),(0x138,maximum),(0x120,rage),(0x23c,0x1000 if armed else 0)]:
            probe.write(source+offset,v,4)
        for offset,v in [(0xa10,ids[2]),(0x10c,ids[3]),(0xa30,life),(0xa50,adjust),(0x23c,0x1000 if target_armed else 0)]:
            probe.write(target+offset,v,4)
        _,steps1=probe.run(0x1a3c18,[auxiliary,source,target,mode])
        intermediate=probe.floats[0]
        probe.floats[12]=intermediate
        result,steps2=probe.run(0x1a3f90,[source,target])
        max_steps=max(max_steps,steps1+steps2)
        commands.append('matchup '+' '.join(map(str,ids+row)))
        expected.append([intermediate,signed(result,32)])
    contact_count=0
    for _ in range(768):
        auxiliary,guard=rng.randrange(0,201),rng.randrange(2)
        current,maximum,rage=rng.randrange(0,31000),rng.choice([25600,28160]),rng.randrange(3)
        flags,strength=0x1000|rng.choice([0,0x40000000]),rng.randrange(3)
        life,target_rage,amount=rng.randrange(0,201),rng.randrange(3),rng.randrange(0,0xb801)
        decay,tc,tm,tflags=rng.randrange(200),rng.randrange(31000),25600,rng.choice([0,8,0x10008])
        probe.memory[source:source+0x2000]=bytes(0x2000)
        for off,v in [(0x134,current),(0x138,maximum),(0x120,rage),(0x23c,flags),
                      (0x194,1),(0x19a,[0,2,4][strength])]: probe.write(source+off,v,4 if off!=0x19a else 1)
        for off,v in [(0xa30,life),(0x23c,0x1000),(0x120,target_rage),(0x124,amount),
                      (0x128,decay),(0x134,tc),(0x138,tm),(0x248,tflags)]: probe.write(target+off,v,4)
        result,steps=probe.run(0x1a41b8,[auxiliary,source,target,0x10 if guard else 0])
        max_steps=max(max_steps,steps)
        commands.append('contact '+' '.join(map(str,[auxiliary,guard,current,maximum,rage,flags,strength,
                                                     life,target_rage,amount,decay,tc,tm,tflags])))
        expected.append([signed(result,32),probe.read(source+0x134,4),probe.read(source+0x23c,4)]+
                        [probe.read(target+o,4) for o in [0x120,0x124,0x128,0x134,0x138,0x248]])
        contact_count+=1
    result=subprocess.run([str(binary),str(ROOT/'work/ss6/extracted/resources')],
                          input='\n'.join(commands)+'\n',text=True,capture_output=True,check=True)
    actual=[list(map(int,line.split())) for line in result.stdout.splitlines()]
    assert len(actual)==len(expected),(len(actual),len(expected))
    for i,(a,e) in enumerate(zip(actual,expected)):
        assert a==e,(i,commands[i],a,e)
    # Existing strict fixtures must continue to reject inexact arithmetic.
    strict=Probe(raw)
    try: strict.put_exact_float(0,0.1)
    except NotImplementedError: pass
    else: raise AssertionError('Default exact-only probe accepted inexact input')
    report=dict(elf_sha256=SOURCE_HASH,native_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
        scalar_cases=scalar_count,matchup_cases=len(cases)-baseline,original_damage_function_cases=len(cases),original_contact_meter_cases=contact_count,
        max_original_steps=max_steps,
        model='finite RZ, one alignment guard bit, RZ multiplication/division',
        scope='0x1a3c18 + 0x1a3f90 + ordinary 0x1a41b8; damage for both seats with resources 00/01 and six factory spirits, meter contacts for 00/Rage; no patched instructions or call hooks',
        limitations=['EE hardware MUL low-bit behavior is not modeled; DIV hardware accuracy is not established.',
                     'No real-console reference; these checks validate the port under an explicit shared FP model.',
                     'Specials with scripted damage overrides, CPU modifiers and damage-to-life commit are not covered.'],
        status='passed_under_explicit_model')
    (OUT/'damage_validation.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))

if __name__=='__main__': main()
