#!/usr/bin/env python3
"""Camera shake requests, publication and round resets against the Japanese EE code."""
from collections import Counter
import json
from pathlib import Path
import struct
import subprocess
import tempfile

from inspect_iso import Elf
from mips_probe import Probe,signed
from round_entry_oracle import buffered_stdout
from validate_dash_motion import ELF,PIN,ROOT,digest

PROJECTION=(0x4a2a58,0x4a2a5c,0x4a2a60,0x4a2a6c,0x4a2a68)
CAMERA_OFFSETS=(0,4,8,12,16,20,28,32,36,40,44,48,52,68,72)
FLOAT_FIELDS=(4,8,12,32,36,40)
REPORT=ROOT/'outputs/ss6-feasibility/camera_shake_validation.json'

def bits(f):return struct.unpack('<I',struct.pack('<f',f))[0]

class OriginalCamera:
    """Independent EE camera. Projection words have the order of --stage-fields."""
    def __init__(self,probe=None,battle=0x1b00000):
        self.p=probe if probe is not None else Probe(ELF.read_bytes(),finite_model=True)
        self.battle=battle;self.at=battle+0x34
        self.p.write(0x4d3d00,battle,4)
        self.instructions=0;self.calls=Counter()
        buffered_stdout(self.p)
        self.seed()

    def call(self,pc,*args):
        ret,n=self.p.run(pc,args,limit=100000)
        self.instructions+=n;self.calls[hex(pc)]+=1
        return ret

    def seed(self,x=320,y=120,width=320,delta=256):
        p=self.p
        p.memory[self.at:self.at+0xd0]=bytes(0xd0)
        p.write(self.at,delta,4);p.write(self.battle+0x110,256,4)
        for k,v in zip(FLOAT_FIELDS,(x,y,width,x,y,width)):p.write(self.at+k,bits(v),4)
        self.publish()

    def request(self,x,y):self.call(0x141528,x,y)
    def publish(self):self.call(0x146870,self.at)
    def update(self,x0,y0,x1,y1,freeze=False,elapsed=256):
        self.p.write(self.battle+0x140,{256:0,128:1,85:2,0:3}[elapsed],4)
        self.p.floats[12:16]=list(map(bits,(x0,y0,x1,y1)))
        self.call(0x146460,self.at)
        self.call(0x1463d0,self.at,int(freeze))

    def projection(self):return tuple(self.p.read(a,4) for a in PROJECTION)
    def snapshot(self):
        p=self.p
        return [p.read(self.at+k,4) if k in FLOAT_FIELDS else signed(p.read(self.at+k,4),32)
                for k in CAMERA_OFFSETS]+list(self.projection())

DRIVER=r'''
#include "stage_camera.hpp"
#include <bit>
#include <iostream>
int main() {
    ss6::StageCamera c; char op;
    while(std::cin>>op) {
        if(op=='S'){
            c={};std::cin>>c.x>>c.y>>c.width>>c.delta;
            c.targetX=c.x;c.targetY=c.y;c.targetWidth=c.width;c.publish();
        } else if(op=='Q'){int x,y;std::cin>>x>>y;c.requestShake(x,y);}
        else if(op=='V')c.publish();
        else if(op=='R')c.resetRound();
        else if(op=='D')std::cin>>c.delta;
        else if(op=='C'){unsigned k;int t;std::cin>>k>>t;c.appendCommand(k,t);}
        else if(op=='U'){
            float x,y,u,v;int freeze,d;std::cin>>x>>y>>u>>v>>freeze>>d;c.update(x,y,u,v,d,freeze);
        }
        std::cout<<c.delta;
        for(float v:{c.x,c.y,c.width})std::cout<<' '<<std::bit_cast<unsigned>(v);
        std::cout<<' '<<c.left<<' '<<c.right<<' '<<c.top;
        for(float v:{c.targetX,c.targetY,c.targetWidth})std::cout<<' '<<std::bit_cast<unsigned>(v);
        for(int v:{c.vx,c.vy,c.vwidth,c.shakeX44,c.shakeY48})std::cout<<' '<<v;
        for(float v:{c.projectionX,c.projectionY,c.depth,c.depthOffset,c.verticalOffset})
            std::cout<<' '<<std::bit_cast<unsigned>(v);
        std::cout<<'\n';
    }
}
'''

def exercise(exe):
    o=OriginalCamera()
    cmd=[];expected=[];groups=Counter();label='initial'
    def take(op,*args):
        cmd.append(' '.join(map(str,(op,*args))));groups[label]+=1
        if op=='S':o.seed(*args)
        elif op=='D':o.p.write(o.at,args[0],4)
        elif op=='R':o.call(0x146388,o.at)
        elif op=='C':o.call(0x146b30,o.at,*args)
        elif op=='Q':o.request(*args)
        elif op=='V':o.publish()
        elif op=='U':o.update(*args)
        expected.append(o.snapshot())
    for eye in ((320,120,320),(160,120,444),(480,336,444),(320,180.5,360)):
        for pair in ((-1,16),(16,-1),(16,16),(0,32),(24,0),(-1,30)):
            for dt in (0,64,85,128,192,256,512):
                label='frozen_fractional_full_double_delta_or_world_edge'
                take('S',*eye,dt);take('Q',*pair)
                for t in range(42):
                    if t==6:take('Q',-1,-1)
                    if t==9:take('Q',8,-1)
                    if t==12:take('Q',-1,2)
                    take('V')
    label='queued_motion_reset_and_independent_retrigger'
    for first in (0,1,2,3,4,5,7,10):
        for frozen in (0,1):
            take('S',320,155.125,358.625,128)
            take('C',first,0 if first<3 else 3);take('Q',16,16)
            for i in range(23):
                if i==6:take('R')
                if i==13:take('Q',-1,32)
                take('U',76+i,27,407,17-i,frozen,85)
    label='word_shift_and_repeated_input'
    take('S',320,130,340,256)
    for pair in ((1,2),(0x800000,0x1000001),(-27,-99),(0,0),(3,9),(8,-1)):
        take('Q',*pair);take('V')
    out=subprocess.run([exe],input='\n'.join(cmd)+'\n',text=True,capture_output=True,check=True)
    for i,(line,want) in enumerate(zip(out.stdout.splitlines(),expected,strict=True)):
        got=list(map(int,line.split()))
        assert got==want,(i,cmd[i],[(n,a,b) for n,(a,b) in enumerate(zip(got,want)) if a!=b])
    return dict(snapshots=len(expected),groups=dict(groups),original_calls=dict(o.calls),original_instructions=o.instructions)

def producers():
    raw=ELF.read_bytes()
    elf=Elf(raw)
    code=next(section for section in elf.sections if section['name']=='.text')
    p=Probe(raw)
    # Inspect genuine direct J/JAL instructions in the executable text.
    # Data embedded in the phase tables uses an operation number instead.
    entry=0x141528
    calls=[]
    for at in range(code['address'],code['address']+code['size'],4):
        word=p.read(at,4)
        if word in (0x08000000|(entry>>2),0x0c000000|(entry>>2)):
            calls.append(at)
    assert calls==[0x11ec5c,0x14295c,0x1429b0,0x1676c0,0x1f4124,0x1ff0d0,0x1ff20c]

    config=0x1c00000
    system_gates=[]
    for system in (0,1,2,3,4,5,7,8):
        p.write(config,system,4)
        allowed,_=p.run(0x14f968,[config])
        system_gates.append((system,allowed))
    assert [system for system,allowed in system_gates if allowed]==[2]

    # All resource00 paired-action rows end before the next character's first
    # row. The last four alignment bytes do not constitute another record.
    ptr=0x4e4a68
    first,following=p.read(ptr,4),p.read(ptr+4,4)
    opcodes=[p.read(first+20*i+19,1) for i in range((following-first)//20)]
    assert len(opcodes)==17 and 44 not in opcodes
    assert p.read(0x5f1210+44*4,4)==0x1676bc
    actions=[p.read(0x4e8fe8+i*4,4) for i in range(51)]
    owners=[next(i for i in range(50) if actions[i]<=pc<actions[i+1])
            for pc in (0x1f4124,0x1ff0d0,0x1ff20c)]
    assert owners==[10,27,27]
    return dict(direct_call_sites=[hex(pc) for pc in calls],
                non_custom_gauge_system_gate=dict(system_gates),
                character_specific_handler_ranges=owners,
                character_00_paired_script_operations=opcodes,
                shared_script_shake_operation=44,
                scope='Body FE 0x40/0x80 uses X16/Y16 before 146460 and 1463d0. The 11ec5c gauge branch requires 14f968, system2 or system6 custom byte3=12; local system0 returns false. Paired-script operation44 asks for X0/Y32. No complete resource00 paired-action row contains it. The X24 and other two independent Y16 callers are in character-specific handler ranges 10 and 27.')

def main():
    assert digest(ELF)==PIN
    with tempfile.TemporaryDirectory() as d:
        root=ROOT/'src';cpp=Path(d)/'driver.cpp';exe=Path(d)/'driver'
        cpp.write_text(DRIVER)
        subprocess.run(['c++','-O2','-std=c++20', '-I',root,cpp,root/'stage_camera.cpp',root/'scalar_float.cpp','-o',exe],check=True)
        result=exercise(exe)
    report=dict(status='passed',elf_sha256=PIN,source_sha256=digest(ROOT/'src/stage_camera.cpp'),**result,producer_audit=producers(),
                scope='Complete 141528/146ba0,146388/146418,146460,1463d0,146870/146dc8/146e28/146d60 with finite EE scalar model. Compare stored and projected centers, world bounds, targets, velocities, both signed 8.8 residuals and all five projection globals after every request, reset, publish or queued movement.')
    REPORT.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report))

if __name__=='__main__':main()
