#!/usr/bin/env python3
"""Original sound-choice tables and decoded stage jump-table categories."""
import hashlib,json,struct
from inspect_iso import Elf
from extract_collision_tables import SOURCE_HASH
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def main():
 raw=(ROOT/'work/ss6/extracted/SLPS_255.59').read_bytes();assert hashlib.sha256(raw).hexdigest()==SOURCE_HASH
 elf=Elf(raw)
 def read(address,size):return raw[elf.offset(address):elf.offset(address)+size]
 data=read(0x585200,140);categories=[]
 for address,targets in [(0x663200,[0x1e8618,0x1e8658,0x1e8650]),(0x663230,[0x1e8690,0x1e86d0,0x1e86c8]),(0x663260,[0x1e8708,0x1e872c,0x1e8724])]:
  pointers=struct.unpack('<12I',read(address,48));mapped=[targets.index(v) for v in pointers]
  data+=bytes(mapped);categories.append(dict(address=hex(address),targets=list(map(hex,targets)),categories=mapped))
 (ROOT/'work/ss6/extracted/resources/sound_selection.bin').write_bytes(data)
 report=dict(elf_sha256=SOURCE_HASH,asset='sound_selection.bin',table_address='0x585200',table_bytes=140,stage_categories=categories,
  bytes=len(data),sha256=hashlib.sha256(data).hexdigest())
 (ROOT/'outputs/ss6-feasibility/sound_selection_tables.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
if __name__=='__main__':main()
