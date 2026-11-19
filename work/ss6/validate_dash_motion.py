#!/usr/bin/env python3
"""Compare native armed Haohmaru 66/44 to the original input and actor callbacks."""
import argparse
from concurrent.futures import ProcessPoolExecutor
import hashlib
import json
import struct
import subprocess
import tempfile
import shutil
from pathlib import Path

from mips_probe import signed
from round_entry_oracle import fixture, ROOT
from validate_input_features import PADS
from validate_input_lifecycle import Boundary

ASSETS = ROOT / 'work/ss6/extracted/resources'
ELF = ASSETS.parent / 'SLPS_255.59'
PIN = '72420e74e04d7ac39119d1b6ec7d70ed004fc98c5035fade96e87d05d4b9ffbf'
PROBE = ROOT / 'work/ss6/build-native/ss6-ground-state-probe'
REPORT = ROOT / 'outputs/ss6-feasibility/dash_motion_validation.json'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Original:
    def __init__(self, player, character=0):
        self.player = player
        p, a, o, b = fixture(player, character)
        self.p, self.a, self.o, self.b = p, a, o, b
        self.other = 0x1c00000 + (1-player)*0xf2c
        self.instructions = self.previous = 0
        p.finite_model = True
        p.write(self.other, o+0x1000, 4)
        p.write(self.other+4, o+0x2000, 4)
        p.write(self.other+0x23c, 0x1000, 4)
        p.write(self.other+0xa24, 1-player, 4)
        p.write(o+0x10cc, 1-player, 4)
        p.write(b+0x24c+(1-player)*4, self.other, 4)
        p.write(a+4, o+0x3000, 4)
        p.write(o+0x30c4, -1, 4)
        self.run(0x149008, a, 0)
        self.run(0x149918, a)
        self.run(0x11d8e0, o)
        self.run(0x179258, a+0x2c4, a+0x10c)
        p.write(0x4c38a8, 0, 4)
        p.write(b, 4, 4)
        p.write(b+0x18, 0, 4)
        p.write(b+0x144, 380, 4)
        p.write(o+0x38, 0x10000000 | player<<19, 4)
        p.write(a+0xa08, player, 4)
        struct.pack_into('<f', p.memory, o+0x40, 500 if player else 120)
        struct.pack_into('<f', p.memory, o+0x1040, 120 if player else 500)
        for side in range(2):
            struct.pack_into('<8I', p.memory, 0x4eaac0+side*32, *(1<<n for n in range(8,16)))

    def run(self, fn, *args, stops=()):
        _, count = self.p.run(fn, args, limit=2_000_000, stop_before=stops)
        self.instructions += count

    def slice(self, start, end):
        stop = Boundary(end)
        self.run(start, stops=stop)
        assert stop.stopped == end

    def frame(self, held):
        p, a, o, b = self.p, self.a, self.o, self.b
        p.put(16, b+4*self.player)
        p.put(17, 3)
        p.put(19, 0x140000)
        self.slice(0x142580, 0x142618)
        self.run(0x11d730, o)
        self.run(0x11d6c8, o)
        delta = 128 if p.read(a+0x1b4, 4) else 256
        p.write(a+0x1ac, delta, 4)
        p.write(o+0x30, delta, 4)
        p.put(11, o)
        p.put(14, o+0x1000)
        p.put(18, b)
        self.slice(0x1428f4, 0x142918)
        self.run(0x151b00, a)
        self.run(0x151eb0, a)
        self.run(0x151968, a)
        pad = PADS + self.player*12
        p.write(pad, held, 4)
        p.write(pad+4, held & ~self.previous, 4)
        self.previous = held
        p.put(16, 1)
        p.put(17, a)
        p.put(18, self.other)
        self.slice(0x1495e8, 0x149770)
        self.run(0x149d08, a)
        p.put(17, a)
        p.write(0x1fff038, 0x1ffff00, 8)
        self.run(0x149790)
        self.run(0x149918, a)
        self.run(0x11d8e0, o)
        values = [p.read(a+0x194,4), p.read(a+0x18c,4), signed(p.read(a+0x190,2),16),
                  signed(p.read(a+0x192,2),16), p.read(a+0x19a,1)]
        values += [p.read(a+ofs,4) for ofs in (0x23c,0x244,0x248,0xc0)]
        values += [p.read(a+ofs,4) for ofs in (*range(0x15c,0x168,4), *range(0x260,0x27c,4))]
        values += [signed(p.read(a+0x1b0+index*4,4),32) for index in range(35)]
        values += [p.read(o+ofs,4) for ofs in (0x24,0x28,0x2c,0xc0,0x38,0x104,0x108)]
        values += [p.read(o+0xfe,2)]
        values += [signed(p.read(o+ofs,4),32) for ofs in range(0x4c,0x64,4)]
        values += [p.read(o+0x40,4),p.read(o+0x44,4)]
        values += [p.read(a+0x2c4+i*4,4) for i in range(171)]
        return values


def trajectories(player):
    forward, back, down = (0x40,0x80,0x20) if player else (0x80,0x40,0x20)
    run = [0,forward,0,forward]
    backstep = [0,back,0,back]
    neutral = [0]*70
    yield 'run-long-hold', run+[forward]*42+neutral, {28,34}
    yield 'run-tap', run+neutral, {28,34}
    yield 'run-reverse', run+[forward]*12+[back]*14+neutral, {28,34}
    yield 'run-down', run+[forward]*12+[down]*24+neutral, {28,34}
    yield 'backstep-neutral', backstep+neutral, {36}
    yield 'backstep-crouch', backstep+[down]*40+neutral, {36}
    yield 'single-forward', [forward]*30+neutral, set()
    yield 'single-back', [back]*30+neutral, set()
    yield 'late-second-forward', [forward]+[0]*45+[forward]+neutral, set()
    yield 'late-second-back', [back]+[0]*45+[back]+neutral, set()
    for direction,prefix,action in ((forward,'forward',28),(back,'back',36)):
        for gap,required in ((11,{action}),(12,set())):
            yield f'{prefix}-gap-{gap}',[0,direction]+[0]*gap+[direction]+neutral,required
    for index, button in enumerate((0x100,0x200,0x400,0x800)):
        yield f'run-button-{index}', run+[forward]*12+[forward|button]+neutral, {28,219+index}


def original_trace(case):
    player,label,held,required=case
    oracle=Original(player)
    commands=[f'reset {player} {player} {500 if player else 120} {120 if player else 500}','combat']
    expected=[]
    for bits in held:
        commands.append(f'pad {bits} {bits & ~oracle.previous}')
        expected.append(oracle.frame(bits))
    actions={row[54] for row in expected}
    assert required <= actions,(player,label,required,actions)
    if not required:assert not actions & {28,34,36},(player,label,actions)
    summary=dict(player=player,case=label,frames=len(expected),actions=sorted(actions),
                 peak_y=max(struct.unpack('<f',struct.pack('<I',r[69]))[0] for r in expected),
                 final_x=struct.unpack('<f',struct.pack('<I',expected[-1][68]))[0],
                 original_instructions=oracle.instructions)
    return summary,commands,expected


def check_native(probe,trace):
    summary,commands,expected=trace
    result=subprocess.run([probe,ASSETS],text=True,capture_output=True,input='\n'.join(commands)+'\n')
    assert result.returncode==0,(summary,result.stderr)
    rows=result.stdout.splitlines()[2:]
    assert len(rows)==len(expected)
    for tick,(line,want) in enumerate(zip(rows,expected)):
        got=list(map(int,line.split(maxsplit=len(want))[:len(want)]))
        differences=[(i,x,y) for i,(x,y) in enumerate(zip(got,want)) if x!=y]
        assert not differences,(summary['player'],summary['case'],tick,differences[:15])


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--original-only',action='store_true');parser.add_argument('--case')
    args=parser.parse_args();assert digest(ELF)==PIN
    cases=[(i,name,masks,required) for i in range(2) for name,masks,required in trajectories(i) if args.case in (None,name)]
    assert cases
    # Generate independent original traces before taking the native binary
    # snapshot. An ordinary parallel build can replace the executable path.
    with ProcessPoolExecutor(max_workers=min(4,len(cases))) as pool:
        traces=[]
        for trace in pool.map(original_trace,cases):
            traces.append(trace);summary=trace[0];print(summary['player'],summary['case'],summary['actions'],flush=True)
    if args.original_only:return
    with tempfile.TemporaryDirectory() as tmp:
        probe=Path(tmp)/'ground-state-probe';shutil.copy2(PROBE,probe);probe_digest=digest(probe)
        for trace in traces:check_native(probe,trace)
    if args.case:return
    results=[trace[0] for trace in traces]
    report=dict(status='passed',cases=results,snapshots=sum(r['frames'] for r in results),
                original_instructions=sum(r['original_instructions'] for r in results),
                elf_sha256=PIN,probe_sha256=probe_digest,validator_sha256=digest(Path(__file__)),
                scope='Resource00/system0 matched software-pad input, request, actor update and body commits. '
                      'Compares all 171 input features, actor state/conditions/callbacks, timers, body flags, '
                      'animation clock, fixed-point motion, X/Y. Independent actor fixtures with fixed opponent '
                      'position; stage clamps, contact resolution and sound are separate.')
    REPORT.write_text(json.dumps(report,indent=2)+'\n');print(f"{len(results)} cases, {report['snapshots']} snapshots PASS")


if __name__=='__main__':
    main()
