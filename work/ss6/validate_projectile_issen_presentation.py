#!/usr/bin/env python3
"""Compare the native route-7 callback with the Japanese spark/voice branch during Issen."""
import itertools
import json
from pathlib import Path
import subprocess
import tempfile

from validate_battle_sound import OBJECTS,actor,put,sound_oracle
from validate_contact_presentation import ASSETS,ROOT,SOURCE_HASH,buffered_stdout,initialize_effects
from validate_dash_motion import digest

OUT=ROOT/'outputs/ss6-feasibility'
LIB=ROOT/'work/ss6/build-native/libss6-runtime.a'
DRIVER=r'''
#include "native_match.hpp"
#include <iostream>
using namespace ss6;
int main(int argc,char** argv){
    unsigned seat,kind,issen,group;
    while(std::cin>>seat>>kind>>issen>>group) {
        VersusLineup team{};team[seat]={2,3,0};team[seat^1]={0,3,1};
        NativeMatch match(argv[1],-1,VersusMode::Console,nullptr,{3,3},team,0);
        for(int i=0;i<500;++i)match.tick({});
        auto& pools=match.battle_.entry.tasks;
        auto& attacker=match.fighters_[seat];auto& defender=match.fighters_[seat^1];
        auto from=match.collisionPlayer(seat),to=match.collisionPlayer(seat^1);
        from.objectKind=kind?2:seat;to.objectKind=seat^1;
        uint32_t h=0;
        if(kind) {
            h=pools.allocateObject(0x1396);
            auto& projectile=pools.objects[h-1];projectile[3]=seat;projectile[4]=seat;
            projectile[5]=projectile[6]=2;projectile[9]=559;
            projectile[0xcc/4]=2;projectile[0xd0/4]=8;
            from.objectFlags104=from.objectFlags108=0;
        }
        attacker.actor.state194=issen?0x260001:0;
        defender.body.sound34=0x4012;match.sounds_.beginFrame();
        ContactEvent e{};e.route=7;e.centerX=240;e.centerY=60;e.auxiliary=4;
        e.a.fields=decodeJudgment(group?0x2b000000u:0x28600000u);e.b.fields.type=1;
        ContactMarks sm{from.objectKind,from.objectFlags104,from.objectFlags108,0},tm{to.objectKind,to.objectFlags104,to.objectFlags108,0};
        auto previous=pools.tasks;
        if(!match.resolveStrike(e,from,to,sm,tm,h))return 3;
        std::cout<<defender.body.sound34;
        for(unsigned i=0;i<pools.tasks.size();++i){
            const auto& t=pools.tasks[i];
            if(!previous[i][1] && t[0]==0x124898)std::cout<<' '<<t[8]-0x100;
        }
        std::cout<<'\n';
    }
}
'''


def original(seat,kind,issen,group):
    p=sound_oracle().probe;initialize_effects(p);buffered_stdout(p)
    for address in (0x1123a8,0x112570,0x11e290):p.run(address)
    for i,name in enumerate(('01HitFlash.bin','02Guard.bin','03etc.bin')):
        at=0x4a4810+i*0x3da0;p.memory[at:at+0x3da0]=(ASSETS/name).read_bytes();p.write(0x4c3510+4*(i+1),i+2,4)
    event,child=0x1e05000,0x1e09000;victim=OBJECTS[seat^1]
    put(p,event,[(0x40,child if kind else OBJECTS[seat]),(0x68,victim),(4,240),(8,60),
                 (0x20,10),(0x24,4 if group else 0),(0x28,0 if group else 2),(0x2c,0),(0x48,1)])
    put(p,child,[(0xcc,2),(0x10,seat),(0xc,seat),(0x14,2),(0x24,559)])
    put(p,victim,[(0x34,0x4012)])
    put(p,actor(seat),[(0x194,0x260001 if issen else 0),(0xa10,2)])
    effects=[]
    p.run(0x156fb8,[event,0],limit=300000,observe=lambda pc:effects.append(p.registers[4]) if pc==0x1242c0 else None)
    return [p.read(victim+0x34,4),*effects]


def main():
    exe_hash=digest(ASSETS.parent/'SLPS_255.59');assert exe_hash==SOURCE_HASH
    # One real group-0 hit box from 02 ACT559. Group 4 is a separate branch
    # isolation for retained voice; do not imply it is present in that ACT.
    import struct
    aid,act,jdg=[(ASSETS/f'{s}_02.bin').read_bytes() for s in ('aid','act','jdg')]
    first,end=struct.unpack_from('<2h',aid,559*2)
    assert any(struct.unpack_from('<I',jdg,idx*16)[0]==0x28600000 for rec in range(first,end)
               for idx in struct.unpack_from('<'+'h'*(struct.unpack_from('<H',act,rec*60+30)[0]&7),act,rec*60+14))
    cases=list(itertools.product((0,1),repeat=4))
    with tempfile.TemporaryDirectory() as td:
        cpp=Path(td)/'main.cpp';cpp.write_text(DRIVER);exe=Path(td)/'probe'
        # Call the same real strike resolver with the controlled simultaneous
        # states; keep its production visibility and the shipping binary intact.
        subprocess.run(['c++','-std=c++20','-O2','-fno-access-control','-I',ROOT/'src',cpp,LIB,'-o',exe],check=True)
        raw=subprocess.check_output([exe,OUT/'native-viewer/assets'],text=True,input=''.join('%s %s %s %s\n'%c for c in cases))
    result=[]
    for case,row in zip(cases,raw.splitlines(),strict=True):
        values=list(map(int,row.split()));want=original(*case)
        assert values==want,(case,values,want)
        assert (11 in values[1:])==(not case[1] and bool(case[2]))
        result.append(dict(seat=case[0],source_kind=2 if case[1] else case[0],owner_issen=bool(case[2]),
                           group=4 if case[3] else 0,retained_voice=values[0],spawned_descriptors=values[1:]))
    doc=dict(passed=True,source_sha256=exe_hash,runtime_sha256=digest(LIB),viewer_sha256=digest(OUT/'native-viewer/ss6-viewer'),
             cases=result,scope='Controlled contact fixtures through the production NativeMatch::resolveStrike and full original 156fb8. Both seats, source body or thrown ice, neutral or Issen owner, and an existing interruptible voice. Group 0 uses on-disc 02 ACT559 hit metadata. Group 4 isolates the voice exception. No claim of an input-only simultaneous Issen encounter.')
    (OUT/'projectile-issen-presentation-validation.json').write_text(json.dumps(doc,indent=2)+'\n')
    print('passed',len(cases),result[:8])

if __name__=='__main__':main()
