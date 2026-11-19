#!/usr/bin/env python3
"""Pinned original resource00 range and near/far standing-light descriptors."""
import hashlib,json
from pathlib import Path
from inspect_iso import Elf
from extract_collision_tables import SOURCE_HASH
ROOT=Path(__file__).resolve().parents[2]
def main():
 raw=(ROOT/'work/ss6/extracted/SLPS_255.59').read_bytes();assert hashlib.sha256(raw).hexdigest()==SOURCE_HASH
 elf=Elf(raw);regions=[('ranges_00',0x4e5ab8,8),('near_light',0x5853e8,5),('far_light',0x585668,5)]
 data=b''.join(raw[elf.offset(a):elf.offset(a)+n] for _,a,n in regions)
 for folder in [ROOT/'work/ss6/extracted/resources',ROOT/'outputs/ss6-feasibility/native-viewer/assets']:
  (folder/'ordinary_00.bin').write_bytes(data)
 report=dict(elf_sha256=SOURCE_HASH,sha256=hashlib.sha256(data).hexdigest(),asset='ordinary_00.bin',
             regions=[dict(name=name,address=hex(a),size=n) for name,a,n in regions])
 (ROOT/'outputs/ss6-feasibility/ordinary_tables.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps(report,indent=2))
if __name__=='__main__':main()
