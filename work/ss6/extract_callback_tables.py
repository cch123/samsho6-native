#!/usr/bin/env python3
"""Pinned parameters and handler identities used by whole172eb0/14efb8."""
import hashlib,json
from pathlib import Path
from inspect_iso import Elf
from extract_collision_tables import SOURCE_HASH
ROOT=Path(__file__).resolve().parents[2]

def main():
 raw=(ROOT/'work/ss6/extracted/SLPS_255.59').read_bytes();assert hashlib.sha256(raw).hexdigest()==SOURCE_HASH
 elf=Elf(raw);tables=[]
 for name,address,size in [('attack_handlers',0x4e8fe8,51*4),('special_parameters',0x4e6618,53*32*4),
                           ('character_parameters',0x50d948,51*28),('constants',0x5ea9d0,8)]:
  data=raw[elf.offset(address):elf.offset(address)+size];filename=f'callback_{name}.bin'
  for folder in ['work/ss6/extracted/resources','outputs/ss6-feasibility/native-viewer/assets']:(ROOT/folder/filename).write_bytes(data)
  tables.append(dict(asset=filename,address=hex(address),bytes=size,sha256=hashlib.sha256(data).hexdigest()))
 report=dict(elf_sha256=SOURCE_HASH,tables=tables,scope='172eb0 attack handler identities,168ec0 special parameters,1a3bd8 character parameters and14efb8 constants. Existing permission_systems.bin supplies1a3bf8. Handler words are native dispatch labels, never executed as PS2 code or cast to native pointers.')
 (ROOT/'outputs/ss6-feasibility/callback_tables.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps(dict(assets=len(tables),bytes=sum(t['bytes'] for t in tables))))

if __name__=='__main__':main()
