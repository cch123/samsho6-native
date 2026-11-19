#!/usr/bin/env python3
"""Recover Stage 1 world-space vertices, atlas rectangles and all picture alternatives."""
from hashlib import sha256
import struct

from extract_combat_stage import floats
from extract_versus_result_layout import canvas
from validate_dash_motion import ASSETS, ELF, PIN

ROW_BASE=0x514a50
ROWS=28
ANIMATED=(3,4,5,20,21,22,23,24,25,26)


def prepare():
    p=canvas()
    p.write(0x50e048,0x60000000,4)
    p.write(0x510ce8,p.read(0x652d14,4),4)
    for slot,bank in ((4,32),(5,32),(6,48),(7,48)):
        p.run(0x10add8,(slot,bank))
    for fn in (0x1a7d98,0x1a7e70):
        p.run(fn,limit=2000000)
    p.run(0x13847c,stop_before=[0x1384cc])
    p.write(0x46a908,256,4)
    return p


def clock(p,row):
    entry=p.read(ROW_BASE+row*72+0x28,4)
    state,timing=struct.unpack_from('<2I',p.memory,entry)
    period,cycle=struct.unpack_from('<2i',p.memory,timing)
    return state,period,cycle//period


def collect(p,picture):
    # Force the original picture selector into each available frame. The
    # switched timers only drive which original descriptor it passes on.
    for row in ANIMATED:
        state,period,count=clock(p,row)
        p.write(state,period*(picture if picture<count else 0),4)
        p.write(state+0x30,1,4)
    groups=[[] for _ in range(1+ROWS)]
    group=0
    def observe(pc):
        nonlocal group
        reg=p.registers
        if pc==0x1a8418:
            group=1+reg[20]
        elif pc in (0x1a8768,0x1a88e8):
            if pc==0x1a8768:
                slot,columns,rows=reg[4:7]
                ptr=0x50e110
            else:
                slot,ptr,columns,rows=reg[4:8]
            # The local 4-column grid occupies the same 33-column row stride.
            verts=[floats(p,ptr+20*(x+dx)+0x294*y,5)
                   for x in range(columns) for y in range(rows+1) for dx in range(2)]
            groups[group].append((6,slot,[verts[0][2],2*(rows+1)],verts))
        elif pc==0x1a51b0:
            params=[p.float_value(i) for i in (12,13,14,19)]
            params.append(floats(p,reg[29],1)[0])
            groups[group].append((1,reg[4],params,[[p.float_value(i) for i in range(15,19)]]))
        elif pc==0x1a6210:
            slot,count,ptr=reg[4:7]
            rects=[struct.unpack_from('<4i',p.memory,ptr+24*i) for i in range(count)]
            groups[group].append((1,slot,[*[p.float_value(i) for i in (12,13,14)],1,1],rects))
        elif pc in (0x1a4f40,0x1a5d40,0x1a5f68,0x1a6460,0x1a66b8,0x1a6b08):
            raise AssertionError(f'Unexpected stage 1 geometry helper {pc:x}')
    p.run(0x114e80)
    p.run(0x1a8098,limit=2000000,observe=observe)
    assert [c[0] for c in groups[0]]==[6,6,1,1]
    assert [len(c[-1]) for c in groups[0]]==[320,40,1,1]
    assert all(len(g)==1 for g in groups[1:])
    return groups


def extract():
    assert sha256(ELF.read_bytes()).hexdigest()==PIN
    p=prepare()
    counts=[1]+[clock(p,n)[2] if n in ANIMATED else 1 for n in range(ROWS)]
    variants=[collect(p,k) for k in range(max(counts))]
    other=prepare()
    struct.pack_into('<6f',other.memory,0x4a2a58,144.75,190,-540,-155,-61.5,70)
    assert variants==[collect(other,k) for k in range(max(counts))]
    data=bytearray(b'STG1'+struct.pack('<I',1))
    for group,count in enumerate(counts):
        data.extend(struct.pack('<I',count))
        for k in range(count):
            commands=variants[k][group]
            data.extend(struct.pack('<I',len(commands)))
            for kind,slot,params,records in commands:
                data.extend(struct.pack('<4I',kind,slot,len(params),len(records)))
                data.extend(struct.pack(f'<{len(params)}f',*params))
                for rec in records:
                    data.extend(struct.pack(f'<{len(rec)}f',*rec))
        assert all(variant[group]==variants[0][group] for variant in variants[count:])
    return bytes(data),counts


if __name__=='__main__':
    data,counts=extract()
    path=ASSETS/'combat_stage_01.bin'
    path.write_bytes(data)
    print(path,len(data),sha256(data).hexdigest(),counts)
