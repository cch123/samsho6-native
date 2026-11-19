#!/usr/bin/env python3
"""Compare resource00 ordinary throw catches, victim ACT playback and simultaneous catches with PS2 routines."""
import collections
import hashlib
import itertools
import json
import subprocess
import tempfile
from pathlib import Path

from character_tiles_oracle import ROOT,ASSETS,bits
from extract_collision_tables import SOURCE_HASH
from mips_probe import Probe
from round_entry_oracle import buffered_stdout
from validate_input_lifecycle import Boundary

WORK=ROOT/'work/ss6'
ACTORS=0x1c00000
OBJECTS=0x1e00000
EVENT=0x1b60000
CTX=0x1e02000
BATTLE=0x1b80000
DRIVER=r'''
#include "throw_victim.hpp"
#include "ground_state.hpp"
#include "combat_decision.hpp"
#include <bit>
#include <iostream>
using namespace ss6;

void emit(uint32_t w){std::cout<<w<<' ';}
void sample(const PlayerObject& body,const StateEntryActor& a,const ContactMarks& marks) {
    const auto c=body.timeline.clock();const auto m=body.timeline.motion();
    for(int32_t v:{int32_t(a.pendingTable),int32_t(a.pendingIndex),int32_t(a.request18c),int32_t(a.flags244),
                   int32_t(a.flags248),int32_t(a.variantA48),a.queuedActionA3c})emit(v);
    for(auto v:a.callbacks260)emit(v);
    emit(c.objectFlags);emit(c.flags104);emit(c.flags108);emit(marks.consumed);
    emit(std::bit_cast<uint32_t>(m.x));emit(std::bit_cast<uint32_t>(m.y));
    for(auto v:{m.dx,m.vx,m.ax,m.dy,m.vy,m.ay})emit(v);
    emit(body.timeline.action().id());emit(c.step);emit(c.fractionalTime);emit(c.endReached);emit(c.endControl);
}
int main(int argc,char** argv) {try {
    ActionBank bank(argv[1],true);
    unsigned slot,mir,targetMir,back,armed,mode;float x,y;
    while(std::cin>>slot>>mir>>targetMir>>back>>armed>>mode>>x>>y){
        PlayerObject source(bank),victim(bank);StateEntryActor s,t;ContactMarks sm,tm;
        auto init=[&](PlayerObject& o,StateEntryActor& a,ContactMarks& marks,unsigned i,unsigned flip){
            a.pendingTable=5+i;a.pendingIndex=7+i;a.request18c=i;a.flags244=0x800011+i;a.flags248=0x2800+i;
            a.variantA48=i?4:back;a.queuedActionA3c=-1;a.flags23c=armed?0x1000:0;
            a.callbacks260={0,0,0,15,16,17,18};marks.consumed=i+1;marks.flags104=0x340;marks.flags108=0x200;
            o.timeline.setMotion({1,2,3,4,5,6,i?x+12:x,i?y+5:y});
            o.timeline.setObjectFlags(0x10000000|(flip<<19),marks.flags104,marks.flags108);
        };
        init(source,s,sm,0,mir);init(victim,t,tm,1,targetMir);
        auto snap=[&]{sample(source,s,sm);sample(victim,t,tm);std::cout<<'\n';};
        if(mode==2){breakGroundThrows(s,t);snap();continue;}
        catchGroundThrow(source,s,sm,victim,t,tm);snap();
        victim.setFlags(victim.timeline.clock().flags104|0x2000,victim.timeline.clock().flags108);
        beginThrowVictim(victim,t,source);snap();
        if(!mode)continue;
        while(t.callbacks260[0]==0x171090) {
            GroundStateRuntime::commitAction(victim,t);victim.commitRequested();
            victim.animate(256);victim.move(256);
            const auto clock=victim.timeline.clock();
            victim.setFlags(clock.flags104|0x2000,clock.flags108);
            updateThrowVictim(victim,t,source);snap();
        }
        GroundStateRuntime::commitAction(victim,t);victim.commitRequested();snap();
    }
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}}
'''

def main():
    raw=(ASSETS.parent/'SLPS_255.59').read_bytes()
    assert hashlib.sha256(raw).hexdigest()==SOURCE_HASH
    p=Probe(raw,finite_model=True)
    act=(ASSETS/'act_00.bin').read_bytes()
    aid=(ASSETS/'aid_00.bin').read_bytes()
    p.memory[0x1700000:0x1700000+len(act)]=act
    for i in (0,1):
        pos=0x46a9b0+0x1800*i
        p.memory[pos:pos+len(aid)]=aid
        p.write(0x4751b0+i*4,0x1700000,4)
    p.write(0x4d3d08,ACTORS,4);p.write(0x4d3d00,BATTLE,4);p.write(0x4c3808,3,4)
    descriptor=0x1b70000
    p.write(EVENT+0x3c,descriptor,4);p.write(descriptor,4,1);p.write(descriptor+1,255,1)
    calls=collections.Counter();total=0
    def run(pc,*args,stop=()):
        nonlocal total
        _,n=p.run(pc,args,limit=450000,stop_before=stop);calls[hex(pc)]+=1;total+=n
    def dump(a,o):
        get=lambda off:p.read(a+off,4)
        body=lambda off:p.read(o+off,4)
        return [p.read(a+0x190,2),p.read(a+0x192,2),*[get(k) for k in (0x18c,0x244,0x248,0xa48,0xa3c,*range(0x260,0x27c,4))],
                *[body(k) for k in (0x38,0x104,0x108)],p.read(o+0x100,1),
                *[body(k) for k in (0x40,0x44,*range(0x4c,0x64,4),0x24,0x28,0x2c,0xc0,0x3c)]]
    xs=(20,53.5,54,54.5,73.5,74,74.5,119.5,120,120.5,320,519.5,520,520.5,565.5,566,566.5,585.5,586,586.5,610)
    cases=[(n%2,mirror,(n//2)%2,back,(n//3)%2,0,x,[-2,0,13][n%3])
           for n,(mirror,back,x) in enumerate(itertools.product(range(2),range(2),xs))]
    cases.extend((slot,mirror,1-mirror,back,armed,1,320,-2) for slot,mirror,back,armed in itertools.product(range(2),repeat=4))
    cases.extend((slot,slot,1-slot,back,1,2,320,0) for slot,back in itertools.product(range(2),repeat=2))
    expected=[];stages=[];commands=[];lengths={}
    for idx,(slot,mirror,target_mir,back,armed,mode,x,y) in enumerate(cases):
        buffered_stdout(p)
        commands.append(f'{slot} {mirror} {target_mir} {back} {armed} {mode} {x} {y}')
        a=ACTORS+slot*0xf2c;t=ACTORS+(1-slot)*0xf2c
        o=OBJECTS+slot*0x1000;v=OBJECTS+(1-slot)*0x1000
        for n,(actor,obj,owner,flip) in enumerate([(a,o,slot,mirror),(t,v,1-slot,target_mir)]):
            p.memory[actor:actor+0xf2c]=bytes(0xf2c);p.memory[obj:obj+320]=bytes(320)
            for off,val in [(0,obj),(0x18c,n),(0x190,5+n|((7+n)<<16)),(0x244,0x800011+n),(0x248,0x2800+n),
                            (0xa48,4 if n else back),(0xa3c,-1),(0xa24,owner),(0x23c,0x1000*armed),
                            *zip(range(0x26c,0x27c,4),range(15,19))]:p.write(actor+off,val,4)
            p.write(BATTLE+0x24c+4*owner,actor,4)
            for off,val in [(0xc,owner),(0x10,owner),(0xcc,owner),(0x30,256),(0xc8,1),(0x38,0x10000000|flip<<19),
                            (0x40,bits(x+12*n)),(0x44,bits(y+5*n)),(0x104,0x340),(0x108,0x200),
                            *zip(range(0x4c,0x64,4),range(1,7))]:p.write(obj+off,val,4)
            p.write(obj+0x100,n+1,1)
        def record(stage):
            expected.append(dump(a,o)+dump(t,v));stages.append((idx,stage))
        p.write(EVENT+0x40,o,4);p.write(EVENT+0x68,v,4);p.write(CTX,t,4);p.write(CTX+4,a,4)
        if mode==2:
            edge=Boundary(0x1574f0)
            run(0x1556a8,EVENT,stop=edge)
            assert edge.stopped==0x1574f0 and p.registers[4]==EVENT and p.registers[5]==7
            record('mutual');continue
        run(0x1551c0,EVENT);record('capture')
        run(0x168aa0,CTX);run(0x170fe8,CTX);record('begin')
        if not mode:continue
        ticks=0
        while p.read(t+0x260,4)==0x171090:
            ticks+=1
            assert ticks<160
            for pc,arg in [(0x149918,t),(0x11d8e0,v),(0x11d730,v),(0x11d6c8,v),(0x168aa0,CTX),(0x171090,CTX)]:run(pc,arg)
            record(f'advance {ticks}')
        run(0x149918,t);run(0x11d8e0,v);record('release clip')
        lengths[f'ACT{404+2*back+(1-armed)}']=ticks
    assert lengths=={"ACT404":33,"ACT405":33,"ACT406":49,"ACT407":49}
    with tempfile.TemporaryDirectory() as tmp:
        cpp=Path(tmp)/'probe.cpp';cpp.write_text(DRIVER);exe=Path(tmp)/'probe'
        subprocess.run(['c++','-std=c++20','-O2','-I',ROOT/'src',cpp,ROOT/'src/throw_victim.cpp',WORK/'build-native/libss6-runtime.a','-o',exe],check=True)
        result=subprocess.run([exe,ASSETS],input='\n'.join(commands)+'\n',text=True,capture_output=True)
        for index,(line,want) in enumerate(zip(result.stdout.splitlines(),expected)):
            got=list(map(int,line.split()))
            assert got==want,(cases[stages[index][0]],stages[index],[(j,u,v) for j,(u,v) in enumerate(zip(got,want)) if u!=v])
        assert result.returncode==0,result.stderr
        assert len(result.stdout.splitlines())==len(expected)
    report=dict(status='passed',elf_sha256=SOURCE_HASH,cases=len(cases),snapshots=len(expected),instructions=total,
                cases_by_kind=dict(wall_boundaries=84,full_first_clip=16,mutual=4),capture_clip_updates=lengths,call_counts=calls,
                scope='Whole original 1551c0, 170fe8 and 171090. Compares both actors and bodies, direction, stage edge shifts, stop flags/velocities, queued actions and callback, and actual clip playback through release. Mutual 1556a8 is compared through the exact call to effect 7. Separate live match replays cover thrower contact and health.')
    (ROOT/'outputs/ss6-feasibility/throw_victim_validation.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
if __name__=='__main__':main()
