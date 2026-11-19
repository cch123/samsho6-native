#!/usr/bin/env python3
"""Compare the native idle clock with executed original integer instructions."""
import csv
import hashlib
import io
import json
import struct
import subprocess
from pathlib import Path
from mips_probe import Probe, idle_fixture, MASK64

ROOT = Path(__file__).resolve().parents[2]


def runner_checks(executable):
    probe = Probe(executable)
    start = 0x1d00000
    # A not-taken branch-likely annuls its delay slot; JR still executes its
    # delay slot. The animation routines use both behaviors extensively.
    words = [0x24080001,0x51000002,0x24020063,0x24020007,0x03e00008,0x24420001]
    for i,w in enumerate(words): probe.write(start+i*4,w,4)
    value,_ = probe.run(start)
    assert value == 8
    # Taken BEQ executes the slot before its target, including side effects.
    words = [0x10000002,0x24020003,0x24020063,0x24420004,0x03e00008,0x24420001]
    for i,w in enumerate(words): probe.write(start+i*4,w,4)
    value,_ = probe.run(start)
    assert value == 8
    words = [0x2408fffe,0x24090003,(8<<21)|(9<<16)|(2<<11)|0x18,0x03e00008,0]
    for i,w in enumerate(words): probe.write(start+i*4,w,4)
    value,_ = probe.run(start)
    assert value == (-6 & MASK64) and probe.hi == MASK64


def main():
    assets = ROOT/'work/ss6/extracted/resources'
    executable = (ROOT/'work/ss6/extracted/SLPS_255.59').read_bytes()
    runner_checks(executable)
    aid, act = (assets/'aid_00.bin').read_bytes(), (assets/'act_00.bin').read_bytes()
    binary = ROOT/'work/ss6/build-native/ss6-runtime-trace'
    results, normal_boundaries = [], []
    for delta in [0,1,64,128,255,256,300,512,2048,65535]:
        updates = 512
        native = subprocess.run([str(binary),str(assets),str(updates),str(delta)],capture_output=True,text=True,check=True)
        rows = list(csv.DictReader(io.StringIO(native.stdout)))
        assert len(rows) == updates+1
        original, obj = idle_fixture(executable,aid,act,delta)
        executed, previous = 0, -1
        for tick,row in enumerate(rows):
            expected = dict(step=original.read(obj+0x28,4),time=original.read(obj+0x2c,4),end=original.read(obj+0xc0,4))
            actual = {k:int(row[k]) for k in expected}
            assert actual == expected, (delta,tick,actual,expected)
            if delta == 256 and tick <= 55 and expected['step'] != previous:
                normal_boundaries.append(dict(update=tick,**expected))
                previous = expected['step']
            if tick != updates:
                _,count = original.run(0x120ac8,[obj])
                executed += count
        results.append(dict(delta=delta,states_compared=len(rows),original_instructions_executed=executed))
    assert [x['update'] for x in normal_boundaries] == [0,4,12,16,18,20,29,40,48,55]
    report = dict(resource='00',action=0,records=aid[0x1000],normal_cycle_updates=55,
                  original_elf_sha256=hashlib.sha256(executable).hexdigest(),
                  native_trace_binary_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
                  original_entry='0x00120ac8',record_lookup='0x001212c0',
                  rates=results,total_states_compared=sum(x['states_compared'] for x in results),
                  all_states_match=True,normal_boundaries=normal_boundaries,
                  scope='Integer idle timing under ordinary global state; not a complete PS2 emulator, hardware test, hitstop test, or whole-game equivalence proof.')
    output = ROOT/'outputs/ss6-feasibility/idle_validation.json'
    output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ['rates','normal_boundaries']},indent=2))


if __name__ == '__main__':
    main()
