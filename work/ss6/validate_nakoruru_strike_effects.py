#!/usr/bin/env python3
"""Validate Nakoruru's personal and common ACT attachments and throw world-effect lifetimes."""
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from hashlib import sha256
import json
from pathlib import Path
import struct
import subprocess
import tempfile

from validate_nakoruru_strikes import controls
from validate_selected_combat import prefix
from validate_nakoruru_eagle_attacks import sequence
from validate_haohmaru_special import BUILD, ELF, RES, ROOT
from validate_dash_motion import PIN
from validate_weapon_handling import setup

FIELDS=(0xcc,0x24,0x28,0x2c,0x40,0x44,0x108)
DRIVER=r'''
#include "local_versus.hpp"
#include <iostream>
using namespace ss6;
int main(int argc,char** argv) {try {
 const unsigned side=unsigned(std::stoi(argv[2])),start=unsigned(std::stoi(argv[3]));
 LocalVersus session(argv[1],-1,VersusMode::Console,{},true);
 std::array<uint32_t,2> prev{},keys{};
 unsigned ordinal=0;
 while(std::cin>>keys[0]>>keys[1]) {
  std::array<NormalizedPadSample,2> pads;
  for(unsigned i=0;i<2;++i)pads[i]={keys[i],keys[i]&~prev[i]};
  prev=keys;session.tick(pads);if(++ordinal<start)continue;
  auto& match=session.match();auto& b=match.battle();auto& f=match.fighter(side);auto& other=match.fighter(1-side);
  auto motion=f.body.timeline.motion();
  std::cout<<ordinal<<' '<<std::bit_cast<uint32_t>(motion.x)<<' '<<std::bit_cast<uint32_t>(motion.y)<<' '
           <<std::bit_cast<uint32_t>(other.body.timeline.motion().x)<<' '<<b.camera.left<<' '<<b.camera.right<<' '<<f.body.timeline.action().id()<<' '
           <<other.body.timeline.action().id()<<' '<<f.actor.stateTable()<<' '<<other.actor.stateTable()<<' '<<other.actor.fieldA30;
  for(auto& t:b.entry.tasks.tasks)if(t[0]==0x124898&&(t[8]==0x10f||t[8]==0x11d)&&t[1]&&t[1]!=0x12)std::cout<<" w"<<t[8]-0x100;
  auto print=[&](auto& registry){for(auto task:registry)if(task){
   const auto& t=b.entry.tasks.tasks.at(task-1);const auto& o=b.entry.tasks.objects.at(t[7]-1);
   if(!((o[0xcc/4]==6&&o[0x24/4]==794)||(o[0xcc/4]==7&&o[0x24/4]==0&&o[0x118/4]==side+1)))continue;
   for(auto off:OFFSETS)std::cout<<' '<<o[off/4];
  }};print(f.storage.objectTasks);print(b.objectTasks);
  std::cout<<'\n';
 }
 }catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}}
'''.replace('OFFSETS','{'+','.join(map(str,FIELDS))+'}')


def read_driver(exe,side,before,pads):
    proc=subprocess.run([exe,RES,str(side),str(before)],input=''.join('%d %d\n'%tuple(row) for row in pads),text=True,capture_output=True)
    assert proc.returncode==0,(side,len(proc.stdout.splitlines()),proc.stderr)
    rows=[r.split() for r in proc.stdout.splitlines()]
    return [([int(v) for v in r[:11]],[int(v[1:]) for v in r[11:] if v.startswith('w')],
             [int(v) for v in r[11:] if not v.startswith('w')]) for r in rows]


def trace(job):
    exe,side,state=job
    pre,words,both=controls(side,state,'miss')
    rows=read_driver(exe,side,len(pre),pre+both)
    src,reg=setup(side,1);p,a,obj,b=src.p,src.a,src.o,src.b
    common=b+0x14c
    p.memory[common:common+256]=bytes(256)
    for name,at in [('aid',0x46a9b0+0x3000),('act',0x1a60000)]:
        data=(RES/f'{name}_51.bin').read_bytes();p.memory[at:at+len(data)]=data
    p.write(0x4751b8,0x1a60000,4);p.write(0x46a9a8,51,4);p.write(0x345188,0,4)
    camera,_=p.run(0x140040)
    samples=Counter();steps={0:set(),794:set()};births=[]
    for t,(key,(prev,_,_),(row,_,observed)) in enumerate(zip(words,rows,rows[1:]),1):
        for which,n in ((reg,48),(common,64)):src.run(0x147028,which,n)
        p.write(obj+0x40,prev[1],4);p.write(obj+0x1040,prev[3],4)
        p.write(camera+16,row[4],4);p.write(camera+20,row[5],4)
        src.frame(key)
        for which,n in ((reg,48),(common,64)):src.run(0x146ef8,which,n)
        # Source 1404b0 consumes the ACT request; 1404c0 creates the actual
        # typed object and applies offset and facing before the drawable pass.
        p.write(obj+0x40,row[1],4);p.write(obj+0x44,row[2],4)
        flags=p.read(obj+0x104,4)
        if flags&0x8000:births.append([t,p.read(obj+0x10c,4),p.read(obj+0x110,4),p.read(obj+0x114,4)])
        src.run(0x16d9c8,a);p.write(obj+0x104,flags&~0x18000,4)
        src.run(0x1207d8)
        for which,n in ((reg,48),(common,64)):src.run(0x1470a8,which,n)
        expected=[]
        for which,n in ((reg,48),(common,64)):
            for task in struct.unpack_from(f'<{n}I',p.memory,which):
                if task:
                    child=p.read(task+28,4);kind=p.read(child+0xcc,4);act=p.read(child+0x24,4)
                    assert (kind,act) in ((6,794),(7,0)),(side,state,t,kind,act)
                    expected.extend(p.read(child+off,4) for off in FIELDS)
                    samples[act]+=1;steps[act].add(p.read(child+0x28,4))
        assert expected==observed,(side,state,t,expected,observed)
        if t>5 and row[6]==0 and not expected:break
    assert samples[794] and bool(samples[0])==(state<=66) and row[6]==0
    return dict(player=side+1,state=state,frames=t,object_ticks=dict(samples),steps={k:sorted(v) for k,v in steps.items()},births=births,original_instructions=src.instructions)


def thrown(exe,side,air):
    if air:
        pads=prefix((1-side,side))+[(128,64)]*40+[(0,0)]*10
        n=len(pads);forward=(128,64)[side]
        for t in range(200):
            pair=(16,16) if t==0 else (forward|2048,0) if t==13 else (0,0)
            pads.append(pair[::-1] if side else pair)
    else:pads,n=sequence(side,77,'hit',True)
    rows=read_driver(exe,side,n,pads)
    actions={i:set() for i in (6,7)};changes=[];seen=set()
    for row,particles,_ in rows:
        for i in actions:actions[i].add(row[i])
        if not changes or changes[-1][1]!=particles:changes.append([row[0]-n,particles]);seen.update(particles)
    expected={29} if air else {15,29}
    assert expected<=seen and (571 if air else 682) in actions[6] and (1310 if air else 1307) in actions[7],(side,air,changes,actions)
    assert row[8:10]==[0,0] and row[10]<200 and not particles,(side,row,particles)
    return dict(player=side+1,air_throw=air,remaining_life=row[10],actions=[sorted(v) for v in actions.values()],world_tasks=changes)


def main():
    assert sha256(ELF.read_bytes()).hexdigest()==PIN
    with tempfile.TemporaryDirectory() as td:
        tmp=Path(td);path=tmp/'trace.cpp';exe=tmp/'trace';path.write_text(DRIVER)
        subprocess.run(['c++','-std=c++20','-ffp-contract=off','-O2','-I',ROOT/'src',path,BUILD/'libss6-runtime.a','-o',exe],check=True)
        with ProcessPoolExecutor(4) as pool:
            cases=[]
            for r in pool.map(trace,[(exe,s,i) for s in range(2) for i in range(64,70)]):cases.append(r);print(r['player'],r['state'],r['object_ticks'],flush=True)
        throws=[thrown(exe,side,air) for side in range(2) for air in (False,True)]
    report=dict(status='passed',elf_sha256=PIN,runtime_sha256=sha256((BUILD/'libss6-runtime.a').read_bytes()).hexdigest(),cases=cases,throws=throws,
                scope='Weapon trail794 and common smoke0, through original 16d9c8/16dcc0 allocations, 147028/146ef8/1470a8 clock passes and disappearance. Entire mixed seat match uses true pad input, the isolated source child oracle is fed the published actor X/Y and camera bounds. Also traces actual visible lifetime of world15/29 tasks and idle recovery during the 632146+C and jumping forward+D throws.')
    (ROOT/'outputs/ss6-feasibility/nakoruru_strike_effects_validation.json').write_text(json.dumps(report,indent=2)+'\n')
    print(len(cases),'strike traces and',len(throws),'throws')

if __name__=='__main__':main()
