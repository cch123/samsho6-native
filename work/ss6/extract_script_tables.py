#!/usr/bin/env python3
"""Extract move-script rows (4e2788), action locks (4e5458) and projectile descriptors (4e4b38) from the pinned ELF.

script_rows.bin: 51 headers (u32 original row-base address, u32 row count
including the terminator row), then every character's raw 20-byte rows in order.
The original base addresses are kept because the actor registry r[11] stores
them, and validators compare that word with the Japanese executable.
action_locks.bin: 51 x 8 (s16 ACT, s16 ticks) pairs read by 168c18.
"""
import hashlib
import json
import struct
from pathlib import Path
from inspect_iso import Elf

ROOT = Path(__file__).resolve().parents[2]
SOURCE_HASH = '72420e74e04d7ac39119d1b6ec7d70ed004fc98c5035fade96e87d05d4b9ffbf'


def main():
    data = (ROOT/'work/ss6/extracted/SLPS_255.59').read_bytes()
    assert hashlib.sha256(data).hexdigest() == SOURCE_HASH, 'Unrecognized original executable'
    elf = Elf(data)
    headers, rows = bytearray(), bytearray()
    counts = []
    for character in range(51):
        base, = struct.unpack_from('<I', data, elf.offset(0x4e2788 + 4*character))
        n = 0
        # 163348 compares the id first and stops on END CODE 0xff (byte +4).
        while True:
            row = data[elf.offset(base + 20*n):elf.offset(base + 20*n) + 20]
            rows += row; n += 1
            if row[4] == 0xff: break
            assert n < 0x1000
        headers += struct.pack('<II', base, n); counts.append(n)
    script = bytes(headers + rows)
    locks = data[elf.offset(0x4e5458):elf.offset(0x4e5458) + 51*32]
    # 163430: 190 twelve-byte projectile descriptors (ids 0x00..0xbd).
    descriptors = data[elf.offset(0x4e4b38):elf.offset(0x4e4b38) + 190*12]
    out = []
    for target in (ROOT/'work/ss6/extracted/resources', ROOT/'outputs/ss6-feasibility/native-viewer/assets'):
        if not target.exists(): continue
        (target/'script_rows.bin').write_bytes(script)
        (target/'action_locks.bin').write_bytes(locks)
        (target/'projectile_descriptors.bin').write_bytes(descriptors)
        out.append(str(target))
    report = dict(elf_sha256=SOURCE_HASH,
                  script_rows=dict(size=len(script), sha256=hashlib.sha256(script).hexdigest(), rows=counts,
                                   source='0x4e2788 pointer table'),
                  action_locks=dict(size=len(locks), sha256=hashlib.sha256(locks).hexdigest(), source='0x4e5458'),
                  projectile_descriptors=dict(size=len(descriptors), sha256=hashlib.sha256(descriptors).hexdigest(), source='0x4e4b38'),
                  written=out)
    (ROOT/'outputs/ss6-feasibility/script_tables.json').write_text(json.dumps(report, indent=2) + '\n')
    print(f'{len(script)} script bytes, {len(locks)} lock bytes')


if __name__ == '__main__':
    main()
