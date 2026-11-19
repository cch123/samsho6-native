#!/usr/bin/env python3
"""Exercise body ACT shake requests and the original phase that consumes them."""
import hashlib
import json
import struct

from mips_probe import Probe, signed
from validate_haohmaru_special import BUILD, ELF, RES, ROOT, SOURCE_HASH, pads_for, run_native

BATTLE=0x1b00000
CAMERA=BATTLE+0x34
BODIES=(0x1e00000,0x1e01000)


def source_flags(p,who,action,step,flags38,flags104):
    start=FIRST[action]
    # 120f10 reads the same ACT as native playback. It can set the flag
    # before it tests motion gates, including on an explicitly held record.
    record=0x1b10000+60*(start+step)
    body=BODIES[who]
    for off,value in ((0x38,flags38),(0xc0,0),(0x104,flags104)):
        p.write(body+off,value,4)
    p.registers[16]=body
    p.registers[17]=record
    p.registers[15]=flags38
    p.run(0x120f10,stop_before=[0x120fc4,0x12104c])


def check(label,slot,pads):
    p=Probe(ELF.read_bytes(),finite_model=True)
    p.write(0x4d3d00,BATTLE,4)
    p.memory[0x1b10000:0x1b10000+len(ACT)]=ACT
    data=['500 0 0']+[f'1 {a} {b}' for a,b in pads]
    rows=run_native('ss6-match-replay',data,'--mode','versus','--shake-fields')
    impulses=[]
    displayed=set()
    for old,new in zip(rows,rows[1:]):
        # Fighter geometry updates precede the actor callbacks. The tested
        # flagged records are all mid-clip transitions, so their ACT identity
        # survives the final actor phase. Entry-frame FE markers are instead
        # taken from the previous body's actual pending word.
        for who,body in enumerate(BODIES):
            action,step=map(int,new[5+10*who:7+10*who])
            old_action,old_step=map(int,old[5+10*who:7+10*who])
            p.write(body+0xfe,int(old[26+who]),2)
            if action==old_action and step!=old_step:
                source_flags(p,who,action,step,*map(int,new[32+2*who:34+2*who]))
        queued=tuple(p.read(body+0xfe,2)&0xc0 for body in BODIES)
        if any(queued):
            impulses.append(dict(tick=int(new[0]),body_requests=queued,acts=[tuple(map(int,new[n:n+2])) for n in (5,15)]))
        p.registers[11],p.registers[14]=BODIES
        stack=0x1fff000
        for i,body in enumerate(BODIES):
            p.write(stack+0x20+4*i,body,4)
        p.run(0x14293c,stop_before=[0x1429e0])
        assert all(p.read(o+0xfe,2)&0xc0==0 for o in BODIES)
        p.write(CAMERA,int(new[25]),4)
        p.run(0x146dc8,[CAMERA]);p.run(0x146e28,[CAMERA])
        expected=[signed(p.read(CAMERA+n,4),32) for n in (0x44,0x48)]
        got=list(map(int,new[23:25]))
        assert got==expected,(label,slot,new[0],got,expected,queued,old[5:7],new[5:7],old[15:17],new[15:17])
        assert list(map(int,new[30:32]))==list(map(int,old[28:30])),(label,new[0],'priority-10 projection')
        displayed.add(int(new[29]))
    for who in range(2):
        assert all(int(r[26+who])&0xc0==0 for r in rows), (label,'unexpected late body request')
    return dict(case=label,attacker=slot+1,compared_ticks=len(pads),impulses=impulses,
                distinct_published_y=len(displayed),hits=int(rows[-1][10+10*slot]),guards=int(rows[-1][11+10*slot]),
                victim_min_life=min(int(r[9+10*(1-slot)]) for r in rows))


def inputs(state,slot,mode):
    forward,back=(128,64) if slot==0 else (64,128)
    close=(state in (80,'heavy','heavy-KO')) or state in (64,65,66)
    approach=40 if close else 32
    steps=[(approach,forward,back),(15,0,0)]
    if mode=='whiff':steps=[(75,back,forward),(15,0,0)]
    guard=forward if mode=='guard' else 0
    if state=='heavy-KO':
        steps=[(45,forward,0),(1,1024,0),(84,0,0)]*10
    else:
        motion=[1024] if state=='heavy' else pads_for(state,slot)
        steps.extend((1,k,guard) for k in motion)
        steps.append((200,0,guard))
    return [(b,a) if slot else (a,b) for n,a,b in steps for _ in range(n)]


ACT=(RES/'act_00.bin').read_bytes()
FIRST=struct.unpack_from('<2048H',(RES/'aid_00.bin').read_bytes())
if __name__=='__main__':
    assert hashlib.sha256(ELF.read_bytes()).hexdigest()==SOURCE_HASH
    samples=[]
    for slot in (0,1):
        for state in (64,65,66,67,68,69,70,71,72,73,74,75,76,77,80,'heavy','heavy-KO'):
            modes=('hit','guard','whiff') if state in (64,65,66,74,75,76,80) else ('hit',)
            for mode in modes:
                row=check(f'{state}-{mode}',slot,inputs(state,slot,mode))
                events=row['impulses']
                if state in (74,75,76,80):
                    assert len(events)==(4 if state==80 else 1),(state,slot,mode,events)
                    assert all(e['body_requests'][slot]==0x80 and not e['body_requests'][1-slot] for e in events)
                elif state in (64,65,66) and mode=='hit':
                    assert len(events)==2 and all(e['body_requests'][1-slot]==0x80 for e in events),row
                elif state=='heavy-KO':
                    assert row['victim_min_life']==0 and not events, row
                else:
                    assert not events,row
                if mode=='guard':assert row['guards']>0 and not row['hits'], row
                if mode=='whiff':assert not row['guards'] and not row['hits'], row
                samples.append(row)
        # The projectile still belongs to an armed caster. Disarming only the
        # defender changes the landing clip to 1285, retaining both impulses.
        other_forward=128 if slot else 64
        discard=(other_forward|8,0) if slot else (0,other_forward|8)
        for state in (64,65,66):
            row=check(f'{state}-unarmed-victim',slot,[discard]+[(0,0)]*125+inputs(state,slot,'hit'))
            events=row['impulses']
            assert row['hits']==1 and [e['acts'][1-slot] for e in events]==[(1285,1),(1285,4)]
            assert all(e['body_requests'][1-slot]==0x80 and not e['body_requests'][slot] for e in events)
            samples.append(row)
    report=dict(status='passed',elf_sha256=SOURCE_HASH,match_sha256=hashlib.sha256((BUILD/'ss6-match-replay').read_bytes()).hexdigest(),
                cases=samples,ticks=sum(r['compared_ticks'] for r in samples),
                source='SLPS_255.59 120f10..120fc4 record flags, 14293c..1429e0 two fighter flag halfwords, '
                       '141528/146ba0 request,146dc8 and146e28 signed clock consumption. Actual normalized '
                       'console inputs, both players. Action/record transitions and camera delta supplied from '
                       'live native match. Complete camera publication and framebuffer have separate oracles.')
    (ROOT/'outputs/ss6-feasibility/shake-input-validation.json').write_text(json.dumps(report,indent=2)+'\n')
    print(f"{len(samples)} double-player replays, {report['ticks']} clock and body-flag comparisons")
