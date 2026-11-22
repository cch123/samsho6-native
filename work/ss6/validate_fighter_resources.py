#!/usr/bin/env python3
"""Check a shipped Japanese fighter's character, collision, priority and audio data in both player slots.

Parameterized form of validate_mina_resources.py (pipeline step F).
Usage: validate_fighter_resources.py --fighter 26
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import struct
import subprocess
import tempfile

from character_tiles_oracle import fixture
from inspect_iso import Iso
from round_entry_oracle import fixture as round_fixture
from validate_nakoruru_resources import ASSETS, DRIVER, ISO, ROOT, verify_slot
from validate_rimururu_resources import SOURCE, SOURCE_HASH, sounds, ending_cues, sha
from fighter_roster import FIGHTERS as FIGHTERS_ROSTER, LOGIC, SELECTABLE
import validate_rimururu_resources as rimururu

def spec_for(n):
    """Cases derived from the native roster and the pinned original tables."""
    roster=FIGHTERS_ROSTER[LOGIC.get(n,n)]  # 42 runs as 1 (148df0); its bank keeps resource 42
    depth=(ASSETS/'depth_rules.bin').read_bytes()
    rules=sum(1 for i in range(0,len(depth),6) if depth[i]==n and struct.unpack_from('<h',depth,i+2)[0]!=-1)
    other=1 if n==0 else 0
    return dict(ranges=[(a,b+1) for a,b in roster['held']] or [(0,166),(185,446)],depth_rules=rules,
                lineups=(((other,n,51),1),((n,other if other else 1,51),0)))
OUT_DIR=ROOT/'outputs/ss6-feasibility'
LIB=ROOT/'work/ss6/build-native/libss6-runtime.a'
COMPILE=['c++','-std=c++20','-O2','-ffp-contract=off','-I',SOURCE]

def collision_and_depth(tmp,aid,n,rule_count):
    cpp=tmp/'priority.cpp';exe=tmp/'priority'
    cpp.write_text(r'''#include "fighter_depth.cpp"
#include "collision.hpp"
#include <iostream>
int main(int argc,char** argv) {
    ss6::CollisionTables tables(argv[1]);ss6::FighterTables depth(argv[1]);
    for(unsigned raw=0;raw<64;++raw) {
        int cls;try{cls=tables.classFor(raw,FIGHTER);}catch(std::runtime_error&){cls=-1;}
        std::cout<<cls<<" "<<tables.usesAttackDamage(raw,FIGHTER)<<"\n";
    }
    std::array<unsigned,2> chars,acts,steps;uint32_t a,b;
    while(std::cin>>chars[0]>>acts[0]>>steps[0]>>chars[1]>>acts[1]>>steps[1]>>a>>b) {
        ss6::applyFighterDepthOverride(depth,chars,acts,steps,a,b);std::cout<<a<<" "<<b<<"\n";
    }
}''')
    subprocess.run([*COMPILE,f'-DFIGHTER={n}',cpp,LIB,'-o',exe],check=True)
    p,a,o,_=round_fixture()
    p.finite_model=True
    classes=[]
    for raw in range(64):
        p.write(0x1e00000,raw,4)
        row,_=p.run(0x153090,[0x1e00000,n])
        val=p.read(row,1);classes.append([val if val<18 else -1,int(p.read(row+1,1)==255)])
    assert p.memory[0x4d7278+64*n:0x4d7278+64*(n+1)]==(ASSETS/f'collision_{n:02}.bin').read_bytes()
    rules={};i=0
    while True:
        char,act,mode=struct.unpack_from('<BxhBx',p.memory,0x4d3d18+6*i)
        if act==-1:break
        if char==n:rules[act]=mode
        i+=1
    assert len(rules)==rule_count
    actors=[a,a+0xf2c];bodies=[o,o+0x1000]
    for index in (0,1):
        p.write(actors[index],bodies[index],4)
        p.write(actors[index]+0xa24,index,4)
    inputs=[];values=[]
    def check(chars,acts,steps,initial,entry,args):
        for i in range(2):
            p.write(actors[i]+0xa10,chars[i],4)
            for off,value in ((0x24,acts[i]),(0x28,steps[i]),(0xb0,initial[i])):
                p.write(bodies[i]+off,value,4)
        p.run(entry,args,limit=30000)
        inputs.append(' '.join(map(str,(*[x for i in range(2) for x in (chars[i],acts[i],steps[i])],*initial))))
        values.append([p.read(obj+0xb0,4) for obj in bodies])
    fbits=lambda v:struct.unpack('<I',struct.pack('<f',v))[0]
    depths=[fbits(27),fbits(33)]
    for side in (0,1):
        for act,mode in rules.items():
            chars=[0,0];acts=[0,0];steps=[0,0];chars[side]=n;acts[side]=act
            for record in range(aid[4096+act]):
                steps[side]=record
                for z in (depths,depths[::-1]):
                    # Verify row selection with the full search and the mode
                    # independently at every actual animation record.
                    check(chars,acts,steps,z,0x148900 if record==0 else 0x1489c0,
                          [] if record==0 else [actors[side],mode])
    for act in (*rules,0,185):
        check([n,n],[act,max(rules) if rules else 185],[0,2],depths[::-1],0x148900,[])
    native=subprocess.check_output([exe,ASSETS],input='\n'.join(inputs)+'\n',text=True)
    got=[list(map(int,line.split())) for line in native.splitlines()]
    assert got[:64]==classes and got[64:]==values
    return dict(class_count=len(classes),class_file_sha256=sha((ASSETS/f'collision_{n:02}.bin').read_bytes()),
                depth_actions=len(rules),depth_cases=len(values),depth_evidence=['148900','1489c0'])

def archive(iso,character):
    """rimururu.archive for any fighter; returns the 4d4bb0/4c3728 names too."""
    raw=iso.read('/SLPS_255.59')
    assert sha(raw)==SOURCE_HASH
    elf=rimururu.Elf(raw)
    names=[]
    for addr in (0x4d4bb0+4*character,0x4c3728+4*character):
        ptr=struct.unpack_from('<I',raw,elf.offset(addr))[0]
        names.append(raw[elf.offset(ptr):elf.offset(ptr)+32].split(b'\0')[0].decode('cp932'))
    container=iso.by_path['/SAM_DATA.BIN']
    entries={e['name']:e for e in rimururu.recover(elf,container['size'])}
    rom={};hashes={}
    for kind in ('aid','act','jdg','pil','idx','chr','map','pal_all'):
        name=f'{kind}_{character:02}.bin' if kind!='pal_all' else 'pal_all.bin'
        e=entries[name]
        data=iso.read_at(container['lba']*iso.block+e['offset'],e['size'])
        assert data==(ASSETS/name).read_bytes()
        rom[kind,character]=data;hashes[name]=sha(data)
    return rom,hashes,names

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--fighter',type=int,required=True);n=ap.parse_args().fighter
    spec=spec_for(n);out=ROOT/f'outputs/ss6-feasibility/fighter_{n:02}_resources_validation.json'
    iso=Iso(ISO);rom,hashes,names=archive(iso,n);aid=rom['aid',n]
    ids=[id for lo,hi in spec['ranges'] for id in range(lo,hi) if aid[4096+id] and struct.unpack_from('<h',aid,id*2)[0]>=0]
    # Every n-th admitted body ACT above the shared common block, about 20 in all.
    sample=[i for i in ids if i>=185];keyframes=sample[::max(1,len(sample)//20)]
    frames=[(0,0,i) for i in range(5)]+[(id,min(1,aid[4096+id]-1),i%5) for i,id in enumerate(keyframes)]
    package=OUT_DIR/'native-viewer'
    for name in [*hashes,f'collision_{LOGIC.get(n,n):02}.bin',f'vs_sounds_{n:02}.bin',f'vs_voice_{n:02}.bin']:
        assert (ASSETS/name).read_bytes()==(package/'assets'/name).read_bytes(),name
    stats=Counter();images=[]
    with tempfile.TemporaryDirectory() as temp:
        tmp=Path(temp);cpp=tmp/'draw.cpp';exe=tmp/'draw';cpp.write_text(DRIVER)
        subprocess.run([*COMPILE,cpp,*[SOURCE/(x+'.cpp') for x in ('action_runtime','player_object','judgment',
                         'native_scene','character_draw','character_tiles')],LIB,'-o',exe],check=True)
        for slots,seat in spec['lineups']:
            verify_slot(fixture(slots),slots,seat,exe,rom,stats,images,ids,frames)
            idle=[r['hash'] for r in images if 0 in r['actions'] and 'costume' in r and f'seat-{seat}-' in r['case']]
            # Five costume colors per selectable fighter; the arcade boss Makai Gaoh (43, no grid cell) draws one
            # (the per-image comparison against the original above already passed for all five).
            assert len(set(idle))==(5 if n in SELECTABLE else 1),(len(set(idle)),len(idle))
        routing=collision_and_depth(tmp,aid,LOGIC.get(n,n),spec['depth_rules'])  # the profile is the logic resource (11d5b0)
        audio=sounds(iso,tmp,n)
        audio['intro_victory_act_cues']=ending_cues(tmp,aid,rom['act',n],n)
    report=dict(status='passed',character=names[0],short_name=names[1],fighter=n,original_elf_sha256=SOURCE_HASH,archive_sha256=hashes,
                viewer_sha256=sha((package/'ss6-viewer').read_bytes()),runtime_sha256=sha(LIB.read_bytes()),
                packaged_assets_verified=True,body_actions=len(ids),counts=stats,frames=images,collision_priority=routing,audio=audio,
                scope='Japanese ISO archive and sampled GS output, body ACT/JDG data, physical audio lanes and modeled SPU output. These resource checks run independently of player input.')
    out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(dict(stats),len(images),routing,audio['effect_tones'],audio['voice_tones'],audio['stereo_frames'])

if __name__=='__main__':main()
