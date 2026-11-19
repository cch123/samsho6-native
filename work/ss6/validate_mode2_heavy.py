#!/usr/bin/env python3
"""Contrast the PS2 VS menu's submode 2 with the fixed-match submode 0 on heavy attacks."""
from concurrent.futures import ProcessPoolExecutor
import json
import subprocess

from validate_dash_motion import ASSETS, ELF, PIN, PROBE, ROOT, Original, check_native, digest
from validate_haohmaru_special import ContactOracle
from mips_probe import Probe
from validate_versus_result import G, Original as PageOracle

REPORT=ROOT/'outputs/ss6-feasibility/versus_mode2_heavy_comparison.json'

def actor(args):
    side,name=args
    f=(128,64)[side]
    start={'standing':[0,1024], 'crouching':[32,32|1024], 'vertical':[16]+[0]*6+[1024],
           'diagonal':[16|f]+[0]*6+[1024], 'running':[0,f,0]+[f]*14+[f|1024]}[name]
    masks=start+[0]*80
    traces=[];commands=[f'reset {side} {side} {500 if side else 120} {120 if side else 500}','combat']
    for mode in (0,2):
        o=Original(side)
        o.p.write(G+0xa0,mode,4)
        trace=[]
        for held in masks:
            if mode==0:commands.append(f'pad {held} {held & ~o.previous}')
            trace.append(o.frame(held))
        traces.append(trace)
    assert traces[0]==traces[1],(side,name)
    check_native(PROBE,({'player':side,'case':name},commands,traces[1]))
    actions=sorted({r[54] for r in traces[1]})
    expected={'standing':190,'crouching':196,'vertical':211,'diagonal':214,'running':221}[name]
    assert expected in actions and traces[1][-1][54]==0,(name,actions)
    return dict(player=side,move=name,frames=len(masks),compared_actor_object_and_command_fields=len(traces[0][0]),actions=actions)

def contacts(side,guard):
    f,b=(128,64) if side==0 else (64,128)
    pads=[(0,0)]*500+[(f,b)]*35+[(0,0)]*3+[(1024, f if guard else 0)]+[(0,f if guard else 0)]*87
    if side:pads=[(v,u) for u,v in pads]
    inputs=''.join(f'1 {u} {v}\n' for u,v in pads)
    result=subprocess.run([PROBE.with_name('ss6-match-replay'),ASSETS,'--contact-fields'],
                          input=inputs,text=True,capture_output=True,check=True)
    # The collector oracle checks adjacent combat snapshots. Include the
    # opening only in the native replay; the last five neutral rows seed it.
    rows=[line.split() for line in result.stdout.splitlines()][493:]
    hits=[]
    for mode in (0,2):
        o=ContactOracle()
        o.probe.write(G+0xa0,mode,4)
        hits.append(o.contacts(rows,side))
    assert len(hits[0])==1 and hits[0]==hits[1] and bool(hits[0][0]['defense'])==guard
    return dict(player=side,guard=guard,contact=hits[0][0])

def score():
    snapshots={}
    for mode in (0,2):
        o=PageOracle()
        p=o.p
        states=[]
        for win in (0,0,1,-1):
            p.write(G,3,4);p.write(G+8,win,4);p.write(G+0xa0,mode,4);p.write(G+16,1,4);p.write(G+20,0,4)
            o.run(0x124da0)
            states.append(dict(winner=win,game_mode=p.read(G,4),streak=p.read(G+0x38,4),last_entrant=p.read(G+16,4),
                               p1=[p.read(G-16+i,4) for i in (0,4)],p2=[p.read(G-8+i,4) for i in (0,4)]))
        snapshots[mode]=states
    assert snapshots[0][0]['game_mode']==1 and snapshots[2][0]['game_mode']==3
    assert snapshots[2][-1]['p1']!=snapshots[0][-1]['p1']
    return snapshots

def rounds():
    p=Probe(ELF.read_bytes())
    battle,base=0x1b00000,0x1c00000
    p.write(0x4d3d00,battle,4);p.write(0x4d3d08,base,4);p.write(G,3,4)
    trials=[]
    for win,wins in ((0,[1,0]),(1,[0,1]),(-1,[1,1]),(0,[2,0]),(1,[0,2]),(-1,[2,2])):
        pairs=[]
        for submode in (0,2):
            p.write(G+0xa0,submode,4)
            for where,value in ((0,8),(0x18,7),(0x20,win==-1),(0x24,win)):
                p.write(battle+where,value,4)
            for i in range(2):
                a=base+0xf2c*i
                p.write(battle+0x24c+4*i,a,4)
                p.write(a,0x1e00000+i*0x1000,4)
                p.write(a+0xa24,i,4);p.write(a+0x244,0x40000000,4)
                p.write(battle+0x254+0x108*i+0x28,wins[i],4);p.write(battle+0x254+0x108*i+0x2c,2,4)
            p.run(0x144570,(battle,))
            pairs.append([p.read(battle,4),p.read(battle+0x11c,4)//256])
        assert pairs[0]==pairs[1]
        assert pairs[0][0]==(10 if max(wins)==2 else 0)
        trials.append(dict(winner=win,score=wins,next_battle_state=pairs[0][0],wait=pairs[0][1]))
    return trials

def main():
    assert digest(ELF)==PIN
    with ProcessPoolExecutor(4) as pool:
        cases=list(pool.map(actor,((i,k) for i in range(2) for k in ('standing','crouching','vertical','diagonal','running'))))
    hit=[contacts(i,g) for i in range(2) for g in (False,True)]
    report=dict(elf_sha256=PIN,scope='Match gameMode 3, Haohmaru/system 0. Original actor and command logic changes only gameData+A0 between 0 and 2. Both compared against the same native actor runtime. Standing contact cases use both original collectors and hit/guard callbacks on externally supplied native combat snapshots. The PS2 versus screen/whole match is not emulated.',
                actor_cases=cases,contacts=hit,round_transitions=rounds(),score_cases=score(),mode2_menu='1cd3e4 dispatches character select in gameMode 6; 1cd404 publishes submode 2. The two-human battle runs in gameMode 3. 1434d0 invokes 1daec0, original postmatch choices are CHARACTER SELECT / CONTINUE / RETURN TO TITLE. The fixed preview instead runs submode0. Neither an original BIOS session nor the menu/AI/handicap/stage/audio paths are compared.')
    REPORT.write_text(json.dumps(report,indent=2)+'\n')
    print(len(cases),'dual-mode actor paths;',sum(r['frames'] for r in cases),'ticks;',len(hit),'contacts; mode-specific scoring')

if __name__=='__main__':
    main()
