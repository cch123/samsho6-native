#!/usr/bin/env python3
"""Pinned descriptors and logical palette mapping for the round opening."""
import hashlib
import json
from pathlib import Path
from inspect_iso import Elf
from extract_collision_tables import SOURCE_HASH

ROOT = Path(__file__).resolve().parents[2]


def main():
    raw = (ROOT/'work/ss6/extracted/SLPS_255.59').read_bytes()
    assert hashlib.sha256(raw).hexdigest() == SOURCE_HASH
    elf = Elf(raw)
    ranges = [(0x4a3e30, 15*108), (0x5dd628+10*4, 4)]
    data = b''.join(raw[elf.offset(at):elf.offset(at)+size] for at, size in ranges)
    (ROOT/'work/ss6/extracted/resources/opening_tasks.bin').write_bytes(data)
    report = dict(elf_sha256=SOURCE_HASH, asset='opening_tasks.bin', bytes=len(data),
                  sha256=hashlib.sha256(data).hexdigest(),
                  ranges=[dict(address=hex(at), bytes=size) for at, size in ranges],
                  scope='Opening descriptors1..14 and logical palette10 mapping. Callback words are native dispatch IDs, never executed as machine code. Descriptor0 retained for table indexing but not admitted.')
    (ROOT/'outputs/ss6-feasibility/opening_task_tables.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
