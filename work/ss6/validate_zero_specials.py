"""Zero spirit's Mu, Issen, Rage Explosion and weapon flip on real VS inputs."""
from concurrent.futures import ProcessPoolExecutor
import json
import struct

from validate_dash_motion import ELF, PIN, ROOT, digest
from validate_shin_specials import ASSETS, REPLAY, compare_contacts, configure, read, setup_actor, verify_weapon
from validate_ten_explosion import scenario as ten_scenario, source_callbacks, unavailable_secret

ABC, DE, AB = 1792, 6144, 768
REPORT = ROOT / 'outputs/ss6-feasibility/zero_specials_validation.json'


def scenario(slot, case):
    front = (128,64)[slot]
    back = front^192
    def p(n,own=0,opponent=0):
        return (n,opponent,own) if slot else (n,own,opponent)
    if case in ('weapon','explosion-weapon'):
        return ten_scenario(slot,case)
    if case in ('first-round','explosion'):
        pre = [p(500),p(75,front),p(8)]
        if case=='first-round':return pre,[p(1,DE)]+[p(1)]*80
        return pre,[p(1,ABC)]+[p(1)]*70+[p(1,ABC)]+[p(1)]*160

    # Lose the first round in normal play. Meditation after each hit banks
    # the reserve that carries across rounds. No meter or HP is injected.
    heavy = [p(75,0,back),p(5),p(1,0,1024),p(102),p(1,AB),p(138,AB),p(1)]
    pre = [p(500)]+heavy*6+[p(750)]+heavy*3
    if case=='deciding-ko':
        # Win the second round without spending Mu, then create an actual
        # match-point Issen in the third with both sides still standing.
        own_heavy=[p(65,front),p(5),p(1,1024),p(107)]
        pre=[p(500)]+heavy*6+[p(750)]+own_heavy*6+[p(800)]+heavy*3+own_heavy*5
    if case=='lethal':pre += [p(65,front),p(5),p(1,1024),p(90)]*5
    if case=='unarmed':pre += [p(1,front|8),p(130)]
    if case=='miss':pre += [p(250,back,front),p(5)]
    if case in ('hit','guard','lethal','deciding-ko','expiry','throw','struck','block','disarmed-after'):pre += [p(75,front),p(7)]
    if case=='startup-struck':pre += [p(75,front),p(12),p(1,0,256),p(3)]
    guard=front if case=='guard' else 0
    # The defender evades the rushing sword with a real upward jump.
    second = p(1,ABC,16 if case=='miss' else guard)
    if case=='expiry':steps=[p(1,DE),p(650),p(1,DE),p(80)]
    elif case=='throw':steps=[p(1,DE),p(45),p(1,0,back|1536),p(360)]
    elif case in ('struck','block'):
        steps=[p(1,DE),p(45),p(1,0,256),p(14),p(650,back if case=='block' else 0)]
    elif case=='disarmed-after':
        steps=[p(1,DE),p(45),p(1,front|8),p(135),p(1,ABC),p(650)]
    elif case=='startup-struck':steps=[p(1,DE),p(95)]
    else:steps=[p(1,DE),p(45),second,p(780 if case=='deciding-ko' else 300,0,guard)]
    return pre,[(1,a,b) for n,a,b in steps for _ in range(n)]


def source_entry(slot, incoming, meter, keys, expected, continuation=()):
    src=setup_actor(slot)
    configure(src,4)
    p,a=src.p,src.a
    k=23+26*slot; other=23+26*(1-slot)
    for off,col in ((0x23c,5),(0x244,7),(0x248,8),(0x120,16),(0x124,17),(0x134,18),(0x138,19)):
        p.write(a+off,int(incoming[k+col]),4)
    p.write(a+0xa30,int(incoming[9+10*slot]),4)
    p.write(src.b+0x144,abs(int(float(incoming[7])-float(incoming[17]))),4)
    p.write(src.o+0x38,int(incoming[k+2]),4)
    p.write(src.o+0x10,slot,4) # 11f450 chooses the clock by object selector.
    p.write(src.o+0x40,int(incoming[k]),4);p.write(src.o+0x1040,int(incoming[other]),4)
    j=23+8*slot
    for off,val in zip((0x13c,0x140,0x144,0x148),meter[j:j+4]):p.write(a+off,int(val),4)
    p.write(a+0x11c,int(meter[j+4]),1)
    p.write(0x46a910+slot*4,int(meter[j+7]),4)
    p.write(0x1239d84,int(meter[39]),4)
    for key in keys:r=src.frame(key)
    actual=(r[0]&65535,r[0]>>16,r[54])
    assert actual==expected,(slot,keys,expected,actual,incoming[:23])
    if actual[1]==37:
        assert (r[12],r[13],r[17])==(0x169a50,1,0)
        assert (p.read(0x46a910+4*slot,4),p.read(0x1239d84,4),p.read(0x3ebf30+1024,2),p.read(a+0x11c,1))==(5,0,1,1)
        # The caster's own animation runs at full speed while the opponent
        # and stage freeze. Follow the original callback through its return.
        pos=3+10*slot;cb=88+27*slot
        for row in continuation:
            r=src.frame(0)
            assert (r[0],*r[54:57])==((int(row[pos+1])<<16)|int(row[pos]),int(row[pos+2]),int(row[pos+3]),int(row[cb+11])),(row[0],slot,r[54:57],row[pos:pos+4],row[cb+11])
            if r[0]!=(37<<16)|1:break
        else:assert not continuation
    if actual[:2]==(1,38):assert p.read(a+0x13c,4)==4 and not p.read(a+0x144,4)
    return src.instructions


def verify(spec):
    slot,case=spec;target=1-slot
    pre,pads=scenario(slot,case)
    def trace(name):
        return read(REPLAY,['--mode','versus',f'--p{slot+1}-spirit','zero',name],
                    ['%d %d %d'%r for r in pre+pads])[len(pre)-1:]
    rows,meters=trace('--shin-fields'),trace('--zero-fields')
    sounds={int(r[0]):r for r in trace('--sound-fields')}
    j=23+8*slot;ix=3+10*slot
    starts=[];ins=0
    for i,(old,row) in enumerate(zip(rows,rows[1:]),1):
        state=tuple(map(int,row[ix:ix+3]))
        if state[:2]==tuple(map(int,old[ix:ix+2])) or state[0]!=1 or state[1] not in (36,37,38,78):continue
        cmd={36:[ABC],37:[DE],38:[ABC],78:[32,32|(128,64)[slot],(128,64)[slot]|AB]}[state[1]]
        ins+=source_entry(slot,rows[i-len(cmd)],meters[i-len(cmd)],cmd,state,
                          () if case=='startup-struck' else rows[i+1:i+22])
        starts.append([int(row[0]),state[1],state[2]])
    expected={'weapon':[78],'explosion-weapon':[36,78],'explosion':[36],'unarmed':[],
              'first-round':[],'expiry':[37],'throw':[37],'struck':[37],'block':[37],
              'startup-struck':[37],'disarmed-after':[37]}.get(case,[37,38])
    assert [s[1] for s in starts]==expected,(case,slot,starts)
    if case in ('unarmed','first-round'):
        state=tuple(map(int,rows[1][ix:ix+3]));assert state[:2]==(1,12)
        ins+=source_entry(slot,rows[0],meters[0],[DE],state)
    if case=='explosion':
        assert any(int(r[j+5])==2 for r in meters)
        assert not any(tuple(map(int,r[ix:ix+2]))==(1,38) for r in rows)
    lookup={int(r[0]):r for r in meters}
    spirits=[0,0];spirits[slot]=4
    contacts,n=compare_contacts(slot,38,rows,spirits,sounds,(238,227,625),lookup)
    expected_raw={'weapon':[39],'explosion-weapon':[29,39],'explosion':[29],'hit':[31],
                  'lethal':[31],'deciding-ko':[31],'guard':[31]}.get(case,[])
    assert [v['raw'] for v in contacts]==expected_raw,(case,contacts)
    interruptions=[]
    if case in ('struck','block','startup-struck'):
        action=next(int(old[5+10*target]) for old,now in zip(rows,rows[1:])
                    if old[10+10*target:12+10*target]!=now[10+10*target:12+10*target])
        interruptions,ni=compare_contacts(target,37,rows,spirits,sounds,(action,),lookup)
        n+=ni
        assert len(interruptions)==1,(slot,case,interruptions)
        event=interruptions[0];assert bool(event['defense'])==(case=='block'),event
        m=lookup[event['frame']]
        phase,scale={'struck':(4,256),'block':(3,64),'startup-struck':(2,0)}[case]
        assert (int(m[j]),int(m[39]))==(phase,scale),m
        if case=='startup-struck':
            assert int(next(r for r in rows if r[0]==m[0])[23+26*slot+8])&0x10000
            assert not any(int(r[j])==3 for r in meters)
            event['pending_release']=next(int(r[0]) for r in meters if int(r[j])==4)
    if case=='throw':
        caught=next(r for r in rows if tuple(map(int,r[ix:ix+2]))==(2,13))
        tick=int(caught[0])
        assert int(lookup[tick-1][j])==3 and int(lookup[tick][j])==4
        interruptions=[dict(frame=tick,requested=13)]
    if case=='disarmed-after':
        assert any(tuple(map(int,r[ix:ix+3]))==(0,62,145) for r in rows)
    if case=='guard':assert contacts[0]['defense'] and not contacts[0]['damage'] and any(int(r[ix+2])==228 for r in rows)
    if case in ('hit','lethal','deciding-ko'):
        assert not contacts[0]['defense'] and contacts[0]['requested']==58 and any(int(r[ix+2])==229 for r in rows)
        if case!='hit':assert any(int(r[9+10*target])==0 for r in rows)
        if case=='deciding-ko':
            assert [int(rows[-1][12+10*i]) for i in (slot,target)]==[2,1]
    flight=None
    if case in ('weapon','explosion-weapon'):
        flight=verify_weapon(slot,rows,4,0,contacts[-1]['post_contact_library_seed'])
    if 37 in expected:
        assert int(meters[0][41])==(2 if case=='deciding-ko' else 1) and int(meters[0][j])==2
        assert int(meters[0][j+1])>=int(rows[0][ix+6])*256
        assert int(meters[-1][j])==4
        assert any(int(r[j+7])==5 and int(r[39])==0 and int(r[40])==1 for r in meters)
        if case!='startup-struck':
            assert any(int(r[j])==3 and int(r[j+7])==6 and int(r[39])==64 for r in meters)
    callbacks={}
    if case in ('hit','guard','miss'):
        for who,state,acting in ((slot,38,True),(target,58,False)):
            ins+=source_callbacks(who,rows,state,acting,callbacks,4)
    return dict(player=slot+1,case=case,actions=starts,contacts=contacts,interruptions=interruptions,weapon=flight,
                eligible_reserve=int(meters[0][j+1]),life=int(rows[0][ix+6]),
                original_instructions=ins+n,original_callbacks=callbacks)


def original_bindings(slot):
    actor=setup_actor(slot);configure(actor,4);p=actor.p
    owner=actor.a+0x2c4
    normal=struct.unpack_from('<3h',p.memory,owner+0x4c4+40)
    special=struct.unpack_from('<3h',p.memory,owner+0x644+28)
    assert normal==(27,27,26) and special==(173,-1,177)
    return dict(player=slot+1,system_commands=normal,character_states_78_79_80=special)

def original_damage_registration(slot):
    values={}
    for state in (13,14,32,80,81,82,83):
        src=setup_actor(slot);configure(src,4);p,a=src.p,src.a
        p.write(a+0x194,(state<<16)|2,4);p.write(a+0x18c,0,4)
        p.write(a+0x13c,3,4);p.write(a+0x144,21257,4)
        p.write(0x46a918+4*slot,1,4);p.write(0x1239d84,64,4)
        src.run(0x173108,a)
        got=[p.read(a+0x13c,4),p.read(a+0x144,4),p.read(0x1239d84,4)]
        # Ordinary hurt registration itself preserves Mu. Its earlier
        # damage call already cancelled Mu; the throw cancels on registration.
        assert got==([3,21257,64] if state==32 else [4,0,256]),(slot,state,got)
        values[str(state)]=got
    return values

if __name__=='__main__':
    import sys
    assert digest(ELF)==PIN
    if len(sys.argv)==3:print(verify((int(sys.argv[1]),sys.argv[2])));sys.exit()
    names=('hit','guard','miss','lethal','deciding-ko','expiry','unarmed','first-round','explosion','weapon','explosion-weapon','struck','block','throw','disarmed-after','startup-struck')
    with ProcessPoolExecutor(max_workers=3) as pool:
        rows=list(pool.map(verify,[(slot,case) for slot in range(2) for case in names]))
    report=dict(status='passed',original_sha256=PIN,native_sha256=digest(REPLAY),
                cases=rows,bindings=[original_bindings(slot) for slot in range(2)],
                hurt_registration=[original_damage_registration(s) for s in range(2)],
                unavailable_shin_secret=[unavailable_secret(s,4) for s in range(2)])
    REPORT.write_text(json.dumps(report,indent=2)+'\n')
    print(len(rows),'real-input matches,',sum(len(r['contacts']) for r in rows),'original contacts')
