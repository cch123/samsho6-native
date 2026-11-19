#!/usr/bin/env python3
"""Verify the second stage's packaged stereo mix through stage select, two battles and CONTINUE."""
import argparse
from hashlib import sha256
from itertools import groupby
import json
import os
from pathlib import Path
import subprocess
import tempfile
import wave

import numpy as np
from validate_battle_sound import frame_events
from validate_combat_music import capture, PITCH
from validate_nakoruru_round_finish import combat_pads
from validate_selected_combat import BUILD, OUT
from extract_versus_quotes import ORIGINAL


def trace(replay,assets,pads,field):
    events=''.join(f'1 {a} {b}\n' for a,b in pads)
    result=subprocess.run([replay,assets,'--mode','select',field],input=events,text=True,capture_output=True)
    assert not result.returncode,(field,len(result.stdout.splitlines()),result.stderr)
    return [s.split() for s in result.stdout.splitlines()]


def audio_export(viewer,assets,pads,out):
    subprocess.run([viewer,'--assets',assets,'--mode','select','--match-replay',pads,'--audio-out',out],
                   env=dict(os.environ,SDL_VIDEODRIVER='dummy',SDL_AUDIODRIVER='dummy'),check=True,stdout=subprocess.DEVNULL)
    with wave.open(str(out),'rb') as snd:
        assert snd.getparams()[:3]==(2,2,48000)
        return np.frombuffer(snd.readframes(snd.getnframes()),dtype='<i2').reshape(-1,2)


def ceiling(a,b):return -((-a)//b)


def source_gain(pcm,weights,t):
    pos=t*PITCH;idx=pos//4096;phase=(pos//16)%256
    gain=np.minimum(32767,16383+4*((t-3)//32768))
    gain=np.where(t==0,14336,np.where(t==1,28672,np.where(t==2,32767,gain)))
    sides=[]
    for samples in pcm:
        value=sum(weights[phase,k]*samples[(idx+k)%len(samples)]//32768 for k in range(4))
        sides.append((value*gain//32768)*(2*0x3200)//32768)
    return np.stack(sides,axis=1)


def possible_pre_master(values):
    # Hardware clips voices first, then applies master 0x7ffe with a floor.
    # At the two extrema the pre-clamp dry sum can extend beyond 16 bits.
    low=ceiling(values*32768,32766);high=ceiling((values+1)*32768,32766)-1
    low=np.where(values==-32766,-(1<<30),low)
    high=np.where(values==32765,1<<30,high)
    return low,high


def main(args):
    viewer,replay,assets=args.viewer,args.replay,args.assets
    binary={p.name:sha256(p.read_bytes()).hexdigest() for p in (viewer,replay)}
    controls=combat_pads((0,0),0,'stand')
    # The menu accepts a new stage movement after its 30-frame slide.
    controls[339:339]=[(0,128)]+[(0,0)]*29
    menu=trace(replay,assets,controls,'--vs-menu-fields')
    first=next(i for i,r in enumerate(menu) if r[24]=='1')
    controls=controls[:first+1]+[(0,0)]*45+[(32,0),(0,0),(1024,0)]+[(0,0)]*650
    picks=trace(replay,assets,controls,'--select-fields')
    assert picks[389][45:48]==['1','1','1']
    for r in picks:
        if r[24]=='0':assert r[52]=='1' and r[49]=='0'
    assert picks[-1][23:25]==['2','0'] and picks[-1][1]=='4'
    assert [int(menu[first][j]) for j in (12,22)]==[2,0]
    rows=trace(replay,assets,controls,'--sound-fields')
    music=[(t,e) for t,row in enumerate(rows,1) for e in frame_events(row) if e[0] in (5,6,7,8)]
    preloads=[(t,e) for t,e in music if e[0]==5];starts=[t for t,e in music if e[0]==6]
    assert len(preloads)==len(starts)==2 and all(e==(5,0,6) for t,e in preloads)
    assert all(rows[t-1][1]=='4' for t in starts) and all(e[2]==0x3200 for t,e in music if e[0]==6)
    assert any(e==(8,0x3200,2) for t,e in music if t<preloads[0][0])
    assert any(e==(8,0x3200,24) for t,e in music if starts[0]<t<preloads[1][0])
    # The first ordinary round end does not stop the stage; the second one
    # does. Each new set releases its own preload exactly once.
    stops=[next((t for t,e in music if t>start and e[0] in (5,7,8)),len(rows)+1) for start in starts]
    for (pt,_),start in zip(preloads,starts):assert start-pt>18
    assert rows[stops[0]-1][1]=='5' and rows[stops[0]-1][12]=='2' and stops[1]==len(rows)+1
    with tempfile.TemporaryDirectory() as td:
        tmp=Path(td);pads=tmp/'input';muted=tmp/'assets';muted.mkdir()
        pads.write_text(''.join(f'{sum(1 for _ in g)} {a} {b}\n' for (a,b),g in groupby(map(tuple,controls))))
        # Preserve every gameplay event and every other sound. The two
        # check-only silent BGM06 files isolate the real viewer's pre-master
        # contribution even when a strike/voice overlaps the music.
        for asset in assets.iterdir():
            dest=muted/asset.name
            if asset.name in ('bgm06_l.vb','bgm06_r.vb'):dest.write_bytes(bytes(asset.stat().st_size))
            else:dest.symlink_to(asset.resolve())
        mixed=audio_export(viewer,assets,pads,tmp/'actual.wav')
        no_stage=audio_export(viewer,muted,pads,tmp/'no_stage.wav')
        assert len(mixed)==len(no_stage)==len(rows)*800
        sides,source,table=capture(6,assets);pcm=[np.frombuffer(s,dtype='<i2') for s in sides]
        weights=np.asarray(table,dtype=np.int64);last=0;quiet=active=0
        for start,stop in zip(starts,stops):
            lo=(start-1)*800;hi=(stop-1)*800
            assert np.array_equal(mixed[last:lo],no_stage[last:lo])
            for ix in range(lo,hi,32768):
                end=min(ix+32768,hi)
                baseline=no_stage[ix:end].astype(np.int64)
                assert np.array_equal(baseline[:,0],baseline[:,1])
                wet=mixed[ix:end].astype(np.int64)
                stage=source_gain(pcm,weights,np.arange(ix-lo,end-lo,dtype=np.int64))
                drylow,dryhigh=possible_pre_master(baseline[:,0]);wetlow,wethigh=possible_pre_master(wet)
                lo_bound=np.maximum(drylow,(wetlow-stage).max(axis=1))
                hi_bound=np.minimum(dryhigh,(wethigh-stage).min(axis=1))
                if np.any(lo_bound>hi_bound):
                    j=int(np.flatnonzero(lo_bound>hi_bound)[0]);raise AssertionError((start,ix+j,wet[j],baseline[j],stage[j]))
                quiet+=int(np.count_nonzero((baseline[:,0]==0)&(stage[:,0]!=0)))
                active+=len(wet)
            last=hi
        assert np.array_equal(mixed[last:],no_stage[last:]) and quiet>800*60
        wave_sha=sha256(mixed.tobytes()).hexdigest()
    assert binary=={p.name:sha256(p.read_bytes()).hexdigest() for p in (viewer,replay)}
    report=dict(status='passed',source_elf_sha256=ORIGINAL,binaries=binary,pad_frames=len(rows),stage=1,
                menu_tick=first+1,stage_preloads=[t for t,_ in preloads],stage_starts=starts,stage_stops=stops,
                stage_active_stereo_frames=active,checked_stereo_frames=len(mixed),audible_stage_frames_with_silent_dry_mix=quiet,
                pcm_sha256=wave_sha,original_channels=[source[s] for s in 'LR'],ordered_music=music,
                scope='Actual packaged --mode select, factory soundtrack, both human pads, stage 1, two P1 heavy-attack wins then CONTINUE on the same stage. Every stereo sample is checked against the original BGM06 CD/DMA output and SPU2 mix equation with the same observed dry SFX/voices. Original pre-master dry sums are bounded by the exact integer master gain and clipping.')
    (OUT/'selected-stage1-music-validation.json').write_text(json.dumps(report,indent=2)+'\n')
    print({k:report[k] for k in ('pad_frames','stage_preloads','stage_starts','stage_stops','checked_stereo_frames','pcm_sha256')})


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--viewer',type=Path,default=OUT/'native-viewer/ss6-viewer')
    ap.add_argument('--assets',type=Path,default=OUT/'native-viewer/assets');ap.add_argument('--replay',type=Path,default=BUILD/'ss6-match-replay')
    main(ap.parse_args())
