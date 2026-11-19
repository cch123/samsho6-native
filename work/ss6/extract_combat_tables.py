#!/usr/bin/env python3
"""Extract contact consumption indices from the pinned original executable."""
import hashlib
import json
from pathlib import Path
from inspect_iso import Elf
from extract_collision_tables import SOURCE_HASH

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'outputs/ss6-feasibility'

def main():
    elf=(ROOT/'work/ss6/extracted/SLPS_255.59').read_bytes()
    assert hashlib.sha256(elf).hexdigest()==SOURCE_HASH
    offset=Elf(elf).offset(0x4d89c0)
    data=elf[offset:offset+96]
    for target in [ROOT/'work/ss6/extracted/resources',OUT/'native-viewer/assets']:
        (target/'combat_consumption.bin').write_bytes(data)
    (OUT/'combat_tables.json').write_text(json.dumps(dict(elf_sha256=SOURCE_HASH,
        asset='combat_consumption.bin',elf_address='0x4d89c0',size=96,
        sha256=hashlib.sha256(data).hexdigest()),indent=2)+'\n')
    print('Extracted 12 original consumption-index pairs')

if __name__=='__main__': main()
