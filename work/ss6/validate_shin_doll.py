#!/usr/bin/env python3
"""Compare Haohmaru's doll, both smoke births and unarmed fall-through with the Japanese game."""
import json
from concurrent.futures import ProcessPoolExecutor
import struct
import subprocess
from validate_dash_motion import ASSETS, ELF, PIN, ROOT, digest
from validate_weapon_handling import setup

REPLAY=ROOT/'work/ss6/build-native/ss6-match-replay'
OUT=ROOT/'outputs/ss6-feasibility/shin_doll_validation.json'


def compare(case):
    player,system,armed=case
    front=(128,64)[player]
    back=front^192
    masks=[front,32|front,32,32|back,back,front,back|4096]+[0]*121
    pair=lambda mask: (0,mask) if player else (mask,0)
    initial=[(500,0,0)]
    if not armed:initial.extend([(1,*pair(front|8)),(145,0,0)])
    rows=initial+[(1,*pair(mask)) for mask in masks]
    replay=subprocess.run([REPLAY,ASSETS,'--mode','versus',f'--p{player+1}-spirit',system,'--spirit-fields'],
                          input=''.join(f'{n} {a} {b}\n' for n,a,b in rows),capture_output=True,text=True,check=True)
    lines=[row.split() for row in replay.stdout.splitlines()]
    src,_=setup(player)
    p,a,o,b=src.p,src.a,src.o,src.b
    p.write(a+0x10c,int(system=='shin'),4)
    src.run(0x179258,a+0x2c4,a+0x10c)
    before=lines[len(initial)-1]
    for body,x in ((o,before[7+10*player]),(o+0x1000,before[7+10*(1-player)])):
        struct.pack_into('<f',p.memory,body+0x40,float(x))
    if not armed:
        p.write(a+0x23c,p.read(a+0x23c,4)&~0x1000,4)
        p.write(a+0xa3c,1,4)
        src.run(0x149918,a);src.run(0x11d8e0,o)
    # Slot 2 is the resident common graphics bank. ACT 54 belongs to
    # the battle registry and uses a different atlas from body ACT 164.
    for name,address in [('aid',0x46a9b0+2*0x1800),('act',0x1a60000)]:
        data=(ASSETS/f'{name}_51.bin').read_bytes()
        p.memory[address:address+len(data)]=data
    p.write(0x4751b8,0x1a60000,4);p.write(0x46a9a8,51,4)
    p.write(0x345188,0,4)
    common=b+0x14c
    p.memory[common:common+256]=bytes(256)
    moves=[];births=[]
    for n,(mask,row) in enumerate(zip(masks,lines[len(initial):])):
        src.run(0x147028,common,64)
        values=src.frame(mask)
        src.run(0x146ef8,common,64)
        returned,_=p.run(0x16d9c8,[a],limit=400000)
        if returned:births.append(n)
        p.write(o+0x104,p.read(o+0x104,4)&~0x18000,4)
        src.run(0x1207d8);src.run(0x1470a8,common,64)
        core=3+player*10
        if n>=6:
            assert (int(row[core]),int(row[core+1]),int(row[core+2]),int(row[core+3]))==(values[0]&65535,values[0]>>16,values[54],values[55]),(case,n,row[core:core+4],values[:1],values[54:56])
        assert int(row[24+4*player])==p.read(a+0xf24,1)
        smoke=[]
        for j in range(64):
            task=p.read(common+4*j,4)
            if not task:continue
            obj=p.read(task+0x1c,4)
            if p.read(obj+0x24,4)!=54:continue
            smoke.extend([player+1,*[p.read(obj+k,4) for k in (0x24,0x28,0x40,0x44,0xb0,0x104,0x108)]])
        assert list(map(int,row[33:]))==smoke,(case,n,row[33:],smoke)
        pose=(values[0]>>16,values[54],values[55])
        if pose[0]==48 and (not moves or moves[-1][1]!=pose):
            moves.append((n,pose))
    if system=='shin' and armed:
        assert births==[6,86] and [v[-1] for _,v in moves]==[0,1,2,3],(case,births,moves)
    else:assert not moves and not births,(case,births,moves)
    return dict(player=player+1,spirit=system,armed=armed,body=moves,smoke_births=births)


if __name__=='__main__':
    assert digest(ELF)==PIN
    cases=[(player,system,armed) for player in range(2) for system,armed in [('shin',True),('shin',False),('rage',True)]]
    with ProcessPoolExecutor(max_workers=4) as pool:results=list(pool.map(compare,cases))
    OUT.write_text(json.dumps(dict(status='passed',original=PIN,replay_sha256=digest(REPLAY),cases=results),indent=2)+'\n')
    print(OUT)
