#!/usr/bin/env python3
"""Compare original 156fb8/157318/1574f0 calls and scheduled particle lifetimes."""
import collections
import hashlib
import itertools
import json
import struct
import subprocess
import sys
import tempfile
from pathlib import Path
from character_tiles_oracle import ROOT,ASSETS,bits
from extract_collision_tables import SOURCE_HASH
from knockdown_oracle import initialize_effects
from mips_probe import Probe
from round_entry_oracle import buffered_stdout
from validate_object_pools import OBJECTS,TASKS,handle

DRIVER=r'''
#include "contact_presentation.hpp"
#include "auxiliary_objects.hpp"
#include <bit>
#include <iostream>
using namespace ss6;
void emit(auto v){std::cout<<+v<<' ';}
int main(int argc,char** argv){try{
 if(argc!=2)return 2;ScheduledOpening fx(argv[1]);AuxiliaryObjects objects(argv[1],{0,0,51});BattleRoundState b;ObjectDrawQueue queue;std::string op;
 auto& p=b.entry.tasks;
 while(std::cin>>op){
  if(op=="reset"){b={};queue={};p.initializeOwners();p.initializeTasks();p.initializeObjects();for(unsigned i=1;i<=3;++i)b.effectResidency.slots[i]=i+1;std::cin>>b.random.mode>>b.random.gameSeed>>b.random.librarySeed;continue;}
  if(op=="tick"){
   std::cin>>b.gauges.words910[5];queue.beginFrame();TaskDispatch f;
   f.call=[&](uint32_t id,uint32_t h){if(id!=0x124898)throw std::runtime_error("Unexpected handler");fx.task(h,p,b.effectResidency,b.paletteState,queue,b.gauges);};p.dispatchTasks(f);
  }else if(op=="contact"){
   ContactEvent e{};CollisionPlayer target;unsigned mirror=0,defense=0,chip=0,special=0,state=0;
   std::cin>>e.a.fields.type>>e.a.fields.group>>e.a.fields.variant>>e.b.fields.type>>mirror>>e.centerX>>e.centerY>>defense>>chip>>special>>state>>target.x>>target.judgmentProfile;
   target.mirrorX=mirror;
   if(e.b.fields.type==6)fx.startContact(9,e.centerX,e.centerY,1,p,b.effectResidency,b.random);
   else if(e.a.fields.type==0)fx.startWorld(27,mirror<<19,mirror,e.centerX,e.centerY,-10,1,p,b.effectResidency,b.random);
   else if(e.a.fields.type==33)presentWeaponClash(fx,b,e);else presentContact(fx,b,e,target,defense,chip,special,state,objects);
  }else throw std::runtime_error("Unknown contact fixture");
  emit(b.random.gameSeed);emit(b.random.librarySeed);emit(p.freeObjectCount);emit(p.freeObjectHead);emit(p.freeTaskHead);emit(p.freedStacks);
  for(unsigned i=1;i<=3;++i)emit(b.effectResidency.references[i+1]);
  for(unsigned i=1;i<=2;++i)emit(p.stacks.at(i).flags);
  std::vector<uint32_t> active;for(unsigned h=1;h<=256;++h)if(p.tasks.at(h-1)[1])active.push_back(h);
  emit(active.size());for(auto h:active){auto& t=p.tasks.at(h-1);for(auto i:{0,1,2,3,4,5,6,7,8})emit(t[i]);
   for(auto o=t[7];o;o=p.objects[o-1][0]){emit(o);for(auto v:p.objects[o-1])emit(v);}}
  emit(queue.count);for(const auto& row:queue.active())for(auto v:row)emit(v);std::cout<<'\n';
 }
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}}
'''

def words(p,at,n):return list(struct.unpack_from('<'+'I'*n,p.memory,at))

def snapshot(p):
    oh=lambda v:handle(v,OBJECTS,320);th=lambda v:handle(v,TASKS,52);hh=lambda v:handle(v,0x3d2e88,8)
    row=[p.read(0x3d2e80,4),p.read(p.read(0x5d1bf8,4)+0xa8,8),p.read(0x46a904,4),oh(p.read(0x46a900,4)),th(p.read(0x1232844,4)),p.read(0x3d3690,4)]
    row+=words(p,0x4c3658+8,3)+[p.read(0x3d2e88+i*8,4) for i in range(2)]
    tasks=[TASKS+i*52 for i in range(256) if p.read(TASKS+i*52+4,4)]
    row.append(len(tasks))
    for at in tasks:
        t=words(p,at,9);addr=t[8];t[8]=0x100+(addr-0x4a2b30)//108;t[3]=th(t[3]);t[6]=hh(t[6]);obj=t[7];t[7]=oh(obj);row+=t
        while obj:
            o=words(p,obj,80);row.append(oh(obj));obj=o[0];o[0]=oh(obj);o[78]=oh(o[78]);row+=o
    count=p.read(0x4a2250,4);row.append(count)
    for i in range(count):
        o=words(p,0x479250+i*328,82);o[0]=oh(o[0]);row+=o
    return row


def main():
    raw=(ASSETS.parent/'SLPS_255.59').read_bytes();assert hashlib.sha256(raw).hexdigest()==SOURCE_HASH
    p=Probe(raw,finite_model=True);initialize_effects(p);calls=collections.Counter();instructions=0;draws=0;checks=0;counts=collections.Counter()
    def run(address,args=()):
        nonlocal instructions
        _,n=p.run(address,args,limit=500000);instructions+=n;calls[f'{address:x}']+=1
    for bank,name in enumerate(('01HitFlash.bin','02Guard.bin','03etc.bin'),1):
        at=0x4a4810+(bank-1)*0x3da0;p.memory[at:at+0x3da0]=(ASSETS/name).read_bytes()
    event,src,defender,actors=0x1e00000,0x1e01000,0x1e02000,0x1c00000
    p.write(0x4d3d08,actors,4);p.write(event+0x40,src,4);p.write(event+0x68,defender,4);p.write(defender+0xc,1,4)
    def reset(seed):
        buffered_stdout(p);p.memory[0x3d2e88:0x3d2e88+2048]=bytes(2048);p.memory[OBJECTS:OBJECTS+256*320]=bytes(256*320)
        p.memory[0x1232440:0x1232440+258*4]=bytes(258*4);p.memory[0x3d3698:0x3d3698+257*4]=bytes(257*4)
        run(0x1123a8);run(0x112570);run(0x11e290)
        for i in range(32):p.write(0x4c3510+4*i,i+1 if 1<=i<=3 else 0,4)
        for i in range(44):p.write(0x4c3658+4*i,0,4)
        mode=seed%4;game=seed*1234+1;lib=seed*871+15
        for at,v in [(0x345188,0),(0x443150,mode),(0x3d2e80,game),(0x4a2250,0),(0x46a924,0)]:p.write(at,v,4)
        p.write(p.read(0x5d1bf8,4)+0xa8,lib,8);return f'reset {mode} {game} {lib}'
    cases=[]
    for raw_type,group,variant in [(10,2,2),(10,0,2),(11,0,3),(12,0,1),(12,0,2),(17,0,2),(25,3,2),(31,0,2),(15,1,1),(32,5,2),(12,4,3),(12,0,0)]:
        for mirror,special in itertools.product(range(2),range(2)):
            cases.append(('hit',raw_type,group,variant,1,mirror,0,0,special,0))
    for part,mirror,defense,chip in itertools.product((1,2,3),(0,1),(1,2,3),(0,1)):
        cases.append(('guard',12,0,2,part,mirror,defense,chip,0,0))
    for mirror in (0,1):cases += [('clash',33,0,2,33,mirror,0,0,0,0),('forced',12,0,1,1,mirror,0,0,0,0x260001)]
    deflection = '--deflection' in sys.argv
    anchors='--anchors' in sys.argv
    if anchors:
        cases=[('raw31',31,0,2,1,mirror,0,0,0,0) for profile in (0,1,2,35,48,49,50,51) for mirror in (0,1)]
    if deflection:
        cases=[(label,kind,0,0,part,mirror,0,0,0,0) for mirror in (0,1)
               for label,kind,part in [('parry',10,6),('catch-release',0,0)]]
    with tempfile.TemporaryDirectory() as tmp:
        srcpath=Path(tmp)/'probe.cpp';srcpath.write_text(DRIVER);exe=Path(tmp)/'probe';lib=ROOT/'work/ss6/build-native/libss6-runtime.a'
        subprocess.run(['c++','-O2','-std=c++20','-I',str(ROOT/'src'),str(srcpath),str(ROOT/'src/contact_presentation.cpp'),str(ROOT/'src/scheduled_opening.cpp'),str(ROOT/'src/effect_runtime.cpp'),str(lib),'-o',str(exe)],check=True)
        for seed,case in enumerate(cases):
            label,raw_type,group,variant,part,mirror,defense,chip,special,state=case
            x=230+seed%70;y=50+seed%39;target_x=279.75 if mirror else 301.375
            profile=(0,1,2,35,48,49,50,51)[seed//2] if anchors else 0
            p.write(defender+0x14,profile,4)
            cmds=[reset(seed),f'contact {raw_type} {group} {variant} {part} {mirror} {x} {y} {defense} {chip} {special} {state} {target_x} {profile}']
            for ofs,val in [(4,x),(8,y),(0x20,raw_type),(0x24,group),(0x28,variant),(0x2c,0),(0x48,part)]:p.write(event+ofs,val,4)
            p.write(actors+0x194,state,4);p.write(defender+0x38,mirror<<19,4);p.write(defender+0x40,bits(target_x),4)
            if label=='parry':run(0x1574f0,[event,9])
            elif label=='catch-release':
                p.floats[12:16]=list(map(bits,(x,y,-10,1)))
                run(0x124430,[27,mirror<<19,mirror])
            elif raw_type==33:run(0x1574f0,[event,8])
            elif defense:run(0x157318,[event,defense,chip])
            else:run(0x156fb8,[event,special])
            expected=[snapshot(p)];counts[label]+=1
            # Drive whole shared task scheduler until final draw and reclamation.
            for tick in range(55):
                if p.read(0x46a904,4)==256:break
                paused=int(tick in (3,4));cmds.append(f'tick {paused}');p.write(0x4a2250,0,4);p.write(0x46a924,paused,4);run(0x112838)
                expected.append(snapshot(p));draws+=p.read(0x4a2250,4)
            assert p.read(0x46a904,4)==256,(case,'unfinished')
            proc=subprocess.run([exe,ASSETS],input='\n'.join(cmds)+'\n',text=True,capture_output=True);assert proc.returncode==0,(case,proc.stderr)
            rows=proc.stdout.splitlines();assert len(rows)==len(expected)
            for step,(line,want) in enumerate(zip(rows,expected)):
                got=list(map(int,line.split()));diff=[(i,a,b) for i,(a,b) in enumerate(zip(got,want)) if a!=b]
                assert got==want,(case,step,len(got),len(want),diff[:8]);checks+=1
            if seed%20==0:print(seed,case,checks,flush=True)
    assert (draws>100 and checks>40) if deflection or anchors else (draws>1000 and checks>500 and calls['112838']>500)
    report=dict(status='passed',cases=len(cases),counts=counts,snapshots=checks,draws=draws,original_instructions=instructions,functions=calls,elf_sha256=SOURCE_HASH,
                table_sha256=hashlib.sha256((ASSETS/'contact_effects.bin').read_bytes()).hexdigest(),validator_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                scope='Full original 156fb8, 157318 and 1574f0 for grounded resource00 contacts with no attached secondary character object. Compares ordinary game/library RNG, shared task/owner/texture lifetime, all live object words and raw queued effect snapshots, including paused effects, both target facings, guard heights, additional critical/chip groups and clash. Audio muted. Pixel hardware coverage separate.')
    if deflection:
        report['scope']='1574f0 contact group 9 and 124430 ACT world group 27. Compares every particle and draw through reclamation, both facings, pause and RNG.'
    output='weapon_deflection_effect_validation.json' if deflection else 'contact_presentation_validation.json'
    if anchors:
        output='character-contact-anchor-validation.json'
        report['scope']='Both facings, character body resource IDs 0/1/2/35/48/49/50 and common fallback 51. Compares full raw31 156fb8 particle spawn, every submitted position and draw until destruction using the two independent signed byte tables at 4d8a70.'
    (ROOT/'outputs/ss6-feasibility'/output).write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
