#!/usr/bin/env python3
"""Differential checks against bounded execution of the user's original ELF.

No original code is patched: synthetic ACT records test the command decoder;
real ACT/AID/JDG resources test integrated action traces. Sound uses the game's
own mute bit. The probe rejects inexact or exceptional floating-point math.
"""
import csv
import hashlib
import io
import json
import random
import struct
import subprocess
from pathlib import Path
from mips_probe import idle_fixture, signed
from validate_idle import runner_checks

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT/'work/ss6/extracted/resources'
OUT = ROOT/'outputs/ss6-feasibility'
BUILD = ROOT/'work/ss6/build-native'


def main():
    executable = (ROOT/'work/ss6/extracted/SLPS_255.59').read_bytes()
    aid,act,jdg = [(ASSETS/f'{name}_00.bin').read_bytes() for name in ['aid','act','jdg']]
    runner_checks(executable)
    probe,obj = idle_fixture(executable,aid,act)
    # Fail-closed checks for the newly admitted FPU subset and second multiplier.
    probe.lo=77; probe.hi=88
    start=0x1d00000
    for i,w in enumerate([0x2408fffe,0x24090003,(0x1c<<26)|(8<<21)|(9<<16)|(2<<11)|0x18,0x03e00008,0]):
        probe.write(start+i*4,w,4)
    value,_=probe.run(start)
    assert signed(value,64)==-6 and (probe.lo,probe.hi)==(77,88) and signed(probe.lo1,64)==-6
    try: probe.put_exact_float(0,1+2**-30)
    except NotImplementedError: pass
    else: raise AssertionError('Inexact floating point must be refused')

    rng=random.Random(0x25559)
    lines,expected=[],[]
    counts={}
    for kind in range(19):
        for reverse in [0,1]:
            for suppress in [0,1]:
                for _ in range(8):
                    state=[rng.randint(-2**31,2**31-1) for _ in range(6)]
                    values=[rng.randint(-32768,32767) for _ in range(6)]
                    for i,v in enumerate(state): probe.write(obj+0x4c+i*4,v,4)
                    for off in [0x24,0x28,0xc0,0xfe]: probe.write(obj+off,0,4 if off!=0xfe else 2)
                    probe.write(obj+0x104,0x80 if suppress else 0,4)
                    probe.write(obj+0x108,0x200 if reverse else 0,4)
                    for i,v in enumerate([kind]+values): probe.write(0x1700000+0x20+i*2,v,2)
                    probe.run(0x120d10,[obj])
                    lines.append('command '+' '.join(map(str,state+[kind]+values+[reverse,suppress])))
                    expected.append([signed(probe.read(obj+0x4c+i*4,4),32) for i in range(6)])
    counts['motion_command_cases']=len(lines)
    for _ in range(1024):
        state=[rng.randint(-2**31,2**31-1) for _ in range(6)]
        delta=rng.choice([0,1,64,128,255,256,300,512,2048,65535])
        for i,v in enumerate(state): probe.write(obj+0x4c+i*4,v,4)
        probe.write(obj+0x104,0,4); probe.write(obj+0x38,0,4); probe.write(obj+0x30,delta,4)
        probe.run(0x120618,[obj])
        lines.append('integrate '+' '.join(map(str,state+[delta])))
        expected.append([signed(probe.read(obj+0x4c+i*4,4),32) for i in range(6)])
    counts['integer_integration_cases']=1024

    obj2,rect,defn=0x1c00000,0x1c01000,0x1c02000
    for _ in range(1024):
        coords=[rng.randint(-32768,32767) for _ in range(4)]
        x,y=[rng.randint(-4000,4000)/8 for _ in range(2)]
        mx,my=[rng.randint(0,1) for _ in range(2)]
        for i,v in enumerate(coords): probe.write(defn+6+i*2,v,2)
        probe.write(obj2+0x38,(mx<<19)|(my<<18),4)
        probe.write(obj2+0x40,struct.unpack('<I',struct.pack('<f',x))[0],4)
        probe.write(obj2+0x44,struct.unpack('<I',struct.pack('<f',y))[0],4)
        probe.run(0x153170,[rect,obj2,defn])
        lines.append('rect '+' '.join(map(str,coords+[x,y,mx,my])))
        expected.append([signed(probe.read(rect+i*4,4),32) for i in range(4)])
    counts['world_rectangle_cases']=1024

    fixtures=[([0,10,0,10],[10,20,10,20]),([0,0,0,0],[0,0,0,0]),
              ([-9,-3,-7,-1],[-5,2,-3,3]),([0,10,0,10],[11,20,0,10])]
    for _ in range(2048):
        a=sorted([rng.randint(-100,100) for _ in range(2)])+sorted([rng.randint(-100,100) for _ in range(2)])
        b=sorted([rng.randint(-100,100) for _ in range(2)])+sorted([rng.randint(-100,100) for _ in range(2)])
        fixtures.append((a,b))
    for a,b in fixtures:
        for i,v in enumerate(a): probe.write(obj2+i*4,v,4)
        for i,v in enumerate(b): probe.write(defn+i*4,v,4)
        for i,v in enumerate([0,123,456,789]): probe.write(rect+i*4,v,4)
        probe.run(0x1532d0,[rect,obj2,defn])
        lines.append('intersect '+' '.join(map(str,a+b)))
        expected.append([signed(probe.read(rect+i*4,4),32) for i in range(4)])
    counts['inclusive_intersection_cases']=len(fixtures)
    output=subprocess.run([str(BUILD/'ss6-mechanics-probe')],input='\n'.join(lines)+'\n',capture_output=True,text=True,check=True)
    actual=[[int(x) for x in row.split()] for row in output.stdout.splitlines()]
    assert len(actual)==len(expected)
    for i,(a,e) in enumerate(zip(actual,expected)):
        assert a==e,(lines[i],a,e)

    traces=[]
    for action in [0,1,10,11,12,13,185,286,287,290,291]:
        for delta in [0,1,128,255,256,300,512,2048,65535]:
            updates=256
            native=subprocess.run([str(BUILD/'ss6-runtime-trace'),str(ASSETS),str(updates),str(delta),str(action)],capture_output=True,text=True,check=True)
            rows=list(csv.DictReader(io.StringIO(native.stdout)))
            assert len(rows)==updates+1
            p,o=idle_fixture(executable,aid,act,delta)
            p.write(o+0xc8,1,4)
            p.write(o+0x104,0x200,4) # Original mute bit, without stubbing any call.
            p.memory[0x1800000:0x1800000+len(jdg)]=jdg
            p.write(0x4751e0,0x1800000,4)
            _,instructions=p.run(0x120390,[o,action])
            for tick,row in enumerate(rows):
                e={k:p.read(o+off,4) for k,off in dict(step=0x28,time=0x2c,end=0xc0,control=0x3c,flags=0x38,x_bits=0x40,y_bits=0x44).items()}
                e.update({k:signed(p.read(o+0x4c+i*4,4),32) for i,k in enumerate(['dx','vx','ax','dy','vy','ay'])})
                p.run(0x152fd8,[o+0xb8,0,action,e['step']])
                count=p.read(o+0xba,1)
                first,_=p.run(0x11db40,[o,0])
                e.update(jdg_count=count,jdg_first=(first-0x1800000)//16 if count else -1)
                a={k:int(row[k]) for k in e}
                assert a==e,(action,delta,tick,a,e)
                if tick!=updates:
                    _,n=p.run(0x120618,[o]); instructions+=n
                    _,n=p.run(0x120ac8,[o]); instructions+=n
            traces.append(dict(action=action,delta=delta,states=len(rows),original_instructions=instructions))
    counts['action_states_compared']=sum(t['states'] for t in traces)
    report=dict(all_passed=True,**counts,traces=traces,
                elf_sha256=hashlib.sha256(executable).hexdigest(),
                probe_sha256=hashlib.sha256((BUILD/'ss6-mechanics-probe').read_bytes()).hexdigest(),
                trace_sha256=hashlib.sha256((BUILD/'ss6-runtime-trace').read_bytes()).hexdigest(),
                scope='Ordinary clock, selected actions, movement command arithmetic, raw JDG rectangles and inclusive geometry. Audio muted by original object flag. No input-state machine, damage, hitstop, GS output or hardware equivalence claim.')
    (OUT/'mechanics_validation.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='traces'},indent=2))


if __name__=='__main__': main()
