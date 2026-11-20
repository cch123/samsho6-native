#!/usr/bin/env python3
"""Compare the Japanese Rimururu assets, bank 02 hit classes, fighter drawing, and playing audio."""
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import struct
import subprocess
import tempfile

from character_tiles_oracle import fixture
from extract_combat_sound_bank import extract, MAGIC
from extract_collision_tables import SOURCE_HASH
from extract_resources import recover
from inspect_iso import Elf,Iso
from validate_battle_sound import events_at, sound_oracle
from validate_combat_audio import OriginalDriver
from validate_nakoruru_resources import ASSETS,DRIVER,ISO,ROOT,verify_slot
from validate_select_audio import DRIVER as AUDIO_DRIVER

OUT=ROOT/'outputs/ss6-feasibility/rimururu_resources_validation.json'
SOURCE=ROOT/'src'
sha=lambda b:sha256(b).hexdigest()


def archive(iso,character=2,expected_name='リムルル'):
    raw=iso.read('/SLPS_255.59')
    assert sha(raw)==SOURCE_HASH
    elf=Elf(raw)
    for addr in (0x4d4bb0+4*character,0x4c3728+4*character):
        ptr=struct.unpack_from('<I',raw,elf.offset(addr))[0]
        name=raw[elf.offset(ptr):elf.offset(ptr)+32].split(b'\0')[0]
        assert name.decode('cp932')==expected_name
    container=iso.by_path['/SAM_DATA.BIN']
    entries={e['name']:e for e in recover(elf,container['size'])}
    rom={}
    hashes={}
    for kind in ('aid','act','jdg','pil','idx','chr','map','pal_all'):
        name=f'{kind}_{character:02}.bin' if kind!='pal_all' else 'pal_all.bin'
        e=entries[name]
        data=iso.read_at(container['lba']*iso.block+e['offset'],e['size'])
        assert data==(ASSETS/name).read_bytes()
        rom[kind,character]=data
        hashes[name]=sha(data)
    return rom,hashes


def semantics(program):
    p=fixture((0,2,51))
    table=(ASSETS/'collision_02.bin').read_bytes()
    assert table==p.memory[0x4d72f8:0x4d7338]
    commands=[]
    for raw in range(64):
        p.write(0x1e00000,raw,4)
        entry,_=p.run(0x153090,[0x1e00000,2])
        category=p.read(entry,1)
        uses_damage=int(p.read(entry+1,1)==255)
        commands.append((raw,category if category<18 else -1,uses_damage))
    native=subprocess.check_output([program,ASSETS],text=True)
    assert [tuple(map(int,row.split())) for row in native.splitlines()]==commands
    rows=[]
    for i in range((0x4d4b58-0x4d3d18)//6):
        ch,act,mode=struct.unpack_from('<Bx h Bx',p.memory,0x4d3d18+6*i)
        if act==-1:break
        if ch==2:rows.append((act,mode))
    assert not rows and act==-1
    return dict(raw_types=len(commands),original_calls='153090',depth_table_rows=i,custom_depth_entries=rows,
                table_sha256=sha(table))


def ending_cues(folder,aid,act,character=2):
    # 14ab80 and 169810 choose different victory ACTs according to standing
    # health, weapon and deciding round. Feed the unaltered body commands
    # into the original 1e8298 dispatcher for both possible winners.
    p=sound_oracle().probe
    cpp=folder/'cues.cpp';exe=folder/'cues'
    cpp.write_text('''#include "sound_selection.hpp"
#include <iostream>
int main(int argc,char** argv) {
    ss6::GameRandom rng;ss6::SoundSelection s(argv[1]);unsigned seat,cmd;
    while(std::cin>>seat>>cmd) {
        s.beginFrame();s.act(cmd,seat,std::stoi(argv[2]),0,3,0,rng);
        for(auto x:s.events())std::cout<<int(x.kind)<<" "<<x.bank<<" "<<x.tone<<" ";
        std::cout<<"\\n";
    }
}''')
    subprocess.run(['c++','-std=c++20','-O2','-I',SOURCE,cpp,SOURCE/'sound_selection.cpp',
                    SOURCE/'game_random.cpp','-o',exe],check=True)
    commands=[];expected=[];cues=[]
    for id in (492,*range(495,503)):
        start=struct.unpack_from('<h',aid,2*id)[0]
        for i in range(aid[4096+id]):
            command=struct.unpack_from('<h',act,60*(start+i)+56)[0]
            if not command:continue
            for seat in (0,1):
                events=[];p.run(0x1e8298,[seat,command,character],limit=16000,observe=events_at(p,events))
                commands.append(f'{seat} {command}')
                expected.append([v for item in events for v in item])
                cues.append(dict(seat=seat,body_act=id,record=i,command=command,issued=events))
    got=subprocess.check_output([exe,ASSETS,str(character)],input='\n'.join(commands)+'\n',text=True)
    assert [list(map(int,line.split())) for line in got.splitlines()]==expected
    return cues


def sounds(iso,folder,character=2):
    o=OriginalDriver(iso)
    groups={}
    for prefix,stem,stride in (('BVOICE2','vs_sounds',0x250),('BVOICE1','vs_voice',0x110)):
        for id in (0,character):
            raw=extract(iso,[(prefix,id,stride)])[len(MAGIC):]
            if id:assert raw==(ASSETS/f'{stem}_{id:02}.bin').read_bytes()
            groups[id,prefix]=(raw[:stride],raw[stride:])
    expected=[]
    commands=[]
    def op(name,*args):
        command=' '.join(map(str,(name,*args)))
        r=0
        if name=='S':r=o.call(0x212fa0,*args)
        elif name=='V':r=o.call(0x213378,*args)
        elif name=='G':o.call(0x213be8,*args)
        elif name=='R':o.render(args[0])
        elif name=='T':o.call(0x213660)
        elif name=='B':
            for seat,id in enumerate(args):
                o.ee.write(0x59d01c+4*seat,id,4)
                data=groups[id,'BVOICE2'][1]
                at=(0x5b010,0xb1010)[seat]
                o.spu[at:at+len(data)]=data
                data=groups[id,'BVOICE1'][1]
                at=0x1466980+0x76800*seat
                o.ee.memory[at:at+len(data)]=data
        commands.append(command);expected.append(r)
        return r
    voiceHeader,soundsHeader=(groups[character,k][0] for k in ('BVOICE1','BVOICE2'))
    voiceCount=struct.unpack_from('<I',voiceHeader,4)[0]
    effectCount=struct.unpack_from('<I',soundsHeader,4)[0]
    # Cover every tone on both physical lanes. In a mirror match, the original
    # streamed-voice lookup chooses the first matching character.
    lineups=((character,0),(0,character),(character,character))
    for lineup in lineups:
        op('B',*lineup)
        for seat,id in enumerate(lineup):
            if id!=character:continue
            for tone in range(effectCount):
                channel=op('S',seat+1,tone)
                start=struct.unpack_from('<I',soundsHeader,20+8*tone)[0]
                assert o.registers[(1+2*channel)|0x2040]==(0x5b010,0xb1010)[seat]+start
                op('R',613);op('G',1);op('R',7)
            for tone in range(voiceCount):
                slot=o.ee.read(0x59d008,4)
                r=op('V',character,tone)
                # 213378 keys character 50's and character 29's first eight lines
                # on a short physical channel instead of the streamed-voice slot.
                if character==50 or (character==29 and tone<8):assert r>=0
                else:assert r==-1 and o.ee.read(0x15539a0+4*slot,4)==lineup.index(character)
                for _ in range(3):op('T')
                op('R',811);op('G',2);op('R',7)
    cpp=folder/'audio.cpp';cpp.write_text(AUDIO_DRIVER);exe=folder/'audio';pcm=folder/'pcm'
    subprocess.run(['c++','-std=c++20','-O2','-I',SOURCE,cpp,SOURCE/'combat_audio.cpp',SOURCE/'combat_music.cpp',
                    SOURCE/'combat_sound_bank.cpp','-o',exe],check=True)
    actual=subprocess.check_output([exe,ASSETS,pcm],input='\n'.join(commands)+'\n',text=True)
    assert list(map(int,actual.split()))==expected
    assert pcm.read_bytes()==o.pcm
    return dict(effect_tones=effectCount,voice_tones=voiceCount,seat_binds=lineups,
                sound_bank_sha256=sha((ASSETS/f'vs_sounds_{character:02}.bin').read_bytes()),
                voice_bank_sha256=sha((ASSETS/f'vs_voice_{character:02}.bin').read_bytes()),
                pcm_sha256=sha(o.pcm),stereo_frames=len(o.pcm)//4,ee_instructions=o.ee_steps,iop_instructions=o.iop_steps)


def main():
    iso=Iso(ISO)
    original,assets=archive(iso)
    aid=original['aid',2]
    ids=[i for i in (*range(166),*range(185,446),*range(489,508),*range(529,639))
         if aid[4096+i] and struct.unpack_from('<h',aid,2*i)[0]>=0]
    frames=[(0,0,n) for n in range(5)]+[(act,step,n%5) for n,(act,step) in enumerate([
        (232,1),(264,1),(495,5),(497,5),(529,1),(531,1),(539,1),(547,1),(559,1),(573,1),
        (576,0),(581,1),(587,1),(595,1),(601,1),(614,1),(623,1),(634,1),(636,1),(637,1),
        (769,0),(773,0),(774,0),(775,0)])]
    stats=Counter();images=[]
    with tempfile.TemporaryDirectory() as td:
        tmp=Path(td);cpp=tmp/'draw.cpp';cpp.write_text(DRIVER);exe=tmp/'draw'
        compile=['c++','-std=c++20','-O2','-ffp-contract=off','-I',SOURCE]
        subprocess.run([*compile,cpp,*[SOURCE/f'{x}.cpp' for x in ('action_runtime','player_object','judgment','native_scene','character_draw','character_tiles')],
                        ROOT/'work/ss6/build-native/libss6-runtime.a','-o',exe],check=True)
        for slots,seat in [((0,2,51),1),((2,1,51),0)]:
            verify_slot(fixture(slots),slots,seat,exe,original,stats,images,ids,frames)
        # Every original palette slot must produce a distinct visible idle frame.
        for seat in range(2):
            palettes=[r for r in images if 0 in r['actions'] and 'costume' in r and f'seat-{seat}-' in r['case']]
            assert len({r['hash'] for r in palettes})==5
        cpp=tmp/'class.cpp';exe=tmp/'class'
        cpp.write_text('#include "collision.hpp"\n#include <iostream>\nint main(int argc,char** argv){ss6::CollisionTables c(argv[1]);for(unsigned n=0;n<64;++n){int k;try{k=c.classFor(n,2);}catch(std::runtime_error&){k=-1;}std::cout<<n<<" "<<k<<" "<<c.usesAttackDamage(n,2)<<"\\n";}}')
        subprocess.run([*compile,cpp,SOURCE/'collision.cpp',ROOT/'work/ss6/build-native/libss6-runtime.a','-o',exe],check=True)
        collision=semantics(exe)
        audio=sounds(iso,tmp)
        audio['intro_victory_act_cues']=ending_cues(tmp,aid,original['act',2])
    report=dict(status='passed',character='リムルル',id=2,elf=SOURCE_HASH,archive_sha256=assets,
                counts=dict(stats),checked_body_actions=len(ids),frame_count=len(images),frames=images,
                collision=collision,audio=audio,
                scope='Japanese disc extents, original EE ACT/JDG and GS character packets including five selectable colors, 02 in either seat. Original EE/IRX sound requests, modeled SPU2 output and native PCM. Each sampled animation record and effect tone is a resource comparison; gameplay input coverage is separate.')
    OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(dict(stats),len(images),audio)

if __name__=='__main__':main()
