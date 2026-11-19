#!/usr/bin/env python3
"""Rasterize the Japanese VS portrait, frame, winning-streak and round-win packets."""
from functools import lru_cache
from itertools import product
from pathlib import Path
import argparse
import hashlib
import json
import struct
import subprocess
import tempfile

import numpy as np
from character_tiles_oracle import ASSETS, ROOT, ATLAS, fixture, begin
from validate_native_scene import original_quad
from validate_rage_gauge import backdrop, draw

OUT = ROOT / 'outputs/ss6-feasibility/fighter-identity-hud-validation.json'
LIB = ROOT / 'work/ss6/build-native/libss6-runtime.a'
QUEUE = 0x479250
BATTLE = 0x1d00000
OBJ = 0x132f128


@lru_cache(maxsize=1)
def atlases():
    raw = np.frombuffer((ASSETS/'obj2_16.tex').read_bytes(), np.uint8)
    return {10: (raw[:-1024].reshape(512,512),raw[-1024:].reshape(8,4,8,4)[:,[0,2,1,3]].reshape(256,4))}


def make_original(characters,palettes,required):
    p=fixture((*characters,51))
    # Fixture MAP0 custom storage overlaps real game's resident HUD BSS.
    # Relocate the complete map and clear the two static portrait objects.
    data=(ASSETS/f'map_{characters[0]:02}.bin').read_bytes()
    p.memory[0x1e00000:0x1e00000+len(data)]=data
    p.write(0x475210,0x1e00000,4)
    p.memory[0x132f000:0x1330000]=bytes(4096)
    begin(p,zcount=100)
    tex=(ASSETS/'obj2_16.tex').read_bytes()
    p.memory[0x1c80000:0x1c80000+len(tex)]=tex
    for offset,value in ((0,0x1c80000),(4,512),(8,512),(12,19),(20,9),(24,9),(36,1)):
        p.write(0x3a9680+10*40+offset,value,4)
    p.write(0x4d3d00,BATTLE,4)
    for s in range(2):
        select=0x456890+s*0x30
        p.write(select,characters[s],4);p.write(select+8,palettes[s],4)
        p.write(select+0x20,required[s],4)
    # Enter immediately after resource load and task creation. Both original
    # 11fed0 initializations, including slot -> base palette, run in full.
    p.put(16,OBJ);p.put(17,OBJ+0x138)
    for reg,at in ((20,0x6547f0),(21,0x6547ec),(22,0x6547e8)):
        p.floats[reg]=p.read(at,4)
    p.run(0x1ba9d0,stop_before=(0x1baa20,),limit=200000)
    p.put(16,0x132f398)
    p.run(0x1baad8,stop_before=(0x1bab04,),limit=1000)
    return p


def paint_original(frame,characters=(0,0),palettes=(0,0),wins=(0,0),required=(2,2),*,
                   language=0,session_wins=(0,0),submode=2,focus=-2,clocks=(0,0),
                   tones=None,portraits=True,ornaments=True,previous_visits=0):
    """Paint in place. session_wins gives the current consecutive wins in each seat."""
    p=make_original(characters,palettes,required)
    assert not min(session_wins)
    streak=max(session_wins);last_entrant=1 if session_wins[0] or not streak else 0
    for addr,value in ((0x58223c,3),(0x582240,submode),(0x582244,streak),(0x4c3818,last_entrant),
                       (0x46a948,focus),(0x46a918,clocks[0]),(0x46a91c,clocks[1])):
        p.write(addr,value,4)
    p.write(0x43d052,language,1)
    for seat,win in enumerate(wins):
        p.write(BATTLE+0x254+0x108*seat+0x28,win,4)
    if tones is not None:
        p.memory[0x3ebf30:0x3ec730]=np.asarray(tones,dtype='<u2').tobytes()
    for _ in range(previous_visits+1):
        p.run(0x1207d8)
        p.run(0x1baf18,limit=200000)
    assert p.read(0x4a2250,4)==2
    rows=[bytes(p.memory[QUEUE+i*328:QUEUE+(i+1)*328]) for i in range(2)]
    quads=[]
    if portraits:
        def observe(pc):
            if pc==0x108910:
                verts=struct.unpack_from('<24I',p.memory,p.registers[4])
                arg=p.registers[6]&0xffffffff
                assert arg>>8==128
                quads.append((0x11e7980+(arg&255)*64,(verts,p.read(0x3a8e44,4),p.read(0x348b10,4))))
        for i in range(2):p.run(0x1208b0,[QUEUE+i*328],observe=observe,limit=600000)
        p.run(0x116d10,limit=600000)
        flat=memoryview(frame).cast("B")
        atlas=memoryview(p.memory)[ATLAS:ATLAS+131072]
        for palette,quad in quads:original_quad(p,palette,atlas,flat,quad)
    planes=0
    if ornaments:
        funcs=(0x1baf18,0x1bb2c8,0x1bbec8)
        for ptr in (0x345178,0x378e08):p.write(ptr,0,4)
        planes=draw(p,frame,atlases(),functions=funcs)
    return rows,len(quads),planes


DRIVER=r'''
#include "fighter_identity_hud.hpp"
#include "native_scene.hpp"
#include "battle_round.hpp"
#include <iostream>
using namespace ss6;
int main(int argc,char** argv) {
    FighterIdentityHud hud(argv[1]);
    std::array<unsigned,3> chars{};chars[2]=51;
    unsigned c0,c1,sub,lang,streak,last,w0,w1,r0,r1,clk0,clk1,tone;
    int focus;
    while(std::cin>>c0>>c1>>sub>>lang>>streak>>last>>w0>>w1>>r0>>r1>>focus>>clk0>>clk1>>tone) {
        chars[0]=c0;chars[1]=c1;
        BattleRoundState b;
        b.consoleMenu.session.streak=streak;b.consoleMenu.session.lastEntrant=last;
        b.matchEnd.submodeA0=sub;b.matchEnd.characterVersion43d052=lang;
        b.match.players[0].wins=w0;b.match.players[1].wins=w1;
        b.match.players[0].requiredWins=r0;b.match.players[1].requiredWins=r1;
        b.gauges.delta46a908=0;b.gauges.words910[2]=clk0;b.gauges.words910[3]=clk1;b.gauges.paletteTones.fill(tone);
        FighterIdentityHudState state;state.sample(b,false);
        // Later priority-50 can change the menu score, while this HUD still owns the sampled streak.
        b.consoleMenu.session.streak++;if(sub==0||streak)state.sample(b,false);
        ObjectDrawQueue queue;FighterIdentityHud::submitPortraits(queue,b.gauges,chars,state);queue.sort();
        for(const auto& row:queue.active())std::cout.write(reinterpret_cast<const char*>(row.data()),328);
        NativeScene scene(argv[1],chars);
        std::vector<uint8_t> rgba(640*448*4);
        for(int y=0;y<448;++y)for(int x=0;x<640;++x){
            auto* px=&rgba[(y*640+x)*4];px[0]=x+2*y;px[1]=3*x+y;px[2]=x^y;px[3]=255;
        }
        scene.paint(queue,{b.camera,{clk0,clk1},focus,0},b.paletteState,b.gauges.paletteTones,rgba,[](const auto&){});
        hud.paint(state,rgba);
        std::cout.write(reinterpret_cast<const char*>(rgba.data()),640*105*4);
    }
}
'''


def live(viewer,assets,replay):
    from PIL import Image
    from validate_nakoruru_round_finish import combat_pads
    from validate_select_session import encode

    stamps=[]
    with tempfile.TemporaryDirectory() as td:
        td=Path(td)
        for seat,lineup in ((0,(1,0)),(1,(0,1))):
            pads=combat_pads(lineup,seat,'stand')
            raw=subprocess.check_output([replay,assets,'--mode','select','--vs-menu-fields'],
                                        input=''.join('1 %d %d\n'%tuple(r) for r in pads).encode())
            rows=[s.split() for s in raw.decode().splitlines()]
            won=next(i for i,r in enumerate(rows) if r[12+10*seat]=='1')
            menu=next(i for i,r in enumerate(rows) if r[24]=='1')
            assert tuple(map(int,rows[menu][37:40]))==(seat,1,1-seat)
            button=lambda mask:(0,mask) if seat else (mask,0)
            pads=pads[:menu+1]+[(0,0)]*45+[button(32),(0,0),button(1024)]+[(0,0)]*510
            cases=[(1250,'opening',(0,0),(0,0)),(won+1,'before-points',(0,0),(0,0)),
                   (won+2,'points',button(1),(0,0)),(len(pads),'continue',(0,0),button(1))]
            for tick,label,wins,streak in cases:
                seq=td/'input.pad';seq.write_text(encode(pads[:tick]));stage=td/'scene.rgba';img=td/'window.bmp'
                subprocess.run([viewer,'--assets',assets,'--mode','select','--match-replay',seq,'--dump',stage,
                                '--snapshot',img],check=True,capture_output=True)
                frame=np.frombuffer(stage.read_bytes(),np.uint8,offset=8).reshape(448,640,4).copy()
                with Image.open(img) as im: window=np.array(im.convert('RGBA'))[:448]
                # The adjacent life and central clock have independently tested textures.
                # These cutouts contain no life/clock geometry but retain the stage below the HUD.
                mask=np.zeros((448,640),bool)
                mask[28:85,4:59]=True;mask[28:85,581:636]=True
                mask[85:99,232:277]=True;mask[85:99,366:411]=True
                mask[10:28,174:281]=True;mask[10:28,362:447]=True
                paint_original(frame,lineup,wins=wins,session_wins=streak)
                dif=np.argwhere(mask&np.any(frame!=window,axis=-1))
                if len(dif):
                    y,x=dif[0];raise AssertionError((seat,label,tick,len(dif),int(x),int(y),frame[y,x],window[y,x]))
                stamps.append(dict(winner=seat+1,lineup=lineup,event=label,tick=tick,round_points=wins,
                                   consecutive_match_wins=streak,pixels=int(mask.sum()),
                                   sha256=hashlib.sha256(window[mask].tobytes()).hexdigest()))
    report=dict(status='passed',viewer_sha256=hashlib.sha256(viewer.read_bytes()).hexdigest(),
                replay_sha256=hashlib.sha256(replay.read_bytes()).hexdigest(),captures=stamps,
                source='Public character select and two natural heavy-slash rounds per side, actual CONTINUE from second menu row. Original 1baf18/1208b0 portraits, 1bbec8 round points and 1bb2c8 consecutive-match wins on the released SDL framebuffer. Original common inputs exercised by validate_fighter_identity_hud.py.')
    (OUT.parent/'fighter-identity-window-validation.json').write_text(json.dumps(report,indent=2)+'\n')
    print(len(stamps),'window captures',sum(s['pixels'] for s in stamps),'pixels')


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--window',action='store_true')
    ap.add_argument('--viewer',type=Path,default=OUT.parent/'native-viewer/ss6-viewer')
    ap.add_argument('--assets',type=Path,default=OUT.parent/'native-viewer/assets')
    ap.add_argument('--replay',type=Path,default=LIB.parent/'ss6-match-replay')
    args=ap.parse_args()
    if args.window:return live(args.viewer,args.assets,args.replay)
    cases=[]
    for k,chars in enumerate(product(range(4),repeat=2)):
        for n in range(4):
            submode=0 if n==3 else 2
            last=(k+n)%2;streak=(0,1,23,105)[n]
            cases.append((chars,submode,n%2,streak,last,(n%3,k%3),(2,3),(-2,0,1,-2)[n],
                          ((0,0),(0,1),(1,0),(0,0))[n],int(n==3)*4))
    with tempfile.TemporaryDirectory() as work:
        work=Path(work);src=work/'validate.cpp';src.write_text(DRIVER)
        exe=work/'validate'
        subprocess.run(['c++','-std=c++20','-O2','-ffp-contract=off','-I',ROOT/'src',src,
                        ROOT/'src/fighter_identity_hud.cpp',LIB,'-o',exe],check=True)
        lines=[' '.join(map(str,(*c,sm,lan,st,last,*wins,*req,f,*cl,t))) for c,sm,lan,st,last,wins,req,f,cl,t in cases]
        output=subprocess.check_output([exe,ASSETS],input=('\n'.join(lines)+'\n').encode())
    offset=0;tiles=planes=0
    for i,(characters,sm,language,streak,last,wins,required,focus,clocks,tone) in enumerate(cases):
        frame=backdrop()
        session=[0,0];session[1-last]=streak
        rows,n,s=paint_original(frame,characters,(i%5,(i+2)%5),wins,required,language=language,
                                submode=sm,session_wins=session,focus=focus,clocks=clocks,tones=[tone]*1024,previous_visits=int(bool(sm==0 or streak)))
        for seat,expected in enumerate(rows):
            actual=output[offset:offset+328];offset+=328
            if actual!=expected:
                fields=[(i//4,actual[i:i+4].hex(),expected[i:i+4].hex()) for i in range(0,328,4) if actual[i:i+4]!=expected[i:i+4]]
                raise AssertionError((characters,seat,'queue',fields))
        count=640*105*4;actual=np.frombuffer(output[offset:offset+count],np.uint8).reshape(105,640,4);offset+=count
        diff=np.argwhere(np.any(actual!=frame[:105],axis=-1))
        if len(diff):
            y,x=diff[0];raise AssertionError((i,characters,len(diff),x,y,actual[y,x],frame[y,x]))
        tiles+=n;planes+=s
    assert len(output)==offset
    report=dict(status='passed',fighters=[0,1,2,3],lineups=16,cases=len(cases),round_wins=[0,1,2],required_wins=[2,3],
                consecutive_match_wins=[0,1,23,105],portrait_queue_records=len(cases)*2,original_portrait_tile_quads=tiles,
                original_atlas_packets=planes,rgba_pixels=len(cases)*640*105,
                elf_sha256=hashlib.sha256((ASSETS.parent/'SLPS_255.59').read_bytes()).hexdigest(),
                runtime_sha256=hashlib.sha256(LIB.read_bytes()).hexdigest(),
                source='1ba9d0 and 1baad8 initialization slices; complete 1baf18, 1bb2c8 and 1bbec8. Original 1207e8 character queue and 1208b0 GS tiles, 116d10 CLUT, and 108464 atlas packets. Independent software raster, local two-human VS and fixed-match. Original 1bc098 omitted by dispatch for GameData.mode=3.')
    OUT.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))


if __name__=='__main__':main()
