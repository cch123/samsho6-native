#!/usr/bin/env python3
"""Actual pad discard, approach, pickup and recovery against the Japanese release."""
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import json
import struct
import subprocess
import tempfile

from validate_directional_slash import setup_actor
from validate_dash_motion import ASSETS, ELF, PIN, PROBE, ROOT, Original, digest

REPORT = ROOT/'outputs/ss6-feasibility/weapon_pickup_validation.json'
LIBRARY = PROBE.parent/'libss6-runtime.a'

# A read-only observer of the same match used by the window. The source registry
# retires the weapon before draw submission and releases its task one tick later.
DRIVER = r'''
#include "native_match.hpp"
#include "input_permissions.hpp"
#include <bit>
#include <iostream>
int main(int argc, char** argv) {
    unsigned slot=std::stoul(argv[2]);
    if(argc==4) {
        ss6::InputPermissions rules(argv[1]);
        uint32_t body, n;
        while(std::cin>>body>>n) {
            ss6::PermissionActor actor, other;
            ss6::PermissionContext ctx;
            actor.x=std::bit_cast<float>(body);
            for(unsigned i=0;i<n;++i) {
                uint32_t group, index, kind, act, bits;
                std::cin>>group>>index>>kind>>act>>bits;
                if(!group)ctx.ownObjects.at(index)=ss6::PermissionObject{int(kind),0,int(act),0,std::bit_cast<float>(bits)};
            }
            std::cout<<rules.condition(1,actor,other,{},ctx)<<'\n';
        }
        return 0;
    }
    ss6::NativeMatch m(argv[1]);
    std::array<uint32_t,2> previous{};
    unsigned n, first, second, lastWeaponTask=0;
    while(std::cin>>n>>first>>second) {
        const std::array held{first,second};
        for(unsigned i=0;i<n;++i) {
            std::array<ss6::NormalizedPadSample,2> pads;
            for(unsigned j=0;j<2;++j)pads[j]={held[j],held[j]&~previous[j]};
            m.tick(pads);
            previous=held;
        }
        const auto& f=m.fighter(slot);
        const auto& a=f.actor;
        const auto& t=f.body.timeline;
        const auto& c=t.clock();
        const auto& pools=m.battle().entry.tasks;
        std::cout<<a.state194<<' '<<t.action().id()<<' '<<c.step<<' '<<c.fractionalTime
                 <<' '<<bool(a.flags23c&0x1000)<<' '<<std::bit_cast<uint32_t>(t.motion().x)
                 <<' '<<std::bit_cast<uint32_t>(t.motion().y)<<' '<<bool(c.objectFlags&0x80000);
        for(unsigned i:{0u,1u,2u,5u})std::cout<<' '<<a.callbacks260[i];
        uint32_t count=0, action=0, x=0, draw=0;
        for(auto h:f.storage.objectTasks)if(h) {
            const auto& o=pools.objects.at(pools.tasks.at(h-1)[7]-1);
            if(o[0xcc/4]!=4)continue;
            ++count;action=o[0x24/4];x=o[0x40/4];lastWeaponTask=h;
        }
        for(const auto& d:m.objectDraws().active())
            if(d[0xcc/4]==4&&d[0xc/4]==slot)++draw;
        std::cout<<' '<<count<<' '<<action<<' '<<x<<' '<<draw<<' '
                 <<(lastWeaponTask?pools.tasks.at(lastWeaponTask-1)[1]:0)<<'\n';
    }
}
'''

def bits(value):
    return struct.unpack('<I',struct.pack('<f',value))[0]

def number(word):
    return struct.unpack('<f',struct.pack('<I',word))[0]

def run_driver(exe, slot, commands, mode=()):
    data=''.join(' '.join(map(str,line))+'\n' for line in commands)
    out=subprocess.run([exe,ASSETS,str(slot),*mode],input=data,text=True,capture_output=True,check=True)
    return [list(map(int,line.split())) for line in out.stdout.splitlines()]

def ranges(exe, slot):
    middle=bits(256.25)
    lo, hi=bits(232.25), bits(280.25)
    own=(0,3,4,467,middle)
    cases=[('center',middle,[own],1),('lower',lo,[own],1),('upper',hi,[own],1),
           ('below',lo-1,[own],0),('above',hi+1,[own],0),
           ('inside-lower',lo+1,[own],1),('inside-upper',hi-1,[own],1),
           ('empty',middle,[],0),('opponent-sword',middle,[(1,0,4,467,middle)],0),
           ('airborne-pending-landing',middle,[(0,0,4,466,middle)],0),
           ('first-weapon-too-far',middle,[(0,0,4,467,bits(400)),own],0),
           ('first-weapon-airborne',middle,[(0,0,4,466,middle),own],0),
           ('skip-nonweapon-and-holes',middle,[(0,0,6,467,middle),own],1),
           ('last-slot',middle,[(0,47,4,467,middle)],1)]
    commands=[(x,len(entries),*(j for entry in entries for j in entry)) for _,x,entries,_ in cases]
    actual=run_driver(exe,slot,commands,('range',))
    s=Original(slot);p=s.p;instructions=0
    for (name,x,entries,expected),row in zip(cases,actual,strict=True):
        for side in range(2):
            reg=s.b+0x29c+side*0x108
            p.memory[reg:reg+48*4]=bytes(48*4)
        p.write(s.o+0x40,x,4)
        for n,(group,index,kind,act,position) in enumerate(entries):
            reg=s.b+0x29c+(slot^group)*0x108
            task,object_=0x1d04000+52*n,0x1d02000+320*n
            p.write(reg+4*index,task,4);p.write(task+0x1c,object_,4)
            for off,value in ((0xcc,kind),(0x24,act),(0xc4,467),(0x40,position),(0x44,bits(120))):
                p.write(object_+off,value,4)
        value,count=p.run(0x140e48,[slot]);instructions+=count
        assert row==[value]==[expected],(slot,name,row,value)
    return dict(player=slot+1,cases=[name for name,*_ in cases],original_instructions=instructions)

def natural(args):
    exe,slot,case=args
    forward=(128,64)[slot]
    walk=0 if case=='distant-light' else 20
    button={'near-medium':512,'near-heavy':1024,'near-kick':2048}.get(case,256)
    pads=[forward|8]+[0]*125+[forward]*walk+[0]*4+[button]+[0]*26+[1024]
    source=setup_actor(slot);p=source.p
    reg=source.b+0x29c+slot*0x108
    # setup_actor resets the shared pools. Remove the three renderer-only
    # startup handles that belonged to their prior allocation generation.
    p.memory[reg:reg+48*4]=bytes(48*4)
    for object_,coord in ((source.o,(240,400)[slot]),(source.o+0x1000,(400,240)[slot])):
        p.write(object_+0x40,bits(coord),4)
    rows=run_driver(exe,slot,[(500,0,0)]+[(1,0,mask) if slot else (1,mask,0) for mask in pads])[1:]
    press=131+walk
    steps=[];idle=None;last_task=0
    for tick,(pad,row) in enumerate(zip(pads,rows,strict=True),1):
        source.frame(pad)
        source.run(0x146ef8,reg,48)
        task=p.read(reg,4)
        action=weapon_x=0
        if task:
            last_task=task
            obj=p.read(task+0x1c,4)
            source.run(0x11d8e0,obj)
            action=p.read(obj+0x24,4);weapon_x=p.read(obj+0x40,4)
        a,o=source.a,source.o
        expected=[p.read(a+0x194,4),p.read(o+0x24,4),p.read(o+0x28,4),p.read(o+0x2c,4),
                  int(bool(p.read(a+0x23c,4)&0x1000)),p.read(o+0x40,4),p.read(o+0x44,4),
                  int(bool(p.read(o+0x38,4)&0x80000))]
        expected += [p.read(a+0x260+i*4,4) for i in (0,1,2,5)]
        expected += [int(bool(task)),action,weapon_x]
        assert row[:15]==expected,(slot,case,tick,row,expected)
        assert row[15]==int(bool(task)),(slot,case,tick,'draw',row[15],task)
        if tick==press:
            if case=='pickup':
                assert row[1]==136 and row[4] and not task and row[16]==p.read(last_task+4,4)==2
                assert rows[tick-2][14]==row[5]
            else:
                assert not row[4] and task
                assert row[1]=={'distant-light':201,'near-medium':202,'near-heavy':202,'near-kick':205}[case]
        if tick>=press and case=='pickup' and row[1]==136:
            if not steps or steps[-1][1]!=row[2]:
                steps.append([tick-press+1,row[2]])
            if row[0]==0 and idle is None:idle=tick-press+1
    if case=='pickup':
        assert steps==[[1,0],[10,1],[12,2],[22,3]] and idle==26 and rows[-2][1]==0 and rows[-1][1]==190
    return dict(player=slot+1,case=case,ticks=len(rows),press=button,press_action=rows[press-1][1],
                before_x=number(rows[press-2][5]),weapon_x=number(rows[press-2][14]),
                after_x=number(rows[press-1][5]),animation_step_changes=steps,actionable=idle,
                original_instructions=source.instructions)

def main():
    assert digest(ELF)==PIN
    with tempfile.TemporaryDirectory() as tmp:
        cpp=Path(tmp)/'observe.cpp';exe=Path(tmp)/'observe'
        cpp.write_text(DRIVER)
        subprocess.run(['c++','-std=c++20','-ffp-contract=off','-I',ROOT/'src',cpp,LIBRARY,'-o',exe],check=True)
        bounds=[ranges(exe,i) for i in range(2)]
        scenarios=[(exe,i,case) for i in range(2) for case in
                   ('pickup','distant-light','near-medium','near-heavy','near-kick')]
        with ProcessPoolExecutor(max_workers=4) as pool:
            rows=list(pool.map(natural,scenarios))
    result=dict(status='passed',elf_sha256=PIN,library_sha256=digest(LIBRARY),validator_sha256=digest(Path(__file__)),
                scope='Both human pad slots from real discard to recovery, plus injected registry geometries for the input predicate. Japanese ELF actor, object callback/reclamation/ACT commit; native window match and sorted submission count. No hardware renderer or audio comparison.',
                range_fixtures=bounds,cases=rows,frames=sum(r['ticks'] for r in rows),
                original_instructions=sum(r['original_instructions'] for r in rows+bounds))
    REPORT.write_text(json.dumps(result,indent=2)+'\n')
    print(len(rows),'pad replays,',sum(len(r['cases']) for r in bounds),'range fixtures,',result['frames'],'ticks PASS')

if __name__=='__main__':main()
