#!/usr/bin/env python3
"""Compare notices in the production versus scene against real Japanese GS submissions."""
import hashlib
import itertools
import json
from pathlib import Path
import struct
import subprocess
import tempfile
import wave
import numpy as np
from PIL import Image
from validate_stage_item_notices import LIB,ASSETS,ROOT,ELF,PIN,original,atlas,digest,raster
from validate_selected_combat import prefix
from validate_combat_audio import OriginalDriver,Iso,ISO
from validate_combat_stage import SourceStage,PROJECTION

OUT=ROOT/'outputs/ss6-feasibility'
BUILD=ROOT/'work/ss6/build-native'
DRIVER=r'''
#include "combat_stage.hpp"
#include "local_versus.hpp"
#include "native_scene.hpp"
#include <bit>
#include <fstream>
#include <iomanip>
#include <iostream>
using namespace ss6;
int main(int argc,char** argv){try{
    LocalVersus session(argv[1],99,VersusMode::Console,{},true);
    CombatStage stage(argv[1]);NativeScene scene(argv[1],{0,1,51});
    std::array<unsigned,2> prev{},held{};int tick=0,capture;
    std::cout<<std::setprecision(9);
    while(std::cin>>held[0]>>held[1]>>capture){
        const auto& old=session.match();auto c=old.battle().camera;auto delta=old.battle().gauges.delta46a908;
        std::array<int,2> x{-1,-1},hp{};
        for(unsigned i=0;i<2;++i){
            const auto& b=old.battle();hp[i]=old.fighter(i).actor.fieldA30;
            for(auto task:old.fighter(i).storage.objectTasks)if(task){
                const auto& o=b.entry.tasks.objects.at(b.entry.tasks.tasks.at(task-1)[7]-1);
                if(o[0xcc/4]!=4)continue;
                if(std::bit_cast<float>(o[0x44/4])<=0)x[i]=int(std::bit_cast<float>(o[0x40/4]));
                break;
            }
        }
        std::array<NormalizedPadSample,2> pads;
        for(unsigned i=0;i<2;++i)pads[i]={held[i],held[i]&~prev[i]};
        prev=held;session.tick(pads);++tick;if(!capture)continue;
        const auto& m=session.match();const auto& b=m.battle();const auto& g=b.gauges;
        unsigned se=0;for(auto e:m.soundEvents())if(e.kind==BattleSoundKind::Sample&&e.bank==0&&e.tone==65)++se;
        unsigned depth=100,fx=0;
        if(capture==2){
            std::vector<uint8_t> pixels(640*448*4);depth=stage.paint(m.combatStage(),g.paletteTones,pixels);
            CharacterDrawContext context{b.camera,{g.words910[2],g.words910[3]},g.focus46a948};
            scene.paint(m.objectDraws(),context,b.paletteState,g.paletteTones,pixels,[&](const auto&){++fx;},m.battleBackdropColor());
            fx+=m.effectDraws().size();
            std::ofstream dest(std::filesystem::path(argv[2])/(std::to_string(tick)+".base"),std::ios::binary);
            dest.write(reinterpret_cast<const char*>(pixels.data()),pixels.size());
        }
        std::cout<<tick<<' '<<delta<<' '<<x[0]<<' '<<x[1];
        for(float f:{c.projectionX,c.projectionY,c.depth,c.depthOffset,c.verticalOffset})std::cout<<' '<<f;
        for(unsigned i=0;i<2;++i){const auto& f=m.fighter(i);std::cout<<' '<<hp[i]<<' '<<f.actor.fieldA30<<' '<<int(f.body.timeline.motion().x);}
        std::cout<<' '<<se<<' '<<depth<<' '<<fx<<' '<<b.itemNotices.draws().size();
        for(const auto& layer:m.combatStage().layers)std::cout<<' '<<layer.step;
        for(const auto& q:b.itemNotices.draws())std::cout<<' '<<q.left<<' '<<q.top<<' '<<q.right<<' '<<q.bottom<<' '<<q.u<<' '<<q.v<<' '<<q.alpha;
        std::cout<<'\n';
    }
}catch(const std::exception& e){std::cerr<<e.what();return 1;}}
'''
P1=[(32,128,64),(5,0,0),(1,0,1024),(75,0,0),*(([(1,256,0),(25,0,0)])*3),(1,256,0),(3637,0,0),(27,128,0),(1,2304,0),(76,0,0)]
P2=[(32,128,64),(5,0,0),(1,1024,0),(513,0,0),(42,128,0),(1051,0,0),(23,0,64),(1,0,2304),(76,0,0)]
ARROWS=[(1,136,72),(150,0,0),(1,128,256),(36,128,0),(1,0,0),(1,256,0),(55,0,0)]

def pads_for(groups,items):
    a=prefix((0,1))
    if items:a[265][1]=128
    for count,p1,p2 in groups:a.extend([(p1,p2)]*count)
    return a

def trace(exe,base,groups,begin,pictures,items):
    inputs=pads_for(groups,items)
    words=''.join(f'{a} {b} {2 if t in pictures else int(t>=begin)}\n' for t,(a,b) in enumerate(inputs,1))
    got=subprocess.run([exe,ASSETS,base],input=words,text=True,capture_output=True,check=True)
    return inputs,[list(map(float,row.split())) for row in got.stdout.splitlines()]

def actual_scene(viewer,inputs,base,tick):
    replay=base/'source.pad';scene=base/'viewer.rgba'
    groups=itertools.groupby(map(tuple,inputs[:tick]))
    replay.write_text(''.join(f'{sum(1 for _ in same)} {a} {b}\n' for (a,b),same in groups))
    subprocess.run([viewer,'--assets',ASSETS,'--mode','select','--round-time','99','--match-replay',replay,'--dump',scene],check=True,stdout=subprocess.DEVNULL)
    data=scene.read_bytes();assert struct.unpack_from('<II',data)==(640,448)
    return np.frombuffer(data,dtype=np.uint8,offset=8).reshape(448,640,4)

def actual_audio(viewer,inputs,base,tick):
    # Silence just the encoded samples in a temporary copy of common tone 65.
    # Retain its entire duration, SPU channel allocation, flags and volume.
    muted=base/'muted';muted.mkdir(exist_ok=True)
    if not (muted/'combat_sound_bank.bin').exists():
        for path in ASSETS.iterdir():
            if path.name!='combat_sound_bank.bin':(muted/path.name).symlink_to(path)
        data=bytearray((ASSETS/'combat_sound_bank.bin').read_bytes());word,off=struct.unpack_from('<II',data,8+16+8*65)
        start=8+0x250+off
        for i in range(start,start+(word>>16),16):data[i+2:i+16]=bytes(14)
        (muted/'combat_sound_bank.bin').write_bytes(data)
    replay=base/'sound.pad';groups=itertools.groupby(map(tuple,inputs))
    replay.write_text(''.join(f'{sum(1 for _ in same)} {a} {b}\n' for (a,b),same in groups))
    audio=[]
    for assets in (ASSETS,muted):
        wav=base/'viewer.wav';subprocess.run([viewer,'--assets',assets,'--mode','select','--round-time','99','--match-replay',replay,'--audio-out',wav],check=True,stdout=subprocess.DEVNULL)
        with wave.open(str(wav),'rb') as f:
            assert f.getparams()[:4]==(2,2,48000,800*len(inputs))
            audio.append(np.frombuffer(f.readframes(f.getnframes()),dtype='<i2').reshape(-1,2))
    sound,silent=audio;offset=(tick-1)*800
    assert np.array_equal(sound[:offset],silent[:offset])
    orig=OriginalDriver(Iso(ISO));channel=orig.call(0x212fa0,0,65);voice=orig.voices[channel];samples=[]
    while (v:=voice.next(orig.table)) is not None:samples.append(v)
    span=len(samples);origSamples=np.asarray(samples,dtype=np.int32)[:,None]
    dry=silent[offset:offset+span].astype(np.int32);heard=sound[offset:offset+span].astype(np.int32)
    # Invert the SPU's final signed master-volume rounding on the muted
    # output. The original audio register programming supplies the dry voice.
    low=-((-dry*32768)//32766);high=-((-(dry+1)*32768)//32766)-1
    low[low<=-32768]=-1000000;high[high>=32767]=1000000
    lo=np.clip(low+origSamples,-32768,32767)*32766//32768
    hi=np.clip(high+origSamples,-32768,32767)*32766//32768
    assert ((lo<=heard)&(heard<=hi)).all(),(tick,int(np.sum((heard<lo)|(heard>hi))))
    assert np.array_equal(sound[offset+span:],silent[offset+span:])
    changed=int(np.any(heard!=dry,axis=1).sum());assert changed>100
    return dict(original_ee_iop_channel=channel,spu_sample_frames=span,changed_stereo_frames=changed,pitch=voice.pitch,volume_register=voice.volume,window_sha256=hashlib.sha256(sound[offset:offset+span].tobytes()).hexdigest())

def verify(viewer,exe,base,name,groups,begin,pictures,heal,items=True):
    inputs,rows=trace(exe,base,groups,begin,pictures,items)
    p=original();p.run(0x1b5b08,limit=100000);p.write(0x4c3808,3,4)
    battle=0x1c30000;p.write(0x4d3d00,battle,4);p.memory[battle:battle+0x500]=bytes(0x500)
    recovery=[];images=[];n=0;first=last=0;tex=atlas()[10];scenery=SourceStage()
    for row in rows:
        t,delta,x0,x1=map(int,row[:4]);cam=row[4:9];hp=list(map(int,row[9:15]));se,depth,fx,count=map(int,row[15:19]);steps=list(map(int,row[19:26]));native=row[26:]
        for a,f in zip((0x4a2a58,0x4a2a5c,0x4a2a60,0x4a2a6c,0x4a2a68),cam):struct.pack_into('<f',p.memory,a,f)
        struct.pack_into('<f',p.memory,0x4a2a64,-160)
        for i,x in enumerate((x0,x1)):
            task=0x1ba0000+i*0x1000;o=task+0x100
            p.write(battle+0x29c+i*0x108,task if x>=0 else 0,4);p.write(task+0x1c,o,4);p.write(o+0xcc,4,4);struct.pack_into('<2f',p.memory,o+0x40,x,0)
        p.write(0x46a908,delta,4);p.write(0x3db8f4,depth,4)
        for a in (0x345178,0x378e08,0x3db8f8):p.write(a,0,4)
        packets=[]
        def draw(pc):
            if pc!=0x108464:return
            sub=p.registers[19];data=p.read(sub+24,4);assert p.registers[16]==10
            packets.append([struct.unpack_from('<5fI',p.memory,data+i*24) for i in range(4)])
        _,ins=p.run(0x1b5e30,limit=500000,observe=draw);n+=ins
        want=[]
        for q in packets:want.extend([*q[0][:2],*q[3][:2],q[0][3],q[0][4],q[0][5]>>24])
        assert len(packets)==count and np.allclose(want,native,rtol=0,atol=1e-5),(name,t,native,want)
        if count:
            if not first:first=t
            last=t
        sent=[]
        for i in range(2):
            old,new,x=hp[3*i:3*i+3]
            if new<=old:continue
            _,ins=p.run(0x1b5b80,[0,x,80],limit=200000,observe=lambda pc:sent.append((p.registers[4]&0xffffffff,p.registers[5])) if pc==0x1e7b70 else None);n+=ins
            recovery.append((t,i,old,new))
        assert sent==[(0xffffffff,65)]*se,(name,t,se,sent)
        if t in pictures:
            assert not fx and packets,(name,t,fx,count)
            # Priority 10 consumes 114d88 depth records before priority 20.
            # Seed current picture steps and use the full stage submission at
            # the observed live projection to validate its cumulative count.
            sp=scenery.p
            for addr,f in zip(PROJECTION,cam):struct.pack_into('<f',sp.memory,addr,f)
            for addr,step in zip(scenery.states,steps):sp.write(addr,0,4);sp.write(addr+0x2c,step,4)
            sp.write(0x46a908,0,4);sp.run(0x114e80);sp.run(0x1a7810,limit=1800000)
            assert sp.read(0x3db8f4,4)==depth,(name,t,sp.read(0x3db8f4,4),depth)
            baseline=np.fromfile(base/f'{t}.base',dtype=np.uint8).reshape(448,640,4)
            expected=raster(packets,tex,baseline);observed=actual_scene(viewer,inputs,base,t)
            different=np.any(observed!=expected,axis=2);changed=int(np.any(expected!=baseline,axis=2).sum())
            assert not different.any() and changed,(name,t,int(different.sum()),changed)
            filename=f'stage-item-{name}.png'
            if t==pictures[0]:Image.fromarray(observed).save(OUT/filename)
            images.append(dict(tick=t,gs_packets=count,visible_pixels=changed,stage_depth_cursor=depth))
    assert recovery==heal,(name,recovery,heal)
    if items:assert first==heal[0][0]+1 and last==heal[0][0]+59,(first,last)
    else:
        counts={int(row[0]):int(row[18]) for row in rows}
        assert [counts[t] for t in (1351,1402,1403,1440,1441,1495)]==[2,2,1,1,0,0]
    sound=actual_audio(viewer,inputs,base,recovery[0][0]) if recovery else None
    return dict(name=name,sound=sound,pad_ticks=len(inputs),first_visible=first,last_visible_in_run=last,heals_and_common_se65=recovery,original_instructions=n,images=images)

def main():
    assert digest(ELF)==PIN
    viewer=BUILD/'ss6-viewer'
    with tempfile.TemporaryDirectory() as temp:
        base=Path(temp);cpp=base/'match.cpp';exe=base/'match';cpp.write_text(DRIVER)
        subprocess.run(['c++','-std=c++20','-ffp-contract=off','-O2','-I',ROOT/'src',cpp,LIB,'-o',exe],check=True)
        result=[verify(viewer,exe,base,'p1-food',P1,5103,[5120,5160],[(5118,0,173,176)]),verify(viewer,exe,base,'p2-food',P2,2914,[2931,2971],[(2929,1,156,171)]),verify(viewer,exe,base,'both-weapons',ARROWS,1250,[1351,1371,1434],[],False)]
    report=dict(status='passed',elf_sha256=PIN,library_sha256=digest(LIB),viewer_sha256=digest(viewer),replay_sha256=digest(BUILD/'ss6-match-replay'),cases=result,scope='Real character, spirit, stage and item option selection and normal gameplay inputs. Samples compare production viewer scene with actual Japanese 1b5e30 packets composited on the same combat view without notices. 1b5b80 sound submissions checked against 212fa0 bank/tone each examined live tick. Production WAV with and without just the heal sample is checked against the dry sample contribution from the Japanese EE and ADPCMST.IRX with separate software SPU2 interpolation model.')
    (OUT/'stage_item_notice_scene_validation.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
