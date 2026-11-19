#!/usr/bin/env python3
"""Compare heavy blade intersections with the original collector and exercise live recoveries."""
from collections import Counter
import itertools
import json
from pathlib import Path
import struct
import subprocess

from mips_probe import Probe
from validate_collisions import ACTORS,OBJECTS,QUEUE,encoded,install,player,read_events
from validate_jump_motion import ASSETS,ELF,ORIGINAL,ROOT,WORK,digest

def collect():
    p=Probe(ELF.read_bytes())
    p.write(0x4d3d08,ACTORS,4)
    p.write(0x4d89b8,QUEUE,4)
    aid=(ASSETS/'aid_00.bin').read_bytes()
    act=(ASSETS/'act_00.bin').read_bytes()
    jdg=(ASSETS/'jdg_00.bin').read_bytes()
    def boxes(id,step):
        off=(struct.unpack_from('<h',aid,id*2)[0]+step)*60
        flags=struct.unpack_from('<H',act,off+30)[0]
        refs=struct.unpack_from('<8h',act,off+14)[:flags&7]
        return flags,[[r,*struct.unpack_from('<I5h',jdg,16*r)] for r in refs]
    def fighter(slot,id,step,x,y):
        flags,js=boxes(id,step)
        air=id in (211,214)
        f=player(slot,js,x,slot)
        f.update(judgmentFlags=flags,y=y,table=1,state={211:10,214:11,189:8}[id],
                 stateFlags=12,actorFlags=0x1000|(0x30 if air else 0))
        return f
    for id in (211,214):
        # Only the armed ground heavy has a raw-33 pre-attack blade. The air
        # heavy's two active rectangles are both damage type 12.
        sequence=[[j[1]>>26 for j in boxes(id,step)[1]] for step in range(aid[4096+id])]
        assert all(33 not in frame for frame in sequence)
        assert [(i,frame.count(12)) for i,frame in enumerate(sequence) if 12 in frame]==[(6,2)]
    lines=[];expected=[]
    counts={'ground':Counter(),'air':Counter()}
    instructions=0
    for (a,ai),(b,bi),gap in itertools.product(((211,6),(214,6),(189,3),(189,5)),
            ((211,6),(214,6),(189,3),(189,5)),range(0,181,10)):
        airborne=a!=189 or b!=189
        left=fighter(0,a,ai,240,64 if a!=189 else 0)
        right=fighter(1,b,bi,240+gap,64 if b!=189 else 0)
        install(p,0,left);install(p,1,right);p.write(0x12d2698,0,4)
        for args in (OBJECTS,OBJECTS[::-1]):
            _,n=p.run(0x1536e8,args,limit=50000);instructions+=n
        _,n=p.run(0x1544a0,limit=50000);instructions+=n
        event=read_events(p)
        routes=event[1::26]
        if airborne:assert 8 not in routes and 9 not in routes,(a,b,gap,routes)
        counts['air' if airborne else 'ground'].update(routes)
        expected.append(event)
        lines.append(f'pair 1 1 {encoded(left)} {encoded(right)}')
    exe=WORK/'build-native/ss6-collision-probe'
    result=subprocess.run([exe,ASSETS],input='\n'.join(lines)+'\n',text=True,capture_output=True,check=True)
    assert [list(map(int,l.split())) for l in result.stdout.splitlines()]==expected
    assert counts['ground'][8] and counts['ground'][9] and counts['air'][7]
    return dict(cases=len(lines),routes=counts,instructions=instructions,native_sha256=digest(exe))

def lock_gate():
    p=Probe(ELF.read_bytes())
    battle=0x1b00000
    p.write(0x4d3d00,battle,4)
    cases=0
    for mode,option,raw,flags in itertools.product((2,3),(0,3),(0,9,10,11,12),range(4)):
        p.write(0x123a0c0,mode,1)
        p.write(battle+0x138,flags,4)
        p.write(battle+0x13c,option,4)
        p.write(battle+0x114,raw*(0xb400 if mode==2 else 0x5a00),4)
        value,_=p.run(0x140678)
        assert value==int(not(flags&2) and (option==3 or raw>=11))
        cases+=1
    return cases

def replays():
    exe=WORK/'build-native/ss6-match-replay'
    def run(pads):
        commands=['500 0 0']+[f'1 {p0} {p1}' for p0,p1 in pads]
        result=subprocess.run([exe,ASSETS],input='\n'.join(commands)+'\n',text=True,capture_output=True,check=True)
        return [line.split() for line in result.stdout.splitlines()]
    result=[]
    for swift,back in itertools.product((0,1),(False,True)):
        forward=(0x80,0x40)[swift]
        pads=[]
        for tick in range(170):
            hit=forward if tick in (0,2,3,4) else forward|0x400 if tick==5 else 0
            recovery=(0x1000|(forward if back else 0)) if tick==67 else 0
            pads.append((hit,recovery) if swift==0 else (recovery,hit))
        rows=run(pads)
        a,b=3+10*swift,3+10*(1-swift)
        chosen=76 if back else 70
        assert [int(row[b+2]) for row in rows if int(row[b+2]) in (70,76)][0]==chosen
        assert rows[-1][b+2]=='0' and int(rows[-1][b+6])==175 and int(rows[-1][a+7])==1
        assert any(int(row[a+2])==221 and int(row[b+2])==382 for row in rows)
        first=next(int(row[0]) for row in rows if int(row[b+2])==chosen)
        result.append(dict(attacker=swift,roll=chosen,first_tick=first,defender_hp=int(rows[-1][b+6])))
    for advance in (False,True):
        pads=[((0x90 if advance else 0x10),(0x50 if advance else 0x10)) if i==0 else
              (1024,1024) if i==6 else (0,0) for i in range(150)]
        rows=run(pads)
        assert all(int(r[5]) not in (137,138,139,140,141,142,143) and
                   int(r[15]) not in (137,138,139,140,141,142,143) for r in rows)
        health=172 if advance else 200
        assert int(rows[-1][9])==int(rows[-1][19])==health and rows[-1][5]==rows[-1][15]=='0'
        result.append(dict(jump='forward' if advance else 'vertical',both_hp=health,
                           air_hurt=any(r[5]==r[15]=='378' for r in rows)))
    return result,digest(exe)

if __name__=='__main__':
    assert digest(ELF)==ORIGINAL
    matrix=collect()
    matches,binary=replays()
    report=dict(status='passed',elf_sha256=ORIGINAL,collision=matrix,lock_gate_cases=lock_gate(),
                match_native_sha256=binary,native_replays=matches,validator_sha256=digest(Path(__file__)),
                scope='Resource00 armed system0, original whole collector in both directions and event sort '
                      'over real ground/air heavy rectangles. Original time and one-lock-per-match gate. '
                      'Separate native replays cover simultaneous jumping heavies, bilateral hurt and whiff, '
                      'and both manual rolls after a live running heavy knockdown.')
    (ROOT/'outputs/ss6-feasibility/heavy_weapon_contact_validation.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
