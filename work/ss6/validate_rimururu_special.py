#!/usr/bin/env python3
"""Run both public select pads through Rimururu's 27 special slots and compare each actor and ice callback to SLPS_255.59."""
import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from hashlib import sha256
from itertools import groupby
import json
from pathlib import Path
import subprocess
import tempfile

from validate_dash_motion import ELF, PIN
from validate_selected_combat import BUILD, ROOT, prefix
from validate_weapon_handling import setup
from validate_nakoruru_capture import DRIVER as VICTIM_DRIVER, compare as compare_victim

RES=ROOT/'work/ss6/extracted/resources'
OUT=ROOT/'outputs/ss6-feasibility/rimururu-special-validation.json'
ICE=(0x20,0x24,0x100,0x104,0x108,0xd0,0xd4,0x11c,0x38,0x40,0x44,0x4c,0x50,0x54,0x58,0x5c,0x60,0x64,0x68,0x6c,0x70,0xc0,0xc4)
SOURCE_IDS=(0,0,0,11,11,11,1,1,1,2,2,3,4,4,4,5,5,5,6,6,6,7,7,8,8,10,9)
BASE=(529,537,567,571,545,581,553,614,616,634,623,595)
PROJECTILE=(2,3,4,5,6,7,8,None,None,9,None,10)

def pads(side,state,mode):
    pair=lambda x,y=0:(y,x) if side else (x,y)
    f,b=(128,64)[side],(64,128)[side]
    row=prefix((0,2) if side else (2,0))
    if state in (87,88,89):
        # Native public Zan selection, then hold A+B for the original manual charge.
        for tick in (211,222,233):row[tick-1][side]=128
        row += [pair(768)]*215+[pair(0)]*30
    elif state==90:
        for tick in (211,228):row[tick-1][side]=128
    else:row[229]=[128,128]
    if 85<=state<=88 or mode=='unarmed':row += [pair(f|8)]+[pair(0)]*119
    walk=0 if state==74 else 45
    if mode=='distance':walk=-75
    if mode=='unarmed' and state==82:walk=10
    row += [(64,128) if walk<0 else (128,64)]*abs(walk)+[pair(0)]*9
    if 67<=state<=69:row += [pair(16)]+[pair(0)]*16
    if 85<=state<=88:row += [pair(f),pair(0)]+[pair(f)]*18
    start=len(row);button=(256,512,1024)[(state-64)%3]
    if state<=66:keys=[b,32,32|b|button]
    elif state<=69:keys=[32|button]
    elif state<=72:keys=[0,32,0,32|button]
    elif state<=75:keys=[32,f|32,f|button]
    elif state<=78:keys=[f,32,f|32|button]
    elif state<=81:keys=[32,b|32,b|button]
    elif state<=84:keys=[f|button,0,f|button,0,f|button]
    elif state<=88:keys=[(256|1024) if state%2 else (256|2048)]
    elif state==89:keys=[32,32|f,f|768]
    else:keys=[f,f|32,32,b|32,b]*2;keys[-1]|=1536
    if mode=='unarmed' and state==82:keys=[f|button,0]*8
    guard=(f|32 if 70<=state<=72 or state==81 else f) if mode=='guard' else 0
    moves=keys+[0]*410
    if mode=='rebound':moves[42:44]=[16|f,16|f]
    row += [pair(k,guard) for k in moves]
    if mode=='airborne':row[start+5]=pair(moves[5],16)
    return row,start

class Japanese:
    def __init__(self,side):
        original,self.reg=setup(side,2);self.o=original;self.p=original.p
        self.stage=self.p.run(0x140040)[0];self.side=side
        self.visits=Counter();self.instructions=0
        self.task=0x1ce0000;self.child=0x1cf0000;self.ctx=0x1dc0000
        self.p.write(self.task+0x1c,self.child,4)
        self.p.write(self.child+4,self.task,4)
        self.p.write(self.child+0x118,original.a,4)
        self.p.write(self.ctx,original.a,4);self.p.write(self.ctx+4,original.other,4)
        # 169810 hands off to the shared recovery implementation. The
        # native trace hook returns the same request before its caller runs it.
        self.p.write(0x169810,0x03e00008,4);self.p.write(0x169814,0,4)
    def visit(self,pc,arg):
        reached=[]
        _,ins=self.p.run(pc,[arg],limit=500000,observe=lambda adr:reached.append(adr) if adr==0x169810 else None)
        self.instructions+=ins;self.visits[hex(pc)]+=1
        return bool(reached)
    def assign(self,mapped,initial):
        assert len(mapped)==len(initial),(len(mapped),len(initial))
        for (addr,size),v in zip(mapped,initial):self.p.write(addr,v,size)
    def compare(self,mapped,expected,tick,pc):
        values=[self.p.read(ad,n) for ad,n in mapped]
        mismatch=[(hex(ad),hex(ee),hex(nat)) for (ad,n),ee,nat in zip(mapped,values,expected) if ee!=nat&((1<<(n*8))-1)]
        assert not mismatch,(tick,hex(pc),mismatch)
    def actor(self,tick,data):
        o=self.o;a=o.a;b=o.o;p=self.p
        mapped=[(a+i,1 if i==0x19a else 4) for i in (0x194,0x23c,0x248,0x19a,0x18c,0xa3c,*range(0x260,0x27c,4),*range(0x28c,0x2c0,4))]
        mapped += [(b+i,4) for i in (0x24,0x104,0x108,0x38,0xc0,0x3c,0x134,0x40,0x44,0x1040,*range(0x4c,0x64,4))]
        mapped += [(a+0x2c4+i,4) for i in (0xe0,0xfc,0x160,0x168)]
        mapped += [(o.other+0x23c,4),(o.b+0x108,4),(0x46a948,4),(0x3ebf30+2*512,2),(a+0x190,2),(a+0x192,2)]
        n=len(mapped);before=data[:n];kind,*platform=data[n:n+1+len(ICE)];recovery=data[n+1+len(ICE)]
        after=data[n+2+len(ICE):];assert len(after)==n
        self.assign(mapped,before);p.write(self.ctx+8,before[8],4)
        p.write(self.reg,self.task if kind else 0,4);p.write(self.child+0xcc,kind,4)
        self.assign([(self.child+i,4) for i in ICE],platform)
        pc=before[6];recovered=self.visit(pc,self.ctx)
        assert recovered==bool(recovery),(tick,hex(pc),recovered,recovery)
        if not recovered:self.compare(mapped,after,tick,pc)
    def child_visit(self,tick,data):
        action,left,right,pc=data[:4];fields=[(self.child+i,4) for i in ICE]
        self.assign(fields,data[4:4+len(ICE)])
        self.p.write(self.task,pc,4);self.p.write(self.o.o+0x24,action,4)
        self.p.write(self.stage+0x10,left,4);self.p.write(self.stage+0x14,right,4)
        self.visit(pc,self.task)
        self.compare([(self.task,4)]+fields,data[4+len(ICE):],tick,pc)

def check(job):
    exe,assets,side,state,mode=job
    seq,start=pads(side,state,mode)
    cmd=''.join(f'{x} {y}\n' for x,y in seq)
    run=subprocess.run([exe,assets,str(start)],input=cmd,text=True,capture_output=True)
    assert run.returncode==0,(side,state,mode,run.stderr)
    src=Japanese(side);body=[];ice=set();frames=[];seen=False
    for line in run.stdout.splitlines():
        t,*rest=line.split();v=list(map(int,rest));tick=v[0]
        if tick<start:continue
        if t=='F':
            own=v[1+side*10:11+side*10];opp=v[1+(1-side)*10:11+(1-side)*10];frames.append((tick,own,opp))
            if own[2:4]==[1,state]:body.append(own[4])
        elif v[1]==side:
            if t=='I':
                ice.add(v[2+4+5]);src.child_visit(tick,v[2:])
            else:src.actor(tick,v[2:]);seen=True
    actions=[k for k,_ in groupby(body)]
    assert seen and body and frames[-1][1][2]==frames[-1][2][2]==0,(side,state,mode,actions,frames[-1])
    expected=PROJECTILE[SOURCE_IDS[state-64]]
    if expected is not None and not 79<=state<=81:assert expected in ice,(side,state,mode,ice)
    # The trace build interposes two observation functions. Also run the
    # uninstrumented public replay against the packaged assets for the same pads.
    public=subprocess.run([BUILD/'ss6-match-replay',assets,'--mode','select','--projectile-fields'],
                          input=''.join(f'1 {x} {y}\n' for x,y in seq),text=True,capture_output=True,check=True)
    rows=public.stdout.splitlines()[start-1:]
    assert len(frames)==len(rows)
    for (tick,attacker,target),line in zip(frames,rows):
        row=line.split()
        for who,seat in ((attacker,side),(target,1-side)):
            base=3+10*seat
            want=[int(row[base+i]) for i in (0,1,2,3,6,7,8)]
            assert who[2:9]==want,(tick,seat,who[2:9],want)
    last=frames[-1];assert last[1][0]==2 and last[2][0]==0
    if mode=='unarmed':assert any(not (s[9]&4096) for _,s,_ in frames if s[2:4]==[1,state])
    if mode=='near' and state!=79:assert last[1][7]>0,(side,state,mode,last)
    if mode=='guard' and state!=79:assert last[1][8]>0,(side,state,mode,last)
    if mode=='airborne':assert last[2][6]<200 and last[1][7]>0
    if mode=='rebound':assert 599 not in actions and any(f[2:4]==[0,20] for _,f,d in frames)
    return dict(seat=side,state=state,scenario=mode,entry=next(t for t,s,d in frames if s[2:4]==[1,state]),actions=actions,
                ice=sorted(ice),life=last[2][6],hits=last[1][7],guards=last[1][8],callbacks=src.visits,instructions=src.instructions)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--case',nargs=3);ap.add_argument('--assets',type=Path,default=RES)
    args=ap.parse_args()
    with tempfile.TemporaryDirectory() as folder:
        d=Path(folder);exe=d/'fight';obj=d/'traced.o';cxx=['c++','-std=c++20','-ffp-contract=off','-O2','-I',str(ROOT/'src')]
        subprocess.run([*cxx,'-DupdateRimururuSpecial=tracedCast','-DupdateRimururuIce=tracedIce','-c',ROOT/'src/rimururu_special.cpp','-o',obj],check=True)
        subprocess.run([*cxx,ROOT/'work/ss6/rimururu_special_trace.cpp',obj,BUILD/'libss6-runtime.a','-o',exe],check=True)
        cases=[(side,state,mode) for side in (0,1) for state in range(64,91) for mode in ('near','guard','distance')]
        cases += [(side,state,'unarmed') for side in (0,1) for state in (*range(64,85),89,90)]
        cases += [(side,67,'rebound') for side in (0,1)]+[(side,79,'airborne') for side in (0,1)]
        if args.case:cases=[(int(args.case[0]),int(args.case[1]),args.case[2])]
        with ProcessPoolExecutor(4) as pool:results=list(pool.map(check,[(exe,args.assets,*case) for case in cases]))
        if args.case:print(results);return
        # 1edfa0 chooses 2/69 after weapon loss. Exercise the independent
        # target-side capture callback, including its simultaneous-hit fallback.
        victim=d/'victim';cpp=d/'victim.cpp';cpp.write_text(VICTIM_DRIVER)
        subprocess.run([*cxx,cpp,BUILD/'libss6-runtime.a','-o',victim],check=True)
        specs=[(0,side,armed,target,mode,spirit,2) for side in (0,1) for armed in (0,1)
               for target in (0,1,2) for mode in (0,1,2,3,4,15,16,17) for spirit in (1,2)]
        result=subprocess.run([victim,args.assets,'2'],input=''.join('%d %d %d %d %d %d\n'%spec[:6] for spec in specs),
                              text=True,capture_output=True,check=True)
        with ProcessPoolExecutor(4) as pool:expected=list(pool.map(compare_victim,specs))
        for spec,line,(want,_) in zip(specs,result.stdout.splitlines(),expected,strict=True):
            got=list(map(int,line.split()))
            assert got==want,(spec,[(i,a,b) for i,(a,b) in enumerate(zip(got,want)) if a!=b])
    assert sha256(ELF.read_bytes()).hexdigest()==PIN
    report=dict(status='passed',elf_sha256=PIN,replay_sha256=sha256((BUILD/'ss6-match-replay').read_bytes()).hexdigest(),
                runtime_sha256=sha256((BUILD/'libss6-runtime.a').read_bytes()).hexdigest(),cases=results,
                weapon_loss_cases=len(specs),weapon_loss_instructions=sum(count for _,count in expected),
                callback_visits=sum(sum(r['callbacks'].values()) for r in results),original_instructions=sum(r['instructions'] for r in results),
                scope='Both publicly selected pads exercise all 27 slots, real disarming, Zan manual charge and Shin secret input. The original fighter and projectile callbacks execute independently with each observed incoming state. The common recovery handoff and the final live match positions/state are checked separately.')
    packaged=args.assets.parent/'ss6-viewer'
    if packaged.is_file():report['packaged_viewer_sha256']=sha256(packaged.read_bytes()).hexdigest()
    OUT.write_text(json.dumps(report,indent=2)+'\n');print(len(results),'fights,',report['callback_visits'],'EE callback calls')
if __name__=='__main__':main()
