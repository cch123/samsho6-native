#!/usr/bin/env python3
"""Run the full local-VS item scheduler from the Japanese executable for each test input."""
from collections import Counter
import json
from pathlib import Path
import struct
import subprocess
import tempfile

from mips_probe import Probe, signed
from validate_dash_motion import ASSETS, ELF, PIN, ROOT, digest

LIB = ROOT/'work/ss6/build-native/libss6-runtime.a'
REPORT = ROOT/'outputs/ss6-feasibility/stage-item-schedule-validation.json'
DRIVER = r'''
#include "battle_round.hpp"
#include <iostream>
int main(int,char** argv) {
    ss6::StageItemSchedule schedule(argv[1]);
    ss6::BattleRoundState b{};
    b.entry.tasks.initializeOwners();b.entry.tasks.initializeTasks();b.entry.tasks.initializeObjects();
    auto task=b.entry.tasks.registerObjectTask(b.objectTasks,0x1396,0x1415a8);
    auto& object=b.entry.tasks.objects.at(b.entry.tasks.tasks.at(task-1)[7]-1);
    object[0xcc/4]=5;
    int busy,act;
    ss6::StageEventPlayers players{};
    while(std::cin>>b.stageItemsOption4c3828>>busy>>act>>b.matchEnd.metadataStage04>>b.timers.values[1]
          >>b.timers.values[3]>>b.timers.delta>>b.lastItemSecond>>b.random.mode>>b.random.gameSeed
          >>b.random.librarySeed>>players.x0>>players.x1>>b.camera.projectionX) {
        b.stageItems.clear();
        if(busy)b.stageItems.start(1,320,0,b.camera);
        b.objectTasks[0]=act==-1?0:task;
        object[0x24/4]=uint32_t(act);
        auto drop=schedule.next(b,players);
        std::cout<<(drop?drop->kind:-1)<<' '<<(drop?drop->targetX:0)<<' '<<(drop?drop->fromRight:0)
                 <<' '<<b.timers.values[1]<<' '<<b.timers.values[3]<<' '<<b.lastItemSecond
                 <<' '<<b.random.gameSeed<<' '<<b.random.librarySeed<<'\n';
    }
}
'''

def cases():
    seeds=(1,7,19,29,163,947,821421,0xa1234567)
    seconds=(ASSETS/'stage_item_schedule.bin').read_bytes()[0x170:]
    def row(opt,busy,act,stage,timer,cooldown,rate,last,mode,seed):
        return opt,busy,act,stage,timer,cooldown,rate,last,mode,seed,0x1234567800000000+seed,-57.75,346.25,331.75
    for stage in range(12):
        for sec in seconds:
            for mode in (0,1):
                for seed in seeds:
                    yield row(1,0,-1,stage,(60-sec)*0x5a00+137,0,256,-1,mode,seed)
    # Includes elapsed-time wrap during a long or unlimited match, equality
    # with the previous tick, expiring cooldown, and the bomb's three blocking ACTs.
    for stage in (0,11,12,14):
        for elapsed in (0,1,61,89,99):
            for opt,busy,act,cooldown,rate,last in (
                    (0,0,-1,128,256,3),(1,1,-1,0,256,3),(1,0,76,0,256,3),
                    (1,0,78,0,128,3),(1,0,133,0,0,3),(1,0,55,0,256,3),
                    (1,0,-1,1,256,3),(1,0,-1,256,128,3),(1,0,-1,0,0,60-elapsed)):
                yield row(opt,busy,act,stage,elapsed*0x5a00,cooldown,rate,last,1,7)

def main():
    assert digest(ELF)==PIN
    inputs=list(cases());p=Probe(ELF.read_bytes(),finite_model=True)
    b,a,o,task,obj=0x1b00000,0x1c00000,0x1d00000,0x1e00000,0x1e01000
    libc=p.read(0x5d1bf8,4)+0xa8
    def word(addr,w):p.write(addr,w,4)
    for addr,w in ((0x4d3d00,b),(0x4d3d08,a),(a,o),(a+0xf2c,o+0x1000),
                   (b+0x24c,a),(b+0x250,a+0xf2c),(0x4c3808,3),(task+28,obj),(obj+0xcc,5)):
        word(addr,w)
    struct.pack_into('<f',p.memory,0x4a2a60,-400.)
    counts=Counter();sides=set();anchors=set();cooldowns=set();instructions=0
    with tempfile.TemporaryDirectory() as tmp:
        src=Path(tmp)/'probe.cpp';exe=Path(tmp)/'probe';src.write_text(DRIVER)
        subprocess.run(['c++','-std=c++20','-ffp-contract=off','-O2','-I',ROOT/'src',src,LIB,'-o',exe],check=True)
        raw=subprocess.run([exe,ASSETS],input=''.join(' '.join(map(str,row))+'\n' for row in inputs),
                           capture_output=True,check=True,text=True)
    for i,(row,line) in enumerate(zip(inputs,raw.stdout.splitlines(),strict=True)):
        opt,busy,act,stage,timer,cooldown,rate,last,mode,seed,libseed,x0,x1,camera=row
        for address,w in ((0x4c3828,opt),(0x132c218,busy),(b+0x14c,0 if act==-1 else task),
                          (obj+0x24,act),(b+0x10,stage),(b+0x118,timer),(b+0x120,cooldown),(b+0x110,rate),
                          (0x12d2304,last),(0x443150,mode),(0x3d2e80,seed),(0x132c4b8,-1)):
            word(address,w)
        for addr,value in ((o+0x40,x0),(o+0x1040,x1),(0x4a2a58,camera)):
            struct.pack_into('<f',p.memory,addr,value)
        p.write(libc,libseed,8)
        _,n=p.run(0x144f40,[b]);instructions+=n
        kind=signed(p.read(0x132c4b8,4),32)
        x=int(struct.unpack_from('<f',p.memory,0x132c4a4)[0]) if kind!=-1 else 0
        right=(p.read(0x132c220+0x38,4)>>19)&1 if kind!=-1 else 0
        want=[kind,x,right,*[signed(p.read(at,4),32) for at in (b+0x118,b+0x120,0x12d2304)],
              p.read(0x3d2e80,4),p.read(libc,8)]
        got=list(map(int,line.split()))
        assert got==want,(i,row,got,want)
        counts[kind]+=1
        if kind!=-1:sides.add(right);anchors.add(x);cooldowns.add(want[4]//256)
    assert sides=={0,1} and len(anchors)==4 and len(cooldowns)==8
    record=dict(status='passed',cases=len(inputs),instructions=instructions,elf_sha256=PIN,runtime_sha256=digest(LIB),
                drops=dict(sorted(counts.items())),anchor_x=sorted(anchors),cooldown_ticks=sorted(cooldowns),
                scope='Original 144f40 and all callees including 1b5800. Both random streams, stage rows 0 through 11, all trigger times, camera and two actor anchors, item option, elapsed-time wrap, busy/empty/occupied bombs and cooldown boundary. Compares each drop, side, target, timers, time latch and RNG states.')
    REPORT.write_text(json.dumps(record,indent=2)+'\n')
    print(len(inputs),'cases;',instructions,'original instructions;',sorted(counts.items()))

if __name__=='__main__':main()

