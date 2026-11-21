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

def chain_parents():
    # Condition id -> the special states (lo..hi) it requires the fighter to be in: input_permissions.cpp's
    # 'attack(lo,hi)' cases (follow-up commands that cancel a running special).
    import re
    src=(ROOT/'src/input_permissions.cpp').read_text();out={}
    for m in re.finditer(r'case (\d+):(?:case \d+:)*(.*?)(?=\n    case \d+:|\n    default:)',src,re.S):
        for lo,hi in re.findall(r'(?<!raw)[aA]ttack\((\d+),(\d+)\)',m.group(2)):
            out.setdefault(int(m.group(1)),set()).update(range(int(lo),int(hi)+1))
    return out

CATEGORY_LEADS={0:('g','up'),1:('g',),2:('run','runhold'),3:('run','runhold','g'),4:('up','apex','fall'),5:('apex','fall'),6:('apex',),
                7:('fall',),8:('apex','fall'),9:('g',),10:('guard',),11:('guard','roll','rollback')}

def slot_jobs(exe,n,tmp):
    import struct
    res=ROOT/'work/ss6/extracted/resources'
    pads_exe=Path(tmp)/'cpads'
    subprocess.run(['c++','-std=c++20','-O1','-I',ROOT/'src',ROOT/'work/ss6/command_pads.cpp',BUILD/'libss6-runtime.a','-o',pads_exe],check=True)
    cmds=[{},{}]
    for facing in (0,1):
        for line in subprocess.check_output([pads_exe,res,str(facing)],text=True).splitlines():
            i,status,pads=line.split(' ',2)
            if status=='ok':cmds[facing][int(i)]=pads
    d=(res/'input_special.bin').read_bytes();recs=[struct.unpack_from('<BBhHHHH',d,i*12) for i in range(972)]
    from fighter_roster import LOGIC
    logic=LOGIC.get(n,n) # Purple Nakoruru (42) binds Nakoruru's (1) records and entries
    start=next(i for i,r in enumerate(recs) if r[0]==logic);ent=(res/'entry_special.bin').read_bytes()
    seen=set()
    for suf in ('','spirit_','rage_'):
        f=ROOT/f'outputs/ss6-feasibility/fighter_{n:02}_{suf}gaps.json'
        if f.exists():seen|={int(x[2:]) for x in json.loads(f.read_text())['states_seen'] if x.startswith('1/')}
    jobs=[];slots=[]
    for slot in range(32):
        r=recs[start+slot]
        if r[2]==-1:break
        slots.append(r)
    # Candidate entering commands for form requirements: the fighter's own ground commands without form bits.
    chains=chain_parents()
    entering=[r[2] for r in slots if (r[3]>>8) in (0,1,9) and not (r[4]&0x32)]
    for slot in range(32):
        _,_,cmd,cond,flags,systems,_=recs[start+slot]
        if cmd==-1:break
        e=ent[(logic*32+slot)*5:(logic*32+slot)*5+5];category=cond>>8
        if (e[0]==0 and e[1]==0) or category==12 or not systems or 64+slot in seen:continue
        spirits=[s for s in range(6) if systems>>s&1] if n not in (44,45,46,47) else [None]
        leads=CATEGORY_LEADS.get(category,('g',))
        # Spirit-gauge moves (meterReady: the system gauge >= life): block the CPU's attacks to build the
        # gauge while it lowers life, then try the command.
        if (cond&255) in (6,28,31,79):leads=leads+('guard','guardlong')
        pres=[(None,0)]
        # The entering command plus a settling wait (a hawk or partner has to arrive first).
        # Conditions 29..31 need Amakusa's alternate stance (23c:400000), also entered by one of his commands.
        if flags&0x30 or (cond&255) in (29,30,31):pres=[(p,w) for p in dict.fromkeys(entering) for w in (40,100,180)]
        # A follow-up: perform a parent special first, then this command after a short gap.
        parents=chains.get(cond&255,())
        if parents:
            # Chains: play the parent's own chain first (Genjuro 76..78 -> 70..75 -> 64..69). pres entries
            # are (tuple of command ids, wait); each step waits the same gap before the next command.
            def paths(st,depth=0):
                c=slots[st-64][3]&255
                if depth<3 and c in chains:
                    return [p+(slots[st-64][2],) for q in sorted(chains[c]) if q-64<len(slots) and q!=st for p in paths(q,depth+1)]
                return [(slots[st-64][2],)]
            seqs=list(dict.fromkeys(p for st in sorted(parents) if st-64<len(slots) for p in paths(st)))
            gaps=(2,4,6,8,10,14,18,24,30,38,48,60) if all(len(p)==1 for p in seqs) else (6,12,20)
            pres=[(p,w) for p in seqs for w in gaps]
            leads=leads+('near',) # walk up to an idle opponent so the parent connects
        if (cond&255)==73:pres=[('C',w) for w in (2,4,6,8,12)];leads=leads+('near',) # cancel a heavy slash (normal 8/9)
        # Kuroko's collection (conditions 78/79, f21 == 0x7f): every projectile technique must hit first, so
        # play each object-spawning ground command twice against the idle opponent, then the command.
        if (cond&255) in (78,79):
            techs=tuple(dict.fromkeys(r[2] for r in slots if r[4]&4 and (r[3]>>8) in (0,1) and r[3]&255==255))
            pres=[(techs*2,w) for w in (60,120)]
        # Companion ready (requirement bit 3, e.g. Kazuki's fire level f15 from script event 24): enter it first.
        if flags&8 and pres==[(None,0)]:pres=[(p,w) for p in dict.fromkeys(entering) for w in (20,60)]
        # A form follow-up on contact (condition 34: Rera riding, 0x800000, a ridden attack ACT that hits):
        # the form's entering command, one of the form's own attacks, then this command after a short gap.
        if (cond&255)==34:
            attacks=[r[2] for r in slots if r[4]&0x20 and (r[3]&255)==255]+[0,1,2]
            pres=[((e,f'W{settle}',c),w) for e in dict.fromkeys(entering) for settle in (40,100) for c in dict.fromkeys(attacks) for w in (6,12,20)]
            leads=('nearfirst',) # walk in before the form and its attack, so the ridden attack connects
        # Any other situational condition: try each of the fighter's own commands as the entering move.
        if pres==[(None,0)] and (cond&255)!=255:
            pres=[(c,w) for c in dict.fromkeys(r[2] for r in slots) for w in (4,10,20,40)];leads=leads+('near',)
        # Unarmed moves: discard the weapon first, then the move's own lead (running, jumping, ...).
        if flags&2:pres=[(('D',)+(p if isinstance(p,tuple) else (() if p is None else (p,))),w) for p,w in pres]
        for sp in spirits:
            for lead in leads:
                for pre,wait in pres:
                    opponents=((0,(n,7),'p2'),(1,(26,n),'p1'))
                    # A form (riding) is lost to hits: also try against an idle opponent.
                    if flags&0x32 or (cond&255)!=255:opponents+=((0,(n,7),'none'),(1,(26,n),'none'))
                    for seat,lineup,cpu in opponents:
                        steps=() if pre is None else (pre if isinstance(pre,tuple) else (pre,))
                        if cmd not in cmds[seat] or any(x not in ('C','D') and not str(x).startswith('W') and x not in cmds[seat] for x in steps):continue
                        b=(0x40,0x80)[seat]
                        token=lambda x:'1024,1024' if x=='C' else f'{b|8}'+',0'*300 if x=='D' else cmds[seat][x]
                        # 'W<n>': n extra neutral ticks (a form's settling time) instead of a command.
                        p=','.join(','.join(['0']*int(x[1:])) if str(x).startswith('W') else token(x)+',0'*wait for x in steps)
                        jobs.append((exe,lineup,seat,cpu,f'SLOT:{lead}:{p}:{cmds[seat][cmd]}',(sp,sp) if sp is not None else None))
    return jobs

SLOT_LEADS=None
def slot_pads(seat,move):
    # The pad sequence (after the select prefix and 330 neutral ticks) of a 'SLOT:' move.
    _,lead,pre,raw=move.split(':',3);cmd=[int(x) for x in raw.split(',')]
    pre=[int(x) for x in pre.split(',')] if pre else []
    # A lead-in (run, jump, guard) must flow straight into the command: drop its leading neutral ticks.
    if lead!='g':
        while cmd and cmd[0]==0:cmd.pop(0)
    if lead=='runhold':cmd=[x|(0x80,0x40)[seat] for x in cmd];lead='run'
    f,b=(0x80,0x40)[seat],(0x40,0x80)[seat]
    leads={'g':[],'run':[f]*3+[0]*3+[f]*24,'up':[0x10]*3+[0]*2,'apex':[0x10|f]*3+[0]*14,'fall':[0x10|b]*3+[0]*26,
           'guard':[b]*40,'guardlong':[b]*240,'near':[f]*90+[0]*4,'nearfirst':[],'disarm':[b|8]+[0]*300,
           # Category 11 also admits the recovery rolls 0/54 and 0/55: 1720b0 latches feature 10 (pad 0x1000)
           # during the knockdown fall, back (input+100) choosing 55; the command follows the roll.
           'roll':[f|0x1000,f|0x1000,f,f]*8,'rollback':[b|0x1000,b|0x1000,b,b]*8}
    out=[]
    for _ in range(50):out+=[0]*120+([f]*90+[0]*4 if lead=='nearfirst' else [])+pre+leads[lead]+cmd
    return out

def slot_selection(n,limit=40):
    # Greedy cover of the special states the slot sweep reached for fighter n, as (lineup, seat, cpu, move, spirits).
    f=ROOT/f'outputs/ss6-feasibility/fighter_{n:02}_slots_gaps.json'
    if not f.exists():return []
    runs=[r for r in json.loads(f.read_text())['results'] if r['result'].startswith('END')]
    covered=set();picked=[]
    while len(picked)<limit:
        best=max(runs,key=lambda r:len(set(r['specials'])-covered),default=None)
        if not best or not set(best['specials'])-covered:break
        covered|=set(best['specials']);picked.append(best)
    return [(tuple(r['lineup']),r['seat'],r['cpu'],r['move'],tuple(r['spirits']) if r['spirits'] else None) for r in picked]

def run(job):
    exe,lineup,seat,cpu,move=job[:5];spirits=job[5] if len(job)>5 else None
    seq=prefix(lineup,spirits)+[[0,0]]*330
    if move and move.startswith('SLOT:'):
        # 'SLOT:<lead>:<pre>:<pads>': an optional entering command <pre> (a form such as riding), a
        # category lead-in, then the synthesized command pads, repeated while the CPU opponent attacks
        # (rage and spirit gauges fill, guard and hit situations occur). lead 'disarm' discards the weapon.
        _,lead,pre,raw=move.split(':',3);cmd=[int(x) for x in raw.split(',')]
        pre=[int(x) for x in pre.split(',')] if pre else []
        # A lead-in (run, jump, guard) must flow straight into the command: drop its leading neutral ticks.
        if lead!='g':
            while cmd and cmd[0]==0:cmd.pop(0)
        if lead=='runhold':cmd=[x|(0x80,0x40)[seat] for x in cmd];lead='run'
        f,b=(0x80,0x40)[seat],(0x40,0x80)[seat]
        leads={'g':[],'run':[f]*3+[0]*3+[f]*24,'up':[0x10]*3+[0]*2,'apex':[0x10|f]*3+[0]*14,'fall':[0x10|b]*3+[0]*26,
               'guard':[b]*40,'guardlong':[b]*240,'near':[f]*90+[0]*4,'nearfirst':[],'disarm':[b|8]+[0]*300,
           # Category 11 also admits the recovery rolls 0/54 and 0/55: 1720b0 latches feature 10 (pad 0x1000)
           # during the knockdown fall, back (input+100) choosing 55; the command follows the roll.
           'roll':[f|0x1000,f|0x1000,f,f]*8,'rollback':[b|0x1000,b|0x1000,b,b]*8}
        for _ in range(50):
            seq+=[[0,0]]*120
            for x in ([f]*90+[0]*4 if lead=='nearfirst' else [])+pre+leads[lead]+cmd:seq.append([x,0] if seat==0 else [0,x])
    elif move and move.startswith('RAGE:'):
        # The CPU opponent beats the idle fighter into rage; the motion repeats every 150 ticks.
        for _ in range(60):
            seq+=[[0,0]]*150
            for x in pads(seat,move[5:]):seq.append([x,0] if seat==0 else [0,x])
    elif move:
        for x in pads(seat,move):seq.append([x,0] if seat==0 else [0,x])
    else:seq+=[[0,0]]*12000
    r=subprocess.run([exe,ROOT/'work/ss6/extracted/resources',cpu],input=''.join(f'{a} {b}\n' for a,b in seq),text=True,capture_output=True)
    if r.returncode not in (0,1,2):return dict(lineup=lineup,seat=seat,cpu=cpu,move=move,spirits=spirits,result=f'CRASH {r.returncode} {r.stderr[-200:]}',states=[],acts=[])
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
    ap.add_argument('--rage',action='store_true')
    # --slots: every special slot no earlier sweep reached, with its own command and situation (see SLOT:).
    ap.add_argument('--slots',action='store_true');args=ap.parse_args()
    n=args.fighter
    with tempfile.TemporaryDirectory() as tmp:
        exe=Path(tmp)/'gap'
        subprocess.run(['c++','-std=c++20','-ffp-contract=off','-O2','-I',ROOT/'src',ROOT/'work/ss6/fighter_gap_probe.cpp',BUILD/'libss6-runtime.a','-o',exe],check=True)
        jobs=[]
        if args.slots:jobs=slot_jobs(exe,n,tmp)
        elif args.rage:
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
    seen=sorted({s for r in results if len(r['states'])>r['seat'] for s in r['states'][r['seat']]})
    out=ROOT/f'outputs/ss6-feasibility/fighter_{n:02}_{"slots_" if args.slots else "rage_" if args.rage else "spirit_" if args.spirits else ""}gaps.json'
    out.write_text(json.dumps(dict(fighter=n,runs=len(results),gaps=gaps,states_seen=seen,
        results=[{**{k:(list(v) if isinstance(v,tuple) else v) for k,v in r.items() if k not in('states','acts')},'specials':[x for x in (r['states'][r['seat']] if len(r['states'])>r['seat'] else []) if x.startswith('1/') and int(x[2:])>=64]} for r in results]),indent=1)+'\n')
    for k,v in gaps.items():print(len(v),k,'e.g.',v[0])
    print(len(results),'runs',sum(r['result'].startswith('END') for r in results),'clean')

if __name__=='__main__':main()
