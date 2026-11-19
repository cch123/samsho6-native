#!/usr/bin/env python3
"""Compare resource00 projectile candidates and pre-dispatch decisions with the Japanese ELF."""
from collections import Counter
import itertools
import argparse
import json
from pathlib import Path
import struct
import subprocess

from mips_probe import Probe
from round_entry_oracle import buffered_stdout
from validate_collisions import ACTORS,OBJECTS,QUEUE,encoded,install,player,read_events
from validate_jump_motion import ASSETS,ELF,ORIGINAL,ROOT,WORK,digest


def compare(binary,commands,expected,labels):
    exe=PROBE_DIR/binary
    proc=subprocess.run([exe,ASSETS],input='\n'.join(commands)+'\n',text=True,capture_output=True)
    assert proc.returncode==0,(proc.stderr,len(proc.stdout.splitlines()))
    rows=[list(map(int,row.split())) for row in proc.stdout.splitlines()]
    assert len(rows)==len(expected)
    for i,(got,want) in enumerate(zip(rows,expected)):
        assert got==want,(i,labels[i],got,want)
    return digest(exe)


def candidate_matrix():
    p=Probe(ELF.read_bytes())
    p.write(0x4d3d08,ACTORS,4);p.write(0x4d89b8,QUEUE,4)
    banks={id:[(ASSETS/f'{bank}_{id:02}.bin').read_bytes() for bank in ('aid','act','jdg')] for id in (0,1,51)}
    def records(action,id=0):
        aid,act,jdg=banks[id]
        start=struct.unpack_from('<h',aid,2*action)[0]
        for frame in range(aid[4096+action]):
            off=60*(start+frame)
            flags=struct.unpack_from('<H',act,off+30)[0]
            refs=struct.unpack_from('<8h',act,off+14)[:flags&7]
            jud=[[ref,*struct.unpack_from('<I5h',jdg,ref*16)] for ref in refs]
            yield frame,flags,jud
    commands=[];expected=[];labels=[]
    counts=Counter();real_routes=Counter();actual_types=set();actual_directions=Counter()
    def body(owner,kind,refs,x,mirror,descriptor=0):
        flags,jud=refs
        f=player(owner,jud,x,mirror)
        f.update(kind=kind,d0=descriptor,judgmentFlags=flags,stateFlags=4)
        return f
    def run(a,b,label,live=False):
        halves=[]
        for i,obj in enumerate([a,b]):
            install(p,i,obj)
            p.write(OBJECTS[i]+0xcc,obj['kind'],4);p.write(OBJECTS[i]+0xd0,obj['d0'],4)
            desc=p.read(0x4e4b38+12*obj['d0']+10,1) if obj['d0']>=0 else 0
            profile=51 if obj['kind']==5 else int(label[0]=='eagle' and obj['kind']==3)
            p.write(OBJECTS[i]+0x18,profile,4)
            halves.append(f"{profile} {obj['kind']} {obj['d0']} {desc} {encoded(obj)}")
        p.write(0x12d2698,0,4)
        for pair in [OBJECTS,OBJECTS[::-1]]:
            _,n=p.run(0x1536e8,pair,limit=50000);counts['instructions']+=n
        _,n=p.run(0x1544a0,limit=50000);counts['instructions']+=n
        result=read_events(p)
        for i in range(result[0]):
            event=result[1+26*i:27+26*i]
            if live:
                route=event[0];real_routes[route]+=1
                source=(a,b)[event[15]];target=(a,b)[event[25]]
                actual_directions[f"{source['kind']}->{target['kind']}/route{route}"]+=1
                if source['kind']==2:
                    assert event[3]==0
                    actual_types.add(event[7])
        commands.append('pair-profile 1 1 '+' '.join(halves))
        expected.append(result);labels.append(label)
    # Cover every record, including inactive startup and ending records. Mirror
    # both directions; compare all decoded fields, rectangle edges, and queue order.
    for action in (532,533,534,535,538):
        for i,flags,boxes in records(action):
            for other,other_frame,distance,height in [(0,0,12,0),(189,5,44,0),(211,6,-16,56)]:
                _,of,ob=list(records(other))[other_frame]
                for side in (0,1):
                    a=body(side,2,(flags,boxes),-12.5,side)
                    b=body(1-side,1-side,(of,ob),-12.5+(1-2*side)*distance,1-side)
                    b.update(y=height,actorFlags=0x1010 if height else 0x1000)
                    run(a,b,('record',action,i,other,side),True)
    # Real opposing projectiles, including non-overlap and crossing positions.
    for a,b,gap in itertools.product((532,533,534), (532,533,534),(-64,-8,0,8,28,64)):
        _,af,aj=list(records(a))[5];_,bf,bj=list(records(b))[5]
        run(body(0,2,(af,aj),0,0),body(1,2,(bf,bj),gap,1),('clash',a,b,gap),True)
    # The companion stays registered while idle. Four of its real ACTs have
    # boxes, including the distinct capture judgment in 779.
    for action in range(769,788):
        for i,flags,boxes in records(action,1):
            for side in (0,1):
                _,of,ob=next(records(0))
                run(body(side,3,(flags,boxes),0,side),body(1-side,1-side,(of,ob),8,1-side),('eagle',action,i,side))
    # Scene items use resident resource 51 even when the fighter owns their
    # task. Test each flight and the bomb's floor/air explosion against the
    # actual idle, crouching and airborne hurt boxes on both sides.
    item_cases=0
    for action,descriptor in [(55,110),(56,110),(73,109),(78,110)]+[(82+5*n,111+n) for n in range(10)]:
        for i,flags,boxes in records(action,51):
            for opponent,dx,dy in ((0,0,0),(4,18,0),(14,8,35)):
                _,of,ob=next(records(opponent))
                for side in (0,1):
                    a=body(side,5,(flags,boxes),0,side,descriptor)
                    b=body(1-side,1-side,(of,ob),dx if side==0 else -dx,1-side)
                    b['y']=dy
                    run(a,b,('stage-item',action,i,opponent,side),True)
                    item_cases+=1
    real_cases=len(commands)
    # Route and descriptor boundaries with literal JDG words, including class4
    # projectiles and body-only checks. The actual blast has class2 and D0=0.
    table=(ASSETS/'collision_00.bin').read_bytes()
    raw_by_class={}
    for raw in range(64):
        cls=table[raw*2 if raw<36 else 396+(raw-36)*2]
        if cls<18:raw_by_class.setdefault(cls,raw)
    for i,((ak,bk),at,bt) in enumerate(itertools.product(((0,2),(2,1),(2,2),(3,1),(0,3),(3,2),(2,3),(3,3)),raw_by_class.values(),raw_by_class.values())):
        aj=[[1,at<<26|0x238200,-7,-20,-20,20,20]]
        bj=[[2,bt<<26|0x123401,5,-20,-20,20,20]]
        d0=(-1,0,1,0xaa,0xb4)[i%5]
        a=body(0,ak,(1,aj),0,0,d0);b=body(1,bk,(1,bj),8,1,d0)
        run(a,b,('classes',ak,bk,at,bt,d0))
    for kind_pair,source_cls,u in itertools.product(((0,2),(2,1),(2,2)),(2,4),range(32)):
        ak,bk=kind_pair
        js=lambda raw,low:[[0,raw<<26|low,0,-8,-8,8,8]]
        a=body(0,ak,(1,js(raw_by_class[source_cls],0)),0,0)
        b=body(1,bk,(1,js(1,2 if u&4 else 0)),1,1)
        b.update(table=2 if u&1 else 0,state=11,field1c8=1 if u&2 else 0,actorFlags=0x1010 if u&8 else 0x1000)
        a.update(actorFlags=(0x200400 if ak==2 else 0x400) if u&16 else 0x1000)
        run(a,b,('branch',kind_pair,source_cls,u))
    assert actual_types=={36,37,38} and real_routes[7] and set(real_routes)=={7},(actual_types,real_routes)
    return dict(real_record_pairs=real_cases,common_item_pairs=item_cases,branch_cases=len(commands)-real_cases,real_routes=real_routes,
                kinds_and_routes=actual_directions,original_instructions=counts['instructions'],
                native_sha256=compare('ss6-collision-probe',commands,expected,labels))


def dispatch_matrix():
    p=Probe(ELF.read_bytes(),finite_model=True)
    buffered_stdout(p)
    p.write(0x4d3d08,ACTORS,4);p.write(QUEUE+0x40,OBJECTS[0],4);p.write(QUEUE+0x68,OBJECTS[1],4)
    for i,obj in enumerate(OBJECTS):
        p.write(obj+0xc,i,4);p.write(ACTORS+i*0xf2c,obj,4);p.write(obj+0x24,532+i,4)
    commits,expected,labels=[],[],[];branches=Counter();instructions=0
    def case(route,ak,bk,same,block,src108,sm,tm,pa,pb,table,state,state_flags,f398,f39c):
        nonlocal instructions
        a,b=OBJECTS;t=ACTORS+0xf2c
        for obj,kind,owner,pause,consumed in [(a,ak,0,pa,sm),(b,bk,1-int(same),pb,tm)]:
            p.write(obj+0xcc,kind,4);p.write(obj+0x10,owner,4);p.write(obj+0xfc,pause,1);p.write(obj+0x100,consumed,1)
            for off,val in [(0xdc,7),(0xe4,5),(0xe8,9)]:p.write(obj+off,val,4)
        p.write(a+0x104,block,4);p.write(a+0x108,src108,4);p.write(QUEUE,route,4)
        for off,val in [(0x23c,0x1000),(0x244,0),(0x398,f398),(0x39c,f39c)]:p.write(t+off,val,4)
        p.write(t+0x194,table,2);p.write(t+0x196,state,2);p.write(t+0x19a,state_flags,1)
        seen=set()
        # Run the complete 155850 defense selector and observe the selected hit
        # or guard producer at its call boundary. Particle/SE dispatch is a
        # separate subsystem; include the real 2-tick freeze writes before it.
        _,n=p.run(0x156820,[QUEUE],limit=50000,observe=seen.add,
                  stop_before=[0x155a88,0x155d50,0x157f80,0x155780,0x155078,0x156ca8])
        instructions+=n
        kind=choice=pause=0
        if 0x156bd4 in seen:kind=1
        elif 0x156b54 in seen:kind=1;choice=p.registers[6]
        elif 0x156a54 in seen:
            kind=2
            if 0x156a80 in seen:
                pause=1
                for obj in OBJECTS:
                    assert [p.read(obj+off,4) for off in (0xdc,0xe4,0xe8)]==[512,0,0] and p.read(obj+0xfc,1)==2
        elif 0x156880 in seen:kind=3
        elif 0x156ac8 in seen:kind=4
        elif 0x156970 in seen:kind=5
        bits=p.read(b+0x100,1)
        args=(route,ak,bk,0,1-int(same),block,src108,sm,tm,pa,pb,table,state,state_flags,f398,f39c)
        commits.append('projectile '+' '.join(map(str,args)))
        expected.append([kind,choice,bits,pause]);labels.append(args);branches[kind]+=1
    pairs=((0,2),(2,1),(2,2),(3,1),(0,3),(3,2),(2,3),(3,3),(0,5),(5,1),(2,5),(5,2),(5,5))
    for route,(ak,bk),same,flag in itertools.product((1,2,3,4,5,7,9),pairs,(False,True),(0,0x2000000,0x4000000)):
        # The collision collector admits reflection on projectiles and common items.
        if route==5 and bk not in (2,5):continue
        case(route,ak,bk,same,flag,0,3,0x11,0,0,0,0,0,0,0)
    for pa,pb,consumed in itertools.product((0,1,2),(0,1,2),(0,1,2,0xfe)):
        case(7,2,2,False,0,0,3,consumed,pa,pb,0,0,0,0,0)
    for state,attack_bits,consumed in itertools.product((0,6,7,8,47,53),(0,4,8,12),(0,3,0xff)):
        case(7,2,1,False,0,attack_bits,consumed,consumed,2,2,0,state,0,0,0)
    for table,state,f398,f39c in itertools.product((0,1,2),(0,3,6,8),(0,1),(0,1)):
        case(7,2,0,False,0,0,1,2,0,0,table,state,0x80,f398,f39c)
    assert all(branches[i] for i in range(6)),branches
    assert [p.run(0x1690b0,[0,action])[0] for action in (532,533,534)]==[0,0,0]
    return dict(cases=len(commits),branches=branches,original_instructions=instructions,
                native_sha256=compare('ss6-combat-probe',commits,expected,labels))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--probe-dir',type=Path,default=WORK/'build-native')
    PROBE_DIR=parser.parse_args().probe_dir
    assert digest(ELF)==ORIGINAL
    report=dict(status='passed',original_elf_sha256=ORIGINAL,geometry=candidate_matrix(),dispatch=dispatch_matrix(),
                validator_sha256=digest(Path(__file__)),
                scope='Complete original 1536e8 and 1544a0 on paired snapshots. Real ACT532–535/538 vs '
                      'idle, ground and jumping heavy; real 01 companion ACT769..787, 51 stage-item flight and explosions, and mixed auxiliary pairings. Original 156820 '
                      'through the 155a88/155d50 boundary includes whole 155850; mutual projectile '
                      'pre-handler through 157f80 includes original freeze writes. Damage, effect '
                      'allocation, sprite drawing and projectile callback lifetimes are separate.')
    (ROOT/'outputs/ss6-feasibility/projectile_contact_validation.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
