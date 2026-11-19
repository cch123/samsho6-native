#!/usr/bin/env python3
"""Check throw catch, simultaneous grab, scripted damage and follow-up against the Japanese ELF on actual match geometry."""
import hashlib
import itertools
import json
import struct
import subprocess
from pathlib import Path
from validate_haohmaru_special import ContactOracle
from validate_collisions import ACTORS,ASSETS,OBJECTS,QUEUE,ROOT
from validate_input_lifecycle import Boundary
from extract_collision_tables import SOURCE_HASH

EXE=ROOT/'work/ss6/build-native/ss6-match-replay'
OUT=ROOT/'outputs/ss6-feasibility'
def pads(slot,mode):
    forward=(128,64)[slot]
    variant=forward if mode!='back' else 192^forward
    grab=1536|variant
    approach=70 if mode!='whiff' else 1
    lines=[(500,0,0),(approach,128,0)]
    p=[0,0];p[slot]=grab
    if mode=='mutual':p[1-slot]=1536|(192^forward)
    return lines+[(1,*p),(235,0,0)]

def test(slot,mode):
    commands=pads(slot,mode)
    rows=[]
    for n,a,b in commands:
        if n==235:rows.extend(f'1 {a} {b}' for _ in range(n))
        else:rows.append(f'{n} {a} {b}')
    data=subprocess.run([EXE,ASSETS,'--whirlwind-fields'],input='\n'.join(rows)+'\n',capture_output=True,text=True,check=True)
    rows=[row.split() for row in data.stdout.splitlines()]
    oracle=ContactOracle();p=oracle.probe
    # Original collector fixtures put JDG references in the same area used by
    # buffered_stdout by default. Keep original newlib output away from them.
    reent=p.read(0x5d1bf8,4);stdout=p.read(reent+8,4)
    p.write(stdout,0x19e0000,4);p.write(stdout+16,0x19e0000,4)
    total=0
    def run(pc,*args,stop=()):
        nonlocal total
        v,n=p.run(pc,args,limit=300000,stop_before=stop);total+=n
        return v
    victim=1-slot
    live=lambda row,i:tuple(map(int,row[3+10*i:6+10*i]))
    events=[];direct=[];falls=[];transitions=[];last=None
    for step in range(2,len(rows)):
        prev,now=rows[step-1:step+1]
        frame=int(now[0]);old_life=int(prev[9+10*victim]);hp=int(now[9+10*victim])
        for i in range(2):
            oracle.install_player(prev,i)
            p.write(ACTORS+0xf2c*i+0xa48,int(mode=='back'),4)
        old_record=prev[5+10*slot:7+10*slot]
        record_enter=old_record!=rows[step-2][5+10*slot:7+10*slot]
        if record_enter:
            act,rec=map(int,old_record)
            start=struct.unpack_from('<h',oracle.aid,2*act)[0]
            base=oracle.act[60*(start+rec)+2]
            p.write(OBJECTS[slot]+0xd8,base,4)
        else:base=0
        run(0x154120,OBJECTS[slot])
        if base:
            assert p.read(OBJECTS[slot]+0xd8,4)==0
            direct.append(dict(frame=frame,base=base,damage=p.read(ACTORS+victim*0xf2c+0xa38,4)))
        p.write(0x12d2698,0,4)
        for pair in (OBJECTS,OBJECTS[::-1]):run(0x1536e8,*pair)
        run(0x1544a0)
        for k in range(p.read(0x12d2698,4)):
            e=QUEUE+108*k;route=p.read(e,4)
            if route not in (0,4,7):continue
            src=OBJECTS.index(p.read(e+0x40,4));dst=1-src
            if any(run(0x154a88,e+off,p.read(0x4d89c0+route*8+4*j,4)) for j,off in enumerate((0x1c,0x44))):continue
            if route==0:
                boundary=Boundary(0x1574f0)
                run(0x1556a8,e,stop=boundary)
                assert boundary.stopped==0x1574f0 and p.registers[5]==7
                assert all(live(now,i)==(0,37,236) for i in range(2))
            elif route==4:
                assert src==slot
                run(0x1551c0,e)
                assert (p.read(ACTORS+0xf2c*slot+0x190,4),p.read(ACTORS+0xf2c*victim+0x190,4))==(31<<16|1,13<<16|2)
                assert live(now,src)==(1,31,232+2*(mode=='back')) and live(now,dst)==(2,13,404+2*(mode=='back'))
            else:
                if p.read(OBJECTS[src]+0x104,4)&0x06000000:continue
                assert src==slot and run(0x155850,e)==0
                boundary=Boundary(0x155bb8)
                run(0x155a88,e,0,stop=boundary)
                assert boundary.stopped==0x155bb8
                state=p.read(ACTORS+dst*0xf2c+0x192,2)
                assert live(now,dst)[:2]==(2,state)
                assert int(now[10+10*src])==int(prev[10+10*src])+1
                falls.append(dict(frame=frame,reaction=state,raw=p.read(e+0x20,4)))
            events.append(dict(frame=frame,route=route,source=src,raw=p.read(e+0x20,4)))
            break
        pending=p.read(ACTORS+victim*0xf2c+0xa38,4)
        assert old_life-pending==hp,(slot,mode,frame,pending,old_life,hp)
        pair=(live(now,slot),live(now,victim))
        if pair!=last:
            transitions.append(dict(frame=frame,thrower=pair[0],victim=pair[1],hp=hp))
            last=pair
    final_life=int(rows[-1][9+10*victim])
    assert all(live(rows[-1],i)==(0,0,0) for i in range(2))
    if mode in ('forward','back'):
        assert [v['route'] for v in events]==[4,7] and len(direct)==1 and final_life==186,(events,direct,final_life)
        assert any(v['victim']==(2,16,48) for v in transitions)
    elif mode=='whiff':assert not events and not direct and final_life==200
    else:assert [v['route'] for v in events]==[0] and not direct and final_life==200
    return dict(player=slot+1,variant=mode,contacts=events,record_damage=direct,release=falls,final_life=final_life,
                snapshots=len(rows)-2,original_instructions=total,inputs=commands,transitions=transitions)

if __name__=='__main__':
    assert hashlib.sha256((ASSETS.parent/'SLPS_255.59').read_bytes()).hexdigest()==SOURCE_HASH
    cases=[test(slot,mode) for slot,mode in itertools.product(range(2),('forward','back','whiff','mutual'))]
    for mode in ('forward','back','mutual'):
        (OUT/f'ground-throw-{mode}.replay').write_text(''.join(f'{n} {a} {b}\n' for n,a,b in pads(0,mode)))
    report=dict(status='passed',elf_sha256=SOURCE_HASH,cases=cases,snapshots=sum(c['snapshots'] for c in cases),
                original_instructions=sum(c['original_instructions'] for c in cases),
                scope='Armed Haohmaru mirror, system 0, default duel. Native normal input through both characters returning to standing. Each published pair of ACT/JDG and coordinate snapshots feeds original 1536e8 and 1544a0. The original capture and record-damage routines execute in full; the release hit executes through 155bb8 prior to graphics, and the mutual grab through the call to spark 7. Compares accepted contacts, life on every tick, and resulting state. Other modes, roles and independent full-battle CPU execution are outside this fixture.')
    (OUT/'ground_throw_match_validation.json').write_text(json.dumps(report,indent=2)+'\n')
    print([(c['player'],c['variant'],c['contacts'],c['record_damage'],c['final_life']) for c in cases])
