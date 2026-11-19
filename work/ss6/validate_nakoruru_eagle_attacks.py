#!/usr/bin/env python3
"""Compare actual 214 slashes, 632146 heavy grab and 236 A+B on both Nakoruru seats to the Japanese EE."""
import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

from nakoruru_eagle_contacts import contact_trace
from validate_dash_motion import Original, PIN, ELF
from validate_selected_combat import prefix, ROOT
from validate_shin_specials import objects as weapon_objects

BUILD=ROOT/'work/ss6/build-native'
DATA=ROOT/'work/ss6/extracted/resources'
REPORT=ROOT/'outputs/ss6-feasibility/nakoruru-eagle-attack-validation.json'
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def sequence(side,state,outcome,armed):
    fw=(128,64)[side];back=fw^192
    pair=lambda x,y=0:(y,x) if side else (x,y)
    pads=prefix((1-side,side))
    if outcome=='shatter':
        for tick in (211,228):pads[tick-1][side]=128
        # Five genuine opposing heavy hits fill Shin rage at eight HP.
        for _ in range(5):pads.extend([pair(0,back)]*65+[pair(0)]*5+[pair(0,1024)]+[pair(0)]*88)
        pads.extend([pair(0)]*100+[pair(fw)]*75+[pair(0)]*5)
        start=len(pads);pads.extend([pair(32),pair(32|fw),pair(fw|768)]+[pair(0)]*1200)
        return pads,start
    if state==90:
        # Select Zan and charge via both real attack buttons. No meter,
        # damage, weapon status or actor coordinates are injected.
        for tick in (211,222,233):pads[tick-1][side]=128
    if outcome=='ko':
        # Eight real two-hit standing heavy slashes leave seven or nine HP.
        # Neither the weapon throw nor its finisher receives test-only damage.
        for _ in range(8):pads.extend([(128,64)]*50+[pair(0)]*10+[pair(1024)]+[pair(0)]*90)
        if state==90:pads.extend([pair(0)]*30) # Release the final heavy recovery before a fresh charge edge.
    if state==90:pads.extend([pair(768)]*215+[pair(0)]*30)
    if not armed:pads.extend([pair(fw|8)]+[pair(0)]*119)
    walk={'hit':40,'guard':40,'miss':0,'ko':40}[outcome]
    if state==75 and outcome=='miss' or state==90 and outcome=='miss':walk=-65
    if state==76:walk=40 if outcome=='miss' else 0
    pads.extend(([(64,128)]*(-walk)) if walk<0 else [(128,64)]*walk)
    pads.extend([pair(0)]*(30 if walk<0 else 7))
    start=len(pads)
    keys={74:[32,32|back,back|256],75:[32,32|back,back|512],76:[32,32|back,back|1024],
          77:[fw,32|fw,32,32|back,back,fw|1024],90:[32,32|fw,fw|768]}[state]
    pads.extend(pair(k,fw if outcome=='guard' else 0) for k in [*keys,*([0]*490)])
    if outcome=='ko':
        pads.extend([pair(0)]*520+[pair(256)]+[pair(0)]*120)
    return pads,start

class CallbackOracle:
    def __init__(self,side):
        self.ref=Original(side,1);self.visits=0;self.instructions=0
        p=self.ref.p
        # Native returns to its common receiver here. Observe the original
        # request of that same receiver while comparing the body-specific
        # callback and its epilogue. The public replay checks actual recovery.
        p.write(0x169810,0x03e00008,4);p.write(0x169814,0,4)
    def compare(self,tick,before,after,recovered):
        o=self.ref;p=o.p;a=o.a;b=o.o;bird=p.read(a+4,4)
        ctx=0x1dc0000;other=o.other
        actor_offsets=[0x194,0x23c,0x244,0x248,0x24c,0x19a,0x18c,0xa3c,0x3c0,*range(0x260,0x27c,4),*range(0x28c,0x2c0,4)]
        actor_sizes=[1 if q in (0x19a,0x24c) else 4 for q in actor_offsets]
        body_offsets=[0x24,0x104,0x108,0x38,0xc0,0x3c,0x134,0x40,0x44]
        mapped=[(a+q,n) for q,n in zip(actor_offsets,actor_sizes)]
        mapped += [(b+q,4) for q in body_offsets]+[(b+0x1040,4)]+[(b+q,4) for q in range(0x4c,0x64,4)]
        mapped += [(bird+q,4) for q in (0x40,0x44,0x128,0x12c,0x130)]
        mapped += [(other+0x23c,4),(o.b+0x108,4),(0x46a948,4),(0x3ebf30+2*512,2),(a+0x190,2),(a+0x192,2)]
        assert len(mapped)==len(before)==len(after)
        for (addr,n),v in zip(mapped,before):p.write(addr,v,n)
        p.write(ctx,a,4);p.write(ctx+4,other,4);p.write(ctx+8,before[11],4)
        calls=[]
        _,n=p.run(before[9],[ctx],limit=500000,observe=lambda pc:calls.append(pc) if pc==0x169810 else None)
        self.instructions+=n;self.visits+=1
        assert bool(calls)==recovered,(tick,hex(before[9]),'common recover',bool(calls),recovered)
        for i,((addr,n),v) in enumerate(zip(mapped,after)):
            want=p.read(addr,n)
            assert want==(v&((1<<(n*8))-1)),(tick,hex(before[9]),i,hex(addr),hex(before[i]),hex(want),hex(v))

def check(args):
    exe,assets,case=args;side,state,outcome,armed=case
    pads,start=sequence(*case)
    run=subprocess.run([exe,assets,str(start)],input=''.join(f'{x} {y}\n' for x,y in pads),text=True,capture_output=True)
    if run.returncode:raise AssertionError((case,run.returncode,run.stderr,run.stdout[-200:]))
    oracle=CallbackOracle(side);bodies=[];bird=[];reactions=[];callbacks=Counter();frames=[];scoreboard=[];eagles={}
    for line in run.stdout.splitlines():
        token,*nums=line.split();v=list(map(int,nums))
        if token=='C':
            tick,seat=v[:2];n=(len(v)-3)//2
            before=v[2:2+n];recovered=bool(v[2+n]);after=v[3+n:]
            if tick<start or seat!=side:continue
            callbacks[hex(before[9])]+=1
            try:oracle.compare(tick,before,after,recovered)
            except AssertionError as e:raise AssertionError((case,e.args)) from e
        else:
            tick=v[0];f=v[1+side*15:16+side*15];d=v[1+(side^1)*15:16+(side^1)*15];frames.append((tick,f,d));scoreboard.append(v[31:34]);eagles[tick]=v[34:]
            for seq,val in ((bodies,f[4]),(bird,f[11]),(reactions,(d[2],d[3],d[4]))):
                if not seq or seq[-1]!=val:seq.append(val)
    target=frames[-1][2];fighter=frames[-1][1]
    entry=next((i for i,f,d in frames if f[2:4]==[1,state]),None)
    assert entry and oracle.visits and (fighter[2]==target[2]==0),(case,entry,bodies,reactions)
    assert all((f[0],d[0])==(1,0) for i,f,d in frames)
    if state==90:
        assert frames[0][1][1]==(1 if outcome=='shatter' else 2) and frames[0][1][10]==1
        assert [x for x in bodies if x in (691,693,694,695,696)]==[691,693+int(not armed),695+int(not armed)],(case,bodies)
        assert ({'hit':703+int(not armed),'shatter':703,'ko':703+int(not armed),'guard':700,'miss':697}[outcome] in bodies),(case,bodies)
    if 74<=state<=76:assert 670+2*(state-74)+int(not armed) in bodies and 776+state-74 in bird,(case,bodies,bird)
    if state==77:assert 681 in bodies
    expected=(target[6]==200) if outcome=='miss' else (target[6]<200)
    knockout={}
    if outcome=='ko':
        lethal=next((i for i,(_,f,d) in enumerate(frames) if d[6]==0),None)
        restored=next((i for i,r in enumerate(scoreboard) if r[0]>scoreboard[0][0] and frames[i][2][6]==200),None)
        assert lethal and restored and lethal<restored and scoreboard[-1][side+1]==1,(case,lethal,restored,scoreboard[-1],reactions)
        next_light=[i for i,f,d in frames[restored:] if f[2:4]==[1,0]]
        assert next_light and frames[0][2][6] in (7,9),(case,next_light,frames[0][2],bodies)
        expected=target[6]==fighter[6]==200
        knockout=dict(before=frames[0][2][6],ko_tick=frames[lethal][0],next_round=frames[restored][0],next_light=next_light[0],wins=scoreboard[-1][1:])
    assert expected and (outcome!='guard' or fighter[8]>0) and (outcome!='miss' or fighter[7:9]==[0,0]),(case,fighter,target,reactions)
    events=contact_trace(BUILD/'ss6-match-replay',assets,pads,start,side,eagles,outcome,frames[0][1][1])
    weapon=[]
    if outcome=='shatter':
        assert frames[0][1][6]==8
        run=subprocess.run([BUILD/'ss6-match-replay',assets,'--mode','select','--shin-fields'],input=''.join(f'1 {x} {y}\n' for x,y in pads),text=True,capture_output=True,check=True)
        seen=set()
        for tick,line in enumerate(run.stdout.splitlines()[start:],start+1):
            timer,parts=weapon_objects(line.split())[side^1]
            new=tuple(x[0] for x in parts)
            if new and new not in seen:weapon.append(dict(tick=tick,act=new,timer=timer));seen.add(new)
        assert {(468,),(469,470,471),(466,),(467,)}<=seen,(side,seen)

    return dict(weapon=weapon,original_contacts=events,seat=side+1,state=state,outcome=outcome,armed=armed,entry=entry,actions=bodies,eagle_actions=bird,
                target_reactions=reactions,remaining_life=target[6],hits=fighter[7],guards=fighter[8],visits=oracle.visits,
                instructions=oracle.instructions,callbacks=callbacks,knockout=knockout)

def main(args):
    runtime_sha=digest(BUILD/'libss6-runtime.a')
    with tempfile.TemporaryDirectory() as folder:
        d=Path(folder);obj=d/'callbacks.o';exe=d/'fight'
        cxx=['c++','-std=c++20','-O2','-I',str(ROOT/'src')]
        subprocess.run([*cxx,'-DupdateNakoruruEagleAttack=tracedEagleImplementation','-c',ROOT/'src/nakoruru_eagle_attack.cpp','-o',obj],check=True)
        subprocess.run([*cxx,ROOT/'work/ss6/nakoruru_eagle_trace.cpp',obj,BUILD/'libss6-runtime.a','-o',exe],check=True)
        cases=[(s,st,out,armed) for s in (0,1) for st in (74,75,76,77,90) for armed in (True,False) if armed or st!=77
               for out in ('hit','guard','miss') if not(st==77 and out=='guard')]
        cases.extend((s,st,'ko',True) for s in (0,1) for st in (77,90))
        cases.extend((s,90,'shatter',True) for s in (0,1))
        if args.case:cases=[v for v in cases if ','.join(map(str,v))==args.case]
        assert cases,'unknown case'
        with ProcessPoolExecutor(4) as pool:
            results=[]
            for item in pool.map(check,[(exe,args.assets,case) for case in cases]):
                results.append(item);print(item['seat'],item['state'],item['outcome'],item['armed'],item['actions'],flush=True)
    if args.case:return
    report=dict(status='passed',original_sha256=PIN,runtime_sha256=runtime_sha,callback_source_sha256=digest(ROOT/'src/nakoruru_eagle_attack.cpp'),replay_sha256=digest(BUILD/'ss6-match-replay'),cases=results,
                verified_contacts=sum(len(r['original_contacts']) for r in results),callback_visits=sum(r['visits'] for r in results),ee_instructions=sum(r['instructions'] for r in results),
                scope='Two-pad public factory selection, real discard, Zan charge and Shin rage via actual incoming heavy hits. The Japanese collector, hit/guard, capture and record-damage handlers run on the observed geometry including the independent eagle object and its independent data. Direct Japanese callbacks on the exact inputs of each native actor visit. Source common recovery is recorded at the handoff and final actual matches must recover. No memory injection in live play.')
    REPORT.write_text(json.dumps(report,indent=2)+'\n');print(len(results),'fights',report['callback_visits'],'original callbacks')

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--assets',type=Path,default=DATA);ap.add_argument('--case');main(ap.parse_args())
