"""Compare Ten Rage Explosion, Issen and the weapon flip with the Japanese game."""
from concurrent.futures import ProcessPoolExecutor
import json
import sys

from validate_dash_motion import ELF, PIN, ROOT, digest
from validate_pursuit_attack import REPLAY, read
import struct
from validate_shin_specials import ASSETS, compare_contacts, configure, objects, setup_actor, verify_weapon

REPORT=ROOT/'outputs/ss6-feasibility/ten_explosion_validation.json'
ABC=1792

def scenario(slot,name):
    front=(128,64)[slot]
    back=front^192
    def pair(n,actor=0,defender=0):
        return (n,defender,actor) if slot else (n,actor,defender)
    pre=[pair(500)]
    if name!='full':
        for _ in range(5 if name=='weapon' else 3):
            pre.extend([pair(65,0,back),pair(5),pair(1,0,1024),pair(88)])
    if name in ('bare','bare-target'):
        pre.extend([pair(1,front|8) if name=='bare' else pair(1,0,back|8),pair(135)])
    if name=='lethal':
        for _ in range(5):
            pre.extend([pair(65,front),pair(5),pair(1,1024),pair(88)])
    near=name in ('full','air','hit','bare','bare-target','lethal','weapon','explosion-weapon')
    pre.extend([pair(75,front) if near else pair(75 if name=='late' else 270,back,front),pair(8)])
    if name=='air':pre.extend([pair(1,0,16),pair(1)])
    if name=='explosion-weapon':
        steps=[pair(1,ABC),pair(60),pair(70,front,back),pair(8),
               pair(1,32),pair(1,front|32),pair(1,front|768)]
    elif name=='weapon':
        steps=[pair(1,32),pair(1,front|32),pair(1,front|768)]
    else:
        steps=[pair(1,ABC),pair(130 if name=='late' else 60)]
        if name!='miss':steps.extend([pair(130 if name=='late' else 80,front,back),pair(10 if name=='late' else 8)])
        # An opponent can actually evade Issen by jumping at a distance.
        guard=front if name=='guard' else 0
        steps.extend([pair(1,ABC,16 if name=='miss' else guard),pair(285,0,guard)])
        # The normal once-per-match gate must also reject a later ABC.
        steps.extend([pair(1,ABC),pair(70)])
    steps.extend([pair(330)])
    pads=[(1,x,y) for count,x,y in steps for _ in range(count)]
    return pre,pads

def play(slot,pre,pads,trace,spirit=3):
    return read(REPLAY,['--mode','versus',f'--p{slot+1}-spirit',{3:'ten',4:'zero'}[spirit],trace],
                ['%d %d %d'%r for r in pre+pads])[len(pre)-1:]

def original_entry(slot,move,start,inputs):
    src=setup_actor(slot)
    configure(src,3)
    p=src.p;own=23+26*slot;opp=23+26*(1-slot)
    for off,col in ((0x23c,5),(0x244,7),(0x248,8),(0x120,16),(0x124,17),(0x134,18),(0x138,19)):
        p.write(src.a+off,int(start[own+col]),4)
    p.write(src.a+0xa30,int(start[9+10*slot]),4)
    p.write(src.b+0x144,abs(int(float(start[7])-float(start[17]))),4)
    p.write(src.o+0x38,int(start[own+2]),4)
    p.write(src.o+0x40,int(start[own]),4)
    p.write(src.o+0x1040,int(start[opp]),4)
    for key in inputs:snap=src.frame(key)
    assert (snap[0],snap[54])==((move<<16)|1,{26:231,36:238,38:227,78:625}[move])
    if move!=26:assert (snap[12],snap[13])==({36:0x16b9a8,38:0x16bf00,78:0x163610}[move],1)
    if move==36:
        assert p.read(0x46a910+4*slot,4)==3 and p.read(0x1239d84,4)==0 and snap[7]&4
    if move==38:assert snap[6]&0x80000000
    return src.instructions

def source_callbacks(slot,rows,state,acting,checks,spirit=3):
    """Apply each observed callback to the original actor objects at that visit."""
    src=setup_actor(slot)
    configure(src,spirit if acting else 0)
    p,a,o=src.p,src.a,src.o
    other=1-slot;ca=23+26*slot;cb=88+27*slot
    aid=(ASSETS/'aid_00.bin').read_bytes();act=(ASSETS/'act_00.bin').read_bytes()
    ctx=0x1981000
    for off,value in ((0,a),(4,src.other)):p.write(ctx+off,value,4)
    # 1400d8 is the match-stat accessor used by 14abb0 on capture release.
    # Production records both states; original pointers in this fixture are separate.
    for i in range(2):
        stats,_=p.run(0x1400d8,[i]);p.write(stats+0x2c,2,4)
    for old,now in zip(rows,rows[1:]):
        if int(old[4+10*slot])!=state or int(old[3+10*slot])!=(1 if acting else 2):continue
        if (int(old[ca+5])|int(now[ca+5]))&0x100:continue  # 168ab8's temporary contact callback owns this visit.
        oldfn=int(old[cb])
        if oldfn not in (0x16b9a8,0x16ba08,0x16bf00,0x16bfc0,0x16c028,0x172a18,0x172a90):continue
        # Validate the nonterminal and branching visits. ACT progression on
        # a completed attack can immediately replace the clock with a new ACT.
        if int(now[3+10*slot])!=int(old[3+10*slot]) or int(now[4+10*slot])!=state:continue
        oc=23+26*other
        for j in range(7):p.write(a+0x260+4*j,int(old[cb+j]),4)
        p.write(a+0xa3c,0xffffffff,4)
        p.write(a+0x120,int(now[ca+16]),4)
        p.write(o+0x40,int(now[ca]),4);p.write(o+0x38,int(old[ca+2]),4)
        p.write(src.other+0x23c,int(now[oc+5]),4)
        otherrow=now if other<slot else old
        p.write(src.other+0x194,(int(otherrow[4+10*other])<<16)|int(otherrow[3+10*other]),4)
        p.write(src.o+0x1040,int(now[oc]),4)
        flags=int(now[ca+3])
        expected=int(now[cb])
        if oldfn in (0x16b9a8,0x172a18):
            # 1699f8 clears the held bit before the post-visit snapshot. The
            # incoming bit is either retained or installed by the new ACT row.
            before=int(old[ca+3]);new_step=int(now[6+10*slot])
            record=struct.unpack_from('<h',aid,2*int(now[5+10*slot]))[0]+new_step
            if before&0x100 or (now[6+10*slot]!=old[6+10*slot] and struct.unpack_from('<h',act,60*record+52)[0]==0):
                flags|=0x100
        if oldfn==0x16bf00 and old[5+10*slot]!=now[5+10*slot]:
            # Changing action clears old collision-consumed flags at commit.
            flags|=int(old[ca+3])&0xc0000
        p.write(o+0x104,flags,4)
        p.write(o+0xc0,int(now[cb+13]),4)
        src.run(oldfn,ctx)
        got=p.read(a+0x260,4)
        assert got==expected,(slot,state,old[0],hex(oldfn),hex(expected),hex(got),old[:23],now[:23])
        checks[hex(oldfn)]=checks.get(hex(oldfn),0)+1
    return src.instructions

def verify(spec):
    slot,name=spec;target=1-slot
    pre,pads=scenario(slot,name)
    rows=play(slot,pre,pads,'--shin-fields')
    move=78 if name=='weapon' else 36
    col=23+26*slot
    starts=[(i,int(row[4+10*slot])) for i,row in enumerate(rows) if i and int(row[3+10*slot])==1
            and int(row[4+10*slot]) in (36,38,78) and row[4+10*slot]!=rows[i-1][4+10*slot]]
    if name=='bare':
        assert not starts and tuple(map(int,rows[1][3+10*slot:6+10*slot]))==(1,26,231)
        verified=original_entry(slot,26,rows[0],[ABC])
        return dict(player=slot+1,case=name,contacts=[],fallback='unarmed throw',source_actor_instructions=verified)
    expected_moves={'weapon':[78],'explosion-weapon':[36,78],'full':[36]}.get(name,[36,38])
    assert [n for _,n in starts]==expected_moves,(spec,starts)
    ins=0
    for i,n in starts:
        keys=([32,32|(128,64)[slot],768|(128,64)[slot]] if n==78 else [ABC])
        ins+=original_entry(slot,n,rows[i-len(keys)],keys)
    spirits=[0,0];spirits[slot]=3
    sounds=play(slot,pre,pads,'--sound-fields')
    contact,count=compare_contacts(slot,move,rows,spirits,{int(r[0]):r for r in sounds},(238,227,625))
    wanted={'full':[29],'hit':[29,31],'guard':[31],'miss':[],'air':[29,31],'lethal':[29,31],'bare-target':[29,31],'weapon':[39],'explosion-weapon':[29,39],'late':[31]}[name]
    assert [e['raw'] for e in contact]==wanted,(spec,contact)
    if name=='guard':
        assert contact[0]['defense'] and contact[0]['damage']==0
        assert any(int(r[5+slot*10])==228 for r in rows)
    if name in ('air','hit','lethal','bare-target','full'):
        assert contact[0]['requested']==(75 if name=='air' else 54)
        assert contact[0]['damage']==0
    if name in ('hit','air','lethal','bare-target','late'):
        assert contact[-1]['requested']==58 and not contact[-1]['defense']
        assert any(int(r[5+slot*10])==229 for r in rows)
    if name=='late':assert contact[-1]['frame']==1333 and contact[-1]['damage']==51
    if name=='lethal':assert any(int(r[9+10*target])==0 for r in rows)
    if name=='miss':assert int(rows[starts[1][0]+80][9+10*target])==200
    if name!='weapon':
        assert 2 in [int(r[col+16]) for r in rows] and int(rows[-1][col+16])==3
    flight=None
    if name in ('weapon','explosion-weapon'):
        assert int(rows[starts[-1][0]-1][col+16])==(2 if name=='explosion-weapon' else 1)
        flight=verify_weapon(slot,rows,3,0,contact[-1]['post_contact_library_seed'])
        assert any(any(o[0]==467 for o in objects(r)[target][1]) for r in rows)
    music=[]
    if name in ('hit','air','lethal','bare-target','late'):
        last=contact[-1]['frame']; music=[(int(r[0]),int(r[j])) for r in sounds if int(r[0])>=last for j in range(26,len(r),3) if int(r[j]) in (5,6,7)]
        recovered=next(int(r[0]) for r in rows if int(r[0])>last and int(r[4+10*target])==16)
        assert music[:3]==[(last,7),(last+1,5),(recovered,6)],(name,music[:6],last,recovered)
    if name=='late':assert music[:3]==[(1333,7),(1334,5),(1517,6)]
    callbacks={}
    if name in ('hit','miss','guard','air','bare-target'):
        for side,state,acting in ((slot,36,True),(slot,38,True),(target,58,False)):
            ins+=source_callbacks(side,rows,state,acting,callbacks)
    return dict(player=slot+1,case=name,moves=[(int(rows[i][0]),n) for i,n in starts],contacts=contact,
                source_actor_instructions=ins,source_contact_instructions=count,original_callback_visits=callbacks,
                weapon=flight,music=music[:3])

def escape(slot):
    front=(128,64)[slot]
    def pair(n,one=0,two=0):return (n,two,one) if slot else (n,one,two)
    pre=[pair(500),pair(75,front),pair(8)]
    pads=[pair(1,ABC if i==18 else 0,1024 if i==0 else 0) for i in range(21)]
    rows=play(slot,pre,pads,'--shin-fields')
    before,after=rows[18:20]
    assert tuple(map(int,before[3+slot*10:5+slot*10]))==(2,34)
    assert tuple(map(int,after[3+slot*10:6+slot*10]))==(1,36,238)
    src=setup_actor(slot);configure(src,3);p,a=src.p,src.a
    own=23+26*slot;other=23+26*(1-slot)
    p.write(a+0x194,(34<<16)|2,4);p.write(a+0x19a,int(before[own+10]),1)
    for off,col in ((0x23c,5),(0x244,7),(0x248,8),(0x120,16),(0x124,17)):
        p.write(a+off,int(before[own+col]),4)
    p.write(src.o+0x40,int(before[own]),4);p.write(src.o+0x1040,int(before[other]),4)
    wanted=src.frame(ABC)
    assert (wanted[0],wanted[54])==((36<<16)|1,238)
    return dict(player=slot+1,case='during heavy hitstun',from_state=34,source_hp=int(before[9+10*slot]),
                act=238,tick=int(after[0]),source_actor_instructions=src.instructions)

def unavailable_secret(slot,spirit=3):
    front=(128,64)[slot];back=front^192
    pre,_=scenario(slot,'weapon')
    keys=[front|32,back,back|32,32,front|32,front,back,32,back|32|1536]
    pads=[(1,0,key) if slot else (1,key,0) for key in keys]
    rows=play(slot,pre,pads,'--shin-fields',spirit)
    field=23+26*slot;other=23+26*(1-slot)
    assert int(rows[0][field+16])==1
    src=setup_actor(slot);configure(src,spirit);p,a=src.p,src.a
    # The preceding and following character slots remain registered. The
    # character's Shin secret alone is absent in this spirit's command table.
    commands=struct.unpack_from('<3h',p.memory,a+0x2c4+0x644+2*14)
    assert commands==(173,-1,177)
    for old,now,key in zip(rows,rows[1:],keys):
        for offset,j in ((0x120,16),(0x124,17),(0x134,18),(0x138,19)):
            p.write(a+offset,int(old[field+j]),4)
        p.write(src.o+0x40,int(old[field]),4);p.write(src.o+0x1040,int(old[other]),4)
        snap=src.frame(key)
        assert (snap[0],snap[54])==((int(now[4+slot*10])<<16)|int(now[3+slot*10]),int(now[5+slot*10]))
    assert snap[0]!=((79<<16)|1)
    return dict(player=slot+1,rage=1,state=snap[0]>>16,act=snap[54],bindings=commands)

if __name__=='__main__':
    assert digest(ELF)==PIN
    if len(sys.argv)==3:print(verify((int(sys.argv[1]),sys.argv[2])));sys.exit()
    cases=[(s,n) for s in range(2) for n in ('full','air','hit','guard','miss','lethal','bare','bare-target','weapon','explosion-weapon','late')]
    with ProcessPoolExecutor(max_workers=3) as pool:results=list(pool.map(verify,cases))
    report=dict(status='passed',original_sha256=PIN,native_sha256=digest(REPLAY),cases=results,
                hitstun_escape=[escape(s) for s in range(2)],unavailable_shin_secret=[unavailable_secret(s) for s in range(2)])
    REPORT.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(len(results),'real pad matches', sum(len(r['contacts']) for r in results),'original contacts')
