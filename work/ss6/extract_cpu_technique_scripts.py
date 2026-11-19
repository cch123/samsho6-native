"""Extract the Japanese CPU command script records used by 15f4b8/15f4e8."""
from hashlib import sha256
from pathlib import Path
import struct
from inspect_iso import Elf
from extract_collision_tables import SOURCE_HASH

ROOT=Path(__file__).resolve().parents[2]
def main():
    resources=ROOT/'work/ss6/extracted/resources'
    raw=(resources.parent/'SLPS_255.59').read_bytes()
    if sha256(raw).hexdigest()!=SOURCE_HASH:raise ValueError('Unexpected PS2 executable')
    elf=Elf(raw)
    for name,address,count,end in [('steps',0x4da788,556,-1),('definitions',0x4dc1a8,833,-2)]:
        offset=elf.offset(address)
        for i in range(count):
            assert struct.unpack_from('<h',raw,offset+i*12)[0]!=end
        assert struct.unpack_from('<h',raw,offset+count*12)[0]==end
        (resources/f'cpu_technique_{name}.bin').write_bytes(raw[offset:offset+count*12])
if __name__=='__main__':main()
