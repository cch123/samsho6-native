#!/usr/bin/env python3
"""Compare the native save image, its CRC container and option decoding with SLPS-25559."""
import hashlib
import json
import random
import subprocess
import tempfile
from pathlib import Path

from extract_console_versus_art import prepare, ORIGINAL
from extract_save_default import factory_image

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT/'outputs/ss6-feasibility/native-viewer/assets'
REPORT = ROOT/'outputs/ss6-feasibility/system_data_validation.json'
DRIVER = r'''
#include "system_data.hpp"
#include <cstdio>
#include <iostream>
#include <vector>
int main(int argc,char** argv) {
    ss6::SystemData data(argv[1]);
    std::string op;
    while(std::cin>>op) {
        if(op=="crc") {
            size_t n;std::cin>>n;std::vector<uint8_t> b(n);
            for(auto& v:b){unsigned x;std::cin>>x;v=uint8_t(x);}
            std::cout<<ss6::SystemData::checksum(b)<<'\n';
        } else if(op=="seal") {
            // Mutate the image, write the container and read it back.
            unsigned n;std::cin>>n;
            for(unsigned i=0;i<n;++i){size_t at;unsigned v;std::cin>>at>>v;data.image()[at]=uint8_t(v);}
            data.save(argv[2]);
            ss6::SystemData copy(argv[1]);
            std::cout<<copy.load(argv[2])<<' '<<(copy.image()[0]==data.image()[0]&&std::equal(copy.image().begin(),copy.image().end(),data.image().begin()))<<'\n';
        } else if(op=="wins") {
            unsigned index;std::cin>>index;data.option(7)=uint8_t(index);
            const auto w=data.cpuMatchWins();std::cout<<w[0]<<' '<<w[1]<<'\n';
        } else if(op=="unlock") {
            unsigned d6,character,value;std::cin>>d6>>character>>value;
            data.restoreFactory();data.option(0x7e)=uint8_t(d6);data.option(0x47+character)=uint8_t(value);
            std::cout<<data.modeMenuUnlock()<<'\n';
        } else if(op=="factory") {
            data.restoreFactory();
            std::cout<<data.gameLevel()<<' '<<data.gameTime()<<' '<<data.arcadeRules()<<' '<<data.cpuMatchPoint()<<' '
                     <<data.versusMatchPoint()<<' '<<data.damageLevel()<<' '<<data.brightness()<<' '
                     <<data.spiritsGauge(0)<<' '<<data.mikiriGauge(0)<<' '<<data.kyouchiGauge(0)<<' '
                     <<data.spiritsGauge(1)<<' '<<data.mikiriGauge(1)<<' '<<data.kyouchiGauge(1)<<' '<<data.autoSave()<<'\n';
        }
    }
}
'''

def main():
    rng = random.Random(0x10dcc0)
    p = prepare()
    factory = factory_image()
    assert (ASSETS/'save_default.bin').read_bytes() == factory
    BUF = 0x1c00000
    with tempfile.TemporaryDirectory() as tmp:
        cpp = Path(tmp)/'system.cpp'; cpp.write_text(DRIVER); exe = cpp.with_suffix(''); save = Path(tmp)/'save.bin'
        subprocess.run(['c++','-std=c++20','-O2','-I',ROOT/'src',cpp,ROOT/'src/system_data.cpp','-o',exe],check=True)
        proc = subprocess.Popen([exe,ASSETS,save],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
        def ask(line):
            proc.stdin.write(line+'\n'); proc.stdin.flush(); return proc.stdout.readline().split()
        instructions = crcs = 0
        for case in range(96):
            n = rng.choice((0,1,2,7,64,255,1024))
            data = bytes(rng.randrange(256) for _ in range(n))
            p.memory[BUF:BUF+n] = data
            want,count = p.run(0x10dcc0,[BUF,n],limit=200000); instructions += count; crcs += 1
            assert int(ask(f'crc {n} '+' '.join(map(str,data)))[0]) == want,(case,n)
        seals = 0
        for case in range(6):
            edits = [(rng.randrange(0x65a8),rng.randrange(256)) for _ in range(rng.randrange(0,40))]
            assert ask(f'seal {len(edits)} '+' '.join(f'{a} {v}' for a,v in edits)) == ['1','1']
            native = save.read_bytes(); assert len(native) == 0x6800
            # 10dd60 seals the 6800-byte staging buffer; 10dd18 verifies it.
            p.memory[BUF:BUF+0x6800] = native[:0x65a8]+bytes(0x6800-0x65a8)
            _,count = p.run(0x10dd60,[BUF],limit=3000000); instructions += count
            assert bytes(p.memory[BUF:BUF+0x6800]) == native,case
            ok,count = p.run(0x10dd18,[BUF],limit=3000000); instructions += count; assert ok == 0
            p.memory[BUF+rng.randrange(0x65a8)] ^= 1 << rng.randrange(8)
            bad,count = p.run(0x10dd18,[BUF],limit=3000000); instructions += count; assert bad != 0
            corrupt = bytearray(native); corrupt[rng.randrange(0x67fe)] ^= 0x40; save.write_bytes(corrupt)
            seals += 1
        wins = []
        for index in range(15):
            # 111558(seat) stores the wins needed in both profile records.
            p.write(0x43d05f,index,1)
            for seat in (0,1):
                p.write(0x456890+0x20,-1,4); p.write(0x456890+0x50,-1,4)
                _,count = p.run(0x111558,[seat]); instructions += count
                got = [p.read(0x456890+0x30*s+0x20,4) for s in (seat,seat^1)]
                assert list(map(int,ask(f'wins {index}'))) == got,(index,seat,got)
            wins.append(got)
        unlock = 0
        for d6 in (0,1,2):
            for character,value in ((0,0),(0,1),(17,3),(48,1)):
                p.memory[0x43d058:0x43d058+0x98] = factory[0x618c:0x618c+0x98]
                p.write(0x43d0d6,d6,1); p.write(0x43d09f+character,value,1)
                seen,count = p.run(0x1e3f70,[0x43d09f]); instructions += count
                assert int(ask(f'unlock {d6} {character} {value}')[0]) == (d6 == 1)|(seen != 0) << 1; unlock += 1
        o = factory[0x618c:]
        expected = [o[4],o[5],int(o[6] == 1),o[7],o[8],o[9],int.from_bytes(o[12:16],'little',signed=True),
                    o[0x10],o[0x11],o[0x12],o[0x13],o[0x14],o[0x15],int.from_bytes(factory[:4],'little')]
        assert list(map(int,ask('factory'))) == expected == [4,0,0,0,2,100,256,0,32,20,0,32,20,0],expected
        proc.stdin.close(); assert proc.wait() == 0
    report = dict(status='passed',elf_sha256=ORIGINAL,factory_image_sha256=hashlib.sha256(factory).hexdigest(),
                  whole_10dcc0_checksums=crcs,sealed_containers=seals,cpu_match_point_wins=wins,
                  mode_menu_unlock_cases=unlock,factory_options=expected,original_instructions=instructions,
                  scope='Original 10f000 factory image, whole 10dcc0/10dd60/10dd18 checksum container, 111558 match points '
                        'and the 1e3f70 ending-flag count. Memory-card IO and dialogs are replaced by a native file.')
    REPORT.write_text(json.dumps(report,indent=2)+'\n'); print(report)

if __name__ == '__main__':main()
