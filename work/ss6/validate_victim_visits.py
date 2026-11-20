#!/usr/bin/env python3
"""Replay every live table-B call of a source fighter on SLPS_255.59.

Each native call of updateVictimScript (the 4e97a8 stub entry and every
165cc0 visit of a multi-row script) recorded in publicly selected matches
(CPU-vs-CPU against every playable fighter in both seats, plus the source's
special inputs) is replayed on the original from the same victim and
attacker actor/body words and battle words; all of them are compared
afterwards, together with whether 169810 was reached.
Usage: validate_victim_visits.py --source 18
"""
import argparse
import os
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import tempfile

from validate_selected_combat import BUILD, ROOT, prefix
from validate_weapon_handling import setup
from probe_fighter_gaps import pads as move_pads, PLAYABLE, MOTIONS

RES=ROOT/'work/ss6/extracted/resources'
ACTOR=[(0x194,4),(0x23c,4),(0x244,4),(0x248,4),(0x19a,1),(0x18c,4),(0x190,2),(0x192,2),(0xa3c,4),(0xa30,4),(0xa38,4),(0x254,1),
       *[(0x260+4*i,4) for i in range(7)],*[(0x27c+4*i,4) for i in range(4)],*[(0x28c+4*i,4) for i in range(13)],
       *[(0x1b0+4*i,4) for i in range(35)],(0x1ac,4),*[(o,4) for o in (0x120,0x124,0x128,0x134,0x138)],(0xf1c,1),(0xf1d,1),(0xf15,1),(0xf16,1),(0xa50,4)]
BODY=[(0x24,4),(0x28,4),(0x38,4),(0x104,4),(0x108,4),(0xc0,4),(0x3c,4),(0xfe,2),(0x124,4),(0x128,4),(0x12c,4),(0x130,4),(0x134,4),
      (0x40,4),(0x44,4),*[(0x4c+4*i,4) for i in range(6)],(0xec,4),(0xf0,4),(0xb0,4),(0x30,4)]
PAUSE_COUNT,PAUSE_DELAY=0x123a0ec,0x123a0e8
SCENE_WORDS=(0x24,0x28,0x38,0x40,0x44,0xb0,0xc0,0xc4,0x104,0x108,0x8c,0x30)
# A stale body handle can name a reallocated object; compare only the character's own scene objects.
# Scene slots holding handles (0..3 victim 128..134, 4..7 attacker); Sugoroku's attacker 128/12c are its curtain fade, 130 the curtain.
SCENE_SLOTS={33:(6,)}
SCENE_ACTS={5:range(0x261,0x26a),33:(0x243,),11:(0x24a,0x24c,0x222),31:(0x25b,),35:range(0x230,0x234),39:range(0x21f,0x223)}

class Original:
    def __init__(self,seat,victim,source,own=False):
        self.src,_=setup(seat,victim);o=self.src;self.p=p=o.p
        stage=p.run(0x140040)[0];self.ctx=0x1dc0000
        p.write(0x169810,0x03e00008,4);p.write(0x169814,0,4)
        p.write(0x43d061,100,1)  # factory 100% handicap read by 14f2b8 (script damage)
        self.v,self.a=o.a,o.other
        self.vb,self.ab=p.read(self.v,4),p.read(self.a,4)
        p.write(self.a+0xa10,source,4);p.write(self.a+0xa14,source,4);p.write(self.a+0x114,source,4)
        b=o.b
        self.fields=[(self.v+off,n) for off,n in ACTOR]+[(self.vb+off,n) for off,n in BODY]
        self.fields+=[(self.a+off,n) for off,n in ACTOR]+[(self.ab+off,n) for off,n in BODY]
        self.fields+=[(b+0x128,4),(b+0x12c,4),(PAUSE_COUNT,4),(PAUSE_DELAY,4),(b+0x78,4),(b+0x7c,4),(b+0x80,4)]
        for i in range(4):self.fields+=[(b+0x84+8*i,1),(b+0x88+8*i,4)]
        self.fields+=[(b+0x114,4),(b+0x13c,4),(b+0x08,4)]  # round timer, time option, field 08 (14a8d0's time-out test)
        self.fields+=[(self.a+0x2c4+4*n,4) for n in range(58,62)]+[(stage+0x10,4),(stage+0x14,4),(stage+4,4),(self.v+0x10c,4),(self.a+0x10c,4)]+[(self.a+0x5ec+0x18+4*n,4) for n in range(3)]+[(self.v+0x2c4+4*n,4) for n in (10,63,64)]+[(self.a+0x634,4)]
        # The delivering object: native handles become a fixture object and,
        # when registered, a fixture task in its owner's registry slot 0.
        self.child,self.ctask=0x1de9000,0x1de8000;p.write(self.ctask+0x1c,self.child,4);p.write(self.child+4,self.ctask,4)
        self.registries=[b+0x29c+0x108*s for s in (0,1)]
        self.extra=len(self.fields)
        self.fields+=[(0x1de7000,4),(0x1de7004,4)]+[(self.child+o,4) for o in (0x0c,0xcc,0x38,0x40,0x44,0x104,0x108,0xdc,0xe4,0xe8,0xc0,0x24,0x28,0x14)]
        self.fields+=[(self.ctask,4)]  # the child's task callback word
        # The victim's body+134 object (Genjuro's 0x1e rows): a second fixture object.
        self.kept=0x1de9800;self.fields+=[(self.kept+off,4) for off in (0x24,0xc4,0x108)]
        self.keptAt=len(self.fields)-3
        self.body124=[i for i,(ad,_) in enumerate(self.fields) if ad==self.vb+0x124][0]
        # registry28c[10]: the adopted child (165a78 flag 0x40)
        self.adopted=[i for i,(ad,_) in enumerate(self.fields) if ad==self.v+0x28c+40][0]
        self.body134=[i for i,(ad,_) in enumerate(self.fields) if ad==self.vb+0x134][0]
        # Kyoshiro's scene objects behind body+128..134 (source 5 only).
        # Kyoshiro's scene: his victims' visits, and his own 174158 visits (own=True).
        self.sceneSource=victim if own else source;self.source=source
        self.scene=self.sceneSource in SCENE_ACTS;self.seat=seat
        self.sceneSlots=[i for i,(ad,_) in enumerate(self.fields) if ad in [base+o for base in (self.vb,self.ab) for o in (0x128,0x12c,0x130,0x134)]]
        self.calls=Counter();self.instructions=0
    def compare(self,case,pc,values):
        p=self.p;n=len(self.fields);values=list(values);W=len(SCENE_WORDS)+1;SN=8*W
        sstart=values[n:n+SN];send=values[2*n+1+SN:]
        values=values[:n]+values[n+SN:2*n+1+SN]
        rawChild=(values[self.body124],values[n+1+self.body124])  # native handles before renaming
        for base in (0,n+1):
            if values[base+self.body124]:values[base+self.body124]=self.child
            if values[base+self.adopted]:values[base+self.adopted]=self.child
        start,end=values[:n],values[n+1:]
        assert len(start)==len(end)==n,(len(start),len(end),n)
        if start[self.body134]==0x80000000:start[self.body134]=self.kept
        handles={}
        for reg in self.registries:
            for slot in range(1,9):p.write(reg+4*slot,0,4)
        if self.scene:
            # Fixture objects for every live handle, in slot order (v 128..134, a 128..134).
            for j in (4,5,6,7,0,1,2,3):  # the attacker's slots first: only they are registered
                i=self.sceneSlots[j];h=start[i]
                if not h or j not in SCENE_SLOTS.get(self.sceneSource,range(8)):continue
                if j<4 and h not in handles:continue  # victim words matter only as copies of the attacker's handles
                if h not in handles:
                    k=len(handles)
                    if h in rawChild:handles[h]=self.child  # the delivering object is also a scene object
                    else:
                        addr=0x1dea000+0x200*k;handles[h]=addr
                        p.memory[addr:addr+0x140]=bytes(0x140)
                        # Every scene object is registered with its owner (the attacker), so 168400 freezes it.
                        task=0x1deb000+0x40*k;p.write(task+0x1c,addr,4);p.write(addr+4,task,4)
                        if j>=4 and sstart[W*j+W-1] and sstart[W*j+7] in SCENE_ACTS.get(self.sceneSource,()):p.write(self.registries[1-self.seat]+4*(1+k),task,4)
                    for off,val in zip(SCENE_WORDS,sstart[W*j:W*j+W-1]):p.write(handles[h]+off,val,4)
                start[i]=handles[h]
        for (addr,size),v in zip(self.fields,start):p.write(addr,v,size)
        present,registered,owner=start[self.extra],start[self.extra+1],start[self.extra+2]
        for reg in self.registries:
            if p.read(reg,4)==self.ctask:p.write(reg,0,4)
        if (present or self.source==4) and registered and owner<2:p.write(self.registries[owner],self.ctask,4)
        if self.source==4:p.write(self.a+4,self.child,4)  # Poppy (actor+4) is the child rows 0x19/0x1a adopt
        p.write(self.ctx,self.v,4);p.write(self.ctx+4,self.a,4);p.write(self.ctx+8,start[ACTOR.index((0x260+8,4))],4)
        recover=[];attackerRecover=[]
        def observe(ad):
            if ad!=0x169810:return
            # 169810 is stubbed; a call for the attacker (Iroha's 200710 recovers A) is not the victim's recovery.
            if p.read(p.registers[4],4)==self.a:attackerRecover.append(1)
            else:recover.append(1)
        _,ins=p.run(pc,[self.ctx],limit=800000,observe=observe)
        self.instructions+=ins;self.calls[hex(pc)]+=1
        # The presence pseudo-field follows the original's body +124 (end ops 23..26 detach the child).
        p.write(0x1de7000,int(p.read(self.vb+0x124,4)!=0),4)
        fields=list(self.fields)
        if end[self.body134]==0x80000000:
            kept=p.read(self.vb+0x134,4)
            end[self.body134]=kept
            if kept and kept!=self.kept:fields[self.keptAt:self.keptAt+3]=[(kept+off,4) for off in (0x24,0xc4,0x108)]
        if self.scene:
            back={a:h for h,a in handles.items()}
            created={}
            for j,i in enumerate(self.sceneSlots):
                if j not in SCENE_SLOTS.get(self.sceneSource,range(8)):continue
                ad=self.fields[i][0];v=p.read(ad,4)
                if v in back:p.write(ad,back[v],4)
                elif v and end[i] and 0x100000<=v<0x2000000:
                    # An object the visit created: the original's new pointer stands for the native handle.
                    created[j]=v;p.write(ad,end[i],4)
        problems=[]
        if self.scene:
            for j,i in enumerate(self.sceneSlots):
                if j not in SCENE_SLOTS.get(self.sceneSource,range(8)):continue
                h=end[i]
                reused={end[self.sceneSlots[c]] for c in created}
                # A stale word whose handle the visit reallocated keeps its old (fixture) value in the original.
                own=sstart[W*j+7] in SCENE_ACTS.get(self.sceneSource,()) # c4 at the start: still that scene object
                if j in created or (h in handles and h not in reused and own):
                    base=created[j] if j in created else handles[h]
                    got=[p.read(base+off,4) for off in SCENE_WORDS]
                    if got!=send[W*j:W*j+W-1]:problems.append(('scene',j,'v194',hex(start[0]),'a244',hex(start[len(ACTOR)+len(BODY)+2]),'a194',hex(start[len(ACTOR)+len(BODY)]),[(hex(o),hex(x),hex(y)) for o,x,y in zip(SCENE_WORDS,got,send[W*j:W*j+W-1]) if x!=y]))
        if bool(recover)!=bool(values[n]):problems.append(('recovery',bool(recover),values[n]))
        if attackerRecover:  # the native ran the real 169810 on the attacker: its pending request is not comparable
            skip={self.a+0x190,self.a+0x192}
            for i,(ad,size) in enumerate(fields):
                if ad in skip:end[i]=p.read(ad,size)
        problems+=[(i,hex(ad),hex(p.read(ad,size)),hex(v)) for i,((ad,size),v) in enumerate(zip(fields,end))
                   if p.read(ad,size)!=v&((1<<(size*8))-1)]
        if problems and os.environ.get('SS6_DEBUG_V'):problems.append(('v38start',hex(start[81]),'v194',hex(start[0]),'a23c',hex(start[len(ACTOR)+len(BODY)+1]),'child',hex(start[self.body124]),'presence',start[self.extra]))
        return (case,hex(pc),problems) if problems else None

# Spirit lineups found by probe_fighter_gaps.py --spirits (seat of the source, opponent, spirits).
SPIRIT_CASES={4:((1,21,(0,0)),(0,12,(1,1)),(1,12,(1,1)),(1,21,(4,4)),(1,40,(4,4))),
              48:((0,21,(3,3)),(1,15,(1,1)),(0,24,(3,3)))}

def run(job):
    exe,seat,other,move,source=job[:5];spirits=job[5] if len(job)>5 else None
    lineup=(source,other) if seat==0 else (other,source)
    if move:
        seq=prefix(lineup)+[[0,0]]*330;cpu=[]
        for x in move_pads(seat,move):seq.append([x,0] if seat==0 else [0,x])
    else:seq=prefix(lineup,spirits)+[[0,0]]*12000;cpu=['both']
    r=subprocess.run([exe,RES,*cpu],input=''.join(f'{a} {b}\n' for a,b in seq),text=True,capture_output=True)
    if r.returncode:raise RuntimeError((lineup,move,r.stderr[-300:]))
    wrong=[];originals={};visits=Counter()
    for line in r.stdout.splitlines():
        if not line.startswith(('V','L')):continue
        v=list(map(int,line.split()[1:]))
        victim_seat,pc=v[1],v[2]
        if line[0]=='L':
            # The source's own 174158 landing (end ops 11..22 on its slot), run
            # with the visiting actor in the cb[0] role.
            if victim_seat!=seat:continue
            key=('L',victim_seat)
            if key not in originals:originals[key]=Original(victim_seat,source,lineup[1-victim_seat],own=True)
        else:
            if victim_seat==seat:continue  # only victims of the source fighter
            key=victim_seat
            if key not in originals:originals[key]=Original(victim_seat,lineup[victim_seat],source)
        visits[hex(pc)]+=1
        bad=originals[key].compare((lineup,move,v[0]),pc,v[3:])
        if bad:wrong.append(bad)
    ins=sum(o.instructions for o in originals.values())
    return dict(lineup=lineup,move=move,visits=dict(visits),instructions=ins),wrong

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--source',type=int,required=True);n=ap.parse_args().source
    lib=BUILD/'libss6-runtime.a';digest=sha256(lib.read_bytes()).hexdigest()
    with tempfile.TemporaryDirectory() as tmp:
        exe=Path(tmp)/'trace';obj=Path(tmp)/'victim.o';cxx=['c++','-std=c++20','-ffp-contract=off','-O2','-I',ROOT/'src']
        subprocess.run([*cxx,'-DupdateVictimScript=tracedVictim','-DupdateLanding174158=tracedLanding','-DupdateLifeHold=tracedLifeHold','-c',ROOT/'src/victim_script.cpp','-o',obj],check=True)
        subprocess.run([*cxx,ROOT/'work/ss6/victim_script_trace.cpp',obj,lib,'-o',exe],check=True)
        jobs=[(exe,s,o,None,n) for s in (0,1) for o in PLAYABLE]
        jobs+=[(exe,s,0,m,n) for s in (0,1) for m in MOTIONS if m.startswith('W')]
        # The default sweep plays Ken (the wheel's first cursor); also play Rage/Shin/Zan/Ten/Zero
        # against a fixed opponent sample, both seats with the same spirit.
        jobs+=[(exe,s,o,None,n,(sp,sp)) for sp in range(5) for s in (0,1) for o in PLAYABLE[::6]]
        jobs+=[(exe,s,o,None,n,sp) for s,o,sp in SPIRIT_CASES.get(n,())]
        with ThreadPoolExecutor(6) as pool:results=list(pool.map(run,jobs))
    wrong=[w for _,ws in results for w in ws]
    total=Counter()
    for r,_ in results:total.update(r['visits']);total['instructions']+=r['instructions']
    assert not wrong,(len(wrong),wrong[:4])
    assert digest==sha256(lib.read_bytes()).hexdigest(),'Runtime changed during validation'
    out=ROOT/f'outputs/ss6-feasibility/victim_visits_{n:02}_validation.json'
    out.write_text(json.dumps(dict(status='passed',source=n,library_sha256=digest,calls=dict(total),cases=[r for r,_ in results],
        scope='Every live table-B call (stub entry and 165cc0 visits) of this source, replayed on the original with both fighters and battle words.'),indent=2)+'\n')
    print(dict(total))

if __name__=='__main__':main()
