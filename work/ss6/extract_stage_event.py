#!/usr/bin/env python3
"""Pinned data used by the original stage event requests and round placement."""
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
    ranges = [(0x573430, 60), (0x653b98, 4), (0x5e9c00, 4)]
    data = b''.join(raw[elf.offset(at):elf.offset(at)+size] for at, size in ranges)
    (ROOT/'work/ss6/extracted/resources/stage_event.bin').write_bytes(data)
    # Twelve 20-byte arena rows, sixteen 8-byte weighted distributions
    # and the sixteen trigger times consumed by 14e938.
    start=elf.offset(0x4d5a20)
    schedule=raw[start:start+384]
    (ROOT/'work/ss6/extracted/resources/stage_item_schedule.bin').write_bytes(schedule)
    report = dict(elf_sha256=SOURCE_HASH, asset='stage_event.bin', bytes=len(data),
                  sha256=hashlib.sha256(data).hexdigest(),
                  item_schedule=dict(asset='stage_item_schedule.bin',address='0x4d5a20',bytes=len(schedule),
                                     sha256=hashlib.sha256(schedule).hexdigest()),
                  ranges=[dict(address=hex(at), bytes=size) for at, size in ranges],
                  scope='15 event flags, fixed Z for1b4e88, round placement X from143430. Actor animation state handlers are not part of these tables.')
    (ROOT/'outputs/ss6-feasibility/stage_event_tables.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
