#!/usr/bin/env python3
"""Compare Ten's four 連斬 paths, command cancels and rejected inputs to the Japanese game."""
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import json
import struct
import sys

from validate_collisions import ACTORS, OBJECTS
from validate_dash_motion import ELF, PIN, ROOT, digest
from validate_haohmaru_special import ContactOracle
from validate_shin_evasion import EXE, replay, setup_state
from validate_weapon_handling import setup

OUT=ROOT/'outputs/ss6-feasibility/ten_chain_validation.json'
A,B,C,D=256,512,1024,2048
ROUTES={
    'AAA':[(15,A),(32,A),(49,A)],
    'BBC':[(15,B),(31,B),(48,C)],
    'CCD':[(15,C),(31,C),(52,D)],
    'AABBCCC':[(15,A),(32,A),(49,B),(64,B),(81,C),(97,C),(114,C)]
}
STATES={
    'AAA':[39,40,41,42,43], 'BBC':[39,40,44,45,46],
    'CCD':[39,40,47,48,49], 'AABBCCC':[39,40,41,42,50,51,52,53,54]
}
CASES=[*ROUTES,'cancel236','cancel623','whiff','guard','crouching-guard','early','invalid-D',
       'multi-button','holding-A','bare','air-start','crouch-start','crouch-target','jump-target','jump-over','finisher-blocked','finisher-whiff']


class TenContacts(ContactOracle):
    def __init__(self,slot):
        super().__init__()
        self.slot=slot

    def install_player(self,row,slot):
        super().install_player(row,slot)
        self.probe.write(ACTORS+slot*0xf2c+0x10c,3 if slot==self.slot else 0,4)


def controls(slot,mode):
    front,back=(128,64) if slot==0 else (64,128)
    pair=lambda x,y:(y,x) if slot else (x,y)
    opener={0:A|B}
    defender={}
    start=[(500,0,0)]
    if mode=='bare':
        start.extend([(1,*pair(front|8,0)),(135,0,0),(36,*pair(back,0)),(10,0,0)])
    else:
        far=mode in ('whiff','air-start','crouch-start')
        start.extend([(60 if far else 40,*(pair(back,front) if far else pair(front,back))),(8,0,0)])
    if mode in ROUTES:opener.update(ROUTES[mode])
    elif mode.startswith('finisher-'):
        # An airborne opening hit leaves the next slashes swinging through
        # empty space. Without their hitstop, the input windows come earlier.
        opener.update(zip((15,28,39,49,60,71,87),(A,A,B,B,C,C,C)))
        defender[6]=16
        defender.update(dict.fromkeys(range(20,170),front|(16 if mode=='finisher-whiff' else 0)))
    elif mode.startswith('cancel'):
        opener.update(ROUTES['BBC'])
        directions=(32,32|front,front|A) if mode=='cancel236' else (front,32,32|front|A)
        opener.update(enumerate(directions,55))
    elif mode=='early':opener[5]=A
    elif mode=='invalid-D':opener[15]=D
    elif mode=='multi-button':opener[15]=B|C
    elif mode=='holding-A':opener.update({i:A for i in range(1,28)})
    elif mode=='air-start':opener={0:16,9:A|B}
    elif mode=='crouch-start':opener={**dict.fromkeys(range(10),32),10:32|A|B}
    elif mode in ('guard','crouching-guard','crouch-target'):
        defender=dict.fromkeys(range(40),{'guard':front,'crouching-guard':32|front,'crouch-target':32}[mode])
    elif mode=='jump-target':defender[6]=16
    elif mode=='jump-over':defender[1]=16
    duration=305 if mode in ROUTES else 195 if mode.startswith(('cancel','finisher-')) else 100
    pads=[(opener.get(i,0),defender.get(i,0)) for i in range(duration)]
    return start,pads,[*start,*[(1,*pair(*v)) for v in pads]]


def case(args):
    slot,mode=args
    start,pads,commands=controls(slot,mode)
    rows=replay(slot,'ten',commands)[len(start)-1:]
    core,col,cb=3+10*slot,23+26*slot,88+27*slot
    victim=1-slot
    source=TenContacts(slot)
    # On a special cancel the slash chain has ended. Separate validators cover
    # projectile collision and the rising slash once their own callbacks run.
    cancel=next((j for j,row in enumerate(rows) if int(row[core])==1 and int(row[core+1])>=64),None)
    if mode.startswith('cancel'):
        assert cancel and rows[cancel-1][core:core+2]==['1','46']
        assert int(rows[cancel][core+1])=={'cancel236':64,'cancel623':68}[mode]
    else:assert cancel is None,(args,cancel)
    def capture(e,p,item,target):
        e['part']=p.run(0x153140,[item+0x48])[0]
        e['strength']=p.read(item+12,4)
        e['secondary']=p.read(target+0x256,1)
        e['counter']=p.run(0x157fa8,[target,item+0x48])[0]
    hits=source.contacts(rows[:cancel] if cancel else rows,slot,capture)
    if mode.startswith('cancel') or mode in ROUTES:
        assert len(hits)==(8 if mode=='AABBCCC' else 4),(args,hits)
    elif mode.startswith('finisher-'):
        assert len(hits)==(1 if mode=='finisher-whiff' else 3) and hits[0]['target_state']==74
        assert all(e['defense'] for e in hits[1:])
    elif mode in ('early','invalid-D','multi-button','holding-A','guard','crouching-guard','crouch-target','jump-target'):
        assert len(hits)==1,(args,hits)
    else:assert not hits,(args,hits)
    if mode=='jump-target':assert hits[0]['target_state']==74
    if mode.endswith('guard'):assert hits[0]['defense']==(2 if mode=='crouching-guard' else 1)
    contacts={e['frame']:e for e in hits}
    src,_=setup(slot)
    setup_state(src,3,0,rows[0],slot,mode=='bare')
    p,a,o=src.p,src.a,src.o
    observed=[]
    for j,((held,_),prev,now) in enumerate(zip(pads,rows,rows[1:]),1):
        p.write(o+0x1040,int(prev[23+26*victim]),4)
        p.write(src.b+0x144,abs(int(float(prev[7]))-int(float(prev[17]))),4)
        if e:=contacts.get(int(now[0])):
            # 153450/155a88 acknowledge an accepted source once per ACT entry.
            # The original contact table selects both pause timers, including
            # the standing-column timing when the defender was hit in the air.
            blocked=e['defense']
            p.write(o+0x104,p.read(o+0x104,4)|(0x2080000 if blocked else 0x2040000),4)
            if blocked:
                src.run(0x14d5a0,src.other,o,blocked,e['strength'])
                # 155564 also tests the attacker's descriptor; the blocked
                # opener queues its dedicated ACT 307 from the recoil state.
                if p.run(0x169700,[a])[0]:src.run(0x14d070,a,e['strength'],0)
            else:src.run(0x151578,src.other,o,e['target_state'],e['secondary'])
        v=src.frame(held)
        got=[int(now[core])|int(now[core+1])<<16,*map(int,now[core+2:core+4]),int(now[cb+11]),
             *map(int,now[cb:cb+3]),*map(int,now[cb+8:cb+10]),int(now[col+17])]
        want=[v[0],v[54],v[55],v[56],*v[12:15],v[19],v[20],p.read(a+0x124,4)]
        assert got==want,(args,j,int(now[0]),[(i,x,y) for i,(x,y) in enumerate(zip(got,want)) if x!=y])
        record=[v[0]&65535,v[0]>>16,v[54]]
        if not observed or record!=observed[-1][1]:observed.append([int(now[0]),record])
        if j==cancel:break
        if j>12 and record==[0,0,int(mode=='bare')]:break
    route='BBC' if mode.startswith('cancel') else 'AABBCCC' if mode.startswith('finisher-') else mode
    attack_states=list(dict.fromkeys(s for _,(t,s,_) in observed if t==1 and 39<=s<=54))
    if mode in ('guard','crouching-guard'):
        assert any(t==0 and 25<=s<=30 and act==307 for _,(t,s,act) in observed)
    if route in ROUTES:assert attack_states==STATES[route],(args,attack_states)
    elif mode in ('bare','air-start'):assert not attack_states and any(x[2] in (201,209) for _,x in observed)
    elif mode in ('guard','crouching-guard','whiff','jump-over','crouch-start'):assert attack_states==[39],(args,attack_states)
    else:assert attack_states==[39,40],(args,attack_states)
    assert int(rows[-1][col+17])==(27648 if mode=='AABBCCC' else 0)
    assert list(map(int,rows[-1][core:core+3]))==[0,0,int(mode=='bare')],(args,rows[-1][:23])
    victim_result=None
    if mode in ROUTES:
        victim_result=compare_recipient(slot,rows,pads,hits)
        assert int(rows[-1][9+10*victim])==(160 if mode=='AABBCCC' else 178)
        assert list(map(int,rows[-1][3+10*victim:6+10*victim]))==[0,0,0],(args,rows[-1][:23])
    return dict(player=slot+1,case=mode,controls=[[i,x,y] for i,(x,y) in enumerate(pads) if x or y],
                contacts=hits,matched_actor_visits=j,original_actor_instructions=src.instructions,
                state_and_action=observed,recipient=victim_result,life=int(rows[-1][9+10*victim]),rage=int(rows[-1][col+17]))


def compare_recipient(slot,rows,pads,hits):
    """Run each fresh 14d198 and the recipient continuously through rising."""
    victim=1-slot
    src,_=setup(victim)
    setup_state(src,0,0,rows[0],victim,False)
    p,a,o=src.p,src.a,src.o
    events={e['frame']:e for e in hits}
    col,cb,core=23+26*victim,88+27*victim,3+10*victim
    other=23+26*slot
    states=[]
    for tick,((_,held),prev,now) in enumerate(zip(pads,rows,rows[1:]),1):
        # The stage clamps and pushes the two actors. Supply its horizontal
        # positions; the EE continuously integrates the vertical fall itself.
        p.write(o+0x1040,int(prev[other]),4);p.write(o+0x40,int(prev[col]),4)
        p.write(src.b+0x144,abs(int(float(prev[7]))-int(float(prev[17]))),4)
        p.write(src.other+0x194,int(prev[3+10*slot])|int(prev[4+10*slot])<<16,4)
        p.write(src.other+0x19a,int(prev[other+10]),1)
        if e:=events.get(int(now[0])):
            src.run(0x14d198,a,o+0x1000,0,e['raw'],e['part'],e['counter'])
            for off,val in zip((0x250,0x251,0x252,0x254),e['metadata']):p.write(a+off,val,1)
            p.write(a+0xa38,e['damage'],4)
            p.write(a+0x24c,int(prev[col+9]),1)
        v=src.frame(held)
        got=[int(now[core])|int(now[core+1])<<16,*map(int,now[core+2:core+4]),int(now[cb+11]),
             *map(int,now[cb:cb+3]),*map(int,now[cb+8:cb+10]),int(now[col+1])]
        want=[v[0],v[54],v[55],v[56],*v[12:15],v[19],v[20],v[69]]
        if int(now[0])<min(events):continue
        assert got==want,(slot,tick,int(now[0]),got,want)
        pose=[v[0]&65535,v[0]>>16,v[54]]
        if not states or pose!=states[-1][1]:states.append([int(now[0]),pose])
        if int(now[0])>max(events) and pose==[0,0,0]:
            return dict(visits=tick,original_instructions=src.instructions,states=states)
    raise AssertionError((slot,'Recipient never stood up',states))


def main():
    assert digest(ELF)==PIN
    image=ELF.read_bytes()
    # Menu pointers are linked EE virtual addresses, while this ELF's text
    # strings have file offsets 0xff000 below their runtime addresses.
    entries=[]
    for pos in range(0x3cbdd8,0x3cbe29,20):
        row=[]
        for address in struct.unpack_from('<3I',image,pos):
            start=address-0xff000
            row.append(image[start:image.index(0,start)].decode('cp932'))
        entries.append(row)
    assert entries[0]==['連斬入り込み','','IAIB同時押し']
    assert [s[2].split('CR')[0] for s in entries[1:]]==['IA・IA・IA','IB・IB・IC','IC・IC・ID','IA・IA・IB・IB・IC・IC・IC']
    jobs=[(who,name) for who in range(2) for name in CASES]
    if len(sys.argv)==3:print(json.dumps(case((int(sys.argv[1]),sys.argv[2])),ensure_ascii=False));return
    with ProcessPoolExecutor(6) as pool: results=list(pool.map(case,jobs))
    verdict=dict(original_sha256=PIN,native_sha256=digest(EXE),validator_sha256=digest(Path(__file__)),help=entries,
        scope='Both players use the console versus input pipeline. The original Japanese input, ACT and callbacks run continuously on the attacker. Original geometry/defense/damage handlers use prior native positions and clips on both actors. Cases with special cancels compare through the first special ACT. The original recipient is also compared continuously on all four completed routes through landing and getting up, including its vertical motion, hitstop and ACT. Horizontal stage clamps/pushes are supplied separately.',
        original_actor_visits=sum(r['matched_actor_visits'] for r in results),
        original_actor_instructions=sum(r['original_actor_instructions'] for r in results),
        original_recipient_visits=sum(r['recipient']['visits'] for r in results if r['recipient']),
        original_recipient_instructions=sum(r['recipient']['original_instructions'] for r in results if r['recipient']),cases=results)
    OUT.write_text(json.dumps(verdict,indent=2,ensure_ascii=False)+'\n')
    print(f'{len(results)} Ten 連斬 scenarios matched the Japanese actor and collision paths')

if __name__=='__main__':main()
