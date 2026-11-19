#!/usr/bin/env python3
"""Pinned1a3070 group2 presence words; invalid alternate rows remain explicit."""
import hashlib
import json
import struct
from pathlib import Path
from inspect_iso import Elf
from extract_collision_tables import SOURCE_HASH

ROOT = Path(__file__).resolve().parents[2]


def main():
    raw = (ROOT/'work/ss6/extracted/SLPS_255.59').read_bytes()
    assert hashlib.sha256(raw).hexdigest() == SOURCE_HASH
    elf = Elf(raw)
    def word(at):return struct.unpack_from('<I', raw, elf.offset(at))[0]
    rows, addresses, invalid = [], [], []
    for version, base in enumerate([0x50d550, 0x50d618]):
        for character in range(49):
            at = word(base+character*4)
            #43 returns zero before dereferencing either table. Other rows
            #must be file-backed; do not fabricate absent alternate data.
            if character == 43:row = [1]+[0]*16
            else:
                try:row = [1]+[word(at+0xd8+i*4) for i in range(16)]
                except ValueError:
                    row = [0]*17
                    invalid.append([version, character, hex(at)])
            rows.extend(row)
            addresses.append(dict(version=version, character=character, pointer=hex(at), valid=bool(row[0])))
    data = struct.pack(f'<{len(rows)}I', *rows)
    (ROOT/'work/ss6/extracted/resources/ending_choices.bin').write_bytes(data)
    report = dict(elf_sha256=SOURCE_HASH, bytes=len(data), sha256=hashlib.sha256(data).hexdigest(),
                  invalid_rows=invalid, rows=addresses,
                  scope='Two49-row group2 presence tables. Raw pointer words are read only for zero/nonzero availability. Unresolved alternate rows are rejected at runtime, not treated as absent.')
    (ROOT/'outputs/ss6-feasibility/ending_choice_tables.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='rows'}, indent=2))


if __name__ == '__main__':main()
