#!/usr/bin/env python3
"""Compare Mina's attack callbacks (1fb7a8, the 163610 script interpreter and
her continuations) in real, publicly selected fights with SLPS_255.59.

Each native visit is replayed on the original executable starting from the
same actor, body, opponent, camera and Chample words; all of those words are
compared afterwards, together with whether 169810 recovery was reached.
"""
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import tempfile

from validate_selected_combat import BUILD, ROOT
from validate_weapon_handling import setup
from validate_mina_projectiles import pads, MOVES

RES=ROOT/'work/ss6/extracted/resources'
OUT=ROOT/'outputs/ss6-feasibility/mina-special-validation.json'

class Original:
    def __init__(self,side):
        self.src,_=setup(side,24);o=self.src;self.p=p=o.p
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
        target=p.read(o.other,4);self.fields += [(target+0x40,4),(target+0x44,4),(a+0x24c,1)]
        aux=p.read(a+4,4);assert aux,'149008 must create Chample for character 24'
        # setup() reinitializes the pools after 149008, so the original Chample
        # slot is free again; keep its words where no allocation can reuse them.
        p.memory[0x1dd0000:0x1dd0140]=p.memory[aux:aux+0x140];aux=0x1dd0000;p.write(a+4,aux,4)
        self.fields += [(aux+off,4) for off in (0x128,0x12c,0x40,0x44)]+[(a+0x244,4)]
        self.calls=Counter();self.instructions=0
    def compare(self,case,values):
        p=self.p;n=len(self.fields);start,end=values[:n],values[n+1:]
        assert len(start)==len(end)==n,(len(start),len(end),n)
        for (addr,size),v in zip(self.fields,start):p.write(addr,v,size)
        pc=start[6];p.write(self.ctx+8,start[8],4);recover=[]
        _,ins=p.run(pc,[self.ctx],limit=800000,observe=lambda ad:recover.append(1) if ad==0x169810 else None)
        self.instructions+=ins;self.calls[hex(pc)]+=1
        problems=[]
        if bool(recover)!=bool(values[n]):problems.append(('recovery',bool(recover),values[n]))
        problems+=[(i,hex(ad),hex(p.read(ad,size)),hex(v)) for i,((ad,size),v) in enumerate(zip(self.fields,end)) if p.read(ad,size)!=v&((1<<(size*8))-1)]
        return (case,hex(pc),problems) if problems else None

def run(job):
    exe,side,move=job
    seq=pads(side,move)
    r=subprocess.run([exe,RES,'1'],input=''.join(f'{a} {b}\n' for a,b in seq),text=True,capture_output=True)
    if r.returncode:raise RuntimeError((side,move,r.stderr[-300:]))
    src=Original(side);wrong=[];visits=0
    for line in r.stdout.splitlines():
        if not line.startswith('C'):continue
        v=list(map(int,line.split()[1:]))
        if v[1]!=side:continue
        visits+=1
        bad=src.compare((side,move,v[0]),v[2:])
        if bad:wrong.append(bad)
    return dict(seat=side+1,move=move,visits=visits,callbacks=dict(src.calls),instructions=src.instructions),wrong

def main():
    tracked=(BUILD/'libss6-runtime.a',)
    digest=sha256(tracked[0].read_bytes()).hexdigest()
    with tempfile.TemporaryDirectory() as tmp:
        exe=Path(tmp)/'trace';obj=Path(tmp)/'mina.o';cxx=['c++','-std=c++20','-ffp-contract=off','-O2','-I',ROOT/'src']
        subprocess.run([*cxx,'-DupdateMinaAttack=tracedCast','-c',ROOT/'src/mina_special.cpp','-o',obj],check=True)
        subprocess.run([*cxx,ROOT/'work/ss6/mina_special_trace.cpp',obj,tracked[0],'-o',exe],check=True)
        jobs=[(exe,s,m) for s in (0,1) for m in MOVES]
        with ThreadPoolExecutor(6) as pool:results=list(pool.map(run,jobs))
    wrong=[w for _,ws in results for w in ws]
    total=Counter()
    for r,_ in results:total.update(r['callbacks']);total['instructions']+=r['instructions']
    assert not wrong,(len(wrong),wrong[:6])
    assert digest==sha256(tracked[0].read_bytes()).hexdigest(),'Runtime changed during validation'
    OUT.write_text(json.dumps(dict(status='passed',library_sha256=digest,callbacks=dict(total),cases=[r for r,_ in results],
        scope='Per-visit original comparison of 1fb7a8, 163610 and Mina continuations; objects spawned by these callbacks are checked by validate_mina_projectiles.py.'),indent=2)+'\n')
    print(dict(total))

if __name__=='__main__':main()
