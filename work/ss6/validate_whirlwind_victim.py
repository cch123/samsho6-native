#!/usr/bin/env python3
"""Compare another fighter's whirlwind capture (table-B rows 0..2 in the
whirlwind form, e.g. Rasetsumaru 4e3570) with SLPS_255.59, tick by tick.

The original side reuses validate_haohmaru_whirlwind.original_victim with the
source's own bank loaded into player 1's resource slot and its own table-A
row spawning the projectile through 16d9c8. The native side is a publicly
selected match (source vs Haohmaru) using the same 236+slash input; the
victim's state, body ACT/clock, Y, landing, attachment, timer23, callbacks and
registry are compared every tick until the downed state.
Usage: validate_whirlwind_victim.py --source 18
"""
import argparse
import hashlib
import json
import struct
from validate_haohmaru_whirlwind import compare_victim
from validate_haohmaru_special import (ACTORS, ELF, ROOT, SOURCE_HASH, fixture, initialize_effects, pads_for, run_native)
from validate_selected_combat import prefix

RES=ROOT/'work/ss6/extracted/resources'

def script_row(source,script):
    data=(RES/'script_rows.bin').read_bytes()
    base,_=struct.unpack_from('<II',data,8*source);at=51*8
    for c in range(source):at+=20*struct.unpack_from('<I',data,8*c+4)[0]
    for i in range(struct.unpack_from('<I',data,8*source+4)[0]):
        if data[at+20*i]==script:return base+20*i
    raise AssertionError('script row not found')

def original_victim(strength,source,row,child_words):
    p,a,o,b=fixture(0)
    p.finite_model=True
    attacker=ACTORS+0xf2c;parent=o+0x1000
    for addr,val in ((b+0x250,attacker),(attacker,parent),(attacker+0xa24,1),(parent+0xcc,1),(parent+0xc,1)):
        p.write(addr,val,4)
    # Player 1's resource slot holds the source's own bank (aid at slot 1,
    # act in the free overflow arena).
    aid=(RES/f'aid_{source:02}.bin').read_bytes();act=(RES/f'act_{source:02}.bin').read_bytes()
    p.memory[0x46a9b0+0x1800:0x46a9b0+0x1800+len(aid)]=aid
    p.memory[0x1d40000:0x1d40000+len(act)]=act
    p.write(0x4751b4,0x1d40000,4);p.write(0x46a9a4,source,4)
    for off in (0x114,0xa10,0xa14):p.write(attacker+off,source,4)
    for off in (0x14,0x18):p.write(parent+off,source,4)
    for actor,obj,weapon in ((a,o,o+0x4000),(attacker,parent,o+0x3000)):
        p.write(actor+4,weapon,4)
        p.write(weapon+0xc4,-1,4)
        for fn,args in ((0x149008,[actor,0]),(0x149918,[actor]),(0x11d8e0,[obj])):
            p.run(fn,args,limit=500000)
        for addr,val in ((actor+0x23c,0x1000),(obj+0x30,256),(obj+0xc8,1)):
            p.write(addr,val,4)
    initialize_effects(p)
    for addr,val in ((0x345188,0),(a+0x18c,1),(attacker+0x194,(66+strength)<<16|1),
                     (attacker+0x26c,strength),(attacker+0x2b8,row),(attacker+0x28c,0),(parent+0x104,0x8000),
                     (parent+0x38,0x10080000)):
        p.write(addr,val,4)
    p.write(attacker+0x19a,8|(1<<strength),1)
    for obj,x in ((o,312),(parent,330)):struct.pack_into('<f',p.memory,obj+0x40,x)
    child=p.run(0x16d9c8,[attacker],limit=80000)[0]
    assert child,'16d9c8 spawned nothing'
    p.run(0x11d8e0,[child])
    # A rising whirlwind meets the opponent away from its spawn point: start
    # the capture from the native object's position and motion one tick
    # before contact (words 40/44 and 4c..60).
    for off in (0x40,0x44,0x4c,0x50,0x54,0x58,0x5c,0x60):p.write(child+off,child_words[off//4],4)
    p.write(child+0x104,0x40000,4)
    p.write(child+0x108,p.read(child+0x108,4)|0x2000000,4)
    p.write(o+0x124,child,4)
    p.write(a+0x254,source,1)
    p.run(0x14ff80,[a+0x18c,2,80+strength])
    p.write(a+0x18c,1,4)
    result=[]
    for _ in range(180):
        for fn,args in ((0x11d730,[o]),(0x11d6c8,[o]),(0x147028,[b+0x3a4,48]),(0x149d08,[a]),
                        (0x149918,[a]),(0x11d8e0,[o]),(0x146ef8,[b+0x3a4,48]),(0x1470a8,[b+0x3a4,48])):
            p.run(fn,args,limit=300000)
        regs=[p.read(a+off,4) for off in range(0x28c,0x2c0,4)]
        regs[10]=int(bool(regs[10]))
        result.append([p.read(a+0x194,4),p.read(o+0x24,4),p.read(o+0x28,4),p.read(o+0x2c,4),
                       p.read(o+0x44,4),p.read(o+0xc0,4),int(bool(p.read(o+0x124,4))),p.read(a+0x20c,4),
                       *[p.read(a+off,4) for off in range(0x260,0x27c,4)],*regs])
        if p.read(a+0x194,4)==(16<<16|2):return result
    raise AssertionError('Original victim never released into downed state')

def native_match(strength,slot,source):
    forward,back=(128,64) if slot==0 else (64,128)
    lineup=(source,0) if slot==0 else (0,source)
    sequence=[(1,a,b) for a,b in prefix(lineup)]+[(330,0,0),(20,forward if slot==0 else 0,back if slot==0 else 0) if slot==0 else (20,back,forward),(30,0,0)]
    pads=[(1,x,0) if slot==0 else (1,0,x) for x in pads_for(64+strength,slot)]
    sequence+=pads+[(1,0,0)]*290
    return run_native('ss6-match-replay',[' '.join(map(str,v)) for v in sequence],'--mode','select','--whirlwind-fields')

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--source',type=int,required=True);source=ap.parse_args().source
    assert hashlib.sha256(ELF.read_bytes()).hexdigest()==SOURCE_HASH
    row=script_row(source,1)  # the 236+slash script that spawns the whirlwind
    reports=[]
    for strength in range(3):
        for slot in (0,1):
            rows=native_match(strength,slot,source)
            dst=1-slot;first=3+10*slot;defender=3+10*dst
            contacts=[j for j in range(1,len(rows)) if len(rows[j])>first+8 and rows[j-1][first+7:first+9]!=rows[j][first+7:first+9]]
            assert contacts,'the whirlwind must hit'
            j=contacts[0]
            before=rows[j-1];assert len(before)==129+82,'one whirlwind object expected before contact'
            expected=original_victim(strength,source,row,[int(x) for x in before[131:211]])
            compare_victim(rows,j,dst,expected)
            actions={int(r[140]) for r in rows if len(r)>129}
            reports.append(dict(strength=strength,player=slot+1,contact_tick=int(rows[j][0]),victim_ticks=len(expected),projectile_actions=sorted(actions)))
    out=ROOT/f'outputs/ss6-feasibility/whirlwind_victim_{source:02}_validation.json'
    out.write_text(json.dumps(dict(status='passed',source=source,elf_sha256=SOURCE_HASH,cases=reports,
        scope='Captured-victim callbacks of whirlwind rows 0..2 compared tick by tick with the original (state, body ACT/clock, Y, landing, attachment, timer23, callbacks, registry). Contact geometry/damage are checked by the projectile and gap validators.'),indent=2)+'\n')
    print(len(reports),'cases',sum(r['victim_ticks'] for r in reports),'victim ticks')

if __name__=='__main__':main()
