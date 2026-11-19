#!/usr/bin/env python3
"""Real 236+E parries, empty-hand catches and bypasses against the Japanese PS2 handlers."""
from concurrent.futures import ProcessPoolExecutor
import hashlib
import json
import struct
from validate_combined_slash import initialize_pools
from validate_haohmaru_special import ACTORS, ELF, OBJECTS, QUEUE, ROOT, SOURCE_HASH, RES, ContactOracle, actor_trace, pads_for, run_native
from validate_weapon_handling import setup

OUT = ROOT/'outputs/ss6-feasibility/weapon_deflection_validation.json'


def scenario(slot, move, offset, bare=False):
    victim = 1-slot
    forward = (128, 64)[slot]
    pair = lambda a,d: (d,a) if slot else (a,d)
    sequence = [(500,0,0), (66,*pair(forward,0)), (4,0,0)]
    if bare:
        # First perform the actual discard. A grounded weapon remains on the
        # stage while its owner uses precisely the same 236+E input as before.
        sequence += [(1,*pair(0,(forward^192)|8)),(125,0,0)]
    first = {'light':(256,), 'medium':(512,), 'heavy':(1024,), 'combined':(768,), 'kick':(2048,),
             'uppercut':pads_for(68,slot), 'wall-slash':pads_for(80,slot)}[move]
    second = pads_for(24 if bare else 23,victim)
    for i in range(320):
        a,d=i-5,i-5-offset
        sequence.append((1,*pair(first[a] if 0<=a<len(first) else 0,second[d] if 0<=d<len(second) else 0)))
    rows=run_native('ss6-match-replay',[' '.join(map(str,v)) for v in sequence],'--whirlwind-fields')
    return rows


def trajectory(rows, hit, side, other, g):
    src,registry=setup(side)
    p,a,o=src.p,src.a,src.o
    addr=ACTORS+side*0xf2c
    pre=rows[hit-1]
    # Contact runs before the fighter visits. Seed the outgoing state and
    # request from the ELF resolver, then execute the original actor callbacks
    # independently through every hold, drop, fall and recovery.
    for off in (0x18c,0x190,0x194,0x23c,0x244,0x248,0xa48):
        p.write(a+off,g.read(addr+off,4),4)
    p.write(a+0x19a,g.read(addr+0x19a,1),1)
    for off in (0x38,0x40,0x44):
        p.write(o+off,g.read(OBJECTS[side]+off,4),4)
    for off,idx in ((0x104,3),(0x108,4)):
        p.write(o+off,int(pre[23+26*side+idx]),4)
    for i,name in enumerate(('01HitFlash.bin','02Guard.bin','03etc.bin')):
        start=0x4a4810+i*0x3da0
        p.memory[start:start+0x3da0]=(RES/name).read_bytes()
    actions=[]
    for j in range(hit,len(rows)):
        row,prev=rows[j],rows[j-1]
        p.write(o+0x1040,int(prev[23+26*other]),4)
        p.write(src.other+0x23c,int(prev[28+26*other]),4)
        p.write(src.other+0x194,int(prev[3+10*other])|(int(prev[4+10*other])<<16),4)
        p.write(src.other+0x19a,int(prev[33+26*other]),1)
        src.run(0x147028,registry,48)
        vals=src.frame(0)
        src.run(0x146ef8,registry,48)
        src.run(0x1207d8)
        src.run(0x1470a8,registry,48)
        base=3+10*side
        cb=88+27*side
        want=[vals[0],*vals[54:57],*vals[12:19],p.read(a+0x23c,4)&0x81000]
        got=[int(row[base])|int(row[base+1])<<16,*map(int,row[base+2:base+4]),int(row[cb+11]),
             *map(int,row[cb:cb+7]),int(row[28+26*side])&0x81000]
        assert got==want, (side,j-hit,vals[54],[(i,x,y) for i,(x,y) in enumerate(zip(got,want)) if x!=y])
        if not actions or actions[-1]!=vals[54]:actions.append(vals[54])
        if vals[0]==0:break
    assert vals[0]==0
    return dict(frames=j-hit+1,actions=actions,instructions=src.instructions)


def check(case):
    slot,move,offset,bare=case
    rows=scenario(*case)
    geo=ContactOracle()
    g=geo.probe
    initialize_pools(g)
    out=g.read(g.read(0x5d1bf8,4)+8,4)
    g.write(out,0x19e0000,4);g.write(out+16,0x19e0000,4)
    victim=1-slot
    source,defender=(ACTORS+i*0xf2c for i in (slot,victim))
    contacts=[]
    for j in range(1,len(rows)):
        prev,row=rows[j-1:j+1]
        if int(prev[5+10*victim])!=(131 if bare else 126):continue
        for s in range(2):geo.install_player(prev,s)
        g.write(defender+0xa48,4 if bare else 3,4)
        g.write(0x12d2698,0,4)
        for pair in (OBJECTS,OBJECTS[::-1]):g.run(0x1536e8,pair)
        g.run(0x1544a0)
        for n in range(g.read(0x12d2698,4)):
            ev=QUEUE+n*108
            if g.read(ev,4)!=2 or g.read(ev+0x40,4)!=OBJECTS[slot]:continue
            accepted,ins=g.run(0x154e10,[ev],limit=800000)
            if not accepted:continue
            results={}
            for side,addr in ((slot,source),(victim,defender)):
                state=g.read(addr+0x190,4)
                if state==0xffffffff:continue
                assert state==(int(row[3+10*side])|int(row[4+10*side])<<16),(case,row[0],hex(state))
                results[str(side+1)]=trajectory(rows,j,side,1-side,g)
            assert g.read(source+0xf26,1)==(0 if bare else 1)
            contacts.append(dict(frame=int(row[0]),raw=g.read(ev+0x20,4),recoil=g.read(ev+12,4),
                                 callback_trajectories=results,handler_instructions=ins))
            break
    positive=move not in ('kick','uppercut') and not (move=='combined' and offset==0) and not (bare and move=='wall-slash')
    assert len(contacts)==int(positive),(case,contacts)
    final=rows[-1]
    assert int(final[9+10*slot])==200
    if positive:
        assert int(final[9+10*victim])==200 and int(final[10+10*slot])==0
        assert bool(int(final[28+26*slot])&0x1000)==(not bare and move!='combined')
    else:
        # The same active E command can lose to an ineligible kick or special.
        ev=geo.contacts(rows,slot)
        assert ev and int(final[9+10*victim])<200
    return dict(attacker=slot+1,move=move,offset=offset,bare=bare,contacts=contacts,
                defender_life=int(final[9+10*victim]))


def main():
    assert hashlib.sha256(ELF.read_bytes()).hexdigest()==SOURCE_HASH
    commands=[dict(player=s+1,state=k,frames=n,instructions=ins,actions=act)
              for s in range(2) for k in (23,24) for n,ins,act in (actor_trace(k,s,armed=k==23),)]
    cases=[(s,move,offset,bare) for s in range(2) for bare in (False,True)
           for move,offset in [('light',0),('medium',0),('heavy',0),('combined',14),('kick',0),('uppercut',0),('wall-slash',32),('combined',0)]]
    with ProcessPoolExecutor(max_workers=4) as pool:
        matches=list(pool.map(check,cases))
    report=dict(status='passed',elf_sha256=SOURCE_HASH,commands=commands,matches=matches)
    OUT.write_text(json.dumps(report,indent=2)+'\n')
    print(f'{len(commands)} original command traces, {len(matches)} real versus replays',flush=True)


if __name__=='__main__':
    main()
