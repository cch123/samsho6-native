#!/usr/bin/env python3
"""Check the depth producer, including its game-side inputs and final body ordering."""
import itertools
import json
from pathlib import Path
import struct
import subprocess
import tempfile

from round_entry_oracle import fixture
from validate_jump_motion import ASSETS, ELF, ORIGINAL, ROOT, WORK, digest

LIB = WORK / 'build-native/libss6-runtime.a'
DRIVER = r'''
#include "native_match.hpp"
#include "fighter_depth.hpp"
#include <iostream>
using namespace ss6;
void emit(uint32_t x){std::cout<<x<<' ';}
int main(int argc,char** argv) {
    if(argc!=2)return 2;
    ActionBank bank(argv[1],true);FighterTables depthTables(argv[1]);
    std::array<MatchFighter,2> f{MatchFighter(bank),MatchFighter(bank)};
    auto ref=[](MatchFighter& f){return RoundPlayerRef{f.body,f.actor,f.input,f.config,f.storage,f.objects};};
    std::array<RoundPlayerRef,2> refs{ref(f[0]),ref(f[1])};
    BattleRoundState b;
    std::string op;
    while(std::cin>>op) {
        if(op=="world") {
            unsigned side;std::cin>>side;
            NativeMatch m(argv[1],0);std::array<uint32_t,2> last{};
            for(unsigned tick=1;tick<=570;++tick) {
                std::array<NormalizedPadSample,2> pads{};
                const unsigned mask=tick==501?(16|(side?64:128)):tick==532?256:0;
                pads[side]={mask,mask&~last[side]};last[side]=mask;m.tick(pads);
                if(tick<500)continue;
                emit(tick);emit(m.battle().entry.attackMarker12d2300);
                for(unsigned i=0;i<2;++i) {
                    const auto& x=m.fighter(i);const auto& a=x.actor;const auto& t=x.body.timeline;
                    for(auto v:{a.state194,a.state1a4,a.flags23c,t.action().id(),t.clock().step,t.clock().flags104,
                                x.body.zWords[0],x.body.depthOffsetB0,x.hits})emit(v);
                }
                for(auto h:m.objectDraws().sorted()) {
                    const auto& o=m.objectDraws().slots[h-1];
                    if(o[81]==0&&o[0xcc/4]<2){emit(o[0xcc/4]);emit(o[0xb0/4]);}
                }
                std::cout<<'\n';
            }
        } else if(op=="probe") {
            std::cin>>b.entry.attackMarker12d2300;
            for(unsigned i=0;i<2;++i) {
                auto& x=f[i];auto& a=x.actor;unsigned act,flags;
                std::cin>>a.state194>>a.state1a4>>a.flags23c>>act>>flags>>x.body.depthOffsetB0;
                x.body.timeline.start(bank.get(act));x.body.setFlags(flags,0);
                a.auxiliaryObject04=25+i;b.entry.tasks.objects[24+i][0xb0/4]=0x40a00000;
            }
            // Sparse owner registries and an object in both the owner and
            // common registries exercise the original three-pass write order.
            for(unsigned i=0;i<18;++i) {
                auto& o=b.entry.tasks.objects[i];b.entry.tasks.tasks[i][7]=i+1;
                std::cin>>o[0xcc/4]>>o[0x104/4]>>o[0xb0/4]>>o[0x130/4];
                if(i<16)f[i/8].storage.objectTasks[2*(i%8)]=i+1;
                else b.objectTasks[i]=i+1;
            }
            b.objectTasks[20]=4;
            updateFighterDepths(b,refs,depthTables);
            for(const auto& x:f)emit(x.body.depthOffsetB0);
            for(unsigned i=0;i<18;++i)emit(b.entry.tasks.objects[i][0xb0/4]);
            for(unsigned i:{24u,25u})emit(b.entry.tasks.objects[i][0xb0/4]);
            std::cout<<'\n';
        }else if(op=="override") {
            std::array<unsigned,2> actions{};uint32_t d0,d1;
            std::cin>>actions[0]>>actions[1]>>d0>>d1;
            applyHaohmaruDepthOverride(depthTables,actions,d0,d1);emit(d0);emit(d1);std::cout<<'\n';
        }else return 3;
    }
}
'''

def floats(value):
    return struct.unpack('<I',struct.pack('<f',value))[0]

def main():
    assert digest(ELF)==ORIGINAL
    p,a,o,b=fixture()
    p.finite_model=True
    actors=(a,a+0xf2c)
    bodies=(o,o+0x1000)
    for i in range(2):
        p.write(actors[i],bodies[i],4)
        p.write(actors[i]+0xa24,i,4)
        p.write(bodies[i]+0xcc,i,4)
    def write_body(i,values):
        state,alias,actor_flags,act,step,flags,z,depth=values
        for off,v in ((0x194,state),(0x1a4,alias),(0x23c,actor_flags)):
            p.write(actors[i]+off,v,4)
        for off,v in ((0x24,act),(0x28,step),(0x104,flags),(0x48,z),(0xb0,depth)):
            p.write(bodies[i]+off,v,4)
    calls=0
    def depth(marker):
        nonlocal calls
        p.write(0x12d2300,marker,4)
        _,n=p.run(0x148550,[b],limit=120000)
        calls+=n
        return [p.read(obj+0xb0,4) for obj in bodies]
    commands=['world 0','world 1']
    cases=[]
    for n,(state,act,mark,mask) in enumerate(itertools.product(
        (0,1,0x290000,0x340000,2),(0,234,235),(0,1),range(4))):
        main=(state,0x230000 if n%3==1 else 0)
        acts=(act,(0,234,235)[n%3])
        rows=[(main[i],1,(0x1a00000 if n%5==i else 0),acts[i],0x20000 if mask>>i&1 else 0,
               floats(11.25+i*42)) for i in range(2)]
        objs=[((2,4,3,9,10,6,10,7)[i%8],0x20000 if (n+i)%5==0 else 0,
               floats(12.5+i),(-7+i)&0xffffffff) for i in range(18)]
        cases.append((mark,rows,objs))
        values=[mark,*itertools.chain.from_iterable(rows),*itertools.chain.from_iterable(objs)]
        commands.append('probe '+' '.join(map(str,values)))
    overrides=[]
    for a0,a1,pair in itertools.product(range(531,539),range(531,539),((3,-7),(-7,3),(9,9))):
        item=(a0,a1,*map(floats,pair));overrides.append(item)
        commands.append('override '+' '.join(map(str,item)))
    with tempfile.TemporaryDirectory() as temp:
        source=Path(temp)/'probe.cpp';exe=Path(temp)/'probe'
        source.write_text(DRIVER)
        subprocess.run(['c++','-std=c++20','-ffp-contract=off','-I',ROOT/'src',source,LIB,'-o',exe],check=True)
        out=subprocess.run([exe,ASSETS],input='\n'.join(commands)+'\n',text=True,capture_output=True,check=True)
    lines=iter([int(x) for x in row.split()] for row in out.stdout.splitlines())
    traces=[]
    for side in range(2):
        foreground=[];impact=None
        for tick in range(500,571):
            row=next(lines);assert len(row)==24 and row[0]==tick
            for i in range(2):write_body(i,row[2+9*i:10+9*i])
            want=depth(row[1])
            assert want==[row[9],row[18]],(side,tick,want,row)
            p.run(0x1207d8)
            for body in bodies:p.run(0x1207e8,[body,0])
            p.run(0x122bc0)
            ordered=[p.read(0x4a2258+4*i,4) for i in range(2)]
            assert row[20:]==[p.read(addr+off,4) for addr in ordered for off in (0xcc,0xb0)]
            foreground.append(row[22])
            if impact is None and row[10+9*side]:impact=tick
        assert impact==542 and foreground[42]==side
        traces.append(dict(attacker=side+1,impact=impact,front_runs=[(v+1,len(list(g))) for v,g in itertools.groupby(foreground)]))
    # Compare all mutated layer words with original owner, common, and actor+4
    # objects. Fixed-depth bodies use fractional sentinels to check preservation.
    objects=[0x1b10000+0x200*i for i in range(18)]
    for i,obj in enumerate(objects):
        task=0x1b18000+i*0x40;p.write(task+0x1c,obj,4)
        registry=b+0x29c+0x108*(i//8)+8*(i%8) if i<16 else b+0x14c+4*i
        p.write(registry,task,4)
    p.write(b+0x14c+4*20,0x1b18000+3*0x40,4)
    aux=[0x1b14000,0x1b14400]
    for i in range(2):p.write(actors[i]+4,aux[i],4)
    for mark,rows,objs in cases:
        for i,(state,alias,af,act,flags,initial) in enumerate(rows):
            write_body(i,(state,alias,af,act,0,flags,0,initial));p.write(aux[i]+0xb0,floats(5),4)
        for obj,values in zip(objects,objs):
            for off,val in zip((0xcc,0x104,0xb0,0x130),values):p.write(obj+off,val,4)
        want=depth(mark)+[p.read(obj+0xb0,4) for obj in objects+aux]
        got=next(lines);assert got==want,(rows,got,want)
    for a0,a1,d0,d1 in overrides:
        for i,(act,d) in enumerate(((a0,d0),(a1,d1))):
            p.write(bodies[i]+0x24,act,4);p.write(bodies[i]+0xb0,d,4)
        p.run(0x148900,limit=30000)
        assert next(lines)==[p.read(obj+0xb0,4) for obj in bodies]
    assert next(lines,None) is None
    report=dict(status='passed',world_updates=142,world=traces,sparse_registry_cases=len(cases),
                raw_body_action_overrides=len(overrides),original_148550_instructions=calls,source_sha256=ORIGINAL,runtime_sha256=digest(LIB),
                validator_sha256=digest(Path(__file__)),scope='Unmodified resource00 depth producer, original queue and sort versus both native player slots, including actual jumping A input, first impact, hurt playback, and return to standing. Seeded cases compare body, owner, common and auxiliary depth words.')
    (ROOT/'outputs/ss6-feasibility/fighter_depth_validation.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()
