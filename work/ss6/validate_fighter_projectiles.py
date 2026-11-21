#!/usr/bin/env python3
"""Compare a fighter's live descriptor projectiles with SLPS_255.59.

Parameterized form of validate_mina_projectiles.py: --fighter N, every
generic probe motion (probe_fighter_gaps.MOTIONS) in both seats.

Every bow normal and arrow special is entered through public pad input from
the selection screen, for both seats. Each native call of 16def0, 16cac0 or
the group-17 chain is replayed on the original executable with the same 80
object words, task callback, owner flags and arrow counter, then all words
are compared. The 0x51 counter spawn (16d2b0 inside 16def0) is excluded and
reported separately because its allocation is outside this unit fixture.
"""
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
import json
import os
from pathlib import Path
import struct
import subprocess
import tempfile

from character_tiles_oracle import ROOT,ASSETS,fixture
from validate_mamahaha import BATTLE,ACTORS,BODY,TASK
from validate_selected_combat import prefix,BUILD,substitute_env
from extract_collision_tables import SOURCE_HASH

OBJECT=0xb10000
from probe_fighter_gaps import pads as move_pads, MOTIONS, PLAYABLE, slot_pads, slot_selection
SLOT_RUNS=[]
import argparse
FIGHTER=None

def pads(seat,move):
    seq=prefix((0,FIGHTER) if seat else (FIGHTER,0))+[[0,0]]*330
    return seq+[[0,x] if seat else [x,0] for x in move_pads(seat,move)]

def original(seat,expected,counts):
    lineup=(0,FIGHTER,51) if seat else (FIGHTER,0,51)
    p=fixture(lineup);p.write(0x4d3d00,BATTLE,4);p.write(0x4d3d08,ACTORS,4);p.write(TASK+28,OBJECT,4)
    stage,_=p.run(0x140040)
    act=p.read(0x4751b0+4*seat,4)
    actor=ACTORS+seat*0xf2c
    p.write(actor,BODY,4);p.write(actor+0xa24,seat,4);p.write(actor+0xa10,FIGHTER,4)
    p.write(actor+4,BODY+0x2000,4)
    wrong=[]
    for case,before,after,owner in expected:
        handler,words,flags,f17,left,right,top,c128=before
        b38,b40,b44,s194,a3c,c0,c1,c5,r18c,ox,oy,osys,ostate,f244,c3,h0,h1,h2,ot20,pend=owner[:20]
        p.write(actor+0x244,f244,4);p.write(actor+0x190,pend,4)
        p.write(actor+0x26c,c3,4)
        for k,h in enumerate((h0,h1,h2)):p.write(actor+0x2c4+4*(0x5b+k),h,4)
        opp=ACTORS+(1-seat)*0xf2c;p.write(opp,BODY+0x4000,4)
        for off,v in ((0x40,ox),(0x44,oy)):p.write(BODY+0x4000+off,v,4)
        p.write(opp+0x10c,osys,4);p.write(opp+0x13c,ostate,4);p.write(opp+0x1b0+4*20,ot20,4)
        for off,v in ((0x38,b38),(0x40,b40),(0x44,b44)):p.write(BODY+off,v,4)
        for off,v in ((0x194,s194),(0xa3c,a3c),(0x260,c0),(0x264,c1),(0x274,c5),(0x18c,r18c)):p.write(actor+off,v,4)
        if words[0xd0//4]==0x51 and after[1][0xd0//4]==0x51 and f17!=after[2]:
            counts['excluded_0x51_counter']+=1;continue
        # Object +4 is the task pointer that 147530 (hold) writes through.
        obj=list(words);obj[0x118//4]=actor;obj[1]=TASK
        if obj[47]:obj[47]+=act-1
        p.memory[OBJECT:OBJECT+320]=struct.pack('<80I',*obj)
        p.write(TASK,handler,4);p.write(actor+0x23c,flags,4);p.write(actor+0xf17,f17,1)
        for off,v in ((0x10,left),(0x14,right),(0x1c,top)):p.write(stage+off,v,4)
        p.write(BODY+0x2000+0x128,c128,4)
        _,n=p.run(handler,[TASK],limit=60000);counts['ee_instructions']+=n;counts[hex(handler)]+=1
        got=list(struct.unpack_from('<80I',p.memory,OBJECT))
        got[0x118//4]=words[0x118//4];got[1]=words[1]
        if got[47] and act<=got[47]<act+0x100000:got[47]-=act-1
        ref=[p.read(TASK,4),got,p.read(actor+0xf17,1),p.read(BODY+0x2000+0x128,4),
             [p.read(actor+off,4) for off in (0x23c,0xa3c,0x260,0x264,0x274,0x18c,0x244)]]
        mine=[after[0],after[1],after[2],after[3],[x&0xffffffff for x in owner[20:]]]  # object callbacks without owner words
        if ref!=mine:
            diff=[(hex(i*4),hex(x),hex(y)) for i,(x,y) in enumerate(zip(mine[1],ref[1])) if x!=y]
            wrong.append((case,hex(handler),hex(mine[0]),hex(ref[0]),diff[:6],mine[2],ref[2],mine[3],ref[3],
                          [(k,hex(x),hex(y)) for k,(x,y) in enumerate(zip(mine[4],ref[4])) if x!=y]))
    return wrong

SPAWN_WORDS=(0x0c,0x10,0x14,0x20,0x24,0x28,0x2c,0x30,0x38,0x40,0x44,0x48,0x4c,0x50,0x54,0x58,0x5c,0x60,0x70,
             0xc0,0xc8,0xcc,0xd0,0xd4,0x104,0x108,0x11c)
BODY_WORDS=(0x20,0x30,0x38,0x40,0x44,0x48,0x4c,0x50,0x54,0x58,0x5c,0x60,0x64,0x68,0x6c,0x70,0xc8,0xcc,0x104,0x10c,0x110,0x114)

def original_spawns(seat,spawns,counts):
    # 16d9c8 on the original with live task/object pools (149008 fixture).
    from validate_weapon_handling import setup
    wrong=[]
    for case,v in spawns:
        src,_=setup(seat,FIGHTER);p,a,o=src.p,src.a,src.o
        st,f23c,f244,f248,var,f17=v[:6];reg=v[6:19];body=v[19:99];ox,oy=v[99:101];left,right,top=v[101:104]
        made,f17_after,f248_after=v[104:107]
        for off,val in ((0x194,st),(0x23c,f23c),(0x244,f244),(0x248,f248),(0x26c,var)):p.write(a+off,val,4)
        p.write(a+0xf17,f17,1)
        for i,x in enumerate(reg):p.write(a+0x28c+4*i,x,4)
        for off in BODY_WORDS:p.write(o+off,body[off//4],4)
        # The native spawn runs only under the ACT marker, which its parent
        # snapshot omits; the original reads it from the body itself.
        p.write(o+0x104,(body[0x104//4]|0x8000)&~2,4)
        p.write(o+0x1000+0x40,ox,4);p.write(o+0x1000+0x44,oy,4)
        stage,_=p.run(0x140040)
        for off,val in ((0x10,left),(0x14,right),(0x1c,top)):p.write(stage+off,val,4)
        obj,n=p.run(0x16d9c8,[a],limit=400000);counts['spawn_ee_instructions']+=n
        ref=[bool(obj),p.read(a+0xf17,1),p.read(a+0x248,4)]
        mine=[bool(made),f17_after,f248_after]
        if obj:
            ref.append(p.read(p.read(obj+4,4),4));ref+=[p.read(obj+off,4) for off in SPAWN_WORDS]
            words=v[108:188];mine.append(v[107]);mine+=[words[off//4] for off in SPAWN_WORDS]
        if ref!=mine:wrong.append(('spawn',case,[(i,hex(x),hex(y)) for i,(x,y) in enumerate(zip(mine,ref)) if x!=y]))
    return wrong

def run(job):
    exe,seat,move=job
    if move.startswith('SLOTSEL'):
        # A slot-sweep run (probe_fighter_gaps.py --slots) chosen to cover special states.
        lineup,_,cpu,mv,sp=SLOT_RUNS[int(move[7:])]
        seq=prefix(lineup,sp)+[[0,0]]*330+[[x,0] if seat==0 else [0,x] for x in slot_pads(seat,mv)]
        cpu=[cpu] if cpu!='none' else []
    elif move.startswith('CPU'):
        # CPU-vs-CPU after selection reaches moves public input does not.
        other=int(move[3:]);seq=prefix((FIGHTER,other) if seat==0 else (other,FIGHTER))+[[0,0]]*12000;cpu=['both']
    else:seq=pads(seat,move);cpu=[]
    r=subprocess.run([exe,ASSETS,*cpu],input=''.join(f'{x} {y}\n' for x,y in seq),text=True,capture_output=True,
                     env=substitute_env((FIGHTER,0) if seat==0 else (0,FIGHTER)))
    if r.returncode:raise RuntimeError((seat,move,r.stderr))
    calls=[];frames=[];spawns=[]
    for line in r.stdout.splitlines():
        v=line.split();tag=v[0];v=list(map(int,v[1:]))
        if tag=='F':frames.append(v)
        elif tag=='S' and v[1]==seat:spawns.append(((seat,move,v[0]),v[2:]))
        elif tag=='P' and v[1]==seat:
            b=v[2:];before=(b[0],b[1:81],b[81],b[82],b[83],b[84],b[85],b[86]);a=b[87:]
            after=(a[0],a[1:81],a[81],a[82])
            calls.append(((seat,move,v[0]),before,after,v[-27:]))
    last=frames[-1];victim=1-seat
    return seat,move,(calls,spawns),dict(life=last[1+6*victim+3],hits=last[1+6*seat+4],guards=last[1+6*seat+5])

def main():
    global FIGHTER
    ap=argparse.ArgumentParser();ap.add_argument('--fighter',type=int,required=True);FIGHTER=ap.parse_args().fighter
    with tempfile.TemporaryDirectory() as td:
        tmp=Path(td);obj=tmp/'projectile.o';exe=tmp/'trace'
        cxx=['c++','-std=c++20','-ffp-contract=off','-O2','-I',ROOT/'src']
        subprocess.run([*cxx,'-DupdateDescriptorProjectile=tracedProjectile','-DspawnScriptProjectile=tracedSpawn','-c',ROOT/'src/projectile_engine.cpp','-o',obj],check=True)
        fighter=tmp/'fighter.o'
        subprocess.run([*cxx,'-DupdateScriptFighterObject=tracedFighterObject','-c',ROOT/'src/script_fighter.cpp','-o',fighter],check=True)
        subprocess.run([*cxx,ROOT/'work/ss6/mina_projectile_trace.cpp',obj,fighter,BUILD/'libss6-runtime.a','-o',exe],check=True)
        jobs=[(exe,s,m) for s in (0,1) for m in (*MOTIONS,*(f'CPU{o}' for o in PLAYABLE))]
        global SLOT_RUNS
        SLOT_RUNS=slot_selection(FIGHTER)
        jobs+=[(exe,r[1],f'SLOTSEL{i}') for i,r in enumerate(SLOT_RUNS)]
        with ThreadPoolExecutor(8) as pool:results=list(pool.map(run,jobs))
    counts=Counter();outcomes=[];wrong=[]
    for seat in (0,1):
        calls=[c for s,_,(cs,_),_ in results if s==seat for c in cs]
        spawned=[c for s,_,(_,sp),_ in results if s==seat for c in sp]
        counts['spawns']+=len(spawned)
        wrong+=original_spawns(seat,spawned,counts)
        counts['calls']+=len(calls)
        wrong+=original(seat,calls,counts)
    for seat,move,(calls,sp),out in results:outcomes.append(dict(seat=seat+1,move=move,callbacks=len(calls),spawns=len(sp),**out))
    assert not wrong,(len(wrong),wrong[:8])
    report=dict(status='passed',source=SOURCE_HASH,library_sha256=sha256((BUILD/'libss6-runtime.a').read_bytes()).hexdigest(),
                counts=dict(counts),outcomes=outcomes,
                scope='Per-visit 16def0/16cac0/16c818/16c8d0/16c940 against the original with live Mina inputs; spawning (16d9c8/16d2b0) and contacts are exercised natively only.')
    (ROOT/f'outputs/ss6-feasibility/fighter_{FIGHTER:02}_projectile_validation.json').write_text(json.dumps(report,indent=2)+'\n')
    print(dict(counts))
    for o in outcomes:print(o)

if __name__=='__main__':main()
