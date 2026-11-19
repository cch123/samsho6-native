#!/usr/bin/env python3
"""Run the real PS2 CPU file loaders, sequence selector and weighted tactical profile on the JP data."""
import argparse
import json
import random
import struct
import subprocess
import tempfile
from hashlib import sha256
from pathlib import Path

from validate_console_versus_session import fixture, COMMON_AI, CHARACTER_AI, SOURCE_HASH
from validate_nakoruru_resources import ISO
from inspect_iso import Iso, Elf
from extract_resources import recover
from validate_versus_heavy import ROOT, HERE, BUILD, PKG

MEM=0x1a00000
CPU=0x19a0000
REENT=0x1b40000

class CpuSource:
    def __init__(self,assets):
        self.p=p=fixture();self.assets=assets
        # Replace only heap, formatted filename and disc transfer. The actual
        # loader runs all aligned/unaligned copies, marks the cache, then 1693f0
        # adjusts both matchup-distance tables in the loaded character block.
        for pc,value in ((0x110aa0,MEM),(0x104d40,0),(0x317a10,0),(0x102810,1)):
            p.memory[pc:pc+12]=struct.pack('<III',0x3c020000|(value>>16),0x03e00008,0x34420000|(value&65535))
        p.write(0x5d1bf8,REENT,4)
        self.transfers=[]
        self._load(0x158158,[COMMON_AI])
    def _load(self,pc,args):
        p=self.p
        def asciiz(a):return bytes(p.memory[a:a+64]).split(b'\0')[0].decode('ascii')
        def watch(address):
            if address==0x317a10:
                dest,fmt,prefix,character=p.registers[4:8]
                name=asciiz(fmt)%(asciiz(prefix),character)
                p.memory[dest:dest+len(name)+1]=name.encode()+b'\0'
            elif address==0x102810:
                name=asciiz(p.registers[4])
                data=(self.assets/name).read_bytes()
                assert len(data)<=p.registers[6]
                index=p.registers[5]
                p.memory[index:index+len(data)]=data;self.transfers.append(name)
        assert p.run(pc,args,observe=watch,limit=1000000)[0]==1
    def character(self,id,seat):
        addr=CHARACTER_AI+seat*0x4c4c
        self._load(0x158380,[addr,id])
        assert self.p.read(addr,4)==1 and self.p.read(addr+4,4)==id
        return addr

DRIVER=r'''
#include "cpu_tactics.hpp"
#include <iostream>
#include <utility>
int main(int argc,char** argv) {
    ss6::CpuTactics common(argv[1],0);
    for(unsigned i=0;i<64;++i)std::cout.put(char(common.normalAttackSituation(i)));
    for(int i=0;i<0x6a0;++i)
        for(bool projectile:{false,true})std::cout.put(char(common.specialPattern(i,projectile)));
    for(int i:{-1,0x6a0})std::cout.put(char(common.specialPattern(i,false)));
    unsigned character;
    while(std::cin>>character) {
        ss6::CpuTactics t(argv[1],character);
        for(unsigned index=0;index<256;++index)
            for(auto byte:t.sequence(index))std::cout.put(char(byte));
        for(unsigned off=8;off<0x4c4c;++off)std::cout.put(char(t.characterByte(off)));
    }
}
'''
PROFILE=r'''
#include "cpu_tactics.hpp"
#include <iostream>
int main(int argc,char** argv) {
    ss6::CpuTactics tactics(argv[1],0);
    ss6::GameRandom r;
    int level,difficulty,clock,category;unsigned pattern,a,b;
    while(std::cin>>r.mode>>r.gameSeed>>r.librarySeed>>level>>difficulty>>clock>>category>>pattern>>a>>b) {
        const auto v=tactics.chooseProfile(r,level,difficulty,clock,category);
        std::cout<<v.tierE4<<' '<<v.patternE8<<' '<<v.actionEC<<' '<<v.variantF0<<' '<<r.gameSeed<<' '
                 <<r.librarySeed<<' '<<tactics.distanceBand(pattern,{a},{b})<<'\n';
    }
}
'''

def build(tmp,name,source):
    cpp=tmp/(name+'.cpp');cpp.write_text(source)
    exe=tmp/name
    subprocess.run(['c++','-O2','-std=c++20','-I',ROOT/'src',cpp,BUILD/'libss6-runtime.a','-o',exe],check=True)
    return exe

def validate(assets):
    src=CpuSource(assets);p=src.p;buf=bytearray()
    # Match the ordinary attack dispatch's indexed byte and run both original
    # lookup functions for every special, including their final two shared banks.
    buf.extend(p.memory[0x4d94f8:0x4d94f8+64])
    for i in range(0x6a0):
        for pc in (0x168ee0,0x168f10):buf.append(p.run(pc,[i])[0])
    for i in (0xffffffff,0x6a0):buf.append(p.run(0x168ee0,[i])[0])
    for id in range(51):
        addr=src.character(id,id%2)
        prev=len(src.transfers);src.character(id,id%2);assert prev==len(src.transfers)
        for seq in range(256):
            at=p.run(0x15d720,[seq,id%2])[0]
            buf+=p.memory[at:at+4]
        buf+=p.memory[addr+8:addr+0x4c4c]
    assert len(src.transfers)==52
    disc=Iso(ISO)
    try:
        elf=disc.read('/SLPS_255.59');assert sha256(elf).hexdigest()==SOURCE_HASH
        container=disc.by_path['/SAM_DATA.BIN']
        entries={e['name']:e for e in recover(Elf(elf),container['size'])}
        for name in src.transfers:
            item=entries[name]
            raw=disc.read_at(container['lba']*disc.block+item['offset'],item['size'])
            assert raw==(assets/name).read_bytes(),name
    finally:disc.file.close()
    rows=[];expected=[];rng=random.Random(0x15bef0)
    # 15bef0 queries the independently validated round clock; hold its public
    # result fixed to cover every table column and the unlimited random branch.
    rng_addr=0x1407d0
    p.memory[rng_addr:rng_addr+8]=struct.pack('<II',0x03e00008,0)
    bits=lambda x:struct.unpack('<I',struct.pack('<f',x))[0]
    for n in range(1800):
        mode=(0,1,-2)[n%3];game=rng.getrandbits(32);lib=rng.getrandbits(64)
        level=n%11;diff=n//11%10;clock=n//7%52-1;kind=n%5
        pat=rng.randrange(3392)
        x,y=[bits(rng.randrange(-600,601)*0.25) for _ in range(2)]
        p.write(0x443150,mode&0xffffffff,4);p.write(0x3d2e80,game,4);p.write(REENT+0xa8,lib,8)
        p.write(CPU+0x100,level,4);p.write(0x43d05c,diff,1)
        p.write(rng_addr+4,0x24020000|(clock&65535),4)
        p.run(0x15bef0,[CPU,kind])
        p.write(CPU+0x2040,x,4);p.write(CPU+0x3040,y,4)
        band=p.run(0x15c0f0,[CPU+0x2000,CPU+0x3000,pat])[0]
        rows.append((mode,game,lib,level,diff,clock,kind,pat,x,y))
        expected.append([p.read(CPU+i,4) for i in (0xe4,0xe8,0xec,0xf0)]+
                        [p.read(0x3d2e80,4),p.read(REENT+0xa8,8),band])
    with tempfile.TemporaryDirectory() as folder:
        tmp=Path(folder);exe=build(tmp,'bytes',DRIVER)
        result=subprocess.run([exe,assets],input=b' '.join(str(i).encode() for i in range(51)),capture_output=True,check=True)
        assert result.stdout==buf
        exe=build(tmp,'profiles',PROFILE)
        result=subprocess.run([exe,assets],input=''.join(' '.join(map(str,row))+'\n' for row in rows),
                              text=True,capture_output=True,check=True)
        for i,(line,want) in enumerate(zip(result.stdout.splitlines(),expected,strict=True)):
            assert list(map(int,line.split()))==want,(rows[i],line,want)
    return dict(status='passed',original_sha256=SOURCE_HASH,loaded_files=len(src.transfers),verified_character_banks=51,
                compared_sequences=51*256,compared_bytes=len(buf),special_pattern_lookups=2*0x6a0+2,ordinary_attack_rows=64,profile_and_distance_cases=len(rows),
                loaded_stream_sha256=sha256(buf).hexdigest())

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--package',action='store_true');args=parser.parse_args()
    result=validate(PKG/'assets' if args.package else HERE/'extracted/resources')
    (ROOT/'outputs/ss6-feasibility/cpu-tactics-validation.json').write_text(json.dumps(result,indent=2)+'\n')
    print(result)
