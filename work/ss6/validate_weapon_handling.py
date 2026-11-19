#!/usr/bin/env python3
"""Real neutral-start taunt/discard and independent PS2 caster and weapon callbacks."""
import argparse
from concurrent.futures import ProcessPoolExecutor
import json
from pathlib import Path
import struct
import subprocess
import tempfile

from validate_dash_motion import ASSETS, ELF, PIN, ROOT, Original, digest
from knockdown_oracle import initialize_effects
from validate_haohmaru_special import ContactOracle

BUILD=ROOT/'work/ss6/build-native'
OUT=ROOT/'outputs/ss6-feasibility'
CHILD=(0xc,0x10,0x14,0x20,0x24,0x28,0x2c,0x30,0x38,0x40,0x44,0x50,0x54,0x5c,0x60,0x70,0xc0,0xcc,0xd0,0x104,0x108)
DRIVER=r'''
#include "native_match.hpp"
#include <bit>
#include <iostream>
int main(int argc,char** argv){try{
    ss6::NativeMatch match(argv[1]);
    uint32_t previous[2]={};
    unsigned ticks,who,first,second;
    while(std::cin>>ticks>>who>>first>>second){
        const std::array held{first,second};
        for(unsigned j=0;j<ticks;++j){
            std::array<ss6::NormalizedPadSample,2> pads;
            for(unsigned i=0;i<2;++i){pads[i]={held[i],held[i]&~previous[i]};previous[i]=held[i];}
            match.tick(pads);
        }
        const auto& f=match.fighter(who);const auto& a=f.actor;const auto& c=f.body.timeline.clock();
        auto out=[](uint32_t v){std::cout<<v<<' ';};
        for(uint32_t v:{a.state194,uint32_t(f.body.timeline.action().id()),c.step,c.fractionalTime,
                        a.flags23c&0x1000,uint32_t(a.characterBytesF22[1]),std::bit_cast<uint32_t>(f.body.timeline.motion().x),
                        std::bit_cast<uint32_t>(f.body.timeline.motion().y),c.flags104&0x100})out(v);
        for(auto v:a.callbacks260)out(v);
        const auto& pool=match.battle().entry.tasks;
        unsigned found=0;
        for(auto task:f.storage.objectTasks)if(task){
            const auto& t=pool.tasks.at(task-1);const auto& o=pool.objects.at(t[7]-1);
            if(o[0xcc/4]!=4)continue;
            ++found;out(t[0]);out(t[5]);out(o[0x118/4]);
            for(unsigned off:{0xc,0x10,0x14,0x20,0x24,0x28,0x2c,0x30,0x38,0x40,0x44,0x50,0x54,0x5c,0x60,0x70,0xc0,0xcc,0xd0,0x104,0x108})out(o[off/4]);
        }
        out(found);std::cout<<'\n';
    }
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}}
'''


def setup(slot, character=0):
    src=Original(slot, character)
    p,a,o,b=src.p,src.a,src.o,src.b
    initialize_effects(p)
    # The lifecycle fixture has introduction tasks. A live round has already
    # reclaimed them before these commands; reinitialize their actual pools.
    reg=b+0x29c+slot*0x108
    p.memory[reg:reg+192]=bytes(192)
    for pc in (0x1123a8,0x112570,0x11e290):
        src.run(pc)
    p.write(0x46a9a0+slot*4,character,4)
    p.write(0x4751b4,p.read(0x4751b0,4),4)
    p.memory[0x46a9b0+0x1800:0x46a9b0+0x3000]=p.memory[0x46a9b0:0x46a9b0+0x1800]
    for addr,v in ((o+0xc,slot),(o+0x10,slot),(o+0x20,slot),(a+0xa28,slot),(o+0x70,0x3f800000),(0x46a908,256),(a+0xa30,200),(o+0x104,p.read(o+0x104,4)&~0x200)):
        p.write(addr,v,4)
    return src,reg


def scenario(arg):
    exe,slot,mode=arg
    front,back=(128,64) if slot==0 else (64,128)
    if mode=='taunt':
        controls=[back|8]+[0]*229
    else:
        controls=[front|8]+[0]*113+[back|8]+[0]*190
    def pair(mask):
        return (mask,0) if slot==0 else (0,mask)
    commands=['500 '+str(slot)+' 0 0']+[f'1 {slot} {a} {b}' for a,b in map(pair,controls)]
    raw=subprocess.run([exe,ASSETS],input='\n'.join(commands)+'\n',text=True,capture_output=True,check=True)
    rows=[list(map(int,line.split())) for line in raw.stdout.splitlines()]
    src,reg=setup(slot);p,a,o=src.p,src.a,src.o
    p.write(o+0x40,rows[0][6],4)
    p.write(o+0x1040,struct.unpack('<I',struct.pack('<f',240 if slot else 400))[0],4)
    actions=[];seen=[];first_weapon=None
    for frame,mask in enumerate(controls,1):
        src.run(0x147028,reg,48)
        src.frame(mask)
        src.run(0x146ef8,reg,48)
        src.run(0x1207d8)
        src.run(0x1470a8,reg,48)
        state=p.read(a+0x194,4)
        expected=[state,p.read(o+0x24,4),p.read(o+0x28,4),p.read(o+0x2c,4),p.read(a+0x23c,4)&0x1000,p.read(a+0xf23,1),
                  p.read(o+0x40,4),p.read(o+0x44,4),p.read(o+0x104,4)&0x100]
        expected+=[p.read(a+0x260+4*j,4) for j in range(7)]
        count=0
        for task in struct.unpack_from('<48I',p.memory,reg):
            if not task:continue
            obj=p.read(task+28,4)
            if p.read(obj+0xcc,4)!=4:continue
            assert p.read(obj+0x118,4)==a
            count+=1
            expected += [p.read(task,4),p.read(task+20,4),slot+1]+[p.read(obj+off,4) for off in CHILD]
            if first_weapon is None:
                first_weapon=frame
                x,y=struct.unpack_from('<2f',p.memory,obj+0x40)
                assert x==struct.unpack_from('<f',p.memory,o+0x40)[0]+(57,-57)[slot] and y==0
        expected.append(count)
        got=rows[frame]
        assert got==expected,(slot,mode,frame,[(i,v,w) for i,(v,w) in enumerate(zip(got,expected)) if v!=w],len(got),len(expected))
        current=(got[0]>>16,got[1],got[4]>>12,got[5],count)
        if not seen or seen[-1][1:]!=list(current):
            seen.append([frame,*current])
        if not actions or actions[-1]!=got[1]:
            actions.append(got[1])
    assert first_weapon==(None if mode=='taunt' else 61)
    assert actions==([150,0] if mode=='taunt' else [135,1,151,1])
    return dict(player=slot+1,mode=mode,visits=len(controls),ee_instructions=src.instructions,first_weapon=first_weapon,timeline=seen)


def interrupted(build,slot,delay):
    front=(128,64)[slot]
    steps=[(500,0,0),(32,front,front^192),(10,0,0),(1,front|8,0)]
    steps += [(1,0,256 if tick==delay else 0) for tick in range(140)]
    if slot:steps=[(n,b,a) for n,a,b in steps]
    commands=''.join(f'{n} {a} {b}\n' for n,a,b in steps)
    native=subprocess.run([build/'ss6-match-replay',ASSETS,'--contact-fields'],input=commands,text=True,capture_output=True,check=True)
    rows=[line.split() for line in native.stdout.splitlines()]
    events=ContactOracle().contacts(rows,1-slot)
    assert len(events)==1
    hit=events[0]
    frame=next(r for r in rows if int(r[0])==hit['frame'])
    life=int(frame[9+slot*10])
    reaction=int(frame[5+slot*10])
    armed=bool(int(frame[23+26*slot+5])&0x1000)
    # The resolver runs before the player's callback. At the hold marker
    # itself a hit prevents creation; one tick later the weapon stays down.
    assert (reaction,armed)==((338,True) if delay==54 else (339,False))
    assert life==192 and int(rows[-1][5+slot*10])==int(not armed)
    return dict(player=slot+1,contact=hit,visits_since_command=int(frame[0])-542,armed_after_hit=armed,hurt_action=reaction)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--build',type=Path,default=BUILD)
    opt=parser.parse_args()
    assert digest(ELF)==PIN
    lib=opt.build/'libss6-runtime.a'
    with tempfile.TemporaryDirectory() as tmp:
        folder=Path(tmp);source=folder/'probe.cpp';exe=folder/'probe'
        source.write_text(DRIVER)
        subprocess.run(['c++','-std=c++20','-O2','-I',ROOT/'src',source,lib,'-o',exe],check=True)
        cases=[(exe,i,m) for i in range(2) for m in ('taunt','discard')]
        with ProcessPoolExecutor(4) as pool:
            results=list(pool.map(scenario,cases))
    data=dict(status='passed',elf_sha256=PIN,runtime_sha256=digest(lib),scenarios=results,
              interrupted=[interrupted(opt.build,i,t) for i in range(2) for t in (54,55)],
              scope='Both sides of a native versus round, raw pad through action selection and natural recovery. Independent unmodified original actor, 16fe20 allocation, 147028/146ef8/1470a8 object updates. Compare armed state, taunt count, state/ACT/step/clock, all callback words, actual position, weapon task tag/handler/owner, position and action, object flags and lifetime each tick.')
    (OUT/'weapon_handling_validation.json').write_text(json.dumps(data,indent=2)+'\n')
    for case in results:print(case['player'],case['mode'],case['visits'],case['timeline'])


if __name__=='__main__':main()
