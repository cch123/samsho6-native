#!/usr/bin/env python3
"""Compare original 16bb38/16bb88/16c250/16c2b0 with the native pickup and throw."""
from concurrent.futures import ProcessPoolExecutor
import json
from pathlib import Path
import struct
import subprocess
import tempfile

from validate_dash_motion import ASSETS, ELF, PIN, ROOT, digest
from validate_weapon_handling import setup

LIB = ROOT/'work/ss6/build-native/libss6-runtime.a'
REPORT = ROOT/'outputs/ss6-feasibility/stage-item-contact-validation.json'
FLOOR, BUSY, SLOT = 0x132c4bc, 0x132c218, 0x1e80000
OBJ = (0x24,0xc4,0xd0,0x40,0x44)
DRIVER = r'''
#include "battle_round.hpp"
#include "sound_selection.hpp"
#include "stage_item_contact.hpp"
#include "thrown_stage_item.hpp"
#include <iostream>
int main(int,char** argv) {try {
    unsigned seat,character,armed;int kind,gate,bomb;
    while(std::cin>>seat>>character>>armed>>kind>>gate>>bomb) {
        ss6::BattleRoundState b;
        auto& tasks=b.entry.tasks;tasks.initializeOwners();tasks.initializeTasks();tasks.initializeObjects();
        ss6::ActionBank clips(argv[1],true,character);ss6::PlayerObject body(clips),otherBody(clips);
        ss6::StateEntryActor a,opponent;ss6::AuxiliaryObjects objects(argv[1],{character,character,51});
        ss6::SoundSelection sound(argv[1]);std::array<uint32_t,48> reg{};
        ss6::WeaponLockActorContext world{otherBody,opponent,b.camera,0,objects,reg};
        ss6::GroundStateFrame frame{};frame.battle=&b;frame.weaponLock=&world;frame.sound=&sound;
        b.entry.player=seat;b.gauges.words910[2]=1;
        a.flags23c=(armed?0x1000:0)|(gate==5?0x80:0);opponent.flags23c=gate==4?0x80:0;
        a.flags248=0x800;a.pickedItemA40=999;a.bodyState128=42;a.pendingDamageA38=2;
        b.gameMode=gate==6?0:3;b.timeOption13c=gate==2?3:0;b.field08=gate==3?1:0;
        b.timers.values[0]=(gate>=1&&gate<=3)?0:90;
        body.timeline.setPosition(320,0);body.resourceSlot0c=seat;body.ownerCC=seat;
        body.timeline.setObjectFlags(0x10000000|(seat<<19),0,0);
        b.stageItems.start(kind<0?0:kind,320,0,b.camera);
        if(kind>=0) {
            ss6::ObjectDrawQueue draws;
            for(int n=0;b.stageItems.itemIndex()==-1&&n<600;++n) {
                draws.beginFrame();b.stageItems.visit(b.gauges,objects,draws);
            }
            if(b.stageItems.itemIndex()!=kind)return 2;
        }
        if(bomb) {
            ss6::spawnStageBomb(objects,tasks,b.objectTasks,320);
            for(auto t:b.objectTasks)if(t)objects.commitRequested(tasks.objects[tasks.tasks[t-1][7]-1]);
            auto& first=tasks.objects[tasks.tasks[b.objectTasks[0]-1][7]-1];
            first[0x24/4]=bomb==1?76:bomb==2?133:78;
        }
        ss6::beginStageItemPickup(body,a);
        auto row=[&](bool recover) {
            auto word=[](uint32_t w){std::cout<<w<<' ';};const auto& c=body.timeline.clock();
            for(auto w:{uint32_t(a.queuedActionA3c),uint32_t(a.pickedItemA40),uint32_t(a.pendingDamageA38),uint32_t(a.bodyState128),
                    uint32_t(b.stageItems.itemIndex()),uint32_t(b.stageItems.busy()),uint32_t(recover),a.flags248&0x800,
                    uint32_t(body.timeline.action().id()),c.step,c.fractionalTime,c.endReached,c.flags104&0x8101})word(w);
            for(unsigned n:{0,1,2,5})word(a.callbacks260[n]);
            int sfx=-1;for(auto& e:sound.events())if(e.kind==ss6::BattleSoundKind::Sample)sfx=e.tone;word(sfx);
            for(auto registry:{std::span<const uint32_t>(reg),std::span<const uint32_t>(b.objectTasks)}) {
                for(auto t:registry)if(t) {
                    const auto& obj=tasks.objects.at(tasks.tasks.at(t-1)[7]-1);
                    if(obj[0xcc/4]==5)for(auto off:{0x24,0xc4,0xd0,0x40,0x44})word(obj[off/4]);
                }
            }
            std::cout<<'\n';
        };
        row(false);
        for(unsigned n=0;n<90;++n) {
            ss6::GroundStateRuntime::commitAction(body,a);body.commitRequested();
            body.animate(256);body.move(256);sound.beginFrame();
            bool recover=ss6::updateStageItemPickup(body,a,b.entry,frame);row(recover);
            if(recover||a.callbacks260[0]==0x169a50)break;
        }
        std::cout<<".\n";
    }
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}}
'''

def source(arg):
    seat,ch,armed,kind,gate,bomb=arg
    src,reg=setup(seat,ch);p,a,o,b=src.p,src.a,src.o,src.b
    for addr,file in ((0x46a9b0+2*0x1800,'aid_51.bin'),(0x1a40000,'act_51.bin')):
        data=(ASSETS/file).read_bytes();p.memory[addr:addr+len(data)]=data
    for addr,v in ((0x4751b8,0x1a40000),(0x46a9a8,51),(0x4c3808,0 if gate==6 else 3),
                   (SLOT,a),(SLOT+4,src.other),(SLOT+8,-1),(a+0x23c,0x1000*armed+0x80*(gate==5)),
                   (src.other+0x23c,0x80*(gate==4)),(a+0x248,0x800),(a+0xa40,999),(o+0x128,42),
                   (a+0xa38,2),(FLOOR,kind),(BUSY,1),(b+0x13c,3 if gate==2 else 0),(b+8,int(gate==3)),
                   (b+0x114,0 if 1<=gate<=3 else 90),(o+0x38,0x10000000|seat<<19),(o+0x104,0)):
        p.write(addr,v,4)
    p.write(0x43d061,100,1);struct.pack_into('<f',p.memory,o+0x40,320)
    p.memory[b+0x14c:b+0x24c]=bytes(256)
    if bomb:
        # Allocate real shared objects. Deliberately change the first action
        # in the third fixture to exercise the source's first-object rule.
        struct.pack_into('<f',p.memory,0x132c398,320)
        src.run(0x141f18,1)
        for t, in struct.iter_unpack('<I',p.memory[b+0x14c:b+0x24c]):
            if t:src.run(0x11d958,p.read(t+28,4))
        obj=p.read(p.read(b+0x14c,4)+28,4)
        assert p.read(obj+0xcc,4)==5
        p.write(obj+0x24,(76,133,78)[bomb-1],4)
    src.run(0x16bb38,SLOT)
    def row(recover,tone):
        words=[p.read(a+d,4) for d in (0xa3c,0xa40,0xa38)]+[p.read(o+0x128,4),p.read(FLOOR,4),p.read(BUSY,4),
              int(recover),p.read(a+0x248,4)&0x800]+[p.read(o+d,4) for d in (0x24,0x28,0x2c,0xc0)]+[p.read(o+0x104,4)&0x8101]
        words.extend(p.read(a+0x260+4*i,4) for i in (0,1,2,5));words.append(tone&0xffffffff)
        for pool,size in ((reg,48),(b+0x14c,64)):
            for t in struct.unpack_from(f'<{size}I',p.memory,pool):
                if t:
                    obj=p.read(t+28,4)
                    if p.read(obj+0xcc,4)==5:words.extend(p.read(obj+j,4) for j in OBJ)
        return words
    rows=[row(False,-1)]
    for tick in range(90):
        src.run(0x149918,a);src.run(0x11d8e0,o);src.run(0x11d730,o);src.run(0x11d6c8,o)
        observed=[]
        def trace(pc):
            if pc==0x169810:observed.append(('recover',0))
            if pc==0x1e7b70:observed.append(('tone',p.registers[5]&0xffffffff))
        _,n=p.run(p.read(a+0x260,4),[SLOT],observe=trace,limit=500000)
        src.instructions+=n
        recovered=('recover',0) in observed
        rows.append(row(recovered,next((x for event,x in observed if event=='tone'),-1)))
        if recovered or p.read(a+0x260,4)==0x169a50:break
    else:raise AssertionError(('pickup stuck',arg))
    return rows,src.instructions

def inputs(arg):
    """Exercise the real 1495e8 input pipeline, including inclusive range edges."""
    seat,ch=arg;checked=[]
    for offset,mask,expect in [(0,0x900,True),(-36,0x900,True),(36,0x8000,True),(-36.25,0x900,False),
                             (36.25,0x8000,False)]+[(0,1<<k,False) for k in range(8,13)]:
        src,_=setup(seat,ch);p,a,o=src.p,src.a,src.o
        x,=struct.unpack_from('<f',p.memory,o+0x40)
        struct.pack_into('<f',p.memory,0x132c398,x+offset)
        p.write(FLOOR,0,4);p.write(BUSY,1,4);p.write(0x4c3808,3,4)
        src.frame(0);src.frame(mask)
        state=p.read(a+0x194,4);act=p.read(o+0x24,4)
        assert (state==0x230001 and act==152)==expect,(seat,ch,offset,mask,state,act)
        checked.append([offset,mask,state,act])
    return dict(seat=seat,character=ch,cases=checked)

# Segment durations are real controller inputs from the public character and
# stage select entry. All four cases start with a heavy hit to the recipient.
FOOD_ROUTES = (
    (1,0,2929,156,171,[(32,128,64),(5,0,0),(1,1024,0),(513,0,0),(42,128,0),(1051,0,0),(23,0,64)]),
    (0,1,5118,173,176,[(32,128,64),(5,0,0),(1,0,1024),(75,0,0)]+[(1,256,0),(25,0,0)]*3+[(1,256,0),(3637,0,0),(27,128,0)]),
    (1,2,2950,156,167,[(32,128,64),(5,0,0),(1,1024,0),(75,0,0),(1,0,256),(25,0,0),(1,0,256),(972,0,0),(9,64,128),(29,64,0),(502,0,0),(36,0,64)]),
    (1,3,5099,156,187,[(32,128,64),(5,0,0),(1,1024,0),(75,0,0)]+[(1,0,256),(25,0,0)]*6+[(1,0,256),(903,0,0),(18,64,128),(6,0,128),(2136,0,0),(5,0,128),(473,0,0),(26,0,64)]),
)

def original_life(seat,kind,hp,x):
    src,_=setup(seat,seat);p,a,o,b=src.p,src.a,src.o,src.b
    for addr,value in ((0x4c3808,3),(b+0x114,90),(a+0xa30,hp),(a+0xa34,200),(a+0xa38,0)):
        p.write(addr,value,4)
    p.write(0x43d061,100,1)
    struct.pack_into('<f',p.memory,o+0x40,x)
    src.run(0x14d8c8,a,kind)
    pending=struct.unpack_from('<i',p.memory,a+0xa38)[0]
    calls=[]
    def observe(pc):
        if pc in (0x1b5b80,0x1e7b70):
            args=[int(p.registers[4+i]&0xffffffff) for i in range(3 if pc==0x1b5b80 else 2)]
            calls.append([hex(pc),*args])
    _,n=p.run(0x151968,[a],observe=observe,limit=500000)
    return dict(hp=p.read(a+0xa30,4),pending=pending,timer28=p.read(a+0x1b0+28*4,4),calls=calls,
                instructions=src.instructions+n)

def live():
    from itertools import groupby
    from validate_selected_combat import prefix
    pads=prefix((0,1));pads[265][1]=128
    select=[(sum(1 for _ in group),*row) for row,group in groupby(pads)]
    exe=LIB.parent/'ss6-match-replay';results=[]
    for seat,kind,when,before,after,fight in FOOD_ROUTES:
        chord=(0,2304) if seat else (2304,0)
        # Keep the 12 pickup and HP ticks as separate output boundaries.
        segments=select+fight+[(1,*chord)]+[(1,0,0)]*11+[(40,0,0)]
        lines=''.join(f'{n} {x} {y}\n' for n,x,y in segments)
        assert sum(n for n,x,y in segments)==when+40
        def run(flag):
            r=subprocess.run([exe,ASSETS,'--mode','select','--round-time','99',flag],input=lines,text=True,capture_output=True)
            assert r.returncode==0,(kind,r.stderr,r.stdout.splitlines()[-1:])
            return [x.split() for x in r.stdout.splitlines()]
        rows=run('--stage-item-fields');body=5+10*seat;life=9+10*seat
        press,consume,heal,neutral=rows[-13],rows[-3],rows[-2],rows[-1]
        assert int(press[body])==152 and int(press[4+10*seat])==35 and int(press[28])==kind
        assert all(int(r[23])==1 for r in (press,consume,heal)) and int(consume[33+seat])==kind
        assert int(consume[28])==-1 and int(consume[life])==before and int(heal[life])==after
        assert int(neutral[body])==0 and int(neutral[life])==after
        ref=original_life(seat,kind,before,float(consume[7+10*seat]))
        assert ref['hp']==after and ref['pending']==before-after and ref['timer28']==30*256
        assert ref['calls']==[['0x1b5b80',0,int(float(consume[7+10*seat])),80],['0x1e7b70',0xffffffff,65]]
        sounds=run('--sound-fields')[-2]
        count=int(sounds[25]);ev=[tuple(map(int,sounds[26+i*3:29+i*3])) for i in range(count)]
        assert (0,0,65) in ev,(kind,sounds)
        cap=original_life(seat,kind,200,float(consume[7+10*seat]))
        assert cap['hp']==200 and cap['calls']==ref['calls'] and cap['timer28']==30*256
        results.append(dict(player=seat+1,resource=seat,food=kind,healing_tick=when,
                            life=[before,after],original=ref,full_life_original=cap,
                            sound_events=ev,segments=select+fight+[(1,*chord),(51,0,0)]))
    return results

def contested_food(case):
    # Both fighters are already within 36 units of this food. Vary only
    # the press edge; the same pickup animates on both seats and exactly
    # one actor gets the item when that animation reaches the callback.
    assert case['food']==0 and case['player']==2
    before=case['segments'][:-2]
    results=[]
    for first,second in ((2304,2304),(2304,0),(0,2304)):
        next_pair=(0,0) if first==second else (second,first)
        pads=[(1,first,second),(1,*next_pair)]+[(1,0,0)]*18
        seq=''.join('%d %d %d\n'%tuple(r) for r in [*before,*pads])
        rows=subprocess.run([LIB.parent/'ss6-match-replay',ASSETS,'--mode','select','--stage-item-fields'],
                            input=seq,text=True,capture_output=True,check=True).stdout.splitlines()[-len(pads):]
        rows=[row.split() for row in rows]
        winner=0 if first else 1
        assert rows[1][5]==rows[1][15]=='152'
        assert all(row[28]=='0' and row[33:35]==['-1','-1'] for row in rows[:10])
        assert rows[10][28]=='-1' and rows[10][33+winner]=='0' and rows[-1][34-winner]=='-1'
        assert rows[-1][9]=='200' and int(rows[-1][19])==(171 if winner else 156)
        results.append(dict(first_pad=[first,second],winner=winner+1,recovering_hp=int(rows[-1][19])))
    return results

def main():
    assert digest(ELF)==PIN
    cases=[(s,c,w,k,0,0) for s in range(2) for c in range(2) for w in (0,1) for k in range(19)]
    cases += [(s,s,1,0,g,0) for s in range(2) for g in range(1,7)]
    cases += [(s,s,1,k,0,b) for s in range(2) for k,b in [(-1,0),(-1,1),(-1,2),(-1,3),(3,1),(6,3)]]
    with tempfile.TemporaryDirectory() as temp:
        path=Path(temp);exe=path/'contact';probe=path/'contact.cpp';probe.write_text(DRIVER)
        subprocess.run(['c++','-std=c++20','-O2','-I',ROOT/'src',probe,LIB,'-o',exe],check=True)
        run=subprocess.run([exe,ASSETS],text=True,capture_output=True,input=''.join(' '.join(map(str,c))+'\n' for c in cases))
        assert run.returncode==0,run.stderr
        native=run.stdout.split('.\n');assert len(native)==len(cases)+1
        results=[];instructions=frames=0
        with ProcessPoolExecutor(4) as pool:
            for args,actual,(expected,n) in zip(cases,native,pool.map(source,cases)):
                got=[list(map(int,line.split())) for line in actual.splitlines()]
                assert len(got)==len(expected),(args,len(got),len(expected))
                for tick,(a,b) in enumerate(zip(got,expected)):
                    assert a==b,(args,tick,[(i,x,y) for i,(x,y) in enumerate(zip(a,b)) if x!=y],a,b)
                instructions+=n;frames+=len(got);pickup=next(t for t,r in enumerate(got) if r[1]!=999)
                results.append(dict(args=args,picked_at=pickup,picked=got[-1][1],pending=struct.unpack('<i',struct.pack('<I',got[-1][2]))[0],
                                    recovery_or_release_at=len(got)-1,frames=len(got)))
            pad=list(pool.map(inputs,[(s,c) for s in range(2) for c in range(2)]))
        actual_match=live()
    doc=dict(real_selected_matches=actual_match,contested_food=contested_food(actual_match[0]),status='passed',elf_sha256=PIN,runtime_sha256=digest(LIB),cases=results,pad=pad,
             original_instructions=instructions,snapshots=frames,
             scope='Public character/stage select, four real stage-0 food pickups with verified HP change and SE65. Original pickup, item identity priority, life adjustment and throw callbacks with both fighters in both seats and weapon states, SDL-independent. Floor state is supplied at contact in the EE fixture; the native fixture actually lands the courier. Includes absent/late parcel, bomb fallback, occupied registry, KO and clock gates, sound requests, original throw object and attachment positions. Recipient collision and courier trajectory have separate tests.')
    REPORT.write_text(json.dumps(doc,indent=2)+'\n')
    print(len(cases),'cases,',frames,'snapshots,',sum(len(r['cases']) for r in pad),'EE pad tests')
if __name__=='__main__':main()
