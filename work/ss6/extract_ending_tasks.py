#!/usr/bin/env python3
"""Pinned round-end effect groups15..19, separate from opening data."""
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
    at, size = 0x4a3e30+15*108, 5*108
    data = raw[elf.offset(at):elf.offset(at)+size]
    (ROOT/'work/ss6/extracted/resources/ending_tasks.bin').write_bytes(data)
    report = dict(elf_sha256=SOURCE_HASH, asset='ending_tasks.bin', bytes=len(data),
                  sha256=hashlib.sha256(data).hexdigest(), address=hex(at),
                  scope='Round-end descriptors15..19, all null completion callbacks. Native dispatch data only; no PS2 code executes at runtime.')
    (ROOT/'outputs/ss6-feasibility/ending_task_tables.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
