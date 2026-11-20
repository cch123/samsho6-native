#!/usr/bin/env python3
"""Extract the JP matchup ranges that the CPU loader applies to each character's sqData."""
from hashlib import sha256
from pathlib import Path
from inspect_iso import Elf
from extract_collision_tables import SOURCE_HASH

ROOT=Path(__file__).resolve().parents[2]
def main():
    raw=(ROOT/'work/ss6/extracted/SLPS_255.59').read_bytes()
    if sha256(raw).hexdigest()!=SOURCE_HASH:raise ValueError('Unsupported game revision')
    elf=Elf(raw)
    for name,address,size in [('cpu_technique_slots',0x4d9a48,53*32*2),('cpu_matchup_ranges',0x4e5ab8,51*8),('cpu_air_attack_timing',0x4de8c0,54*36),('cpu_guard_heights',0x4d8ad8,54*4*12),('cpu_attack_situations',0x4d94f8,64)]:
        start=elf.offset(address)
        (ROOT/'work/ss6/extracted/resources'/f'{name}.bin').write_bytes(raw[start:start+size])
    start=elf.offset(0x4e4b38)
    (ROOT/'work/ss6/extracted/resources/projectile_descriptor_flags.bin').write_bytes(raw[start+10:start+190*12:12])
if __name__=='__main__':main()
