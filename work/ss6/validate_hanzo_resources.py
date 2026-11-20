#!/usr/bin/env python3
"""Check the shipped Japanese Hanzo character, collision, priority and audio data in both player slots."""
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
from validate_rimururu_resources import SOURCE, SOURCE_HASH, archive, sounds, ending_cues, sha

OUT=ROOT/'outputs/ss6-feasibility/hanzo_resources_validation.json'
LIB=ROOT/'work/ss6/build-native/libss6-runtime.a'
COMPILE=['c++','-std=c++20','-O2','-ffp-contract=off','-I',SOURCE]

def collision_and_depth(tmp,aid):
    cpp=tmp/'priority.cpp';exe=tmp/'priority'
    cpp.write_text(r'''#include "fighter_depth.cpp"
#include "collision.hpp"
#include <iostream>
int main(int argc,char** argv) {
    ss6::CollisionTables tables(argv[1]);ss6::FighterTables depth(argv[1]);
    for(unsigned raw=0;raw<64;++raw) {
        int cls;try{cls=tables.classFor(raw,3);}catch(std::runtime_error&){cls=-1;}
        std::cout<<cls<<" "<<tables.usesAttackDamage(raw,3)<<"\n";
    }
    std::array<unsigned,2> chars,acts,steps;uint32_t a,b;
    while(std::cin>>chars[0]>>acts[0]>>steps[0]>>chars[1]>>acts[1]>>steps[1]>>a>>b) {
        ss6::applyFighterDepthOverride(depth,chars,acts,steps,a,b);std::cout<<a<<" "<<b<<"\n";
    }
}''')
    subprocess.run([*COMPILE,cpp,LIB,'-o',exe],check=True)
    p,a,o,_=round_fixture()
    p.finite_model=True
    classes=[]
    for raw in range(64):
        p.write(0x1e00000,raw,4)
        row,_=p.run(0x153090,[0x1e00000,3])
        val=p.read(row,1);classes.append([val if val<18 else -1,int(p.read(row+1,1)==255)])
    assert p.memory[0x4d7338:0x4d7378]==(ASSETS/'collision_03.bin').read_bytes()
    rules={};i=0
    while True:
        char,act,mode=struct.unpack_from('<BxhBx',p.memory,0x4d3d18+6*i)
        if act==-1:break
        if char==3:rules[act]=mode
        i+=1
    assert len(rules)==34
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
            chars=[0,0];acts=[0,0];steps=[0,0];chars[side]=3;acts[side]=act
            for record in range(aid[4096+act]):
                steps[side]=record
                for z in (depths,depths[::-1]):
                    # Verify row selection with the full search and the mode
                    # independently at every actual animation record.
                    check(chars,acts,steps,z,0x148900 if record==0 else 0x1489c0,
                          [] if record==0 else [actors[side],mode])
    for act in (*rules,0,185):
        check([3,3],[act,666],[0,2],depths[::-1],0x148900,[])
    native=subprocess.check_output([exe,ASSETS],input='\n'.join(inputs)+'\n',text=True)
    got=[list(map(int,line.split())) for line in native.splitlines()]
    assert got[:64]==classes and got[64:]==values
    return dict(class_count=len(classes),class_file_sha256=sha((ASSETS/'collision_03.bin').read_bytes()),
                depth_actions=len(rules),depth_cases=len(values),depth_evidence=['148900','1489c0'])

def main():
    iso=Iso(ISO);rom,hashes=archive(iso,3,'服部半蔵');aid=rom['aid',3]
    ids=[id for id in (*range(166),*range(185,446),*range(489,508),*range(529,755))
         if aid[4096+id] and struct.unpack_from('<h',aid,id*2)[0]>=0]
    keyframes=(232,264,492,495,498,500,502,529,535,538,539,546,552,555,556,568,575,592,617,623,625,629,
               642,648,650,652,664,666,668,670,682,692,702,716,723,724,730,732,741,753)
    frames=[(0,0,i) for i in range(5)]+[(id,min(1,aid[4096+id]-1),i%5) for i,id in enumerate(keyframes)]
    package=OUT.parent/'native-viewer'
    # Archive provenance is checked against the extracted source. Check every
    # character-specific input again at the playback package boundary.
    for name in [*hashes,'collision_03.bin','vs_sounds_03.bin','vs_voice_03.bin']:
        assert (ASSETS/name).read_bytes()==(package/'assets'/name).read_bytes(),name
    stats=Counter();images=[]
    with tempfile.TemporaryDirectory() as temp:
        tmp=Path(temp);cpp=tmp/'draw.cpp';exe=tmp/'draw';cpp.write_text(DRIVER)
        subprocess.run([*COMPILE,cpp,*[SOURCE/(x+'.cpp') for x in ('action_runtime','player_object','judgment',
                         'native_scene','character_draw','character_tiles')],LIB,'-o',exe],check=True)
        for slots,seat in [((0,3,51),1),((3,1,51),0)]:
            verify_slot(fixture(slots),slots,seat,exe,rom,stats,images,ids,frames)
            idle=[r['hash'] for r in images if 0 in r['actions'] and 'costume' in r and f'seat-{seat}-' in r['case']]
            assert len(set(idle))==5
        routing=collision_and_depth(tmp,aid)
        audio=sounds(iso,tmp,3)
        audio['intro_victory_act_cues']=ending_cues(tmp,aid,rom['act',3],3)
    report=dict(status='passed',character='服部半蔵',fighter=3,original_elf_sha256=SOURCE_HASH,archive_sha256=hashes,
                viewer_sha256=sha((package/'ss6-viewer').read_bytes()),runtime_sha256=sha(LIB.read_bytes()),
                packaged_assets_verified=True,body_actions=len(ids),counts=stats,frames=images,collision_priority=routing,audio=audio,
                scope='Japanese ISO archive and sampled GS output, body ACT/JDG data, physical audio lanes and modeled SPU output. These resource checks run independently of player input.')
    OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(dict(stats),len(images),routing,audio['effect_tones'],audio['voice_tones'],audio['stereo_frames'])

if __name__=='__main__':main()
