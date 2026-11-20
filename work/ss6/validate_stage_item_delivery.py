#!/usr/bin/env python3
"""Compare the running courier, falling parcel and original draw queue, word for word."""
from concurrent.futures import ProcessPoolExecutor
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
from validate_dash_motion import ASSETS, ELF, PIN, ROOT, digest
from validate_weapon_handling import setup

LIB=ROOT/'work/ss6/build-native/libss6-runtime.a'
OUT=ROOT/'outputs/ss6-feasibility/stage_item_delivery_validation.json'
COURIER, ITEM=0x132c220,0x132c358
DRIVER=r'''
#include "stage_item_delivery.hpp"
#include "auxiliary_objects.hpp"
#include <bit>
#include <iostream>
void emit(uint32_t n){std::cout.write(reinterpret_cast<const char*>(&n),4);}
int main(int,char** argv) {
    ss6::StageItemDelivery d;ss6::AuxiliaryObjects bank(argv[1],{0,0,51});ss6::ObjectDrawQueue draws;
    ss6::GaugeState g{};ss6::StageCamera c;
    int op,kind,x,side,rate,pause,hide;
    while(std::cin>>op>>kind>>x>>side>>c.projectionX>>c.depth>>rate>>pause>>hide) {
        if(op==1)d.start(kind,x,side,c);else if(op==2)d.clear();
        if(hide)d.hideNextDraw();
        g.paused46a940=pause;g.delta46a908=rate;g.words910[2]=1;
        draws.beginFrame();d.visit(g,bank,draws);
        emit(d.busy());emit(d.itemIndex());emit(d.itemCallback());emit(d.courierActive());emit(draws.count);
        for(auto body:{&d.courier(),&d.item()})for(int i=0;i<78;++i)emit((*body)[i]);
        for(const auto& row:draws.active())for(auto n:row)emit(n);
    }
}
'''

def case(arg):
    exe,kind=arg
    p=setup(0)[0].p;p.finite_model=True
    for addr,name in ((0x46a9b0+2*0x1800,'aid_51.bin'),(0x1a40000,'act_51.bin')):
        data=(ASSETS/name).read_bytes();p.memory[addr:addr+len(data)]=data
    p.write(0x4751b8,0x1a40000,4);p.write(0x46a9a8,51,4);p.write(0x4c3808,3,4)
    _,n=p.run(0x1b5090,limit=500000)
    side=kind%2
    def commands():
        for t in range(940):
            # Odd delivery starts from the right. Move/zoom the camera after
            # the request to detect recomputed or mirrored launch coordinates.
            op=1 if t in (1,7) else 0
            # Two mid-flight pickups/resets exercise the separate lifetime
            # of the carrier, including a fresh request before it has exited.
            if kind==16 and t in (170,175):op=2 if t==170 else 1
            if kind==17 and t==220:op=2
            k=kind if t!=7 else (kind+1)%19
            yield op,k,186+kind*13,int(not side) if t==7 else side,275 if t>=7 else 351.5,-444.25 if kind%3 else -400,128 if 73<=t<92 else 256,int(95<=t<99),int(t in (0,13,149,166,501))
    commands=list(commands())
    stream=''.join(' '.join(map(str,c))+'\n' for c in commands)
    proc=subprocess.run([exe,ASSETS],input=stream.encode(),capture_output=True,check=True)
    values=memoryview(proc.stdout).cast('I');pos=0;transitions=[];last=None;totals=[0,0];ground=None;idle=None
    for tick,(op,k,x,mirror,cx,depth,rate,pause,hide) in enumerate(commands):
        p.write(0x46a940,pause,4);p.write(0x46a918,1,4);p.write(0x46a908,rate,4)
        struct.pack_into('<f',p.memory,0x4a2a58,cx);struct.pack_into('<f',p.memory,0x4a2a60,depth)
        if op==1:_,m=p.run(0x1b5800,[k,x,mirror]);n+=m
        elif op==2:_,m=p.run(0x1b5980);n+=m
        if hide:p.run(0x1b59a0)
        p.run(0x1207d8)
        _,m=p.run(0x1b51b8,limit=500000);n+=m
        busy,floor,callback,runner,count=[p.read(a,4) for a in (0x132c218,0x132c4bc,0x132c4c0,0x132c49c,0x4a2250)]
        want=[busy,floor,callback,runner,count]
        for address in (COURIER,ITEM):want.extend(struct.unpack_from('<78I',p.memory,address))
        for i in range(count):want.extend(struct.unpack_from('<82I',p.memory,0x479250+328*i))
        got=values[pos:pos+len(want)];pos+=len(want)
        diff=[(i,hex(a),hex(b)) for i,(a,b) in enumerate(zip(got,want)) if a!=b]
        assert len(got)==len(want) and not diff,(kind,tick,diff[:12],p.read(COURIER+0x24,4),p.read(ITEM+0x24,4),hex(callback))
        state=(busy,floor,callback,runner,p.read(COURIER+0x24,4),p.read(ITEM+0x24,4))
        if state!=last:transitions.append([tick,*state]);last=state
        totals[0]+=int(runner!=0 and not hide);totals[1]+=int(callback!=0 and not hide)
        if floor!=0xffffffff and ground is None:ground=tick
        if tick>100 and not runner and not busy:idle=tick if idle is None else idle
    assert pos==len(values) and idle is not None and ground is not None,(kind,idle,ground)
    return dict(kind=kind,from_right=bool(side),frames=len(commands),first_pickup_tick=ground,idle_tick=idle,
                courier_draws=totals[0],item_draws=totals[1],state_changes=transitions,original_instructions=n)

def main():
    assert digest(ELF)==PIN
    with tempfile.TemporaryDirectory() as temp:
        path=Path(temp);driver=path/'driver';cpp=path/'driver.cpp';cpp.write_text(DRIVER)
        subprocess.run(['c++','-std=c++20','-ffp-contract=off','-O2','-I',ROOT/'src',cpp,ROOT/'src/stage_item_delivery.cpp',LIB,'-o',driver],check=True)
        with ProcessPoolExecutor(6) as pool:rows=list(pool.map(case,[(driver,k) for k in (map(int,sys.argv[1:]) if sys.argv[1:] else range(19))]))
        for r in rows:print(r['kind'],r['first_pickup_tick'],r['idle_tick'])
        if not sys.argv[1:]:
            doc=dict(status='passed',elf_sha256=PIN,runtime_sha256=digest(LIB),module_sha256=digest(ROOT/'src/stage_item_delivery.cpp'),
                     scope='Original 1b5090, 1b5800, 1b51b8, 1b59a0 and 1b5980. Both work objects in full (78 EE words each), complete 82-word graphics submissions, active/pickable kind/handler/runner gates. Supplied item choices, camera, rate, pause, clears and hide requests; selection RNG and effects after player pickup have separate owners.',
                     cases=rows)
            OUT.write_text(json.dumps(doc,indent=2)+'\n')
if __name__=='__main__':main()
