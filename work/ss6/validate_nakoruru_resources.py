#!/usr/bin/env python3
"""Compare both uploaded fighter slots with the unmodified SLPS_255.59 ACT, JDG and GS submissions."""
from collections import Counter
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import struct
import subprocess
import tempfile

from character_tiles_oracle import ROOT, ASSETS, fixture
from extract_collision_tables import SOURCE_HASH
from extract_resources import recover
from inspect_iso import Iso, Elf
from validate_native_scene import compare

OUT=ROOT/'outputs/ss6-feasibility/nakoruru_resources_validation.json'
ISO=Path('/Users/xargin/Downloads/ps2/Samurai Spirits - Tenka-ichi Kenkakuden (Japan).iso')
# Use the actual player object to populate character/clock/palette identity.
DRIVER=r'''
#include "player_object.hpp"
#include "judgment.hpp"
#include "native_scene.hpp"
#include <bit>
#include <iostream>
using namespace ss6;
void out(const auto& v) {std::cout.write(reinterpret_cast<const char*>(&v),sizeof(v));}
int main(int argc,char** argv) {
    std::array<unsigned,3> ids{unsigned(std::stoi(argv[2])),unsigned(std::stoi(argv[3])),51};
    std::array<ActionBank,2> banks{ActionBank(argv[1],true,ids[0]),ActionBank(argv[1],true,ids[1])};
    std::array<JudgmentData,2> boxes{JudgmentData(argv[1],ids[0]),JudgmentData(argv[1],ids[1])};
    NativeScene scene(argv[1],ids);EffectPalettes palettes{};std::array<uint16_t,1024> tones{};
    StageCamera camera;int slot,id,step;char op;
    while(std::cin>>op>>slot>>id>>step) {
        auto& bank=banks.at(slot);
        if(op=='r'){
            auto& r=bank.get(id).record(step);out(r.sourceRecord);out(r.headerFlags);out(r.parts);out(r.judgmentRefs);
            out(r.judgmentFlags);out(int16_t(r.motion.kind));out(r.motion.values);out(r.effectCommand);
            out(r.duration);out(r.soundCommand);out(r.endKind);
            auto judgments=boxes[slot].forRecord(r);out(uint32_t(judgments.size()));
            for(auto& j:judgments){out(j.index);out(j.metadata);out(j.auxiliary);out(j.x1);out(j.y1);out(j.x2);out(j.y2);out(j.tail);}
        }else{
            PlayerObject body(bank,0);body.resourceSlot0c=slot;body.field20=step%4;
            if(op=='c'){int costume;std::cin>>costume;body.field20=0x40000u+unsigned(costume);}
            auto row=body.childParentWords();ObjectDrawQueue queue;queue.count=1;
            std::copy(row.begin(),row.end(),queue.slots[0].begin());auto& o=queue.slots[0];
            o[9]=id;o[10]=step;o[14]=0x10000000|(slot?0x80000:0);o[16]=std::bit_cast<uint32_t>(320.f);
            o[35]=0xffffffff;queue.sort();std::vector<uint8_t> frame(640*448*4);
            for(unsigned i=0;i<frame.size();i+=4)std::copy_n(std::array<uint8_t,4>{17,31,43,255}.begin(),4,frame.begin()+i);
            scene.paint(queue,{camera,{0,0},-2,0},palettes,tones,frame,{});
            for(int x:{0,0,200,1})out(x);for(float x:{camera.projectionX,camera.projectionY,camera.depth,camera.depthOffset,camera.verticalOffset})out(x);
            for(int x:{0,0,-2,0})out(x);out(palettes[2]);out(tones);out(o);out(0);
            std::cout.write(reinterpret_cast<char*>(frame.data()),frame.size());
        }
    }
}
'''

def verify_slot(p,slots,slot,program,original,stats,images,extra_ids=(),extra_frames=()):
    resource=slots[slot]
    aid=original['aid',resource]
    act=original['act',resource]
    jdg=original['jdg',resource]
    base=0x1000000+slot*0x40000
    p.memory[base:base+len(jdg)]=jdg
    p.write(0x4751e0+slot*4,base,4)
    obj=0x1e10000
    p.write(obj+0xc,slot,4)
    ids=[0,4,10,44,84,185,186,187,188,189,190,191,192,193,194,195,196,*range(197,205),*range(209,223),338,339,342,343,378,430,492,495,497]
    if resource==1:
        ids+=list(range(38,44))+[162,163,554,555,556,557,558,715,716]
    ids=sorted(set(ids).union(extra_ids))
    lines=[];expected=bytearray()
    for id in ids:
        for step in range(aid[4096+id]):
            lines.append(f'r {slot} {id} {step}')
            ptr,count=p.run(0x1212c0,[slot,id,step])
            stats['ee_instructions']+=count
            resident=p.read(0x4751b0+slot*4,4)
            raw=bytes(p.memory[ptr:ptr+60])
            assert raw==act[ptr-resident:ptr-resident+60]
            expected+=struct.pack('<I',(ptr-resident)//60)+raw[:54]+raw[56:]
            _,n=p.run(0x152fd8,[obj+0xb8,slot,id,step]);stats['ee_instructions']+=n
            count=p.read(obj+0xba,1);expected+=struct.pack('<I',count)
            for nth in range(count):
                ref,n=p.run(0x11db40,[obj,nth]);stats['ee_instructions']+=n
                expected+=struct.pack('<I',(ref-base)//16)+p.memory[ref:ref+16]
            stats['action_records']+=1;stats['judgment_boxes']+=count
    # Draw the first attacking frame for both stand/crouch and jump heavy;
    # include the introduction and injured body to exercise unrelated PILs.
    frames=[(0,0),(492,3),(495,1),(338,1)]
    for id in (189,190,195,196,215,216):
        start=struct.unpack_from('<h',aid,id*2)[0]
        for step in range(aid[4096+id]):
            raw=act[(start+step)*60:(start+step+1)*60];n=struct.unpack_from('<H',raw,30)[0]&7
            refs=struct.unpack_from('<8h',raw,14)
            if any(struct.unpack_from('<I',jdg,16*r)[0]>>26 in range(10,46) for r in refs[:n]):
                frames.append((id,step));break
    frames=[(id,step,None) for id,step in frames]+list(extra_frames)
    for id,step,costume in frames:
        lines.append(f'p {slot} {id} {step}' if costume is None else f'c {slot} {id} {step} {costume}')
    proc=subprocess.run([program,ASSETS,*map(str,slots[:2])],input=('\n'.join(lines)+'\n').encode(),capture_output=True)
    if proc.returncode:raise RuntimeError(proc.stderr)
    assert proc.stdout[:len(expected)]==expected, (slots,slot,'ACT/JDG bytes')
    data=BytesIO(proc.stdout[len(expected):])
    for id,step,costume in frames:
        item=compare(p,data,stats,f'slots-{slots[0]}-{slots[1]}-seat-{slot}-{id}-{step}')
        assert item['records']==1
        if costume is not None:item['costume']=costume
        images.append(item)
    assert not data.read()

def main():
    iso=Iso(ISO);raw=iso.read('/SLPS_255.59')
    assert sha256(raw).hexdigest()==SOURCE_HASH
    directory=iso.by_path['/SAM_DATA.BIN'];entries={r['name']:r for r in recover(Elf(raw),directory['size'])}
    original={};assets={}
    for k in ('act','aid','chr','idx','jdg','map','pil'):
        for c in (0,1):
            filename=f'{k}_{c:02d}.bin';r=entries[filename]
            data=iso.read_at(directory['lba']*iso.block+r['offset'],r['size']);assert data==(ASSETS/filename).read_bytes()
            original[k,c]=data;assets[filename]=sha256(data).hexdigest()
    stats=Counter();images=[]
    with tempfile.TemporaryDirectory() as tmp:
        src=Path(tmp)/'probe.cpp';src.write_text(DRIVER);exe=src.with_suffix('')
        names=['action_runtime','player_object','judgment','native_scene','character_draw','character_tiles']
        subprocess.run(['c++','-std=c++20','-ffp-contract=off','-O2','-I',ROOT/'src',src,*[ROOT/f'src/{x}.cpp' for x in names],
                        ROOT/'work/ss6/build-native/libss6-runtime.a','-o',exe],check=True)
        for slots in ((0,1,51),(1,0,51)):
            p=fixture(slots)
            for table in (0x4d4bb0,0x4c3728):
                ptr=p.read(table+4,4);assert bytes(p.memory[ptr:ptr+16]).split(b'\0')[0].decode('cp932')=='ナコルル'
            for slot in (0,1):verify_slot(p,slots,slot,exe,original,stats,images)
    summary=dict(all_passed=True,character='ナコルル',index=1,elf_sha256=SOURCE_HASH,assets=assets,counts=dict(stats),
                 frames=images,scope='Original AID/ACT/JDG and GS character packets against native two-seat renderer, covering original ordinary poses and active hitboxes.')
    OUT.write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    print(stats,'frames',len(images))

if __name__=='__main__':main()
