#!/usr/bin/env python3
"""Record a real Mikiri decoy hit unlocking Tenha Fujin Zan on the packaged player."""
from itertools import groupby
import json
from pathlib import Path
import re
import shlex
import struct
import subprocess
import tempfile

from validate_ken_specials import sequence
from validate_live_combat_audio import (
    ASSETS, BUILD, BYTES_PER_TICK, DUMMY, HERE, OUTPUT, RATE, ROOT, VIEWER,
    audio, digest, encode, export_clip, run, sha, stereo,
)


def blocks(rows):
    return [(sum(1 for _ in group),a,b) for (a,b),group in groupby((a,b) for _,a,b in rows)]


def trace(inputs,flag):
    out=run([BUILD/'ss6-match-replay',ASSETS,'--mode','versus','--p1-spirit','ken',flag],
            input=encode(inputs),text=True,capture_output=True)
    return {int(r[0]):r for line in out.stdout.splitlines() if (r:=line.split())}


def stage_colors(folder,inputs,tick):
    replay=folder/'stage.pad';replay.write_text(encode(blocks(inputs[:tick])))
    stage=folder/'stage.rgba'
    run([VIEWER,'--mode','versus','--p1-spirit','ken','--match-replay',replay,'--dump-stage',stage],env=DUMMY)
    data=stage.read_bytes();assert struct.unpack_from('<II',data)==(640,448)
    red,green,blue=(data[8+i::4] for i in range(3))
    count=sum(r!=g or r!=b for r,g,b in zip(red,green,blue))
    offset=8+4*(100*640+90)
    return count,list(data[offset:offset+3])


def main():
    options=['--p1-spirit','ken'];viewer_hash=digest(VIEWER)
    assert viewer_hash==digest(BUILD/'ss6-viewer')
    setup,commands=sequence(0,79,'mikiri')
    inputs=[(1,a,b) for n,a,b in setup+commands for _ in range(n)]
    meters=trace(inputs,'--ken-fields');mikiri=trace(inputs,'--mikiri-fields')
    image_hit=next(t for t,row in meters.items() if int(row[26])>8192)
    assert (int(meters[image_hit][9]),int(meters[image_hit-1][26]),int(meters[image_hit][26]))==(46,8192,16640)
    white=[t for t,r in mikiri.items() if int(r[23])];assert white==list(range(image_hit+1,image_hit+4))
    launch=next(t for t,r in meters.items() if int(r[4])==79)
    recovered=next(t for t in range(launch+1,len(inputs)+1) if int(meters[t][4])==0)
    hits=[t for t in range(launch,recovered) if int(meters[t][19])<int(meters[t-1][19])]
    assert len(hits)==10 and int(meters[recovered][19])==153
    assert int(meters[recovered-1][26])==16640 and int(meters[recovered][26])==0
    warm=image_hit-45;end=recovered+24;live=inputs[warm:end];prior=blocks(inputs[:warm])
    with tempfile.TemporaryDirectory() as temp:
        folder=Path(temp);exe=folder/'audio-loop'
        flags=shlex.split(subprocess.check_output(['pkg-config','--cflags','--libs','sdl3'],text=True))
        run(['c++','-std=c++20','-ffp-contract=off','-O2','-I',ROOT/'src',HERE/'sdl_audio_input_test.cpp',BUILD/'libss6-runtime.a',*flags,'-o',exe])
        start,keys,full,wav,video,pcm=[folder/name for name in ('warm.pad','keys.pad','full.pad','mix.wav','video.rgba','mix.s16')]
        for path,rows in ((start,prior),(keys,blocks(live)),(full,blocks(inputs[:end]))):path.write_text(encode(rows))
        run([VIEWER,'--mode','versus',*options,'--match-replay',full,'--audio-out',wav],env=DUMMY)
        run([exe,ASSETS,start,keys,pcm,*options,video],env=DUMMY)
        heard=pcm.read_bytes();expected=audio(wav,end)[BYTES_PER_TICK*warm:]
        assert expected==heard and any(heard)
        samples=stereo(heard);assert any(l!=r for l,r in zip(samples[::2],samples[1::2]))
        before=image_hit-1;gray=white[-1]+1;focus=launch+1
        stage={tick:stage_colors(folder,inputs,tick) for tick in (before,gray,focus)}
        assert stage[before][0]>200000 and stage[gray][0]==stage[focus][0]==0
        frame_bytes=640*480*4;all_white=b'\xff'*frame_bytes
        with video.open('rb') as src:
            for tick in (image_hit,*white,gray):
                src.seek((tick-warm-1)*frame_bytes)
                assert (src.read(frame_bytes)==all_white)==(tick in white)
            # This stage texel is clear of both players and the HUD on these updates.
            for tick,(count,rgb) in stage.items():
                src.seek((tick-warm-1)*frame_bytes+4*(100*640+90));assert list(src.read(3))==rgb
        report=dict(status='passed',viewer_sha256=viewer_hash,name='見切り → 天覇封神斬',
                    first_update=warm+1,last_update=end,frames=len(live),seconds=len(live)/60,
                    image_hit=image_hit,white_updates=white,stage_non_grayscale_pixel_counts={t:c for t,(c,_) in stage.items()},
                    afterimage_reserve=[32,65],ken_life=46,special_start=launch,hit_updates=hits,
                    defender_life_after_hits=153,special_recovered=recovered,sample_rate=RATE,
                    stereo_sample_frames=len(expected)//4,pcm_sha256=sha(expected))
        landmarks=sorted({warm+1,before,image_hit,*white,gray,launch,focus,hits[0],hits[4],hits[-1],recovered-1,recovered,end})
        filename='ken-mikiri-secret.mp4'
        export_clip(folder,filename,report,expected,video,pcm,options,prior,live,landmarks)
        # Standard H.264 4:2:0 encoding is lossy. Compare all encoded frames
        # in that colorspace as well as the uncompressed SDL landmarks above.
        stats=folder/'ssim.txt'
        run(['ffmpeg','-v','error','-f','rawvideo','-pix_fmt','rgba','-video_size','640x480','-framerate','60','-i',video,
             '-i',OUTPUT/filename,'-filter_complex',f'[0:v]format=yuv420p[ref];[1:v][ref]ssim=stats_file={stats}',
             '-an','-f','null','-'])
        scores=[float(x) for x in re.findall(r'All:([0-9.]+)',stats.read_text())]
        assert len(scores)==len(live) and min(scores)>0.96,(len(scores),min(scores))
        report['decoded_video_ssim_minimum']=min(scores);report['decoded_video_ssim_average']=sum(scores)/len(scores)
        assert digest(VIEWER)==viewer_hash
        (OUTPUT/'ken-secret-video-validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
        print(json.dumps(report,ensure_ascii=False))


if __name__=='__main__':main()
