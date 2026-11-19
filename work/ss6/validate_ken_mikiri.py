#!/usr/bin/env python3
"""Compare actual Ken decoy contacts with original strike collection and dispatch."""
from itertools import product
import json
from pathlib import Path
import struct
import subprocess

from validate_collisions import ACTORS,OBJECTS,QUEUE
from validate_combined_slash import initialize_pools
from validate_dash_motion import ASSETS,ELF,PIN,ROOT,digest
from validate_haohmaru_special import ContactOracle

EXE=ROOT/'work/ss6/build-native/ss6-match-replay'
IMAGE=0x1e02000
OUT=ROOT/'outputs/ss6-feasibility/ken-mikiri-validation.json'


def pads(side,stance):
    if stance=='projectile':
        from validate_ken_defense import paired,prelude
        from validate_haohmaru_special import pads_for
        spell=pads_for(64,1-side)
        return prelude(side,False,True)+[paired(side,30)]+[
            paired(side,1,4096 if t==43 else 0,spell[t] if t<len(spell) else 0) for t in range(85)]
    own_forward=(128,64)[side]
    evade=4096 | {'stand':0,'duck':32,'low':own_forward^192}[stance]
    delay={'stand':12,'duck':0,'low':4}[stance]
    swing=256 if stance=='duck' else 1024
    def pair(n,a=0,b=0):return (n,b,a) if side else (n,a,b)
    return [pair(500),pair(42,own_forward,own_forward^192),pair(8)]+[
        pair(1,evade if t==delay else 0,swing if t==0 else 0) for t in range(85)]


def read(side,field,seq):
    args=[EXE,ASSETS,'--mode','versus',f'--p{side+1}-spirit','ken',field]
    return [r.split() for r in subprocess.check_output(args,input=''.join('%d %d %d\n'%s for s in seq),text=True).splitlines()]


def objects(row):
    off=26;seats=[]
    for _ in range(2):
        n,stored,first,freeze,flash,count=map(int,row[off:off+6]);off+=6
        images=[list(map(int,row[pos:pos+80])) for pos in range(off,off+80*count,80)]
        off+=80*count
        seats.append((n,stored,first,freeze,flash,images))
    assert len(row)==off
    return seats


def compare(side,stance):
    seq=pads(side,stance)
    rows=read(side,'--mikiri-fields',seq)
    contact=read(side,'--whirlwind-fields' if stance=='projectile' else '--contact-fields',seq)
    meters=read(side,'--ken-fields',seq)
    first=next(i for i,r in enumerate(rows) if objects(r)[side][0])
    before,after=map(objects,rows[first-1:first+1])
    tick=int(rows[first][0]);assert tick=={'duck':556,'stand':565,'low':565,'projectile':751}[stance]
    geo=ContactOracle();p=geo.probe;initialize_pools(p)
    battle=p.read(0x4d3d00,4);p.write(battle,4,4)
    for seat in (0,1):
        geo.install_player(contact[first-1],seat)
        a=ACTORS+0xf2c*seat
        p.write(a+0x10c,5 if seat==side else 0,4);p.write(a+0xa24,seat,4)
        p.write(battle+0x24c+4*seat,a,4)
        for off,val in zip((0x14c,0x150,0x154,0x158),meters[first-1][23+8*seat:27+8*seat]):
            p.write(a+off,int(val),4)
    raw,=before[side][5];opponent=1-side
    p.memory[IMAGE:IMAGE+320]=struct.pack('<80I',*raw)
    # The real image shares ACT and JDG tables with its owner's body. The
    # contact fixture has a compact actor JDG table, so restore both pointers.
    def bind_judgments(slot,obj,words):
        base=0x1400000+slot*0x100000
        p.memory[base:base+len(geo.jdg)]=geo.jdg;p.write(0x4751e0+4*slot,base,4)
        rec=60*(struct.unpack_from('<h',geo.aid,2*words[9])[0]+words[10])
        refs=0x17a0000+slot*0x100;p.memory[refs:refs+16]=geo.act[rec+14:rec+30]
        p.write(obj+0xbc,refs,4)
    bind_judgments(side,IMAGE,raw)
    source_object=OBJECTS[opponent]
    if stance=='projectile':
        source_object=0x1e04000
        shot=list(map(int,contact[first-1][131:211]))
        assert shot[0xcc//4]==2 and shot[0x10//4]==opponent
        p.memory[source_object:source_object+320]=struct.pack('<80I',*shot)
        bind_judgments(opponent,source_object,shot)
    p.write(0x12d2698,0,4)
    count=0;calls={}
    def observe(pc):
        if pc in (0x14d9b8,0x1a4708,0x156fb8,0x117170,0x15480c):calls[pc]=calls.get(pc,0)+1
    def run(fn,args=()):
        nonlocal count
        _,n=p.run(fn,args,limit=600000,observe=observe);count+=n
    run(0x1536e8,[source_object,IMAGE]);run(0x1536e8,[IMAGE,source_object])
    events=p.read(0x12d2698,4)
    assert events and all(p.read(QUEUE+108*i,4)==10 for i in range(events))
    run(0x154678)
    a=ACTORS+side*0xf2c
    assert p.read(a+0xf25,1)==after[side][0]==1 and p.read(a+0x158,4)==after[side][1]
    # The ACT may switch judgment flags in the draw pass after the hit.
    # Compare the collision-disabled bit written by 154864 on this visit.
    assert p.read(IMAGE+0x104,4)&0x00400000 and after[side][5][0][0x104//4]&0x00400000
    assert p.read(battle+0x108,4)==int(rows[first][24])
    assert p.read(0x3ebf24,4)==3 and p.read(0x3ec730,4)==0x80ffffff
    # 113aa8 precedes the battle task. 113b28 emits an opaque white quad
    # when its frame flag is set. Player input and object clocks still run.
    for j in range(1,5):
        run(0x113aa8)
        assert int(rows[first+j][23])==p.read(0x3ec73c,4)==int(j<=3)
    # Read the actual vertex packet delivered by 113b28 before GS submission.
    vertices=[]
    class PacketReady(Exception):pass
    def packet(pc):
        if pc==0x110b28:
            vertices.extend(struct.unpack_from('<fffI',p.memory,p.registers[4]+16*i) for i in range(4))
            raise PacketReady
    p.write(0x3ec73c,1,4)
    try:p.run(0x113b28,observe=packet)
    except PacketReady:pass
    assert [(x,y) for x,y,_,_ in vertices]==[(0,0),(0,480),(640,0),(640,480)]
    assert all(color==0xffffffff for _,_,_,color in vertices)
    assert all(calls.get(pc)==1 for pc in (0x14d9b8,0x1a4708,0x156fb8,0x117170))
    assert all(rows[first][i]==rows[first-1][i] for i in (9,19))
    assert int(rows[first][9+10*side])==200
    return dict(side=side+1,stance=stance,tick=tick,candidates=events,stored_before=before[side][1],
                stored_after=after[side][1],original_instructions=count)


if __name__=='__main__':
    assert digest(ELF)==PIN
    cases=[compare(s,d) for s,d in product((0,1),('stand','duck','low','projectile'))]
    OUT.write_text(json.dumps(dict(status='passed',elf_sha256=PIN,native_sha256=digest(EXE),cases=cases),indent=2)+'\n')
    print(len(cases),'two-seat Mikiri contact comparisons passed')
