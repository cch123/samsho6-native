#!/usr/bin/env python3
"""Original state-to-input transition matrices and restricted-state maps."""
import hashlib,json
from pathlib import Path
from inspect_iso import Elf
from extract_collision_tables import SOURCE_HASH
ROOT=Path(__file__).resolve().parents[2]
TABLES=[('normal',0x4d5ba0,64,31),('attack',0x4d6360,64,17),('chain',0x4d67a0,64,17),
        ('normal_map',0x4d6be0,64,1),('attack_map',0x4d6c20,64,2),('normal_descriptors',0x4e8d08,64,5),
        ('character_flags',0x4e5420,51,1),('threat_actions',0x4e8120,9,4)]
def main():
 raw=(ROOT/'work/ss6/extracted/SLPS_255.59').read_bytes();assert hashlib.sha256(raw).hexdigest()==SOURCE_HASH
 elf=Elf(raw);tables=[]
 for name,address,count,stride in TABLES:
  offset=elf.offset(address);data=raw[offset:offset+count*stride]
  if name in ['normal','normal_map']:assert all(v<64 or v==255 for v in data)
  if name in ['attack','chain']:assert all(v<64 or v==255 for v in data)
  filename=f'selection_{name}.bin'
  for folder in ['work/ss6/extracted/resources','outputs/ss6-feasibility/native-viewer/assets']:(ROOT/folder/filename).write_bytes(data)
  tables.append(dict(asset=filename,address=hex(address),count=count,stride=stride,sha256=hashlib.sha256(data).hexdigest()))
 report=dict(elf_sha256=SOURCE_HASH,tables=tables,scope='64-state normal and attack matrices,flag23c800000 remaps,normal descriptors,character flags and168fc8 threat-action pairs including sentinel. Transition255 means refused; transition values are logical states, not animation action IDs.')
 (ROOT/'outputs/ss6-feasibility/action_selection_tables.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
