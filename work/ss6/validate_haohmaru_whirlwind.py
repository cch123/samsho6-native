#!/usr/bin/env python3
"""Compare real 236+slash match replays with the PS2 contact and captured-victim callbacks."""
import hashlib
import itertools
import json
import struct
from validate_haohmaru_special import (
    ACTORS, ELF, OBJECTS, QUEUE, ROOT, SOURCE_HASH, Boundary, ContactOracle,
    actor_trace, fixture, initialize_effects, pads_for, run_native,
)


def matches(strength, slot, mode):
    forward, back = (128,64) if slot==0 else (64,128)
    guard = forward if mode=='guard' else 0
    approach = (60,back,forward) if mode=='whiff' else (20,forward,back)
    sequence = [(500,0,0),approach,(30,0,0)]
    sequence += [(1,x,guard) for x in pads_for(64+strength,slot)] + [(1,0,guard)]*290
    if slot:
        sequence=[(n,b,a) for n,a,b in sequence]
    rows=run_native('ss6-match-replay',[' '.join(map(str,v)) for v in sequence],'--whirlwind-fields')
    assert rows[5][3+slot*10:6+slot*10]==['1',str(64+strength),str(529+strength)]
    return rows


def contact(oracle, previous, current, slot, guard):
    p=oracle.probe
    for who in range(2):
        oracle.install_player(previous,who)
    obj=0x1e03000
    words=list(map(int,previous[131:211]))
    assert len(words)==80 and words[4]==slot and words[0xcc//4]==2
    struct.pack_into('<80I',p.memory,obj,*words)
    # install_player makes private compact references for each body. Give the
    # object and its owner's body independent references into the complete JDG.
    bank=0x17c0000
    p.memory[bank:bank+len(oracle.jdg)]=oracle.jdg
    p.write(0x4751e0+slot*4,bank,4)
    for who,action,step in ((OBJECTS[slot],*map(int,previous[5+10*slot:7+10*slot])),(obj,words[9],words[10])):
        first=struct.unpack_from('<h',oracle.aid,2*action)[0]
        refs=0x17a0000+(0x100 if who==obj else 0)
        p.memory[refs:refs+16]=oracle.act[60*(first+step)+14:60*(first+step)+30]
        p.write(who+0xbc,refs,4)
    victim=1-slot
    dst=OBJECTS[victim]
    actor=ACTORS+victim*0xf2c
    p.write(0x12d2698,0,4)
    for args in ((obj,dst),(dst,obj)):
        p.run(0x1536e8,args)
    p.run(0x1544a0)
    for n in range(p.read(0x12d2698,4)):
        event=QUEUE+108*n
        if p.read(event,4)==7 and p.read(event+0x40,4)==obj and p.read(event+0x68,4)==dst:
            defense,_=p.run(0x155850,[event])
            assert bool(defense)==guard
            end=Boundary(0x155e90 if guard else 0x155bb8)
            p.run(0x155d50 if guard else 0x155a88,[event,0,defense],stop_before=end,limit=200000)
            assert end.stopped
            if guard:
                p.run(0x14d5a0,[actor,obj,defense,p.read(event+12,4)])
            else:
                p.run(0x156538,[event])
                assert p.read(dst+0x124,4)==obj
            pending=p.read(actor+0xa38,4)
            assert int(current[9+victim*10])==int(previous[9+victim*10])-pending
            assert int(current[4+victim*10])==p.read(actor+0x192,2)
            assert int(current[23+26*victim+17])==p.read(actor+0x124,4)
            return dict(frame=int(current[0]),raw=p.read(event+0x20,4),defense=defense,damage=pending)
    raise AssertionError('No original contact on the published geometry')


def original_victim(strength):
    # Give the original two valid, independently registered actors and a real
    # object task. The shape of the registry is checked inside 168220.
    p,a,o,b=fixture(0)
    p.finite_model=True
    source=ACTORS+0xf2c
    parent=o+0x1000
    for addr,val in ((b+0x250,source),(source,parent),(source+0xa24,1),(parent+0xcc,1),(parent+0xc,1),
                     (0x4751b4,p.read(0x4751b0,4))):
        p.write(addr,val,4)
    p.memory[0x46a9b0+0x1800:0x46a9b0+0x3000]=p.memory[0x46a9b0:0x46a9b0+0x1800]
    for actor,obj,weapon in ((a,o,o+0x4000),(source,parent,o+0x3000)):
        p.write(actor+4,weapon,4)
        p.write(weapon+0xc4,-1,4)
        for fn,args in ((0x149008,[actor,0]),(0x149918,[actor]),(0x11d8e0,[obj])):
            p.run(fn,args,limit=500000)
        for addr,val in ((actor+0x23c,0x1000),(obj+0x30,256),(obj+0xc8,1)):
            p.write(addr,val,4)
    initialize_effects(p)
    for addr,val in ((0x345188,0),(a+0x18c,1),(source+0x194,(64+strength)<<16|1),
                     (source+0x26c,strength),(source+0x2b8,0x4df060),(source+0x28c,0),(parent+0x104,0x8000),
                     (parent+0x38,0x10080000)):
        p.write(addr,val,4)
    p.write(source+0x19a,8|(1<<strength),1)
    for obj,x in ((o,312),(parent,330)):
        struct.pack_into('<f',p.memory,obj+0x40,x)
    child=p.run(0x16d9c8,[source],limit=80000)[0]
    p.run(0x11d8e0,[child])
    p.write(child+0x104,0x40000,4)
    p.write(child+0x108,p.read(child+0x108,4)|0x2000000,4)
    p.write(o+0x124,child,4)
    p.write(a+0x254,0,1)
    p.run(0x14ff80,[a+0x18c,2,80+strength])
    p.write(a+0x18c,1,4)
    result=[]
    for _ in range(180):
        for fn,args in ((0x11d730,[o]),(0x11d6c8,[o]),(0x147028,[b+0x3a4,48]),(0x149d08,[a]),
                        (0x149918,[a]),(0x11d8e0,[o]),(0x146ef8,[b+0x3a4,48]),(0x1470a8,[b+0x3a4,48])):
            p.run(fn,args,limit=300000)
        regs=[p.read(a+off,4) for off in range(0x28c,0x2c0,4)]
        regs[10]=int(bool(regs[10]))
        result.append([p.read(a+0x194,4),p.read(o+0x24,4),p.read(o+0x28,4),p.read(o+0x2c,4),
                       p.read(o+0x44,4),p.read(o+0xc0,4),int(bool(p.read(o+0x124,4))),p.read(a+0x20c,4),
                       *[p.read(a+off,4) for off in range(0x260,0x27c,4)],*regs])
        if p.read(a+0x194,4)==(16<<16|2):
            return result
    raise AssertionError('Original victim never released into downed state')


def compare_victim(rows,start,slot,expected):
    b=75+27*slot
    for offset,want in enumerate(expected):
        row=list(map(float,rows[start+offset][:23]))+list(map(int,rows[start+offset][23:]))
        table,state,act,step=map(int,row[3+10*slot:7+10*slot])
        reg=list(row[b:b+13]);reg[10]=int(bool(reg[10]))
        actual=[state<<16|table,act,step,row[b+24],row[23+26*slot+1],row[b+26],int(bool(row[b+20])),row[b+23],
                *row[b+13:b+20],*reg]
        assert actual==want,(slot,offset,[(i,x,y) for i,(x,y) in enumerate(zip(actual,want)) if x!=y])


def main():
    assert hashlib.sha256(ELF.read_bytes()).hexdigest()==SOURCE_HASH
    oracle=ContactOracle()
    targets=[original_victim(s) for s in range(3)]
    reports=[]
    traces=[]
    for strength,slot in itertools.product(range(3),range(2)):
        ticks,instructions,actions=actor_trace(64+strength,slot)
        traces.append(dict(strength=strength,player=slot+1,ticks=ticks,instructions=instructions,actions=actions))
        for mode in ('hit','guard','whiff'):
            rows=matches(strength,slot,mode)
            dst=1-slot
            first=3+10*slot;defender=3+10*dst
            contacts=[j for j in range(1,len(rows)) if rows[j-1][first+7:first+9]!=rows[j][first+7:first+9]]
            assert len(contacts)==int(mode!='whiff')
            event=None
            if contacts:
                j=contacts[0]
                event=contact(oracle,rows[j-1],rows[j],slot,mode=='guard')
                assert event['raw']==36+strength
                if mode=='hit':
                    compare_victim(rows,j,dst,targets[strength])
                    assert rows[-1][defender:defender+3]==['0','0','0']
            child_actions={int(row[140]) for row in rows if len(row)>129}
            assert child_actions==({532+strength,535,536,537} if mode=='hit' else {532+strength,538}),child_actions
            hp=[(int(row[0]),int(row[defender+6])) for j,row in enumerate(rows) if j and row[defender+6]!=rows[j-1][defender+6]]
            assert [k for _,k in hp]==([193,(176,171,168)[strength]] if mode=='hit' else [199] if mode=='guard' else [])
            landing=None
            if mode=='hit':
                life_frame,life=hp[-1]
                commit=next(j for j,row in enumerate(rows) if int(row[0])==life_frame)
                # The victim callback enqueues damage one tick before 14a8d0's
                # pending amount reaches life. 165f94 tags the released-body landing
                # as capture damage for finishing-blow classification.
                for who in range(2):
                    oracle.install_player(rows[commit-2],who)
                p=oracle.probe
                p.run(0x1413d8,[dst,(12,16,18)[strength],OBJECTS[slot],1])
                actor=ACTORS+dst*0xf2c
                amount=p.read(actor+0xa38,4)
                assert life==int(rows[commit-1][defender+6])-amount
                assert p.read(actor+0x124,4)==int(rows[commit-1][23+26*dst+17])
                landing=dict(enqueued=int(rows[commit-1][0]),committed=life_frame,damage=amount)
            assert len(rows[-1])==129 and rows[-1][first:first+3]==['0','0','0']
            reports.append(dict(strength=strength,player=slot+1,mode=mode,contact=event,landing=landing,life_changes=hp,
                                projectile_actions=sorted(child_actions),victim_ticks=len(targets[strength]) if mode=='hit' else 0))
    # Keep using normal inputs through a lethal second-stage slam, the point
    # award and the next round's restoration of the two players' life.
    commands=['500 0 0']
    for _ in range(8):
        commands+=['45 128 0','30 0 0','1 32 0','1 160 0','1 1152 0','290 0 0']
    full_round=run_native('ss6-match-replay',commands)
    after_each=full_round[6::6]
    assert [int(row[19]) for row in after_each]==[168,136,104,72,41,11,0,200]
    won=after_each[6]
    assert int(won[12])==1 and int(after_each[-1][1])==4 and int(after_each[-1][12])==1
    report=dict(status='passed',elf_sha256=SOURCE_HASH,actor_traces=traces,world_replays=reports,heavy_round=dict(knockout_frame=int(won[0]),round_end_player1_wins=int(won[12]),life_after_next_round=int(after_each[-1][19])),
                scope='System0 armed resource00. True normalized 236 input, both players. ELF 1536e8/1544a0/155850 and the original hit or guard prefix plus victim selector on previous published native geometry. Independent original captured-victim traces compare relative timing, body action/clock, exact vertical position, callback words, registry and attachment lifetime through down16. Whole 1413d8 checks landing damage and rage against the published HP/meter state. Absolute X/camera, full-screen pixels and the complete original PS2 battle loop are outside this oracle.')
    (ROOT/'outputs/ss6-feasibility/haohmaru_whirlwind_validation.json').write_text(json.dumps(report,indent=2)+'\n')
    print(f'{len(traces)} caster traces, {len(reports)} native match replays, {sum(x["victim_ticks"] for x in reports)} original/native victim ticks')


if __name__=='__main__':
    main()
