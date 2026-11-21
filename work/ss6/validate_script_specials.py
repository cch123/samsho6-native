#!/usr/bin/env python3
"""Compare a script-only fighter's attack callbacks (its 4e8fe8 stub and the
163610 interpreter) in real, publicly selected fights with SLPS_255.59.

Parameterized form of validate_mina_specials.py (pipeline step F). Each
native visit is replayed on the original executable from the same actor,
body, opponent and camera words; all of them are compared afterwards,
together with whether 169810 recovery was reached.
Usage: validate_script_specials.py --fighter 26
"""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import tempfile

from validate_selected_combat import BUILD, ROOT, prefix
from validate_mina_specials import Original as MinaOriginal
from validate_weapon_handling import setup
from probe_fighter_gaps import pads as move_pads, PLAYABLE, MOTIONS, slot_pads, slot_selection
SLOT_RUNS=[]
from fighter_roster import SCRIPT_STUBS

RES=ROOT/'work/ss6/extracted/resources'
SLOTS=48
SLOT_WORDS=(0xcc,0xd0,0x24,0x40,0x28,0x38,0x44,0xb0,0xc0,0xc4,0x104,0x108,0xe4,0x128,0x12c,0x130,0x134)
# Poppy's (44) puppies keep plain lane/state values in 128..134; other fighters' objects hold native
# handles there (not original pointers), so these words are neither seeded nor compared for them.
PLAIN_WORDS={44:(0x128,0x12c,0x130,0x134)}
# Directed rage scenarios for rage-gated moves the CPU sweep does not reach.
RAGE_MOVES={16:('RAGE7:214BC','RAGE26:236BC'),41:('RAGE7:236BC',),48:('CPU21S3','CPU24S3','CPU15S1'),45:('RAGE7:236AB','RAGE0:236AB','RAGE26:236AB','RIDE40:BC,214A,236B,214C,236C','RIDE40:214B,236A,BC')}
class Original(MinaOriginal):
    def compare(self,case,values):
        # Map the native presence flag onto the fixture's registry slot. An
        # object the visit itself creates lives in a task the original
        # allocated: compare the slot by presence and read that object.
        p=self.p;n=len(self.fields);values=list(values)
        start,end=values[:n],values[n+1:]
        W=1+len(SLOT_WORDS)
        # Presence 2 is the companion's slot: its task points at the companion block (compared there).
        skip=set()
        for s in range(SLOTS):
            k=self.present+W*s
            if start[k]==2:skip.update(range(k+1,k+W))
            start[k]=self.ctask if start[k]==2 else self.tasks[s] if start[k] else 0
        # A registry-slot marker (Basara's body+128, Kyoshiro's 128..134) becomes that slot's fixture object.
        for m in self.markers:
            if (start[m]&0xffffffc0)==0x80000000:start[m]=self.objs[start[m]&63]
        for i,((addr,size),v) in enumerate(zip(self.fields,start)):
            if i not in self.opaque and i not in skip:p.write(addr,v,size)
        pc=start[6];p.write(self.ctx+8,start[8],4);recover=[]
        import os
        dbg=os.environ.get('SS6_DEBUG_ROW')
        trace=[]
        def obs(ad):
            if ad==0x169810:recover.append(1)
            if dbg and ad in (0x140c68,0x140a78):print('ALLOC',case,hex(ad),'ra',hex(p.registers[31]),flush=True)
            if dbg and dbg in str(case):trace.append(ad)
        try:_,ins=p.run(pc,[self.ctx],limit=800000,observe=obs)
        except NotImplementedError as e:raise NotImplementedError((case,hex(pc),str(e),'state',hex(start[0]),'cb',hex(start[6]),'markers',[hex(start[m]) for m in self.markers]))
        if trace:
            out=[];prev=None
            for x in trace:
                if prev is None or x!=prev+4:out.append(hex(x))
                prev=x
            print('TRACE',case,' '.join(out[:200]),flush=True)
        self.instructions+=ins;self.calls[hex(pc)]+=1
        fields=list(self.fields)
        for s in range(SLOTS):
            k=self.present+W*s;slot=p.read(self.slots[s],4)
            if end[k]==2:end[k]=self.ctask;skip.update(range(k+1,k+W));continue
            if slot and slot!=self.tasks[s]:
                obj=p.read(slot+0x1c,4)
                fields[k+1:k+W]=[(obj+off,4) for off in SLOT_WORDS]
                end[k]=slot if end[k] else 0
            else:end[k]=self.tasks[s] if end[k] else 0
        for m in self.markers:
            if (end[m]&0xffffffc0)==0x80000000:
                s=end[m]&63;slot=p.read(self.slots[s],4)
                end[m]=p.read(slot+0x1c,4) if slot and slot!=self.tasks[s] else self.objs[s]
        problems=[]
        import os
        if os.environ.get('SS6_DEBUG_ROW'):
            r0=start[self.fields.index((self.src.a+0x28c,4))];r11=start[self.fields.index((self.src.a+0x28c+44,4))]
            print('ROW',case,hex(pc),r0,bytes(p.read(r11+20*r0+k,1) for k in range(20)).hex() if r11 else None,'body24',hex(p.read(p.read(self.src.a,4)+0x24,4)),flush=True)
        if (self.fighter,start[8]) in ((4,15),(19,5),(41,15),(23,4)):
            # 1ef608 (Galford 15) and 1f82b0 (Rera 5) run the opponent's 1491e0 at once; that entry reads its whole actor, which this
            # fixture does not mirror (the shared state-entry validators cover it).
            k=self.fields.index((self.src.other+0x23c,4));end[k]=p.read(self.src.other+0x23c,4)
        if bool(recover)!=bool(values[n]):problems.append(('recovery',bool(recover),values[n]))
        problems+=[(i,hex(ad),hex(p.read(ad,size)),hex(v)) for i,((ad,size),v) in enumerate(zip(fields,end)) if i not in self.opaque and i not in skip and i!=self.cached and p.read(ad,size)!=v&((1<<(size*8))-1)]
        if problems and os.environ.get('SS6_DEBUG_SEL'):problems.append(('selector',start[8],'state',hex(start[0]),'23c',hex(start[1]),'opp23c',hex(start[self.fields.index((self.src.other+0x23c,4))])))
        return (case,hex(pc),problems) if problems else None

    def __init__(self,side,fighter):
        self.fighter=fighter
        self.src,_=setup(side,fighter);o=self.src;self.p=p=o.p
        stage=p.run(0x140040)[0];self.ctx=0x1dc0000
        p.write(self.ctx,o.a,4);p.write(self.ctx+4,o.other,4)
        p.write(0x169810,0x03e00008,4);p.write(0x169814,0,4)
        a,b=o.a,o.o
        self.fields=[(a+i,1 if i==0x19a else 4) for i in (0x194,0x23c,0x248,0x19a,0x18c,0xa3c,*range(0x260,0x27c,4),*range(0x28c,0x2c0,4))]
        self.fields += [(b+i,4) for i in (0x24,0x104,0x108,0x38,0xc0,0x3c,0x134,0x40,0x44,0x1040,*range(0x4c,0x64,4))]
        self.fields += [(a+0x2c4+i,4) for i in (0xe0,0xfc,0x160,0x168)]
        self.fields += [(o.other+0x23c,4),(o.b+0x108,4),(0x46a948,4),(0x3ebf30+2*512,2),(a+0x190,2),(a+0x192,2),
                        (b+0x128,4),(a+0x1b0+17*4,4),(a+0x1b0+18*4,4),(o.b+0x138,4)]
        self.fields += [(stage+off,4) for off in (0x10,0x14,0x1c)]
        target=p.read(o.other,4);self.fields += [(target+0x40,4),(target+0x44,4),(a+0x24c,1),(o.other+0x194,4)]
        # The companion's command words (Galford's Poppy, written by his selectors). Other script
        # fighters have none: the block is parked in unused memory with zero words.
        if fighter in (4,16,19,32,33,34,45):p.write(a+4,0x1dd0000,4)
        else:assert not p.read(a+4,4),'a script-only fighter has no companion object'
        self.fields += [(0x1dd0000+off,4) for off in (0x128,0x12c,0x40,0x44,0x130,0x134,0x24,0xc0,0xc4,0x104,0x38,0xfc)]+[(a+0x244,4)]
        self.fields += [(a+off,4) for off in (0xa38,0x120,0x124,0x128,0x134,0x138,0x10c,0xa30)]
        # The first SLOTS slots of this seat's registry: each native object
        # becomes a fixture task/object in the same slot (140d78 scans them).
        self.slots=[o.b+0x29c+0x108*side+4*s for s in range(SLOTS)]
        self.tasks=[0x1de8000+0x40*s for s in range(SLOTS)];self.objs=[0x1de9000+0x200*s for s in range(SLOTS)]
        for t,ob in zip(self.tasks,self.objs):p.write(t+0x1c,ob,4)
        self.ctask=0x1de8000+0x40*SLOTS;p.write(self.ctask+0x1c,0x1dd0000,4)
        self.body128=self.fields.index((b+0x128,4))
        self.present=len(self.fields)
        plain=PLAIN_WORDS.get(fighter,());self.opaque=set()
        # Field b+0x1040 is the frame's cached opponent X (seeded before the visit, never updated by it); the
        # original keeps one word, compared through the opponent body's own X field.
        self.cached=self.fields.index((b+0x1040,4))
        for slot,ob in zip(self.slots,self.objs):
            for off in SLOT_WORDS:
                if off>=0x128 and off not in plain:self.opaque.add(len(self.fields)+1+SLOT_WORDS.index(off))
            self.fields += [(slot,4)]+[(ob+off,4) for off in SLOT_WORDS]
        self.fields += [(o.o+0x12c,4)]+[(a+0x2c4+4*n,4) for n in range(6,11)]+[(a+0x2c4+4*n,4) for n in range(0x5b,0x5e)]
        self.fields += [(a+0x1ac,4),(a+0x1b0+22*4,4),(a+0x1b0+23*4,4),(a+0x2c4+62*4,4),(a+0x2c4+64*4,4),(b+0x130,4),(a+0x2c4+55*4,4),(a+0x2c4+57*4,4),(a+0xf18,1),(a+0xf15,1),(a+0xf16,1)]+[(a+0x2c4+off,4) for off in (0x14c,0x150,0x158,0x15c)]+[(a+0x2c4+4*3,4),(a+0x2c4+4*45,4),(b+0xb0,4),(b+0x30,4),(a+0xa44,4),(0x443150,4),(0x3d2e80,4),(p.read(0x5d1bf8,4)+0xa8,4),(p.read(0x5d1bf8,4)+0xac,4),(a+0x2c4+4*24,4),(stage+0xc,4)]+[(target+off,4) for off in (0x128,0x12c,0x130,0x134)]+[(b+0x28,4),(o.other+0xa10,4),(b+0x110,4),(b+0x114,4)]
        # Handle-holding body words (registry-slot markers in the trace).
        self.markers=[self.body128,self.fields.index((o.o+0x12c,4)),self.fields.index((b+0x130,4)),self.fields.index((b+0x134,4))]
        p.write(0x43d061,100,1)  # factory 100% handicap read by 14f2b8
        self.calls=Counter();self.instructions=0

def run(job):
    exe,side,move,fighter=job
    if move.startswith('SLOTSEL'):
        lineup,_,c,mv,sp=SLOT_RUNS[int(move[7:])]
        seq=prefix(lineup,sp)+[[0,0]]*330+[[x,0] if side==0 else [0,x] for x in slot_pads(side,mv)]
        cpu=[c] if c!='none' else []
    elif move.startswith('RAGE'):
        # 'RAGE<opp>:<motion>': a CPU opponent beats the idle fighter into rage while the motion
        # repeats every 150 neutral ticks (rage-gated moves such as Shikuru's hawk assist).
        other,motion=move[4:].split(':');other=int(other)
        seq=prefix((fighter,other) if side==0 else (other,fighter))+[[0,0]]*330;cpu=['p2' if side==0 else 'p1']
        for _ in range(60):
            seq+=[[0,0]]*150
            for x in move_pads(side,motion):seq.append([x,0] if side==0 else [0,x])
    elif move.startswith('RIDE'):
        # 'RIDE<wait>:<m1,m2,..>': mount the hawk (214K), wait, then a riding attack; eight rounds.
        wait,motions=move[4:].split(':');wait=int(wait)
        seq=prefix((fighter,0) if side==0 else (0,fighter))+[[0,0]]*330;cpu=[]
        for _ in range(8):
            for m in motions.split(','):
                for x in move_pads(side,'214K')[:-150]+[0]*wait+move_pads(side,m):seq.append([x,0] if side==0 else [0,x])
    elif move.startswith('CPU'):
        # CPU-vs-CPU after selection: reaches rage-gated moves public input cannot.
        # 'CPU<o>S<s>' selects spirit s (system id) on both wheels; plain 'CPU<o>' keeps the Ken default.
        body,_,sp=move[3:].partition('S');other=int(body);spirits=(int(sp),int(sp)) if sp else None
        seq=prefix((fighter,other) if side==0 else (other,fighter),spirits)+[[0,0]]*12000;cpu=['both']
    else:
        seq=prefix((fighter,0) if side==0 else (0,fighter))+[[0,0]]*330;cpu=[]
        for x in move_pads(side,move):seq.append([x,0] if side==0 else [0,x])
    r=subprocess.run([exe,RES,'1',*cpu],input=''.join(f'{a} {b}\n' for a,b in seq),text=True,capture_output=True)
    if r.returncode:raise RuntimeError((side,move,r.stderr[-300:]))
    src=Original(side,fighter);wrong=[];visits=0;specials=set()
    for line in r.stdout.splitlines():
        if line.startswith('F'):
            v=line.split();t,s=int(v[2+10*side+2]),int(v[2+10*side+3])
            if t==1 and s>=64:specials.add(s)
        if not line.startswith('C'):continue
        v=list(map(int,line.split()[1:]))
        if v[1]!=side:continue
        visits+=1
        bad=src.compare((side,move,v[0]),v[2:])
        if bad:wrong.append(bad)
    return dict(seat=side+1,move=move,visits=visits,specials=sorted(specials),callbacks=dict(src.calls),instructions=src.instructions),wrong

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--fighter',type=int,required=True);n=ap.parse_args().fighter
    lib=BUILD/'libss6-runtime.a';digest=sha256(lib.read_bytes()).hexdigest()
    with tempfile.TemporaryDirectory() as tmp:
        exe=Path(tmp)/'trace';obj=Path(tmp)/'fighter.o';cxx=['c++','-std=c++20','-ffp-contract=off','-O2','-I',ROOT/'src']
        subprocess.run([*cxx,'-DupdateScriptFighterAttack=tracedCast','-c',ROOT/'src/script_fighter.cpp','-o',obj],check=True)
        subprocess.run([*cxx,ROOT/'work/ss6/script_fighter_trace.cpp',obj,lib,'-o',exe],check=True)
        assert n in SCRIPT_STUBS,'validate_script_specials covers ScriptStubs fighters'
        # Every generic probe motion, plus CPU-vs-CPU against each playable fighter.
        jobs=[(exe,s,m,n) for s in (0,1) for m in (*MOTIONS,*(f'CPU{o}' for o in PLAYABLE),*RAGE_MOVES.get(n,()),
                                                   *(f'CPU{o}S{sp}' for sp in range(5) for o in PLAYABLE[::6]))]
        global SLOT_RUNS
        SLOT_RUNS=slot_selection(n)
        jobs+=[(exe,r[1],f'SLOTSEL{i}',n) for i,r in enumerate(SLOT_RUNS)]
        with ThreadPoolExecutor(6) as pool:results=list(pool.map(run,jobs))
    wrong=[w for _,ws in results for w in ws]
    total=Counter()
    for r,_ in results:total.update(r['callbacks']);total['instructions']+=r['instructions']
    seen=sorted({x for r,_ in results for x in r['specials']})
    print('special states reached',seen)
    assert not wrong,(len(wrong),wrong[:6])
    assert digest==sha256(lib.read_bytes()).hexdigest(),'Runtime changed during validation'
    out=ROOT/f'outputs/ss6-feasibility/fighter_{n:02}_special_validation.json'
    out.write_text(json.dumps(dict(status='passed',fighter=n,library_sha256=digest,callbacks=dict(total),special_states=seen,cases=[r for r,_ in results],
        scope='Per-visit original comparison of the attack stub and 163610; contacts and victim rows are exercised natively only.'),indent=2)+'\n')
    print(dict(total))

if __name__=='__main__':main()
