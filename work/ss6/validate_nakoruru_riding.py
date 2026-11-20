#!/usr/bin/env python3
"""Compare the mounted fighter and existing companion task through actual character-selection inputs."""
from concurrent.futures import ProcessPoolExecutor,as_completed
from hashlib import sha256
import json
import shutil
from pathlib import Path
import struct
import subprocess
import tempfile

from validate_dash_motion import ELF, PIN
from validate_selected_combat import prefix, ROOT, BUILD
from validate_weapon_handling import setup

ASSETS=ROOT/'work/ss6/extracted/resources'
DRIVER=r'''
#include "local_versus.hpp"
#include <bit>
#include <iostream>
using namespace ss6;
int main(int argc,char** argv){try{
LocalVersus v(argv[1],-1,VersusMode::Console,{},true);std::array<unsigned,2> old{},keys{};unsigned n;
unsigned seat=std::stoi(argv[2]);auto emit=[](auto x){std::cout<<' '<<uint32_t(x);};
while(std::cin>>n>>keys[0]>>keys[1]){
for(unsigned i=0;i<n;++i){std::array<NormalizedPadSample,2> pads;
for(unsigned s=0;s<2;++s)pads[s]={keys[s],keys[s]&~old[s]};old=keys;v.tick(pads);}
const auto& m=v.match();const auto& f=m.fighter(seat);auto& a=f.actor;
if(m.characterSelect()||f.config.character!=1||!a.auxiliaryObject04){std::cout<<"skip\n";continue;}
auto& g=m.battle();auto& eagle=g.entry.tasks.objects.at(a.auxiliaryObject04-1);auto& body=f.body;
std::cout<<a.state194;emit(a.state1a4);emit(a.callbacks260[0]);emit(a.flags23c);emit(a.timers[23]);
emit(body.timeline.action().id());emit(body.timeline.clock().step);emit(body.timeline.clock().fractionalTime);
auto motion=body.timeline.motion();emit(std::bit_cast<uint32_t>(motion.x));emit(std::bit_cast<uint32_t>(motion.y));
for(auto w:{motion.dx,motion.vx,motion.ax,motion.dy,motion.vy,motion.ay})emit(w);
emit(g.camera.left);emit(g.camera.right);emit(std::bit_cast<uint32_t>(m.fighter(1-seat).body.timeline.motion().x));
for(auto w:eagle)emit(w);
std::cout<<'\n';}
}catch(std::exception& e){std::cerr<<e.what()<<'\n';return 2;}}
'''
BIRD_FIELDS=(0x24,0x28,0x2c,0x38,0x40,0x44,0x50,0x54,0x5c,0x60,0xc0,0x128,0x12c,0x130)
def keys(side,move):
    f,b=((128,64),(64,128))[side]
    if move=='timeout':return []
    if move in ('fly','slide'):return [f|16]*8+[b|32]*5+[0]*8
    if move.startswith('slash'):return [256<<int(move[-1])]
    if move.startswith('dismount'):return [2048|{'0':0,'1':f,'2':b,'3':16,'4':f|16,'5':b|16}[move[-1]]]
    state=int(move)
    if state in (80,81,82):
        return [1536|{80:16|f,81:f,82:32|f}[state]]
    direction=f if state<86 else b
    return [32,32|direction,direction|(256<<((state-83)%3))]

def sequence(side,pads,bare=False,move=""):
    pair=lambda a,b:(b,a) if side else (a,b)
    pre=prefix((1-side,side));pre[229]=[128,128]
    if bare:
        f=(128,64)[side]
        own=lambda key:(0,key) if side else (key,0)
        pre += [own(f|8)]+[own(0)]*130+[own(f)]*9+[own(0)]*35
    if move.isnumeric():
        # Isolate the full whiff trajectory. The companion may cross the
        # entire screen at strength C, so the opposing human also jumps it.
        pre += [pair(0,(128,64)[side])]*100+[pair(0,0)]*60
    return pre+[pair(key,16 if move=="88" and tick==32 else 0) for tick,key in enumerate(pads)]

def native(exe,side,pads,bare=False,move=""):
    seq=sequence(side,pads,bare,move)
    proc=subprocess.run([exe,ASSETS,str(side)],input=''.join('1 %d %d\n'%tuple(k) for k in seq),
                        capture_output=True,text=True)
    if proc.returncode:raise AssertionError((side,len(proc.stdout.splitlines()),proc.stderr))
    return [list(map(int,row.split())) for row in proc.stdout.splitlines()[-len(pads)-1:]]

def seed(side,initial):
    oracle,registry=setup(side,1);p,a,o=oracle.p,oracle.a,oracle.o
    p.write(o+0x40,initial[8],4);p.write(o+0x1040,initial[18],4)
    oracle.run(0x1ed370,a);bird=p.read(a+4,4)
    # Bootstrap the independent original tasks from one published live battle
    # tick. Object pointers and the ACT pointer must stay in the original arena.
    for off in (0xc,0x10,0x14,0x1c,0x20,0x24,0x28,0x2c,0x30,0x38,0x3c,0x40,0x44,
                *range(0x4c,0x64,4),0xc0,0xc4,0xc8,0xfc,0x100,0x104,0x108,0x128,0x12c,0x130,0x134):
        p.write(bird+off,initial[19+off//4],4)
    if not initial[3]&0x1000:
        p.write(a+0x23c,initial[3],4);p.write(a+0x198,1,2)
        oracle.run(0x1493c0,a,initial[5],0);oracle.run(0x149918,a);oracle.run(0x11d8e0,o)
    p.write(o+0x28,initial[6],4);p.write(o+0x2c,initial[7],4)
    stage,_=p.run(0x140040)
    original_run=oracle.run
    def stage_after_movement(function,*args,**kwargs):
        result=original_run(function,*args,**kwargs)
        if function==0x11d6c8 and args==(o,):
            original_run(0x142d00,a)
            original_run(0x142d00,oracle.other)
        return result
    oracle.run=stage_after_movement
    return oracle,registry,bird,stage

class PairPush:
    def __init__(self,side,pads,bare,move):
        from validate_nakoruru_riding_contacts import RiderContact
        self.source=RiderContact((1-side,side))
        seq=sequence(side,pads,bare,move)
        proc=subprocess.run([BUILD/'ss6-match-replay',ASSETS,'--mode','select','--contact-fields'],
                            input=''.join('1 %d %d\n'%tuple(w) for w in seq),capture_output=True,text=True,check=True)
        self.contacts=[r.split() for r in proc.stdout.splitlines()[-len(pads)-1:]]
        self.side=side
    def apply(self,tick):
        from validate_collisions import OBJECTS,QUEUE
        s=self.source;p=s.probe
        for side in (0,1):s.install_player(self.contacts[tick],side)
        p.write(0x12d2698,0,4)
        for pair in (OBJECTS,OBJECTS[::-1]):p.run(0x1536e8,pair,limit=50000)
        p.run(0x1544a0,limit=50000)
        for i in range(p.read(0x12d2698,4)):
            event=QUEUE+108*i
            if p.read(event,4)==11:
                p.run(0x154bd0,[event])
                # The reciprocal body contacts in the sorted queue both push.
        return [p.read(OBJECTS[k]+0x40,4) for k in (self.side,self.side^1)]

def verify(arg):
    exe,side,label=arg;b=(64,128)[side]
    bare=label.startswith('bare-');move=label.removeprefix('bare-')
    pads=[32,32|b,b|2048]+[0]*29+keys(side,move)+[0]*108
    rows=native(exe,side,pads,bare,move);oracle,registry,bird,stage=seed(side,rows[0])
    p,a,o=oracle.p,oracle.a,oracle.o;actions=[];states=[];commands=[];push_visits=0;push=None
    for tick,(held,old,row) in enumerate(zip(pads,rows,rows[1:])):
        p.write(stage+0x10,old[16],4);p.write(stage+0x14,old[17],4)
        p.write(o+0x40,old[8],4);p.write(o+0x1040,old[18],4)
        # When the idle opponent moves, run the two-actor original push
        # collector before both the movement and boundary-clamp passes. This
        # also catches replay/oracle disagreement on the opponent's resulting X.
        if old[18]!=row[18]:
            if push is None:push=PairPush(side,pads,bare,move)
            x,other_x=push.apply(tick)
            p.write(o+0x40,x,4);p.write(o+0x1040,other_x,4);push_visits+=1
        oracle.run(0x147028,registry,48);oracle.frame(held)
        assert p.read(o+0x1040,4)==row[18],(side,label,tick,"opponent X",hex(p.read(o+0x1040,4)),hex(row[18]))
        p.write(stage+0x10,row[16],4);p.write(stage+0x14,row[17],4)
        oracle.run(0x146ef8,registry,48);oracle.run(0x1207d8);oracle.run(0x1470a8,registry,48)
        fighter=[p.read(a+v,4) for v in (0x194,0x1a4,0x260,0x23c,0x20c)]
        fighter.extend(p.read(o+v,4) for v in (0x24,0x28,0x2c,0x40,0x44,*range(0x4c,0x64,4)))

        eagle=[p.read(bird+off,4) for off in BIRD_FIELDS]
        actual=[row[19+off//4] for off in BIRD_FIELDS]
        if fighter!=row[:16] or eagle!=actual:
            raise AssertionError((side,label,tick,[(i,hex(x),hex(y)) for i,(x,y) in enumerate(zip(fighter,row)) if x!=y],
                                  [(hex(off),hex(x),hex(y)) for off,x,y in zip(BIRD_FIELDS,eagle,actual) if x!=y]))
        for out,item in ((actions,row[5]),(states,[row[0],row[1]]),(commands,actual[-3])):
            if not out or out[-1]!=item:out.append(item)
    assert {578,579+bare,581+bare,int(bare)}<=set(actions) and 16 in commands,(side,label,actions,commands)
    if move.isnumeric():assert (int(move)<<16|1) in [q[0] for q in states],(side,label,states,actions)
    if move.startswith('slash'):assert (590 if bare else 588 if move[-1]!='2' else 589) in actions,(side,label,actions)
    return dict(seat=side+1,input=label,frames=len(pads),actions=actions,states=states,bird_commands=commands,
                two_body_anchor_visits=push_visits,original_instructions=oracle.instructions)

def knock_off(side):
    from validate_nakoruru_combat import MixedContactOracle,ACTORS
    class MountedContactOracle(MixedContactOracle):
        def install_player(self,row,slot):
            super().install_player(row,slot)
            base=23+26*slot
            if int(row[base+5])&0x200000:
                # 1ecd90 clears the main state. A stationary rider uses
                # alias 0/0, whose effective ordinary state is 0/19.
                actor=ACTORS+slot*0xf2c
                self.probe.write(actor+0x194,0xffffffff,4)
                self.probe.write(actor+0x1a4,0 if int(row[3+10*slot])==0 else 0xffffffff,4)
                self.probe.write(actor+0x1aa,int(row[base+10]),1)
    f,b=((128,64),(64,128))[side]
    pair=lambda a,d:(d,a) if side else (a,d)
    pre=prefix((1-side,side));pre[229]=[128,128]
    pre+= [pair(f,b)]*24+[pair(0,0)]*30
    pads=[pair(key,b if tick<15 else 16 if tick==25 else 1024 if tick==43 else 0)
          for tick,key in enumerate([32,32|b,b|2048]+[0]*127)]
    data=''.join('1 %d %d\n'%tuple(w) for w in pre+pads)
    proc=subprocess.run([BUILD/'ss6-match-replay',ASSETS,'--mode','select','--contact-fields'],
                        input=data,capture_output=True,text=True,check=True)
    rows=[line.split() for line in proc.stdout.splitlines()[-len(pads):]]
    result=MountedContactOracle((1-side,side)).contacts(rows,side^1)
    hits=[(i,r) for i,r in enumerate(rows[1:],1) if int(r[9+side*10])<int(rows[i-1][9+side*10])]
    assert len(hits)==1 and len(result)==1,(side,hits,result)
    tick,row=hits[0];base=3+10*side
    assert int(rows[tick-1][23+26*side+5])&0x200000 and int(rows[tick-1][base+2])==581
    assert int(row[base+1])==74 and int(row[base+6])==170 and int(rows[-1][base+2])==0
    return dict(rider_seat=side+1,contact_tick=tick+1,prior_action=581,hit_action=int(row[base+2]),original_contact=result)
    
def main():
    import sys
    assert sha256(ELF.read_bytes()).hexdigest()==PIN
    cases=sys.argv[1:] or ['timeout','fly','slash0','slash1','slash2',*['dismount'+str(i) for i in range(6)],*[str(i) for i in range(80,89)],'bare-timeout','bare-slash0','bare-slash1','bare-slash2','bare-83','bare-84','bare-85']
    with tempfile.TemporaryDirectory() as tmp:
        lib=Path(tmp)/'libss6-runtime.a';shutil.copyfile(BUILD/'libss6-runtime.a',lib)
        lib_hash=sha256(lib.read_bytes()).hexdigest()
        cpp=Path(tmp)/'riding.cpp';cpp.write_text(DRIVER);exe=cpp.with_suffix('')
        subprocess.run(['c++','-std=c++20','-ffp-contract=off','-O2','-I',ROOT/'src',cpp,lib,'-o',exe],check=True)
        with ProcessPoolExecutor(max_workers=6) as pool:
            rows=[];failures=[]
            jobs=[pool.submit(verify,(exe,seat,name)) for name in cases for seat in (0,1)]
            for job in as_completed(jobs):
                try:
                    row=job.result()
                except Exception as error:
                    failures.append(str(error));print('FAILED',repr(error),flush=True);continue
                print(row['seat'],row['input'],row['actions'],flush=True);rows.append(row)
            assert not failures,failures
            rows.sort(key=lambda row:(row['seat'],row['input']))
    if not sys.argv[1:]:
        out=dict(status='passed',knock_off=[knock_off(s) for s in (0,1)],elf_sha256=PIN,runtime_sha256=lib_hash,cases=rows)
        (ROOT/'outputs/ss6-feasibility/nakoruru_riding_validation.json').write_text(json.dumps(out,indent=2)+'\n')
if __name__=='__main__':main()
