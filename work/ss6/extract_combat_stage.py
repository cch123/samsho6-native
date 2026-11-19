#!/usr/bin/env python3
"""Export unprojected Stage 00 meshes and the 23 stage object descriptors.

1a7690 initializes world vertices, atlas pieces and a separate picture table
for each animated prop. Nothing here depends on a recorded camera or frame.
"""
import hashlib
import struct

from character_tiles_oracle import ASSETS
from extract_versus_draw_stage import prepare
from finite_float import arithmetic

SPRITES = (0x1a6210, 0x1a6460, 0x1a66b8, 0x1a6b08)
ANIMATED = (1, 2, 15, 16, 18, 21, 22)


def floats(p, address, count):
    return struct.unpack_from(f'<{count}f', p.memory, address)


def collect(p, picture):
    groups = [[] for _ in range(24)]
    group = 0
    # Exercise each actual picture descriptor independent of its duration.
    for row in ANIMATED:
        state, timeline = struct.unpack_from('<II', p.memory, p.read(0x513138+row*0x48+0x28, 4))
        step = 0
        while True:
            key, _ = struct.unpack_from('<ii', p.memory, timeline+step*8)
            if key == picture: break
            if key < 0:
                step = 0
                break
            step += 1
        p.write(state, 0, 4)
        p.write(state+0x2c, step, 4)

    def observe(pc):
        nonlocal group
        if pc == 0x1a7afc:
            group = 1+p.registers[20]
        reg = p.registers
        emit = groups[group].append
        if pc in SPRITES:
            slot, count, ptr = reg[4:7]
            x, y, z, sx, sy = [p.float_value(i) for i in range(12, 17)]
            if pc in SPRITES[:2]: sx = sy = 1
            # Header is also the sole drawable piece for one-piece objects.
            rects = [struct.unpack_from('<4i', p.memory, ptr+24*i) for i in range(count)]
            emit((1+(pc in SPRITES[1::2]), slot, [x,y,z,sx,sy], rects))
        elif pc == 0x1a4f40:
            # x already includes the camera-independent parallax correction at 1a5428.
            emit((3, reg[4], [p.float_value(i) for i in range(12,19)], []))
        elif pc == 0x1a5890:
            slot, ptr, columns, rows = reg[4:8]
            assert (slot, columns, rows) == (5,32,4)
            verts = [floats(p,ptr+20*(x+dx)+0x294*y,5)
                     for x in range(columns) for y in range(rows+1) for dx in range(2)]
            emit((4, slot, [*floats(p,ptr+8,1), *floats(p,0x50e050,1),2*(rows+1)], verts))
        elif pc in (0x1a5d40,0x1a5f68):
            slot, ptr, columns, rows, size = reg[4:9]
            verts=[]
            for x in range(columns):
                for y in range(rows+1):
                    for dx in range(2):
                        at = ptr+36*(x+dx)+0x4a4*y
                        uv = floats(p,at+12,2)
                        if pc == 0x1a5f68:
                            # This variant binds the current animated atlas frame, even
                            # though all its frames share the same world-space mesh.
                            values=[]
                            for axis in range(2):
                                norm=p.read(at+28+4*axis,4)
                                extent=p.read(ptr+0x4ee4+4*axis,4)
                                pos=arithmetic('add',p.floats[12+axis],arithmetic('mul',extent,norm))
                                value=arithmetic('div',pos,struct.unpack('<I',struct.pack('<f',size))[0])
                                values.append(struct.unpack('<f',struct.pack('<I',value))[0])
                            uv=values
                        verts.append((*floats(p,at+20,2),0,*uv))
            emit((5,slot,[*floats(p,ptr,3),*floats(p,ptr+0x4ee4,2),2*(rows+1)],verts))
    p.run(0x1a7810,limit=2000000,observe=observe)
    return groups


def main():
    assert hashlib.sha256((ASSETS.parent/'SLPS_255.59').read_bytes()).hexdigest() == '72420e74e04d7ac39119d1b6ec7d70ed004fc98c5035fade96e87d05d4b9ffbf'
    p=prepare()
    variants=[collect(p,i) for i in range(4)]
    # A moving camera can cull an entire visible piece list. Check that the
    # descriptors observed *before* the renderer's culling are completely
    # independent of both the camera and visibility.
    other=prepare()
    struct.pack_into('<6f',other.memory,0x4a2a58,170.5,160,-500,-160,-79.2,83.2)
    assert variants == [collect(other,i) for i in range(4)]
    output=bytearray(b'STG0'+struct.pack('<I',1))
    for group in range(24):
        choices=[frames[group] for frames in variants]
        if group-1 not in ANIMATED: assert all(c==choices[0] for c in choices)
        unique=[]
        for choice in choices:
            if choice not in unique: unique.append(choice)
        assert choices == unique + [unique[0]]*(4-len(unique))
        output.extend(struct.pack('<I',len(unique)))
        for commands in unique:
            output.extend(struct.pack('<I',len(commands)))
            for kind,slot,params,records in commands:
                output.extend(struct.pack('<4I',kind,slot,len(params),len(records)))
                output.extend(struct.pack(f'<{len(params)}f',*params))
                for rec in records:output.extend(struct.pack(f'<{len(rec)}f',*rec))
    path=ASSETS/'combat_stage.bin'
    path.write_bytes(output)
    print(f'{len(output)} bytes of world meshes, sprite parts and picture alternatives in {path}')

if __name__=='__main__':
    main()
