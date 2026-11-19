#!/usr/bin/env python3
"""Play two full VS rounds from the character grid and compare both lethal hits to the Japanese game."""
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
import hashlib
import json
import subprocess
from validate_nakoruru_combat import MixedContactOracle, BUILD, RES, ROOT, ELF
from validate_selected_combat import prefix
from validate_finishing_blow import actor, stats, put, initialize_effects, OBJECTS, QUEUE, signed
from validate_console_versus_menu import Oracle, G, physical, REMATCH

EXE=BUILD/'ss6-match-replay'

def replay(pads,mode):
    data=''.join(f'1 {a} {b}\n' for a,b in pads)
    run=subprocess.run([EXE,RES,'--mode','select',mode],input=data,text=True,capture_output=True)
    if run.returncode:raise RuntimeError((mode,len(run.stdout.splitlines()),run.stderr.strip()))
    return [line.split() for line in run.stdout.splitlines()]

def combat_pads(lineup,side,move):
    opening=prefix(lineup);opening[229]=[128,128] # Both seats choose rage.
    if move=='draw':return opening+[(0,0)]*13500
    fwd,back=((128,64),(64,128))[side]
    command={'stand':[1024],'421':[back,32,back|32|1024], 'crouch':[32,32|1024]}[move]
    keys=[(0,k) if side else (k,0) for k in command]
    burst=[(128,64)]*44+[(0,0)]*6+keys+[(0,0)]*111
    return opening+burst*55

def check_hit(previous,now,side,lineup,system=0):
    o=MixedContactOracle(lineup);p=o.probe
    initialize_effects(p)
    for pc in (0x1123a8,0x112570,0x11e290):p.run(pc,limit=500000)
    for i,name in enumerate(('01HitFlash.bin','02Guard.bin','03etc.bin')):
        at=0x4a4810+i*0x3da0;p.memory[at:at+0x3da0]=(RES/name).read_bytes()
    for i in range(32):p.write(0x4c3510+i*4,i+1,4)
    stdout=p.read(p.read(0x5d1bf8,4)+8,4);put(p,stdout,[(0,0x19e0000),(16,0x19e0000)])
    for seat in (0,1):
        o.install_player(previous,seat);p.write(actor(seat)+0x10c,system,4)
        put(p,stats(seat),list(zip((12,24,28,32),map(int,previous[75+4*seat:79+4*seat]))))
    p.write(0x12d2698,0,4)
    for pair in (OBJECTS,OBJECTS[::-1]):p.run(0x1536e8,pair,limit=50000)
    p.run(0x1544a0,limit=50000)
    events=[QUEUE+n*108 for n in range(p.read(0x12d2698,4))]
    ev=next(e for e in events if p.read(e,4)==7 and p.read(e+0x40,4)==OBJECTS[side]);defense,_=p.run(0x155850,[ev]);assert defense==0
    category=p.run(0x14dac8,[actor(side)])[0];visits=Counter()
    def observe(pc):
        if pc in (0x1575d0,0x1576e8,0x14dac8):visits[pc]+=1
    p.run(0x155a88,[ev,1,0],limit=500000,observe=observe)
    assert visits[0x1575d0]==visits[0x1576e8]==1 and visits[0x14dac8]>=1,visits
    a=actor(side);s=stats(side);target=actor(side^1)
    assert p.read(target+0xa38,4)>=p.read(target+0xa30,4)>0
    blocks=23+26*side;score=75+4*side
    got=list(map(int,(now[blocks+7],now[blocks+8],now[score+2],now[score+3])))
    want=[p.read(a+0x244,4),p.read(a+0x248,4),p.read(s+0x1c,4),p.read(s+0x20,4)]
    for x,y,mask in zip(got,want,(0x18000000,0xfe0000,0xffffffff,0xffffffff)):assert x&mask==y&mask,(got,want)
    return dict(frame=int(now[0]),prior_hp=p.read(target+0xa30,4),damage=p.read(target+0xa38,4),category=category,
                prior_state=int(previous[4+10*side]),prior_action=int(previous[5+10*side]),outcome=got[2:],raw=p.read(ev+32,4))

def case(spec):
    side,move,lineup=spec;pads=combat_pads(lineup,side,move)
    menu=replay(pads,'--vs-menu-fields');idx=next(j for j,r in enumerate(menu) if r[24]=='1');row=menu[idx];del menu
    winner=-1 if move=='draw' else side
    rounds=[int(row[i]) for i in (12,22)];assert rounds==([2,2] if winner<0 else [2*int(i==winner) for i in (0,1)]),(spec,rounds)
    # Each entered character is the real seat resource in 124da0's session statistics.
    original=Oracle();original.enter(winner,lineup,True)
    stats_jp=[original.p.read(G-16+n*4,4) for n in range(4)]+[signed(original.p.read(G+12,4),32),
             original.p.read(G+0x38,4),original.p.read(G+16,4)]
    assert list(map(int,row[33:40]))==stats_jp
    pads=pads[:idx+1];hits=[]
    if winner>=0:
        trace=replay(pads,'--finish-fields');victim=9+10*(side^1)
        for j in range(1250,len(trace)):
            if trace[j][victim]=='0' and int(trace[j-1][victim])>0:hits.append(check_hit(trace[j-1],trace[j],side,lineup))
        assert len(hits)==2,(spec,hits)
    else:assert row[9]==row[19]=='200' and row[10]==row[20]=='0'
    # Choose the second menu row (CONTINUE); both controllers are accepted.
    rematch=[(0,0)]*45+[(0,32) if side else (32,0),(0,0),(0,1024) if side else (1024,0)]+[(0,0)]*500
    for keys in rematch:
        original.sample(tuple(map(physical,keys)));original.tick()
        if original.destination:break
    assert original.destination==REMATCH
    after=replay(pads+rematch,'--select-fields')[-1]
    assert after[23:25]==['2','0'] and tuple(map(int,(after[25],after[35])))==tuple(lineup)
    assert [after[i] for i in (12,22)]==['0','0'] and [after[i] for i in (9,19)]==['200','200']
    assert [int(after[i]) for i in (54,55)]==stats_jp[::2][:2],(spec,after[50:],stats_jp)
    return dict(lineup=lineup,attacker=side,route=move,rounds=rounds,menu_at_pad=idx+1,original_session=stats_jp,hits=hits,rematch_number=int(after[23]),rematch_hp=[200,200])

def special_finish(spec):
    side,route=spec;lineup=((1,0),(0,1))[side];front,back=((128,64),(64,128))[side]
    keys=lambda values:[(0,k) if side else (k,0) for k in values]
    victim=9+10*(side^1);state=4+10*side
    pre=combat_pads(lineup,side,'stand')[:3400]
    pre[212]=pre[229]=[128,128] # Two steps from Ken to Shin, before confirmation.
    trace=replay(pre,'--finish-fields');i=next(j for j,r in enumerate(trace) if j>1300 and 12<=int(r[victim])<=32)
    approach=[(0,0)]*95+[(128,64)]*44+[(0,0)]*10
    pre=pre[:i+1]+approach
    if route=='secret':
        # The character override selects command 246 on Shin: 3214623+B+C.
        pre+=keys([32|front,32,32|back,back,front,32,32|front|1536]);move=91
    else:
        # One light turn lowers life enough for the follow-up to be lethal.
        spin=keys([back,32,back|32|256]);pre+=spin+approach+spin;move=70
        windup=replay(pre+[(0,0)]*80,'--finish-fields')
        cancel=next(j for j in range(len(pre),len(windup)) if windup[j][state]=='71' and int(windup[j][27+26*side])&0x40)
        pre+=[(0,0)]*(cancel+1-len(pre))+keys([512])
    trace=replay(pre+[(0,0)]*350,'--finish-fields')
    j=next(j for j in range(len(pre),len(trace)) if trace[j][victim]=='0' and int(trace[j-1][victim])>0)
    hit=check_hit(trace[j-1],trace[j],side,lineup,1)
    assert hit['prior_state']==move and hit['category']==(13 if move==91 else 10) and hit['outcome']==([0,0] if move==91 else [5,0]),hit
    return dict(lineup=lineup,seat=side,route=route,**hit)

def main():
    specs=[(side,move,((1,0),(0,1))[side]) for side in (0,1) for move in ('stand','421','draw')]
    specs += [(0,'crouch',(1,1)),(1,'crouch',(1,1))]
    with ProcessPoolExecutor(3) as pool:
        results=list(pool.map(case,specs))
        extra=list(pool.map(special_finish,[(side,route) for side in (0,1) for route in ('follow','secret')]))
    report=dict(status='passed',elf_sha256=hashlib.sha256(ELF.read_bytes()).hexdigest(),replay_sha256=hashlib.sha256(EXE.read_bytes()).hexdigest(),matches=results,additional_KOs=extra,
        scope='Both human pads enter from the Japanese factory character grid, select stage 0, fight from full life, resolve best-of-three or natural clock draws, and choose CONTINUE. Each lethal body strike is re-executed from previous native geometry through Japanese 1536e8/1544a0/155850/155a88/1576e8/14dac8; 124da0/1daec0 and the menu decision check the selected entrants and carried session results.')
    (ROOT/'outputs/ss6-feasibility/nakoruru_round_finish_validation.json').write_text(json.dumps(report,indent=2)+'\n');print(f'{len(results)} full matches, {sum(len(r["hits"]) for r in results)+len(extra)} original lethal contacts')
if __name__=='__main__':main()
