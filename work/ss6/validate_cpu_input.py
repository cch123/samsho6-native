"""Whole Japanese 15d948, including preexisting features and slot lifetimes."""
import random
import struct
import subprocess
import tempfile
from pathlib import Path

from mips_probe import Probe
from validate_dash_motion import ELF, PIN, ROOT, digest

DRIVER=r'''
#include "cpu_input.hpp"
#include <iostream>
int main() {
    unsigned mask,seed;
    int slot,facing,start,count;
    while(std::cin>>mask>>slot>>facing>>start>>count>>seed) {
        ss6::ActorCommandInput owner;
        owner.specialStart=start;owner.specialCount=count;
        auto next=[&] {seed=seed*1664525u+1013904223u;return seed;};
        for(auto& f:owner.sampledFeatures)f=next();
        auto init=[&](auto& s){s.recognized=next();s.cancelAllowed=next();s.progress.buffered=next()&255;};
        for(auto& s:owner.normal)init(s);
        for(auto& s:owner.special)init(s);
        ss6::publishCpuCommand({mask,slot},facing,owner);
        for(auto v:owner.sampledFeatures)std::cout<<v<<' ';
        for(auto& s:owner.normal)std::cout<<s.recognized<<' '<<unsigned(s.progress.buffered)<<' ';
        for(auto& s:owner.special)std::cout<<s.recognized<<' '<<s.cancelAllowed<<' '<<unsigned(s.progress.buffered)<<' ';
        std::cout<<'\n';
    }
}
'''

def initial(p,owner,seed,start,count):
    def next_word():
        nonlocal seed
        seed=(1664525*seed+1013904223)&0xffffffff
        return seed
    struct.pack_into('<171I',p.memory,owner,*(next_word() for _ in range(171)))
    p.write(owner+0x5bc,count,4)
    p.write(owner+0x5c0,start,4)
    for n in range(63):
        special=n>=31;i=n-31 if special else n
        result,cancel,buffer=next_word(),next_word(),next_word()&255
        p.write(owner+(0x328 if special else 0x2ac)+4*i,result,4)
        if special:p.write(owner+0x3a8+4*i,cancel,4)
        p.write(owner+(0x684 if special else 0x502)+6*i+4,buffer,1)

def output(p,owner):
    values=list(struct.unpack_from('<171I',p.memory,owner))
    for i in range(31):
        values.extend((p.read(owner+0x2ac+4*i,4),p.read(owner+0x506+6*i,1)))
    for i in range(32):
        values.extend((p.read(owner+0x328+4*i,4),p.read(owner+0x3a8+4*i,4),p.read(owner+0x688+6*i,1)))
    return values

def main():
    assert digest(ELF)==PIN
    p=Probe(ELF.read_bytes())
    battle,base,body,command=0x1b00000,0x1c00000,0x1c10000,0x1c16000
    p.write(0x4d3d00,battle,4)
    p.write(0x4d3d08,base,4)
    for seat in range(2):
        p.write(battle+0x24c+4*seat,base+0xf2c*seat,4)
        p.write(base+0xf2c*seat,body+0x1000*seat,4)
    rng=random.Random(0x15d948)
    masks=[0,0xffffffff]+[1<<i for i in range(32)]+[rng.getrandbits(32)&~0x1800000 for _ in range(150)]
    rows=[];expected=[]
    for n,mask in enumerate(masks):
        for facing in (0,1):
            for start in (-1,0):
                seat=n%2;slot=rng.randrange(-1,63);count=rng.randrange(33);seed=rng.getrandbits(32)
                actor=base+seat*0xf2c;owner=actor+0x2c4
                p.write(body+0x1000*seat+0x38,facing<<19,4)
                initial(p,owner,seed,start,count)
                p.write(command,mask,4);p.write(command+4,slot,4)
                p.run(0x15d948,[command,owner,seat],limit=15000)
                rows.append((mask,slot,facing,start,count,seed));expected.append(output(p,owner))
    with tempfile.TemporaryDirectory() as tmp:
        driver=Path(tmp)/'probe.cpp';binary=Path(tmp)/'probe'
        driver.write_text(DRIVER)
        subprocess.run(['c++','-std=c++20','-ffp-contract=off','-O2','-I',ROOT/'src',driver,ROOT/'src/cpu_input.cpp',
                        ROOT/'work/ss6/build-native/libss6-runtime.a','-o',binary],check=True)
        result=subprocess.run([binary],input=''.join(' '.join(map(str,row))+'\n' for row in rows),
                              text=True,capture_output=True,check=True)
    outputs=result.stdout.splitlines()
    assert len(outputs)==len(rows)
    for row,line,want in zip(rows,outputs,expected):
        got=list(map(int,line.split()))
        assert got==want,(row,[(i,a,b) for i,(a,b) in enumerate(zip(got,want)) if a!=b][:10])
    print(f'{len(rows)} CPU publications match all 171 features, 63 results, cancel flags and buffers')

if __name__=='__main__':main()
