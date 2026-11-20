#!/usr/bin/env python3
"""Run the Japanese HUD against synthetic changes and normal versus-controller sessions."""
from concurrent.futures import ProcessPoolExecutor
import json
import shutil
from pathlib import Path
import subprocess
import sys
import tempfile

from mips_probe import signed
from validate_zero_hud import original, seed, set_actor
from validate_dash_motion import ASSETS, ELF, PIN, ROOT, digest
from validate_shin_evasion import EXE

OUT = ROOT/'outputs/ss6-feasibility/life-hud-state-validation.json'
DRAW = (0x1be880, 0x1bfbd0, 0x1bfd40)
FIELDS = ('lifeX', 'lifeWidth', 'trail', 'target', 'woundX', 'submittedWoundWidth',
          'storedWoundWidth', 'woundActive', 'delay', 'healing', 'zanPulse', 'reservePulse', 'swordPulse')
DRIVER = r'''
#include "rage_gauge.hpp"
#include <iostream>
using namespace ss6;
int main() {
    RageGaugeState g; int reset;
    while(std::cin>>reset) {
        std::array<LifeGaugeInput,2> z{}; std::array<int32_t,2> systems{},rage{};
        for(unsigned i=0;i<2;++i) {
            auto& a=z[i];
            std::cin>>systems[i]>>rage[i]>>a.life>>a.reserve>>a.phase>>a.sword>>a.swordMax
                    >>a.opponentHits>>a.inPersistentHurt>>a.holdLifeSampling;
        }
        if(reset)g.reset({});
        g.advance(rage,{},systems,{},z);
        for(const auto& p:g.players) {
            for(int v:{p.lifeX,p.lifeWidth,p.lifeTrail,p.lifeGauge.life,p.woundX,p.woundWidth,
                    p.storedWoundWidth,int(p.woundActive),p.lifeDelay,int(p.lifeHealing),p.zanLifePulse,
                    p.lifePulse,p.swordPulse})std::cout<<v<<' ';
        }
        std::cout<<'\n';
    }
}'''


class JapaneseHud:
    def __init__(self, systems):
        self.p = original()
        seed(self.p, systems)
        self.instructions = 0
        # Suppress final DMA packet storage only; GE, HUD branches and all
        # pulse/rectangle submissions still execute with the original code.
        self.p.write(0x3ec73c, 1, 4)

    def frame(self, samples, reset=False, states=None):
        p = self.p
        for i,(system,rage,hp,reserve,phase,sword,cap,hits,hurt,hold) in enumerate(samples):
            set_actor(p,i,(system,rage,0,phase,reserve,0,hp,sword,cap,hits,hurt))
            battle=p.read(0x4d3d00,4)
            p.write(battle+0x260+0x108*(1-i),hits,4)
            if states:
                actor=p.read(0x132f598+4*i,4);table,index=states[i]
                p.write(actor+0x194,table|(index<<16),4)
                assert p.run(0x14ad90,[actor])[0]==hurt,(i,states,hurt)
        for i in (0,1):self.instructions+=p.run(0x1be068,[i])[1]
        assert samples[0][-1]==samples[1][-1]
        p.write(0x582944,samples[0][-1],4)
        if reset:self.instructions+=p.run(0x1be1a8,limit=200000)[1]
        wound=[0,0]
        def submit(pc):
            if pc==0x1145c0 and p.registers[31]==0x1befe8:
                wound[p.registers[16]]=signed(p.registers[6],32)
        for pc in DRAW:
            self.instructions+=p.run(pc,limit=200000,observe=submit if pc==DRAW[0] else None)[1]
        out=[]
        for i,sample in enumerate(samples):
            h=0x132f3a0+152*i;w=0x132f4d0+16*i;offset=4*i
            read=lambda a:signed(p.read(a,4),32)
            a=[read(h),read(h+8),read(h+16),read(h+20),read(w),wound[i],read(w+4),read(w+8),
               read(w+12),read(0x132f4f0+offset),read(0x132f4f8+offset)]
            a += [read((0x132f518 if sample[0]==5 else 0x132f508)+offset),read(0x132f558+offset)]
            out.append(a)
        return out


def compare(name,tick,got,want):
    for side in (0,1):
        diffs=[(k,a,b) for k,a,b in zip(FIELDS,got[side],want[side],strict=True) if a!=b]
        if diffs:raise AssertionError((name,tick,side,diffs))


def input_at(system,t):
    hp=(200 if t<3 else 168 if t<9 else 156 if t<58 else 181 if t<68 else 153 if t<84
        else 24 if t<116 else 15 if t<120 else 23 if t<135 else 0 if t<154 else 12)
    hits=(1 if t<9 or 68<=t<84 or 116<=t<120 else 3)
    hurt=int(4<=t<11 or 66<=t<71 or 85<=t<90 or 135<=t<142)
    reserve=(20 if t<61 else 70 if t<100 else 18 if t<130 else 32)<<8
    phase=(1 if t<35 else 2 if t<92 else 3 if t<144 else 4) if system==4 else 0
    return (system,(t//13)%4,hp,reserve,phase,(100 if t%9>=3 else 89)<<8,100<<8,hits,hurt,0)


def synthetic(spec):
    exe,systems=spec
    src=JapaneseHud(systems);lines=[];expected=[]
    for t in range(195):
        # Deliberately restart in full life after a KO. Include plateaus in
        # hitstop/slow motion, an interrupted heal, and another heal during a
        # live wound. HP rising after the KO cannot revive the drawn bar.
        u=t if t<164 else t-164
        samples=[]
        for i,system in enumerate(systems):
            at=max(0,u-(5 if i else 0))
            sample=list(input_at(system,at))
            sample[-1]=int(56<=u<61 or 128<=u<133)
            samples.append(sample)
        reset=int(t in (0,164))
        lines.append(' '.join(str(w) for w in [reset,*samples[0],*samples[1]]))
        expected.append(src.frame(samples,reset))
    rows=subprocess.run([exe],input='\n'.join(lines)+'\n',text=True,capture_output=True,check=True).stdout.splitlines()
    for t,(row,want) in enumerate(zip(rows,expected,strict=True)):
        r=list(map(int,row.split()));compare(systems,t,[r[:13],r[13:]],want)
    return dict(spirits=systems,ticks=len(rows),original_instructions=src.instructions)


def masks(groups):
    return [pad for n,*pad in groups for _ in range(n)]


def trace(exe,pads,args):
    cmd=[exe,ASSETS,'--life-hud-fields',*args]
    data=''.join(f'1 {a} {b}\n' for a,b in pads)
    run=subprocess.run(cmd,input=data,text=True,check=True,capture_output=True)
    return [row.split() for row in run.stdout.splitlines()]


def live_path(spec):
    name,exe=spec
    from validate_stage_item_notice_scene import P1,P2,pads_for
    from validate_zero_dual_concentration import GROUP
    args=['--mode','versus']
    if name.startswith('food'):
        pads=pads_for(P1 if name=='food_p1' else P2,True)
        args=['--mode','select','--round-time','99']
    elif name=='dual_zero':
        pads=masks([(6300,0,0)]+GROUP*4+[(1,6144,6144),(300,0,0)])
        args+=['--p1-spirit','zero','--p2-spirit','zero']
    else:
        pads=masks([(500,0,0)]+[(70,128,0),(3,0,0),(1,1024,0),(220,0,0)]*19)
        if name=='ko_p2':pads=[((b&~192)|(b&64)<<1|(b&128)>>1,(a&~192)|(a&64)<<1|(a&128)>>1) for a,b in pads]
        first=next(i for i,r in enumerate(trace(exe,pads,args)) if r[28]=='1')
        pads=pads[:first+1]+masks([(50,0,0),(1,32,0),(1,0,0),(1,512,0),(90,0,0)])
    rows=trace(exe,pads,args)
    o=None;rounds=[];heals=[];knockouts=[];active=[];seen=0;paused=0
    previous=None;previous_life=None;number=None;phase=None
    menu_pulses=[];instructions=0
    for t,row in enumerate(rows,1):
        raw=list(map(int,row[23:74]));visible,reset,seconds,stopped,round_index,menu,session=raw[:7]
        if not visible:continue
        seats=[raw[7+i*22:29+i*22] for i in (0,1)]
        samples=[(a[0],a[21],a[1],a[4],a[5],a[2],a[3],a[6],a[7],0) for a in seats]
        if number!=session:
            if o:instructions+=o.instructions
            o=JapaneseHud(tuple(a[0] for a in seats));previous_life=None
            number=session
        if reset:rounds.append([t,round_index])
        prior_states=None
        if previous and not reset and int(previous[29])==session and previous[23]=='1':
            prior_states=[tuple(map(int,previous[j:j+2])) for j in (3,13)]
        want=o.frame(samples,reset,prior_states)
        compare(name,t,[s[8:21] for s in seats],want)
        if previous_life and not reset:
            for side,s in enumerate(seats):
                if s[1]>previous_life[side] and s[17]:heals.append([t,side,previous_life[side],s[1],s[10]])
                if s[1]==0 and previous_life[side]>0:knockouts.append([t,side,s[10],s[13]])
        # Previous match-end actor HP is input to the next priority-20 sample;
        # it precedes this tick's contact resolution even on the fatal update.
        if previous and not reset and int(previous[29])==session and previous[23]=='1':
            assert [s[1] for s in seats]==[max(0,int(previous[j])) for j in (9,19)],(name,t)
        if menu:paused+=1;menu_pulses.append(tuple(s[20] for s in seats))
        if name=='dual_zero' and [s[5] for s in seats]!=phase:
            phase=[s[5] for s in seats];active.append([t,phase])
        previous_life=[s[1] for s in seats];previous=row;seen+=1
    assert seen
    if name.startswith('food'):assert any(h[1]==int(name[-1])-1 for h in heals),(name,heals)
    if name.startswith('ko_'):
        assert len(knockouts)>=2 and paused>=50 and len(set(menu_pulses))>1 and number==2,(name,knockouts,paused,number)
    if name=='dual_zero':assert any(v==[3,3] for _,v in active) and active[-1][1]==[4,4],active
    return dict(name=name,controller_ticks=len(rows),compared_task_visits=seen,original_instructions=instructions+o.instructions,
                last_session=number,round_reseeds=rounds,heals=heals,knockouts=knockouts,menu_samples=paused,
                menu_sword_pulse_pairs=len(set(menu_pulses)),concentration_transitions=active)


def main():
    assert digest(ELF)==PIN
    with tempfile.TemporaryDirectory() as temp:
        f=Path(temp)/'test.cpp';f.write_text(DRIVER);app=Path(temp)/'probe'
        subprocess.run(['c++','-std=c++20','-ffp-contract=off','-O2','-I',ROOT/'src',f,ROOT/'src/rage_gauge.cpp','-o',app],check=True)
        with ProcessPoolExecutor(4) as pool:
            matrices=list(pool.map(synthetic,[(app,pair) for pair in ((0,1),(1,0),(2,3),(3,2),(4,5),(5,4))]))
    if '--synthetic-only' in sys.argv:print(matrices);return
    # Each public input run must use the identical executable, including when
    # a new development build is linked concurrently by another test runner.
    with tempfile.TemporaryDirectory() as temp:
        snapshot=Path(temp)/EXE.name;shutil.copyfile(EXE,snapshot);snapshot.chmod(0o755)
        sha=digest(snapshot)
        with ProcessPoolExecutor(4) as pool:
            live=list(pool.map(live_path,[(name,snapshot) for name in
                                          ('food_p1','food_p2','ko_p1','ko_p2','dual_zero')]))
    report=dict(status='passed',japanese_elf_sha256=PIN,match_replay_sha256=sha,compared_seat_fields=FIELDS,
                original_functions=[hex(x) for x in (0x1be068,*DRAW)],synthetic=matrices,controller_sessions=live,
                scope='Japanese 1be880/1bfbd0/1bfd40 and all reached functions execute. Synthetic scheduling supplies raw actor and hit-counter fields. Live runs use public versus inputs and the native combat-state samples taken by priority 20. Each source task invocation checks both seats and the submitted red rectangle. Independent GS pixel comparisons live in the upper HUD graphics report.')
    OUT.write_text(json.dumps(report,indent=2)+'\n')
    print(OUT)
if __name__=='__main__':main()
