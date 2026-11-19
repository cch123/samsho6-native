#!/usr/bin/env python3
"""Check 632146+A+B, its raw 23 contact and the original wall knockdown."""
import hashlib
import json
import struct
from validate_finishing_blow import BATTLE, Comparison, actor
from mips_probe import signed
from validate_haohmaru_special import ELF, OBJECTS, QUEUE, RES, ROOT, SOURCE_HASH, actor_trace, initialize_effects, pads_for, run_native


def commands(slot, mode, recovery=0):
    forward,back=(128,64) if slot==0 else (64,128)
    opening=(75,back,forward) if mode=='whiff' else (40,forward,back)
    pads=pads_for(80,slot)
    sequence=[(500,0,0),opening,(15,0,0)]+[(1,k,0) for k in pads]
    start=sum(n for n,_,_ in sequence)
    for tick in range(340):
        frame=start+tick+1
        opposing=0
        if mode in ('standing_guard','low_guard') and 32<=tick<=75:
            opposing=forward|(32 if mode=='low_guard' else 0)
        if mode=='jump' and tick==29:opposing=16
        if frame==recovery:opposing=4096|(forward if mode=='roll_back' else 0)
        sequence.append((1,0,opposing))
    if slot:sequence=[(n,b,a) for n,a,b in sequence]
    return [' '.join(map(str,v)) for v in sequence]


def original_contact(check, rows, slot, index, guard):
    p=check.p
    for i in (0,1):check.original.install_player(rows[index-1],i)
    p.write(0x12d2698,0,4)
    for pair in (OBJECTS,OBJECTS[::-1]):check.run(0x1536e8,pair)
    check.run(0x1544a0)
    for k in range(p.read(0x12d2698,4)):
        e=QUEUE+108*k
        if p.read(e,4)!=7 or p.read(e+0x40,4)!=OBJECTS[slot]:continue
        assert p.read(e+0x20,4)==23 and p.read(e+0x10,4)==42
        defense=check.run(0x155850,[e])
        assert defense==guard
        check.run(0x155d50 if guard else 0x155a88,[e,1,defense])
        victim=1-slot
        damage=p.read(actor(victim)+0xa38,4)
        state=p.read(actor(victim)+0x192,2)
        assert int(rows[index][9+10*victim])==int(rows[index-1][9+10*victim])-damage
        assert int(rows[index][4+10*victim])==state
        return dict(frame=int(rows[index][0]),raw=23,base=42,damage=damage,defense=guard,reaction=state)
    raise AssertionError('No original body strike on the published geometry')


def stage_update(check,prev,row,old_shake,new_shake):
    # Use the live stage geometry (the callback can subsequently clamp negative
    # vertical overshoot on landing) and the pre-update camera command queue.
    p=check.p
    offsets=[0,4,8,12,16,20,28,32,36,40,44,48,52]
    camera=BATTLE+0x34
    for off,val in zip(offsets,prev[139:]):p.write(camera+off,int(val),4)
    for off,val in zip((0x44,0x48),old_shake[23:25]):p.write(camera+off,int(val),4)
    count,kind,timer=map(int,prev[131:134])
    p.write(camera+0x4c,count,4);p.write(camera+0x50,kind,1);p.write(camera+0x54,timer,4)
    p.write(BATTLE+0x138,int(prev[134]),4)
    for i in (0,1):
        check.original.install_player(prev,i)
        p.write(BATTLE+0x24c+4*i,actor(i),4)
        base=23+26*i
        p.write(OBJECTS[i]+0x40,int(row[base]),4);p.write(OBJECTS[i]+0x44,int(row[base+1]),4)
        p.write(OBJECTS[i]+0xfe,int(old_shake[26+i]),2)
        a=5+10*i
        if row[a]=='592' and row[a:a+2]!=prev[a:a+2]:
            # The slash renews the Y shake on each of four consecutive ACT
            # records. The wall callback can freeze translation on that same
            # visit, but publishing the camera still consumes the impulse.
            first=struct.unpack_from('<H',check.original.aid,2*592)[0]
            start=60*(first+int(row[a+1]));at=0x19f2000
            p.memory[at:at+60]=check.original.act[start:start+60]
            p.registers[15]=int(row[base+2]);p.registers[16]=OBJECTS[i];p.registers[17]=at
            p.run(0x120f10,stop_before=[0x120f40,0x12104c])
    check.run(0x1426d8,[BATTLE])
    assert not p.read(BATTLE+0x138,4)&4
    fields=[(p.read(camera+off,4) if i in (1,2,3,7,8,9) else signed(p.read(camera+off,4),32))
            for i,off in enumerate(offsets)]
    assert fields==list(map(int,row[139:])),(row[0],[(i,a,b) for i,(a,b) in enumerate(zip(fields,map(int,row[139:]))) if a!=b])
    assert [p.read(camera+off,4) for off in (0x44,0x48)]==list(map(int,new_shake[23:25]))
    return [p.read(camera+0x4c,4),p.read(camera+0x50,1),p.read(camera+0x54,4)]

def check_world(slot, mode, recovery=0):
    pads=commands(slot,mode,recovery)
    rows=run_native('ss6-match-replay',pads,'--wall-fields')
    victim=1-slot;at=3+10*slot;vt=3+10*victim
    assert all(len(r)==152 for r in rows)
    assert rows[8][at:at+3]==['1','80','592'] and rows[-1][at:at+3]==['0','0','0']
    assert rows[-1][vt:vt+3]==['0','0','0']
    changes=[i for i in range(1,len(rows)) if rows[i][at+7:at+9]!=rows[i-1][at+7:at+9]]
    check=Comparison();p=check.p
    initialize_effects(p)
    for pc in (0x1123a8,0x112570,0x11e290):check.run(pc)
    for bank,name in enumerate(('01HitFlash.bin','02Guard.bin','03etc.bin')):
        address=0x4a4810+bank*0x3da0;p.memory[address:address+0x3da0]=(RES/name).read_bytes()
    log=p.read(p.read(0x5d1bf8,4)+8,4)
    p.write(log,0x19e0000,4);p.write(log+16,0x19e0000,4)
    contacts=[]
    if mode in ('whiff','jump'):
        assert not changes and int(rows[-1][vt+6])==200
        # Lack of a native event must also mean the actual ACT/JDG geometry
        # supplied no body strike, for each of the four active records.
        for i,r in enumerate(rows[:-1]):
            if int(r[at+2])!=592 or not 16<=int(r[at+3])<=19:continue
            for who in (0,1):check.original.install_player(r,who)
            p.write(0x12d2698,0,4);check.run(0x1536e8,[OBJECTS[slot],OBJECTS[victim]])
            assert all(p.read(QUEUE+108*n,4)!=7 for n in range(p.read(0x12d2698,4)))
    else:
        assert len(changes)==1
        guard={'standing_guard':1,'low_guard':2}.get(mode,0)
        contacts.append(original_contact(check,rows,slot,changes[0],guard))
    wall=None;checks=0;recovery_tick=0
    if mode in ('hit','roll_forward','roll_back'):
        shake=run_native('ss6-match-replay',pads,'--shake-fields')
        callback=75+27*victim+13
        player_fields=23+26*victim
        side=135+2*victim
        for j in range(changes[0]+1,len(rows)):
            prev,r=rows[j-1:j+1]
            if int(prev[callback]) in (0x171b98,0x171c80) and float(r[vt+5])>=0:
                original_queue=stage_update(check,prev,r,shake[j-1],shake[j])
                if int(prev[callback])==0x171c80:
                    assert not int(r[134])&4
                    count,kind,timer=map(int,r[131:134])
                    assert count==original_queue[0] and (not count or [kind,timer]==original_queue[1:])
            if int(prev[callback])==0x171b98:
                # Test the actual original character radius and boundary helper
                # after stage movement. During contact pause the actor callback
                # has an override; raw geometry still stays away from the wall.
                x=int(r[player_fields]);left,right=map(int,r[129:131])
                p.write(actor(victim),OBJECTS[victim],4);p.write(OBJECTS[victim]+0x40,x,4)
                p.write(BATTLE+0x44,left,4);p.write(BATTLE+0x48,right,4)
                distance=check.run(0x14adf0,[0])+int(struct.unpack_from('<f',p.memory,0x5f1660)[0])
                reached=bool(check.run(0x14aad8,[actor(victim),distance,0,0]))
                assert reached==(int(r[callback])==0x171c80),(slot,mode,r[0],x,left,right)
                assert bool(int(r[134])&4)==(int(prev[75+27*victim+21])==0)
                checks+=1
                if reached:
                    assert list(map(int,r[131:134]))==[1,3,20<<8]
                    assert int(r[side])==(int(prev[side])+1)&15 and int(r[side+1])==0
                    wall=dict(frame=int(r[0]),x=float(r[vt+4]),left=left,right=right,camera_wait=20)
            if int(r[callback])==0x171c80 and float(r[vt+5])<float(prev[vt+5]) and 0<float(r[vt+5])<=20 and not recovery_tick:
                recovery_tick=int(r[0])+1
        assert wall and checks>4
        if mode.startswith('roll'):
            expected=54 if mode=='roll_forward' else 55
            assert any(r[vt:vt+2]==['0',str(expected)] for r in rows),(slot,mode,recovery)
        else:
            recv={int(r[vt+2]) for r in rows}
            assert {390,392,50,54}<=recv and recovery_tick
    return dict(player=slot+1,mode=mode,contacts=contacts,wall=wall,wall_comparisons=checks,
                recovery_input_frame=recovery or None,original_calls=check.coverage),recovery_tick


def main():
    assert hashlib.sha256(ELF.read_bytes()).hexdigest()==SOURCE_HASH
    traces=[];world=[]
    for slot in (0,1):
        for state,fall in ((80,False),(67,True)):
            n,ins,actions=actor_trace(state,slot,fall)
            traces.append(dict(player=slot+1,table=2 if fall else 1,state=state,ticks=n,instructions=ins,actions=actions))
        hit,roll=check_world(slot,'hit');world.append(hit)
        for mode in ('standing_guard','low_guard','whiff','jump','roll_forward','roll_back'):
            result,_=check_world(slot,mode,roll if mode.startswith('roll') else 0)
            world.append(result)
        print(slot+1,world[-7:],flush=True)
    result=dict(status='passed',elf_sha256=SOURCE_HASH,actor_traces=traces,world_replays=world,
                scope='Armed resource 00, system 0. Full original input-to-callback traces on both sides of a fixed stage fixture. Original full 155a88/155d50 on published hit geometry, original 1536e8 on every active whiff record, 1426d8 stage camera state and command timing on wall flight/bounce, 14aad8 wall predicate on live camera bounds. Native full world continues through wall bounce, knockdown, standing recovery, or a human forward/back recovery input. Independent picture/audio hardware comparison and the full original scheduler are outside this check.')
    (ROOT/'outputs/ss6-feasibility/haohmaru_wall_slash_validation.json').write_text(json.dumps(result,indent=2)+'\n')

if __name__=='__main__':main()
