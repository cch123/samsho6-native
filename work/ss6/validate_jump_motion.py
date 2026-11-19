#!/usr/bin/env python3
"""Compare raw directional jump and airborne attack trajectories with the Japanese ELF."""
import argparse
import hashlib
import itertools
import json
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import struct
import subprocess

from mips_probe import signed
from round_entry_oracle import fixture
from validate_input_features import PADS
from validate_input_lifecycle import Boundary

ROOT=Path(__file__).resolve().parents[2]
WORK=ROOT/'work/ss6'
ASSETS=WORK/'extracted/resources'
EXE=WORK/'build-native/ss6-ground-state-probe'
ELF=WORK/'extracted/SLPS_255.59'
ORIGINAL='72420e74e04d7ac39119d1b6ec7d70ed004fc98c5035fade96e87d05d4b9ffbf'

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def float_word(value):
    return struct.unpack('<I',struct.pack('<f',value))[0]

def from_word(value):
    return struct.unpack('<f',struct.pack('<I',value))[0]

def trajectory(player,relative,attack,when,hold,hit_tick,compare):
    probe,actor,body,battle=fixture(player)
    probe.finite_model=True
    other=0x1c00000+(1-player)*0xf2c
    other_body=body+0x1000
    # The isolated probe supplies one fixed facing. Keep the stationary
    # opponent beyond two diagonal jumps so no camera crossing is required.
    other_x=640 if player==0 else -80
    probe.write(other,other_body,4)
    probe.write(other+4,body+0x2000,4)
    probe.write(other+0x23c,0x1000,4)
    probe.write(other+0xa24,1-player,4)
    probe.write(other_body+0xcc,1-player,4)
    probe.write(battle+0x24c+(1-player)*4,other,4)
    probe.write(actor+4,body+0x3000,4)
    probe.write(body+0x30c4,-1,4)
    instructions=0
    def run(pc,*args,stop=None):
        nonlocal instructions
        _,n=probe.run(pc,args,limit=2_000_000,stop_before=stop or ())
        instructions+=n
    def until(start,end):
        boundary=Boundary(end)
        run(start,stop=boundary)
        assert boundary.stopped==end
    run(0x149008,actor,0)
    run(0x149918,actor)
    run(0x11d8e0,body)
    run(0x179258,actor+0x2c4,actor+0x10c)
    probe.write(body+0x38,0x10000000|(player<<19),4)
    probe.write(actor+0xa08,player,4)
    probe.write(body+0x40,float_word(280),4)
    probe.write(other_body+0x40,float_word(other_x),4)
    probe.write(0x4c38a8,0,4)
    probe.write(battle,4,4)
    probe.write(battle+0x144,120,4)
    for side in range(2):
        struct.pack_into('<8I',probe.memory,0x4eaac0+side*32,*(1<<(8+i) for i in range(8)))
    direction=0x10
    if relative:
        direction|=0x80 if (relative==1)!=(player==1) else 0x40
    commands=[f'reset {player} {player} 280 {other_x}','combat']
    expected=[]
    pad_rows=[]
    previous=0
    for tick in range(120 if hit_tick>=0 else 96 if hold else 76):
        held=(direction if tick==0 or hold else 0)|(attack if tick==when else 0)
        edge=held&~previous
        previous=held
        if tick==hit_tick:
            # A separate whole 14d198 call represents the opponent's confirmed
            # heavy hit. The game's actor/ACT callbacks handle its entire aftermath.
            probe.write(other+0x194,(8<<16)|1,4)
            probe.write(other+0x23c,0x1000,4)
            probe.write(other+0x19a,12,1)
            probe.write(other_body+0x24,189,4)
            run(0x14d198,actor,other_body,0,12,0,0)
            commands.append('hit 12 0 0 0')
        pad_rows.append(len(commands))
        commands.append(f'pad {held} {edge}')
        # 142580 post-contact, body animation/motion, then original stage
        # distance and actor gate/timer/life routines in the scheduler's order.
        probe.put(16,battle+player*4);probe.put(17,3);probe.put(19,0x140000)
        until(0x142580,0x142618)
        run(0x11d730,body);run(0x11d6c8,body)
        delta=128 if probe.read(actor+0x1b4,4) else 256
        probe.write(actor+0x1ac,delta,4);probe.write(body+0x30,delta,4)
        probe.put(11,body);probe.put(14,other_body);probe.put(18,battle)
        until(0x1428f4,0x142918)
        run(0x151b00,actor);run(0x151eb0,actor);run(0x151968,actor)
        pad=PADS+12*player
        probe.write(pad,held,4);probe.write(pad+4,edge,4)
        probe.put(16,1);probe.put(17,actor);probe.put(18,other)
        until(0x1495e8,0x149770)
        run(0x149d08,actor)
        probe.put(17,actor)
        probe.write(0x1fff038,0x1ffff00,8)
        run(0x149790);run(0x149918,actor);run(0x11d8e0,body)
        word=lambda a:probe.read(a,4)
        words=[word(actor+0x194),word(actor+0x18c),
               signed(probe.read(actor+0x190,2),16),signed(probe.read(actor+0x192,2),16),
               probe.read(actor+0x19a,1),*[word(actor+off) for off in (0x23c,0x244,0x248,0xc0,0x15c,0x160,0x164)],
               *[word(actor+off) for off in range(0x260,0x27c,4)],
               *[signed(word(actor+off),32) for off in range(0x1b0,0x23c,4)],
               *[word(body+off) for off in (0x24,0x28,0x2c,0xc0,0x38,0x104,0x108)],
               probe.read(body+0xfe,2),
               *[signed(word(body+off),32) for off in range(0x4c,0x64,4)],word(body+0x40),word(body+0x44)]
        expected.append(words)
    if compare:
        result=subprocess.run([EXE,ASSETS],input='\n'.join(commands)+'\n',capture_output=True,text=True)
        assert result.returncode==0,(player,relative,attack,when,result.stderr)
        output=result.stdout.splitlines()
        actual=[list(map(int,output[i].split()))[:70] for i in pad_rows]
        assert len(actual)==len(expected)
        for i,(ours,theirs) in enumerate(zip(actual,expected)):
            assert ours==theirs,(player,relative,attack,when,hold,i,[(j,x,y) for j,(x,y) in enumerate(zip(ours,theirs)) if x!=y])
    actions=list(dict.fromkeys(row[54] for row in expected))
    expected_jump={0:14,1:18,-1:22}[relative]
    assert expected_jump in actions and 26 in actions,(player,relative,attack,when,actions)
    attack_action={0x100:209,0x200:210,0x400:211,0x800:217}.get(attack)
    if attack_action is not None and attack!=0x800 and relative:attack_action+=3
    if attack_action is not None:assert attack_action in actions,(player,relative,attack,when,actions)
    if hit_tick>=0:assert 378 in actions and (74<<16|2) in {row[0] for row in expected},(hit_tick,actions)
    if not hold:assert expected[-1][0]==0 and from_word(expected[-1][69])==0,(actions,expected[-1])
    return dict(player=player,direction=relative,attack=hex(attack),when=when,held=hold,hit_tick=hit_tick,
                ticks=len(expected),actions=actions,peak=max(from_word(row[69]) for row in expected),
                final_x=from_word(expected[-1][68]),instructions=instructions)

def run_case(args):
    return trajectory(*args)

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--quick',action='store_true')
    parser.add_argument('--original-only',action='store_true')
    parser.add_argument('--jobs',type=int,default=4)
    args=parser.parse_args()
    assert digest(ELF)==ORIGINAL
    arguments=[]
    for player,relative in itertools.product(range(1 if args.quick else 2),(0,1,-1)):
        setups=[(0,0,False),(0x400,7,False)] if args.quick else [
            (0,0,False),(0,0,True),(0x100,6,False),(0x200,13,False),(0x400,7,False),(0x400,25,False),(0x800,10,False)]
        for attack,when,hold in setups:
            arguments.append((player,relative,attack,when,hold,-1,not args.original_only))
        if not args.quick or relative==0:
            arguments.append((player,relative,0x400,7,False,12,not args.original_only))
            arguments.append((player,relative,0,0,False,27,not args.original_only))
    cases=[]
    with ProcessPoolExecutor(max_workers=args.jobs) as executor:
        for case in executor.map(run_case,arguments):
            print(case,flush=True)
            cases.append(case)
    if args.quick or args.original_only:return
    report=dict(status='passed',cases=cases,ticks=sum(c['ticks'] for c in cases),
                original_instructions=sum(c['instructions'] for c in cases),elf_sha256=ORIGINAL,
                native_sha256=digest(EXE),validator_sha256=digest(Path(__file__)),
                scope='Resource00 armed system0, raw human input and ordinary actor/body callbacks. '
                      'Both players, neutral/forward/backward, held retrigger, aerial slash and kick, '
                      'ACT motion and clock, interruption by a confirmed heavy hit during flight and attack, '
                      'airborne hurt and landing, grounded recovery. Stationary opponent; '
                      'no hardware raster, two-body contact resolution or camera clamp in this comparison.')
    (ROOT/'outputs/ss6-feasibility/jump_motion_validation.json').write_text(json.dumps(report,indent=2)+'\n')

if __name__=='__main__':
    main()
