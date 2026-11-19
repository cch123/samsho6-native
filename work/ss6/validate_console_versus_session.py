#!/usr/bin/env python3
"""Match-entry data and RNG for SLPS_255.59 console versus and CONTINUE."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import random
import subprocess
import tempfile

from extract_collision_tables import SOURCE_HASH
from mips_probe import Probe
from round_entry_oracle import ROOT, buffered_stdout

ELF=ROOT/'work/ss6/extracted/SLPS_255.59'
G,SELECT,STAGE,OPTIONS=0x4c3808,0x456890,0x4c8d80,0x43d058
BATTLE,ACTORS,PARAMS,OBJECTS=0x1710000,0x1720000,0x1730000,0x1740000
COMMON_AI,CHARACTER_AI=0x1760000,0x1850000
STACK,RET=0x1fff000,0x1ffff00
DRIVER=r'''
#include "console_versus_session.hpp"
#include <iostream>
int main() {
    ss6::GameRandom r;
    int selection;
    while(std::cin>>r.mode>>r.gameSeed>>r.librarySeed>>selection) {
        const int stage=ss6::selectConsoleVersusStage(r,selection);
        std::cout<<stage<<' '<<r.gameSeed<<' '<<r.librarySeed<<'\n';
    }
}
'''

def fixture():
    data=ELF.read_bytes()
    assert hashlib.sha256(data).hexdigest()==SOURCE_HASH
    p=Probe(data,finite_model=True)
    buffered_stdout(p)
    for slot,value in [(0x4d3d00,BATTLE),(0x4d3d04,PARAMS),(0x4d3d08,ACTORS),
                       (0x4d3d0c,OBJECTS),(0x4d3d10,COMMON_AI),(0x4d3d14,CHARACTER_AI)]:
        p.write(slot,value,4)
    p.write(G,3,4)
    p.write(G+0xa0,2,4)
    return p

def factory_options(p):
    # Both the system-data factory initializer and the OPTIONS -> DEFAULT
    # menu action set the same two values. Poison prior settings first.
    # The options screen copies the saved option block. A fresh system file
    # initializes both Zero reserve percentages in 14f4a0 before that copy.
    for seat in range(2):p.write(OPTIONS+0x12+3*seat,0xee,1)
    p.run(0x1113e8,[OPTIONS])
    assert [p.run(0x14f360,[seat])[0] for seat in range(2)]==[20,20]
    for addr,args in [(0x1113e8,[OPTIONS]),(0x1d0840,[0])]:
        for n in (5,8):p.write(OPTIONS+n,0xee,1)
        p.run(addr,args,limit=200000)
        assert (p.read(OPTIONS+5,1),p.read(OPTIONS+8,1))==(0,2)
        p.run(0x1116d8)
        assert [p.read(SELECT+0x20+0x30*i,4) for i in range(2)]==[2,2]

def prepare_entry(p,selected,mode,game,lib):
    p.write(0x443150,mode,4)
    p.write(0x3d2e80,game,4)
    p.write(p.read(0x5d1bf8,4)+0xa8,lib,8)
    p.write(STAGE,selected,4)
    p.write(G+4,0xee,4)
    calls=Counter()
    def observe(pc):
        if pc in (0x316b90,0x112300,0x112290):
            calls[pc]+=1
            if pc==0x112300:calls[p.registers[31]]+=1
    # These are the complete RNG-consuming functions preceding 13fd80.
    # Run the real effects and candidate builders; their rejection loops
    # can vary the number of draws even with the exact same pinned stage.
    for entry in (0x1040a0,0x17f5a0,0x180510,0x17ac98):
        p.run(entry,limit=300000,observe=observe)
    # Start after 1398fc's development-console print with its real saved
    # registers. All branches and callees through the return run unmodified.
    p.put(16,0x4c0000)
    p.put(17,G)
    p.put(20,PARAMS)
    p.write(STACK+0x48,RET,8)
    p.run(0x139904,limit=200000,observe=observe)
    stage=p.read(PARAMS+4,4)
    assert stage==p.read(G+4,4)
    return (stage,p.read(0x3d2e80,4),p.read(p.read(0x5d1bf8,4)+0xa8,8)),calls

def actor_setup(p):
    # Real resident AI slots avoid issuing an optical file request inside
    # 158380. First 13fd80 is the battle runtime's next entry boundary.
    for i in range(2):
        p.write(0x4568f0+i*4,p.read(PARAMS+0x10+i*4,4),4)
        p.write(CHARACTER_AI+i*0x4c4c,1,4)
        p.write(CHARACTER_AI+i*0x4c4c+4,p.read(PARAMS+0x10+i*4,4),4)
    p.put(21,1)
    rng=[]
    p.run(0x13fa38,stop_before=[0x13fd80],limit=500000,
          observe=lambda pc:rng.append(pc) if pc in (0x316b90,0x112300,0x112290) else None)
    assert not rng
    for i in range(2):
        a=ACTORS+i*0xf2c
        assert p.read(a+0xa10,4)==p.read(SELECT+i*0x30,4)
        assert p.read(a+0xa28,4)==p.read(SELECT+i*0x30+4,4)
        assert p.read(a+0x10c,4)==p.read(SELECT+i*0x30+12,4)
        assert p.read(a+0xa20,4)==0 and p.read(a+0xa24,4)==i
        assert p.read(BATTLE+0x280+i*0x108,4)==p.read(SELECT+i*0x30+0x20,4)
    assert all(p.read(BATTLE+n,4)==0xffffffff for n in (0,4,8,12))
    assert p.read(BATTLE+16,4)==p.read(STAGE,4) and p.read(BATTLE+0x18,4)==0
    raw=p.read(OPTIONS+5,1)
    assert p.read(BATTLE+0x13c,4)==(raw if raw<2 else 3)

def transition_checks(p):
    # Stop on entry to the real transition queue, before touching its task
    # pool. Both the pending selector and confirmed-YES branch run here.
    for choice,dialog,target in [(0,3,0x128008),(1,0,0x139760),(2,4,0x127940)]:
        for pos,val in [(0,choice),(4,dialog),(12,0)]:p.write(0x582fb8+pos,val,4)
        p.run(0x1db418,stop_before=[0x1252f0])
        assert p.registers[4:8]==[2,0,0x1db2e0,target]
    # After battle task teardown returns, CONTINUE touches only +a4.
    p.write(0x582fbc,2,4)
    old=bytes(p.memory[G-16:G+0xa8])
    p.write(STACK+8,RET,8)
    p.run(0x1db2f4)
    assert p.memory[G-16:G+0xa4]==old[:-4] and p.read(G+0xa4,4)==1
    # All shared pad driver fields survive clearing the battle's local
    # input-history ring. A held confirm does not create another edge.
    pad=0x1237cc8
    p.memory[pad:pad+24]=bytes(range(24))
    p.memory[0x123a100:0x123a168]=bytes([255])*0x68
    p.run(0x13a160)
    assert not any(p.memory[0x123a100:0x123a168])
    assert p.memory[pad:pad+24]==bytes(range(24))

def start_complete_fight(game,lib):
    p=fixture()
    factory_options(p)
    prepare_entry(p,0,0,game,lib)
    assets=ELF.parent/'resources'
    p.run(0x112570)
    p.run(0x11e290,limit=200000)
    for slot,resource in enumerate((0,0,51)):
        for name,base in [('aid',0x46a9b0+slot*0x1800),('act',0x1b00000+slot*0x80000)]:
            data=(assets/f'{name}_{resource:02}.bin').read_bytes()
            p.memory[base:base+len(data)]=data
            if name=='act':p.write(0x4751b0+slot*4,base,4)
        p.write(0x46a9a0+slot*4,resource,4)
    actor_setup(p)
    p.write(0x345188,0,4)
    p.run(0x13fd80,limit=600000)
    assert [p.read(BATTLE+n,4) for n in (0,4,0x8,0x18,0x114,0x11c)]==[1,0xffffffff,0xffffffff,0,60*90*256,60*256]
    assert [p.read(ACTORS+i*0xf2c+0xa30,4) for i in range(2)]==[200,200]
    return p.read(0x3d2e80,4),p.read(p.read(0x5d1bf8,4)+0xa8,8)

def live_replay():
    exe=ROOT/'work/ss6/build-native/ss6-match-replay'
    assets=ELF.parent/'resources'
    def run(rows,*args):
        out=subprocess.run([exe,assets,*args],input='\n'.join(rows)+'\n',text=True,capture_output=True,check=True)
        return [s.split() for s in out.stdout.splitlines()]
    # Keep the confirming heavy button held through the entire black fade.
    # The second rematch accepts the other controller. Neither gets a new
    # press just because a fresh fight object took over.
    rows=['0 0 0']
    for side in range(2):
        rows.extend(['20000 0 0','1 32 0' if side==0 else '1 0 32','1 0 0',
                     '1 1024 0' if side==0 else '1 0 1024'])
        rows+=['1 1024 0' if side==0 else '1 0 1024']*15
    trace=run(rows,'--vs-menu-fields')
    starts=[i for i,row in enumerate(trace) if row[0]=='0']
    assert len(starts)==3
    for index,at in enumerate(starts):
        row=trace[at]
        prior=list(map(int,trace[at-1][42:44])) if at else (1,1)
        expected=start_complete_fight(*prior)
        assert int(row[23])==index+1 and row[1:3]==['-1','0']
        assert row[9]==row[19]=='200' and row[12]==row[22]=='0'
        assert list(map(int,row[33:37]))==[0,index,0,index]
        assert int(row[40])==60 and int(row[41])==0
        assert tuple(map(int,row[42:44]))==expected
    infinite=run(['1 0 0'],'--vs-menu-fields','--round-time','0')[0]
    assert int(infinite[40])==-1
    fixed=run(['1 0 0'],'--mode','fixed-versus','--round-time','0')[0]
    assert int(fixed[23])==-1
    return dict(confirmed_rematches=len(starts)-1,clock_at_midpoint=60,
                first_and_rematch_random_state_matches=len(starts),match_replay_sha256=hashlib.sha256(exe.read_bytes()).hexdigest())

def main():
    p=fixture()
    factory_options(p)
    transition_checks(p)
    source=random.Random(0x139760)
    patterns=[0,1,0,-2,3,0]
    inputs=[]
    expected=[]
    retry_counts=Counter()
    library_draws=[]
    for i in range(72):
        mode=patterns[i%len(patterns)]
        # Half the sequence carries BOTH preceding seeds into a new match;
        # the rest explores independent states of both generators.
        game,lib=expected[-1][1:] if i%2 else (source.randrange(1,0x7fffffff),source.getrandbits(64))
        selection=(0,10,i%10)[i%3]
        inputs.append((mode,game,lib,selection))
        for side in range(2):
            p.write(SELECT+side*0x30+4,(i+side)%6,4)
            p.write(SELECT+side*0x30+12,(i+side)%6,4)
            p.write(SELECT+side*0x30+0x20,1+(i+side)%5,4)
        p.write(OPTIONS+5,i%3,1)
        result,calls=prepare_entry(p,selection,mode,game,lib)
        expected.append(result)
        assert selection==10 or result[0]==selection
        retry_counts[calls[0x17b598]-3]+=1
        library_draws.append(calls[0x316b90])
        if selection!=10 and i<21:actor_setup(p)
    with tempfile.TemporaryDirectory() as td:
        tmp=Path(td)
        (tmp/'main.cpp').write_text(DRIVER)
        exe=tmp/'test'
        subprocess.run(['c++','-std=c++20','-O2','-I',ROOT/'src',tmp/'main.cpp',
                        ROOT/'src/console_versus_session.cpp',ROOT/'src/game_random.cpp','-o',exe],check=True)
        output=subprocess.run([exe],input=''.join(' '.join(map(str,row))+'\n' for row in inputs),
                              text=True,capture_output=True,check=True).stdout
    actual=[tuple(map(int,line.split())) for line in output.splitlines()]
    assert len(actual)==len(expected)
    for case,(a,e) in enumerate(zip(actual,expected)):assert a==e,(case,inputs[case],a,e)
    report=dict(elf_sha256=SOURCE_HASH,entry=hex(0x139760),cases=len(inputs),stage_random=10,
                system_reroll_counts=retry_counts,library_draws=[min(library_draws),max(library_draws)],
                default_display_time=60,default_wins_per_side=2,
                transition_targets=['0x128008','0x139760','0x127940'],
                live_replay=live_replay(),
                scope='Japanese console versus, existing two-human Haohmaru selections. All reached instructions in the FX RNG setup, candidate builder, post-log settings copy, resident-resource actor setup and complete 13fd80. Logical stage IDs and live rematches after natural timeouts. Optical I/O, stage images, playback and OS diagnostics are outside the trace.')
    (ROOT/'outputs/ss6-feasibility/console-versus-session-validation.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report))

if __name__=='__main__':main()
