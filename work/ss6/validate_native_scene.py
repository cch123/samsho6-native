#!/usr/bin/env python3
"""Read unmodified draw inputs and packets from the original executable, then compare software composition."""
import collections
import hashlib
import json
import math
import shutil
import struct
import subprocess
import tempfile
from functools import lru_cache
from pathlib import Path
from character_tiles_oracle import ASSETS, ATLAS, ROOT, begin, bits, fixture
from extract_collision_tables import SOURCE_HASH

WIDTH, HEIGHT = 640, 448
LIB = ROOT / 'work/ss6/build-native/libss6-runtime.a'
PICTURE = bytes((17, 31, 43, 255))*(WIDTH*HEIGHT)
EFFECT = bytes((67, 29, 71, 255))*(WIDTH*HEIGHT)
# A solid full-screen marker makes the position of each kind-1 callback
# visible. Actual effect texture/quad pixels have their own validation.
DRIVER = r'''
#include "native_scene.hpp"
#include "native_match.hpp"
#include <bit>
#include <iostream>
#include <memory>
using namespace ss6;
void out(const auto& v){std::cout.write(reinterpret_cast<const char*>(&v),sizeof(v));}
uint32_t word(){uint32_t v;if(!(std::cin>>v))throw std::runtime_error("Missing input");return v;}
void fill(std::vector<uint8_t>& v,std::array<uint8_t,4> color){for(size_t i=0;i<v.size();i+=4)std::copy(color.begin(),color.end(),v.begin()+i);}
int main(int argc,char** argv){try {
    if(argc!=2&&argc!=4)return 2;std::array<unsigned,2> spirits{};
    if(argc==4)spirits={unsigned(std::stoul(argv[2])),unsigned(std::stoul(argv[3]))};
    NativeScene scene(argv[1]);EffectBank legacy(argv[1]);auto match=std::make_unique<NativeMatch>(argv[1],-1,VersusMode::Console,nullptr,spirits);StageCamera camera;
    EffectPalettes palette{};std::array<uint16_t,1024> tones{};std::array<uint32_t,2> previous{};
    std::vector<uint8_t> rgba(640*448*4);std::string op;
    while(std::cin>>op){
        if(op=="reset"){match=std::make_unique<NativeMatch>(argv[1],-1,VersusMode::Console,nullptr,spirits);previous={};continue;}
        ObjectDrawQueue queue;const ObjectDrawQueue* current=&queue;const StageCamera* view=&camera;
        const auto* colors=&palette;const auto* tint=&tones;std::array<uint32_t,2> clocks{};int32_t focus=-2,stage=0;
        fill(rgba,{17,31,43,255});
        auto effect=[&](const EffectDraw&){fill(rgba,{67,29,71,255});};
        if(op=="objects"){
            const unsigned mask=word();for(unsigned i=0;i<24;++i)palette[2][i]=(mask>>i)&1;
            const unsigned tone=word();tones.fill(uint16_t(tone));clocks[0]=word();clocks[1]=word();queue.count=word();
            for(auto& row:std::span(queue.slots).first(queue.count))for(auto& field:row)field=word();
            queue.sort();scene.paint(queue,{camera,clocks,focus,stage},palette,tones,rgba,effect);
        }else if(op=="tick"){
            std::array<NormalizedPadSample,2> pads;for(unsigned i=0;i<2;++i){auto mask=word();pads[i]={mask,mask&~previous[i]};previous[i]=mask;}
            match->tick(pads);if(!word())continue;
            current=&match->objectDraws();const auto& b=match->battle();view=&b.camera;colors=&b.paletteState;tint=&b.gauges.paletteTones;focus=b.gauges.focus46a948;
            clocks={b.gauges.words910[2],b.gauges.words910[3]};scene.paint(*match,rgba,effect);
        }else throw std::runtime_error("Unknown fixture");
        out(match->fighter(0).hits);out(match->fighter(0).guards);out(match->fighter(1).actor.fieldA30);
        out(current->count);for(float x:{view->projectionX,view->projectionY,view->depth,view->depthOffset,view->verticalOffset})out(x);
        out(clocks);out(focus);out(stage);out((*colors)[2]);out(*tint);
        for(auto index:current->sorted())out(current->slots.at(index-1));
        const auto* overlay=(op=="tick"?&match->effectDraws():nullptr);uint32_t overlays=overlay?overlay->size():0;out(overlays);
        if(overlay)for(const auto& draw:*overlay){
            AuxiliaryObject o{};writeEffectState(o,draw.state);bool found=false;
            for(auto [bank,action]:{std::pair{1u,18u},std::pair{7u,0u},std::pair{7u,1u},std::pair{7u,2u},std::pair{7u,3u}}){
                const auto& clip=legacy.action(bank,action);if(draw.state.step>=clip.size()||clip[draw.state.step].fields!=draw.record.fields)continue;
                o[5]=bank;o[9]=action;found=true;break;
            }
            if(!found)throw std::runtime_error("Unknown replay overlay");
            ObjectDrawQueue::Record row{};std::copy_n(o.begin(),78,row.begin());row[81]=1;out(row);
        }
        std::cout.write(reinterpret_cast<char*>(rgba.data()),rgba.size());
    }
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}}
'''


def original_quad(p, palette, atlas, frame, q, minimum_z=0):
    verts, mode, additive = q
    vv=[struct.unpack('<5fI',struct.pack('<6I',*verts[i:i+6])) for i in range(0,24,6)]
    if vv[0][2]<minimum_z:return
    origin=vv[0];a=(vv[1][0]-origin[0],vv[1][1]-origin[1]);b=(vv[2][0]-origin[0],vv[2][1]-origin[1]);det=a[0]*b[1]-a[1]*b[0]
    if not det:return
    mod=origin[5].to_bytes(4,'little');colors=[]
    for r,g,blue,alpha in struct.iter_unpack('4B',p.memory[palette:palette+64]):
        rgb=tuple(min(255,(t*m)//128+(mod[3] if mode==3 else 0)) for t,m in zip((r,g,blue),mod))
        colors.append((*rgb,alpha if mode==3 else min(255,alpha*mod[3]//128)))
    for y in range(max(0,math.floor(min(v[1] for v in vv))),min(HEIGHT,math.ceil(max(v[1] for v in vv)))):
        for x in range(max(0,math.floor(min(v[0] for v in vv))),min(WIDTH,math.ceil(max(v[0] for v in vv)))):
            dx=x+.5-origin[0];dy=y+.5-origin[1]
            aa=(dx*b[1]-dy*b[0])/det;bb=(dy*a[0]-dx*a[1])/det
            if not (0<=aa<1 and 0<=bb<1):continue
            u,v=(max(0,min(511,int(512*(origin[i]+aa*(vv[1][i]-origin[i])+bb*(vv[2][i]-origin[i]))))) for i in (3,4))
            idx=(atlas[v*256+u//2]>>(4*(u%2)))&15
            r,g,blue,alpha=colors[idx]
            if alpha:
                at=(y*WIDTH+x)*4
                for c,src in enumerate((r,g,blue)):
                    dst=frame[at+c];frame[at+c]=max(0,min(255,dst+(src if additive else (src-dst)*alpha//128)))


@lru_cache(None)
def effect_texture(asset):return (ASSETS/f'effect{asset:02d}.tex').read_bytes()


def original_effect(p,frame,row,stats,minimum_z=0,*,before_depth=None):
    at=0x1e00000;p.memory[at:at+328]=struct.pack('<82I',*row)
    rec,_=p.run(0x1233a0,[at]);flags=p.read(rec,2)
    asset,pal,u0,v0,tw,th=struct.unpack_from('<6H',p.memory,rec+4)
    p.write(0x4c3510+asset*4,14,4)
    vertices=[];mode=[]
    def observe(pc):
        if pc==0x114ae8:
            vertices.extend(struct.unpack_from('<5fI',p.memory,p.registers[4]+i*24) for i in range(4))
        if pc==0x108910:
            mode.append(p.read(0x348b10,4));assert p.read(0x3a8e44,4)==0
            assert all(p.read(p.registers[4]+i*24+20,4)==0x80808080 for i in range(4))
    # Complete the caller so 123ef4 restores the additive global before
    # subsequent character shadows. Capturing only the nested call leaks it.
    _,count=p.run(0x123840,[at],observe=observe,limit=100000);stats['effect_projection_instructions']+=count
    assert len(mode)==1 and all(v[5]==0xffffffff for v in vertices) and p.read(0x348b10,4)==0
    if before_depth is not None:assert all(v[2]<before_depth for v in vertices), (vertices,before_depth)
    if vertices[0][2]<minimum_z:return
    flipx=vertices[2][3]<vertices[0][3];flipy=vertices[1][4]<vertices[0][4]
    xy=[(v[0],v[1]) for v in vertices];unit=max(2,max(q.as_integer_ratio()[1] for q0 in xy for q in q0))
    points=[(int(x*unit),int(y*unit)) for x,y in xy]
    def cross(a,b,c):return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
    triangles=[]
    for ids in ((0,1,2),(2,1,3)):
        a,b,c=[points[i] for i in ids];det=cross(a,b,c)
        if det:triangles.append((a,b,c,det,ids))
    tex=effect_texture(asset);palette=(ASSETS/'effect_pal_data.bin').read_bytes()
    for y in range(max(0,math.ceil(min(q[1] for q in xy)-.5)),min(HEIGHT,math.ceil(max(q[1] for q in xy)-.5))):
        for x in range(max(0,math.ceil(min(q[0] for q in xy)-.5)),min(WIDTH,math.ceil(max(q[0] for q in xy)-.5))):
            pt=((2*x+1)*unit//2,(2*y+1)*unit//2)
            for a,b,c,det,ids in triangles:
                weights=[cross(pt,b,c),cross(pt,c,a),cross(pt,a,b)];sign=1 if det>0 else -1
                if any(w*sign<0 for w in weights):continue
                u=tw*sum(w for w,i in zip(weights,ids) if i&2)//det
                v=th*sum(w for w,i in zip(weights,ids) if i&1)//det
                if not(0<=u<tw and 0<=v<th):continue
                if flipx:u=tw-1-u
                if flipy:v=th-1-v
                pixel=512*(v0+v)+u0+u;idx=(tex[pixel//2]>>(pixel%2*4))&15
                rgba=palette[(16*pal+idx)*4:(16*pal+idx+1)*4]
                if rgba[3]:
                    assert rgba[3]==128
                    pixel=(y*WIDTH+x)*4
                    if mode[0]:frame[pixel:pixel+3]=bytes(min(255,v+frame[pixel+i]) for i,v in enumerate(rgba[:3]))
                    else:frame[pixel:pixel+3]=rgba[:3]
                    stats['painted_effect_texels']+=1
                break
    stats['textured_effect_quads']+=1


def capture_combat_layers(viewer,replay,work,spirits=None,assets=ASSETS,snapshot=None):
    arena=work/'arena.rgba'
    scene=work/'scene.rgba'
    options=[] if spirits is None else ['--p1-spirit',spirits[0],'--p2-spirit',spirits[1]]
    if snapshot is not None:options.extend(['--snapshot',snapshot])
    subprocess.run([viewer,'--assets',assets,'--mode','versus',*options,'--match-replay',replay,
                    '--dump',scene,'--dump-stage',arena],check=True,stdout=subprocess.DEVNULL)
    def pixels(path):
        data=path.read_bytes()
        assert struct.unpack_from('<2I',data)==(WIDTH,HEIGHT) and len(data)==8+4*WIDTH*HEIGHT
        return data[8:]
    return pixels(scene),pixels(arena)


def compare(p, data, stats, label,viewer_rgba=None,visibility=None,stage_rgba=None,minimum_z=0,*,final_overlay=None):
    hits,guards,life=struct.unpack('<3I',data.read(12));n, = struct.unpack('<I',data.read(4));controls=struct.unpack('<9I',data.read(36));reserve=struct.unpack('<24I',data.read(96));tones=data.read(2048)
    rows=[struct.unpack('<82I',data.read(328)) for _ in range(n)];legacy_count,=struct.unpack('<I',data.read(4));overlays=[struct.unpack('<82I',data.read(328)) for _ in range(legacy_count)];actual=data.read(WIDTH*HEIGHT*4)
    assert len(actual)==WIDTH*HEIGHT*4
    begin(p,zcount=100)
    for at,v in zip((0x4a2a58,0x4a2a5c,0x4a2a60,0x4a2a6c,0x4a2a68,0x46a918,0x46a91c,0x46a948,0x4c3808),controls):p.write(at,v,4)
    p.write(0x4a2a64,bits(-160),4);p.memory[0x3ebf30:0x3ec730]=tones
    for i,flag in enumerate(reserve):
        p.write(0x439aa8+4*i,0,4);p.write(0x439b08+4*i,flag,4)
        if flag:p.write(0x439a48+4*i,0xffffffff,4)
    draws=[];target_quads=set();expected=bytearray(stage_rgba if minimum_z else PICTURE)
    def observe(pc):
        if pc==0x108910:
            vertices=list(struct.unpack_from('<24I',p.memory,p.registers[4]));arg=p.registers[6]&0xffffffff
            alt=p.read(0x439a40,4);uses_alt=((arg>>8)&255)<128 and alt<72
            palette=0x1232d40+alt*64 if uses_alt else 0x11e7980+(arg&255)*64
            mode=p.read(0x3a8e44,4);additive=p.read(0x348b10,4)
            stats[f'clut-alternate-{uses_alt}']+=1;stats[f'tfx{mode}-add{additive}']+=1
            if ((arg>>8)&255)<128 and alt==72:stats['overflow-fallback']+=1
            draws.append((palette,(vertices,mode,additive)))
    for row in rows:
        if row[81]:
            if visibility is not None and visibility.get('kind')=='effect' and row[5]==visibility['bank'] and row[9] in visibility['actions']:
                target_quads.add(len(draws));visibility['steps'].append([row[9],row[10]])
            draws.append(row);stats['effects']+=1;continue
        p.memory[0x1e00000:0x1e00148]=struct.pack('<82I',*row)
        first_quad=len(draws)
        _,count=p.run(0x1208b0,[0x1e00000],limit=600000,observe=observe);stats['instructions']+=count
        if visibility is not None and visibility.get('kind')!='effect' and (row[3],row[9])==(visibility['slot'],visibility['action']):
            target_quads.update(range(first_quad,len(draws)))
            visibility['steps'].append(row[10])
    _,count=p.run(0x116d10,limit=600000);stats['instructions']+=count
    atlas=p.memory[ATLAS:ATLAS+131072]
    # Overlay independent original actor and effect packets on the exact stage
    # submission. The stage geometry and color are checked separately against
    # the Japanese background task in validate_combat_stage.py.
    assert (viewer_rgba is None)==(stage_rgba is None)
    real=bytearray(stage_rgba) if stage_rgba is not None else None
    without=real.copy() if visibility is not None else None
    before_depth=final_overlay[0] if final_overlay is not None else None
    for index,draw in enumerate(draws):
        if len(draw)==82:
            expected[:]=EFFECT
            if real is not None:original_effect(p,real,draw,stats,minimum_z,before_depth=before_depth)
            if without is not None and index not in target_quads:original_effect(p,without,draw,collections.Counter(),minimum_z)
        else:
            if before_depth is not None:
                words=draw[1][0]
                depths=struct.unpack('<4f',struct.pack('<4I',*words[2::6]))
                assert max(depths)<before_depth,(label,depths,before_depth)
            original_quad(p,draw[0],atlas,expected,draw[1],minimum_z);stats['quads']+=1
            if real is not None:original_quad(p,draw[0],atlas,real,draw[1],minimum_z)
            if without is not None and index not in target_quads:original_quad(p,draw[0],atlas,without,draw[1],minimum_z)
    if real is not None:
        for row in overlays:
            original_effect(p,real,row,stats,minimum_z,before_depth=before_depth)
            if without is not None:original_effect(p,without,row,collections.Counter(),minimum_z)
    if real is not None and final_overlay is not None:
        # This shortcut is valid only when every original fighter/effect packet
        # sorts below the sampled notice, as checked above for this exact frame.
        paint=final_overlay[1];real=paint(real)
        if without is not None:without=paint(without)
    if without is not None:
        visibility['visible_pixels']=sum(a!=b for a,b in zip(memoryview(real).cast('I'),memoryview(without).cast('I')))
        visibility['quads']=len(target_quads)
    if real is not None and real!=viewer_rgba:
        at=next(i for i,(x,y) in enumerate(zip(real,viewer_rgba)) if x!=y)
        raise AssertionError((label,'viewer',at//4%WIDTH,at//4//WIDTH,at%4,real[at],viewer_rgba[at],sum(x!=y for x,y in zip(real,viewer_rgba))))
    if real is not None:stats['verified_viewer_frames']+=1
    if actual!=expected:
        at=next(i for i,(x,y) in enumerate(zip(actual,expected)) if x!=y)
        raise AssertionError((label,at//4%WIDTH,at//4//WIDTH,at%4,actual[at],expected[at],sum(x!=y for x,y in zip(actual,expected))))
    return dict(case=label,records=n,viewer_sha256=hashlib.sha256(viewer_rgba).hexdigest() if viewer_rgba is not None else None,p1_hits=hits,p1_guards=guards,p2_life=life,actions=[r[9] for r in rows if not r[81]],hash=hashlib.sha256(actual).hexdigest())


def scenarios():
    fixture_path=ROOT/'work/ss6/scenarios/character-tiles-preview.txt'
    bodies=[list(map(int,line.split()[1:83])) for line in fixture_path.read_text().splitlines() if line.startswith('object ')]
    def objects(label,rows,mask=0,tone=0,clocks=(0,0)):
        return label,'objects '+' '.join(map(str,[mask,tone,*clocks,len(rows),*(v for row in rows for v in row)]))
    yield objects('lock-weapons-common',bodies)
    yield objects('reserve-all',bodies,(1<<24)-1)
    yield objects('release-alternate-slots',bodies,0x555555,1,(1,0))
    bodies[0][9:11]=[190,6];bodies[0][14]|=0x40000000;bodies[0][35]=0x78bbbbbb
    copies=[]
    for i in range(10):
        body=bodies[0].copy();body[16]=bits(230+18*i);copies.append(body)
    yield objects('glow-clut-capacity',copies)
    effect=[0]*82;effect[5]=5;effect[9]=0;effect[81]=1
    for idx,depth in enumerate([10,0,-10]):
        effect[18]=bits(depth);yield objects(f'sorted-effect-{idx}',[bodies[0],effect,bodies[1],bodies[-1]])
    for action,step in [(28,1),(34,1),(36,2),(189,1),(190,2),(221,2),(499,8)]:
        row=bodies[1].copy();row[9:11]=[action,step];yield objects(f'action-{action}',[row])
    for result in ('hit','guard','backstep','standing','crouching'):
        yield None,'reset'
        for i in range(580):
            rel=i-450
            p1=(0x80 if rel in (2,4) or 5<=rel<24 else 0)|(0x400 if rel==17 else 0)
            p2=0x80 if result=='guard' and rel>=15 else 0
            if result in ('standing','crouching'):
                p1=128 if 438<=i<466 else 0;p2=0
                if result=='crouching':p1=32 if 468<=i<472 else (1056 if i==472 else p1)
                elif i==468:p1=1024
                capture=i in (472,482,488,494)
            elif result=='backstep':
                p1=0;p2=0x80 if rel in (2,4) else 0
                capture=i in (454,459,466,481)
            else:
                capture=i in (455,467,477,483,492,508)
                if result=='hit':capture |= i in (1,40,130,230,320,394,559)
            yield (f'live-{result}-{i}' if capture else None),f'tick {p1} {p2} {int(capture)}'



def main():
    assert hashlib.sha256((ASSETS.parent/'SLPS_255.59').read_bytes()).hexdigest()==SOURCE_HASH
    commands=list(scenarios());stats=collections.Counter();p=fixture()
    viewer=ROOT/'work/ss6/build-native/ss6-viewer'
    for bank,name in enumerate(('01HitFlash.bin','02Guard.bin','03etc.bin'),1):
        at=0x4a4810+(bank-1)*0x3da0;p.memory[at:at+0x3da0]=(ASSETS/name).read_bytes()
    with tempfile.TemporaryDirectory() as d:
        d=Path(d);src=d/'probe.cpp';src.write_text(DRIVER);exe=d/'probe'
        # Retain one binary pair while other local builds can relink the working copies.
        lib=d/'runtime.a';shutil.copyfile(LIB,lib);shutil.copy2(viewer,d/'viewer');viewer=d/'viewer'
        runtime_hash=hashlib.sha256(lib.read_bytes()).hexdigest();viewer_hash=hashlib.sha256(viewer.read_bytes()).hexdigest()
        subprocess.run(['c++','-std=c++20','-O2','-ffp-contract=off','-I',str(ROOT/'src'),str(src),str(lib),'-o',str(exe)],check=True)
        with (d/'frames').open('w+b') as frames:
            subprocess.run([exe,ASSETS],input=('\n'.join(cmd for _,cmd in commands)+'\n').encode(),stdout=frames,check=True);frames.seek(0)
            results=[]
            masks=[]
            for name,command in commands:
                if command=='reset':masks.clear()
                if command.startswith('tick '):masks.append('1 '+' '.join(command.split()[1:3]))
                if name:
                    real=background=None
                    if name in ('live-hit-483','live-hit-492','live-guard-483','live-guard-492','live-standing-482','live-standing-488','live-crouching-488','live-crouching-494'):
                        replay=d/'replay';replay.write_text('\n'.join(masks)+'\n')
                        real,background=capture_combat_layers(viewer,replay,d)
                    result=compare(p,frames,stats,name,real,stage_rgba=background);print(name,result['records'],result['actions'],flush=True);results.append(result)
            assert not frames.read(1)
        assert all(stats[name] for name in ('overflow-fallback','clut-alternate-True','tfx3-add0','effects','quads'))
        by_name={r['case']:r for r in results}
        for outcome,expected in [('hit',(1,0,175)),('guard',(0,1,200))]:
            r=by_name[f'live-{outcome}-477'];assert tuple(r[k] for k in ('p1_hits','p1_guards','p2_life'))==expected,r
            assert 221 in r['actions'],r
        assert 36 in by_name['live-backstep-459']['actions']
        assert runtime_hash==hashlib.sha256(lib.read_bytes()).hexdigest()
        assert viewer_hash==hashlib.sha256(viewer.read_bytes()).hexdigest()
        assert stats['verified_viewer_frames']==8 and stats['textured_effect_quads']>0 and stats['painted_effect_texels']>0
        report=dict(status='passed',cases=results,counts=stats,elf_sha256=SOURCE_HASH,
                    runtime_sha256=runtime_hash,viewer_sha256=viewer_hash,scene_sha256=hashlib.sha256((ROOT/'src/native_scene.cpp').read_bytes()).hexdigest(),
                    validator_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                    scope='640x448 RGBA with independent nearest-sample software raster of original 1208b0 vertices, actual atlas and 116d10 base and alternate palette memory. Sorted callbacks use a full-screen marker. Eight actual shipped viewer-path frames also compare independent original effect projection, texture and CLUT plus character composition. Live queue production is consumed as input. PS2 GS coverage/filtering and depth remain unverified.')
        (ROOT/'outputs/ss6-feasibility/native_scene_validation.json').write_text(json.dumps(report,indent=2)+'\n')
if __name__=='__main__':main()
