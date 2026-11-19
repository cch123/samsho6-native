#!/usr/bin/env python3
"""Interrupt Ken secret recharge with a real KO and check both next-round resets."""
import hashlib
import json
import subprocess

from validate_shin_meters import ROOT,ASSETS,PLAYER,Probe,SOURCE_HASH


def secret(side):
    direction=(128,64)[side]
    def pad(t,own=0,other=0):
        return (t,other,own) if side else (t,own,other)
    heavy=[pad(65,0,direction^192),pad(5),pad(1,0,1024),pad(100)]
    return [pad(500)]+heavy*5+[pad(75,direction),pad(5),pad(1,32),pad(1,32|direction),pad(1,direction|1536)]


def full_guard(side):
    direction=(128,64)[side]
    def pad(n,own=0,other=0):return (n,other,own) if side else (n,own,other)
    # The sixth heavy is blocked at 183, starting full rage without ending
    # the round. Hold neutral before performing A+B to spend 40 from full.
    attack=[pad(65,direction),pad(5),pad(1,1024),pad(100)]
    return ([pad(500)]+attack*5+[pad(65,direction),pad(5),pad(1,1024,direction),
                                      pad(70,0,direction),pad(70),pad(1,768),pad(95)])


def main():
    raw=(ASSETS.parent/'SLPS_255.59').read_bytes();assert hashlib.sha256(raw).hexdigest()==SOURCE_HASH
    p=Probe(raw,finite_model=True);p.run(0x1113e8,[0x43d058]);results=[]
    exe=ROOT/'work/ss6/build-native/ss6-match-replay'
    for side in (0,1):
        other=(64,128)[side]
        def pad(t,x=0,y=0):return (t,y,x) if side else (t,x,y)
        seq=secret(side)+[pad(220),pad(90,0,other),pad(3),pad(1,0,1024),pad(620)]
        input=''.join(('1 %d %d\n'%(a,b))*n for n,a,b in seq)
        out=subprocess.run([exe,ASSETS,'--mode','versus',f'--p{side+1}-spirit','ken','--ken-fields'],input=input,text=True,capture_output=True,check=True)
        rows=[l.split() for l in out.stdout.splitlines()];base=23+8*side
        hp=[int(r[base+7]) for r in rows];dead=hp.index(0)
        reset=hp.index(200,dead)
        assert rows[dead][base:base+4]==['1','45','256','0']
        a=PLAYER+side*0xf2c
        for off,v in ((0x10c,5),(0x110,side),(0xa24,side),(0x138,24320),(0xa30,0)):p.write(a+off,v,4)
        fields=(0x14c,0x150,0x154,0x158,0x120,0x124,0x134)
        old=list(map(int,rows[reset-1][base:base+7]));assert old[0]==1 and old[3]<8192,old
        for off,v in zip(fields,old):p.write(a+off,v,4)
        p.run(0x14ec80,[a+0x10c])
        want=[p.read(a+off,4) for off in fields];got=list(map(int,rows[reset][base:base+7]))
        assert want==got and got[:4]==[0,0,256,8192] and got[5]==old[5]>0,(side,want,got)
        # A blocked sixth heavy fills the last point. Full rage persists
        # past 100 neutral ticks, then A+B must take exactly 40 from it.
        seq=full_guard(side);guard_input=''.join(('1 %d %d\n'%(x,y))*n for n,x,y in seq)
        guard_out=subprocess.run([exe,ASSETS,'--mode','versus',f'--p{side+1}-spirit','ken','--ken-fields'],
                                 input=guard_input,text=True,capture_output=True,check=True)
        guard_rows=[line.split() for line in guard_out.stdout.splitlines()]
        states=[int(row[base+4]) for row in guard_rows]
        start=states.index(1);paid=states.index(0,start)
        assert paid-start>100 and all(int(row[base+5])==184*256 for row in guard_rows[start:paid])
        assert int(guard_rows[start-1][base+5])==183*256 and int(guard_rows[paid][base+5])==144*256
        other_hp=23+8*(1-side)+7
        assert all(int(row[other_hp])==22 for row in guard_rows[start-1:paid+1])
        results.append(dict(seat=side+1,ko_update=dead+1,reset_update=reset+1,before=old,after=got,
                            blocked_heavy_full_update=start+1,full_updates=paid-start,full_guard_paid_update=paid+1,
                            defender_hp_during_full=22,lower_after_full_guard=144))
    report=dict(status='passed',source_sha256=SOURCE_HASH,cases=results,
                scope='Factory first round, real 236+B+C at low HP, offensive rage retained, genuine second-player standing heavy KO during secret recharge, Japanese 14ec80 reset, full rage achieved through a blocked heavy, persistent full gauge and A+B spending 40, both actor orders.')
    (ROOT/'outputs/ss6-feasibility/ken-round-validation.json').write_text(json.dumps(report,indent=2)+'\n');print(report)

if __name__=='__main__':main()
