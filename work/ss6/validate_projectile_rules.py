#!/usr/bin/env python3
"""Compare shared projectile eligibility, hitstop, reflection and hit classification to the Japanese routines."""
import json
import struct
import subprocess
import tempfile
from pathlib import Path
from validate_dash_motion import ASSETS, ELF, PIN, ROOT, digest
from validate_finishing_blow import CHILD, EVENT, OBJECTS, Comparison, actor, put, state
from validate_input_lifecycle import Boundary
from validate_thrown_stage_items import compile_probe

DRIVER=r'''
#include "auxiliary_objects.hpp"
#include "collision.hpp"
#include "finishing_blow.hpp"
#include "input_bindings.hpp"
#include "state_entry.hpp"
#include <iostream>
using namespace ss6;
int main(int,char** argv) {
    const CollisionTables tables(argv[1]);const InputBindings bindings(argv[1]);
    AuxiliaryObjects objects(argv[1],{0,0,51});char op;
    while(std::cin>>op) {
        AuxiliaryObject o{};
        if(op=='f') {
            unsigned id;std::cin>>id;std::cout<<unsigned(tables.projectileFlags(id));
        } else if(op=='h') {
            unsigned resource,action;std::cin>>resource>>action;
            std::cout<<tables.sharesProjectileHitstop(resource,action);
        } else if(op=='c') {
            StateEntryActor a{},b{};
            std::cin>>o[0xcc/4]>>o[0xd0/4]>>o[0x18/4]>>o[0x128/4]>>o[9]
                    >>a.character>>a.state194>>a.state1a4>>a.flags23c>>b.state194>>b.state1a4>>b.flags23c;
            std::cout<<projectileFinishCategory(o,a,b,bindings);
        } else if(op=='r') {
            unsigned team;std::cin>>team;for(auto& word:o)std::cin>>word;
            objects.reflectProjectile(o,team);for(auto word:o)std::cout<<word<<' ';
        } else return 2;
        std::cout<<'\n';
    }
}
'''

def main():
    assert digest(ELF)==PIN
    c=Comparison();p=c.p
    commands=[];answers=[];counts={}
    def check(op,args,expected):
        commands.append(' '.join(map(str,[op,*args])))
        answers.append(expected);counts[op]=counts.get(op,0)+1
    for i in range(190):
        check('f',[i],[p.read(c.run(0x163430,[i])+10,1)])
    pairs=set()
    for i in range(22):
        res,act=struct.unpack_from('<Bxh',p.memory,0x4e8168+i*4)
        pairs.add((res,act))
    assert struct.unpack_from('<Bxh',p.memory,0x4e8168+88)==(255,-1)
    actions={a+d for _,a in pairs for d in (-1,0,1)}|{0,65535}
    for res in sorted({k for k,_ in pairs}|{1,4,24,51,255}):
        for act in sorted(actions):
            check('h',[res,act],[c.run(0x1690b0,[res,act])])
    def category(kind,id,profile,cmd,act,char,index,opp_index,alias,side):
        af=(0x200000 if alias&1 else 0)|0x1000
        bf=(0x200000 if alias&2 else 0)|0x1000
        astate,bstate=state(1,index),state(2,opp_index)
        alias_a,alias_b=state(1,1),state(0,0)
        put(p,actor(side),[(0xa10,char),(0x194,astate),(0x1a4,alias_a),(0x23c,af)])
        put(p,actor(1-side),[(0xa10,0),(0x194,bstate),(0x1a4,alias_b),(0x23c,bf)])
        put(p,CHILD,[(0xcc,kind),(0xd0,id),(0x18,profile),(0x128,cmd),(0x24,act),(0xc,1-side),(0x10,side)])
        check('c',[kind,id,profile,cmd,act,char,astate,alias_a,af,bstate,alias_b,bf],[c.run(0x14dc00,[CHILD])])
    for side in range(2):
        for id in [*range(191),0xffffffff]:
            category(2,id,0,7,810,0,78,87,0,side)
        for kind in (0,1,3,4,5,9):
            for profile in (0,1,4,45,51):
                for cmd in (0,7):
                    for act in (809,810):
                        for opp in (0,87):
                            category(kind,135,profile,cmd,act,profile%51,78,opp,0,side)
        for char in (0,1,3,4,24,45):
            for idx in range(64,96):
                for alias in range(4):
                    category(3,0,4,0,809,char,idx,87 if alias&2 else 0,alias,side)
        for desc in (0,7,109,167,168,169):
            for facing in (0,0x80000):
                words=[0x55+i for i in range(80)]
                for off,val in ((0x10,1-side),(0xc,1-side),(0x14,0),(0x1c,0),(0x24,532),(0x38,facing),
                                (0xcc,2),(0xd0,desc),(0x104,0x140)):
                    words[off//4]=val
                struct.pack_into('<80I',p.memory,CHILD,*words)
                put(p,EVENT,[(0x40,OBJECTS[side]),(0x68,CHILD)])
                put(p,OBJECTS[side],[(0x10,side)])
                stop=Boundary(0x157f80)
                c.run(0x155780,[EVENT],stop_before=stop)
                assert stop.stopped==0x157f80
                check('r',[side,*words],list(struct.unpack_from('<80I',p.memory,CHILD)))
    with tempfile.TemporaryDirectory() as tmp:
        exe=compile_probe(Path(tmp),'rules',DRIVER)
        lines=subprocess.check_output([exe,ASSETS],input='\n'.join(commands)+'\n',text=True).splitlines()
    assert len(lines)==len(answers)
    for case,line,expected in zip(commands,lines,answers):
        got=list(map(int,line.split()))
        assert got==expected,(case,got,expected)
    result=dict(elf=PIN,descriptor_flags=counts['f'],hitstop_cases=counts['h'],shared_pairs=len(pairs),
                finish_cases=counts['c'],reflection_cases=counts['r'],original_instructions=c.instructions)
    (ROOT/'outputs/ss6-feasibility/projectile-rules-validation.json').write_text(json.dumps(result,indent=2)+'\n')
    print(result)

if __name__=='__main__':main()
