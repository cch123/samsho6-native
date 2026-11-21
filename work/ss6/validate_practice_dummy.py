#!/usr/bin/env python3
"""Practice dummy controller: whole 15aa18 for every behaviour code and whole
158990 for the posture codes (15aa18, 15ab30 with 1588c0 and the guard routine
161658, the CPU UKEMI TYPE recovery 1594c8 with 15ace8, and the tail 158fa0),
both seats, compared with src/practice_dummy.cpp.

Nothing is stubbed or patched. 139c88/139ce8 read the committed settings arrays
13738d0/1373930 seeded here; 151478 (already ported as ActionSelection::
opponentThreat) is evaluated by the original on the same fixture and handed to
the native side as an input."""
import argparse
import collections
import json
import random
import struct
import subprocess
import tempfile
from pathlib import Path
from cpu_fight_oracle import cpu_actor
from mips_probe import signed
from validate_dash_motion import ASSETS,ELF,PIN,ROOT,digest

DRIVER=r'''
#include "practice_dummy.hpp"
#include "cpu_execution.hpp"
#include <iostream>
using namespace ss6;
int main(int argc,char** argv){
 unsigned kind,charid;
 while(std::cin>>kind>>charid){
  StateEntryActor a,b;GameRandom rng;PracticeDummyFrame f;int level;unsigned flags,alias;
  a.character=charid;
  std::cin>>f.system>>level>>rng.mode>>rng.gameSeed>>rng.librarySeed>>f.code>>f.ukemi>>f.threat>>f.opponentKind2
          >>a.flags23c>>a.flags240>>a.state194>>a.state1a4>>a.conditions15c[1]>>a.timers[28]>>a.controlModeC8>>a.cpuPrevious174
          >>a.cpuTimerDelta08>>b.character>>b.flags23c>>b.state194>>b.state1a4>>b.stateCharacter198>>b.aliasCharacter1a8;
  auto control=[&](auto visit){for(auto& t:a.controlTimers0c)visit(t);visit(a.controlTimer34);
   visit(a.control88);visit(a.control8c);visit(a.controlFlagsB4);visit(a.flagsB8);visit(a.controlFlagsBC);
   visit(a.controlD8);visit(a.controlE4);visit(a.controlE8);visit(a.controlC4);visit(a.controlCC);
   for(auto& n:a.controlMotion38)visit(n);};
  control([](auto& n){std::cin>>n;});
  CpuTactics tactics(argv[1],charid);
  int ret;
  if(kind==0)ret=practiceRefreshBehaviour(a,f.code,level,rng);
  else {
   // 158990 head: timer 9 counts up, a running timer 1 ends the visit.
   cpuTimerUp(a,9);
   if(cpuTimerDown(a,1))ret=2;
   else ret=practiceDummyVisit(a,b,f,level,tactics,rng);
  }
  std::cout<<ret<<' '<<level<<' '<<a.flags240<<' '<<a.controlModeC8<<' '<<rng.gameSeed<<' '<<rng.librarySeed<<' ';
  control([](auto n){std::cout<<n<<' ';});std::cout<<'\n';
 }
}
'''
OFFS=(*range(0xc,0x38,4),0x88,0x8c,0xb4,0xb8,0xbc,0xd8,0xe4,0xe8,0xc4,0xcc,*range(0x38,0x60,4))
POSTURE=(0,1,2,3,11,12,13,14,20,25,30,0x25)
ALL=(*range(0,9),*range(11,35),0x23,0x24,0x25,*range(0x26,0x46))

def settings(p,code,ukemi,rng):
    """Committed arrays A' (13738d0) and B' (1373930) and the ACTION list (1373960) that make 211058 return `code`."""
    a=[rng.randrange(0,2) for _ in range(12)];b=[rng.randrange(0,5) for _ in range(12)]
    if code<=8:a[2],b[0]=0,code
    elif code<20:a[2],b[1]=1,code-11
    elif code<25:a[2],b[2]=2,code-20
    elif code<30:a[2],b[3]=3,code-25
    elif code<35:a[2],b[4]=4,code-30
    elif code<0x26:a[2]=code-0x23+6
    else:
        a[2]=5;b[5]=rng.randrange(0,32)
        p.memory[0x1373960:0x1373980]=bytes(rng.randrange(0,32) for _ in range(32))
        p.memory[0x1373960+b[5]]=code-0x26
    a[3]=ukemi
    for i in range(12):p.write(0x13738d0+4*i,a[i],4);p.write(0x1373930+4*i,b[i],4)

def cases(seat):
    s=cpu_actor(seat);p,a,o=s.p,s.a,s.o;r=p.read(0x5d1bf8,4);b=s.b;eo=s.other
    rng=random.Random(0x15ab30+seat);base=bytes(p.memory[a:a+0xf2c]);ebase=bytes(p.memory[eo:eo+0xf2c])
    words=lambda:[p.read(a+n,4) for n in OFFS]
    rows=[];expected=[];done=collections.Counter();instructions=0
    p.write(0x123a0c0,1,1);p.write(0x123a0d8,0,4);p.write(0x123a0dc,0,4)
    for n in range(2600):
        kind=int(n>=600)
        p.memory[a:a+0xf2c]=base;p.memory[eo:eo+0xf2c]=ebase
        p.write(0x4c3808,rng.choice((9,10)),4)
        code=ALL[n%len(ALL)] if kind==0 else POSTURE[n%len(POSTURE)]
        if kind and n%29==0:code=rng.choice((0x23,0x24,4,0x26))   # 15aa18 hands the visit to the ordinary pipeline: not run here
        ukemi=rng.randrange(4);settings(p,code,ukemi,rng)
        char=rng.choice((0,1,2,3,4,16,19));spirit=rng.choice((0,1,2,3,4,5,8,8));level=rng.choice((0,3,5,6,8,49))
        flags=0x1000|rng.choice((0,0,0x10,0x10,4))
        table=rng.choice((0,0,1,2,2));index=rng.randrange(0,60)
        if table==0:index=rng.choice((0,6,11,12,9,22))
        state=(index<<16)|table
        cond1=rng.choice((0,1<<30,1<<30,0x70))
        timer28=rng.choice((0,0,0x100,0x1e00))
        flags240=rng.choice((0,1,4,5,2,8))
        old=rng.choice((code,code,0x23,0,2,11,0x25))
        echar=rng.choice((0,1,2,3,19,19));eflags=0x1000|rng.choice((0,0,0x800000,0x200000))
        etable=rng.choice((0,1,1,1,2));eindex=rng.randrange(0,96);estate=(eindex<<16)|etable
        ealias=(rng.randrange(0,40)<<16)|rng.choice((0,1,1))
        e198,e1a8=rng.randrange(0,4),rng.randrange(0,4)
        prev=rng.randrange(0,4);delta=rng.choice((256,256,128,32))
        for off,v in ((0x10c,spirit),(0xa10,char),(0x100,char),(0x108,level),(0x23c,flags),(0x240,flags240),(0x194,state),
                      (0x160,cond1),(0x220,timer28),(0xc8,old),(8,delta),(0xfc,seat),(0xa24,seat),(0xa20,1)):p.write(a+off,v,4)
        p.write(a+0x174,prev,2)
        for off,v in ((0xa10,echar),(0x23c,eflags),(0x194,estate),(0x1a4,ealias)):p.write(eo+off,v,4)
        p.write(eo+0x198,e198,2);p.write(eo+0x1a8,e1a8,2)
        for side in range(2):p.memory[b+0x29c+0x108*side:b+0x29c+0x108*side+192]=bytes(192)
        kind2=int(rng.randrange(3)==0)
        if kind2:
            node=0x1c30000;body=node+0x100;p.write(b+0x29c+(1-seat)*0x108,node,4);p.write(node+0x1c,body,4)
            for off,v in ((0xcc,2),(0xd0,rng.randrange(0,8)),(0x10,1-seat),(0x24,0),(0x38,0)):p.write(body+off,v,4)
            struct.pack_into('<f',p.memory,body+0x40,400.0)
        for offset in OFFS:p.write(a+offset,rng.choice((0,0,rng.randrange(1,9),rng.getrandbits(12))),4)
        p.write(a+0xb4,rng.choice((0,0x10,0x7f0,0x811,1)),4)
        p.write(a+0x10,rng.choice((0,0,0,0x300)),4)          # timer 1: a running count ends the visit at 1589b8
        p.write(a+0xe4,rng.choice((0xffffffff,3)),4);p.write(a+0xe8,rng.choice((0xffffffff,2)),4)
        p.write(r+0xa8,rng.getrandbits(64),8);p.write(0x3d2e80,rng.getrandbits(32),4);p.write(0x443150,n%2,4)
        before=bytes(p.memory[a:a+0xf2c])
        threat,count=p.run(0x151478,[a],limit=50000);instructions+=count
        assert bytes(p.memory[a:a+0xf2c])==before,'151478 must be a pure predicate here'
        ran_code,count=p.run(0x139c88,[],limit=20000);instructions+=count
        assert signed(ran_code,32)==code,(n,code,ran_code)
        initial=[kind,char,spirit,level,n%2,p.read(0x3d2e80,4),p.read(r+0xa8,8),code,ukemi,int(threat!=0),kind2,
                 flags,flags240,state,p.read(a+0x1a4,4),cond1,timer28,old,prev,delta,echar,eflags,estate,ealias,e198,e1a8,*words()]
        timer1=p.read(a+0x10,4)
        ret,count=p.run(0x15aa18 if kind==0 else 0x158990,[a+8],limit=200000);instructions+=count
        c8=p.read(a+0xc8,4)
        if kind==0:result=ret
        elif timer1:result=2
        else:
            # 15aa18's verdict is not returned by 158990: posture visits are recognised by the code installed.
            result=int(signed(c8,32) in POSTURE and not(c8==0x25 and p.read(a+0x240,4)&4))
        if kind and result==0:
            # The ordinary pipeline (158b08..15f638) ran in the original; only 15aa18's effect is comparable.
            p.memory[a:a+0xf2c]=before
            done['ordinary_skipped']+=1
            continue
        rows.append(initial)
        expected.append([result,p.read(a+0x108,4),p.read(a+0x240,4),c8,p.read(0x3d2e80,4),p.read(r+0xa8,8),*words()])
        done['15aa18' if kind==0 else '158990']+=1
        if kind:
            done[f'code_{signed(c8,32)}']+=1
            if result==1 and cond1&(1<<30):done['1594c8']+=1
            if result==1 and p.read(a+0x88,4)&0x1800000:done['161658_guard']+=1
            if result==1 and p.read(a+0x88,4)&0x2000:done['recovery_issued']+=1
            if result==2:done['timer1_return']+=1
    return rows,expected,done,instructions

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--build',default=str(ROOT/'work/ss6/build-native'))
    args=parser.parse_args()
    assert digest(ELF)==PIN
    total=collections.Counter();instructions=0;compared=0
    with tempfile.TemporaryDirectory() as td:
        driver=Path(td)/'probe.cpp';exe=Path(td)/'probe';driver.write_text(DRIVER)
        subprocess.run(['c++','-std=c++20','-ffp-contract=off','-O2','-I',ROOT/'src',driver,
                        Path(args.build)/'libss6-runtime.a','-o',exe],check=True)
        for seat in range(2):
            rows,expected,done,count=cases(seat)
            out=subprocess.run([exe,ASSETS],input=''.join(' '.join(map(str,row))+'\n' for row in rows),text=True,capture_output=True)
            assert out.returncode==0,out.stderr[-2000:]
            got=[list(map(int,row.split())) for row in out.stdout.splitlines()]
            assert len(got)==len(rows),(len(got),len(rows))
            for i,(g,w) in enumerate(zip(got,expected)):
                assert g==w,(seat,i,rows[i][:26],[(j,u,v) for j,(u,v) in enumerate(zip(g,w)) if u!=v])
            total.update(done);instructions+=count;compared+=len(rows)
    for code in POSTURE:assert total[f'code_{code}']>0,code
    assert total['1594c8']>50 and total['161658_guard']>20 and total['recovery_issued']>10 and total['timer1_return']>20,dict(total)
    report={'validator':'practice_dummy','passed':True,'snapshots':compared,'instructions':instructions,'coverage':dict(sorted(total.items())),
            'scope':'whole 15aa18 (all behaviour codes) and whole 158990 on posture codes for both seats; no stubs or patches; '
                    '151478 and 139c88 evaluated by the original and passed to the native side as inputs; visits that 15aa18 '
                    'hands to the ordinary CPU pipeline are excluded'}
    (ROOT/'outputs/ss6-feasibility/practice_dummy_validation.json').write_text(json.dumps(report,indent=1)+'\n')
    print(f"practice dummy: passed, {compared} snapshots, {instructions} instructions, {dict(total)}")

if __name__=='__main__':main()
