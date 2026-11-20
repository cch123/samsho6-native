#!/usr/bin/env python3
"""Play Ten's CC-D chain and compare both element sprites against their Japanese callbacks."""
import json
import struct
import subprocess
import tempfile
from pathlib import Path

from validate_weapon_handling import ASSETS, BUILD, ELF, OUT, PIN, ROOT, digest, setup

# Keep live raw ACT-derived fields, flags, clock, sprite offsets and the
# victim contact generation. Allocator handles/host addresses are excluded.
CHILD=(0xc,0x10,0x14,0x20,0x24,0x28,0x2c,0x30,0x38,0x40,0x44,0x4c,0x50,0x54,0x58,0x5c,0x60,0x70,0xb0,0xc0,0xcc,0xec,0xf0,0x104,0x108,0x128,0x12c,0x130,0x134)
DRIVER=r'''
#include "native_match.hpp"
#include <bit>
#include <iostream>
int main(int argc,char** argv) {try {
 unsigned victim=std::stoi(argv[2]),attacker=1-victim;
 std::array<unsigned,2> spirits{};spirits[attacker]=3;
 ss6::NativeMatch match(argv[1],60,ss6::VersusMode::Console,nullptr,spirits);
 unsigned n,p0,p1;std::array<uint32_t,2> previous{};
 while(std::cin>>n>>p0>>p1) {
    std::array<uint32_t,2> held{p0,p1};
    for(unsigned i=0;i<n;++i){
      std::array<ss6::NormalizedPadSample,2> pads;
      for(int side=0;side<2;++side)pads[side]={held[side],held[side]&~previous[side]};
      match.tick(pads);previous=held;
    }
    const auto& b=match.battle();const auto& f=match.fighter(victim);const auto& a=f.actor;
    auto parent=f.body.childParentWords();auto out=[](auto v){std::cout<<' '<<+v;};
    std::cout<<match.updates;out(match.fighter(attacker).hits);out(a.fieldA30);out(a.state194);out(a.flags23c);
    out(a.contactKind252);out(a.landingCount253);out(b.field140);out(b.gauges.delta46a908);out(a.timerDelta);
    for(unsigned off:{0x30,0x38,0x40,0x44,0x48,0x4c,0x50,0x54,0x58,0x5c,0x60,0x64,0x68,0x6c,0xb0})out(parent[off/4]);
    for(auto task:b.objectTasks)if(task){
      const auto& t=b.entry.tasks.tasks.at(task-1);const auto& o=b.entry.tasks.objects.at(t[7]-1);
      if(o[0xcc/4]!=7 || (o[0x24/4]!=16 && o[0x24/4]!=17))continue;
      out(t[0]);out(o[0x118/4]);
      for(unsigned off:OFFSETS)out(o[off/4]);
    }
    std::cout<<'\n';
 }
 }catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}}
'''.replace('OFFSETS','{'+','.join(map(str,CHILD))+'}')
PARENT=(0x30,0x38,0x40,0x44,0x48,0x4c,0x50,0x54,0x58,0x5c,0x60,0x64,0x68,0x6c,0xb0)

def pads(side):
    def pair(n,a=0,b=0):return (n,b,a) if side else (n,a,b)
    f=(128,64)[side]
    return [pair(500),pair(40,f,f^192),pair(8)]+[pair(1,{0:768,15:1024,31:1024,52:2048}.get(i,0)) for i in range(165)]


def check(exe,victim):
    raw=subprocess.run([exe,ASSETS,str(victim)],input=''.join('%d %d %d\n'%r for r in pads(1-victim)),
                       capture_output=True,text=True)
    assert raw.returncode==0,raw.stderr
    rows=[list(map(int,line.split())) for line in raw.stdout.splitlines()]
    src,_=setup(victim);p,a,o,b=src.p,src.a,src.o,src.b;reg=b+0x14c
    for name,at in [('aid',0x46a9b0+2*0x1800),('act',0x1a60000)]:
        data=(ASSETS/f'{name}_51.bin').read_bytes();p.memory[at:at+len(data)]=data
    p.write(0x4751b8,0x1a60000,4);p.write(0x46a9a8,51,4);p.write(0x345188,0,4)
    p.memory[reg:reg+256]=bytes(256)
    events=[];counts={16:0,17:0};first=None;last=None;steps={16:set(),17:set()};previous=None
    for row in rows:
        if row[0]<610:previous=row;continue
        tick,hits,hp,state,flags,element,generation,speed,delta,actor_delta=row[:10]
        # Source callback and renderer read the owner's actual live motion.
        # Move gets the preceding body state. Draw sees the current body.
        p.write(b+0x140,speed,4);p.write(0x46a908,delta,4)
        for off,value in zip(PARENT,previous[10:25]):p.write(o+off,value,4)
        src.run(0x147028,reg,64)
        for off,value in zip(PARENT,row[10:25]):p.write(o+off,value,4)
        p.write(a+0x194,state,4);p.write(a+0x23c,flags,4);p.write(a+0x252,element,1);p.write(a+0x253,generation,1)
        native=row[25:]
        if first is None and native:
            first=tick;assert tick==616 and hits==4 and element==2
            first_sprite=native[2:2+len(CHILD)]
            center=[int(struct.unpack('<f',struct.pack('<I',first_sprite[CHILD.index(off)]))[0]) for off in (0x40,0x44)]
            src.run(0x16e218,a,2,*center)
        if state!=previous[3] and generation!=previous[6] and element==2:
            src.run(0x16e2c8,a,2,state>>16)
        src.run(0x146ef8,reg,64);src.run(0x1207d8);src.run(0x1470a8,reg,64)
        expected=[];actions=[]
        for task in struct.unpack_from('<64I',p.memory,reg):
            if not task:continue
            obj=p.read(task+0x1c,4);act=p.read(obj+0x24,4)
            assert p.read(obj+0x118,4)==a and act in (16,17)
            expected += [p.read(task,4),victim+1]+[p.read(obj+off,4) for off in CHILD]
            counts[act]+=1;actions.append(act);steps[act].add(p.read(obj+0x28,4))
        if expected!=native:
            raise AssertionError((victim,tick,len(expected),len(native),actions,hex(state),element,generation,events,
                [(i,hex(v),hex(w),('handler/owner',*CHILD)[(i%(len(CHILD)+2))-1]) for i,(v,w) in enumerate(zip(expected,native)) if v!=w][:8]))
        if events==[] or events[-1][1]!=actions:events.append([tick,actions])
        if actions:last=tick
        previous=row
    assert all(counts.values()) and first<last and events[-1][1]==[]
    return dict(victim=victim+1,from_hit=first,last_sprite=last,raw_center=center,original_steps={k:sorted(v) for k,v in steps.items()},
                object_ticks=counts,changes=events,original_instructions=src.instructions)


if __name__=='__main__':
    assert digest(ELF)==PIN
    with tempfile.TemporaryDirectory() as td:
        path=Path(td);cpp=path/'probe.cpp';exe=path/'probe';cpp.write_text(DRIVER)
        subprocess.run(['c++','-O2','-std=c++20','-ffp-contract=off','-I',ROOT/'src',cpp,BUILD/'libss6-runtime.a','-o',exe],check=True)
        reports=[check(exe,i) for i in range(2)]
    report=dict(status='passed',source_sha256=PIN,sides=reports,
                scope='Two real CCD pad matches. Source 16e218/16e2c8 constructors, 16e3b8, 147028/146ef8/1470a8 and common AID/ACT. Uses observed collision center and fighter transforms as inputs; compares independent ACT records, offsets, positions, flags, damage-state and generation, draw lifetime through removal.')
    (OUT/'ten-element-validation.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(reports))
