#!/usr/bin/env python3
"""Project two real 632146+A+B matches with the Japanese stage, camera and character routines."""
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import tempfile

import numpy as np
from PIL import Image,ImageDraw,ImageFont

from validate_camera_shake import OriginalCamera,CAMERA_OFFSETS
from validate_shake_inputs import inputs,check
from validate_haohmaru_special import run_native
from validate_combat_stage import (ASSETS,OUT,PACKAGE,SourceStage,jump_draw_records,compare_pixels,
                                   decode_floats)
from validate_jump_light_presentation import verify_queue
from validate_native_scene import compare,capture_combat_layers
from validate_dash_motion import ELF,PIN,digest


def segments(pads):
    result=[]
    for a,b in pads:
        if result and (a,b)==result[-1][1:]:
            result[-1]=(result[-1][0]+1,a,b)
        else:result.append((1,a,b))
    return result


def replay_text(pads):
    return ''.join(f'{n} {a} {b}\n' for n,a,b in segments(pads))


def validate_match(tmp,slot,mode,viewer):
    commands=inputs(80,slot,mode)
    source_flags=check(mode,slot,commands)
    triggers={item['tick']:item['body_requests'] for item in source_flags['impulses']}
    assert len(triggers)==4 and all(flags[slot]==128 and flags[1-slot]==0 for flags in triggers.values())
    first=min(triggers)
    chosen=sorted({first-1,first+1,first+2,first+3,max(triggers)+2,max(triggers)+15})
    inputs_all=[(0,0)]*500+commands
    pads=inputs_all[:max(chosen)]
    args=[f'1 {a} {b}' for a,b in pads]
    def trace(field):
        return [[int(v) if '.' not in v else float(v) for v in row] for row in
                run_native('ss6-match-replay',args,'--mode','versus',field)]
    walls,shake,stage_rows=map(trace,('--wall-fields','--shake-fields','--stage-fields'))
    active=first-5
    camera=OriginalCamera()
    # Seed from the last still frame before the move's first request, then
    # evolve the Japanese camera independently, including the unsmoothed
    # position and bounds it writes back. Only fighter positions, the
    # wall-flight hold and command queue are supplied by the battle.
    for off,raw in zip(CAMERA_OFFSETS[:13],walls[active-2][139:152],strict=True):
        camera.p.write(camera.at+off,raw,4)
    p,records=jump_draw_records(tmp,segments(pads),chosen)
    stage=SourceStage(); stats=Counter(); results=[]
    for tick,(w,s,r) in enumerate(zip(walls,shake,stage_rows,strict=True),1):
        if tick<active:
            stage.visit(256,r[24:29])
            continue
        if tick==active:
            # The previous native publication preceded every recoil request.
            previous=tuple(r[24:29])
        assert previous==tuple(r[24:29]), (mode,tick,'priority 10 camera')
        draw=tick in chosen
        strips=stage.visit(256,previous,draw)
        assert stage.layers()==list(zip(r[29:50:3],r[30:50:3],r[31:50:3]))
        old=walls[tick-2]
        if tick in triggers:camera.request(-1,16)
        count,kind,remaining=old[131:134]
        for off,value,size in ((0x4c,count,4),(0x50,kind,1),(0x54,remaining,4)):
            camera.p.write(camera.at+off,value,size)
        xy=decode_floats([w[i] for i in (23,24,49,50)])
        camera.update(*xy,bool(old[134]&4))
        projection=camera.projection()
        assert projection[:2]==tuple(s[28:30]) and camera.snapshot()[13:15]==s[23:25], (mode,tick,'fighter camera')
        stage_y,actor_y=decode_floats([previous[1],projection[1]])
        previous=projection
        if not draw:continue
        # Verify these five camera words before the existing independent
        # body/effect raster consumes the draw queue and its projection.
        n,=struct.unpack('<I',records.read(4))
        submitted=[records.read(328) for _ in range(n)]
        payload=records.getbuffer()[records.tell():]
        verify_queue(p,submitted,payload)
        assert struct.unpack_from('<5I',payload,16)==projection
        tones=struct.unpack_from('<1024H',payload,148)[512:]
        expected_stage=stage.rgba(strips,tones)
        replay=tmp/'sample.pad';replay.write_text(replay_text(pads[:tick]))
        shown,background=capture_combat_layers(viewer,replay,tmp)
        compare_pixels(np.frombuffer(background,np.uint8).reshape(448,640,4),expected_stage,(mode,tick,'stage'))
        visible=dict(slot=slot,action=592,steps=[])
        info=compare(p,records,stats,(mode,tick),shown,visible,expected_stage.tobytes())
        assert visible['visible_pixels']>0
        results.append(dict(tick=tick,stage_y=stage_y,fighter_y=actor_y,shake_y_remaining=s[24],
                            life=[w[9],w[19]],strips=len(strips),action_step=visible['steps'][0],
                            attacker_pixels=visible['visible_pixels'],composed_sha256=info['viewer_sha256']))
    assert not records.read(1) and any(frame['stage_y']!=frame['fighter_y'] for frame in results)
    assert walls[-1][19 if slot==0 else 9]==(135 if mode=='hit' else 200)
    return dict(outcome=mode,attacker=slot+1,request_ticks=list(triggers),camera_updates=len(pads)-active+1,
                sampled_compositions=results,source_calls=dict(camera.calls),pixel_checks=dict(stats)),inputs_all


def record(tmp,pads,viewer,sha,requests):
    start,end=requests[0]-45,requests[-1]+38
    ticks=range(start,end+1,2)
    def capture(tick):
        replay=tmp/f'{tick}.pad';replay.write_text(replay_text(pads[:tick]))
        image=tmp/f'{tick}.bmp'
        subprocess.run([viewer,'--mode','versus','--match-replay',replay,'--snapshot',image],check=True,capture_output=True)
        with Image.open(image) as frame:return frame.convert('RGB')
    with ThreadPoolExecutor(max_workers=4) as pool:frames=list(pool.map(capture,ticks))
    font=ImageFont.truetype('/System/Library/Fonts/Supplemental/Arial Unicode.ttf',16)
    for frame in frames:
        assert frame.size==(640,480)
        pen=ImageDraw.Draw(frame)
        # Preserve the live HUD and complete arena; the label uses only
        # the keyboard-help footer underneath the 448-line playfield.
        pen.rectangle((0,448,640,480),fill=(24,29,32))
        pen.text((14,464),'霸王丸  ·  632146＋轻斩＋中斩',font=font,fill='white',anchor='lm')
        pen.text((626,464),'实战命中  ·  原速',font=font,fill='white',anchor='rm')
    # One global palette avoids flashing colors during the actual shake.
    atlas=Image.new('RGB',(160*7,120*((len(frames)+6)//7)))
    for i,frame in enumerate(frames):atlas.paste(frame.resize((160,120),Image.Resampling.NEAREST),(i%7*160,i//7*120))
    pal=atlas.quantize(256);indexed=[f.quantize(palette=pal,dither=Image.Dither.NONE) for f in frames]
    durations=[10*(round((i+1)*100/30)-round(i*100/30)) for i in range(len(frames))]
    gif=OUT/'camera-shake-special.gif'
    indexed[0].save(gif,save_all=True,append_images=indexed[1:],duration=durations,loop=0,optimize=False,
                    disposal=1,comment=f'Packaged ss6-viewer SHA-256 {sha}; 60 Hz fight sampled at 30 fps'.encode())
    with Image.open(gif) as image:
        ms=0
        for i in range(image.n_frames):image.seek(i);ms+=image.info['duration']
        assert ms==sum(durations) and image.size==(640,480)
    (OUT/'camera-shake-special.pad').write_text(replay_text(pads[:end]))
    return dict(first_tick=start,last_tick=end,playback_ms=sum(durations),gif_sha256=digest(gif))


def main():
    assert digest(ELF)==PIN
    viewer=PACKAGE/'ss6-viewer';sha=digest(viewer)
    with tempfile.TemporaryDirectory(prefix='ss6-camera-art-') as folder:
        tmp=Path(folder)
        hit,pads=validate_match(tmp,0,'hit',viewer)
        print('P1 hit',flush=True)
        miss,_=validate_match(tmp,1,'whiff',viewer)
        print('P2 whiff',flush=True)
        clip=record(tmp,pads,viewer,sha,hit['request_ticks'])
    assert digest(viewer)==sha
    report=dict(status='passed',viewer_sha256=sha,source_sha256=PIN,traces=[hit,miss],demo=clip,
                scope='Original ACT requests and 141528,146460,1463d0,146870 camera. Real gameplay actor coordinates and camera-command inputs. All pixels of the 640x448 playable scene at selected ticks compared against software rasters of the original background, character and effect packets. Demo is captured from the packaged 640x480 window. No hardware GS capture.')
    (OUT/'camera-shake-scene-validation.json').write_text(json.dumps(report,indent=2)+'\n')
    print('Verified',sum(len(s['sampled_compositions']) for s in (hit,miss)),'complete scenes and',clip,flush=True)


if __name__=='__main__':main()
