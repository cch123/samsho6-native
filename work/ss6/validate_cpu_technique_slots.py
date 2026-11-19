"""Compare the Japanese CPU technique selector, acceptance window and recovery, including script dispatch."""
import argparse
import json
import random
import subprocess
import struct
import tempfile
from pathlib import Path

from cpu_fight_oracle import cpu_actor
from validate_dash_motion import ELF,PIN,ROOT,digest
from validate_input_lifecycle import Boundary
from validate_versus_heavy import BUILD,PKG,HERE

CONTEXT=0x1850000
WAIT,RECOVER=0x162ce0,0x162d70
DRIVER=r'''
#include "cpu_technique.hpp"
#include <iostream>
#include <memory>

namespace ss6 {
int scriptRequested;
void observeScriptRequest(StateEntryActor&,const CpuExecutionFrame&,int id) {scriptRequested=id;}
}
int main(int argc,char** argv) {
    using namespace ss6;
    InputBindings bindings(argv[1]);
    std::array<std::unique_ptr<CpuTactics>,51> tactics;
    unsigned id,spirit,slot,phase,charge,board;
    while(std::cin>>id>>spirit>>slot>>phase>>charge>>board) {
        if(!tactics.at(id))tactics[id]=std::make_unique<CpuTactics>(argv[1],id);
        StateEntryActor a;
        GameRandom rng;
        a.character=id;a.characterBytesF14[4]=charge;a.characterBytesF14[13]=board;
        std::cin>>a.state194>>a.bodyAction24>>a.cpuTimerDelta08>>a.controlTimers0c[9]>>a.controlTimers0c[0]
                >>a.controlFlagsB4>>a.controlFlagsBC>>a.control88>>a.control8c>>a.controlMotion38[0]
                >>a.controlMotion60[3]>>rng.mode>>rng.gameSeed>>rng.librarySeed;
        InputSystemConfig config{spirit,id};
        CpuExecutionFrame f{config,bindings,*tactics[id],rng,0,4,0};
        StateEntryActor enemy;std::cin>>a.flags23c>>enemy.y;f.opponent=&enemy;
        const bool category=phase>=216 && phase<=218;
        a.controlMotion38[9]=category?0:phase;
        scriptRequested=-1;
        if(!phase)beginCpuTechnique(a,f,slot);
        if(category){a.control88=0;a.control8c=UINT32_MAX;chooseCpuTechniqueSlot(a,f,phase);}
        if(scriptRequested==-1)visitCpuTechnique(a,f);
        std::cout<<scriptRequested<<' '<<unsigned(a.characterBytesF14[4])<<' '<<a.controlTimers0c[9]<<' '
                 <<a.controlTimers0c[0]<<' '<<a.controlFlagsB4<<' '<<a.controlFlagsBC<<' '<<a.control88<<' '
                 <<a.control8c<<' '<<a.controlMotion38[0]<<' '<<a.controlMotion38[9]<<' '<<a.controlMotion60[3]
                 <<' '<<rng.gameSeed<<' '<<rng.librarySeed<<'\n';
    }
}
'''

def cases():
    src=cpu_actor();p,a,o=src.p,src.a,src.o
    src.run(0x15f5d8,CONTEXT,a+8)
    reent=p.read(0x5d1bf8,4)
    rand=random.Random(0x162ab0)
    def sample(id,spirit,slot,phase,n):
        rawslot=slot if phase else rand.randrange(32)
        state=((64+rawslot)<<16)|1 if n%3 else 0
        body=597+n%2 if n%5==1 else 200
        step=(256,128,0,512)[n%4]
        elapsed=(0,180,300,480,179,299,479)[n%7]*256
        charge=n%8 if n%2 else 0
        board=(0,1,32,64,127,127-64,255,rand.randrange(128))[n%8]
        delay=(n%6)*128
        flags,bits,mask,oldslot=[rand.getrandbits(32) for _ in range(4)]
        running=n%2
        mode=(0,1,-2)[n%3];game=rand.getrandbits(32);lib=rand.getrandbits(64)
        category=216<=phase<=218
        fighter_flags=(0,0x10,0x400000,0x800000,0xc00010,0x1000)[n%6]
        height=(0.,47.5,48.,48.5,225.)[n%5]
        row=(id,spirit,slot,phase,charge,board,state,body,step,elapsed,delay,flags,bits,mask,oldslot,running,rawslot,mode,game,lib,fighter_flags,height)
        for off,val in ((0xa10,id),(0x100,id),(0x10c,spirit),(0x194,state),(8,step),(0x30,elapsed),
                        (0xc,delay),(0xb4,flags),(0xbc,bits),(0x88,mask),(0x8c,oldslot),(0x38,running),
                        (0x5c,0 if category else phase),(0x44,phase),(0x6c,rawslot),(0x23c,fighter_flags)):p.write(a+off,val,4)
        p.write(a+0xf18,charge,1);p.write(a+0xf21,board,1);p.write(o+0x24,body,4)
        p.write(0x443150,mode&0xffffffff,4);p.write(0x3d2e80,game,4);p.write(reent+0xa8,lib,8)
        struct.pack_into("<f",p.memory,p.read(src.other,4)+0x44,height)
        boundary=Boundary(0x15e370)
        # The next subroutine owns multi-step execution. Capture its actual id
        # and the complete caller state immediately before its first instruction.
        p.run(0x15c550 if category else phase or 0x162ab0,[CONTEXT,slot],stop_before=boundary,limit=20000)
        script=p.registers[5] if boundary.stopped else -1
        expected=[script,p.read(a+0xf18,1),*[p.read(a+i,4) for i in (0x30,0xc,0xb4,0xbc,0x88,0x8c,0x38,0x5c,0x6c)],
                  p.read(0x3d2e80,4),p.read(reent+0xa8,8)]
        return row,expected
    for id in range(51):
        for slot in range(32):
            for k in range(2):
                n=(id*32+slot)*2+k
                yield sample(id,(0,1,2,3,4,5,7,8)[(slot+k*3)%8],slot,0,n)
    for id in range(51):
        for phase in (216,217,218):
            for k in range(8):yield sample(id,(0,1,2,3,4,5,7,8)[k],0,phase,phase+id+k)
    for n in range(720):
        yield sample((0,1,2,3,9,48)[n%6],n%6,n%32,(WAIT,RECOVER)[(n//2)%2],n)
    for n in range(128):
        yield sample(9,3,13,0,n)
        yield sample(48,3,29+n%3,0,n)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--package',action='store_true');args=parser.parse_args()
    assert digest(ELF)==PIN
    rows=list(cases())
    with tempfile.TemporaryDirectory() as folder:
        tmp=Path(folder);probe=tmp/'driver.cpp';probe.write_text(DRIVER);exe=tmp/'probe'
        code=(ROOT/'src/cpu_technique.cpp').read_text()
        at='        beginCpuTechniqueScript(a,f,script);'
        assert code.count(at)==1
        code=code.replace(at,'        extern void observeScriptRequest(StateEntryActor&,const CpuExecutionFrame&,int);\n        observeScriptRequest(a,f,script);')
        instrumented=tmp/'technique.cpp';instrumented.write_text(code)
        subprocess.run(['c++','-std=c++20','-O2','-I',ROOT/'src',probe,instrumented,BUILD/'libss6-runtime.a','-o',exe],check=True)
        result=subprocess.run([exe,PKG/'assets' if args.package else HERE/'extracted/resources'],
                              input=''.join(' '.join(map(str,row))+'\n' for row,_ in rows),text=True,capture_output=True,check=True)
    for line,(row,want) in zip(result.stdout.splitlines(),rows,strict=True):
        got=list(map(int,line.split()));assert got==want,(row,got,want)
    report=dict(status='passed',original_sha256=PIN,characters=51,slots_per_character=32,
                comparisons=len(rows),script_dispatches=sum(r[0]>=0 for _,r in rows))
    (ROOT/'outputs/ss6-feasibility/cpu-technique-slot-validation.json').write_text(json.dumps(report,indent=2)+'\n')
    print(report)
if __name__=='__main__':main()

