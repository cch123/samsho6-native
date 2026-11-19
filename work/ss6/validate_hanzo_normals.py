#!/usr/bin/env python3
"""Select Hanzo in real local VS and compare ordinary movements and attacks with SLPS-25559."""
from concurrent.futures import ProcessPoolExecutor
from functools import partial
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import struct
import tempfile

from validate_dash_motion import PIN
from validate_haohmaru_special import BUILD, ELF, ROOT
from validate_normal_attacks import attack_cases
from validate_rimururu_normals import (contact_group, heavy_timeline, introduction, jump_defenders,
    motion, unarmed_attacks)
from inspect_iso import Elf

FIGHTER=3
MOVEMENTS=('walk-forward','walk-back','vertical','forward','back','wall-high','wall-low','run','backstep','3+B')
HEAVY={189,190,195,196,211,214,221}


def attacks(side):
    forward=(128,64)[side]
    for state,action,approach,key in attack_cases(side):
        if action in (191,192,193,194,195,196):
            approach=approach[:-1]+[(20,32)]
        if action in (209,210,212,213,217):
            approach=approach[:-1]+[({209:35,210:37,212:35,213:37,217:33}[action],0)]
        if action==197:
            # The standing kick reaches the airborne hurtbox above Haohmaru's head.
            approach += [(1,0,16),(23,0)]
        yield state,action,approach,key,0
        if action in (189,195,211,214,221):
            if action==221:
                # Hanzo crosses over during this running slash; block toward
                # his starting position once he is on the defender’s far side.
                yield state,action,approach,key,1,forward^192
            else:yield state,action,approach,key,1
            yield state,action,approach,key,2
    # His normal slots 2 and 3 are disabled in the original bindings. The
    # 3+B input thus chooses the regular crouching medium at both distances.
    for k,action in ((45,193),(30,194)):
        yield 5,action,[(k,forward),(2,0)],32|forward|512,0
    for state,action,approach,key,condition in unarmed_attacks(side):
        if state==22:state,action=5,204
        if approach[-1]==(10,32):approach=approach[:-1]+[(20,32)]
        if action==205:approach += [(1,0,16),(23,0)]
        yield state,action,approach,key,condition


def contacts(side):
    return contact_group(side,FIGHTER,list(attacks(side)))


def incoming(side):
    cases=[(state,act,approach,key,0) for state,act,approach,key in attack_cases(side)
           if act in (185,187,189,195,211,214,221)]
    return contact_group(side,0,cases,opponent=FIGHTER)


def run(exe):
    raw=ELF.read_bytes()
    assert sha256(raw).hexdigest()==PIN
    elf=Elf(raw)
    flags=raw[elf.offset(0x4e5420+FIGHTER)]
    normal_commands=struct.unpack_from('<6h',raw,elf.offset(0x4eab00+12*FIGHTER))
    assert flags==3 and normal_commands[1:3]==(-1,-1)
    jobs=[(s,u+m) for s in (0,1) for u in ('','unarmed-') for m in MOVEMENTS]
    heavy_jobs=[(s,act,approach,key) for s in (0,1) for state,act,approach,key,outcome,*_ in attacks(s)
                if outcome==0 and act in HEAVY]
    with ProcessPoolExecutor(max_workers=4) as pool:
        hit_jobs=[pool.submit(contacts,s) for s in (0,1)]
        flights=list(pool.map(partial(motion,character=FIGHTER),jobs))
        timelines=list(pool.map(partial(heavy_timeline,character=FIGHTER),heavy_jobs))
        normals=[v for future in hit_jobs for v in future.result()]
        incoming_cases=[v for group in pool.map(incoming,(0,1)) for v in group]
        aerial_contacts=[v for group in pool.map(partial(jump_defenders,character=FIGHTER),(0,1)) for v in group]
    intro=[introduction(pair,s) for pair,s in (((3,0),0),((0,3),1),((3,3),0),((3,3),1))]
    data=dict(status='passed',japanese_elf_sha256=PIN,replay_sha256=sha256(exe.read_bytes()).hexdigest(),
              movement_flags=flags,character_input_overrides=normal_commands,starting_cell=2,selected_cell=13,resource=FIGHTER,introductions=intro,
              movements=flights,heavy_timelines=timelines,ordinary_attacks=normals,hanzo_as_defender=incoming_cases,
              jump_contacts_vs_crouch_and_air=aerial_contacts,
              movement_frames=sum(f['frames'] for f in flights),contacts=sum(len(r['contacts']) for r in normals),
              scope='Source actor visits use the live world horizontal anchors when pushboxes or the wall can intervene. Vertical motion, facing, ACT/step, callback and airborne flags are independently advanced. Contact expectations execute the Japanese two-body JDG collector, reaction and damage routes on published positions. Heavy timelines also check fractional ACT clocks and both source hitstop counters until idle.')
    path=ROOT/'outputs/ss6-feasibility/hanzo_normals_validation.json'
    path.write_text(json.dumps(data,indent=2)+'\n')
    print(f'{len(flights)} movements / {data["movement_frames"]} updates, {len(normals)} normal attack cases / {data["contacts"]} contacts, {len(timelines)} heavy timelines')


if __name__=='__main__':
    with tempfile.TemporaryDirectory() as tmp:
        exe=Path(tmp)/'ss6-match-replay'
        shutil.copy2(BUILD/'ss6-match-replay',exe)
        os.environ['SS6_NORMALS_REPLAY']=str(exe)
        run(exe)
