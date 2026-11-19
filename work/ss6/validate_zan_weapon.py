"""Haohmaru's Zan weapon-flipping technique against the Japanese PS2 callbacks."""
from concurrent.futures import ProcessPoolExecutor
from itertools import product
import json
from pathlib import Path
import struct
import sys
from validate_shin_specials import ASSETS, ELF, PIN, REPLAY, ROOT, compare_contacts, configure, digest, objects, pad_actor, read, setup_actor, verify_weapon

REPORT=ROOT/'outputs/ss6-feasibility/zan_weapon_flip_validation.json'

def sequence(slot,mode,prime):
    front=(128,64)[slot];back=front^192
    def pair(n,a,b):return (n,b,a) if slot else (n,a,b)
    pre=[(500,0,0)]
    if prime=='charge':
        pre.extend([pair(400,768,0),(15,0,0)])
    else:
        for _ in range(5 if prime=='critical' else 4):
            pre.extend([pair(65,0,back),(5,0,0),pair(1,0,1024),(88,0,0)])
        if prime=='critical':
            pre.extend([pair(65,0,back),(5,0,0),pair(1,0,256),(70,0,0)])
        pre.append((100,0,0))
    if mode=='bare':pre.extend([pair(1,0,back|8),(135,0,0)])
    pre.extend([pair(130,back,front) if mode=='miss' else pair(75,front,0),(5,0,0)])
    pads=[pair(1,key,0) for key in [32,32|front,front|768]]
    pads.extend([pair(1,0,front if mode=='guard' else 0)]*360)
    return pre,pads

def real(slot,other,trace,segments):
    options=['--mode','versus',f'--p{slot+1}-spirit','zan',f'--p{2-slot}-spirit',other,trace]
    return read(REPLAY,options,['%d %d %d'%seg for seg in segments])

def check(spec):
    slot,mode,prime,other=spec;t=1-slot;opponent={'rage':0,'shin':1,'zan':2}[other];pre,pads=sequence(slot,mode,prime)
    rows=real(slot,other,'--shin-fields',pre+pads)[len(pre)-1:];base=23+26*slot;target=23+26*t
    assert int(rows[0][base+16]) in (1,2),(spec,'rage',rows[0][base+16:base+20],rows[0][:23])
    assert int(rows[0][9+10*slot])<=20 if prime=='critical' else int(rows[0][9+10*slot])>20
    if prime=='charge':assert int(rows[0][9+10*slot])==200
    actor=pad_actor(slot,78,mode,rows,pads,2)
    spirits=[2,2];spirits[t]=opponent
    sound_rows=real(slot,other,'--sound-fields',pre+pads) if mode=='hit' else []
    sound_by_tick={int(r[0]):r for r in sound_rows} if sound_rows else None
    contact,ins=compare_contacts(slot,78,rows,spirits,sound_by_tick)
    assert len(contact)=={'hit':1,'bare':1,'miss':0,'guard':4}[mode]
    assert all(e['raw']==39 and bool(e['defense'])==(mode=='guard') for e in contact)
    observed={}
    for row in rows:
        timer,blades=objects(row)[t]
        assert timer==0,(spec,row[0],timer)
        for blade in blades:observed.setdefault(blade[0],int(row[0]))
    assert not set(observed)&{468,469,470,471}
    pickup=None;flight=None
    if mode=='hit':
        assert observed.keys()=={466,467} and observed[466]==contact[0]['frame']<observed[467]
        assert int(rows[0][target+5])&0x1000 and not int(rows[-1][target+5])&0x1000
        flight=verify_weapon(slot,rows,2,opponent,contact[0]['post_contact_library_seed'])
        # Walk toward the sword at its actual touchdown position. Stop as
        # soon as the original light-slash pickup predicate can see it.
        base_inputs=pre+pads
        def pair(n,k):return (n,0,k) if t else (n,k,0)
        x=float(rows[-1][7+10*t]);blade=objects(rows[-1])[t][1][0];wx=struct.unpack('<f',struct.pack('<I',blade[2]))[0]
        move=128 if wx>x else 64
        approach=real(slot,other,'--shin-fields',base_inputs+[pair(1,move)]*250)[len(base_inputs)-1:]
        walk=next(i for i,row in enumerate(approach) if abs(wx-float(row[7+10*t]))<12)
        after=([pair(walk,move)] if walk else [])+[(4,0,0),pair(1,256)]+[(1,0,0)]*55+[pair(1,1024)]
        end=real(slot,other,'--shin-fields',base_inputs+after)[len(base_inputs):]
        acquired=next(r for r in end if int(r[5+10*t])==136)
        assert int(acquired[4+10*t])==51 and int(acquired[target+5])&0x1000 and not objects(acquired)[t][1]
        assert int(end[-1][5+10*t]) in (189,190)
        pickup=dict(frame=int(acquired[0]),heavy=int(end[-1][5+10*t]),walk=walk)
    elif mode=='bare':
        assert not any(int(r[target+5])&0x1000 for r in rows)
        # The target already placed its own sword on the floor. A second
        # sword must not be created merely because raw39 reaches state83.
        assert all(len(objects(r)[t][1])==1 for r in rows)
    else:assert not observed and all(int(r[target+5])&0x1000 for r in rows)
    return dict(player=slot+1,victim_spirit=other,mode=mode,priming=prime,source_life=int(rows[0][9+10*slot]),
                contacts=contact,actor=actor,flight=flight,weapon_first_frames=observed,pickup=pickup,original_contact_instructions=ins)

def restrictions(slot):
    front=(128,64)[slot];back=front^192
    def pair(n,k):return (n,0,k) if slot else (n,k,0)
    out=[]
    for name,command in [('236+AB uncharged',[32,front|32,front|768]),('Shin secret',[front|32,back,back|32,32,front|32,front,back,32,(back|32)|1536])]:
        source=setup_actor(slot);configure(source,2)
        owner=source.a+0x2c4
        ids=struct.unpack_from('<17h',source.p.memory,owner+0x644)
        assert ids[14:]==(173,-1,177)
        for k in command:record=source.frame(k)
        realrow=real(slot,'shin','--contact-fields',[(500,0,0)]+[pair(1,k) for k in command])[-1]
        assert (record[0]>>16,record[54])==(int(realrow[4+10*slot]),int(realrow[5+10*slot]))
        assert record[0]>>16 not in (78,79)
        out.append(dict(player=slot+1,case=name,state=record[0]>>16,act=record[54]))
    return out

def lethal(slot):
    # A living target starts timers 5 and 6. Under 168750 a defeated
    # target still drops its intact sword but leaves both timers alone.
    front=(128,64)[slot];target=1-slot
    def pair(n,key):return (n,0,key) if slot else (n,key,0)
    pre=[(500,0,0)]
    for _ in range(5):
        pre.extend([pair(65,front),(5,0,0),pair(1,1024),(88,0,0)])
    pre.extend([pair(400,768),(15,0,0),pair(75,front),(5,0,0)])
    pads=[pair(1,k) for k in (32,front|32,front|768)]+[(1,0,0)]*115
    rows=real(slot,'rage','--shin-fields',pre+pads)[len(pre)-1:]
    sounds={int(r[0]):r for r in real(slot,'rage','--sound-fields',pre+pads)}
    spirits=[0,0];spirits[slot]=2
    events,ins=compare_contacts(slot,78,rows,spirits,sounds)
    assert len(events)==1 and events[0]['raw']==39
    frame=events[0]['frame'];before,hit=rows[frame-int(rows[0][0])-1:frame-int(rows[0][0])+1]
    assert int(before[9+10*target])>0 and int(hit[9+10*target])==0
    assert [int(v) for v in hit[-6:-4]]==[0,0]
    flight=verify_weapon(slot,rows,2,0,events[0]['post_contact_library_seed'],first_only=True)
    return dict(player=slot+1,damage=events[0]['damage'],remaining_life=int(before[9+10*target]),frame=frame,flight=flight,original_contact_instructions=ins)

if __name__=='__main__':
    assert digest(ELF)==PIN
    data=ELF.read_bytes()
    for offset,name in [(0x4e3930,'斬スピリッツ'),(0x4e3ac8,'武器飛ばし技'),(0x4e46b8,'天覇凄煌斬')]:
        assert data[offset:].startswith(name.encode('cp932'))
    if len(sys.argv)==5:print(check((int(sys.argv[1]),*sys.argv[2:])));sys.exit()
    cases=[(s,m,'damage','shin') for s,m in product(range(2),('hit','guard','miss','bare'))]
    cases.extend((s,'hit',p,'rage') for s,p in product(range(2),('charge','critical')))
    with ProcessPoolExecutor(max_workers=3) as pool:results=list(pool.map(check,cases))
    report=dict(original_sha256=PIN,native_sha256=digest(REPLAY),restrictions=[r for s in range(2) for r in restrictions(s)],lethal=[lethal(s) for s in range(2)],cases=results)
    REPORT.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print(len(results),'matches',REPORT)
