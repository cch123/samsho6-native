#!/usr/bin/env python3
"""Original per-character spawn offsets and scalar constants, pinned to ELF."""
import hashlib,json
from pathlib import Path
from inspect_iso import Elf
from extract_collision_tables import SOURCE_HASH
ROOT=Path(__file__).resolve().parents[2]
def main():
 raw=(ROOT/'work/ss6/extracted/SLPS_255.59').read_bytes();assert hashlib.sha256(raw).hexdigest()==SOURCE_HASH
 elf=Elf(raw);tables=[]
 for name,parts in [('weapon_positions.bin',[(0x4e5ee8,51*36)]),
                    ('weapon_constants.bin',[(0x5df2c8,4),(0x5df3d0,8),(0x5f1630,4)])]:
  data=b''.join(raw[elf.offset(a):elf.offset(a)+n] for a,n in parts)
  for folder in ['work/ss6/extracted/resources','outputs/ss6-feasibility/native-viewer/assets']:(ROOT/folder/name).write_bytes(data)
  tables.append(dict(asset=name,parts=[dict(address=hex(a),bytes=n) for a,n in parts],bytes=len(data),sha256=hashlib.sha256(data).hexdigest()))
 (ROOT/'outputs/ss6-feasibility/weapon_tables.json').write_text(json.dumps(dict(elf_sha256=SOURCE_HASH,tables=tables),indent=2)+'\n')
 print(json.dumps(dict(assets=len(tables),bytes=sum(t['bytes'] for t in tables))))
if __name__=='__main__':main()
