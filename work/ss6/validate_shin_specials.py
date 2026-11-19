"""Real Shin pad commands and resource-00 combat compared with the Japanese PS2 ELF."""
from concurrent.futures import ProcessPoolExecutor
from itertools import product
from pathlib import Path
import json
import struct
import sys

from validate_collisions import ACTORS, OBJECTS, QUEUE
from validate_combined_slash import initialize_pools
from validate_dash_motion import ASSETS, ELF, PIN, ROOT, digest
from validate_directional_slash import setup_actor
from validate_haohmaru_special import ContactOracle
from validate_pursuit_attack import REPLAY, read


def sequence(slot,move,mode):
    front=(128,64)[slot];back=front^192
    def pair(n,a,b):return (n,b,a) if slot else (n,a,b)
    pre=[(500,0,0)]
    if move==78:
        # Four actual hits activate Shin rage; all later commands are player input.
        for _ in range(4):pre += [pair(65,0,back),(5,0,0),pair(1,0,1024),(88,0,0)]
        pre += [(100,0,0)]
    if mode=='bare':pre += [pair(1,0,back|8),(135,0,0)]
    pre += [pair(130,back,front) if mode=='miss' else pair(75,front,0),(5,0,0)]
    cmd=[32,32|front,front|768] if move==78 else [32|front,back,32|back,32,32|front,front,back,32,(32|back)|1536]
    target=front if mode=='guard' else 0
    moves=[pair(1,pad,0) for pad in cmd]+[pair(1,0,target)]*(910 if move==78 and mode=='hit' else 340)
    if move==78 and mode=='hit':
        # The delivery lands within pickup range in these mirrored encounters.
        moves += [pair(1,0,256)]+[(1,0,0)]*58+[pair(1,0,1024)]
    return pre,moves


def objects(row):
    pos=129;owners=[]
    # Whirlwind diagnostics precede the two weapon lists. Each projectile
    # carries its task handle/callback and 80 words of the real object.
    while (len(row)>=pos+82+10 and 0x100000<=int(row[pos+1])<0x340000
           and int(row[pos+2+0xcc//4])==2):
        pos+=82
    for _ in range(2):
        timer,count=map(int,row[pos:pos+2]);pos+=2
        active=[list(map(int,row[pos+7*i:pos+7*i+7])) for i in range(count)]
        pos+=count*7;owners.append((timer,active))
    assert pos+6==len(row)
    return owners


def configure(actor,spirit):
    actor.p.write(actor.a+0x10c,spirit,4)
    actor.run(0x179258,actor.a+0x2c4,actor.a+0x10c)


def pad_actor(slot,move,mode,rows,cmds,spirit=1,secret_meter=None,battle_clocks=None):
    actor=setup_actor(slot);p=actor.p;configure(actor,spirit)
    f=23+26*slot;of=23+26*(1-slot);b=3+10*slot;c=88+27*slot
    p.write(actor.a+0xa30,int(rows[0][9+10*slot]),4)
    if secret_meter is not None:p.write(actor.a+0x158,secret_meter,4)
    changes=[];entered=False;checks=0;source_trail=None
    for old,now,cmd in zip(rows,rows[1:],cmds):
        if battle_clocks is not None:
            # 1743c0 picks a different idle ACT in the last 30 seconds.
            p.write(actor.b+0x13c,0,4)
            p.write(actor.b+0x114,battle_clocks[int(now[0])],4)
        # The priority-5 gauge update precedes the player visit. On a miss,
        # the current meter is already final, including a rage expiry on recovery.
        meter=now if mode=='miss' else old
        for off,j in [(0x120,16),(0x124,17),(0x134,18),(0x138,19)]:p.write(actor.a+off,int(meter[f+j]),4)
        p.write(actor.o+0x40,int(old[f]),4);p.write(actor.o+0x1040,int(old[of]),4)
        p.write(actor.b+0x144,abs(int(float(old[b+4]))-int(float(old[10*(1-slot)+7]))),4)
        # Run the real clock before issuing this actor visit. This installs
        # the original selector and releases the previous super stop in order.
        actor.run(0x1421b0,actor.b,stops=[0x14238c])
        snap=actor.frame(cmd[1+slot]);state=snap[0];action,step=snap[54:56]
        focus=p.read(0x46a948,4);focus=focus if focus<2**31 else focus-2**32
        globals_=(focus,p.read(actor.b+0x108,4),p.read(actor.b+0x140,4),p.read(0x3ebf30+1024,2))
        assert globals_==tuple(map(int,now[-4:])),(slot,move,now[0],globals_,now[-4:])
        if state>>16==move:entered=True
        if not entered:
            assert (state,action)==((int(now[b+1])<<16)|int(now[b]),int(now[b+2]));continue
        if len(changes)==0 and move==79:
            # 16d9c8 selects the same slot-bound object on either facing.
            h,_=p.run(0x16d9c8,[actor.a],limit=200000)
            source_trail=[p.read(h+n,4) for n in (0xcc,0xc4,0x40,0x44)]
            assert source_trail[0:2]==[6,614]
            child=next(o for o in objects(now)[slot][1] if o[0]==614)
            assert source_trail[2:4]==child[2:4]
        # The open-space replay has no contact stops. It is an independent
        # clock/phase oracle all the way through command recovery.
        if mode!='miss':break
        compare=(state,action,step,snap[56],snap[69],snap[12],snap[13],snap[14])
        actual=((int(now[b+1])<<16)|int(now[b]),int(now[b+2]),int(now[b+3]),int(now[c+11]),int(now[f+1]),*map(int,now[c:c+3]))
        assert compare==actual,(move,slot,now[0],compare,actual)
        if not changes or (state,action)!=tuple(changes[-1][1:]):changes.append([int(now[0]),state,action])
        checks+=1
        if state==0 and action in (0,2):break
    assert entered
    if mode=='miss':assert state==0 and action in (0,2)
    return dict(actor_ticks=checks,actions=changes,source_trail=source_trail,original_instructions=actor.instructions)


def compare_contacts(slot,move,rows,spirits=None,sound_by_tick=None,attack_actions=None,zero_meters=None):
    geo=ContactOracle();p=geo.probe;initialize_pools(p);target=1-slot
    if spirits is None:spirits=[int(i==slot) for i in range(2)]
    stdout=p.read(p.read(0x5d1bf8,4)+8,4)
    for off in (0,16):p.write(stdout+off,0x19e0000,4)
    battle=p.read(0x4d3d00,4);p.write(battle,4,4)
    for i in range(2):p.write(battle+0x24c+4*i,ACTORS+0xf2c*i,4)
    visits=0;events=[]
    def run(fn,*argv):
        nonlocal visits
        result,n=p.run(fn,argv,limit=500000);visits+=n;return result
    if attack_actions is None:attack_actions=(625,) if move==78 else (612,613)
    for old,now in zip(rows,rows[1:]):
        if int(old[5+slot*10]) not in attack_actions:continue
        f=23+26*slot
        for i in (0,1):
            geo.install_player(old,i);p.write(ACTORS+0xf2c*i+0x10c,spirits[i],4)
            if spirits[i]==4 and zero_meters is not None:
                meter=zero_meters[int(old[0])][23+8*i:31+8*i]
                for off,value in zip((0x13c,0x140,0x144,0x148),meter):p.write(ACTORS+0xf2c*i+off,int(value),4)
                p.write(ACTORS+0xf2c*i+0x11c,int(meter[4]),1)
        p.write(0x12d2698,0,4)
        for order in (OBJECTS,OBJECTS[::-1]):run(0x1536e8,*order)
        run(0x1544a0);matched=False
        for i in range(p.read(0x12d2698,4)):
            e=QUEUE+i*108
            if p.read(e,4)!=7 or p.read(e+0x40,4)!=OBJECTS[slot] or int(old[f+3])&0x06000000:continue
            defense=run(0x155850,e);raw=p.read(e+0x20,4)
            if sound_by_tick is not None:
                rng=sound_by_tick[int(old[0])]
                p.write(0x3d2e80,int(rng[23]),4)
                p.write(p.read(0x5d1bf8,4)+0xa8,int(rng[24]),8)
            run(0x155d50 if defense else 0x155a88,e,1,defense)
            recipient=ACTORS+0xf2c*target;damage=p.read(recipient+0xa38,4);reaction=p.read(recipient+0x192,2)
            old_life=int(old[9+10*target]);actual=old_life-int(now[9+10*target])
            if zero_meters is not None and spirits[target]==4:
                # 1a44dc ends active Mu before the later hurt-state entry.
                # Snapshot at that same contact distinguishes guard from hit.
                j=23+8*target
                if int(zero_meters[int(old[0])][j])==3:
                    assert p.read(recipient+0x13c,4)==int(zero_meters[int(now[0])][j]),(now[0],target,defense)
                if int(old[23+26*target+8])&8:
                    assert (p.read(recipient+0x248,4)^int(now[23+26*target+8]))&0x10000==0,(now[0],target,defense)
            assert min(old_life,damage)==actual,(move,slot,now[0],damage,actual,defense)
            assert int(now[4+10*target])==(71 if reaction==83 else reaction),(slot,move,now[0],reaction,now[:23])
            assert int(now[10+10*slot+bool(defense)])==int(old[10+10*slot+bool(defense)])+1
            events.append(dict(frame=int(now[0]),act=int(old[5+slot*10]),step=int(old[6+slot*10]),raw=raw,defense=defense,damage=damage,requested=reaction,entered=int(now[4+10*target])))
            if sound_by_tick is not None:
                events[-1]['post_contact_library_seed']=p.read(p.read(0x5d1bf8,4)+0xa8,8)
            matched=True;break
        assert matched==(old[10+10*slot:12+10*slot]!=now[10+10*slot:12+10*slot]),(slot,move,old[0],now[:23])
    return events,visits

def verify_weapon(slot,rows,attacking_spirit=1,target_spirit=0,drop_library_seed=None,first_only=False,battle_clocks=None):
    from validate_weapon_handling import setup
    target=1-slot;f=23+26*target;b=3+10*target;c=88+27*target
    first=next(i for i,r in enumerate(rows) if int(r[b+2])==1295)
    actor,registry=setup(target);p=actor.p;a=actor.a;o=actor.o
    configure(actor,target_spirit)
    if drop_library_seed is not None:
        p.write(p.read(0x5d1bf8,4)+0xa8,drop_library_seed,8)
    for addr,value in ((o+0x40,int(rows[first][f])),(o+0x38,int(rows[first][f+2])),
                       (a+0x194,(83<<16)|2),(a+0x18c,1),(actor.other+0x10c,attacking_spirit),
                       (a+0xa30,int(rows[first][b+6]))):p.write(addr,value,4)
    original_run=actor.run;speed=0
    def run(fn,*args,**kwargs):
        if fn==0x151b00:
            # The fighter fixture normally runs at full speed. The real 168750
            # slow-motion timers select 85, then 128, then 256 subunits per tick.
            delta=(256,128,85,0)[speed];p.write(a+0x1ac,delta,4);p.write(o+0x30,delta,4)
        return original_run(fn,*args,**kwargs)
    actor.run=run
    actions=[];checks=0
    for i in range(first,min(first+245,len(rows))):
        row,old=rows[i],rows[i-1]
        if battle_clocks is not None:
            p.write(actor.b+0x13c,0,4);p.write(actor.b+0x114,battle_clocks[int(row[0])],4)
        if i>first:
            speed=2 if int(old[-5]) else 1 if int(old[-6]) else 0
            p.write(actor.b+0x140,speed,4);actor.run(0x147028,registry,48)
        snap=actor.frame(0)
        if i==first:
            assert [p.read(actor.b+0x114+4*n,4) for n in (5,6)]==list(map(int,row[-6:-4]))
        actor.run(0x146ef8,registry,48);actor.run(0x1207d8);actor.run(0x1470a8,registry,48)
        want=[]
        for task in struct.unpack_from('<48I',p.memory,registry):
            if not task:continue
            child=p.read(task+28,4)
            want.append([p.read(child+k,4) for k in (0x24,0x28,0x40,0x44,0x104,0x108)]+[p.read(task,4)])
        timer,items=objects(row)[target]
        assert items==want,(slot,row[0],items,want)
        assert timer==p.read(a+0x1b0+4*14,4),(slot,row[0],timer,p.read(a+0x1b0+4*14,4))
        actual=((int(row[b+1])<<16)|int(row[b]),int(row[b+2]),int(row[b+3]),int(row[c+11]),int(row[f+1]),*map(int,row[c:c+7]))
        assert actual==(snap[0],*snap[54:57],snap[69],*snap[12:19]),(slot,row[0],actual,snap[:19])
        if not actions or actions[-1]!=snap[54]:actions.append(snap[54])
        checks+=len(items)
        if first_only:break
        if i>first+5 and snap[0]==0 and snap[54] in (1,3):break
    assert actions==[1295] if first_only else actions[:-1]==[1295,1297,49,53] and actions[-1] in (1,3)
    return dict(ticks=i-first+1,object_records=checks,actions=actions,original_instructions=actor.instructions)


def verify_limits(slot):
    front=(128,64)[slot];back=front^192
    def pair(n,a):return (n,0,a) if slot else (n,a,0)
    secret=[front|32,back,back|32,32,front|32,front,back,32,(back|32)|1536]
    breaker=[32,32|front,front|768]
    results=[]
    for name,cmd,discard,repeat in [('breaker without rage',breaker,False,False),('secret unarmed',secret,True,False),('secret repeated',secret,False,True)]:
        actor=setup_actor(slot);configure(actor,1);p=actor.p
        pre=[(500,0,0)]
        if discard:
            pre += [pair(1,front|8),(130,0,0)];p.write(actor.a+0x23c,p.read(actor.a+0x23c,4)&~0x1000,4)
        if repeat:
            pre += [pair(1,key) for key in secret]+[(300,0,0)]
            # Verify the input changes eligibility in the executable and that
            # 14fe10 preserves this one-per-match latch across a round reset.
            for key in secret:successful=actor.frame(key)
            assert successful[0]==(79<<16)|1 and p.read(actor.a+0x244,4)&0x40
            p.run(0x14fe10,[actor.a+0x23c],limit=200000)
            assert p.read(actor.a+0x244,4)&0x40
            fresh=setup_actor(slot);configure(fresh,1);fresh.p.write(fresh.a+0x244,p.read(actor.a+0x244,4),4);actor=fresh
        pads=pre+[pair(1,k) for k in cmd]
        rows=read(REPLAY,['--mode','versus',f'--p{slot+1}-spirit','shin','--contact-fields'],['%d %d %d'%pad for pad in pads])
        for key in cmd:snap=actor.frame(key)
        row=rows[-1];state=snap[0];action=snap[54]
        assert (state,action)==((int(row[4+10*slot])<<16)|int(row[3+10*slot]),int(row[5+10*slot])),(slot,name,state,action,row[:23])
        assert (state>>16) not in (78,79)
        results.append(dict(player=slot+1,case=name,state=state>>16,action=action))
    return results

def simultaneous():
    left=[160,64,96,32,160,128,64,32,1632]
    right=[96,128,160,32,96,64,128,32,1696]
    seq=[(500,0,0)]+[(1,a,b) for a,b in zip(left,right)]+[(1,0,0)]*21
    rows=read(REPLAY,['--mode','versus','--p1-spirit','shin','--p2-spirit','shin','--shin-fields'],['%d %d %d'%p for p in seq])[len(left):]
    source=setup_actor(0);p=source.p
    lock,_=p.run(0x168c18,[0,612]);assert lock==16
    for seat in (0,1):p.run(0x141318,[lock,seat,1],limit=50000)
    assert list(map(int,(rows[0][4],rows[0][14])))==[79,79]
    focus=[]
    for tick,row in enumerate(rows):
        if tick:source.run(0x1421b0,source.b,stops=[0x14238c])
        selector=struct.unpack_from('<i',p.memory,0x46a948)[0]
        assert [selector,p.read(source.b+0x108,4),p.read(source.b+0x140,4),p.read(0x3ebf30+1024,2)]==list(map(int,row[-4:]))
        for i,a in enumerate((source.a,source.other)):
            assert (p.read(a+0x23c,4)^int(row[28+26*i]))&0x08000000==0
        focus.append(selector)
    assert focus[:17]==[1]*17 and focus[17:]==[-2]*5
    return dict(first_tick=int(rows[0][0]),owner=2,held_updates=16)


def check(args):
    slot,move,mode=args;target=1-slot;pre,pads=sequence(slot,move,mode)
    rows=read(REPLAY,['--mode','versus',f'--p{slot+1}-spirit','shin','--shin-fields'],['%d %d %d'%entry for entry in pre+pads])[len(pre)-1:]
    assert int(rows[0][39+26*slot])==int(move==78)
    actor=pad_actor(slot,move,mode,rows,pads)
    events,ins=compare_contacts(slot,move,rows)
    assert bool(events)==(mode!='miss') and all(bool(e['defense'])==(mode=='guard') for e in events)
    arms={bool(int(row[28+26*target])&0x1000) for row in rows}
    expected={False} if mode=='bare' else {True,False} if move==78 and mode=='hit' else {True}
    assert arms==expected,(move,slot,mode,arms)
    seen={};timer_start=0
    for row in rows:
        timer,objs=objects(row)[target]
        if timer==600*256 and not timer_start:timer_start=int(row[0])
        for o in objs:seen.setdefault(o[0],int(row[0]))
    broken=move==78 and mode=='hit'
    assert all((act in seen)==broken for act in (468,469,470,471))
    if broken:
        assert timer_start==seen[469]==seen[470]==seen[471] and seen[468]==events[0]['frame']
        assert objects(rows[-1])[target][0]==0
        assert seen[466]>timer_start+590 and seen[467]>seen[466]
        pickup=next(row for row in rows if int(row[5+10*target])==136)
        assert int(pickup[4+10*target])==51 and int(pickup[28+26*target])&0x1000
        assert not objects(pickup)[target][1] and int(rows[-1][5+10*target])==190
    return dict(player=slot+1,state=move,mode=mode,broken_weapon=verify_weapon(slot,rows) if broken else None,events=events,original_contact_instructions=ins,body=actor,weapon_first_frames=seen,timer_start=timer_start)

if __name__=='__main__':
    assert digest(ELF)==PIN
    cases=list(product(range(2),(78,79),('hit','guard','miss','bare')))
    if len(sys.argv)==4:print(check((int(sys.argv[1]),int(sys.argv[2]),sys.argv[3])));sys.exit()
    with ProcessPoolExecutor(max_workers=3) as pool:result=list(pool.map(check,cases))
    report=dict(original_sha256=PIN,native_sha256=digest(REPLAY),simultaneous=simultaneous(),limits=[r for side in range(2) for r in verify_limits(side)],cases=result)
    output=ROOT/'outputs/ss6-feasibility/shin_special_validation.json';output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print(len(result),'cases passed',output)
