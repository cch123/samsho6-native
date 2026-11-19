#!/usr/bin/env python3
"""Cross-action state and ACT jumps against original unmodified EE functions."""
import hashlib
import json
import random
import struct
import subprocess
import sys
from pathlib import Path
from mips_probe import idle_fixture,signed

ROOT=Path(__file__).resolve().parents[2]
ASSETS=ROOT/'work/ss6/extracted/resources'

def main():
    raw=(ROOT/'work/ss6/extracted/SLPS_255.59').read_bytes()
    p,o=idle_fixture(raw,(ASSETS/'aid_00.bin').read_bytes(),(ASSETS/'act_00.bin').read_bytes())
    p.write(o+0xc8,1,4); p.write(o+0x104,0x200,4)
    p.run(0x120390,[o,0])
    commands,expected=[],[]
    fields=[0x24,0x28,0x2c,0xc0,0x3c,0x38,0x104,0x108,0xc4]+list(range(0x4c,0x64,4))+[0x40,0x44]
    def command(op,*values):
        commands.append(' '.join(map(str,[op,*values])))
        if op=='flags':
            for offset,v in zip([0x38,0x104,0x108],values):p.write(o+offset,v,4)
        elif op=='start': p.run(0x120390,[o,values[0]])
        elif op=='stop': p.run(0x11d990,[o])
        elif op=='motion':
            for offset,v in zip(range(0x4c,0x64,4),values[:6]):p.write(o+offset,v,4)
            for offset,v in zip([0x40,0x44],values[6:]):p.write(o+offset,struct.unpack('<I',struct.pack('<f',v))[0],4)
        elif op=='advance':
            p.write(o+0x30,values[0],4)
            p.run(0x120618,[o]);p.run(0x120ac8,[o])
        expected.append([signed(p.read(o+off,4),32) if 0x4c<=off<0x64 else p.read(o+off,4) for off in fields])
    rng=random.Random(120390)
    ground='--ground-transitions' in sys.argv
    actions=[0,1,2,3,4,5,6,7,8,9,10,11,12,13,141,185,186,278,279,282,283,286,287,288,289,290,291,292,293,
             338,339,344,345,350,351,362,368,369,143,189,190,191,192,195,196,342,348,354,360,366,372,48,49,50,51,52,53,54,55,382,383,384,385,400,401,402,403,492,493,494,495,496,497,498,499,500,501]
    if ground:actions=[44,45,46,47,280,281,284,285]
    for action in actions:
        if action==48:
            exact_states=len(expected)
            # Raw playback intentionally omits the actor floor clamp. Long
            # airborne traces with fractional/high deltas can round floats;
            # opt in explicitly, retaining the old exact-only regression.
            p.finite_model=True
        for delta in [0,1,128,255,256,300,512,2048]:
            flags=0x10000000|(rng.randrange(2)<<19)|(rng.randrange(2)<<18)
            command('flags',flags,0x6000200,rng.randrange(2)<<9)
            command('motion',0,544*256,0,0,0,0,13.25,-4.5)
            command('start',action)
            for _ in range(65): command('advance',delta)
    # Switching clips does not clear residual movement; stopping is a distinct
    # actor operation. Include interrupted clips and already-ended loops.
    for _ in range(512):
        op=rng.randrange(5)
        if op==0:command('start',rng.choice(actions))
        elif op==1:command('stop')
        else:command('advance',rng.choice([0,128,256,300,512]))
    binary=ROOT/'work/ss6/build-native/ss6-action-sequence-probe'
    result=subprocess.run([str(binary),str(ASSETS)],input='\n'.join(commands)+'\n',text=True,capture_output=True,check=True)
    actual=[list(map(int,row.split())) for row in result.stdout.splitlines()]
    assert len(actual)==len(expected)
    for i,(a,e) in enumerate(zip(actual,expected)):
        assert a==e,(i,commands[max(0,i-3):i+1],a,e)
    if ground:exact_states=len(expected)
    report=dict(status='passed',states=len(expected),actions=actions,
                exact_states=exact_states,finite_model_states=len(expected)-exact_states,
                elf_sha256=hashlib.sha256(raw).hexdigest(),native_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
                scope='0x120390 start, 0x11d990 stop, 0x120618 movement, 0x120ac8 advance including landing gates and ACT jumps; original regression exact FP, added airborne/high-delta traces explicit finite FP model, not hardware proof; no actor input or collision dispatch')
    if ground:report['scope']='Additional armed/unarmed ground turn and guard-exit ACT resources: whole120390/11d990/120618/120ac8, both facing/vertical-flip flags and8 clock deltas including zero/fractional/high, terminal jumps and interrupted cross-action playback. Exact arithmetic fixtures, not full unarmed actor or physical GS validation.'
    (ROOT/'outputs/ss6-feasibility'/('ground_action_sequence_validation.json' if ground else 'action_sequence_validation.json')).write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))

if __name__=='__main__': main()
