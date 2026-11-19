#!/usr/bin/env python3
"""Compare Shin's directional E actions with the complete Japanese input and actor callbacks."""
from concurrent.futures import ProcessPoolExecutor
import json
import os
from pathlib import Path
import subprocess

from validate_dash_motion import ASSETS, ELF, PIN, ROOT, digest
from validate_weapon_handling import setup
from validate_haohmaru_special import ContactOracle
from validate_collisions import ACTORS

EXE=ROOT/'work/ss6/build-native/ss6-match-replay'
OUT=ROOT/'outputs/ss6-feasibility/shin_evasion_validation.json'
# Original standing selector prioritizes diagonal rolls and prone before its
# ordinary E fallback. All these aliases still consult the command permissions.
MOVES={'forward-roll':(3,57,62),'back-roll':(1,58,64),'prone':(2,56,60),
       'low-evade':(4,60,66),'neutral-E':(5,60,66),'forward-E':(6,60,66),'up-E':(8,60,66)}


def replay(slot,system,segments):
    args=[EXE,ASSETS,'--mode','versus',f'--p{slot+1}-spirit',system,'--whirlwind-fields']
    data=''.join(f'{n} {a} {b}\n' for n,a,b in segments)
    result=subprocess.run(args,input=data,text=True,capture_output=True)
    if result.returncode:raise RuntimeError(result.stderr)
    return [r.split() for r in result.stdout.splitlines()]


def setup_state(source,system,held,row,slot,bare):
    p,a,o=source.p,source.a,source.o
    p.write(a+0x10c,system,4)
    source.run(0x179258,a+0x2c4,a+0x10c)
    p.write(a+0x23c,int(row[28+26*slot]),4)
    if bare:
        p.write(a+0xa3c,1,4)
        source.run(0x149918,a);source.run(0x11d8e0,o)
    p.write(o+0x40,int(row[23+26*slot]),4)
    p.write(o+0x1040,int(row[23+26*(1-slot)]),4)
    p.write(o+0x38,int(row[25+26*slot]),4)
    source.previous=held


def case(args):
    slot,name,bare,system=args
    front,back=(128,64) if slot==0 else (64,128)
    pair=lambda a,b:(b,a) if slot else (a,b)
    direction,state,action=MOVES[name]
    move={1:32|back,2:32,3:32|front,4:back,5:0,6:front,8:16}[direction]
    spacing=pair(front,back) if name=='back-roll' else pair(back,front)
    initial=[(500,0,0),(14,*spacing),(8,0,0)]
    if bare:initial.extend([(1,*pair(front|8,0)),(135,0,0)])
    controls=[move|4096]+[0]*46
    rows=replay(slot,system,initial+[(1,*pair(bits,0)) for bits in controls])[len(initial)-1:]
    src,_=setup(slot)
    setup_state(src,int(system=='shin'),0,rows[0],slot,bare)
    col=23+26*slot
    cb=88+27*slot
    seen=[]
    if system=='rage':
        controls=controls[:4]
    for tick,(mask,old,now) in enumerate(zip(controls,rows,rows[1:])):
        v=src.frame(mask)
        core=3+10*slot
        got=[int(now[core])|(int(now[core+1])<<16),int(now[core+2]),int(now[core+3]),int(now[col+1]),int(now[col+10]),int(now[col+5])&0x1018]
        want=[v[0],v[54],v[55],v[69],v[4],v[5]&0x1018]
        if system=='shin':
            got += [int(now[col]),int(now[cb+11]),*map(int,now[cb:cb+3])]
            want += [v[68],v[56],*v[12:15]]
        assert got==want,(args,tick,[(i,a,b) for i,(a,b) in enumerate(zip(got,want)) if a!=b],now[:23])
        record=(v[0]>>16,v[54],v[12])
        if not seen or record!=seen[-1][1]:seen.append((tick,record))
        if system=='shin' and tick>0 and v[0]==0 and v[54]==int(bare):break
    if system=='shin':
        assert seen[0][1][0:2]==(state,action+bare) and seen[-1][1][:2]==(0,int(bare)),(args,seen)
    else:assert all(s[1][0] not in (56,57,58,60) for s in seen)
    return dict(player=slot+1,move=name,armed=not bare,system=system,
                frames=tick+1,state_action_callback=seen,original_instructions=src.instructions)



class ShinContactOracle(ContactOracle):
    def __init__(self, defender):
        super().__init__()
        self.defender=defender

    def install_player(self,row,slot):
        super().install_player(row,slot)
        self.probe.write(ACTORS+slot*0xf2c+0x10c,int(slot==self.defender),4)


def under_attack(args):
    slot,name,attack,delay=args
    front,back=(128,64) if slot==0 else (64,128)
    pair=lambda a,b:(b,a) if slot else (a,b)
    directions={'standing':0,'prone':32,'forward-roll':front|32,'back-roll':back|32,'low-evade':back}
    dodge=directions[name]|(4096 if name!='standing' else 0)
    commands=[(500,0,0),(42,*pair(front,back)),(8,0,0)]
    commands += [(1,*pair(dodge if i==delay else 0,attack if i==0 else 0)) for i in range(75)]
    rows=replay(slot,'shin',commands)
    hits=ShinContactOracle(slot).contacts(rows,1-slot)
    assert len(hits)==int(rows[-1][10+10*(1-slot)])
    return dict(defender=slot+1,evade=name,opponent_pad=attack,evade_delay=delay,
                contacts=hits,final_life=int(rows[-1][9+10*slot]))


def full_gauge(args):
    slot,bare=args
    front,back=(128,64) if slot==0 else (64,128)
    pair=lambda a,b:(b,a) if slot else (a,b)
    commands=[(500,0,0)]
    if bare:commands += [(1,*pair(front|8,0)),(135,0,0)]
    # The opponent advances before each slash so knockback does not turn a
    # later hit into a whiff. Every meter increase is earned in the match.
    for slash in range(4):
        commands += [(60,*pair(0,back)),(8,0,0),(1,*pair(0,1024))]+[(1,0,0)]*(200 if slash==3 else 150)
    rows=replay(slot,'shin',commands)
    base,col,cb=3+10*slot,23+26*slot,88+27*slot
    start=next(i for i,r in enumerate(rows) if r[base:base+2]==['0','63'])
    prev=rows[start-1]
    assert int(prev[col+16])==1 and not int(prev[col+8])&2
    src,_=setup(slot)
    setup_state(src,1,0,prev,slot,bare)
    p,a=src.p,src.a
    p.write(a+0x248,int(prev[col+8]),4)
    p.write(a+0x120,1,4)
    p.write(a+0xa30,int(prev[9+10*slot]),4)
    visited=[]
    for tick,now in enumerate(rows[start:start+100]):
        v=src.frame(0)
        want=[v[0],v[54],v[55],v[56],*v[12:15],v[7]&2]
        got=[int(now[base])|(int(now[base+1])<<16),int(now[base+2]),int(now[base+3]),
             int(now[cb+11]),*map(int,now[cb:cb+3]),int(now[col+8])&2]
        assert got==want,(slot,bare,tick,got,want)
        if v[54] not in visited:visited.append(v[54])
        if tick and v[0]==0 and v[54]!=162+bare:break
    assert len(visited)==2 and visited[0]==162+bare and tick==83,(args,visited,tick)
    return dict(player=slot+1,armed=not bare,entered=int(rows[start][0]),finished=int(now[0]),
                steps=41,actions=visited,opponent_hits=int(rows[start][10+10*(1-slot)]),
                original_instructions=src.instructions)

def main():
    assert digest(ELF)==PIN
    raw=ELF.read_bytes();menu={}
    for offset,text in ((0x4e36f8,'真スピリッツ'),(0x4e3770,'前転'),(0x4e3778,'I3PLIE'),
                        (0x4e3780,'後転'),(0x4e3790,'伏せ'),(0x4e37a0,'下段避け'),
                        (0x4e37b8,'ぬいぐるみ'),(0x4e3850,'秘奥義'),(0x4e38e0,'武器破壊技')):
        assert raw[offset:offset+len(text.encode('cp932'))]==text.encode('cp932')
        menu[hex(offset)]=text
    events=[(s,n,b,'shin') for s in range(2) for n in MOVES for b in ((False,True) if n in list(MOVES)[:4] else (False,))]
    events +=[(s,n,False,'rage') for s in range(2) for n in list(MOVES)[:4]]
    contexts=[(side,defender,attack,delay) for side in range(2)
              for defender in ('standing','forward-roll','back-roll','prone','low-evade')
              for attack,delay in ((1024,0),(1024,12),(1056,0),(2080,0))]
    with ProcessPoolExecutor(max_workers=min(6,os.cpu_count() or 1)) as pool:
        results=list(pool.map(case,events))
        gauge=list(pool.map(full_gauge,[(i,b) for i in range(2) for b in (False,True)]))
        fighting=list(pool.map(under_attack,contexts))
    for row in fighting:
        if row['evade']=='standing':assert row['contacts']
    for side in (1,2):
        for name in list(MOVES)[:4]:
            reached={bool(r['contacts']) for r in fighting if r['evade']==name and r['defender']==side}
            assert reached=={False,True},(side,name,reached)
    report=dict(status='passed',elf_sha256=PIN,replay_sha256=digest(EXE),validator_sha256=digest(Path(__file__)),
                scope='Japanese menu and original 179258 input definitions, real submitted pads and 149xxx actor routines, both players, armed/unarmed maneuvers. Compare 60 Hz state, ACT, clock, exact X/Y movement, callbacks and natural recovery. Held-free direction aliases and system0 rejection. Compare 1536e8/1544a0/155850 and actual damage/guard handlers using the prior production pose for each close-contact scenario. Full Shin meter earned through four heavy slashes, then original 149980 and the state63 actor callback iterate until the next idle ACT.',
                menu=menu,evasions=results,full_meter=gauge,attack_interactions=fighting)
    OUT.write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n')
    print(f'{len(results)} input paths, {len(gauge)} full gauge activations and {len(fighting)} original collision comparisons passed')


if __name__=='__main__':main()
