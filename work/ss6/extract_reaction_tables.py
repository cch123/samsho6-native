#!/usr/bin/env python3
"""Extract common hit reactions, descriptors and ordinary action mapping."""
import hashlib
import json
from pathlib import Path
from inspect_iso import Elf
from extract_collision_tables import SOURCE_HASH

ROOT=Path(__file__).resolve().parents[2]
REGIONS=[('reaction_selection',0x4d7f38,36*24),('reaction_descriptors',0x4e90b8,80*14),
         ('reaction_actions',0x4e8c08,16*4)]

def main():
    raw=(ROOT/'work/ss6/extracted/SLPS_255.59').read_bytes()
    assert hashlib.sha256(raw).hexdigest()==SOURCE_HASH
    elf=Elf(raw)
    data=b''.join(raw[elf.offset(a):elf.offset(a)+size] for _,a,size in REGIONS)
    out=ROOT/'outputs/ss6-feasibility'
    for path in [ROOT/'work/ss6/extracted/resources',out/'native-viewer/assets']:
        (path/'reaction_common.bin').write_bytes(data)
    (out/'reaction_tables.json').write_text(json.dumps(dict(elf_sha256=SOURCE_HASH,
        asset='reaction_common.bin',regions=[dict(name=n,address=hex(a),size=s) for n,a,s in REGIONS],
        sha256=hashlib.sha256(data).hexdigest()),indent=2)+'\n')
    print(f'Extracted {len(data)} bytes of original reaction tables')

if __name__=='__main__':main()
