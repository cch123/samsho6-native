#!/usr/bin/env python3
"""Execute Japanese Rage/Shin contact, round reset and meter callbacks for both sides."""
import hashlib
import itertools
import json
from pathlib import Path
import random
import struct
import subprocess
import sys
import tempfile

from extract_collision_tables import SOURCE_HASH
from mips_probe import Probe

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / 'work/ss6/extracted/resources'
OUTPUT = ROOT / 'outputs/ss6-feasibility/shin-meter-validation.json'
PLAYER, OBJECT, BATTLE = 0x1c00000, 0x1e00000, 0x1e02000
FIELDS = (0x120, 0x124, 0x128, 0x134, 0x138, 0x130)
RUNNER = r"""
#include "damage.hpp"
#include "state_entry.hpp"
#include <iostream>
void emit(const ss6::DamageActor& a) {
    std::cout<<' '<<a.rageState<<' '<<a.rageAmount<<' '<<a.rageDecay
             <<' '<<a.swordCurrent<<' '<<a.swordMaximum<<' '<<a.swordWait;
}
int main(int argc,char** argv) {
    ss6::DamageTables rules(argv[1]);
    char op;
    while(std::cin>>op) {
        ss6::DamageActor a,b;
        if(op=='C') {
            int aux,mode,strength,concentration;
            std::cin>>a.system>>b.system>>aux>>mode>>a.state194>>strength>>a.flags23c>>a.rageState>>a.rageAmount
                    >>a.swordCurrent>>a.swordMaximum>>b.life>>b.armed>>b.rageState>>b.rageAmount
                    >>b.rageDecay>>b.swordCurrent>>b.swordMaximum>>b.flags248>>concentration>>a.systemAmount140;
            a.concentrationUsed11c=concentration;
            a.attackStrength=strength;
            auto source=rules.calculate(aux,a,b,mode);
            auto damage=rules.applyOrdinaryContact(aux,a,b,mode&16,(a.state194>>16)>=64,mode&15);
            std::cout<<source.sourceAmount.bits<<' '<<damage<<' '<<a.swordCurrent<<' '<<a.flags23c<<' '<<b.flags248;emit(a);
            emit(b);
        } else if(op=='K') {
            int system;ss6::StateEntryActor actor;
            std::cin>>system>>actor.fieldA30>>actor.rageState120>>actor.rageAmount124>>actor.rageDecay128
                    >>actor.rageCharge12c>>actor.swordCurrent134>>actor.swordMaximum138;
            rules.updateCriticalRage(actor,system);
            std::cout<<actor.rageState120<<' '<<actor.rageAmount124<<' '<<actor.rageDecay128<<' '
                     <<actor.rageCharge12c<<' '<<actor.swordCurrent134<<' '<<actor.swordMaximum138;
        } else if(op=='H') {
            std::cin>>a.system>>a.flags23c>>a.rageState>>a.rageAmount>>a.rageDecay>>a.rageCharge
                    >>a.swordCurrent>>a.swordMaximum;
            bool filled=false;uint32_t flags108=0;
            rules.advanceOrdinaryMeters(a,0,0,0,flags108,false,&filled);
            std::cout<<a.rageState<<' '<<a.rageAmount<<' '<<a.rageDecay<<' '<<a.rageCharge<<' '
                     <<a.swordCurrent<<' '<<a.swordMaximum<<' '<<filled;
        } else {
            int table,state,strength,transition; unsigned f104,f108;
            std::cin>>a.system>>a.rageState>>a.rageAmount>>a.rageDecay>>a.swordCurrent>>a.swordMaximum
                    >>a.swordWait>>table>>state>>strength>>f104>>f108>>transition;
            a.attackStrength=strength;
            if(op=='R') rules.resetOrdinaryRoundMeters(a);
            else rules.advanceOrdinaryMeters(a,table,state,f104,f108,transition);
            std::cout<<f108;emit(a);
        }
        std::cout<<'\n';
    }
}
"""


def main():
    raw = (ASSETS.parent / 'SLPS_255.59').read_bytes()
    assert hashlib.sha256(raw).hexdigest() == SOURCE_HASH
    p = Probe(raw, finite_model=True)
    table = (ASSETS / 'permission_systems.bin').read_bytes()
    assert table == p.memory[0x50dee0:0x50dee0 + 9 * 40]
    zan="--zan" in sys.argv
    ten="--ten" in sys.argv
    ken="--ken" in sys.argv
    zero="--zero" in sys.argv
    focus=5 if ken else 4 if zero else 3 if ten else 2 if zan else None
    systems=range(6 if ken else 5 if zero else 4 if ten else 3 if zan else 2)
    rows = [struct.unpack_from('<10i', table, n*40) for n in systems]
    rng = random.Random(0x1a41b8)
    commands, expected, examples = [], [], []
    def store(base, values):
        for offset, value in values:
            p.write(base+offset, value, 4)
    def meter(actor):
        return [p.read(actor+offset, 4) for offset in FIELDS]
    def sample(op, args, values):
        commands.append(op+' '+' '.join(map(str, args)))
        expected.append(values)
    def blank(a):
        p.memory[a:a+0xf2c] = bytes(0xf2c)
    for slot, source_system, target_system, target_armed in itertools.product(range(2), systems, systems, range(2)):
        if focus is not None and focus not in (source_system,target_system):continue
        a = PLAYER + 0xf2c*slot
        b = PLAYER + 0xf2c*(1-slot)
        for case in range(128):
            blank(a)
            blank(b)
            rage_a = rng.randrange(2)
            rage_b = rng.choice((0,0,0,1))
            if ten or zero:
                if source_system in (3,4):rage_a=rng.choice((0,1,2,3))
                if target_system in (3,4):rage_b=rng.choice((0,0,1,2,3))
            source_amount_before = (rng.randrange(0xb801) if ten or zero or ken else 0)
            maximum = rows[source_system][8 if rage_a==2 else 7 if rage_a==1 else 6]*256
            current = rng.choice((0,maximum-1,maximum,rng.randrange(maximum)))
            amount = rng.choice((0,rng.randrange(0xb800),0xb600,0xb700,0xb7ff,0xb800))
            strength = rng.randrange(3)
            action = rng.choice((8,21,69,77,80))
            if (ten or zero) and source_system in (3,4) and case%3==0:action=38
            mode = rng.choice((0,1,2,16,17))
            flags = 0x1000 | rng.choice((0, 0x40000000))
            aux = rng.choice((0,4,8,10,18,24,36,40,60))
            life = rng.choice((1,19,20,49,180,199,200))
            if case in (0,1):
                # Full-sword heavy sized comparison and the exact full-rage threshold.
                rage_a=rage_b=0
                current=maximum=rows[source_system][6]*256
                amount=0 if case==0 else 0xb700
                strength,action,mode,flags,aux,life=2,8,0,0x1000,24,200
            bmax = rows[target_system][8 if rage_b==2 else 7 if rage_b==1 else 6]*256
            bflags = rng.choice((0,8,0x10008))
            state_word = (action<<16)|1
            store(a,[(0x10c,source_system),(0x120,rage_a),(0x124,source_amount_before),(0x134,current),(0x138,maximum),
                     (0x194,state_word),(0x23c,flags),(0xa24,slot)])
            concentration=int(zero and source_system==4 and action==38 and case%2==0)
            reserve=rng.randrange(51201) if concentration else 0
            p.write(a+0x11c,concentration,1);p.write(a+0x140,reserve,4)
            p.write(a+0x19a,(0,2,4)[strength],1)
            store(b,[(0x10c,target_system),(0x120,rage_b),(0x124,amount),(0x128,71),
                     (0x134,bmax),(0x138,bmax),(0xa30,life),(0x23c,target_armed*0x1000),
                     (0x248,bflags),(0xa24,1-slot)])
            p.run(0x1a3c18,[aux,a,b,mode])
            source_amount=p.floats[0]
            hit,_ = p.run(0x1a41b8,[aux,a,b,mode])
            m=meter(b)
            sample('C',(source_system,target_system,aux,mode,state_word,strength,flags,rage_a,source_amount_before,
                       current,maximum,life,target_armed,rage_b,amount,71,bmax,bmax,bflags,concentration,reserve),
                   [source_amount,hit,p.read(a+0x134,4),p.read(a+0x23c,4),p.read(b+0x248,4),*meter(a),*m])
            if case in (0,1) and not slot and target_armed:
                examples.append(dict(source_spirit=source_system,target_spirit=target_system,
                                     target_rage_before=amount,damage=hit,target_rage_after=m[1],
                                     rage_decay=m[2],sword_max=m[4]))
    contacts=len(commands)
    p.write(0x4d3d08,PLAYER,4);p.write(0x4d3d00,BATTLE,4)
    resets=0
    for slot,system in itertools.product(range(2),(focus,) if focus is not None else systems):
        a=PLAYER+slot*0xf2c
        for case in range(256):
            blank(a)
            rage=case%4
            amount=rng.choice((0,1,81,82,83,111,112,113,0xb7ff,0xb800))
            decay=(112,82,98,78,112,78)[system]
            maximum=rows[system][7 if rage in (1,2) else 6]*256
            current=rng.choice((0,maximum,maximum-1,rng.randrange(maximum),maximum-30*256))
            wait=rng.choice((0,1,20))
            table,state=rng.choice(((0,0),(1,8),(1,21),(1,36),(1,77),(2,8)))
            strength=rng.randrange(3)
            f104=rng.choice((0,0,0x40000,0x80000))
            f108=rng.choice((0,0x10,0x200,0x210))
            transition=rng.randrange(2)
            op='R' if case<32 else 'M'
            args=(system,rage,amount,decay,current,maximum,wait,table,state,strength,f104,f108,transition)
            store(a,[(0,OBJECT),(0xa24,slot),(0x10c,system),(0x110,slot),(0x194,(state<<16)|table),
                     (0x23c,0x1000),*zip(FIELDS,(rage,amount,decay,current,maximum,wait))])
            p.write(a+0x19a,(0,2,4)[strength],1)
            store(OBJECT,[(0x104,f104),(0x108,f108)])
            store(BATTLE,[(0,4),(8,transition)])
            if op=='R':
                p.run(0x14ec80,[a+0x10c])
                resets+=1
            else:
                p.run(0x11e760,[slot])
            sample(op,args,[p.read(OBJECT+0x108,4),*meter(a)])
    regular=len(commands)-contacts-resets
    threshold_cases=critical_cases=0
    if zan:
        # 14ba18 is an actor callback. A previously active meter keeps its
        # sword at low HP, while a newly active one restores the full sword.
        for system,life,state in itertools.product(systems,(-1,0,1,19,20,21,200),range(4)):
            for amount,decay in [(0,0),(1234,0),(0xb800,98)]:
                a=PLAYER;blank(a)
                initial=(state,amount,decay,40,15000,25600)
                store(a,[(0x10c,system),(0xa30,life),*zip((0x120,0x124,0x128,0x12c,0x134,0x138),initial)])
                p.run(0x14ba18,[a]);critical_cases+=1
                sample('K',(system,life,*initial),[p.read(a+off,4) for off in (0x120,0x124,0x128,0x12c,0x134,0x138)])
        # Charge is examined at priority five. Check both signed boundary
        # comparisons independently of the actor's earlier decision to hold.
        for slot,active,state,counter,amount in itertools.product(range(2),range(2),range(2),(0,1,40,100),(0,0xb7a6,0xb7a7,0xb7ff,0xb800)):
            a=PLAYER+slot*0xf2c;blank(a);flag=0x1000|(0x10000 if active else 0)
            initial=(state,amount,98 if state else 0,counter,25600,25600)
            store(a,[(0,OBJECT),(0x10c,2),(0xa24,slot),(0x110,slot),(0x23c,flag),
                     *zip((0x120,0x124,0x128,0x12c,0x134,0x138),initial)])
            store(OBJECT,[(0x104,0),(0x108,0)]);store(BATTLE,[(0,4),(8,0)])
            effects=[]
            def watch(pc):
                if pc in (0x141528,0x1e7b70):effects.append([pc,p.registers[4]&0xffffffff,p.registers[5]])
            p.run(0x11e760,[slot],observe=watch);threshold_cases+=1
            if effects:assert effects==[[0x141528,0xffffffff,30],[0x1e7b70,0xffffffff,61]]
            sample('H',(2,flag,*initial),[p.read(a+off,4) for off in (0x120,0x124,0x128,0x12c,0x134,0x138)]+[int(bool(effects))])
    with tempfile.TemporaryDirectory() as tmp:
        tmp=Path(tmp)
        (tmp/'probe.cpp').write_text(RUNNER)
        binary=tmp/'probe'
        subprocess.run(['c++','-std=c++20','-ffp-contract=off','-O2','-I',ROOT/'src',tmp/'probe.cpp',
                        ROOT/'src/damage.cpp',ROOT/'src/scalar_float.cpp','-o',binary],check=True)
        result = subprocess.run([binary,ASSETS],input='\n'.join(commands)+'\n',
                                capture_output=True,text=True,check=True)
    actual=[list(map(int,row.split())) for row in result.stdout.splitlines()]
    assert len(actual)==len(expected)
    for command,got,want in zip(commands,actual,expected):
        assert got==want,(command,got,want)
    report=dict(status='passed',elf_sha256=SOURCE_HASH,combatant_orders=[[0,0],[1,0],[0,1],[1,1]],
                source_rows=rows,original_contact_cases=contacts,original_round_resets=resets,
                original_meter_updates=regular,critical_hp_actor_visits=critical_cases,manual_charge_updates=threshold_cases,examples=examples,
                scope='Unpatched Japanese 1a3c18/1a41b8 and callees, 14ec80 and 11e760. Finite EE arithmetic model. Includes guard and hit, all accepted source modes, armed and unarmed targets, both slots, sword recovery and cross-round rage.')
    if zan:
        report['combatant_orders']=[[a,b] for a,b in itertools.product(systems,repeat=2) if 2 in (a,b)]
        report['scope']+=' Original 14ba18 critical-health entry/exit through exact 0/1/20/21 HP boundaries and both charge-crossing calls from 11e760.'
    if ten:
        report['combatant_orders']=[[a,b] for a,b in itertools.product(systems,repeat=2) if 3 in (a,b)]
        report['scope']+=' Includes explosion/exhaustion and the 1/38 remaining-meter base damage with guarding and armed/unarmed targets.'
    if ken:report["combatant_orders"]=[[a,b] for a,b in itertools.product(systems,repeat=2) if 5 in (a,b)]
    if zero:report["combatant_orders"]=[[a,b] for a,b in itertools.product(systems,repeat=2) if 4 in (a,b)]
    output=OUTPUT.with_name("ken-contact-meter-validation.json" if ken else "zero-contact-meter-validation.json" if zero else "ten-meter-validation.json" if ten else "zan-meter-validation.json") if focus is not None else OUTPUT
    output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report))

if __name__ == '__main__':
    main()
