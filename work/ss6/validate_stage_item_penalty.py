#!/usr/bin/env python3
"""Verify both controller seats throwing the naturally delivered defense-down item and attacking again."""
import json
import struct
import subprocess
import tempfile
from pathlib import Path

from validate_dash_motion import ELF, PIN, ROOT, digest
from validate_finishing_blow import actor, CHILD, OBJECTS, put, QUEUE
from validate_hanzo_knockdown import FireContact
from validate_nakoruru_combat import MixedContactOracle
from validate_stage_item_battle_scene import pads
from validate_thrown_stage_items import compile_probe

OUT=ROOT/'outputs/ss6-feasibility'
ASSETS=OUT/'native-viewer/assets'
REPLAY=ROOT/'work/ss6/build-native/ss6-match-replay'

DRIVER=r'''
#include "local_versus.hpp"
#include <iostream>
using namespace ss6;
int main(int,char** argv) {
    unsigned side=std::stoi(argv[2]),seed=std::stoi(argv[3]);
    LocalVersus game(argv[1],-1,VersusMode::Console,{},true);
    std::array<uint32_t,2> last{},held{};unsigned t=0;
    while(std::cin>>held[0]>>held[1]) {
        ++t;
        if(t==1900 && seed) {
            // Change only the starting counters for the saturation boundary.
            const_cast<StateEntryActor&>(game.match().fighter(1-side).actor).fieldA50=seed;
            const_cast<StateEntryActor&>(game.match().fighter(side).actor).characterBytesF22[6]=98+side;
        }
        std::array<NormalizedPadSample,2> sample;
        for(unsigned i=0;i<2;++i)sample[i]={held[i],held[i]&~last[i]};
        last=held;game.tick(sample);
        if(t<1839||t>2090)continue;
        const auto& m=game.match();const auto& b=m.battle();const auto& f=m.fighter(side);
        const auto& v=m.fighter(1-side).actor;
        std::cout<<t<<' '<<b.stageItems.itemIndex()<<' '<<f.actor.pickedItemA40<<' '<<v.fieldA50
                 <<' '<<unsigned(f.actor.characterBytesF22[6])<<' '<<unsigned(v.contactKind252)
                 <<' '<<v.bodyColor8c<<' '<<v.landingCount253+0<<' '<<v.fieldA2c;
        unsigned count=0;
        for(auto q:b.itemNotices.draws())if(q.v==102&&q.u==317&&q.width==131)++count;
        std::cout<<' '<<count;
        for(auto task:f.storage.objectTasks)if(task) {
            const auto& p=b.entry.tasks;
            const auto& o=p.objects.at(p.tasks.at(task-1)[7]-1);
            if(o[0xcc/4]==5)for(auto word:o)std::cout<<' '<<word;
        }
        std::cout<<'\n';
    }
}
'''

def inputs(side):
    q=pads()[:1840]
    for i in range(8):q[1310+34*i][0]=(256,512,1024,2048)[i%4]
    q.extend([[0,0] for _ in range(320)])
    for i in range(12):q[1840+i][0]=64
    for i in range(49):q[1840+i][1]=64
    q[1897][side]=2304
    for i in range(1990,2003):q[i][side]=(128,64)[side]
    q[2010][side]=1024
    return q

class ItemOracle(MixedContactOracle):
    def __init__(self):
        super().__init__((0,1))
        # Use the same live effect pools and audio tables as the full Japanese
        # 155a88 comparison. The common item ACT/JDG lives in its own slot.
        self.probe=FireContact(0).probe
        self.banks.append(tuple((ASSETS/f'{key}_51.bin').read_bytes() for key in ('aid','act','jdg')))

    def setup_bodies(self,prev):
        p=self.probe
        for s in range(2):
            self.install_player(prev,s)
            put(p,actor(s),[(0x10c,5),(0xa34,200)])

    def event(self,prev,words,side):
        p=self.probe;self.setup_bodies(prev)
        obj=CHILD;struct.pack_into('<80I',p.memory,obj,*words)
        slot=words[3]
        assert slot==2 and words[4]==side and words[0xd0//4]==109
        # Both compressed fighter JDG lists from install_player keep their
        # own pointers. Only the common object's original indices need remapping.
        aid,act,jdg=self.banks[slot]
        record=(struct.unpack_from('<h',aid,2*words[9])[0]+words[10])*60
        refs=0x17a0400;bank=0x17c0000
        p.memory[refs:refs+16]=act[record+14:record+30]
        p.memory[bank:bank+len(jdg)]=jdg
        put(p,obj,[(0xbc,refs),(0x118,actor(side))])
        p.write(0x4751e0+slot*4,bank,4)
        p.write(0x12d2698,0,4);p.run(0x1536e8,[obj,OBJECTS[1-side]]);p.run(0x1544a0)
        return next(e for e in (QUEUE+108*i for i in range(p.read(0x12d2698,4))) if p.read(e,4)==7)

def case(exe,side,seed):
    seq=inputs(side);data=''.join(f'{x} {y}\n' for x,y in seq)
    arr={r[0]:r for r in (list(map(int,line.split())) for line in
         subprocess.check_output([exe,ASSETS,str(side),str(seed)],input=data,text=True).splitlines())}
    live=[None]+[r.split() for r in subprocess.check_output([REPLAY,ASSETS,'--mode','select','--contact-fields'],
          input=''.join('1 '+s for s in data.splitlines(keepends=True)),text=True).splitlines()]
    victim=1-side;col=9+10*victim
    assert arr[1840][1]==7
    t=next(i for i in range(1905,1935) if arr[i][5]==6)
    old,now=arr[t-1],arr[t]
    assert old[2]==7 and len(old)==90
    oracle=ItemOracle();p=oracle.probe
    event=oracle.event(live[t-1],old[10:],side)
    put(p,actor(victim),[(0xa50,old[3])]);p.write(actor(side)+0xf28,old[4],1)
    assert p.run(0x155850,[event])[0]==0
    notices=[]
    def observe(pc):
        if pc==0x1b5b80:notices.append(tuple(p.registers[4:7]))
    _,ops=p.run(0x156ad8,[event],limit=500000,observe=observe)
    assert p.read(actor(victim)+0xa38,4)==0 and live[t-1][col]==live[t][col]
    assert [p.read(actor(victim)+0xa50,4),p.read(actor(side)+0xf28,1)]==now[3:5]
    assert now[3:5]==[min(seed+20,100),min(old[4]+1,99)]
    assert notices==[(1,int(float(live[t-1][7+10*victim])),80)]
    # The victim's pending bit is consumed by 149e9c in this same tick.
    # Its temporary color has no particle ACT. The damage modifier survives it.
    assert p.read(actor(victim)+0x248,4)&0x400
    assert now[5:9]==[6,0xff6030b0,(old[7]+1)%16,6],(side,t,now[:10])
    labels=[i for i in arr if arr[i][9]]
    assert labels==list(range(t+1,t+60)),(side,labels)
    assert arr[1989][5:9][0]==0 and arr[1989][3]==min(seed+20,100)
    result=dict(player=side+1,initial_penalty=seed,pickup=next(i for i in arr if arr[i][2]==7),
                impact=t,penalty=now[3],throw_count_before=old[4],throw_count_after=now[4],
                item_hit_damage=0,first_label=labels[0],last_label=labels[-1],original_route_instructions=ops)
    if seed:return result
    follow=[]
    for i in range(2011,2080):
        if live[i][10+10*side]==live[i-1][10+10*side]:continue
        oracle.setup_bodies(live[i-1]);p.write(0x12d2698,0,4)
        for a,b in (OBJECTS,OBJECTS[::-1]):p.run(0x1536e8,[a,b])
        p.run(0x1544a0)
        hit=next(e for e in (QUEUE+108*j for j in range(p.read(0x12d2698,4))) if p.read(e,4)==7 and p.read(e+0x40,4)==OBJECTS[side])
        damage=[]
        for penalty in (0,20):
            oracle.setup_bodies(live[i-1])
            p.write(actor(victim)+0xa50,penalty,4)
            p.run(0x155a88,[hit,1],stop_before={0x155bb8},limit=500000)
            damage.append(p.read(actor(victim)+0xa38,4))
        actual=int(live[i-1][col])-int(live[i][col])
        assert actual==damage[1] and damage[0]<actual,(side,i,damage,actual)
        follow.append(dict(tick=i,normal_damage=damage[0],actual_damage=actual))
    assert follow
    result['following_heavy']=follow
    return result

def main():
    assert digest(ELF)==PIN
    with tempfile.TemporaryDirectory() as td:
        exe=compile_probe(Path(td),'penalty',DRIVER)
        cases=[case(exe,s,seed) for s in range(2) for seed in (0,90,100)]
    report=dict(elf=PIN,viewer=digest(OUT/'native-viewer/ss6-viewer'),cases=cases)
    (OUT/'stage-item-penalty-validation.json').write_text(json.dumps(report,indent=2)+'\n');print(cases)

if __name__=='__main__':main()
