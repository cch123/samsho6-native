#!/usr/bin/env python3
"""Run the original two-body contact path on actual mounted and dismounting strikes."""
from hashlib import sha256
import itertools
import json
import subprocess
from validate_nakoruru_riding import ROOT,BUILD,ASSETS,PIN,prefix,keys,knock_off
from validate_nakoruru_combat import MixedContactOracle,ACTORS

class RiderContact(MixedContactOracle):
    def install_player(self,row,slot):
        super().install_player(row,slot)
        col=23+26*slot
        if int(row[col+5])&0x200000:
            # Match replay reports effective 0/19 or 1/2,1/10 rather than
            # the original compact alias. Recover the raw alias from its ACT.
            actor=ACTORS+slot*0xf2c
            action=int(row[5+slot*10])
            alias=0 if int(row[3+slot*10])==0 else (1|((action-588)<<16)) if action in (588,589,590) else 0xffffffff
            self.probe.write(actor+0x194,0xffffffff,4);self.probe.write(actor+0x1a4,alias,4)
            self.probe.write(actor+0x1aa,int(row[col+10]),1)

def strike(side,move,approach,jump,guard=False,start=None):
    f,b=((128,64),(64,128))[side]
    pair=lambda a,d:(d,a) if side else (a,d)
    lineup=(1-side,side)
    pre=prefix(lineup);pre[229]=[128,128];pre += [pair(f,b)]*24+[pair(0,0)]*30
    lines=['%d %d %d'%(sum(1 for _ in values),*k) for k,values in itertools.groupby(pre)]
    startup=start or (31 if move in ('slash0','slash1') else 33)
    pads=[32,32|b,b|2048]+[0]*(startup-3)+keys(side,move)+[0]*300
    for tick,k in enumerate(pads):
        held=16 if jump and tick==jump else b if tick<approach else f if guard and tick<150 else 0
        lines.append('1 %d %d'%pair(k,held))
    proc=subprocess.run([BUILD/'ss6-match-replay',ASSETS,'--mode','select','--contact-fields'],
                        input='\n'.join(lines)+'\n',capture_output=True,text=True,check=True)
    rows=[line.split() for line in proc.stdout.splitlines()[-len(pads):]]
    original=RiderContact(lineup).contacts(rows,side)
    act=[int(rows[i-1][5+10*side]) for i in range(1,len(rows)) if rows[i][10+10*side:12+10*side]!=rows[i-1][10+10*side:12+10*side]]
    assert act and len(act)==len(original),(side,move,act,original)
    assert any(c["defense"] for c in original)==guard,(side,move,guard,original)
    assert int(rows[-1][5+10*side])==0 and int(rows[-1][5+10*(side^1)])==0,(side,move,rows[-1][3:23])
    return dict(seat=side+1,move=move,guard=guard,source_actions=act,original_contacts=original,defender_life=int(rows[-1][9+10*(side^1)]))

def timeout_dismount(side):
    from validate_collisions import OBJECTS
    lineup=(1-side,side);pre=prefix(lineup);pre[229]=[128,128]
    lines=['%d %d %d'%(sum(1 for _ in g),*k) for k,g in itertools.groupby(pre)]
    b=(64,128)[side];keys=[32,32|b,b|2048]+[0]*550
    lines+=['5035 0 0']+['1 %d %d'%((0,k) if side else (k,0)) for k in keys]
    out=subprocess.run([BUILD/'ss6-match-replay',ASSETS,'--mode','select','--round-time','60','--contact-fields'],
                       input='\n'.join(lines)+'\n',capture_output=True,text=True,check=True)
    rows=[r.split() for r in out.stdout.splitlines()[-len(keys):]]
    tick=next(t for t,r in enumerate(rows) if int(r[1])==5)
    source=RiderContact(lineup);row=rows[tick][:23]+rows[tick][-52:];p=source.probe
    for i in (0,1):source.install_player(row,i)
    actor,obj=ACTORS+side*0xf2c,OBJECTS[side]
    assert int(row[5+side*10])==581 and p.read(actor+0x23c,4)&0x200000
    # The original actor is alive and airborne when the round times out.
    # 145240 stops motion and requests the neutral drop on this first visit.
    for off in range(0x4c,0x64,4):p.write(obj+off,12345,4)
    ready,count=p.run(0x145240,[actor,52])
    assert ready==0 and p.read(actor+0x190,4)==32<<16 and all(p.read(obj+off,4)==0 for off in range(0x4c,0x64,4))
    col=3+10*side;following=rows[tick+1]
    assert list(map(int,following[col:col+3]))==[0,32,596]
    assert any(int(r[col+1])==52 for r in rows[tick+1:]) and any(int(r[1])==1 for r in rows[tick+1:])
    return dict(seat=side+1,round_timer=60,match_tick=int(row[0]),origin=581,drop=596,original_instructions=count)

def main():
    cases=[]
    for side in (0,1):
        for move,approach,jump in (('slash0',3,32),('slash1',3,32),('slash2',20,0),
                                  ('80',0,21),('81',0,26),('82',0,0),('83',0,26),('84',0,0),('85',0,0)):
            cases.append(strike(side,move,approach,jump))
        for move,approach,jump,start in (('slash2',24,0,33),('82',24,0,33),('83',10,0,48),
                                         ('84',24,21,33),('85',10,21,33)):
            cases.append(strike(side,move,approach,jump,guard=True,start=start))
    report=dict(status='passed',elf_sha256=PIN,replay_sha256=sha256((BUILD/'ss6-match-replay').read_bytes()).hexdigest(),
                contacts=cases,timeout_dismount=[timeout_dismount(s) for s in (0,1)],hit_by_jump_heavy=[knock_off(s) for s in (0,1)])
    (ROOT/'outputs/ss6-feasibility/nakoruru_riding_contacts.json').write_text(json.dumps(report,indent=2)+'\n')
    print(len(cases),'offensive matches, two knock-offs')
if __name__=='__main__':main()
