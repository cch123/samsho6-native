#!/usr/bin/env python3
"""Extract the original resource-00 routing data, with a pinned ELF baseline."""
import hashlib
import json
from pathlib import Path
from inspect_iso import Elf

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT/'outputs/ss6-feasibility'
SOURCE_HASH = '72420e74e04d7ac39119d1b6ec7d70ed004fc98c5035fade96e87d05d4b9ffbf'

def main():
    data = (ROOT/'work/ss6/extracted/SLPS_255.59').read_bytes()
    assert hashlib.sha256(data).hexdigest() == SOURCE_HASH, 'Unrecognized original executable'
    elf = Elf(data)
    result = bytearray()
    regions = []
    for name, address, size in [('common_classes',0x4d70e8,72),
                                ('routing_matrix',0x4d7130,324),
                                ('resource_00_classes',0x4d7278,64)]:
        offset = elf.offset(address)
        regions.append(dict(name=name,elf_address=hex(address),output_offset=len(result),size=size))
        result.extend(data[offset:offset+size])
    for target in [ROOT/'work/ss6/extracted/resources', OUT/'native-viewer/assets']:
        (target/'collision_00.bin').write_bytes(result)
    # 153090 uses the object's +18 profile for raw classes 36..67.
    for profile in (1,2,3):
        start=elf.offset(0x4d7278+64*profile)
        (ROOT/f'work/ss6/extracted/resources/collision_{profile:02}.bin').write_bytes(data[start:start+64])
    report = dict(elf_sha256=SOURCE_HASH,asset='collision_00.bin',size=len(result),
                  sha256=hashlib.sha256(result).hexdigest(),regions=regions,
                  scope='Common types and character-table slot 0 only; tables are data, not executed code.')
    (OUT/'collision_tables.json').write_text(json.dumps(report,indent=2)+'\n')
    print(f'Extracted {len(result)} bytes of original collision routing data')

if __name__ == '__main__': main()
