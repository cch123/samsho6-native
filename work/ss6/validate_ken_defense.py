#!/usr/bin/env python3
"""Compare Ken's directional slips and complete guard on both sides with the Japanese EE program."""
from concurrent.futures import ProcessPoolExecutor
import json
import os
import struct
from pathlib import Path

from validate_collisions import ACTORS
from validate_dash_motion import ELF, PIN, ROOT, digest
from validate_haohmaru_special import ContactOracle
from validate_shin_evasion import EXE, replay, setup_state
from validate_weapon_handling import setup
from validate_input_lifecycle import Boundary

OUT=ROOT/'outputs/ss6-feasibility/ken_defense_validation.json'
MOVES={1:(56,92),2:(56,92),3:(56,92),4:(60,100),5:(58,84),
       6:(60,100),7:(58,84),8:(58,84),9:(58,84)}

def menu():
    b=ELF.read_bytes()
    def word(address):
        start=address-0xff000
        return b[start:b.index(0,start)].decode('cp932')
    rows=[list(map(word,struct.unpack_from('<3I',b,j))) for j in range(0x3cbf90,0x3cbfe0,20)]
    assert [r[2] for r in rows]==['IE','I2PLIE','I4PLIE','IAIB同時押し']
    assert [r[0] for r in rows]==['ミキリスライド（見切り）','ミキリスライド（伏せ）','ミキリスライド（下段避け）','完全ガード']
    return rows

def paired(side,n,own=0,other=0):
    return (n,other,own) if side else (n,own,other)

def prelude(side,bare,charge):
    front=(128,64)[side];back=front^192
    initial=[paired(side,500)]
    if charge:
        # The armed opening heavy earns 41 points; wait for both actors'
        # return to neutral before spending the 40-point guard cost.
        initial += [paired(side,42,front,back),paired(side,8),paired(side,1,1024),paired(side,120)]
    if bare:initial += [paired(side,1,front|8),paired(side,135)]
    return initial

def actor_case(job):
    side,move,bare=job
    direction=isinstance(move,int)
    front=(128,64)[side];back=front^192
    raw={1:back|32,2:32,3:front|32,4:back,5:0,6:front,7:back|16,8:16,9:front|16}
    mask=(raw[move]|4096) if direction else 768
    charged=move=='perfect-guard'
    initial=prelude(side,bare,charged)
    initial += [paired(side,14,back,front),paired(side,8)]
    controls=[mask]+[0]*75
    rows=replay(side,'ken',initial+[paired(side,1,h) for h in controls])[len(initial)-1:]
    base,c,cb=3+10*side,23+26*side,88+27*side
    src,registry=setup(side)
    setup_state(src,5,0,rows[0],side,bare)
    p,a=src.p,src.a
    p.write(a+0x120,int(rows[0][c+16]),4);p.write(a+0x124,int(rows[0][c+17]),4)
    assert bool(p.read(a+0x124,4)>=40*256)==charged
    changes=[];shadow=None
    for t,(h,row) in enumerate(zip(controls,rows[1:]),1):
        v=src.frame(h)
        got=[int(row[base])|(int(row[base+1])<<16),*map(int,row[base+2:base+4]),
             int(row[cb+11]),*map(int,row[cb:cb+3]),int(row[c+10]),
             int(row[c+5])&0x1018,int(row[c]),int(row[c+1]),int(row[c+17])]
        want=[v[0],v[54],v[55],v[56],*v[12:15],v[4],v[5]&0x1018,v[68],v[69],p.read(a+0x124,4)]
        assert got==want,(job,t,[(i,x,y) for i,(x,y) in enumerate(zip(got,want)) if x!=y])
        if t==1 and direction:
            for task in struct.unpack_from('<48I',p.memory,registry):
                if not task:continue
                obj=p.read(task+28,4)
                if p.read(obj+0xcc,4)==9:
                    assert p.read(obj+0x118,4)==a
                    shadow=p.read(obj+0xc4,4)  # 16c408 queues the ACT for the registry commit.
            assert shadow==MOVES[move][1]+bare+2,(job,shadow)
        state=(v[0]&0xffff,v[0]>>16,v[54],v[12])
        if not changes or changes[-1][1:]!=list(state):changes.append([t,*state])
        if t>=2 and v[0]==0 and v[54]==int(bare):break
    assert changes[-1][1:4]==[0,0,int(bare)],(job,changes)
    if direction:assert changes[0][1:4]==[0,MOVES[move][0],MOVES[move][1]+bare]
    elif charged:assert [c[3] for c in changes]==[314+bare,314+bare,318+bare,318+bare,int(bare)],(job,changes)
    else:assert changes[0][1]==1,(job,changes)
    return dict(side=side+1,armed=not bare,command=move,original_shadow_actor=shadow,
                visits=t,timeline=changes,original_instructions=src.instructions)

class KenContacts(ContactOracle):
    def __init__(self,side):
        super().__init__();self.side=side
    def install_player(self,row,slot):
        super().install_player(row,slot)
        self.probe.write(ACTORS+slot*0xf2c+0x10c,5 if slot==self.side else 0,4)

def guard_case(job):
    side,bare,attack,delay=job
    front=(128,64)[side];back=front^192
    initial=prelude(side,bare,True)+[paired(side,60,0,back),paired(side,8)]
    seq=[paired(side,1,768 if i==delay else 0,attack if i==0 else 0) for i in range(90)]
    rows=replay(side,'ken',initial+seq)[len(initial)-1:]
    original=KenContacts(side)
    contacts=original.contacts(rows,1-side)
    base=3+10*side
    success=[x for x in contacts if x['defense']==3]
    assert success and all(x['target_state']==53 and x['damage']==0 for x in success),(job,contacts)
    t=success[0]['frame']-int(rows[0][0])
    assert list(map(int,rows[t][base:base+2]))==[0,53]
    assert any(int(r[base+2])==316+bare for r in rows[t:])
    assert rows[-1][base:base+3]==['0','0',str(int(bare))],(job,rows[-1][:23])
    # Match the original's order. It moves bodies first, then clamps both
    # using the previous history sample and distributes half the correction
    # to the grounded opponent before either fighter executes its callback.
    src,_=setup(side);setup_state(src,5,0,rows[0],side,bare)
    p,a,o=src.p,src.a,src.o;c,cb=23+26*side,88+27*side
    for off,col in ((0x120,c+16),(0x124,c+17),(0x134,c+18),(0x138,c+19)):
        p.write(a+off,int(rows[0][col]),4)
    for off,col in ((0x28,base+3),(0x2c,cb+11)):p.write(o+off,int(rows[0][col]),4)
    p.write(a+0xa6c,p.read(o+0x40,4),4)
    p.write(src.b+0x44,0,4);p.write(src.b+0x48,640,4)
    run=src.run
    def with_stage(pc,*args,**kw):
        run(pc,*args,**kw)
        if pc==0x11d6c8:
            boundary=Boundary(0x1427f0)
            run(0x1426d8,src.b,stops=boundary)
            assert boundary.stopped==0x1427f0
    src.run=with_stage
    stop=None
    for i,(cmd,row) in enumerate(zip(seq,rows[1:]),1):
        if i==t:
            src.run(0x14d5a0,a,o+0x1000,3,0)
            stop=[p.read(a+off,4) for off in (0x1b0,0x1b4)]
        v=src.frame(cmd[1+side])
        got=[*map(int,row[base:base+4]),*map(int,row[cb:cb+3]),*map(int,row[cb+8:cb+10]),
             int(row[cb+11]),int(row[c+17])]
        want=[v[0]&0xffff,v[0]>>16,v[54],v[55],*v[12:15],v[19],v[20],v[56],p.read(a+0x124,4)]
        if attack!=256 and i<t:
            # The enemy's advancing heavy changes its push box before the
            # guard. Seed this actor-only oracle from the last published
            # separation; guarding and its recoil then run independently.
            p.write(o+0x40,int(row[c]),4);p.write(a+0xa6c,int(row[c]),4)
            p.write(o+0x1040,int(row[23+26*(1-side)]),4)
        else:
            got.append(int(row[c]));want.append(v[68])
        if attack==256:
            got.append(int(row[23+26*(1-side)]));want.append(p.read(o+0x1040,4))
        assert got==want,(job,i,[(j,l,r) for j,(l,r) in enumerate(zip(got,want)) if l!=r])
        if i>t and v[0]==0 and v[54]==int(bare):break
    assert stop==[1024,512]
    return dict(side=side+1,armed=not bare,attack=attack,guard_delay=delay,contacts=contacts,
                ee_stop=stop,ee_actor_and_stage_visits=i,ee_instructions=src.instructions,
                entered_guard=next(int(r[0]) for r in rows if int(r[base+1])==47),
                first_recovery=next(int(r[0]) for r in rows[t:] if r[base:base+3]==['0','0',str(int(bare))]))

def thresholds():
    cases=[]
    for amount in (0,40*256-1,40*256,40*256+1,184*256):
        s,_=setup(0);p,a=s.p,s.a
        p.write(a+0x10c,5,4);s.run(0x179258,a+0x2c4,a+0x10c)
        p.write(a+0x124,amount,4)
        if amount==184*256:p.write(a+0x120,1,4)
        row=s.frame(768)
        reaches=row[0]==47<<16
        assert reaches==(amount>=40*256)
        assert p.read(a+0x124,4)==amount-(40*256 if reaches else 0)
        assert p.read(a+0x120,4)==0
        cases.append(dict(before=amount,after=p.read(a+0x124,4),state=row[0],action=row[54]))
    return cases

def projectile(side):
    from validate_haohmaru_special import pads_for
    from validate_haohmaru_whirlwind import contact
    spell=pads_for(64,1-side)
    initial=prelude(side,False,True)+[paired(side,30)]
    seq=[paired(side,1,768 if i==40 else 0,spell[i] if i<len(spell) else 0) for i in range(90)]
    rows=replay(side,'ken',initial+seq)
    j=next(j for j,r in enumerate(rows) if r[4+10*side]=='53')
    source=KenContacts(side)
    verdict=contact(source,rows[j-1],rows[j],1-side,True)
    assert verdict['defense']==3 and verdict['damage']==0 and verdict['raw']==36
    original_stop=source.probe.read(0x1e03000+0xdc,4)
    owner_cb=88+27*(1-side)
    # The hit freezes the projectile, not its distant caster. Its first
    # priority-actor visit consumes one tick of its independently set pause.
    for dt,row in enumerate(rows[j:j+5]):
        assert int(row[131+0xdc//4])==max(original_stop-256*(dt+1),0)
        assert list(map(int,row[owner_cb+8:owner_cb+10]))==[0,0]
    assert original_stop==1280 and rows[-1][3+side*10:6+side*10]==['0','0','0']
    return dict(side=side+1,original_projectile_pause=original_stop,**verdict)

def grabbed(side):
    from validate_collisions import OBJECTS, QUEUE
    front=(128,64)[side]
    pre=prelude(side,False,True)+[paired(side,60,0,front^192),paired(side,8)]
    seq=[paired(side,1,768 if i==2 else 0,1536 if i==0 else 0) for i in range(235)]
    rows=replay(side,'ken',pre+seq)
    b=3+10*side
    j=next(i for i,r in enumerate(rows) if r[b:b+2]==['2','13'])
    prev,now=rows[j-1:j+1];assert prev[b:b+2]==['0','47']
    oracle=KenContacts(side);p=oracle.probe
    for i in range(2):oracle.install_player(prev,i)
    p.write(0x12d2698,0,4)
    for pair in (OBJECTS,OBJECTS[::-1]):p.run(0x1536e8,pair)
    p.run(0x1544a0)
    e=next(e for i in range(p.read(0x12d2698,4)) if p.read(e:=QUEUE+108*i,4)==4)
    assert p.read(e+0x68,4)==OBJECTS[side]
    p.run(0x1551c0,[e,0])
    assert tuple(p.read(ACTORS+i*0xf2c+0x190,4) for i in (side,1-side))==(13<<16|2,31<<16|1)
    assert int(rows[-1][b+6])==186 and rows[-1][b:b+3]==['0','0','0']
    return dict(side=side+1,frame=int(now[0]),original_route=4,final_life=186)

def repeated_guard(side,state,delay):
    from validate_haohmaru_special import pads_for
    attack=pads_for(state,1-side)
    front=(128,64)[side]
    pre=prelude(side,False,True)+[paired(side,60,0,front^192),paired(side,8)]
    seq=[paired(side,1,768 if i==delay else (32 if i>delay else 0),attack[i] if i<len(attack) else 0) for i in range(240)]
    rows=replay(side,'ken',pre+seq)[len(pre)-1:]
    verdicts=KenContacts(side).contacts(rows,1-side)
    assert [c['defense'] for c in verdicts]==({70:[3,0],73:[3]*5,74:[3]*3}[state])
    assert all(c['target_state']==53 and not c['damage'] for c in verdicts if c['defense']==3)
    if state!=70:
        # The original state-53 callback samples DOWN at exit, even when it
        # has been refreshed multiple times by successive guards.
        last=verdicts[-1]['frame']-int(rows[0][0]);base=3+10*side
        crouch=next(r for r in rows[last:] if int(r[base+2])==4)
        assert crouch[base:base+2]==['0','1']
    return dict(side=side+1,attack_state=state,contact_verdicts=verdicts)

def slides_in_combat(side):
    import subprocess
    from validate_dash_motion import ASSETS
    checks=[]
    for move,attack,delay,expected in ((5,1024,12,17920),(4,1024,4,17920),(2,256,0,9984),
                                       (5,1024,0,8192)):
        front=(128,64)[side]
        mask={5:4096,4:4096|(front^192),2:4096|32}[move]
        seq=[(500,0,0),(42,128,64),(8,0,0)]+[paired(side,1,mask if i==delay else 0,attack if i==0 else 0) for i in range(95)]
        command=''.join('%d %d %d\n'%s for s in seq)
        trace=subprocess.run([EXE,ASSETS,'--mode','versus',f'--p{side+1}-spirit','ken','--ken-fields'],
                             input=command,text=True,capture_output=True,check=True)
        rows=[v.split() for v in trace.stdout.splitlines()]
        k,life=26+8*side,9+10*side
        assert rows[2][k]=='8192' and int(rows[-1][k])==expected
        assert rows[-1][3+side*10:6+side*10]==['0','0','0']
        matched=expected!=8192
        assert (int(rows[-1][life])==200)==matched
        change=next(int(v[0]) for q,v in zip(rows[2:],rows[3:]) if v[k]!=q[k] or v[life]!=q[life])
        checks.append(dict(side=side+1,command=move,opponent=attack,delay=delay,contact=change,
                           decoy_struck=matched,life=int(rows[-1][life]),secret=expected))
    return checks

def keyboard_checks(viewer=None,assets=None):
    from validate_versus_heavy import HERE, PKG, run
    from validate_zan_window import verify_keys
    import shlex
    import shutil
    import tempfile
    records=[]
    assets=assets or PKG/'assets'
    with tempfile.TemporaryDirectory(prefix='ss6-ken-def-') as tmp:
        folder=Path(tmp)
        shutil.copy2(viewer or PKG/'ss6-viewer',folder/'viewer')
        flags=shlex.split(run(['pkg-config','--cflags','--libs','sdl3'],text=True).stdout)
        run([*shlex.split(os.environ.get('CXX','c++')),'-std=c++20','-O2','-I',ROOT/'src',
             HERE/'sdl_slash_input_test.cpp',EXE.parent/'libss6-runtime.a',*flags,'-o',folder/'keys'])
        for side in (0,1):
            front=(128,64)[side]
            for move,mask in ((5,4096),(2,4128),(4,4096|(front^192))):
                seq=[(500,0,0),paired(side,1,mask),paired(side,3)]
                observed=verify_keys(folder,side,seq,504,'ken',assets)[side]
                assert tuple(observed[1:3])==MOVES[move]
                records.append(dict(side=side+1,command=move,tick=504,body=observed,bitmap=digest(folder/'snapshot.bmp')))
            pre=prelude(side,False,True)+[paired(side,60,0,front^192),paired(side,8)]
            seq=pre+[paired(side,1,768,256),paired(side,10)]
            for update,expected in ((1,(47,314)),(6,(53,316))):
                tick=sum(n for n,_,_ in pre)+update
                observed=verify_keys(folder,side,seq,tick,'ken',assets)[side]
                assert tuple(observed[1:3])==expected
                records.append(dict(side=side+1,command='A+B',tick=tick,body=observed,bitmap=digest(folder/'snapshot.bmp')))
        return records,digest(folder/'viewer')


def main():
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument("--keyboard",action="store_true",help="also verify the current packaged SDL viewer")
    args=parser.parse_args()
    assert digest(ELF)==PIN
    rows=menu()
    jobs=[(s,d,b) for s in (0,1) for b in (False,True) for d in [*MOVES,'perfect-guard','under-cost']]
    g=[(s,b,attack,delay) for s in (0,1) for b in (False,True) for attack,delay in ((256,0),(1056,13))]
    with ProcessPoolExecutor(max_workers=min(5,os.cpu_count() or 1)) as pool:
        actors=list(pool.map(actor_case,jobs))
        guards=list(pool.map(guard_case,g))
    report=dict(throw_during_guard=[grabbed(s) for s in (0,1)],elf_sha256=PIN,replay_sha256=digest(EXE),validator_sha256=digest(Path(__file__)),
                menu=rows,actors=actors,combat_perfect_guards=guards,original_cost_boundaries=thresholds(),
                projectiles=[projectile(s) for s in (0,1)],
                multi_hit_guards=[repeated_guard(s,state,d) for s in (0,1) for state,d in ((70,4),(73,24),(74,18))],
                slides_under_attack=sum((slides_in_combat(s) for s in (0,1)),[]))
    if args.keyboard:
        report['keyboard'],report['viewer_sha256']=keyboard_checks()
    OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(len(actors),'actor and',len(guards),'combat cases match Japanese original')

if __name__=='__main__':main()
