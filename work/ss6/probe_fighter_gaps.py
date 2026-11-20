#!/usr/bin/env python3
"""Pipeline step C: gap probe for a newly admitted fighter.

Selects the fighter through the real console VS grid against every other
playable fighter in both seats, then runs (a) a CPU-vs-CPU match and (b) a
public pad sequence covering movement, normals and every input-binding
special motion. Reports the first UnportedFighterState or runtime error of
each run; it never decides that a move is complete.
Usage: probe_fighter_gaps.py --fighter 26 [--build]
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import subprocess
import tempfile

from validate_selected_combat import prefix, ROOT, BUILD

U,D,A,B,C,K,E=0x10,0x20,0x100,0x200,0x400,0x800,0x1000
from fighter_roster import PLAYABLE
MOTIONS=['5A','5B','5C','5K','2A','2B','2C','2K','6A','6B','6C','3A','3B','3C','3K','4A','4K','AB','BC','CK','BK','AC','CE','BE','AE',
         '236A','236B','236C','236K','214A','214B','214C','214K','623A','623B','623C','623K','421A','421B','421C','421K',
         '41236A','41236B','41236C','41236K','63214A','63214B','63214C','63214K','22A','22B','22C','22K','236AB','236BC','214AB','623AB',
         '6321463214A','2363214C','6321AK','6321BK','6321AB','W6321AK','W623K','W236A','W236B','W236C','W236K','W6C','W4C','W214K','W623C','W63214C','W5C','W2C','W236AB','W236BC',*[f'W236A.236B.236C@{g}' for g in (0,3,6,9,12,16,20,26)],'TAUNT','j5A','j5B','j5C','j5K','j2A','j2B','j2C','u5A','u5C','66','44','8','9','7','6A6B6C',
         *[f'H{n}421{x}' for n in (40,120,240) for x in 'ABC']]

RAGE_MOTIONS=['236AB','236BC','214AB','623AB','623BC','214BC','6321463214A','6321463214C','2363214C','41236C','63214C','22AB','22BC','AB','BC','CK']

def pads(seat,move):
    # 'X.Y@g': perform X, then Y after g neutral ticks (cancel chains).
    if '.' in move:
        body,gap=move.split('@');parts=body.split('.');out=[]
        for i,m in enumerate(parts):
            out+=pads(seat,m)[:-150]+([0]*int(gap) if i+1<len(parts) else [])
        return out+[0]*150
    f,b=(0x80,0x40)[seat],(0x40,0x80)[seat]
    dirs={'5':0,'6':f,'4':b,'2':D,'3':D|f,'1':D|b,'8':U,'9':U|f,'7':U|b}
    btn={'A':A,'B':B,'C':C,'K':K,'E':E}
    out=[]
    m=move
    # Hn: keep the final buttons held n ticks after the command (charge moves).
    if m[0]=='H':
        n=int(''.join(ch for ch in m[1:4] if ch.isdigit()));m=m[1+len(str(n)):]
        base=pads(seat,m)[:-150];held=base[-1]
        return base+[held]*n+[0]*150
    if m[0]=='W':out+=[f]*150+[0]*24;m=m[1:]
    if m[0] in 'ju':out+=[U|(f if m[0]=='j' else 0)]*4+[0]*8;m=m[1:]
    if m=='TAUNT':out+=[b|8]+[0]*300;return out+[0]*150
    if m in('66','44'):out+=[dirs[m[0]]]*3+[0]*3+[dirs[m[0]]]*30
    elif m in('8','9','7'):out+=[dirs[m]]*4
    elif m=='6A6B6C':
        for x in 'ABC':out+=[f|btn[x]]*3+[0]*12
    else:
        i=0;ds=[];bs=0
        while i<len(m) and m[i].isdigit():ds.append(m[i]);i+=1
        ds=ds or ['5']
        for ch in m[i:]:bs|=btn[ch]
        out+=[dirs[d] for d in ds[:-1] for _ in range(3)]+[dirs[ds[-1]]|bs]*3
    return out+[0]*150

def run(job):
    exe,lineup,seat,cpu,move=job[:5];spirits=job[5] if len(job)>5 else None
    seq=prefix(lineup,spirits)+[[0,0]]*330
    if move and move.startswith('RAGE:'):
        # The CPU opponent beats the idle fighter into rage; the motion repeats every 150 ticks.
        for _ in range(60):
            seq+=[[0,0]]*150
            for x in pads(seat,move[5:]):seq.append([x,0] if seat==0 else [0,x])
    elif move:
        for x in pads(seat,move):seq.append([x,0] if seat==0 else [0,x])
    else:seq+=[[0,0]]*12000
    r=subprocess.run([exe,ROOT/'work/ss6/extracted/resources',cpu],input=''.join(f'{a} {b}\n' for a,b in seq),text=True,capture_output=True)
    lines=r.stdout.splitlines()
    head=lines[0] if lines else r.stderr[-300:]
    states=[l.split()[2:] for l in lines if l.startswith('STATES')]
    acts=[l.split()[2:] for l in lines if l.startswith('ACTS')]
    return dict(lineup=lineup,seat=seat,cpu=cpu,move=move,spirits=spirits,result=head,states=states,acts=acts)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--fighter',type=int,required=True)
    # --spirits: CPU-vs-CPU with both seats on Rage/Shin/Zan/Ten/Zero against a fixed opponent sample.
    ap.add_argument('--spirits',action='store_true')
    # --rage: every spirit, a CPU opponent beats the human-controlled fighter into rage while it repeats
    # a secret-art style command (rage-gated moves the CPU sweep rarely reaches).
    ap.add_argument('--rage',action='store_true');args=ap.parse_args()
    n=args.fighter
    with tempfile.TemporaryDirectory() as tmp:
        exe=Path(tmp)/'gap'
        subprocess.run(['c++','-std=c++20','-ffp-contract=off','-O2','-I',ROOT/'src',ROOT/'work/ss6/fighter_gap_probe.cpp',BUILD/'libss6-runtime.a','-o',exe],check=True)
        jobs=[]
        if args.rage:
            for sp in range(6):
                for m in RAGE_MOTIONS:
                    jobs+=[(exe,(n,7),0,'p2','RAGE:'+m,(sp,sp)),(exe,(26,n),1,'p1','RAGE:'+m,(sp,sp))]
        elif args.spirits:
            sample=[o for o in PLAYABLE][::5]+[n]
            for s in range(0,5): # Rage, Shin, Zan, Ten, Zero (the default sweep plays Ken)
                for other in sample:jobs+=[(exe,(n,other),0,'both',None,(s,s)),(exe,(other,n),1,'both',None,(s,s))]
        else:
         for other in PLAYABLE:
            jobs+=[(exe,(n,other),0,'both',None),(exe,(other,n),1,'both',None)]
         for seat in (0,1):
            lineup=(n,0) if seat==0 else (0,n)
            jobs+=[(exe,lineup,seat,'none',m) for m in MOTIONS]
        with ThreadPoolExecutor(8) as pool:results=list(pool.map(run,jobs))
    gaps={}
    for r in results:
        key=r['result'].split(' ',2)[-1] if not r['result'].startswith('END') else None
        if key:gaps.setdefault(key,[]).append(f"{r['lineup']} seat{r['seat']} {r['cpu']} {r['move']}")
    seen=sorted({s for r in results for s in r['states'][r['seat']]} if results else [])
    out=ROOT/f'outputs/ss6-feasibility/fighter_{n:02}_{"rage_" if args.rage else "spirit_" if args.spirits else ""}gaps.json'
    out.write_text(json.dumps(dict(fighter=n,runs=len(results),gaps=gaps,states_seen=seen,
        results=[{**{k:(list(v) if isinstance(v,tuple) else v) for k,v in r.items() if k not in('states','acts')},'specials':[x for x in (r['states'][r['seat']] if r['states'] else []) if x.startswith('1/') and int(x[2:])>=64]} for r in results]),indent=1)+'\n')
    for k,v in gaps.items():print(len(v),k,'e.g.',v[0])
    print(len(results),'runs',sum(r['result'].startswith('END') for r in results),'clean')

if __name__=='__main__':main()
