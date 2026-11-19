#!/usr/bin/env python3
"""Extract the finite Japanese versus introduction timeline at its draw ABI."""
import hashlib
import struct

from extract_versus_result_layout import ASSETS, calls, canvas

# Start can enter the short fight transition on the final normal draw. The
# director keeps drawing and incrementing both clocks during that fade.
FRAME_COUNT = 540
TARGET = ASSETS / 'vs_faceoff_layout.bin'

def rectangle(slot, vertices):
    # 126370 only emits axis-aligned rectangles. Keep signed UV extents for
    # mirrors. Sort corners in screen space before serializing the rectangle.
    ordered = sorted(vertices, key=lambda v: (v[1], v[0]))
    first, right, bottom, last = ordered
    x,y = first[:2]
    x1,y1 = last[:2]
    assert right[:2] == (x1,y) and bottom[:2] == (x,y1)
    assert all(v[-1] == first[-1] for v in ordered)
    if slot:
        size = 1024 if slot == 4 else 512
        u,v,u1,v1 = (first[3]*size,first[4]*size,last[3]*size,last[4]*size)
        if x != x1 and y != y1:
            assert (right[3],right[4]) == (last[3],first[4])
            assert (bottom[3],bottom[4]) == (first[3],last[4])
        assert first[-1]&0xffffff == 0xffffff
    else:
        u=v=u1=v1=0
        assert first[-1]&0xffffff == 0
    values=(x,y,x1,y1,u,v,u1,v1)
    assert all(int(n)==n for n in values)
    return struct.pack('<BB8h',slot,first[-1]>>24,*(int(n) for n in values))

def extract():
    assert hashlib.sha256((ASSETS.parent/'SLPS_255.59').read_bytes()).hexdigest() == '72420e74e04d7ac39119d1b6ec7d70ed004fc98c5035fade96e87d05d4b9ffbf'
    p=canvas()
    catalog={}
    backgrounds=[]
    poses=[]
    for tick in range(FRAME_COUNT):
        p.write(0x3db8f8,0,4)
        draws,_=calls(p,0x126370,tick,tick)
        ordered=sorted(draws,key=lambda pair:pair[1][0][2])
        assert ordered[0][0]==4 and sum(slot==4 for slot,_ in ordered)==1
        refs=[]
        for slot,vertices in ordered:
            record=rectangle(slot,vertices)
            refs.append(catalog.setdefault(record,len(catalog)))
        backgrounds.append(refs[0])
        poses.append(refs[1:])
    data=bytearray(struct.pack('<4s3I',b'VSFO',1,FRAME_COUNT,len(catalog)))+b''.join(catalog)
    for bg,pose in zip(backgrounds,poses):
        data.extend(struct.pack(f'<HB{len(pose)}H',bg,len(pose),*pose))
    TARGET.write_bytes(data)
    print(f'{FRAME_COUNT} frame pairs, {len(catalog)} unique rectangles, {len(data)} bytes')
if __name__=='__main__':
    extract()
