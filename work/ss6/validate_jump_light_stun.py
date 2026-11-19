#!/usr/bin/env python3
"""Compare jump-light contact, hurt playback and first available inputs with the original ELF."""
from concurrent.futures import ProcessPoolExecutor
import argparse
import itertools
import json
from pathlib import Path
import struct
import subprocess

from round_entry_oracle import fixture
from validate_jump_motion import ROOT,WORK,ASSETS,ELF,ORIGINAL,digest
from validate_haohmaru_special import ContactOracle
from validate_collisions import ACTORS,OBJECTS,QUEUE
from validate_input_features import PADS
from validate_input_lifecycle import Boundary

EXE=WORK/'build-native/ss6-match-replay'
def native(slot,posture,reply,jump):
    forward=(128,64)[slot];victim_forward=forward^192
    diagonal=jump=='forward'
    attack=({'stand':31,'crouch':33,'air':19} if diagonal else {'stand':29,'crouch':31,'air':19})[posture]
    contact=({'stand':42,'crouch':44,'air':30} if diagonal else {'stand':42,'crouch':44,'air':32})[posture]
    commands=['500 0 0'];defender_pad=[0]
    if not diagonal:commands.append(f'43 {forward} 0' if slot==0 else f'43 0 {forward}')
    for tick in range(1,contact+81):
        a=(16|(forward if diagonal else 0)) if tick==1 else 256 if tick==attack+1 else 0
        d=(32 if posture=='crouch' else 16 if posture=='air' and tick==1 else 0)
        if tick>=contact:
            d={'idle':0,'walk':victim_forward,'guard':forward,
               'attack0':256 if (tick-contact)%2==0 else 0,
               'attack1':256 if (tick-contact)%2==1 else 0}[reply]
        defender_pad.append(d)
        commands.append(f'1 {a} {d}' if slot==0 else f'1 {d} {a}')
    proc=subprocess.run([EXE,ASSETS,'--mode','versus','--whirlwind-fields'],input='\n'.join(commands)+'\n',capture_output=True,text=True,check=True)
    rows=[row.split() for row in proc.stdout.splitlines()]
    if not diagonal:rows=rows[1:]
    hit=next(i for i,row in enumerate(rows) if int(row[10+10*slot]))
    assert hit==contact and int(rows[hit][19-10*slot])==191,(slot,posture,reply,jump,hit)
    return rows,defender_pad,hit


def original_contact(rows,hit,attacker):
    oracle=ContactOracle();p=oracle.probe
    # Replay source geometry up to and including the actual first impact.
    instructions=0
    for tick,row in enumerate(rows[:hit],1):
        oracle.install_player(row,0);oracle.install_player(row,1)
        p.write(0x12d2698,0,4)
        for pair in (OBJECTS,OBJECTS[::-1]):
            _,n=p.run(0x1536e8,pair,limit=50000);instructions+=n
        _,n=p.run(0x1544a0,limit=50000);instructions+=n
        for k in range(p.read(0x12d2698,4)):
            e=QUEUE+108*k
            if p.read(e,4)!=7 or p.read(e+0x40,4)!=OBJECTS[attacker]:continue
            assert tick==hit and p.read(e+0x20,4)==10 and p.read(e+12,4)==0
            assert p.run(0x155850,[e])[0]==0
            boundary=Boundary(0x155bb8)
            _,n=p.run(0x155a88,[e,1],stop_before=boundary,limit=250000);instructions+=n
            assert boundary.stopped==0x155bb8
            target=ACTORS+(1-attacker)*0xf2c
            part=p.run(0x153140,[e+0x48])[0]
            special=p.run(0x157fa8,[target,e+0x48])[0]
            base=ACTORS+attacker*0xf2c
            timers=tuple(p.read(actor+off,4) for actor in (base,target) for off in (0x1b0,0x1b4))
            return part,special,p.read(target+0x192,2),timers,instructions
    raise AssertionError('missing original hit')


def run_case(args):
    attacker,posture,reply,jump=args
    rows,held,hit=native(*args)
    part,special,state,initial_timers,ins=original_contact(rows,hit,attacker)
    slot=1-attacker
    p,a,o,b=fixture(slot);p.finite_model=True
    oth=ACTORS+attacker*0xf2c;ob=o+0x1000
    def call(pc,*args,stop=()):
        nonlocal ins
        value,n=p.run(pc,args,limit=350000,stop_before=stop);ins+=n
        return value
    def until(start,end):
        boundary=Boundary(end);call(start,stop=boundary);assert boundary.stopped==end
    aid=(ASSETS/'aid_00.bin').read_bytes()
    p.memory[0x46a9b0+0x1800:0x46a9b0+0x1800+len(aid)]=aid
    p.write(0x4751b4,p.read(0x4751b0,4),4)
    p.write(oth,ob,4);p.write(oth+4,o+0x2000,4);p.write(oth+0xa24,attacker,4)
    p.write(b+0x24c+4*attacker,oth,4);p.write(ob+0xcc,attacker,4);p.write(ob+0xc,attacker,4)
    p.write(a+4,o+0x3000,4);p.write(o+0x30c4,-1,4);p.write(o+0xc,slot,4)
    call(0x149008,a,0);call(0x149918,a);call(0x11d8e0,o);call(0x179258,a+0x2c4,a+0x10c)
    p.write(0x4c38a8,0,4);p.write(b,4,4);p.write(b+0x144,160,4)
    for which in range(2):
        struct.pack_into('<8I',p.memory,0x4eaac0+which*32,*(1<<(8+i) for i in range(8)))
    def opponent(row):
        i=attacker;n=23+26*i
        p.write(oth+0x194,int(row[3+10*i])|(int(row[4+10*i])<<16),4)
        for off,j in ((0x23c,5),(0x240,6),(0x244,7),(0x248,8)):
            p.write(oth+off,int(row[n+j]),4)
        p.write(oth+0x19a,int(row[n+10]),1);p.write(oth+0x24c,int(row[n+9]),1)
        for off,j in ((0x40,n),(0x44,n+1),(0x38,n+2),(0x104,n+3),(0x108,n+4),
                      (0x24,5+10*i),(0x28,6+10*i)):
            p.write(ob+off,int(row[j]),4)
    def projection():
        return (p.read(a+0x194,4),p.read(o+0x24,4),p.read(o+0x28,4),
                p.read(a+0x1b0,4),p.read(a+0x1b4,4),p.read(oth+0x1b0,4),p.read(oth+0x1b4,4))
    def native_fields(row):
        base=3+10*slot;ts=96+27*slot;ss=96+27*attacker
        return (int(row[base])|int(row[base+1])<<16,int(row[base+2]),int(row[base+3]),
                *map(int,row[ts:ts+2]),*map(int,row[ss:ss+2]))
    active=0
    checks=[];choices=[]
    # This event asks 155850 whether a guardable slash would be defended on
    # this exact update; polling covers the landing frame before walking starts.
    sample=0x1bb0000;p.write(sample+0x40,ob,4);p.write(sample+0x68,o,4)
    # The round has already opened. Use the displayed stage X / facing at
    # its update boundary; input, vertical motion, callbacks and hurt clocks
    # evolve in the original actor continuously from the same control inputs.
    for i in range(1,len(rows)):
        prev,now=rows[i-1],rows[i]
        opponent(prev)
        s=23+26*slot
        p.write(o+0x40,int(prev[s]),4)
        p.write(o+0x38,(p.read(o+0x38,4)&~0x80000)|(int(prev[s+2])&0x80000),4)
        if i==hit:
            call(0x14d198,a,ob,0,10,part,special)
            assert p.read(a+0x192,2)==state
            assert tuple(p.read(actor+off,4) for actor in (oth,a) for off in (0x1b0,0x1b4))==initial_timers
            p.write(a+0xa38,9,4)
        p.put(16,b+4*slot);p.put(17,3);p.put(19,0x140000);until(0x142580,0x142618)
        call(0x11d730,o);call(0x11d6c8,o)
        # Position/orientation from the stage pass supplies opponent distance
        # and side tests without emulating the camera or opponent's input.
        p.write(o+0x40,int(now[s]),4)
        p.write(a+0xa08,int(float(now[7+10*slot])>float(now[7+10*attacker])),4)
        p.write(ob+0x40,int(now[23+26*attacker]),4)
        p.put(11,o);p.put(14,ob);p.put(18,b);until(0x1428f4,0x142918)
        for actor,body in ((a,o),(oth,ob)):
            delta=128 if p.read(actor+0x1b4,4) else 256
            p.write(actor+0x1ac,delta,4);p.write(body+0x30,delta,4)
        call(0x151b00,a);call(0x151eb0,a);call(0x151968,a)
        call(0x151eb0,oth)
        pad=PADS+12*slot
        p.write(pad,held[i],4);p.write(pad+4,held[i]&~held[i-1],4)
        if slot==1:opponent(now)
        p.put(16,1);p.put(17,a);p.put(18,oth);until(0x1495e8,0x149770)
        call(0x149d08,a);p.put(17,a);p.write(0x1fff038,0x1ffff00,8)
        call(0x149790);call(0x149918,a);call(0x11d8e0,o)
        if i<hit:continue
        want=projection();got=native_fields(now)
        assert got==want,(args,i-hit,got,want)
        active+=1
        if reply=='guard':
            oracle_choice=call(0x155850,sample)
            choices.append(oracle_choice)
            source_col=23+26*attacker
            cols=(int(now[source_col+3]),int(now[source_col+4]),int(now[s+5]),int(now[s+7]),
                  int(now[3+10*slot]),int(now[4+10*slot]),int(now[s+10]),0,int(now[s+12]),
                  int(now[s+13]),int(now[s+14]),int(now[s+15]),0,0)
            checks.append('defense '+' '.join(map(str,cols)))
        # Once control returns, movement/attacks can produce a new collision
        # unrelated to the first hit. Stop after observing the requested input.
        if reply.startswith('attack') and want[0]&0xffff==1:break
        if reply in ('walk','guard') and want[0] in (2<<16,3<<16):break
        if reply=='idle' and want[1]==0:break
    else:raise AssertionError((args,'requested control never returned'))
    guard_tick=None
    if checks:
        result=subprocess.run([WORK/'build-native/ss6-combat-probe',ASSETS],input='\n'.join(checks)+'\n',capture_output=True,text=True,check=True)
        assert list(map(int,result.stdout.split()))==choices,(args,choices,result.stdout)
        guard_tick=next(j for j,value in enumerate(choices) if value)
    final=next(i for i in range(hit,len(rows)) if (int(rows[i][3+10*slot])!=2))
    return dict(attacker=attacker,posture=posture,reply=reply,jump=jump,contact=hit,reaction=state,
                initial_timers=list(initial_timers),hurt_exits=final-hit,
                response=i-hit,first_guard_probe=guard_tick,matched_updates=active,original_instructions=ins)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--one',nargs=4)
    args=parser.parse_args()
    assert digest(ELF)==ORIGINAL
    if args.one:print(run_case((int(args.one[0]),*args.one[1:])))
    else:
        jobs=list(itertools.product((0,1),('stand','crouch','air'),('idle','walk','guard','attack0','attack1'),('forward','vertical')))
        with ProcessPoolExecutor(max_workers=4) as pool:cases=list(pool.map(run_case,jobs))
        report=dict(status='passed',original_elf_sha256=ORIGINAL,native_sha256=digest(EXE),
                    validator_sha256=digest(Path(__file__)),cases=cases,
                    original_instructions=sum(c['original_instructions'] for c in cases),
                    scope='Whole original collector/ordering/defense and hit handler up to post-reaction metadata '
                          'on native pre-impact geometry. Original defender actor and its raw software input '
                          'before and after impact, including full 149d08 and timer passes. Stage X/facing and '
                          'opponent snapshots supplied at their scheduler boundaries. Matched post-hit actor '
                          'state, ACT, record, and source/target timer0/1 until neutral, walk, block input or attack.')
        (ROOT/'outputs/ss6-feasibility/jump_light_stun_validation.json').write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps(report,indent=2))
