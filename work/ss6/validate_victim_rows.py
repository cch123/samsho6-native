#!/usr/bin/env python3
"""Compare a source fighter's plain table-B dispatcher with SLPS_255.59.

The source characters admitted by victim_script.cpp (Gaoh 26 -> 1fe368,
Earthquake 36 -> 205e40) use the common stub 165780 -> 1657b0 -> 165a78 /
169810. Every row id plus absent ids is entered natively through
updateVictimScript and on the original with the same victim/attacker words,
including every gate/failure fixture of validate_nakoruru_capture.py.
Compared: both actors (35 timers each), callbacks, overrides, registry,
anchors/facing, linked object, weapon ACT, battle timers 5/6, camera queue
and whether 169810 was reached.
Usage: validate_victim_rows.py --source 26
"""
import argparse
from hashlib import sha256
import json
import struct
from validate_nakoruru_capture import MODES, compare_entries, ROOT, ELF, PIN
from fighter_roster import PLAYABLE, SCRIPT_STUBS

RES=ROOT/'work/ss6/extracted/resources'
# Row features victim_script.cpp ports; ids using anything else are skipped
# (the engine throws UnportedFighterState for them).
TYPES={0xff,0x00,0x01,0x02,0x03,0x04,0x05,0x13,0x15,0x18,0x4b,0x2d,0x4d,0x4e,0x4f,0x50,0x51,0x52,0x53,0x54,0x55,0x57,0x58,0x19,0x1a,0x1d,0x1e,0x27,0x28,0x29,0x2e,0x39,0x3a,0x3b,0x3c,0x3d,0x06,0x07,0x08,0x09,0x0a,0x0b,0x0c,0x14,0x16,0x24,0x25,0x26,0x2a,0x2b,0x2c,0x31,0x32,0x33,0x34,0x36,0x37,0x38,0x3e,0x3f,0x40,0x41,0x42,0x43,0x44,0x45,0x46,0x47,0x4a,0x4c,0x59,0x5a}

def table_b(source):
    data=(RES/'victim_rows.bin').read_bytes();at=51*8
    for c in range(51):
        n=struct.unpack_from('<I',data,8*c+4)[0]
        if c==source:return [data[at+20*i:at+20*i+20] for i in range(n)]
        at+=20*n

def scripts(source):
    """{id: [rows]} following 1633c0 (first id match, then r[0]++ to the last row)."""
    rows=table_b(source);out={}
    for i,r in enumerate(rows):
        if r[0]==0xff:break
        if r[0] in out:continue
        k=i;script=[]
        while True:
            script.append(rows[k])
            if rows[k][18]&1:break
            k+=1
        out[r[0]]=script
    return out

def admitted(script):
    for k,r in enumerate(script):
        child=struct.unpack_from('<h',r,6)[0];damage=struct.unpack_from('<h',r,16)[0];flags,typ=r[18],r[19]
        if child!=-1 or r[10] or r[13] or (flags&0x10 and not flags&8) or typ not in TYPES and typ<0x5d:return False
        if k==0 and flags&0x40:return False
        ops=(0,1,2,3,5,6,7,8,*range(10,23),*range(27,35))
        if any(w not in (0,1,2,3,4,5,6,7) for w in r[8:10]) or r[11] not in (*ops,4) or r[12] not in ops:return False
    return True

def handler(source):
    stubs=(RES/'fighter_stubs.bin').read_bytes()
    return struct.unpack_from('<I',stubs,12*source+4)[0]

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--source',type=int,required=True);n=ap.parse_args().source
    assert sha256(ELF.read_bytes()).hexdigest()==PIN
    assert n in SCRIPT_STUBS,'victim_script.cpp owns only ScriptStubs sources'
    victims=PLAYABLE;table=scripts(n)
    rows=tuple(sorted(k for k,v in table.items() if admitted(v)))
    skipped=sorted(set(table)-set(rows))
    # Missing rows that run character code needing the attacker's live scene
    # objects (Kyoshiro's k == 0 catch) are covered by validate_victim_visits.py.
    scene={5:{0},31:{0},39:{0}}.get(n,set())  # 31: 1ffd90 places both fighters from the live camera
    absent=next(k for k in range(64) if k not in table and k not in scene)
    weapon=[k for k in rows if table[k][0][18]&0x80]
    slots=(*rows,absent,9 if 9 not in table else absent)
    specs=[(slot,seat,armed,who,0,system,n) for slot in slots for seat in (0,1) for armed in (0,1)
           for who in victims for system in (1,2)]
    specs+=[(slot,seat,1,victims[(slot+seat+mode)%len(victims)],mode,system,n) for slot in (*rows,absent) for seat in (0,1)
            for mode in range(1,len(MODES)) for system in ((1,2) if slot in weapon else (2,))]
    instructions=compare_entries(specs,(str(n),))
    report=dict(status='passed',elf=PIN,source=n,handler=hex(handler(n)),entries=len(specs),original_instructions=instructions,
                modes=MODES,victims=victims,rows=rows,skipped_rows=skipped,
                source_sha256=sha256((ROOT/'src/victim_script.cpp').read_bytes()).hexdigest(),
                scope='Entry visit of the table-B stub for every row and absent ids. Failure states are constructed directly; '
                      'live throws are covered by probe_fighter_gaps.py.')
    (ROOT/f'outputs/ss6-feasibility/victim_rows_{n:02}_validation.json').write_text(json.dumps(report,indent=2)+'\n')
    print(len(specs),'entries',instructions,'instructions')
if __name__=='__main__':main()
