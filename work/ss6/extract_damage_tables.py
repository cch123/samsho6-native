#!/usr/bin/env python3
"""Extract the ordinary resource-00/system-0 damage data, without edits."""
import hashlib
import json
from pathlib import Path
from inspect_iso import Elf
from extract_collision_tables import SOURCE_HASH

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'outputs/ss6-feasibility'
REGIONS=[('rules',0x50d858,0xec),('character_00',0x50d948,28),
         ('system_0',0x50dee0,40),('constants',0x6529d8,48)]

def main():
    raw=(ROOT/'work/ss6/extracted/SLPS_255.59').read_bytes()
    assert hashlib.sha256(raw).hexdigest()==SOURCE_HASH
    elf=Elf(raw)
    data=b''.join(raw[elf.offset(a):elf.offset(a)+n] for _,a,n in REGIONS)
    for target in [ROOT/'work/ss6/extracted/resources',OUT/'native-viewer/assets']:
        (target/'damage_00.bin').write_bytes(data)
    (OUT/'damage_tables.json').write_text(json.dumps(dict(elf_sha256=SOURCE_HASH,
        asset='damage_00.bin',regions=[dict(name=n,address=hex(a),size=s) for n,a,s in REGIONS],
        sha256=hashlib.sha256(data).hexdigest()),indent=2)+'\n')
    print(f'Extracted {len(data)} bytes of original damage tables')

if __name__=='__main__': main()
