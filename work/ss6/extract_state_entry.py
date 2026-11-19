#!/usr/bin/env python3
"""Pinned state metadata for complete14a348 entry preparation."""
import hashlib,json,struct
from pathlib import Path
from inspect_iso import Elf
from extract_collision_tables import SOURCE_HASH
ROOT=Path(__file__).resolve().parents[2]

def main():
 raw=(ROOT/'work/ss6/extracted/SLPS_255.59').read_bytes();assert hashlib.sha256(raw).hexdigest()==SOURCE_HASH
 elf=Elf(raw);manifest=[]
 def data(address,size):return raw[elf.offset(address):elf.offset(address)+size]
 def emit(name,content,source):
  filename=f'entry_{name}.bin'
  for folder in ['work/ss6/extracted/resources','outputs/ss6-feasibility/native-viewer/assets']:(ROOT/folder/filename).write_bytes(content)
  manifest.append(dict(asset=filename,bytes=len(content),source=source,sha256=hashlib.sha256(content).hexdigest()))
 attack=[];special=[];damage=[]
 for c in range(51):
  attack.append(struct.unpack('<I',data(0x4e8e48+c*4,4))[0]);special.append(struct.unpack('<I',data(0x4e8f18+c*4,4))[0]);damage.append(struct.unpack('<I',data(0x4e96d8+c*4,4))[0])
 emit('attack',b''.join(data(address,4*64*5) for address in attack),dict(pointer_table='0x4e8e48',addresses=list(map(hex,attack)),characters=51,variants=4,states=64,stride=5))
 emit('special',b''.join(data(address,32*5) for address in special),dict(pointer_table='0x4e8f18',addresses=list(map(hex,special)),characters=51,states=32,stride=5))
 emit('damage',data(0x4e90b8,80*14)+b''.join(data(address,32*14) for address in damage),dict(common='0x4e90b8',common_states=80,pointer_table='0x4e96d8',addresses=list(map(hex,damage)),characters=51,extra_states=32,stride=14))
 emit('conditions',data(0x4d6ce0,69*3),dict(address='0x4d6ce0',count=69,stride=3))
 pairs=bytearray();address=0x4e8348
 while len(pairs)<4096:
  pair=data(address+len(pairs),2);pairs.extend(pair)
  if 255 in pair:break
 else:raise ValueError('Missing169308 sentinel')
 emit('special_exceptions',pairs,dict(address=hex(address),pairs=len(pairs)//2,includes_sentinel=True))
 report=dict(elf_sha256=SOURCE_HASH,tables=manifest,scope='Raw normal metadata is already selection_normal_descriptors.bin. These assets add51character/four-variant ordinary attack descriptors,51special blocks,common and character-specific damage descriptors,69condition sets and169308 exceptions. Logical states/poses/conditions,not newly playable animations.')
 (ROOT/'outputs/ss6-feasibility/state_entry_tables.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps(dict(assets=len(manifest),bytes=sum(t['bytes'] for t in manifest),exceptions=len(pairs)//2)))

if __name__=='__main__':main()
