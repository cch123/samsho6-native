#!/usr/bin/env python3
"""Compare both Shin seats' actual battle layers and stage with Japanese EE draw commands."""
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
import hashlib
import io
import json
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile

from PIL import Image

from validate_combat_stage import DRIVER as STAGE_DRIVER, PACKAGE, SourceStage, replay_text
from validate_jump_light_presentation import (
    ASSETS, BUILD, CAPTURE_DRIVER, HEIGHT, LIB, OUT, ROOT, SOURCE_HASH, WIDTH, compare, fixture, sha, verify_queue,
)
from validate_native_scene import capture_combat_layers

BANKS=('01HitFlash.bin','02Guard.bin','03etc.bin','04tenso.bin','Display.bin','Display2.bin','Display3.bin')


def pads(side,move):
    forward=(128,64)[side];back=forward^192
    def pair(n,a=0,b=0):return (n,b,a) if side else (n,a,b)
    seq=[pair(500)]
    if move=='doll':
        keys=[forward,32|forward,32,32|back,back,forward,back|4096]
    else:
        if move=='destruction':
            # Four counterparty standing heavies fill the Shin fighter's rage.
            seq += [pair(65,0,back),pair(5),pair(1,0,1024),pair(88)]*4+[pair(100)]
        seq += [pair(75,forward),pair(5)]
        keys=([32,32|forward,forward|768] if move=='destruction'
              else [32|forward,back,32|back,32,32|forward,forward,back,32,(32|back)|1536])
    return seq+[pair(1,key) for key in keys]+[pair(250)]


def targets(side,move):
    def actor(slot,act):return dict(slot=slot,action=act,steps=[])
    def world(bank,acts):return dict(kind='effect',bank=bank,actions=list(acts),steps=[])
    if move=='doll':return {527:('wooden-doll-smoke',actor(2,54))}
    if move=='secret':return {596:('secret-focus',actor(side,612)),616:('secret-attachment',actor(side,614))}
    return {
        1318:('before-start',actor(2,25)),1327:('world2',world(4,range(4))),
        1383:('last-focused-update',actor(1-side,0)),1384:('focus-released',actor(1-side,0)),
        1411:('referee-points',actor(2,(37,36)[side])),1470:('broken-weapon-falling',actor(1-side,468)),
        1487:('world10-sword-shattering',world(3,range(16,23))),1502:('world10-late-fragments',world(3,range(16,23))),
    }


def compile_driver(folder,name,source,lib):
    path=folder/(name+'.cpp');path.write_text(source)
    subprocess.run(['c++','-std=c++20','-O2','-ffp-contract=off','-I',ROOT/'src',path,lib,'-o',folder/name],check=True)


def run_case(args):
    tmp,side,move=args
    window=range(1319,1384) if move=='destruction' else range(589,606) if move=='secret' else ()
    return compare_battle_sequence(tmp,side,move,'shin',pads(side,move),targets(side,move),window,
                                   ('world2','world10-sword-shattering'))


def compare_battle_sequence(tmp,side,move,spirit,seq,wanted,focus_ticks,saved,assets=PACKAGE/'assets',white_ticks=(),concentration_ticks=()):
    work=tmp/f'{side}-{move}';work.mkdir()
    spirits=('rage',spirit) if side else (spirit,'rage')
    raw_spirits=[str(('rage','shin','zan','ten','zero','ken').index(name)) for name in spirits]
    last=max(wanted)
    replay=replay_text(seq,last)
    stage_rows=subprocess.check_output([tmp/'stage',assets,work,'--spirits',*raw_spirits],input=replay,text=True).splitlines()
    ticks=[(a,b) for n,a,b in seq for _ in range(n)][:last]
    commands=''.join(f'tick {a} {b} {int(i in wanted)}\n' for i,(a,b) in enumerate(ticks,1))
    data=io.BytesIO(subprocess.check_output([tmp/'queue',assets,*raw_spirits],input=commands.encode()))
    ee=fixture();stage=SourceStage();stats=Counter();cases=[]
    for i,name in enumerate(BANKS):
        start=0x4a4810+0x3da0*i;blob=(ASSETS/name).read_bytes()
        assert len(blob)==0x3da0 and blob==(assets/name).read_bytes()
        ee.memory[start:start+len(blob)]=blob
    for line in stage_rows:
        row=list(map(int,line.split()));tick,visit,delta=row[:3]
        if not visit:
            assert tick not in wanted
            continue
        stage.p.write(0x50e04c,int(tick-1 in white_ticks),4)
        strips=stage.visit(delta,row[5:10],tick in wanted)
        assert stage.layers()==list(zip(row[16::3],row[17::3],row[18::3])),(move,side,tick,'stage clocks')
        if tick not in wanted:continue
        name,vis=wanted[tick]
        count,=struct.unpack('<I',data.read(4));submission=[data.read(328) for _ in range(count)]
        meta=data.getbuffer()[data.tell():]
        earlier=tuple(int(i==side and tick-1 in concentration_ticks) for i in range(2)) if concentration_ticks else None
        verify_queue(ee,submission,meta,earlier)
        focus,=struct.unpack_from('<i',meta,44)
        # 1493c0 assigns the acting seat on entry. 1421e8 clears focus on
        # the update after the 64/16-tick lock. Stage tones cover 512..1023.
        expected_focus=side if tick in focus_ticks else -2
        assert focus==expected_focus,(name,side,tick,focus)
        tone=(4 if focus>=0 else 0) | int(tick in concentration_ticks)
        assert set(struct.unpack_from('<512H',meta,148+1024))=={tone},(name,side,tick,'stage tint')
        del meta
        image=stage.rgba(strips,[tone]*512).tobytes()
        pad=work/'replay';pad.write_text(replay_text(seq,tick))
        # Save the shipping SDL view with the HUD for inspection. Its arena
        # pixels are independently verified before these images are published.
        snapshot=work/'window.bmp' if name in saved else None
        seen,arena=capture_combat_layers(tmp/'viewer',pad,work,spirits,assets,snapshot)
        assert arena==image,(name,side,tick,'stage raster')
        depth=0
        if tick in white_ticks:
            packets=[]
            def submit(pc):
                if pc==0x1058f8:
                    for j in range(4):
                        at=ee.registers[6]+16*j
                        xyz=ee.read(at+16,8)
                        packets.append((((xyz&65535)-0x6c00)//16,(((xyz>>16)&65535)-0x7900)//8,
                                        xyz>>32,ee.read(at+8,4)))
            ee.run(0x1419b0,(0xffffffff,1),observe=submit,limit=130000)
            assert {(x,y) for x,y,_,_ in packets}=={(0,0),(0,480),(640,0),(640,480)}
            depth=packets[0][2]
            assert all(z==9995756 and color==0x80ffffff for _,_,z,color in packets)
            assert all(s[0]<depth for s in strips)
            image=bytes([255])*len(image)
        out=compare(ee,data,stats,(name,side,tick),seen,vis,image,depth)
        assert vis['steps'] and vis['visible_pixels']>0,(name,side,tick,vis)
        cases.append(dict(move=move,update=tick,**{spirit+'_seat':side+1},sample=name,focus=focus,stage_tone=tone,
                          stage_strips=len(strips),stage_sha256=hashlib.sha256(arena).hexdigest(),backdrop_depth=depth,
                          draw_records=count,**vis,rgba_sha256=out['viewer_sha256']))
        if snapshot is not None:
            filename=f'p{side+1}-{name}.png'
            with Image.open(snapshot) as display:
                assert display.size==(640,480)
                display.convert('RGB').save(tmp/filename)
            cases[-1]['screenshot']=spirit+'-window/'+filename
        print(f'P{side+1} {tick} {name}: {vis["visible_pixels"]} visible pixels',flush=True)
    assert not data.read(1) and len(cases)==len(wanted)
    return cases,stats


def main():
    assert sha(ASSETS.parent/'SLPS_255.59')==SOURCE_HASH
    with tempfile.TemporaryDirectory(prefix='ss6-shin-scene-') as folder:
        tmp=Path(folder);lib=tmp/'runtime.a';shutil.copyfile(LIB,lib)
        shutil.copy2(PACKAGE/'ss6-viewer',tmp/'viewer')
        assert sha(tmp/'viewer')==sha(BUILD/'ss6-viewer'),'Repackage the current native build before validation.'
        compile_driver(tmp,'queue',CAPTURE_DRIVER,lib)
        compile_driver(tmp,'stage',STAGE_DRIVER,lib)
        cases=[];counts=Counter()
        with ProcessPoolExecutor(max_workers=4) as pool:
            for results,stats in pool.map(run_case,[(tmp,s,m) for s in range(2) for m in ('doll','destruction','secret')]):
                cases.extend(results);counts.update(stats)
        assert counts['verified_viewer_frames']==len(cases)
        result=dict(status='passed',elf_sha256=SOURCE_HASH,viewer_sha256=sha(tmp/'viewer'),runtime_sha256=sha(lib),
                    frames=len(cases),compared_pixels=len(cases)*WIDTH*HEIGHT,cases=cases,counters=counts,
                    scope='Packaged console-mode input replays. Original stage 1a7810, palette 116478/116588, sort 1207e8/122bc0, actors including referee bank 51 from 1208b0, and effects 123840, with the extracted textures and independent CPU raster. Subject visibility is the final pixel difference when its original draws are omitted. Compares the 640x448 combat layers before HUD, without PS2 GS hardware scanout.')
        (OUT/'shin-window').mkdir(exist_ok=True)
        for case in cases:
            if 'screenshot' in case:
                artifact=Path(case['screenshot']);shutil.copyfile(tmp/artifact.name,OUT/artifact)
        (OUT/'shin-scene-validation.json').write_text(json.dumps(result,indent=2)+'\n')
        print(len(cases),'frames passed',result['viewer_sha256'])


if __name__=='__main__':main()
