#!/usr/bin/env python3
"""Extract the PS2 contact groups selected by 156fb8, 157318 and 1574f0."""
from pathlib import Path
import hashlib
from extract_collision_tables import SOURCE_HASH
from inspect_iso import Elf
ROOT=Path(__file__).resolve().parents[2]
IDS=(7,8,9,11,*range(13,29),32,*range(35,41))
if __name__=='__main__':
    raw=(ROOT/'work/ss6/extracted/SLPS_255.59').read_bytes();assert hashlib.sha256(raw).hexdigest()==SOURCE_HASH
    elf=Elf(raw); data=bytearray()
    for index in IDS:
        at=elf.offset(0x4a2b30+index*108);data+=bytes([index])+raw[at:at+108]
    (ROOT/'work/ss6/extracted/resources/contact_effects.bin').write_bytes(data)
    print(len(IDS),len(data),hashlib.sha256(data).hexdigest())
