#!/usr/bin/env python3
"""Tabulate the original 10b4b8 (cosine) and 10b4f8 (sine) for every 16-bit angle unit.

Both routines mask their argument with 0xffff, so 65536 entries cover every call. The
values come from running the original routines (finite FP model), not from a host
libm, so callers that rotate by arbitrary angles (Kazuki's orbiting fire, 1f7318)
reproduce the original results bit for bit.
Output: angle_trig.bin = 65536 x (u32 cosine bits, u32 sine bits), little endian.
"""
import hashlib
import json
from pathlib import Path
import struct

from mips_probe import Probe
from extract_collision_tables import SOURCE_HASH

ROOT=Path(__file__).resolve().parents[2]


def main():
    raw=(ROOT/'work/ss6/extracted/SLPS_255.59').read_bytes()
    assert hashlib.sha256(raw).hexdigest()==SOURCE_HASH
    p=Probe(raw,finite_model=True)
    out=bytearray();instructions=0
    for unit in range(0x10000):
        values=[]
        for fn in (0x10b4b8,0x10b4f8):
            _,n=p.run(fn,[unit]);instructions+=n;values.append(p.floats[0])
        out+=struct.pack('<II',*values)
    data=bytes(out)
    for target in (ROOT/'work/ss6/extracted/resources',ROOT/'outputs/ss6-feasibility/native-viewer/assets'):
        if target.exists():(target/'angle_trig.bin').write_bytes(data)
    report=dict(elf_sha256=SOURCE_HASH,size=len(data),sha256=hashlib.sha256(data).hexdigest(),
                source='10b4b8 / 10b4f8 for units 0..0xffff',instructions=instructions)
    (ROOT/'outputs/ss6-feasibility/angle_trig.json').write_text(json.dumps(report,indent=2)+'\n')
    print(report['size'],report['sha256'])


if __name__=='__main__':main()
