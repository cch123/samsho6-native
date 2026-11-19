#!/usr/bin/env python3
"""Compare native defense decisions and consumption helpers to original EE code.

Runs whole original helper functions without code patches or call interception.
No claim is made about completing the downstream damage/effect dispatcher.
"""
import hashlib
import json
import random
import struct
import subprocess
from pathlib import Path
from mips_probe import Probe, signed
from extract_collision_tables import SOURCE_HASH

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'outputs/ss6-feasibility'
ASSETS=ROOT/'work/ss6/extracted/resources'
ACTORS=0x1c00000
OBJECTS=[0x1e00000,0x1e01000]
EVENT=0x1b00000
FIELDS=['src104','src108','flags23c','flags244','table','state','stateFlags','a20','c8','field3c0','field39c','field398','system','descriptor']

def main():
    elf=(ROOT/'work/ss6/extracted/SLPS_255.59').read_bytes()
    assert hashlib.sha256(elf).hexdigest()==SOURCE_HASH
    p=Probe(elf);p.write(0x4d3d08,ACTORS,4)
    for slot,obj in enumerate(OBJECTS):
        p.write(obj+0xc,slot,4);p.write(obj+0xcc,slot,4);p.write(ACTORS+slot*0xf2c,obj,4)
    p.write(EVENT+0x40,OBJECTS[0],4);p.write(EVENT+0x68,OBJECTS[1],4)
    lines=[];expected=[];labels=[];returns={}
    def defense(**values):
        f=dict(src104=0,src108=0,flags23c=0x1000,flags244=0,table=0,state=0,stateFlags=0,
               a20=0,c8=0,field3c0=0,field39c=0,field398=0,system=0,descriptor=0)
        f.update(values)
        target=ACTORS+0xf2c
        p.write(OBJECTS[0]+0x104,f['src104'],4);p.write(OBJECTS[0]+0x108,f['src108'],4)
        for offset,key in [(0x23c,'flags23c'),(0x244,'flags244'),(0xa20,'a20'),(0xc8,'c8'),
                           (0x3c0,'field3c0'),(0x39c,'field39c'),(0x398,'field398'),(0x10c,'system')]:
            p.write(target+offset,f[key],4)
        p.write(target+0x194,f['table'],2);p.write(target+0x196,f['state'],2);p.write(target+0x19a,f['stateFlags'],1)
        # The game's dynamic system-6 descriptor lookup is executed, not
        # replaced by a stub. Vary its real selected slot and player index.
        slot=len(lines)%8;owner=len(lines)%2
        p.write(0x4c38a8,6,4);p.write(target+0x110,owner,4);p.write(target+0x118,slot,4)
        p.write(0x12d2308+(owner*8+slot)*16+12,f['descriptor'],1)
        result,_=p.run(0x155850,[EVENT])
        returns[result]=returns.get(result,0)+1
        lines.append('defense '+' '.join(str(f[key]) for key in FIELDS));expected.append([result]);labels.append(f)

    for table in [-1,0,1,2,3]:
        for state in [-32768,-1,*range(64),32767]:
            for attack in [0,4,8,12]:
                for flags in [0,128]: defense(table=table,state=state,src108=attack,stateFlags=flags)
    matrix_cases=len(lines)
    for state in [0,1,2,3,4,5,6,8]:
        for a20 in [0,1,2]:
            for c8 in [0,35,36,37,38]:
                for field in [-1,0,1]: defense(table=2,state=state,a20=a20,c8=c8,field3c0=field)
    table2_cases=len(lines)-matrix_cases
    for system in range(9):
        for state in [0,6,7,8,47,53]:
            for descriptor in [0,39,40,41,255]: defense(system=system,state=state,descriptor=descriptor)
    system_cases=len(lines)-matrix_cases-table2_cases
    rng=random.Random(0x155850)
    for _ in range(2048):
        defense(table=rng.choice([0,0,0,1,2,2,3]),state=rng.choice([0,1,3,5,6,7,8,11,13,47,53,63]),
                src104=rng.choice([0,0x08000000]),src108=rng.randrange(16),flags23c=rng.choice([0,0x10,0x1000,0x1010]),
                flags244=rng.choice([0,0,0x80000]),stateFlags=rng.randrange(256),
                a20=rng.choice([0,1,2]),c8=rng.choice([0,36,37]),field3c0=rng.choice([0,1,-1]),
                field39c=rng.choice([0,0,1,-1]),field398=rng.choice([0,0,1,-1]),
                system=rng.randrange(9),descriptor=rng.choice([0,40,255]))
    defense_cases=len(lines)
    for kind in [0,1,2,5,9]:
        for index in range(-1,8):
            for byte in [0,1,2,3,4,8,0x55,0xaa,0xff]:
                for flag in [0,0x80]:
                    flags104=rng.getrandbits(32);flags108=rng.getrandbits(32)&~0x80|flag
                    obj=OBJECTS[0];p.write(obj+0xcc,kind,4);p.write(obj+0x100,byte,1)
                    p.write(obj+0x104,flags104,4);p.write(obj+0x108,flags108,4)
                    result,_=p.run(0x154a88,[EVENT+0x1c,index])
                    p.run(0x154ac0,[EVENT+0x1c,index])
                    lines.append(f'marks {kind} {flags104} {flags108} {byte} {index}')
                    expected.append([result,p.read(obj+0x100,1),p.read(obj+0x104,4),p.read(obj+0x108,4)])
                    labels.append(lines[-1])
    mark_cases=len(lines)-defense_cases
    decision_cases=0
    # Integrate the separately executed original helpers in dispatcher order.
    # This does not execute the downstream route-7 handler or logger.
    for state in [0,6,7,8]:
      for flags in [0,0x02000000,0x04000000,0x08000000]:
        for a_byte,b_byte in [(0,0),(1,0),(0,2),(2,1)]:
            a,b=OBJECTS
            p.write(a+0xcc,0,4);p.write(b+0xcc,1,4)
            p.write(a+0x100,a_byte,1);p.write(b+0x100,b_byte,1)
            p.write(a+0x104,flags,4);p.write(a+0x108,0,4)
            target=ACTORS+0xf2c
            for offset in [0x244,0x194,0x19a,0xa20,0xc8,0x3c0,0x39c,0x398,0x10c]: p.write(target+offset,0,4)
            p.write(target+0x23c,0x1000,4);p.write(target+0x196,state,2)
            consumedA,_=p.run(0x154a88,[EVENT+0x1c,0]);consumedB,_=p.run(0x154a88,[EVENT+0x44,1])
            defense_value=0
            if consumedA or consumedB: kind=1
            elif flags&0x06000000: kind=2
            else:
                defense_value,_=p.run(0x155850,[EVENT]);kind=4 if defense_value else 3
            lines.append(f'decision 7 {a_byte} {b_byte} {flags} 0 4096 0 0 {state} 0 0 0 0 0 0 0 0')
            expected.append([kind,defense_value,a_byte,b_byte]);labels.append(lines[-1]);decision_cases+=1
    for route in range(12):
        expected.append([signed(p.read(0x4d89c0+route*8+i*4,4),32) for i in range(2)])
        lines.append('indices '+str(route));labels.append(lines[-1])
    registry_cases=0;registry_submissions=0
    for trial in range(48):
        calls=[];want=[]
        p.run(0x153440)
        count=162 if trial==0 else 40
        for i in range(count):
            identity=i if trial==0 else rng.randrange(8)
            character=rng.choice([0,39]);action=rng.choice([0,185,208,*range(209,220),0xffffffff])
            flags=rng.getrandbits(32)&~0x00400000 if trial==0 else rng.getrandbits(32)
            byte=rng.randrange(256);reset=int(trial!=0 and i%13==0)
            if reset: p.run(0x153440)
            obj=0x1800000+identity*0x200
            p.write(obj+0x14,character,4);p.write(obj+0x24,action,4)
            p.write(obj+0x104,flags,4);p.write(obj+0x100,byte,1)
            before=p.read(0x12d2408,4)
            p.run(0x153450,[obj])
            after=p.read(0x12d2408,4)
            calls.extend([reset,identity,character,action,flags,byte])
            want.extend([int(after>before),p.read(obj+0x100,1),p.read(obj+0x104,4),after])
            registry_submissions+=1
        n=p.read(0x12d2408,4)
        want.append(n);want.extend((p.read(0x12d2410+i*4,4)-0x1800000)//0x200 for i in range(n))
        lines.append('registry '+str(count)+' '+' '.join(map(str,calls)));expected.append(want);labels.append(f'registry {trial}')
        registry_cases+=1
    binary=ROOT/'work/ss6/build-native/ss6-combat-probe'
    result=subprocess.run([str(binary),str(ASSETS)],input='\n'.join(lines)+'\n',capture_output=True,text=True,check=True)
    rows=result.stdout.splitlines();assert len(rows)==len(expected)
    for row,want,label in zip(rows,expected,labels):
        got=list(map(int,row.split()));assert got==want,(label,got,want)
    # Missing descriptor and alternate-state inputs must never silently use
    # the ordinary branch in a caller that has not ported those producers.
    for line in ['defense 0 0 4096 0 0 6 0 0 0 0 0 0 6 -1',
                 'defense 0 0 2097152 0 0 0 0 0 0 0 0 0 0 0']:
        r=subprocess.run([str(binary),str(ASSETS)],input=line+'\n',capture_output=True,text=True)
        assert r.returncode!=0
    report=dict(all_passed=True,elf_sha256=SOURCE_HASH,native_probe_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
        defense_cases=defense_cases,state_matrix_cases=matrix_cases,table2_cases=table2_cases,system_cases=system_cases,
        random_cases=2048,consumption_cases=mark_cases,decision_composition_cases=decision_cases,consumption_table_routes=12,
        registry_sequences=registry_cases,registry_submissions=registry_submissions,total_cases=len(lines),defense_returns=returns,
        original_functions=['0x155850','0x154a88','0x154ac0','0x153440','0x153450'],
        scope='Whole defense selector on ordinary actor state snapshots, system-6 descriptor lookup, consumption helpers and collision-object registration lifecycle. No downstream damage, gauge, reaction, hitstop or effect execution.')
    (OUT/'combat_decision_validation.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))

if __name__=='__main__': main()
