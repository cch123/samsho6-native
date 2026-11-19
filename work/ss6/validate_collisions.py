#!/usr/bin/env python3
"""Execute original contact collection and sorting, compare complete event fields.

The original instructions are neither patched nor hooked. Synthetic player
snapshots cover filtering boundaries; real ACT/JDG records cover asset wiring.
This checks candidate collection, not the later damage/guard dispatcher.
"""
import hashlib
import json
import random
import struct
import subprocess
from pathlib import Path
from mips_probe import Probe, signed, MASK64

ROOT=Path(__file__).resolve().parents[2]
ASSETS=ROOT/'work/ss6/extracted/resources'
OUT=ROOT/'outputs/ss6-feasibility'
OBJECTS=[0x1e00000,0x1e01000]
ACTORS=0x1c00000
QUEUE=0x1b00000

def runner_checks(probe):
    code=0x1d00000
    # Independent byte-copy invariants for every pair of source/target
    # alignments. Event records alternate alignment because sizeof(event)=108.
    for src_align in range(8):
        for dst_align in range(8):
            src,dst=0x1d01000+src_align,0x1d02000+dst_align
            probe.memory[src-8:src+16]=bytes(range(24))
            probe.memory[dst-8:dst+16]=b'\xa5'*24
            words=[(0x1a<<26)|(4<<21)|(8<<16)|7,(0x1b<<26)|(4<<21)|(8<<16),
                   (0x2c<<26)|(5<<21)|(8<<16)|7,(0x2d<<26)|(5<<21)|(8<<16),0x03e00008,0]
            for i,w in enumerate(words): probe.write(code+i*4,w,4)
            probe.run(code,[src,dst])
            assert probe.memory[dst:dst+8]==bytes(range(8,16))
            assert probe.memory[dst-8:dst]==b'\xa5'*8 and probe.memory[dst+8:dst+16]==b'\xa5'*8
    for a,b in [(-13,6),(13,-6),(-13,-6),(127,6),(0,6)]:
        for i,w in enumerate([(4<<21)|(5<<16)|0x1a,0x03e00008,0]): probe.write(code+i*4,w,4)
        probe.run(code,[a&MASK64,b&MASK64])
        q=abs(a)//abs(b)*(-1 if (a<0)!=(b<0) else 1)
        assert signed(probe.lo,64)==q and signed(probe.hi,64)==a-q*b

def player(owner,judgments,x=0,mirror=0):
    return dict(owner=owner,flags104=0,flags108=0,actorFlags=0x1000,table=0,state=0,
                stateFlags=0,field1c8=0,x=x,y=0,mx=mirror,my=0,judgmentFlags=len(judgments),judgments=judgments)

def install(probe,slot,p):
    obj=OBJECTS[slot];actor=ACTORS+slot*0xf2c
    probe.memory[obj:obj+0x200]=bytes(0x200)
    probe.memory[actor:actor+0xf2c]=bytes(0xf2c)
    for offset,value in [(0xc,slot),(0x10,p['owner']),(0x38,(p['mx']<<19)|(p['my']<<18)),
                         (0x104,p['flags104']),(0x108,p['flags108'])]: probe.write(obj+offset,value,4)
    for offset,key in [(0x40,'x'),(0x44,'y')]:
        probe.write(obj+offset,struct.unpack('<I',struct.pack('<f',p[key]))[0],4)
    probe.write(actor,obj,4);probe.write(actor+0x23c,p['actorFlags'],4)
    probe.write(actor+0x194,p['table'],2);probe.write(actor+0x196,p['state'],2)
    probe.write(actor+0x19a,p['stateFlags'],1);probe.write(actor+0x1c8,p['field1c8'],4)
    refs,data=0x1a00000+slot*0x1000,0x1a10000+slot*0x1000
    probe.write(0x4751e0+slot*4,data,4)
    probe.write(obj+0xb8,p['judgmentFlags'],2);probe.write(obj+0xba,len(p['judgments']),1);probe.write(obj+0xbc,refs,4)
    for i,j in enumerate(p['judgments']):
        probe.write(refs+i*2,i,2)
        # j = source record index, metadata, signed auxiliary, four coordinates.
        probe.memory[data+i*16:data+i*16+16]=struct.pack('<I6h',*j[1:],0)

def encoded(p):
    keys=['owner','flags104','flags108','actorFlags','table','state','stateFlags','field1c8','x','y','mx','my','judgmentFlags']
    return ' '.join(map(str,[p[k] for k in keys]+[len(p['judgments'])]+[v for j in p['judgments'] for v in j]))

def read_events(probe):
    count=probe.read(0x12d2698,4);result=[count]
    assert count<=162
    for i in range(count):
        ptr=QUEUE+i*108
        result.extend([probe.read(ptr,4)]+[signed(probe.read(ptr+j*4,4),32) for j in range(1,6)])
        assert probe.read(ptr+24,4)==0
        for offset in [28,68]:
            # Ignore only the two padding bytes after the ACT halfword.
            result.append(probe.read(ptr+offset,2))
            result.extend(probe.read(ptr+offset+4+j*4,4) for j in range(7))
            result.append(probe.read(probe.read(ptr+offset+32,4),1))
            result.append(OBJECTS.index(probe.read(ptr+offset+36,4)))
    return result

def main():
    elf=(ROOT/'work/ss6/extracted/SLPS_255.59').read_bytes()
    probe=Probe(elf);runner_checks(probe)
    probe.write(0x4d3d08,ACTORS,4);probe.write(0x4d89b8,QUEUE,4)
    tables=(ASSETS/'collision_00.bin').read_bytes()
    types=[t for t in range(64) if tables[t*2 if t<36 else 396+(t-36)*2]<18]
    lines=[];expected=[];labels=[];route_counts={}
    def case(a,b,label,both=0,sort=1):
        install(probe,0,a);install(probe,1,b)
        probe.write(0x12d2698,0,4)
        probe.run(0x1536e8,OBJECTS,limit=50000)
        if both: probe.run(0x1536e8,OBJECTS[::-1],limit=50000)
        if sort: probe.run(0x1544a0,limit=50000)
        event=read_events(probe)
        for i in range(event[0]):
            route=event[1+i*26];route_counts[route]=route_counts.get(route,0)+1
        lines.append(f'pair {both} {sort} '+encoded(a)+' '+encoded(b));expected.append(event);labels.append(label)

    # Every defined resource-00 type pair, including type-specific entries.
    for ta in types:
        for tb in types:
            case(player(0,[[0,ta<<26,-5,-20,-20,20,20]]),
                 player(1,[[0,tb<<26,7,-20,-20,20,20]]),f'types {ta},{tb}')
    type_pairs=len(lines)
    rng=random.Random(0x1536e8)
    # Bias toward interacting types, blocked flags, state boundaries, facing,
    # fractional positions, reversed endpoints, and nontrivial metadata.
    for i in range(1536):
        pair=[]
        for slot in range(2):
            js=[]
            for j in range(rng.randint(1,4)):
                t=rng.choice([0,1,2,3,6,7,9,10,16,30,32,33,36,45])
                js.append([j,(t<<26)|rng.getrandbits(26),rng.randint(-32768,32767),
                           *[rng.randint(-40,40) for _ in range(4)]])
            p=player(slot,js,rng.randint(-64,64)/4,rng.randrange(2))
            p.update(y=rng.randint(-32,32)/4,my=rng.randrange(2),stateFlags=rng.randrange(256),
                     flags104=rng.choice([0]*12+[0x00800000,0x01000000,0x02000000,0x04000000]),
                     flags108=rng.choice([0]*8+[1,8,0x01000000]),
                     actorFlags=rng.choice([0x1000]*8+[0,0x400,0x1010]),
                     table=rng.choice([0,1,2]),state=rng.choice([0,9,10,11,12,13]),field1c8=rng.choice([-1,0,1]))
            p['judgmentFlags']|=rng.getrandbits(13)<<3
            pair.append(p)
        if i%37==0: pair[1]['owner']=pair[0]['owner']
        case(*pair,f'random {i}',both=i%2,sort=(i//2)%2)

    aid,act,jdg=[(ASSETS/f'{name}_00.bin').read_bytes() for name in ['aid','act','jdg']]
    def record(action,step):
        start=struct.unpack_from('<h',aid,action*2)[0];offset=(start+step)*60
        flags=struct.unpack_from('<H',act,offset+0x1e)[0]
        refs=struct.unpack_from('<8h',act,offset+0xe)[:flags&7]
        js=[[ref,*struct.unpack_from('<I5h',jdg,ref*16)] for ref in refs]
        return flags,js
    flags,idle=record(0,0)
    real_count=0
    for action in [0,1,10,11,12,13,185,286,287,290,291]:
        for step in range(aid[0x1000+action]):
            af,js=record(action,step)
            for distance in [-120,-64,-32,0,24,48,64,80,96,120]:
                a=player(0,js);a['judgmentFlags']=af
                b=player(1,idle,distance,1);b['judgmentFlags']=flags
                case(a,b,f'action {action} step {step} distance {distance}',both=1)
                real_count+=1

    sort_count=0
    # Repeated priorities expose unstable selection-sort behavior. Include
    # the maximum original capacity and keep identities through each swap.
    for n in [0,1,2,3,8,25,80,162]:
        for _ in range(8):
            routes=[rng.randrange(12) for _ in range(n)]
            probe.write(0x12d2698,n,4)
            for i,route in enumerate(routes):
                probe.write(QUEUE+i*108,route,4);probe.write(QUEUE+i*108+16,i,4)
            probe.run(0x1544a0,limit=500000)
            lines.append('sort '+str(n)+' '+' '.join(map(str,routes)))
            expected.append([probe.read(QUEUE+i*108+16,4) for i in range(n)])
            labels.append(f'sort {n}');sort_count+=1
    binary=ROOT/'work/ss6/build-native/ss6-collision-probe'
    result=subprocess.run([str(binary),str(ASSETS)],input='\n'.join(lines)+'\n',text=True,capture_output=True,check=True)
    rows=result.stdout.splitlines()
    assert len(rows)==len(expected),(len(rows),len(expected))
    for row,want,label in zip(rows,expected,labels):
        got=list(map(int,row.split()))
        assert got==want,(label,got,want)
    # Fail-closed admission checks, separate from original behavior claims.
    p=player(0,[[0,40<<26,0,-1,-1,1,1]]);q=player(1,[[0,0,0,-1,-1,1,1]])
    for change in ['undefined_type','alternate_state']:
        if change=='alternate_state': p['judgments'][0][1]=0;p['actorFlags']|=0x200000
        rejected=subprocess.run([str(binary),str(ASSETS)],input='pair 0 1 '+encoded(p)+' '+encoded(q)+'\n',text=True,capture_output=True)
        assert rejected.returncode!=0,change
    report=dict(all_passed=True,source_elf_sha256=hashlib.sha256(elf).hexdigest(),
                native_probe_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
                type_pair_cases=type_pairs,random_snapshot_cases=1536,real_action_pair_cases=real_count,
                queue_sort_cases=sort_count,total_cases=len(lines),observed_routes=route_counts,
                original_functions=['0x1536e8','0x1544a0'],
                scope='Resource 00, ordinary player objects, non-alternate actor states. Full meaningful candidate event fields and ordering match bounded original instruction execution. No original hardware capture; hit resolution remains unimplemented.')
    (OUT/'collision_validation.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))

if __name__=='__main__': main()
