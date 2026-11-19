#!/usr/bin/env python3
"""Pinned original data used by the96 command permission callbacks."""
import hashlib,json
from pathlib import Path
from inspect_iso import Elf
from extract_collision_tables import SOURCE_HASH
ROOT=Path(__file__).resolve().parents[2]
TABLES=[('air_rectangles',0x4e5d50,51,8),('target_ranges',0x4e5ab8,51,8),('attack_ranges',0x4e5ee8,51,36),('systems',0x50dee0,9,40),('cancel_conditions',0x4ead68,96,4)]
LIMITS=[0x50d928,0x5e9b78,0x5e9b90,0x5f1b20,0x5f1b24]
GATE_LIMITS=[0x5f1db0,0x663874,0x663878,0x66387c,0x663b4c,0x663b50,0x663b54,0x663e8c,0x663e90,0x663e94,0x66454c,0x664550,0x664554]
def main():
 raw=(ROOT/'work/ss6/extracted/SLPS_255.59').read_bytes();assert hashlib.sha256(raw).hexdigest()==SOURCE_HASH
 elf=Elf(raw);tables=[]
 def emit(name,data,source):
  asset=f'permission_{name}.bin'
  for folder in ['work/ss6/extracted/resources','outputs/ss6-feasibility/native-viewer/assets']:(ROOT/folder/asset).write_bytes(data)
  tables.append(dict(asset=asset,bytes=len(data),source=source,sha256=hashlib.sha256(data).hexdigest()))
 for name,address,count,stride in TABLES:
  offset=elf.offset(address);emit(name,raw[offset:offset+count*stride],dict(address=hex(address),count=count,stride=stride))
 emit('limits',b''.join(raw[elf.offset(a):elf.offset(a)+4] for a in LIMITS),dict(word_addresses=list(map(hex,LIMITS))))
 emit('gate_limits',b''.join(raw[elf.offset(a):elf.offset(a)+4] for a in GATE_LIMITS),dict(word_addresses=list(map(hex,GATE_LIMITS))))
 report=dict(elf_sha256=SOURCE_HASH,tables=tables,scope='Original air-grab rectangles,character range data,system rules,cancel-condition flags and constants for input permission callbacks/category/auxiliary gates. No inferred animation data.')
 (ROOT/'outputs/ss6-feasibility/input_permission_tables.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
