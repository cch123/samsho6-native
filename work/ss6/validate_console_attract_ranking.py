#!/usr/bin/env python3
"""Compare the Japanese rank task's demo RNG, clock, rows, START and natural scene requests."""
import random
import json
import subprocess
import tempfile
from pathlib import Path

from validate_console_versus_menu import G, Oracle, T
from validate_dash_motion import ELF, PIN, ROOT, digest
from validate_input_features import PADS
from validate_input_lifecycle import Boundary
from validate_versus_result import ALPHA

RANK=0x13735b0
ARCADE=0x12d3668
DRIVER=r'''
#include "console_attract_ranking.hpp"
#include "game_random.hpp"
#include <iostream>
int main(int argc,char**) {
    if(argc==2) {
        unsigned advance,press,count;
        while(std::cin>>advance>>press>>count) {
            bool alternate=true;ss6::ConsoleAttractRanking rank;
            for(unsigned t=0;t<advance;++t)rank.tick(false,alternate);
            for(unsigned t=0;t<count;++t) {
                const auto destination=rank.tick(t==press||t==press+3,alternate);
                const auto& f=rank.draw;
                std::cout<<f.phase<<' '<<f.tick<<' '<<f.firstRow<<' '
                         <<unsigned(destination)<<' '<<alternate<<' '<<f.paletteLevelWrite()<<'\n';
            }
        }
        return 0;
    }
    int mode;unsigned seed,held;uint64_t library;
    while(std::cin>>mode>>seed>>library>>held) {
        ss6::GameRandom rng{mode,seed,library};
        const auto m=ss6::selectRankingDemo(rng,held);
        std::cout<<m.stage;
        for(const auto& f:m.players)std::cout<<' '<<f.character<<' '<<f.color<<' '<<f.spirit;
        auto append=[](auto& row){for(auto v:row)std::cout<<' '<<v;};
        append(m.opponents);append(m.stages);append(m.roundRolls);append(m.characterRolls);append(m.characterOrder);
        std::cout<<' '<<rng.gameSeed<<' '<<rng.librarySeed<<'\n';
    }
    for(auto config:{0,1,2,3}) {
        bool alternate=config!=1;
        ss6::ConsoleAttractRanking rank;
        for(unsigned t=0;t<4000;++t) {
            const auto transition=rank.tick(config==3&&t==22,alternate,config==2);
            const auto& f=rank.draw;
            std::cout<<f.phase<<' '<<f.tick<<' '<<f.firstRow<<' '<<unsigned(transition)<<' '<<alternate;
            const auto layout=f.rowLayout();
            for(unsigned i=0;i<layout.count;++i) {
                const auto& r=layout.rows[i];
                std::cout<<' '<<r.index<<' '<<r.x<<' '<<r.y<<' '<<r.alpha<<' '<<r.brightness<<' '<<r.stripAlpha;
            }
            std::cout<<'\n';
            if(transition!=ss6::RankingDestination::None)break;
        }
    }
}
'''

def setup_runs(p):
    rng=random.Random(0x1483f8)
    starts=[];want=[]
    # The first seven rounds and speed rolls are initialized before the
    # demo fighter draws. Held D-pad can replace the final schedule opponent.
    for case in range(96):
        mode=(0,1,-2)[case%3];seed=rng.randrange(1,2**31);lib=rng.getrandbits(64)
        held=(0,16,32,64,128,240)[case%6]
        starts.append(f'{mode} {seed} {lib} {held}')
        reent=0x1b00000
        p.write(0x5d1bf8,reent,4);p.write(reent+0xa8,lib,8)
        p.write(0x443150,mode,4);p.write(0x3d2e80,seed,4)
        for pad in (PADS,PADS+12):p.write(pad,held,4)
        b=Boundary(0x1484e0);p.run(0x1483f8,limit=250000,stop_before=b)
        assert b.stopped==0x1484e0
        row=[p.read(G+4,4)]
        for who in (0,1):
            a=0x456890+48*who
            row += [p.read(a+i,4) for i in (0,4,12)]
            assert p.read(a+32,4)==2
        for off,n,sz in ((14,7,2),(0,7,2),(28,7,1),(0x120,49,2),(0x182,49,2)):
            row += [p.read(ARCADE+off+sz*i,sz) for i in range(n)]
        row += [p.read(0x3d2e80,4),p.read(reent+0xa8,8)]
        want.append(row)
    return starts,want


def tick(o):
    p=o.p;a=RANK
    ph,first,t=(p.read(a+x,4) for x in (0x258,0x25c,0x260))
    if ph==10 and t==0:first=19
    p.write(0x3ec73c,1,4)   # Suppress GS submission only, as in the menu oracle.
    for addr in (0x345178,0x345180,0x378e08):p.write(addr,0,4)
    callback=p.read(0x5852c8+ph*4,4)
    layout=[];strip=0
    def draw(pc):
        nonlocal strip
        if pc==0x1145c0 and p.registers[31]==0x1e8df8:
            strip=(p.registers[8]>>24)&255
        elif pc in (0x1e9768,0x1e97d8):
            index=(p.registers[4]-RANK-(120 if pc==0x1e97d8 else 0))//24
            color=p.read(0x3db900,4)
            def signed(v):return (v&0x7fffffff)-(v&0x80000000)
            layout.extend((index,signed(p.registers[5]),signed(p.registers[6]),color>>24,color&255,strip))
    if ph==6 and t==64:
        # 148528 destroys the battle's live task/object pools. The rank task
        # enters phase 7 before that teardown and increments its timer after it.
        o.run(callback,a,stop=(0x115a00,))
        assert p.read(a+0x258,4)==7 and p.read(a+0x260,4)==0
        p.put(17,a);o.run(0x1e911c,stop=(0x1e9130,))
    elif ph==7:
        # 1e8aa8 performs optical texture loading, outside this data fixture.
        o.run(callback,a,stop=(0x1e8aa8,))
        p.put(16,a);o.run(0x1e915c,stop=(0x1e9174,))
    elif ph in (3,10):
        # The parent rank dispatcher restores white before each callback.
        o.run(0x1ea708,255,255,255,255)
        o.run(callback,a,observe=draw)
    else:o.run(callback,a)
    return [ph,t,first],layout


def start_request():
    for s in (0,1):
        o=Oracle();p=o.p
        for addr,val in ((G,0),(0x582210,1),(0x58221c,1),(0x582208,2),(0x43d20c,0x1e89f0)):
            p.write(addr,val,4)
        p.write(PADS+12*s+4,8,4)
        o.run(0x1b9b80)
        assert p.read(T+20,4)==0x127940 and p.read(0x582214,4)==1


def validate_early_exits(exe,trace):
    # Use real task allocation, flag inspection, priority traversal and tick
    # dispatch. Stop at the destructor before the successor's disc loading.
    positions={(ph,t):i for i,((ph,t,_),_) in enumerate(trace)}
    initial=[(1,480,0),(1,539,0),(5,0,0),(3,25,0),(3,355,0),(10,71,0),(10,1726,0),(10,1726,3),(10,1726,6)]
    requests=[];expected=[];report=[]
    for phase,age,press in initial:
        for seat in (0,1):
            o=Oracle();p=o.p;advance=positions[phase,age]
            _,_,first=trace[advance][0]
            for addr,val in ((G,0),(0x582210,1),(0x58221c,1),(0x582208,2),
                             (RANK+0x258,phase),(RANK+0x25c,first),(RANK+0x260,age),(0x582af4,1)):
                p.write(addr,val,4)
            o.run(0x125178)  # resident priority-60 transition task
            p.put(21,RANK);o.run(0x1e887c,stop=(0x1e88a0,))  # priority-20 task + destructor
            levels=[];destinations=[]
            for t in range(96):
                inputs=[0,0];inputs[seat]=8 if t in (press,press+3) else 0
                o.sample(inputs);o.run(0x1b9b80)
                draw=[p.read(RANK+off,4) for off in (0x258,0x260,0x25c)]
                if draw[:2]==[10,0]:draw[2]=19
                for addr in (0x345178,0x345180,0x378e08):p.write(addr,0,4)
                p.write(0x3ec73c,1,4);visits=[];write=[]
                def observe(pc):
                    if pc in (0x1e8b38,0x1251d0):visits.append(pc)
                    if pc==0x117108:write.append(p.registers[5])
                stop=Boundary(0x1e89f0)
                p.run(0x112838,stop_before=stop,observe=observe,limit=500000)
                assert visits==([0x1e8b38,0x1251d0] if p.read(T+4,4) else [0x1e8b38])
                target=p.read(T+20,4);levels.append(p.read(ALPHA,4))
                if not destinations or destinations[-1][1]!=target:destinations.append((t,target))
                expected.append([*draw,target,p.read(0x582af4,4),write[0] if write else -1])
                if stop.stopped:
                    # The destructor ends in 112a70(tag=1f42); prove that this
                    # cancels the live priority-20 handle the scheduler visited.
                    rankHandle=p.read(0x1232440+4*20,4)
                    assert p.read(rankHandle,4)==0x1e8b38 and p.read(rankHandle+4,4)==0x10
                    p.write(0x1fff000,0x1ffff00,8);o.run(0x1e8a08)
                    assert p.read(rankHandle+4,4)&4
                    break
                o.run(0x116b9c,stop=(0x116bf0,0x116bf4))
            else:raise AssertionError('Missing ranking teardown')
            assert levels[-4:]==[256]*4
            if phase not in (1,5):
                assert t==press+14 and levels[press:]==[*range(0,251,25),256,256,256,256]
            if phase==1 and age==539:assert levels==[118,143,168,193,218,243,256,256,256,256]
            requests.append(f'{advance} {press} {t+1}')
            report.append(dict(phase=phase,age=age,seat=seat+1,start=press,updates=t+1,
                               destination_changes=destinations,levels=levels))
    result=subprocess.run([exe,'exits'],input='\n'.join(requests),text=True,capture_output=True,check=True)
    actual=[list(map(int,row.split())) for row in result.stdout.splitlines()]
    assert actual==expected,[(i,k,v) for i,(k,v) in enumerate(zip(actual,expected)) if k!=v][:2]
    return report


def main():
    assert digest(ELF)==PIN
    setup=Oracle()
    starts,want=setup_runs(setup.p)
    with tempfile.TemporaryDirectory() as d:
        path=Path(d);driver=path/'rank.cpp';driver.write_text(DRIVER)
        exe=path/'rank'
        subprocess.run(['c++','-O2','-std=c++20','-ffp-contract=off','-I',ROOT/'src',driver,
                        ROOT/'src/console_attract_ranking.cpp',ROOT/'src/scalar_float.cpp',
                        ROOT/'src/game_random.cpp','-o',exe],check=True)
        verify(exe,starts,want)

def verify(exe,starts,want):
    ran=subprocess.run([exe],input='\n'.join(starts),text=True,capture_output=True,check=True)
    native=iter([list(map(int,row.split())) for row in ran.stdout.splitlines()])
    for seed,row in zip(starts,want):
        got=next(native)
        assert got==row,(seed,[(i,a,b) for i,(a,b) in enumerate(zip(got,row)) if a!=b])
    o=Oracle();p=o.p
    assert p.read(0x582af4,4)==1
    trace=[]
    while p.read(RANK+0x258,4)!=11:
        row,layout=tick(o)
        got=next(native);assert got==row+[0,1]+layout,(row,got[5:],layout)
        trace.append((row,layout))
    for config in range(3):
        if config:
            for row,layout in trace:assert next(native)==row+[0,int(config!=1)]+layout
        p.write(RANK+0x258,11,4);p.write(RANK+0x260,1,4)
        p.write(0x582af4,config!=1,4);p.write(0x43d052,config==2,1)
        row,layout=tick(o);destination=p.read(T+20,4)
        assert next(native)==row+[destination,p.read(0x582af4,4)] and destination in (0x1ea7f0,0x1ca408)
    start_request()
    for row,layout in trace[:22]:assert next(native)==row+[0,1]+layout
    assert next(native)==trace[22][0]+[0x127940,1]
    assert next(native,None) is None
    exits=validate_early_exits(exe,trace)
    report=dict(status='passed',original_elf_sha256=PIN,exits=exits,
                scope='Two raw pad samplers, original 1b9b80 START, 1e8b38 ranking and 1251d0 transition callbacks in complete 112838 dispatch order up to entry to 1e89f0. Separate actual destructor cancellation tail, excluding subsequent disc I/O and SDK display.')
    (ROOT/'outputs/ss6-feasibility/console-ranking-start-validation.json').write_text(json.dumps(report,indent=2)+'\n')
    print(f'{len(want)} complete random selections, {len(trace)+1} ranking updates, '
          'both START ports and three successor cases passed')


if __name__=='__main__':main()
