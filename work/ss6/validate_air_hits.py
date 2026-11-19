#!/usr/bin/env python3
"""Check airborne slash reaction selection, inherited hit-pause and the hurt ACT."""
import itertools
import json
from pathlib import Path
import subprocess

from mips_probe import Probe, signed
from validate_jump_motion import ASSETS, ELF, ORIGINAL, ROOT, WORK, digest

def match_replays(exe):
    # Each case starts with the ordinary two-player round controller and its
    # opening positions, then sends raw pad masks through the window's match.
    cases=[]
    for player,case in itertools.product((0,1),('vertical','forward','air','guard','miss')):
        forward=0x80 if player==0 else 0x40
        jump=0x10 if case=='vertical' else (0x10|forward)
        when={'vertical':20,'forward':19,'air':15,'guard':19,'miss':7}[case]
        walk=45 if case=='vertical' else 0
        commands=['500 0 0']
        def pad(n,left,right):
            if player==1:left,right=right,left
            commands.append(f'{n} {left} {right}')
        if walk:pad(walk,forward,0)
        for tick in range(115):
            attacker=jump if tick==0 else 0x400 if tick==when else 0
            defender=0x10 if case=='air' and tick==0 else forward if case=='guard' and 26<=tick<=42 else 0
            pad(1,attacker,defender)
        result=subprocess.run([exe,ASSETS],input='\n'.join(commands)+'\n',text=True,capture_output=True)
        assert result.returncode==0,(player,case,result.stderr)
        rows=[line.split() for line in result.stdout.splitlines()]
        assert len(rows)==len(commands)
        a,b=3+10*player,3+10*(1-player)
        actions=list(dict.fromkeys(int(row[a+2]) for row in rows))
        targets=list(dict.fromkeys(int(row[b+2]) for row in rows))
        last=rows[-1]
        assert (211 if case=='vertical' else 214) in actions and 26 in actions
        assert last[a+2]==last[b+2]=='0' and last[a+5]==last[b+5]=='0'
        hit=int(last[a+7]);guard=int(last[a+8]);hp=int(last[b+6])
        if case in ('vertical','forward','air'):
            assert (hit,guard,hp)==(1,0,172) and (378 if case=='air' else 360) in targets
        elif case=='guard':
            assert (hit,guard,hp)==(0,1,200) and 288 in targets
        else:
            assert (hit,guard,hp)==(0,0,200) and targets==[0]
        contact=next((int(row[0])-500-walk for row in rows if int(row[a+7]) or int(row[a+8])),None)
        cases.append(dict(player=player,case=case,contact_tick=contact,actions=actions,target_actions=targets,
                          hits=hit,guards=guard,defender_life=hp))
    return cases

def main():
    assert digest(ELF)==ORIGINAL
    probe=Probe(ELF.read_bytes())
    source,target,source_body,target_body,context=0x1c00000,0x1c00f2c,0x1e00000,0x1e01000,0x1e02000
    probe.write(0x4d3d08,source,4)
    probe.write(context,target,4)
    probe.write(context+4,source,4)
    expected=[]
    commands=[]
    secondary=set()
    instructions=0
    for raw,part,alternate,table,armed,shield,source_air in itertools.product(
            (10,11,12),range(3),(0,2),(0,2),(0,1),(0,1),(0,1)):
        probe.memory[source:target+0xf2c]=bytes(2*0xf2c)
        for actor,obj,side in ((source,source_body,0),(target,target_body,1)):
            probe.write(actor,obj,4)
            probe.write(actor+0xa24,side,4)
            probe.write(actor+0x190,-1,4)
            probe.write(actor+0xa3c,-1,4)
            probe.write(obj+0xcc,side,4)
        strength=raw-10
        previous=74
        # In the original the attack-state metadata provides the strength bits.
        # Set a competing crouch/other posture so the airborne precedence is tested.
        flags=0x58|(0x1000 if armed else 0)|(0x02000000 if shield else 0)
        probe.write(source+0x194,1|((4*strength)<<16),4)
        probe.write(source+0x19a,8+2*strength,1)
        probe.write(source+0x23c,0x1000|(0x20 if source_air else 0),4)
        probe.write(source+0x248,0x1234,4)
        probe.write(target+0x194,table,4)
        probe.write(target+0x23c,flags,4)
        probe.write(target+0x24c,alternate,1)
        probe.write(target+0x255,previous,1)
        probe.write(target+0x258,1,4)
        _,n=probe.run(0x14d198,[target,source_body,0,raw,part,1])
        instructions+=n
        state=probe.read(target+0x255,1)
        assert state==74
        secondary.add(probe.read(target+0x256,1))
        # 175538 calls 1708d8 with variant zero and no callback override.
        _,n=probe.run(0x1708d8,[context,0,0])
        instructions+=n
        expected.append([probe.read(target+0x23c,4),signed(probe.read(target+0x190,2),16),
            signed(probe.read(target+0x192,2),16),probe.read(target+0x18c,4),state,
            probe.read(target+0x256,1),probe.read(source+0x1b0,4),probe.read(source+0x1b4,4),
            probe.read(target+0x1b0,4),probe.read(target+0x1b4,4),probe.read(target+0xa3c,4),
            probe.read(target+0x258,4),probe.read(source+0x248,4)])
        commands.append(' '.join(map(str,[flags,alternate,previous,table,part,1,source_air,raw,strength,1,0x1234])))
    exe=WORK/'build-native/ss6-reaction-probe'
    result=subprocess.run([exe,ASSETS,'--ground'],input='\n'.join(commands)+'\n',text=True,capture_output=True)
    assert result.returncode==0,result.stderr
    actual=[list(map(int,line.split())) for line in result.stdout.splitlines()]
    assert len(actual)==len(expected)
    for cmd,ours,theirs in zip(commands,actual,expected):
        assert ours==theirs,(cmd,ours,theirs)
    match=WORK/'build-native/ss6-match-replay'
    report=dict(status='passed',cases=len(expected),secondary_states=sorted(secondary),
                original_instructions=instructions,elf_sha256=ORIGINAL,native_sha256=digest(exe),
                validator_sha256=digest(Path(__file__)),native_match_sha256=digest(match),replays=match_replays(match),
                scope='Whole 14d198 and 1708d8 variant zero for aerial targets receiving raw strikes 10/11/12. '
                      'Source and target pause timers, source flags, pending target state, history and '
                      'armed/unarmed hurt ACT. Separate native end-to-end replays exercise two mirror-match '
                      'players, vertical and diagonal heavy hits, hit in flight, standing guard and whiff '
                      'through geometry, HP, landing and recovery. Those full matches are native regressions.')
    (ROOT/'outputs/ss6-feasibility/air_hit_validation.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))

if __name__=='__main__':
    main()
