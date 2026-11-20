#!/usr/bin/env python3
"""Compare stage 1's ten clocks, shared RNG and reloads with the original EE scheduler."""
import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import re
import struct
import subprocess
import tempfile

from extract_combat_stage01 import ANIMATED,ROW_BASE,clock,extract
from extract_resources import recover
from extract_versus_result_layout import canvas
from inspect_iso import Elf,Iso
from validate_character_select import Source as SelectSource, make_case
from validate_dash_motion import ASSETS,ELF,PIN,ROOT

REPORT=ROOT/'outputs/ss6-feasibility/combat-stage-01-state-validation.json'
ISO=Path.home()/'Downloads/ps2/Samurai Spirits - Tenka-ichi Kenkakuden (Japan).iso'
DRIVER=r'''
#include "combat_stage_state.hpp"
#include "game_random.hpp"
#include <iostream>
int main() {
    ss6::CombatStageState s;
    ss6::StageCamera c;
    ss6::GameRandom random;
    char op;
    uint64_t a;
    unsigned b;
    while(std::cin>>op>>a>>b) {
        if(op=='R') {
            ss6::CombatStageState next;
            next.stage=a;
            next.inheritRematch(s);
            s=next;
        }
        if(op=='V')s.visit(c,a,b,&random);
        if(op=='S')random.librarySeed=a;
        std::cout<<s.stage<<' '<<s.handler()<<' '<<s.visible<<' '<<s.suppressGeometry
                 <<' '<<random.librarySeed<<' '<<random.gameSeed;
        for(auto x:s.layers01)std::cout<<' '<<x.elapsed<<' '<<x.picture<<' '<<x.flags;
        for(unsigned row=0;row<28;++row)std::cout<<' '<<s.pictureForRow(row);
        std::cout<<'\n';
    }
}
'''


def archive(path):
    iso=Iso(path)
    elf=Elf(iso.read('/SLPS_255.59'))
    assert sha256(elf.data).hexdigest()==PIN
    archive=iso.by_path['/SAM_DATA.BIN']
    lookup={e['name']:e for e in recover(elf,archive['size'])}
    data={}
    for address in (0x652cb8,0x652cc8,0x652cd8,0x652ce8,0x652cf8,0x652d08):
        source=elf.cstring(address)
        name=source.replace('.pvr','.tex').replace('.pvp','.pal')
        e=lookup[name]
        raw=iso.read_at(archive['lba']*iso.block+e['offset'],e['size'])
        assert raw==(ASSETS/name).read_bytes()
        data[source]=dict(file=name,bytes=len(raw),sha256=sha256(raw).hexdigest(),
                          archive_offset=e['offset'])
    # Inventory the same raw texture archive family for subsequent stages.
    # Each entry point has a distinct task, so a shared texture format alone
    # does not establish identical geometry, time or palette logic.
    inventory={}
    for i in range(12):
        files=sorted(n for n in lookup if re.fullmatch(fr'bg{i:02}_\d+\.(tex|pal)',n))
        for name in files:
            e=lookup[name]
            source_bytes=iso.read_at(archive['lba']*iso.block+e['offset'],e['size'])
            assert source_bytes==(ASSETS/name).read_bytes()
        inventory[i]=dict(constructor=hex(struct.unpack_from('<I',elf.data,elf.offset(0x50e080+i*4))[0]),
                          files=files)
    return data,inventory


def clocks(driver):
    p=canvas()
    p.run(0x112570)
    for slot,bank in ((4,32),(5,32),(6,48),(7,48)):
        p.run(0x10add8,(slot,bank))
    p.run(0x13847c,stop_before=[0x1384cc])
    reent=p.read(0x5d1bf8,4)+0xa8
    p.write(0x3d2e80,1,4)
    active=None
    calls=Counter()
    states=[clock(p,row)[0] for row in ANIMATED]
    command=[]
    expected=[]
    flags=[set() for _ in states]
    shown=[set() for _ in states]
    instructions=0
    def record(op):
        if op in (0x1a7e70,0x1a74d0,0x316b90):
            calls[hex(op)]+=1
    def run(addr,params=(),stop=()):
        nonlocal instructions
        _,n=p.run(addr,params,stop_before=stop,limit=600000,observe=record)
        instructions+=n
    def snap(cmd,visible,skip):
        command.append(cmd)
        layers=[tuple(p.read(o+offset,4) for offset in (0,4,0x30)) for o in states]
        if active==1:
            selected={row:r[1] for row,r in zip(ANIMATED,layers)}
        else:
            selected={}
            for row in (1,2,15,16,18,21,22):
                obj=p.read(p.read(0x513138+row*72+0x28,4),4)
                selected[row]=p.read(obj+4,4)
        expected.append([active,0x1a8098 if active==1 else 0x1a7810,int(visible),int(skip),
                         p.read(reent,8),p.read(0x3d2e80,4),
                         *(v for row in layers for v in row),*(selected.get(i,0) for i in range(28))])
        for n,(_,pic,flag) in enumerate(layers):
            flags[n].add(flag)
            shown[n].add(pic)
    def switch(stage):
        nonlocal active
        if active is not None:
            run(0x11e3a0,(0xfa1,));run(0x112a70,(0xfa1,))
        # Exercise task creation and the full post-I/O tail, retaining the same
        # EE process. The I/O interval supplies texture/CLUT data only.
        entry,tail,marker={0:(0x1a7690,0x1a77b4,0x5137b0),
                           1:(0x1a7f28,0x1a804c,0x5152a8)}[stage]
        run(entry,stop=(entry+0x2c,))
        p.put(17,0x510000)
        p.write(0x1fff820,0x1ffff00,8)
        seed=p.read(reent,8)
        run(tail)
        assert p.read(marker,4)==1 and p.read(reent,8)==seed
        active=stage
        snap(f'R {stage} 0',False,False)
    def tick(delta,skip,full):
        p.write(0x46a908,delta,4)
        p.write(0x50e04c,int(skip),4)
        if full:
            run(0x114e80)
            run(0x112838)
            calls['whole_scheduler']+=1
        elif active==1:
            for row in ANIMATED:
                p.put(16,ROW_BASE+row*72)
                p.put(22,0x515230)
                run(0x1a8614,stop=(0x1a8460,))
                calls['row_slices']+=1
        else:
            for row in (1,2,15,16,18,21,22):
                p.put(16,0x513138+row*72)
                run(0x1a7ce8,stop=(0x1a7b40,))
        snap(f'V {delta} {int(skip)}',True,skip)

    p.write(reent,1,8)
    switch(1)
    for i in range(3600):
        if i in (70,600,1300,1700):
            switch({70:1,600:0,1300:1,1700:1}[i])
        if i in (721,2000):
            newseed=0xfeeaaaa000000002+i
            p.write(reent,newseed,8)
            snap(f'S {newseed} 0',True,expected[-1][3])
        delta=(256,256,128,64,0,256)[i%6]
        if i%533<20:delta=0
        if 1900<=i<1910:delta=25*256
        tick(delta,i%117<11,i in (0,1,71,1299,1300,1301,1700,1701,1900,1901) or i%239==0)
    output=subprocess.run([driver],input='\n'.join(command)+'\n',text=True,capture_output=True,check=True)
    for i,(actual,want) in enumerate(zip(output.stdout.splitlines(),expected,strict=True)):
        got=list(map(int,actual.split()))
        assert got==want,(i,command[i],[(j,a,b) for j,(a,b) in enumerate(zip(got,want)) if a!=b])
    assert calls['0x1a7e70']==calls['0x1a74d0']==1
    for i in range(len(ANIMATED)):
        maxpic=clock(p,ANIMATED[i])[2]
        assert shown[i]==set(range(maxpic)),(ANIMATED[i],shown[i],maxpic)
        assert flags[i]==({1} if i<3 else {0,2})
    return dict(snapshots=len(expected),fields=len(expected[-1]),original_instructions=instructions,
                calls=calls,per_row_pictures={r:sorted(x) for r,x in zip(ANIMATED,shown)},
                checks='continuous clocks, rare idle and active thresholds, shared RNG, pause, fractional and long ticks, hidden geometry, stage 1→1→0→1→1')


def reselect():
    # Prove the two constructors' once guards are also retained across the
    # intervening character/spirit/stage selection tasks in a single EE RAM.
    owner,seed,pads=make_case('reselect')
    select=SelectSource(owner,seed,True)
    p=select.p
    def load():
        p.put(17,0x510000)
        p.write(0x1fff820,0x1ffff00,8)
        p.run(0x1a804c,limit=500000)
    def snapshot():
        # Include each complete mutable 0xd4-byte descriptor and its flag.
        return (p.read(0x5152a8,4),*[bytes(p.memory[a:a+0xd4]) for a in
                (clock(p,row)[0] for row in ANIMATED)])
    load()
    p.write(0x46a908,256,4)
    for _ in range(45):
        for row in ANIMATED:
            p.put(16,ROW_BASE+row*72)
            p.put(22,0x515230)
            p.run(0x1a8614,stop_before=(0x1a8460,))
    retained=snapshot()
    for fn in (0x112570,0x11e290,0x127eb0,0x128008):
        p.run(fn,limit=500000)
    # From the random stage cell step right twice across 0 and confirm 1.
    pads[369][owner]=128
    pads[374][owner]=0
    pads[404][owner]=4
    for tick,held in enumerate(pads,1):
        chosen=select.step(held)
        assert snapshot()==retained
        if select.complete:
            break
    assert select.complete and chosen[7]==1
    load()
    assert snapshot()==retained
    return dict(select_updates=tick,original_select_instructions=select.visits,
                chosen_stage=chosen[7],complete_descriptor_bytes=len(ANIMATED)*0xd4,
                scope='Real 128008/112838 reselect input through the original 125e10 face-off request, followed by 1a804c reload tail. Select external I/O and drawing use the existing selection fixture.')


def main():
    args=argparse.ArgumentParser()
    args.add_argument('--iso',type=Path,default=ISO)
    args=args.parse_args()
    files,inventory=archive(args.iso)
    geometry,counts=extract()
    assert geometry==(ASSETS/'combat_stage_01.bin').read_bytes()
    with tempfile.TemporaryDirectory() as tmp:
        cpp=Path(tmp)/'stage.cpp'
        binary=Path(tmp)/'stage'
        cpp.write_text(DRIVER)
        src=ROOT/'src'
        subprocess.run(['c++','-std=c++20','-ffp-contract=off','-O2','-I',src,cpp,src/'combat_stage_state.cpp',
                        src/'game_random.cpp',src/'stage_camera.cpp',src/'scalar_float.cpp','-o',binary],check=True)
        result=clocks(binary)
    report=dict(original=PIN,archive_files=files,stage_asset_inventory=inventory,
                geometry=dict(bytes=len(geometry),sha256=sha256(geometry).hexdigest(),picture_counts=counts,
                              camera_invariance_checks=6),clock_validation=result,reselect=reselect())
    REPORT.write_text(json.dumps(report,indent=2)+'\n')
    print(REPORT,result)

if __name__=='__main__':main()
