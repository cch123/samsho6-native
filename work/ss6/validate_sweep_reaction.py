#!/usr/bin/env python3
"""Match sweep reactions, two separate fall rows, and their complete recovery."""
import hashlib
import itertools
import json
from validate_haohmaru_special import ACTORS, ELF, OBJECTS, ROOT, SOURCE_HASH, Probe, actor_trace, buffered_stdout, signed
from validate_heavy_reactions import compare


def main():
    assert hashlib.sha256(ELF.read_bytes()).hexdigest()==SOURCE_HASH
    p=Probe(ELF.read_bytes(),finite_model=True)
    buffered_stdout(p)
    source,target=ACTORS,ACTORS+0xf2c
    ctx=0x1e02000
    p.write(0x4d3d08,source,4)
    commands,expected=[],[]
    for part,posture,alternate,table,armed,state in itertools.product(
            range(3),(0,8,16,64),(0,2),(0,2),(0,1),(11,17)):
        p.memory[source:target+0xf2c]=bytes(2*0xf2c)
        for a,obj,slot in ((source,OBJECTS[0],0),(target,OBJECTS[1],1)):
            p.write(a,obj,4);p.write(a+0xa24,slot,4)
            p.write(a+0x190,-1,4);p.write(a+0xa3c,-1,4)
            p.write(obj+0xcc,slot,4)
        flags=posture | armed<<12
        p.write(source+0x194,state<<16|1,4)
        p.write(source+0x19a,8,1);p.write(source+0x23c,0x1000,4)
        p.write(target+0x194,table,4);p.write(target+0x23c,flags,4)
        p.write(target+0x24c,alternate,1);p.write(target+0x258,1,4)
        p.write(ctx,target,4);p.write(ctx+4,source,4)
        p.run(0x14d198,[target,OBJECTS[0],0,25,part,0])
        hurt=p.read(target+0x255,1)
        assert hurt in (59,60)
        p.run(0x171418,[ctx,12+(hurt==60)])
        expected.append([p.read(target+0x23c,4),signed(p.read(target+0x190,2),16),
                         signed(p.read(target+0x192,2),16),p.read(target+0x18c,4),hurt,
                         p.read(target+0x256,1),p.read(source+0x1b0,4),p.read(source+0x1b4,4),
                         p.read(target+0x1b0,4),p.read(target+0x1b4,4),p.read(target+0xa3c,4),
                         p.read(target+0x258,4),p.read(source+0x248,4)])
        commands.append(f'{flags} {alternate} 0 {table} {part} 0 0 25 0 1 0')
    compare('--ground',commands,expected)
    traces=[]
    for state,slot in itertools.product((59,60),range(2)):
        ticks,ins,actions=actor_trace(state,slot,fall=True)
        traces.append(dict(state=state,player=slot+1,ticks=ticks,instructions=ins,actions=actions))
    report=dict(status='passed',elf_sha256=SOURCE_HASH,raw25_cases=len(commands),actor_traces=traces,
                scope='Resource00/system0. Whole 14d198 raw25 hit plus 171418 callback entry, three body regions, four postures, either facing flag, armed/unarmed variants and repeated-hit history. Four whole player-update traces include fall, first/second landing, downed, get-up and return to idle.')
    (ROOT/'outputs/ss6-feasibility/sweep_reaction_validation.json').write_text(json.dumps(report,indent=2)+'\n')
    print(f'{len(commands)} original/native sweep reactions, {sum(t["ticks"] for t in traces)} recovery ticks')


if __name__=='__main__':
    main()
