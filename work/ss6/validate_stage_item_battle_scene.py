#!/usr/bin/env python3
"""Drive the real item selection, two bomb throws and a ground detonation; compare scene pixels and elemental callbacks."""
import argparse
from collections import Counter
from hashlib import sha256
from itertools import groupby
import json
from pathlib import Path
import struct
import subprocess
import tempfile

from PIL import Image
from extract_versus_quotes import ORIGINAL
from validate_selected_combat import BUILD, CAPTURE, LIB, OUT, ROOT, SOURCE, capture, fixture, prefix
from validate_ten_element import CHILD, PARENT
from validate_thrown_stage_items import compile_probe
from validate_weapon_handling import setup

LINEUP=(0,1)
FIELDS=CHILD+(0x10c,0x110,0x114)
DRIVER=r"""
#include "local_versus.hpp"
#include <iostream>
using namespace ss6;
int main(int argc,char**argv){try{
    LocalVersus game(argv[1],-1,VersusMode::Console,{},true);
    unsigned tick=0,victim=std::stoul(argv[2]);std::array<unsigned,2> held{},previous{};
    auto out=[](auto v){std::cout<<' '<<+v;};
    while(std::cin>>held[0]>>held[1]){
        std::array<NormalizedPadSample,2> pad;
        for(unsigned s=0;s<2;++s)pad[s]={held[s],held[s]&~previous[s]};
        previous=held;game.tick(pad);++tick;if(tick<1550)continue;
        const auto& m=game.match();const auto& b=m.battle();const auto& d=b.stageItems;
        const auto& f=m.fighter(victim);const auto& a=f.actor;const auto& pool=b.entry.tasks;
        std::cout<<tick;out(b.stageItemsOption4c3828);out(d.courierActive());out(d.courier()[9]);out(d.itemCallback());
        out(d.item()[9]);out(d.itemIndex());out(m.fighter(0).actor.fieldA30);out(m.fighter(1).actor.fieldA30);
        for(unsigned s=0;s<3;++s){
            auto reg=s==2?std::span<const uint32_t>(b.objectTasks):std::span<const uint32_t>(m.fighter(s).storage.objectTasks);
            unsigned count=0;for(auto t:reg)if(t){
                auto& o=pool.objects.at(pool.tasks.at(t-1)[7]-1);if(o[51]!=5)continue;
                if(!count)for(unsigned i:{9,10,16,17,77,35})out(o[i]);
                ++count;
            }if(!count)for(unsigned i=0;i<6;++i)out(-1);out(count);
        }
        out(a.state194);out(a.flags23c);out(a.contactKind252);out(a.landingCount253);out(b.field140);out(b.gauges.delta46a908);
        auto parent=f.body.childParentWords();for(unsigned off:PARENT_FIELDS)out(parent[off/4]);
        for(auto t:b.objectTasks)if(t){
            const auto& task=pool.tasks.at(t-1);const auto& o=pool.objects.at(task[7]-1);
            if(o[51]!=7||(o[9]!=4&&o[9]!=5&&o[9]!=6)||o[0x118/4]!=victim+1)continue;
            out(task[0]);out(o[0x118/4]);for(unsigned off:ELEMENT_FIELDS)out(o[off/4]);
        }
        std::cout<<'\n';
    }
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}}
""".replace('PARENT_FIELDS','{'+','.join(map(str,PARENT))+'}').replace('ELEMENT_FIELDS','{'+','.join(map(str,FIELDS))+'}')


def pads(side=None,early=False):
    controls=prefix(LINEUP)
    controls[265][1]=128
    controls.extend([[0,0] for _ in range(2660-len(controls))])
    def hold(t,frames,left,right):
        for tick in range(t-1,t-1+frames):controls[tick]=[left,right]
    hold(1251,32,128,64);hold(1288,1,0,1024);hold(1841,1,2304,0)
    if side==0:
        hold(2363,30,128,0);hold(2398 if early else 2515,1,2304,0)
    else:
        hold(2363,25,128,64)
        if side==1:hold(2514,1,0,2304)
    return controls


def check_element(rows,victim):
    src,_=setup(victim,LINEUP[victim]);p,a,o,b=src.p,src.a,src.o,src.b
    reg=b+0x14c;p.memory[reg:reg+256]=bytes(256)
    for addr,name in ((0x46a9b0+2*0x1800,'aid_51.bin'),(0x1a60000,'act_51.bin')):
        d=(SOURCE/name).read_bytes();p.memory[addr:addr+len(d)]=d
    for addr,val in ((0x4751b8,0x1a60000),(0x46a9a8,51),(0x345188,0)):p.write(addr,val,4)
    counts=Counter();intervals=[];latched=[];seen=False;last=0
    for tick in range(2540,2661):
        row=rows[tick];prev=rows[tick-1];state,flags,element,generation,speed,delta=row[30:36]
        p.write(b+0x140,speed,4);p.write(0x46a908,delta,4)
        for off,w in zip(PARENT,prev[36:51]):p.write(o+off,w,4)
        src.run(0x147028,reg,64)
        for off,w in zip(PARENT,row[36:51]):p.write(o+off,w,4)
        p.write(a+0x194,state,4);p.write(a+0x23c,flags,4);p.write(a+0x252,element,1);p.write(a+0x253,generation,1)
        actual=row[51:]
        if actual and not seen:
            assert tick==2544 and element==1
            obj=actual[2:2+len(FIELDS)]
            center=[int(struct.unpack('<f',struct.pack('<I',obj[FIELDS.index(off)]))[0]) for off in (0x40,0x44)]
            src.run(0x16e218,a,element,*center);seen=True
        if state!=prev[30] and generation!=prev[33] and element==1:src.run(0x16e2c8,a,element,state>>16)
        src.run(0x146ef8,reg,64);src.run(0x1207d8);src.run(0x1470a8,reg,64)
        want=[];actions=[]
        for handle in struct.unpack_from('<64I',p.memory,reg):
            if not handle:continue
            obj=p.read(handle+28,4);action=p.read(obj+0x24,4)
            assert action in (4,5) and p.read(obj+0x118,4)==a
            want+=[p.read(handle,4),victim+1]+[p.read(obj+off,4) for off in FIELDS]
            actions.append(action);counts[action]+=1;last=tick
            if action==4 and p.read(obj+0x104,4)&0x18000==0x18000:
                assert [p.read(obj+off,4) for off in (0x10c,0x110,0x114)]==[6,0xfffffffa,29]
                latched.append(tick)
        assert actual==want,(victim,tick,len(actual),len(want),[(i,hex(w),hex(v)) for i,(w,v) in enumerate(zip(want,actual)) if v!=w][:12])
        if not intervals or intervals[-1][1]!=actions:intervals.append([tick,actions])
    assert seen and counts[4] and counts[5] and latched and intervals[-1][1]==[]
    return dict(victim=victim+1,original_impact_center=center,windows=intervals,final_sprite_tick=last,
                object_updates=dict(counts),common_attach_latch_ticks=latched,original_instructions=src.instructions)


def grouped(controls):
    return ''.join(f'{sum(1 for _ in group)} {left} {right}\n' for (left,right),group in groupby(map(tuple,controls)))


def verify_parcel(watch,draw,viewer,assets,tmp,p,stats,side,guard):
    # The first courier naturally delivers item 18 with this prefix. With the
    # owner within reach, A+D consumes it rather than performing a normal.
    controls=pads(side)[:1950]
    controls[1840]=[0,0]
    for i in range(22 if side==0 else 12):controls[1824+i][side]=(128,64)[side]
    controls[1855][side]=2304
    if guard:
        for i in range(1870,1888):controls[i][1-side]=(128,64)[side]
    victim=side^1
    data=subprocess.run([watch,assets,str(victim)],input=''.join(f'{a} {b}\n' for a,b in controls).encode(),
                        check=True,capture_output=True).stdout
    rows={r[0]:r for r in (list(map(int,line.split())) for line in data.splitlines())}
    flight=1873-side;col=9+7*side
    assert rows[1821][6]==18 and rows[1865][6]==18 and rows[1866][6]==-1
    assert rows[flight][col]==127 and rows[flight+1][col]==128
    assert rows[flight][col+6]==1 and rows[flight+20][col+6]==0
    before,after=rows[flight][7+victim],rows[flight+1][7+victim]
    assert (before-after)==(0 if guard else (12,11)[side])
    state=rows[flight+1][30]
    assert state==(2 if guard else 0x490002),(side,guard,hex(state))
    result=dict(scenario=f'item18-p{side+1}-'+('guard' if guard else 'hit'),pad_ticks=len(controls),
                pickup_tick=1866,first_flight=flight,contact=flight+1,victim_state=hex(state),hp=[before,after])
    if not guard:
        result['frames']=[capture(draw,viewer,assets,tmp,p,LINEUP,controls,flight-1,{'slot':2,'action':127,'steps':[]},stats)]
    return result


def main(opt):
    assets,viewer=opt.assets,opt.viewer
    hashes={key:sha256(f.read_bytes()).hexdigest() for key,f in [('runtime',LIB),('viewer',viewer)]}
    cases=[];pixel_counts=Counter()
    with tempfile.TemporaryDirectory() as td:
        tmp=Path(td);watch=compile_probe(tmp,'watch',DRIVER);draw=compile_probe(tmp,'draw',CAPTURE)
        p=fixture((*LINEUP,51))
        for bank,name in enumerate(('01HitFlash.bin','02Guard.bin','03etc.bin'),1):
            at=0x4a4810+(bank-1)*0x3da0;p.memory[at:at+0x3da0]=(SOURCE/name).read_bytes()
        for name,side,early in [('p1-throw',0,False),('p2-throw',1,False),('early-bounce',0,True),('ground',None,False)]:
            controls=pads(side,early);victim=1 if side==0 else 0
            data=subprocess.run([watch,assets,str(victim)],input=''.join(f'{a} {b}\n' for a,b in controls).encode(),
                                check=True,capture_output=True).stdout
            rows={r[0]:r for r in (list(map(int,line.split())) for line in data.splitlines())}
            assert rows[2361][1]==1 and rows[2361][23:25]==[0,0] and rows[2361][29]==2
            assert rows[2362][23]==76 and rows[2362][29]==2
            assert rows[2541][23]==(55 if side is None else 56)
            assert rows[2600][29]==0
            hp=rows[2544][7:9];want_hp={'p1-throw':[173,198],'p2-throw':[172,200],'early-bounce':[173,200],'ground':[172,198]}[name]
            assert hp==want_hp,(name,hp,want_hp)
            moments=[]
            for act,group in groupby(rows.values(),key=lambda r:r[23]):
                row=next(group)
                if row[0]>=2361:moments.append([row[0],act])
            if early:assert [act for _,act in moments[:6]]==[0,76,78,133,76,56]
            if side is not None and not early:assert [tick for tick,act in moments if act==78]==[(2532,2530)[side]]
            result=dict(scenario=name,pad_ticks=len(controls),hp_before=list(rows[2543][7:9]),hp_after=list(hp),battle_object_actions=moments)
            if side is not None and not early:result['element']=check_element(rows,victim)
            targets={'p1-throw':[(2366,76),(2536,78),(2547,56),(2556,4),(2575,5)],
                     'p2-throw':[(2536,78),(2548,56)],'early-bounce':[(2448,133)],'ground':[(2549,55)]}[name]
            for tick,act in targets:
                frame=capture(draw,viewer,assets,tmp,p,LINEUP,controls,tick-1,{'slot':2,'action':act,'steps':[]},pixel_counts)
                result.setdefault('frames',[]).append(frame)
                if name=='p1-throw' and tick==2547:
                    snapshot=tmp/'window.bmp'
                    subprocess.run([viewer,'--assets',assets,'--mode','select','--match-replay',tmp/'inputs.pad',
                                    '--snapshot',snapshot],check=True,stdout=subprocess.DEVNULL)
                    with Image.open(snapshot) as picture:
                        assert picture.size==(640,480)
                        picture.save(OUT/'stage-item-bomb-hit.png')
            if name=='p1-throw':(OUT/'stage-item-bomb-hit.replay').write_text(grouped(controls))
            cases.append(result);print(name,hp,moments,flush=True)
        for side in (0,1):
            for guard in (False,True):
                case=verify_parcel(watch,draw,viewer,assets,tmp,p,pixel_counts,side,guard)
                cases.append(case);print(case['scenario'],case['hp'],case['victim_state'],flush=True)
    assert hashes=={key:sha256(f.read_bytes()).hexdigest() for key,f in [('runtime',LIB),('viewer',viewer)]}
    result=dict(status='passed',source_elf_sha256=ORIGINAL,sha256=hashes,cases=cases,pixels=pixel_counts,
                scope='Normal selection through both human controllers. HP and registry transitions in four bomb scenarios plus two-sided hit and guard of naturally delivered item 18. Complete Japanese split impact/attachment object callbacks at the observed contact centers for both victims. Scene queue, original GS sprites, per-target visible pixel contribution on the packaged stage.')
    (OUT/'stage-item-bomb-battle-validation.json').write_text(json.dumps(result,indent=2)+'\n')
    print(dict(pixel_counts),flush=True)


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--viewer',type=Path,default=OUT/'native-viewer/ss6-viewer')
    ap.add_argument('--assets',type=Path,default=OUT/'native-viewer/assets')
    main(ap.parse_args())
