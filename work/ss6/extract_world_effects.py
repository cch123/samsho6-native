#!/usr/bin/env python3
"""Pin the original world-effect descriptors used by weapon lock and whirlwind recovery."""
import hashlib,json
from pathlib import Path
from inspect_iso import Elf
from extract_collision_tables import SOURCE_HASH
ROOT=Path(__file__).resolve().parents[2]
def main():
 raw=(ROOT/'work/ss6/extracted/SLPS_255.59').read_bytes()
 assert hashlib.sha256(raw).hexdigest()==SOURCE_HASH
 elf=Elf(raw);ids=[12,36,29,3,30,2,10,5,4,1,6,41,42]
 data=b''.join(raw[elf.offset(0x4a2b30+i*108):elf.offset(0x4a2b30+i*108)+108] for i in ids)
 (ROOT/'work/ss6/extracted/resources/world_effects.bin').write_bytes(data)
 report=dict(elf_sha256=SOURCE_HASH,asset='world_effects.bin',bytes=len(data),sha256=hashlib.sha256(data).hexdigest(),
  descriptors=ids,addresses=[hex(0x4a2b30+i*108) for i in ids],
  scope='World descriptors 12/36 for weapon lock, 29 for whirlwind recovery, 3 for the light+medium attack, 30 for wall impact, 2 for the Shin weapon-breaking attack, 10 for the broken sword, 5 for the Zan charge aura, 4 for the explosion and 1 for Zero concentration, including their completion callbacks. Group 6 supplies meditation particles. Groups 41 and 42 are the Ken perfect guard opening and success effects. Includes fixed and random actions and their velocity ranges.')
 (ROOT/'outputs/ss6-feasibility/world_effect_tables.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps(report,indent=2))
if __name__=='__main__':main()
