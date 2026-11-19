#!/usr/bin/env python3
"""Validate 214+kick, its kind-2 strike, and reflection on real match inputs."""
import hashlib
import json
from itertools import groupby
import struct
from validate_haohmaru_special import (
    ACTORS, OBJECTS, QUEUE, ELF, ROOT, SOURCE_HASH, Boundary, ContactOracle,
    RES, actor_trace, initialize_effects, pads_for, run_native,
)

OUT = ROOT/'outputs/ss6-feasibility'


def matches(slot, mode, strength=0):
    forward, back = ((128, 64), (64, 128))[slot]
    steps = [(500,0,0)]
    if mode == 'reflect':
        # At opening distance the incoming whirlwind meets the extended
        # flask. The heavy whirlwind travels on a different action timeline.
        steps += [(15,0,0)] + [(1,0,v) for v in pads_for(64+strength,1-slot)]
        steps += [(1,0,0)]*(11 if strength==2 else 9)
    else:
        if mode != 'whiff':
            steps += [(25 if mode == 'guard' else 30,forward,back)]
        steps += [(30,0,0)]
    guard = forward if mode=='guard' else 0
    steps += [(1,v,guard) for v in pads_for(77,slot)]
    steps += [(1,0,guard)]*75 + [(1,0,0)]*165
    if slot:
        steps = [(n,b,a) for n,a,b in steps]
    commands = [' '.join(map(str,s)) for s in steps]
    return commands,run_native('ss6-match-replay',commands,'--whirlwind-fields')


def children(row):
    assert (len(row)-129)%82 == 0
    return [list(map(int,row[j+2:j+82])) for j in range(129,len(row),82)]


class FlaskContacts(ContactOracle):
    def install(self,row):
        p=self.probe
        bank=0x17c0000
        p.memory[bank:bank+len(self.jdg)] = self.jdg
        participants=[]
        objects=children(row)
        for slot in range(2):
            self.install_player(row,slot)
            body=OBJECTS[slot]
            a=ACTORS+slot*0xf2c
            p.write(0x4751e0+4*slot,bank,4)
            p.write(body+0x38,int(row[23+26*slot+2]),4)
            p.write(a+0x1ac,256,4)
            for j in range(2):
                p.write(a+0x1b0+4*j,int(row[75+27*slot+21+j]),4)
            participants.append(body)
            for index,words in enumerate(objects):
                if words[3] != slot:
                    continue
                obj=0x1e03000 + index*0x1000
                struct.pack_into('<80I',p.memory,obj,*words)
                p.write(obj+0x118,ACTORS+(words[0x118//4]-1)*0xf2c,4)
                participants.append(obj)

        # The original JDG selector reads each object's resource slot. The
        # reflected whirlwind retains the original slot while changing team.
        for index,obj in enumerate(participants):
            act,step = (p.read(obj+off,4) for off in (0x24,0x28))
            first=struct.unpack_from('<h',self.aid,2*act)[0]
            rec=60*(first+step)
            refs=0x17a0000+index*32
            p.memory[refs:refs+16]=self.act[rec+14:rec+30]
            p.write(obj+0xbc,refs,4)
        p.write(0x12d2698,0,4)
        for a in participants:
            for b in participants:
                if a!=b:
                    p.run(0x1536e8,[a,b],limit=100000)
        p.run(0x1544a0,limit=200000)
        return [QUEUE+108*i for i in range(p.read(0x12d2698,4))]

    def strike(self,previous,current,slot,kind,guard):
        p=self.probe
        events=self.install(previous)
        victim=1-slot
        dst=OBJECTS[victim]
        actor=ACTORS+0xf2c*victim
        owner=ACTORS+0xf2c*slot
        for e in events:
            obj=p.read(e+0x40,4)
            if (p.read(e,4),p.read(obj+0xcc,4),p.read(obj+0xd0,4),p.read(obj+0x10,4),p.read(e+0x68,4))!=(7,2,kind,slot,dst):
                continue
            raw=p.read(e+0x20,4)
            category=p.run(0x14dc00,[obj])[0]
            shares_pause=p.run(0x1690b0,[p.read(obj+0x14,4),p.read(obj+0x24,4)])[0]
            defense=p.run(0x155850,[e])[0]
            assert bool(defense)==guard
            end=Boundary(0x155e90 if guard else 0x155bb8)
            p.run(0x155d50 if guard else 0x155a88,[e,0,defense],stop_before=end,limit=250000)
            assert end.stopped
            if guard:
                p.run(0x14d5a0,[actor,obj,defense,p.read(e+12,4)])
            elif kind==0:
                p.run(0x156538,[e])
                assert p.read(dst+0x124,4)==obj
            pending=p.read(actor+0xa38,4)
            state=p.read(actor+0x192,2)
            assert int(current[9+10*victim])==int(previous[9+10*victim])-pending
            assert int(current[4+10*victim])==state
            assert int(current[23+26*victim+17])==p.read(actor+0x124,4)
            assert int(current[10+10*slot+bool(defense)])==int(previous[10+10*slot+bool(defense)])+1
            assert category==10 and shares_pause==kind
            timers=lambda addr:[p.read(addr+0x1b0+4*j,4) for j in range(2)]
            before=list(map(int,previous[75+27*slot+21:75+27*slot+23]))
            committed=list(map(int,current[75+27*slot+21:75+27*slot+23]))
            result=dict(frame=int(current[0]),raw=raw,defense=defense,damage=pending,target_state=state,
                        category=category,owner_timers_after_contact=timers(owner),owner_timers_after_tick=committed,
                        victim_timers_after_contact=timers(actor),object_pause_before_tick=p.read(obj+0xdc,4))
            if kind==1:
                assert timers(owner)[0]>before[0] and timers(owner)[1]==before[1]
                shell=next(o for o in children(current) if o[0xd0//4]==1)
                assert shell[0xdc//4]==max(0,p.read(obj+0xdc,4)-256)
            # The live body delta halves while timer 1 remains. Run the
            # original timer pass after the contact, including that same tick.
            for who,addr in ((slot,owner),(victim,actor)):
                p.write(addr+0x1ac,128 if timers(addr)[1] else 256,4)
                p.run(0x151eb0,[addr])
                got=list(map(int,current[75+27*who+21:75+27*who+23]))
                assert timers(addr)==got,(slot,raw,who,timers(addr),got)
            result['victim_timers_after_tick']=timers(actor)
            return result
        raise AssertionError(('No PS2 route 7 on published contact geometry',slot,len(events)))

    def reflection(self,previous,current,slot):
        p=self.probe
        for e in self.install(previous):
            src,dst=(p.read(e+off,4) for off in (0x40,0x68))
            if (p.read(e,4),p.read(src+0xcc,4),p.read(dst+0xcc,4),p.read(src+0xd0,4),p.read(dst+0xd0,4))!=(5,2,2,1,0):
                continue
            assert p.read(dst+0x10,4)==1-slot
            stop=Boundary(0x157f80)
            p.run(0x155780,[e],stop_before=stop,limit=200000)
            assert stop.stopped
            projected=next(o for o in children(current) if o[0xd0//4]==0)
            for off in (0xc,0x10,0x38):
                assert p.read(dst+off,4)==projected[off//4],(off,p.read(dst+off,4),projected[off//4])
            assert p.read(dst+0x118,4)==ACTORS+(1-slot)*0xf2c and projected[0x118//4]==2-slot
            return dict(frame=int(current[0]),route=5,team=slot+1,original_caster=2-slot,action=projected[9])
        raise AssertionError(('No PS2 route 5 on published reflection geometry',slot))


def simultaneous():
    # Two flasks remain with their casters and hit both bodies on the same
    # tick. The queue order decides which fighter's hitstop assignment wins.
    steps=[(500,0,0),(20,128,64),(30,0,0),
           *[(1,a,b) for a,b in zip(pads_for(77,0),pads_for(77,1))],*[(1,0,0)]*170]
    rows=run_native('ss6-match-replay',[' '.join(map(str,s)) for s in steps],'--whirlwind-fields')
    win=next(i for i,r in enumerate(rows) if r[9]!='200' and i>5)
    previous,current=rows[win-1:win+1]
    oracle=FlaskContacts()
    p=oracle.probe
    routes=[]
    for e in oracle.install(previous):
        src,dst=(p.read(e+off,4) for off in (0x40,0x68))
        routes.append(p.read(e,4))
        assert p.read(e,4)==7 and p.read(src+0xcc,4)==2 and p.read(dst+0xcc,4)<2
        end=Boundary(0x155bb8)
        p.run(0x155a88,[e,0],stop_before=end)
        assert end.stopped
    assert routes==[7,7]
    timers=[]
    for slot in range(2):
        a=ACTORS+0xf2c*slot
        assert int(previous[9+10*slot])-p.read(a+0xa38,4)==int(current[9+10*slot])==189
        assert p.read(a+0x192,2)==int(current[4+10*slot])==69
        p.write(a+0x1ac,128,4)
        p.run(0x151eb0,[a])
        after=[p.read(a+0x1b0+4*j,4) for j in range(2)]
        assert after==list(map(int,current[96+27*slot:98+27*slot]))
        assert rows[-1][3+10*slot:6+10*slot]==['0','0','0']
        timers.append(after)
    return dict(frame=int(current[0]),routes=routes,life=[189,189],timers=timers)


def save_replay(commands,path):
    parsed=[list(map(int,line.split())) for line in commands]
    with path.open('w') as output:
        for (a,b),group in groupby(parsed,lambda s:(s[1],s[2])):
            print(sum(s[0] for s in group),a,b,file=output)


def lethal(slot, guard):
    forward=(128,64)[slot]
    block=forward if guard else 0
    wind=[(45,forward,0),(30,0,0),*[(1,x,0) for x in pads_for(66,slot)],(290,0,0)]
    chip=[(80,forward,0),(30,0,0),*[(1,x,0) for x in pads_for(66,slot)],(55,0,forward),(190,0,0)]
    pre=[(500,0,0)]+wind*6+chip*(10 if guard else 3)
    final=[(80,forward,0),(30,0,0),*[(1,x,block) for x in pads_for(77,slot)],*[(1,0,block)]*50,(220,0,0)]
    steps=pre+final
    if slot:
        steps=[(n,b,a) for n,a,b in steps]
    commands=[' '.join(map(str,s)) for s in steps]
    rows=run_native('ss6-match-replay',commands,'--whirlwind-fields')
    finish=run_native('ss6-match-replay',commands,'--finish-fields')
    victim=1-slot
    life=9+10*victim
    win=next(j for j in range(len(pre),len(rows)) if rows[j][life]=='0')
    assert int(rows[win-1][life])==(1 if guard else 8) and int(rows[-1][12+10*slot])==1
    oracle=FlaskContacts()
    p=oracle.probe
    initialize_effects(p)
    for pc in (0x1123a8,0x112570,0x11e290):
        p.run(pc)
    for k,name in enumerate(('01HitFlash.bin','02Guard.bin','03etc.bin')):
        at=0x4a4810+k*0x3da0
        p.memory[at:at+0x3da0]=(RES/name).read_bytes()
    for k in range(32):
        p.write(0x4c3510+k*4,k+1,4)
    stdout=p.read(p.read(0x5d1bf8,4)+8,4)
    for off in (0,16):
        p.write(stdout+off,0x19e0000,4)
    events=oracle.install(rows[win-1])
    e=next(e for e in events if p.read(e,4)==7 and p.read(e+0x20,4)==20 and p.read(e+0x68,4)==OBJECTS[victim])
    for i in range(2):
        base=0x1b80254+0x108*i
        for off,value in zip((12,24,28,32),finish[win-1][75+4*i:79+4*i]):
            p.write(base+off,int(value),4)
    defense=p.run(0x155850,[e])[0]
    assert bool(defense)==guard
    _,n=p.run(0x155d50 if guard else 0x155a88,[e,0,defense],limit=600000)
    actor=ACTORS+0xf2c*slot
    base=0x1b80254+0x108*slot
    metadata=[p.read(actor+0x244,4)&0x18000000,p.read(base+28,4),p.read(base+32,4)]
    actual=[int(finish[win][23+26*slot+7])&0x18000000,*map(int,finish[win][77+4*slot:79+4*slot])]
    assert metadata==actual==[0x18000000 if guard else 0x08000000,5,0]
    return dict(player=slot+1,guard=guard,frame=int(rows[win][0]),prior_life=int(rows[win-1][life]),
                category=10,metadata=metadata,ee_instructions=n,round_wins=int(rows[-1][12+10*slot]))


def main():
    assert hashlib.sha256(ELF.read_bytes()).hexdigest()==SOURCE_HASH
    oracle=FlaskContacts()
    traces=[]
    results=[]
    for slot in range(2):
        for armed in (True,False):
            ticks,count,actions=actor_trace(77,slot,armed=armed)
            assert (598 if armed else 599) in actions
            traces.append(dict(player=1+slot,armed=armed,ticks=ticks,ee_instructions=count,actions=actions))
        for mode,strength in [*(('reflect',s) for s in range(3)),('hit',0),('guard',0),('whiff',0)]:
            commands,rows=matches(slot,mode,strength)
            offset=3+10*slot
            assert any(r[offset:offset+3]==['1','77','598'] for r in rows)
            assert rows[-1][3:6]==rows[-1][13:16]==['0','0','0'] and not children(rows[-1])
            events=[]
            reflected=None
            ids=set()
            for j,row in enumerate(rows):
                for obj in children(row):
                    if obj[0xd0//4]==1:
                        ids.add(obj[9])
                    elif obj[4]==slot and reflected is None:
                        reflected=oracle.reflection(rows[j-1],row,slot)
                if j and row[offset+7:offset+9]!=rows[j-1][offset+7:offset+9]:
                    events.append(oracle.strike(rows[j-1],row,slot,int(mode!='reflect'),mode=='guard'))
            assert sorted(ids)==([600,601] if mode in ('hit','guard') else [600]),(mode,ids)
            assert bool(reflected)==(mode=='reflect'),(slot,mode,strength)
            assert len(events)==int(mode!='whiff')
            if events:
                assert events[0]['raw']==(36+strength if mode=='reflect' else 20)
            final=int(rows[-1][9+10*(1-slot)])
            assert final==dict(hit=189,guard=199,whiff=200,reflect=(176,171,168)[strength])[mode]
            results.append(dict(player=slot+1,mode=mode,strength=strength,flask_actions=sorted(ids),
                                reflection=reflected,contacts=events,other_player_life=final))
            if slot==0 and mode=='reflect' and strength==2:
                save_replay(commands,OUT/'haohmaru-flask-reflect-heavy.replay')
    report=dict(status='passed',elf_sha256=SOURCE_HASH,caster_traces=traces,world_replays=results,simultaneous=simultaneous(),
                lethal_replays=[lethal(slot,guard) for slot in range(2) for guard in (False,True)],
                scope='Japanese PS2 SLPS_255.59 resource 00, system 0. Isolated actor traces include both weapon states. The two-player scenarios start armed with normal versus inputs. Original collection, sorting, guard/hit selection, damage, reaction and return ownership run on native live geometry. Independent object creation, updates and rendering records are covered by flask_objects_validation.json.')
    (OUT/'haohmaru_flask_validation.json').write_text(json.dumps(report,indent=2)+'\n')
    print(len(results),'real input match replays and',sum(t['ticks'] for t in traces),'actor updates passed')


if __name__=='__main__':
    main()
