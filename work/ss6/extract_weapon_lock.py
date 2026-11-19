#!/usr/bin/env python3
"""Pin the common resource binding and weapon-lock placement constants."""
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
    word = lambda at: struct.unpack_from('<I', raw, elf.offset(at))[0]
    #11f970 stores the literal from11f968 into46a9a0[2]. Keep this evidence
    #separate from the fact that action135 happens to exist in resource51.
    assert word(0x11f968) == 0x240f0033 and word(0x11f970) == 0xad6f0008
    locations = [0x5e9d70, 0x5e9d74, 0x5e9f1c, 0x5e9f20]
    data = struct.pack('<5I', word(0x11f968)&65535, *map(word, locations))
    (ROOT/'work/ss6/extracted/resources/weapon_lock.bin').write_bytes(data)
    resources = {}
    for name in ['aid_51.bin', 'act_51.bin']:
        content = (ROOT/'work/ss6/extracted/resources'/name).read_bytes()
        resources[name] = dict(bytes=len(content), sha256=hashlib.sha256(content).hexdigest())
    report = dict(elf_sha256=SOURCE_HASH, asset='weapon_lock.bin', bytes=len(data),
                  sha256=hashlib.sha256(data).hexdigest(), resource=51,
                  binding_instructions=['0x11f968', '0x11f970'],
                  scalar_addresses=list(map(hex, locations)), resources=resources)
    (ROOT/'outputs/ss6-feasibility/weapon_lock_tables.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2))

if __name__ == '__main__':main()
