"""Japanese in-round CPU actor and its original common/character sequence resources."""
import struct

from validate_weapon_handling import ASSETS,setup

def cpu_actor(seat=0,character=0,difficulty=3,spacing=160,spirit=0,opponent_character=None):
    src,_=setup(seat,character)
    p,a=src.p,src.a
    common,characters=0x1900000,0x18e0000
    p.write(0x4d3d10,common,4);p.write(0x4d3d14,characters,4)
    other=character if opponent_character is None else opponent_character
    ids=(other,character) if seat else (character,other)
    blocks=[(common,'sqDataCm.bin',[1])]
    blocks.extend((characters+index*0x4c4c,f'sqData{fighter:02X}.bin',[1,fighter]) for index,fighter in enumerate(ids))
    for addr,name,header in blocks:
        blob=struct.pack('<'+'I'*len(header),*header)+(ASSETS/name).read_bytes()
        p.memory[addr:addr+len(blob)]=blob
        if len(header)==2:src.run(0x1693f0,header[1],addr+0x228)
    p.write(a+0x10c,spirit,4)
    src.run(0x179258,a+0x2c4,a+0x10c)
    for fn,args in ((0x1587d0,(a+8,)),(0x158830,(a+8,seat,character,difficulty)),
                    (0x1588b8,(a+8,other)),(0x1588c0,(a+8,))):
        src.run(fn,*args)
    p.write(a+0xa20,1,4);p.write(src.b+0x144,spacing,4)
    own_x=struct.unpack_from('<f',p.memory,src.o+0x40)[0]
    struct.pack_into('<f',p.memory,src.o+0x1040,own_x+(-spacing if seat else spacing))
    p.write(0x43d05c,7,1)
    return src
