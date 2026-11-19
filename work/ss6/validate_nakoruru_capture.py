#!/usr/bin/env python3
"""Check the paired capture rows against the Japanese executable and both local VS ports."""
from concurrent.futures import ProcessPoolExecutor
from hashlib import sha256
import json
from pathlib import Path
import struct
import subprocess
import tempfile

from validate_dash_motion import ELF, PIN
from validate_weapon_handling import setup
from validate_selected_combat import BUILD, ROOT, prefix, trace

ASSETS=ROOT/'work/ss6/extracted/resources'
DRIVER=r'''
#include "nakoruru_capture.hpp"
#include <bit>
#include <iostream>
using namespace ss6;
int main(int argc,char** argv) {
    const unsigned source=argc>2?std::stoul(argv[2]):1;
    unsigned slot,seat,armed,victim,mode,system;
    while(std::cin>>slot>>seat>>armed>>victim>>mode>>system) {
        ActionBank targetBank(argv[1],true,victim),sourceBank(argv[1],true,source);
        PlayerObject body(targetBank),other(sourceBank);
        StateEntryActor a,s;a.character=victim;s.character=source;a.pendingCharacter254=source;
        a.flags23c=armed?4096:0;s.flags23c=4096;a.fieldA30=s.fieldA30=200;
        a.callbacks260[0]=source==3?0x1ee658:source==2?0x1edfa0:0x1ec420;a.state194=2|(80+slot)<<16;
        s.state194=1|((source==2?89:slot==16?79:slot==0?77:90)<<16);
        a.flags244=0x20000;s.flags244=0x1000;
        for(auto* actor:{&a,&s}) {
            actor->request18c=7;actor->pendingTable=0;actor->pendingIndex=11;
            for(unsigned i=0;i<actor->timers.size();++i)actor->timers[i]=256+int(i);
            actor->override27c={0x10,0x20,0x30,0x40};
        }
        if(mode==1||mode==9||mode==11||mode==15||mode==17)a.flags23c|=0x10000000;
        if(mode==15||mode==16)s.flags23c|=0x10000000;
        if(mode==2||mode==13||mode==17)s.state194=2|(36<<16);
        if(mode==3||mode==12)s.fieldA30=0;
        if(mode==4)s.flags23c|=0x80;
        s.stateFlags19a=4;s.callbacks260[0]=0x163610;
        body.timeline.setPosition(seat?342:300,slot==16?50:0);
        other.timeline.setPosition(seat?300:342,slot==16?60:0);
        StateEntryContext context;context.player=seat;StageCamera camera;GameRandom rng;
        auto& pools=context.tasks;pools.initializeTasks();pools.initializeObjects();pools.initializeOwners();
        AuxiliaryObjects objects(argv[1],{victim,source,51});std::array<uint32_t,48> registry{},opponent{},stale{};
        if(mode>=5&&mode<=14) {
            auto& list=(mode==6||mode==9)?stale:((mode==10||mode==14)?registry:opponent);
            auto task=pools.registerObjectTask(list,1,0x1ed440);
            a.bodyField124=pools.tasks.at(task-1)[7];
            s.auxiliaryObject04=mode==10?0:a.bodyField124;
            auto& child=pools.objects.at(a.bodyField124-1);
            child[0xc/4]=mode==8?2:mode==14?seat:1-seat;
            child[0xcc/4]=mode==7?4:mode==12?2:3;
            child[0x40/4]=std::bit_cast<uint32_t>(355.f);
        }
        WeaponLockActorContext shared{other,s,camera,42,objects,registry};
        unsigned suppressed=0;GroundStateFrame frame;frame.weaponLock=&shared;frame.random=&rng;frame.opponentSystem=system;
        frame.opponentObjectTasks=opponent;frame.suppressCaptureObjects=[&]{++suppressed;};
        updateNakoruruCapture(body,a,context,frame);
        auto out=[](uint32_t v){std::cout<<v<<' ';};
        for(auto* actor:{&a,&s}) {
            out(actor->flags23c);out(actor->flags244);out(actor->queuedActionA3c);
            for(auto v:actor->callbacks260)out(v);
        }
        for(auto v:a.registry28c)out(v);
        for(auto* o:{&body,&other}){out(o->timeline.clock().objectFlags&0x80000);
            out(std::bit_cast<uint32_t>(o->timeline.motion().x));out(std::bit_cast<uint32_t>(o->timeline.motion().y));}
        for(auto* actor:{&a,&s}){
            out(actor->request18c);out(uint16_t(actor->pendingTable));out(uint16_t(actor->pendingIndex));out(actor->flags248);
            for(auto v:actor->override27c)out(v);
            for(auto t:actor->timers)out(t);
        }
        unsigned weapon=0;
        for(auto task:registry)if(task){
            const auto& t=pools.tasks.at(task-1);
            if(t[0]==0x1701c0||t[0]==0x170340)weapon=pools.objects.at(t[7]-1)[0x24/4];
        }
        out(weapon);out(suppressed);
        if(a.bodyField124) {
            const auto& child=pools.objects.at(a.bodyField124-1);out(child[0x38/4]&0x80000);out(child[0x104/4]&0x100000);
        }
        std::cout<<'\n';
    }
}'''

def compare(spec):
    slot,seat,armed,victim,mode,system=spec[:6]
    source=spec[6] if len(spec)>6 else 1
    handler={1:0x1ec420,2:0x1edfa0,3:0x1ee658}[source]
    oracle,_=setup(seat,victim);p,a,body,s=oracle.p,oracle.a,oracle.o,oracle.other
    other=p.read(s,4);context=0x1db0000
    for i in range(2):
        reg=oracle.b+0x29c+0x108*i;p.memory[reg:reg+192]=bytes(192)
    p.write(context,a,4);p.write(context+4,s,4);p.write(context+8,slot,4)
    for who,flags,state,action,x,y in [
            (a,4096 if armed else 0,2|(slot+80)<<16,handler,342 if seat else 300,50 if slot==16 else 0),
            (s,4096,1|((89 if source==2 else {0:77,16:79}.get(slot,90))<<16),0x163610,300 if seat else 342,60 if slot==16 else 0)]:
        o=p.read(who,4)
        for offset,value in [(0x23c,flags),(0x244,0),(0x248,0),(0xa30,200),(0x194,state),(0xa3c,0xffffffff)]:
            p.write(who+offset,value,4)
        p.memory[who+0x260:who+0x2c0]=bytes(0x60)
        p.write(who+0x260,action,4);p.write(o+0x38,0,4);p.write(o+0x124,0,4)
        struct.pack_into('<ff',p.memory,o+0x40,x,y)
    p.write(a+0x254,source,1);p.write(a+0xa18,source,4);p.write(s+0xa10,source,4);p.write(s+0x19a,4,1)
    for who in (a,s):
        p.write(who+0x18c,7,4);p.write(who+0x190,0,2);p.write(who+0x192,11,2)
        struct.pack_into('<4I',p.memory,who+0x27c,0x10,0x20,0x30,0x40)
        for i in range(35):p.write(who+0x1b0+4*i,256+i,4)
    p.write(a+0x244,0x20000,4);p.write(s+0x244,0x1000,4);p.write(s+0x10c,system,4)
    if mode in (1,9,11,15,17):p.write(a+0x23c,p.read(a+0x23c,4)|0x10000000,4)
    if mode in (15,16):p.write(s+0x23c,p.read(s+0x23c,4)|0x10000000,4)
    if mode in (2,13,17):p.write(s+0x194,2|(36<<16),4)
    if mode in (3,12):p.write(s+0xa30,0,4)
    if mode==4:p.write(s+0x23c,p.read(s+0x23c,4)|0x80,4)
    child,task=0x1cf0000,0x1ce0000
    if 5<=mode<=14:
        p.write(body+0x124,child,4);p.write(s+4,0 if mode==10 else child,4)
        p.write(child+0xc,2 if mode==8 else seat if mode==14 else 1-seat,4)
        p.write(child+0xcc,4 if mode==7 else 2 if mode==12 else 3,4)
        struct.pack_into('<f',p.memory,child+0x40,355.)
        p.write(task,0x1ed440,4);p.write(task+0x1c,child,4)
        if mode not in (6,9):p.write(oracle.b+0x29c+0x108*(seat if mode in (10,14) else 1-seat),task,4)
    calls=[]
    _,steps=p.run(handler,[context],limit=500000,observe=lambda pc:calls.append(pc) if pc==0x168400 else None)
    values=[]
    for actor in (a,s):
        values.extend(p.read(actor+off,4) for off in (0x23c,0x244,0xa3c,*range(0x260,0x27c,4)))
    values.extend(p.read(a+off,4) for off in range(0x28c,0x2c0,4))
    for o in (body,other):values.extend((p.read(o+0x38,4)&0x80000,p.read(o+0x40,4),p.read(o+0x44,4)))
    for who in (a,s):
        values.extend((p.read(who+0x18c,4),p.read(who+0x190,2),p.read(who+0x192,2),p.read(who+0x248,4)))
        values.extend(p.read(who+off,4) for off in range(0x27c,0x28c,4))
        values.extend(p.read(who+0x1b0+i*4,4) for i in range(35))
    weapon=0
    for col in range(48):
        job=p.read(oracle.b+0x29c+0x108*seat+col*4,4)
        if job and p.read(job,4) in (0x1701c0,0x170340):weapon=p.read(p.read(job+0x1c,4)+0x24,4)
    values.extend((weapon,len(calls)))
    if 5<=mode<=14:values.extend((p.read(child+0x38,4)&0x80000,p.read(child+0x104,4)&0x100000))
    return values,steps

def live(side,kind,near):
    p=prefix((1-side,side));fw=(128,64)[side]
    pair=lambda x,y:(y,x) if side else (x,y)
    p += [(128,64)]*near+[(0,0)]*10
    for t in range(180):
        us=16 if t==0 else ((32 if kind=='down' else fw)|2048) if t==13 else 0
        p.append(pair(us,16 if t==0 and kind=='grab' else 0))
    rows=trace(BUILD/'ss6-match-replay',ASSETS,p)[-180:];x=3+10*side;y=3+10*(1-side)
    states={(int(r[x+1]),int(r[x+2])) for r in rows if r[x]=='1'}
    target={(int(r[y+1]),int(r[y+2])) for r in rows if r[y]=='2'}
    assert all(r[49]=='0' for r in rows)
    assert rows[-1][x:x+3]==rows[-1][y:y+3]==['0','0','0']
    remaining=int(rows[-1][y+6])
    if kind=='down':assert (78,564) in states
    elif near:assert (79,571) in states and (96,1310) in target and remaining==186
    else:assert all(move!=79 for move,_ in states) and remaining==200
    return dict(seat=side+1,input=kind,approach=near,actions=sorted(states),hurt=sorted(target),remaining=remaining)

def main():
    assert sha256(ELF.read_bytes()).hexdigest()==PIN
    modes=('body','locked','source-damage','source-zero-life','source-ko-flag','registered-eagle','unregistered',
           'wrong-kind','global-object','locked-stale','wrong-registry','locked-active-eagle','zero-life-projectile',
           'damaged-source-registered-eagle','own-registered-eagle','both-locked','source-already-locked','source-damage-and-locked-target')
    specs=[(slot,seat,armed,who,0,2) for slot in (0,1,2,3,4,16) for seat in (0,1) for armed in (0,1) for who in (0,1)]
    specs.extend((slot,seat,1,(slot+seat)%2,mode,system) for slot in (0,1,2,3,4,16) for seat in (0,1)
                 for mode in range(1,len(modes)) for system in ((1,2) if slot==4 else (2,)))
    specs.extend((4,seat,0,seat,mode,system) for seat in (0,1) for mode in (1,6,9,11) for system in (1,2))
    with tempfile.TemporaryDirectory() as tmp:
        d=Path(tmp);cpp=d/'play.cpp';exe=d/'play';cpp.write_text(DRIVER)
        subprocess.run(['c++','-std=c++20','-I',ROOT/'src',cpp,ROOT/'src/nakoruru_capture.cpp',BUILD/'libss6-runtime.a','-o',exe],check=True)
        r=subprocess.run([exe,ASSETS],input=''.join('%d %d %d %d %d %d\n'%s for s in specs),text=True,capture_output=True,check=True)
    with ProcessPoolExecutor(4) as pool:expected=list(pool.map(compare,specs))
    for spec,row,(values,_) in zip(specs,r.stdout.splitlines(),expected,strict=True):
        got=list(map(int,row.split()))
        assert got==values,(spec,modes[spec[4]],[(i,x,y) for i,(x,y) in enumerate(zip(got,values)) if x!=y])
    matches=[live(side,kind,dist) for side in (0,1) for kind,dist in [('down',40),('grab',40),('grab',0)]]
    report=dict(status='passed',elf=PIN,replay=sha256((BUILD/'ss6-match-replay').read_bytes()).hexdigest(),entries=len(specs),
                original_instructions=sum(s for _,s in expected),matches=matches,
                modes=modes,source_sha256=sha256((ROOT/'src/nakoruru_capture.cpp').read_bytes()).hexdigest(),scope='The complete Japanese 1ec420 entry dispatcher for all six supported rows. Compare both actors’ requests, 35 timers per actor, callbacks, overrides, lock flags, ACTs, submission to entity suppression, registry, body anchor and facing, linked-object flags and weapon ACT. Failure states are directly constructed. Six public two-player select-to-fight air inputs exercise hit, miss and recovery; the entire match scheduler is not executed by the isolated EE oracle.')
    (ROOT/'outputs/ss6-feasibility/nakoruru_capture_validation.json').write_text(json.dumps(report,indent=2)+'\n')
    print(len(specs),'original pair entries,',len(matches),'full air moves')
if __name__=='__main__':main()
