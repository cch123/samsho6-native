#!/usr/bin/env python3
"""Resolve a selected Shin mirror's lethal ice secret and its rapid ice hitstops with the Japanese handlers."""
from collections import Counter
from hashlib import sha256
from itertools import groupby
import json
import os
from pathlib import Path
import shutil
import tempfile
from validate_console_versus_menu import Oracle, REMATCH, physical, G
from validate_finishing_blow import actor, stats, put, initialize_effects, OBJECTS, RES, signed
from validate_haohmaru_flask import FlaskContacts, children
from validate_nakoruru_combat import MixedContactOracle
from validate_rimururu_normals import BUILD, ROOT, ELF, PIN, prefix, replay, input_row


class IceContacts(FlaskContacts,MixedContactOracle):
    def __init__(self):
        super().__init__((2,2))
        self.aid,self.act,self.jdg=self.banks[0]
        p=self.probe
        initialize_effects(p)
        for entry in (0x1123a8,0x112570,0x11e290):p.run(entry,limit=500000)
        for n,name in enumerate(('01HitFlash.bin','02Guard.bin','03etc.bin')):
            ptr=0x4a4810+n*0x3da0
            p.memory[ptr:ptr+0x3da0]=(RES/name).read_bytes()
        for n in range(32):p.write(0x4c3510+4*n,n+1,4)
        output=p.read(p.read(0x5d1bf8,4)+8,4)
        put(p,output,[(0,0x19e0000),(16,0x19e0000)])

    def install_player(self,row,slot):
        super().install_player(row,slot)
        self.probe.write(actor(slot)+0x10c,1,4)
        self.probe.write(actor(slot)+0xa34,200,4)

    def strike(self,previous,current,finish_prev,finish_now,side,descriptor,blocked=False):
        p=self.probe;victim=side^1;target=actor(victim);source=actor(side)
        for seat in (0,1):
            col=75+4*seat
            put(p,stats(seat),list(zip((12,24,28,32),map(int,finish_prev[col:col+4]))))
        events=self.install(previous)
        def matches(e):
            o=p.read(e+0x40,4)
            return (p.read(e,4),p.read(o+0xcc,4),p.read(o+0xd0,4),p.read(e+0x68,4))==(7,2,descriptor,OBJECTS[victim])
        event=next(e for e in events if matches(e))
        child=p.read(event+0x40,4);act=p.read(child+0x24,4);profile=p.read(child+0x14,4)
        category=p.run(0x14dc00,[child])[0]
        share=p.run(0x1690b0,[profile,act])[0]
        guard=p.run(0x155850,[event])[0]
        assert bool(guard)==blocked and profile==2
        visits=Counter()
        def observe(pc):
            if pc in (0x14dc00,0x1575d0,0x1576e8,0x1690b0):visits[pc]+=1
        _,count=p.run(0x155d50 if guard else 0x155a88,[event,0,guard],limit=800000,observe=observe)
        damage=p.read(target+0xa38,4);life=int(previous[9+10*victim])
        assert int(current[9+10*victim])==max(0,life-damage),(side,act,damage,life,current[9+10*victim])
        out=[p.read(stats(side)+idx,4) for idx in (0x1c,0x20)]
        assert out==[int(v)&0xffffffff for v in finish_now[77+4*side:79+4*side]],(out,finish_now[77+4*side:79+4*side])
        if life<=damage:
            assert descriptor==9 and category==13 and out==[0,0] and visits[0x1576e8]==1 and visits[0x14dc00]>=1
            assert p.read(source+0x244,4)&0x18000000==int(current[30+26*side])&0x18000000==0x08000000
        contact_timers=[p.read(source+offset,4) for offset in (0x1b0,0x1b4)]
        before=[int(v) for v in previous[96+27*side:98+27*side]]
        pause=p.read(child+0xdc,4)
        if descriptor==8:
            assert share==1 and contact_timers==[pause,before[1]] and pause>0,(act,share,contact_timers,before,pause)
        elif descriptor==9:
            assert share==0 and contact_timers==before,(act,share,contact_timers,before)
        for whom in (side,victim):
            address=actor(whom)
            p.write(address+0x1ac,128 if p.read(address+0x1b4,4) else 256,4)
            p.run(0x151eb0,[address])
            expected=[p.read(address+off,4) for off in (0x1b0,0x1b4)]
            actual=list(map(int,current[96+27*whom:98+27*whom]))
            assert expected==actual,(side,act,whom,expected,actual)
        return dict(tick=int(current[0]),act=act,guard=guard,raw=p.read(event+0x20,4),hp_before=life,
                    damage=damage,category=category,lethal=life<=damage,outcome=out,
                    shared_owner_stop=share,object_stop=pause,owner_timers_at_contact=contact_timers,
                    owner_timers_after=list(map(int,current[96+27*side:98+27*side])),
                    original_instructions=count)


def choose():
    pads=prefix((2,2))
    pads[210]=pads[227]=[128,128]
    return [(sum(1 for _ in group),*k) for k,group in groupby(pads)]


def heavy(side):
    return [(45,128,64),(30,0,0),input_row(side,1,1024),(101,0,0)]


def commands(side):
    f=(128,64)[side];b=f^192
    keys=[f,32|f,32,32|b,b]*2
    keys[-1]|=1536
    return [(45,128,64),(15,0,0)]+[input_row(side,1,key) for key in keys]+[(1,0,0)]*180


def full_match(side):
    pads=choose();owner=9+10*side;victim=9+10*(side^1)
    selection=replay(pads,'--select-fields')[-1]
    assert [selection[i] for i in (25,26,35,36)]==['2','1','2','1']
    # Win round one by ordinary strikes. In round two the future loser earns
    # enough rage from those attacks to fill the caster's rage with four heavies.
    for _ in range(12):
        pads+=heavy(side)
        if replay(pads,'--finish-fields')[-1][victim]=='0':break
    else:raise AssertionError('round one did not end')
    now=replay(pads+[(1,0,0)]*720,'--rage-fields')
    wait=next(i-len(pads)+1 for i,r in enumerate(now) if i>=len(pads) and r[victim]=='200' and r[1]=='4')
    pads.append((wait,0,0))
    for _ in range(12):
        pads+=heavy(side)
        row=replay(pads,'--rage-fields')[-1]
        if 0<int(row[victim])<=38:break
    for _ in range(8):
        pads+=heavy(side^1);row=replay(pads,'--rage-fields')[-1]
        if row[23+11*side]=='1':break
    assert row[23+11*side]=='1' and int(row[owner])>0
    start=len(pads);pads+=commands(side)
    objects=replay(pads,'--whirlwind-fields');finish=replay(pads,'--finish-fields')
    target_life=[int(r[victim]) for r in objects]
    oracle=IceContacts();hits=[]
    for i in range(start,len(pads)):
        if target_life[i]<target_life[i-1]:
            hits.append(oracle.strike(objects[i-1],objects[i],finish[i-1],finish[i],side,9))
    assert sum(hit['lethal'] for hit in hits)==1 and hits[-1]['lethal']
    assert int(objects[-1][12+10*side])==2 and int(objects[-1][12+10*(side^1)])==0
    assert any(r[4+10*side:6+10*side]==['90','634'] for r in objects[start:])
    menu_rows=replay(pads+[(1,0,0)]*900,'--vs-menu-fields')
    menu_tick=next(i for i,r in enumerate(menu_rows[len(pads):],1) if r[24]=='1')
    menu=menu_rows[len(pads)+menu_tick-1]
    original=Oracle();original.enter(side,(2,2),True)
    tally=[original.p.read(G-16+n*4,4) for n in range(4)]+[signed(original.p.read(G+12,4),32),original.p.read(G+0x38,4),original.p.read(G+16,4)]
    assert list(map(int,menu[33:40]))==tally
    pads.append((menu_tick,0,0))
    menu_input=[(45,0,0),input_row(side,1,32),(1,0,0),input_row(side,1,1024),(500,0,0)]
    for n,left,right in menu_input:
        for _ in range(n):
            original.sample((physical(left),physical(right)));original.tick()
            if original.destination:break
        if original.destination:break
    assert original.destination==REMATCH
    pads+=menu_input
    result=replay(pads,'--select-fields')[-1]
    assert [result[i] for i in (9,12,19,22,23,25,26,35,36)]==['200','0','200','0','2','2','1','2','1']
    assert [int(v) for v in result[54:56]]==[int(i==side) for i in (0,1)]
    return dict(seat=side+1,first_win='standing heavy',second_win='6321463214+BC',
                before_command=dict(actor_hp=int(row[owner]),opponent_hp=int(row[victim]),rage_state=int(row[23+11*side])),
                lethal_sequence=hits,original_match_statistics=tally,set_score=[int(menu[12]),int(menu[22])],
                rematch_tally=list(map(int,result[54:56])),rematch_both_hp=[200,200])


def hitstop(side):
    reports=[];f=(128,64)[side]
    for idx,button in enumerate((256,512,1024)):
        for guard in (False,True):
            defense=f if guard else 0
            pads=choose()+[(45,128,64),(9,0,0)]
            start=len(pads)
            pads += [input_row(side,1,k,defense) for k in (f|button,0,f|button,0,f|button)]
            pads += [input_row(side,1,0,defense)]*180
            objs=replay(pads,'--whirlwind-fields');finish=replay(pads,'--finish-fields');oracle=IceContacts();found=[]
            for i in range(start+1,len(pads)):
                prev,r=objs[i-1:i+1]
                children_in=children(prev)
                if not any(o[0xd0//4]==8 for o in children_in):continue
                if prev[10+side*10:12+side*10]==r[10+side*10:12+side*10]:continue
                h=oracle.strike(prev,r,finish[i-1],finish[i],side,8,guard)
                assert h['act']==559+idx
                found.append(h)
            assert found,(side,idx,guard)
            reports.append(dict(seat=side+1,guard=guard,act=559+idx,contacts=found))
    return reports


def main():
    assert sha256(ELF.read_bytes()).hexdigest()==PIN
    with tempfile.TemporaryDirectory() as directory:
        binary=Path(directory)/'ss6-match-replay';shutil.copy2(BUILD/'ss6-match-replay',binary)
        os.environ['SS6_RIMURURU_TEST_REPLAY']=str(binary)
        matches=[full_match(side) for side in (0,1)]
        stops=[r for side in (0,1) for r in hitstop(side)]
        report=dict(status='passed',elf_sha256=PIN,replay_sha256=sha256(binary.read_bytes()).hexdigest(),
                    matches=matches,hitstop=stops,scope='Selected Shin vs Shin Rimururu mirror, both seats. Live source JDG and exact preceding body/projectile snapshots feed original 1536e8/1544a0/155850 and full 155a88 or 155d50. Original 14dc00 class, 1690b0 sharing, both timers after 151eb0, damage, finished round and CONTINUE session tally are compared.')
        (ROOT/'outputs/ss6-feasibility/rimururu_projectile_finish_validation.json').write_text(json.dumps(report,indent=2)+'\n')
        print(len(matches),'full matches;',sum(len(v['contacts']) for v in stops),'ice contacts')


if __name__=='__main__':main()
