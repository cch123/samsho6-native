#!/usr/bin/env python3
"""Extract all original command templates from the pinned local ELF."""
import hashlib,json
from pathlib import Path
from inspect_iso import Elf
from extract_collision_tables import SOURCE_HASH
ROOT=Path(__file__).resolve().parents[2]
def main():
 raw=(ROOT/'work/ss6/extracted/SLPS_255.59').read_bytes()
 assert hashlib.sha256(raw).hexdigest()==SOURCE_HASH
 elf=Elf(raw);address=0x4e9898;count=273;stride=17
 data=raw[elf.offset(address):elf.offset(address)+count*stride]
 definitions=[data[i*stride:(i+1)*stride] for i in range(count)]
 assert all(all(v<171 or v==255 for v in d[:14]) and (d[16]<171 or d[16]==255) for d in definitions)
 for folder in [ROOT/'work/ss6/extracted/resources',ROOT/'outputs/ss6-feasibility/native-viewer/assets']:
  (folder/'input_commands.bin').write_bytes(data)
 report=dict(elf_sha256=SOURCE_HASH,address=hex(address),count=count,stride=stride,
  asset='input_commands.bin',sha256=hashlib.sha256(data).hexdigest(),
  definitions=[dict(id=i,tokens=list(d[:14]),timeout=d[14],buffer=d[15],reset_feature=d[16]) for i,d in enumerate(definitions)])
 (ROOT/'outputs/ss6-feasibility/input_tables.json').write_text(json.dumps(report,indent=2)+'\n')
 bindings=[]
 for name,address,count,stride in [('normal',0x4eb068,31,12),('special',0x4eb1e0,972,12),('characters',0x4eab00,51,12),('categories',0x4e5c50,51,5)]:
  blob=raw[elf.offset(address):elf.offset(address)+count*stride]
  for folder in [ROOT/'work/ss6/extracted/resources',ROOT/'outputs/ss6-feasibility/native-viewer/assets']:
   (folder/f'input_{name}.bin').write_bytes(blob)
  bindings.append(dict(asset=f'input_{name}.bin',address=hex(address),count=count,stride=stride,sha256=hashlib.sha256(blob).hexdigest()))
 (ROOT/'outputs/ss6-feasibility/input_binding_tables.json').write_text(json.dumps(dict(elf_sha256=SOURCE_HASH,tables=bindings,
  scope='Normal31 records; special972 records through three terminal sentinels before4edf70;51 character override/category records. Special blocks exist for0..41 and43..48 only. Character42/49/50 require caller alias/context analysis and are not silently mapped.'),indent=2)+'\n')
 print(json.dumps({k:v for k,v in report.items() if k!='definitions'},indent=2))
if __name__=='__main__':main()
