#!/usr/bin/env python3
"""Compare the original per-object completion check 147558 with the native objectCompletion.

Fixtures: object kinds 2..7 (kind 3 = companions such as Galford's Poppy or Mina's Chample, which an
end op 25 lends to a throw victim and 147558 returns to their own task), every combination of the
108 deletion flags 0x1000/0x2000/0x4000/0x8000, ACT ended / still pending, y above, at (+0/-0) and
below the floor, and owner state tables 0..2 (the 0x8000 hit deletion via 1500a8). Compared: object
words 108/128/12c and the task callback word.
"""
from hashlib import sha256
import itertools
import json
import struct
import subprocess
import tempfile
from pathlib import Path

from character_tiles_oracle import ROOT,ASSETS,fixture,bits
from validate_mamahaha import BATTLE,ACTORS,TASK
from extract_collision_tables import SOURCE_HASH

OBJECT=0xb10000
DRIVER=r'''
#include "object_frame.hpp"
#include "tagged_tasks.hpp"
#include <iostream>
using namespace ss6;
int main() {
    TaggedTaskPools pools;pools.initializeTasks();
    GaugeState gauges{};uint32_t jump=0;
    uint32_t kind,f108,c0,f104,y,table,handler,t0;
    while(std::cin>>kind>>f108>>c0>>f104>>y>>table>>handler>>t0) {
        AuxiliaryFrame frame{gauges,jump};
        AuxiliaryObject owner{};frame.owners[0].body=&owner;frame.owners[0].effectiveTable=int32_t(table);
        AuxiliaryObject o{};o[1]=1;o[2]=handler;o[0xcc/4]=kind;o[0x108/4]=f108;o[0xc0/4]=c0;o[0x104/4]=f104;
        o[0x44/4]=y;o[0x118/4]=1;o[0x128/4]=7;o[0x12c/4]=9;pools.tasks.at(0)[0]=t0;
        objectCompletion(o,frame,pools);
        std::cout<<o[0x108/4]<<' '<<o[0x128/4]<<' '<<o[0x12c/4]<<' '<<pools.tasks.at(0)[0]<<'\n';
    }
}
'''

def main():
    p=fixture((4,4,51));p.write(0x4d3d00,BATTLE,4);p.write(0x4d3d08,ACTORS,4)
    assert sha256((ASSETS.parent/'SLPS_255.59').read_bytes()).hexdigest()==SOURCE_HASH
    actor=ACTORS
    cases=[];expected=[];instructions=0
    flagsets=[a|b|c|d for a in (0,0x1000) for b in (0,0x2000) for c in (0,0x4000) for d in (0,0x8000)]
    ys=(bits(5.0),0,0x80000000,bits(-1.0),bits(-0.5))
    for kind,f108,c0,f104,y,table in itertools.product((2,3,4,5,6,7),flagsets,(0,1),(0,1),ys,(0,1,2)):
        handler=0x1efe78;t0=0x147540
        f108|=0x40000
        o=[0]*80;o[1]=TASK;o[2]=handler;o[0xcc//4]=kind;o[0x108//4]=f108;o[0xc0//4]=c0;o[0x104//4]=f104
        o[0x44//4]=y;o[0x118//4]=actor;o[0x128//4]=7;o[0x12c//4]=9
        p.memory[OBJECT:OBJECT+320]=struct.pack('<80I',*o);p.write(TASK,t0,4)
        p.write(actor+0x194,table,4);p.write(actor+0x23c,0,4)
        _,n=p.run(0x147558,[OBJECT],limit=20000);instructions+=n
        expected.append([p.read(OBJECT+0x108,4),p.read(OBJECT+0x128,4),p.read(OBJECT+0x12c,4),p.read(TASK,4)])
        cases.append((kind,hex(f108),c0,f104,hex(y),table,handler,t0))
    with tempfile.TemporaryDirectory() as td:
        src=Path(td)/'c.cpp';exe=Path(td)/'c';src.write_text(DRIVER)
        subprocess.run(['c++','-std=c++20','-ffp-contract=off','-O2','-I',ROOT/'src',src,ROOT/'work/ss6/build-native/libss6-runtime.a','-o',exe],check=True)
        lines='\n'.join(' '.join(str(int(x,16) if isinstance(x,str) else x) for x in c) for c in cases)+'\n'
        got=subprocess.check_output([exe],input=lines,text=True).splitlines()
    wrong=[(c,list(map(int,g.split())),e) for c,g,e in zip(cases,got,expected,strict=True) if list(map(int,g.split()))!=e]
    assert not wrong,(len(wrong),wrong[:8])
    report=dict(status='passed',source=SOURCE_HASH,cases=len(cases),ee_instructions=instructions,
                scope='Whole original 147558 (debug prints through buffered libc) on object fixtures: kinds 2..7, flags 1000/2000/4000/8000, ACT end, y sign including -0.0, owner table 0..2.')
    (ROOT/'outputs/ss6-feasibility/object-completion-validation.json').write_text(json.dumps(report,indent=2)+'\n')
    print(report['cases'],'cases passed')

if __name__=='__main__':main()
