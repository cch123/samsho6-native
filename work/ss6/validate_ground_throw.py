#!/usr/bin/env python3
"""Compare the thrower's original pad, ACT and callbacks with live two-player round replays."""
from concurrent.futures import ProcessPoolExecutor
import collections
import itertools
import json
import shutil
import struct
import subprocess
import tempfile
from pathlib import Path
from validate_dash_motion import ASSETS, ELF, Original, PIN, ROOT, digest
from validate_haohmaru_special import ContactOracle
from validate_collisions import ACTORS, OBJECTS, QUEUE
from validate_input_lifecycle import Boundary

MATCH=ROOT/'work/ss6/build-native/ss6-match-replay'

def pad_case(slot,kind):
    forward=(128,64)[slot];back=forward^192
    chord=0x600
    direction=back if kind=='back' else forward if kind=='forward' else 0
    close=kind not in ('miss','shortcut','stagger','back-miss')
    inputs=[(chord|(back if kind=='back-miss' else direction),chord if kind=='break' else 0)]+[(0,0)]*194
    if kind in ('guard','crouch'):
        guard=forward if kind=='guard' else 32
        inputs=[(a,guard if i<9 else 0) for i,(a,b) in enumerate(inputs)]
    if kind=='shortcut':inputs[0]=(0x2000,0)
    if kind=='stagger':inputs[:2]=[(0x200,0),(0x600,0)]
    return (65 if close else 0),inputs

def simulate(args):
    exe,slot,kind=args
    walk,inputs=pad_case(slot,kind)
    def pair(a,b):return (b,a) if slot else (a,b)
    pads=[(500,0,0)]
    if walk:
        response={'guard':(128,64)[slot],'crouch':32,'jump':16}.get(kind,0)
        pads.extend([(walk,*pair((128,64)[slot],0)),(6,*pair(0,response))])
    pads.extend((1,*pair(a,b)) for a,b in inputs)
    raw=subprocess.run([exe,ASSETS,'--whirlwind-fields'],input=''.join(f'{n} {a} {b}\n' for n,a,b in pads),capture_output=True,text=True)
    assert raw.returncode==0,(slot,kind,raw.stderr)
    rows=[r.split() for r in raw.stdout.splitlines()][len(pads)-len(inputs)-1:]
    src=Original(slot);effect_births=[]
    p=src.p
    # ACT232 creates its own world25. Set up the original shared texture/task
    # pools so the whole record-entry function can run during actor playback.
    for fn in (0x1123a8,0x112570,0x11e290):src.run(fn)
    for i in range(32):p.write(0x4c3510+4*i,i+1,4)
    for bank,name in enumerate(('01HitFlash.bin','02Guard.bin','03etc.bin'),1):
        d=(ASSETS/name).read_bytes();base=0x4a4810+(bank-1)*0x3da0;p.memory[base:base+len(d)]=d
    # The lifecycle fixture supplies the already-established stage coordinates.
    # Source action clocks, callback state and input recognition advance in ELF.
    start=23+26*slot;other_start=23+26*(1-slot)
    p.write(src.o+0x40,int(rows[0][start]),4);p.write(src.o+0x1040,int(rows[0][other_start]),4)
    geo=ContactOracle();q=geo.probe;geo_ins=0
    def run_geo(pc,*values,stop=()):
        nonlocal geo_ins
        result,n=q.run(pc,values,limit=500000,stop_before=stop);geo_ins+=n;return result
    for j in range(2):q.write(0x1b80000+0x24c+4*j,ACTORS+j*0xf2c,4)
    def observe(pc):
        if pc==0x124430:effect_births.append([q0 for q0 in (int(p.registers[4]),*p.floats[12:16])])
    def run_actor(address,*values,stops=()):
        _,n=p.run(address,values,limit=2000000,stop_before=stops,observe=observe if address in (0x11d730,0x11d8e0) else None);src.instructions+=n
    src.run=run_actor
    captured=False;checked=0;route_seen=[];after_impact=False;paired_pose=None
    want_actions=[];variants=set()
    for i,(held,other_held) in enumerate(inputs,1):
        before=rows[i-1];now=rows[i];b=3+10*slot
        pc_action=int(before[b+2]);pc_step=int(before[b+3])
        if pc_action==230 and not captured:
            for j in range(2):geo.install_player(before,j)
            q.write(ACTORS+slot*0xf2c+0xa48,p.read(src.a+0xa48,4),4)
            q.write(0x12d2698,0,4)
            for pair0 in (OBJECTS,OBJECTS[::-1]):run_geo(0x1536e8,*pair0)
            run_geo(0x1544a0)
            for rank in range(q.read(0x12d2698,4)):
                event=QUEUE+108*rank;route=q.read(event,4)
                if route not in (0,4):continue
                if route==4 and q.read(event+0x40,4)!=OBJECTS[slot]:continue
                route_seen.append((i,route))
                # The paired victim/contact suite checks the handler's other
                # actor and both positions. Transfer the source request that
                # its actual resolver just produced, never a synthetic action.
                if route==4:run_geo(0x1551c0,event,0)
                else:
                    # The resolver writes both actors before calling its
                    # separate spark scheduler; compare exactly that boundary.
                    end=Boundary(0x1574f0)
                    run_geo(0x1556a8,event,stop=end)
                    assert end.stopped==0x1574f0
                qa=ACTORS+slot*0xf2c
                for off in (0x18c,0x190):p.write(src.a+off,q.read(qa+off,4),4)
                captured=True;break
        if int(now[10+10*slot])>int(before[10+10*slot]):after_impact=True
        # Secondary blade impact has its own real hitstop/RNG/target tests.
        # End continuous thrower comparison immediately before that impact.
        if after_impact:break
        source=src.frame(held);want=int(now[b])|(int(now[b+1])<<16)
        cb=75+27*slot+13
        got=(source[0],source[54],source[55],source[56],*[p.read(src.a+0x260+4*j,4) for j in range(7)])
        expected=(want,int(now[b+2]),int(now[b+3]),int(now[cb+11]),*[int(x) for x in now[cb:cb+7]])
        # The idle loop was already running for 500 updates when this fixture
        # starts. Compare its finally reached state separately from its phase.
        if source[0]==0 and source[54]==0 and i>1:break
        assert got==expected,(slot,kind,i,got,expected)
        if got[4]==0x16b528 and paired_pose is None:
            paired_pose=[p.read(actor+0x23c,4)&0xe0f for actor in (src.a,src.other)]
            actual=[int(now[23+26*side+5])&0xe0f for side in (slot,1-slot)]
            assert paired_pose==actual==[1,0],(slot,kind,i,paired_pose,actual)
        if source[54]==230:variants.add(p.read(src.a+0xa48,4))
        want_actions.append(source[54]);checked+=1
    all_actions=[int(r[5+10*slot]) for r in rows[1:]]
    victim=[int(r[5+10*(1-slot)]) for r in rows[1:]]
    result=dict(slot=slot,case=kind,source_visits=checked,source_instructions=src.instructions,collector_instructions=geo_ins,
                captures=route_seen,variants=sorted(variants),paired_pose=paired_pose,attacker_actions=list(dict.fromkeys(all_actions)),
                defender_actions=list(dict.fromkeys(victim)),defender_life=int(rows[-1][9+10*(1-slot)]),world_effects=effect_births)
    if kind in ('forward','back','neutral','guard','crouch'):
        assert 230 in want_actions and (234 if kind=='back' else 232) in want_actions
        assert captured and route_seen==[(4,4)] and result['defender_life']==186 and (410 if kind=='back' else 408) in victim
        assert paired_pose==[1,0] and result['variants']==[int(kind=='back')] and any(v[0]==25 for v in effect_births)==(kind!='back')
    elif kind=='break':
        assert captured and route_seen[0][1]==0 and 236 in want_actions and 236 in victim and result['defender_life']==200
    elif kind in ('stagger','jump'):
        assert not captured
        if kind=='stagger':
            # The first button already selected medium slash. This particular
            # startup distance is within the reach of its far ACT188.
            assert 188 in all_actions and 230 not in all_actions and result['defender_life']==180
        else:assert 230 in all_actions and result['defender_life']==200
    else:
        assert result['variants']==[int(kind=='back-miss')] and 230 in want_actions and not captured and result['defender_life']==200
    assert all_actions[-1]==0
    return result

def main():
    assert digest(ELF)==PIN
    with tempfile.TemporaryDirectory() as d:
        exe=Path(d)/'match';shutil.copy2(MATCH,exe);kinds=('miss','shortcut','back-miss','stagger','forward','back','neutral','break','guard','crouch','jump')
        with ProcessPoolExecutor(max_workers=4) as workers:results=list(workers.map(simulate,[(exe,s,k) for s,k in itertools.product(range(2),kinds)]))
        report=dict(status='passed',elf_sha256=PIN,native_sha256=digest(exe),validator_sha256=digest(Path(__file__)),cases=results,
                    scope='Two raw-pad players, ordinary system0. Compare source pad acquisition/recognition/actor entry, active ACT step, fractional clock, continuation parameters to real versus until first terminal follow-up or idle. Original 1536e8/1544a0 contacts use positions from live frames. Successful 1551c0 ordinary throw selection runs in ELF. Route0 selection runs through the original call to its spark scheduler. Full native round replays include exit, secondary strike and landing damage.')
    (ROOT/'outputs/ss6-feasibility/ground_throw_validation.json').write_text(json.dumps(report,indent=2)+'\n')
    for r in results:print(r['slot'],r['case'],r['source_visits'],r['captures'],r['attacker_actions'],r['defender_life'])
if __name__=='__main__':main()
