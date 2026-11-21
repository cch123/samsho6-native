#!/usr/bin/env python3
"""Enter from both real selection pads, test normals, then compare hurt and eagle pixels to Japanese GS."""
import argparse
from collections import Counter
from hashlib import sha256
import io
import json
from pathlib import Path
import struct
import subprocess
import tempfile

from validate_native_scene import ASSETS as SOURCE, LIB, ROOT, compare, fixture
from validate_jump_light_presentation import verify_queue
from extract_versus_quotes import ORIGINAL

OUT=ROOT/'outputs/ss6-feasibility'
BUILD=ROOT/'work/ss6/build-native'
CAPTURE=r'''
#include "local_versus.hpp"
#include "native_scene.hpp"
#include <iostream>
using namespace ss6;
void out(const auto& v){std::cout.write(reinterpret_cast<const char*>(&v),sizeof(v));}
int main(int argc,char** argv){try{
    LocalVersus session(argv[1],-1,VersusMode::Console,{},true);
    std::array<unsigned,3> ids{unsigned(std::stoi(argv[2])),unsigned(std::stoi(argv[3])),51};
    NativeScene scene(argv[1],ids);std::array<uint32_t,2> previous{},held{};
    std::vector<uint8_t> rgba(640*448*4);
    auto fill=[&](std::array<uint8_t,4> c){for(size_t i=0;i<rgba.size();i+=4)std::copy(c.begin(),c.end(),rgba.begin()+i);};
    while(std::cin>>held[0]>>held[1]){
        std::array<NormalizedPadSample,2> pads;
        for(unsigned s=0;s<2;++s)pads[s]={held[s],held[s]&~previous[s]};
        previous=held;session.tick(pads);
    }
    const auto& m=session.match();const auto& b=m.battle();const auto& q=m.objectDraws();
    if(m.lineup()[0].character!=ids[0]||m.lineup()[1].character!=ids[1]||m.characterSelect())return 3;
    fill({17,31,43,255});scene.paint(m,rgba,[&](const auto&){fill({67,29,71,255});});
    out(q.count);for(const auto& row:q.active())out(row);
    out(m.fighter(0).hits);out(m.fighter(0).guards);out(m.fighter(1).actor.fieldA30);out(q.count);
    for(auto x:{b.camera.projectionX,b.camera.projectionY,b.camera.depth,b.camera.depthOffset,b.camera.verticalOffset})out(x);
    out(b.gauges.words910[2]);out(b.gauges.words910[3]);out(b.gauges.focus46a948);out(0);
    out(b.paletteState[2]);out(b.gauges.paletteTones);for(auto i:q.sorted())out(q.slots.at(i-1));
    if(!m.effectDraws().empty())return 4;
    out(uint32_t(0));std::cout.write(reinterpret_cast<char*>(rgba.data()),rgba.size());
}catch(const std::exception& e){std::cerr<<e.what();return 1;}}
'''
from fighter_roster import cursor_path

# Fighters without a grid cell, fielded by selecting the proxy cell and SS6_SUBSTITUTE (LocalVersus).
SUBSTITUTE_PROXY={43:26}  # Makai Gaoh (arcade boss) through Gaoh's cell
def substitute_env(lineup):
    import os
    pairs=[f'{seat}:{c}' for seat,c in enumerate(lineup) if c in SUBSTITUTE_PROXY]
    return dict(os.environ,SS6_SUBSTITUTE=','.join(pairs)) if pairs else None

def prefix(lineup,spirits=None):
    pads=[[0,0] for _ in range(1250)];ends=[]
    for side,resource in enumerate(lineup):
        resource=SUBSTITUTE_PROXY.get(resource,resource)
        # From cell 2, cell 3 is one down. Cell 12 is two columns and two
        # rows up. The horizontal scroll direction mirrors for the second seat.
        forward=(128,64)[side]
        back=forward^192
        # The first five fighters keep the recorded (partly diagonal) timings
        # that existing reference runs use; later fighters follow the shortest
        # path to their CharacterSelect cell, one move every ten ticks.
        # (Rimururu's recorded three-step back path only fitted the 7-column grid; on the
        # unlocked 8-column grid she is four columns away and follows the computed path.)
        legacy={0:{66:32},1:{65:forward,76:forward,88:16,90:16},
                3:{65:forward,76:forward,88:16},
                24:{62:forward|16,72:forward|16,82:forward}}
        if resource in legacy:directions=legacy[resource]
        elif resource==48:directions={62:8}  # Start: the Kuroko view, every cell confirms 48
        else:
            masks={'forward':forward,'back':back,'up':16,'down':32}
            (col,nc),(row,nr)=cursor_path(resource)
            # Row moves ride along with column moves (diagonals, as the
            # recorded Rimururu path does); a column move waits 10 ticks for
            # the page scroll, leftover rows follow 12 ticks after it, and
            # everything lands before P2's confirmation at tick 92.
            directions={}
            for k in range(max(nc,nr)):
                if k<nc:tick=62+10*k
                elif nc:tick=62+10*(nc-1)+12+2*(k-nc)
                else:tick=62+2*k
                directions[tick]=(masks[col] if k<nc else 0)|(masks[row] if k<nr else 0)
        for tick,mask in directions.items():pads[tick-1][side]=mask
        # The cursor accepts input again 10 ticks after a column move (2 after a row move).
        last=max(directions,default=0)
        # The Kuroko wipe blocks input for 21 updates (12db80).
        ends.append(last+(22 if directions[last]==8 else 10 if directions[last]&192 else 2) if directions else 0)
    # Select one costume on each seat (P2 first). A long 8-column path delays both
    # confirmations, and every later step by the same amount; short paths keep the
    # original ticks. Confirm both Ken spirits, let P2 choose the default binary
    # setting, then move random stage 10 to 0.
    p2=max(92,ends[1]);p1=max(99,ends[0],p2+7);delta=p1-99
    # Optional spirits (system ids 0..5): the wheel opens on Ken (5), so system s takes (s+1)%6
    # right presses (one per 12 ticks, 10 for the turn); later steps move by the same amount.
    # 44..47 keep their single spirit 8.
    turns=[(s+1)%6 if lineup[i] not in (44,45,46,47) else 0 for i,s in enumerate(spirits)] if spirits else [0,0]
    for side,k in enumerate(turns):
        for n in range(k):pads[245+delta+12*n-1][side]=128
    delta+=12*max(turns)
    for tick,side,mask in ((p2,1,512),(p1,0,256),(245+delta,0,1024),(249+delta,1,1024),
                          (280+delta,1,1024),(310+delta,1,128),(355+delta,1,1024),(465+delta,0,8)):
        pads[tick-1][side]=mask
    return pads

def trace(exe,assets,pads):
    lines=''.join(f'1 {x} {y}\n' for x,y in pads)
    result=subprocess.run([exe,assets,'--mode','select','--select-fields'],input=lines,text=True,capture_output=True)
    if result.returncode:raise RuntimeError(f'{result.stderr.strip()} at pad tick {len(result.stdout.splitlines())+1}')
    return [r.split() for r in result.stdout.splitlines()]

def capture(exe,viewer,assets,work,p,lineup,pads,tick,visibility,stats,final_overlay=None):
    selected=pads[:tick+1];packet=subprocess.run([exe,assets,*map(str,lineup)],check=True,capture_output=True,
        input=''.join(f'{x} {y}\n' for x,y in selected).encode()).stdout
    stream=io.BytesIO(packet);n,=struct.unpack('<I',stream.read(4))
    raw=[stream.read(328) for _ in range(n)]
    verify_queue(p,raw,stream.getbuffer()[stream.tell():])
    actors=[struct.unpack('<82I',r) for r in raw if struct.unpack_from('<I',r,324)[0]==0]
    companions={a[3]:a[9] for a in actors if a[51]==3}
    assert set(companions)=={i for i,c in enumerate(lineup) if c in (1,2)},(lineup,companions)
    for side,act in companions.items():
        assert (769<=act<=800 if lineup[side]==1 else 771<=act<=773),(lineup,side,act)
    replay=work/'inputs.pad';replay.write_text(''.join(f'1 {x} {y}\n' for x,y in selected))
    scene,arena=work/'scene.rgba',work/'stage.rgba'
    subprocess.run([viewer,'--assets',assets,'--mode','select','--match-replay',replay,
                    '--dump',scene,'--dump-stage',arena],check=True,stdout=subprocess.DEVNULL)
    def pixels(path):
        raw=path.read_bytes();assert struct.unpack_from('<2I',raw)==(640,448)
        return raw[8:]
    pos=stream.tell();seen=[]
    for target in [visibility,*[{'slot':slot,'action':act,'steps':[]} for slot,act in companions.items()]]:
        # Re-use the same original rows and backdrop for the subtraction;
        # reset its real CLUT allocator before rendering each comparison.
        stream.seek(pos)
        report=compare(p,stream,stats,f'{lineup}-{tick+1}',pixels(scene),target,pixels(arena),final_overlay=final_overlay)
        assert target['quads'] and target['visible_pixels']>0,(lineup,tick,target)
        seen.append(target.copy())
    return dict(pad_tick=tick+1,ordered_objects=n,visible=seen,rgba_sha256=report['viewer_sha256'])

def run(args):
    assets=args.assets;exe=args.replay;viewer=args.viewer
    # The viewer is invoked once per frame and may be atomically repackaged.
    # A change mid-run invalidates the per-frame comparison for that release.
    binaries=(exe,viewer)
    initial_hashes=tuple(sha256(binary.read_bytes()).hexdigest() for binary in binaries)
    stats=Counter();cases=[];movement=[]
    with tempfile.TemporaryDirectory() as temp:
        tmp=Path(temp);driver=tmp/'capture';src=tmp/'capture.cpp';src.write_text(CAPTURE)
        subprocess.run(['c++','-std=c++20','-ffp-contract=off','-O2','-I',ROOT/'src',src,LIB,'-o',driver],check=True)
        for lineup in ((0,1),(1,0),(1,1)):
            p=fixture((*lineup,51))
            for bank,filename in enumerate(('01HitFlash.bin','02Guard.bin','03etc.bin'),1):
                addr=0x4a4810+(bank-1)*0x3da0;p.memory[addr:addr+0x3da0]=(SOURCE/filename).read_bytes()
            for side in (0,1):
                jump_delay=32 if lineup[side]==1 else 29
                inputs=[(256,0,0),(512,0,0),(1024,0,0),(2048,0,0),(256,jump_delay,0)]
                if lineup[side]==1:
                    inputs.append((256,32+int(lineup[side^1]==1),32))
                for button,wait,defense in inputs:
                    mask=lambda held,other=0: (other,held) if side else (held,other)
                    pads=prefix(lineup)+[mask((128,64)[side])]*45+[mask(0,defense)]*(6 if defense else 2)
                    if wait:pads.extend([mask(16,defense)]+[mask(0,defense)]*wait)
                    attack=len(pads);pads.extend([mask(button,defense)]+[mask(0,defense)]*160)
                    rows=trace(exe,assets,pads);a=3+10*side;b=3+10*(side^1)
                    assert any(r[24]=='1' and r[45]=='0' and r[47]=='1' for r in rows[:attack])
                    assert any(int(r[48])>0 for r in rows[:attack])
                    for r in (rows[attack],rows[-1]):
                        assert (int(r[25]),int(r[35]))==lineup and (int(r[26]),int(r[36]))==(5,5)
                    action=int(rows[attack][a+2])
                    expected={256:(185,186),512:(187,188),1024:(189,190),2048:(197,)}[button] if not wait else (209,)
                    assert int(rows[attack][a])==1 and action in expected,(lineup,side,button,action)
                    hit=next(i for i,r in enumerate(rows[attack:],attack) if int(r[b+6])<200)
                    assert int(rows[hit][b])==2 and int(rows[-1][a+7])==(2 if lineup[side]==1 and button==1024 else 1) and int(rows[-1][a])==int(rows[-1][b])==0
                    case=dict(lineup=lineup,side=side,button=button,jump=bool(wait),crouching_defender=bool(defense),act=action,
                              hit_tick=hit+1,reaction=int(rows[hit][b+2]),hp=int(rows[-1][b+6]))
                    if wait:
                        # Render one release from hitstop as well as its first held pose.
                        for step in dict.fromkeys(r[b+3] for r in rows[hit:] if int(r[b+2])==case['reaction']):
                            index=next(i for i,r in enumerate(rows[hit:],hit) if r[b+3]==step)
                            case.setdefault('frames',[]).append(capture(driver,viewer,assets,tmp,p,lineup,pads,index,
                                {'slot':side^1,'action':case['reaction'],'steps':[]},stats))
                    cases.append(case)
            # These three reachable actions previously threw on resource 01.
            # Include their actual public-entry replays so a whitelist regression
            # cannot pass the four stand buttons and still crash ordinary movement.
            for side in (i for i,c in enumerate(lineup) if c==1):
                forward=(128,64)[side];back=forward^192
                for command,keys,act in (('66',(forward,0,forward),28),
                                         ('44',(back,0,back),36),
                                         ('6+Start',(forward|8,),135)):
                    pair=lambda key: (0,key) if side else (key,0)
                    pads=prefix(lineup)+[pair(key) for key in keys]+[(0,0)]*180
                    rows=trace(exe,assets,pads)[1250:];col=5+10*side
                    assert act in {int(r[col]) for r in rows}
                    assert int(rows[-1][col])==(1 if command=='6+Start' else 0)
                    movement.append(dict(lineup=lineup,side=side,command=command,act=act))
    assert initial_hashes==tuple(sha256(b.read_bytes()).hexdigest() for b in binaries),'Executable replaced during validation'
    report=dict(status='passed',original_sha256=ORIGINAL,viewer_sha256=initial_hashes[1],
                replay_sha256=initial_hashes[0],cases=cases,movement=movement,counts=stats,
                scope='Public selection entry, two human pads, both seat orders and Nakoruru mirror. All four standing buttons and descending jump A. Selected Japanese fighter/companion queues, target and eagle pixel contributions to actual viewer at stage zero.')
    (OUT/'selected-combat-validation.json').write_text(json.dumps(report,indent=2)+'\n')
    print(len(cases),'combats,',sum(len(x.get('frames',[])) for x in cases),'captured combat updates',flush=True)

if __name__=='__main__':
    ap=argparse.ArgumentParser()
    ap.add_argument('--assets',type=Path,default=OUT/'native-viewer/assets');ap.add_argument('--replay',type=Path,default=BUILD/'ss6-match-replay')
    ap.add_argument('--viewer',type=Path,default=OUT/'native-viewer/ss6-viewer');run(ap.parse_args())
