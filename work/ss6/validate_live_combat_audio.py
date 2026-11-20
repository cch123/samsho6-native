#!/usr/bin/env python3
"""Compare actual SDL keyboard-match audio against the identical normalized-pad replay."""
import argparse
from array import array
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import wave
from validate_versus_heavy import ASSETS, BUILD, DUMMY, HERE, ROOT, OUTPUT, digest
from validate_shin_specials import objects

RATE = 48000
BYTES_PER_TICK = RATE // 60 * 4
VIEWER = OUTPUT / 'native-viewer/ss6-viewer'
def run(args, **kwargs):
    return subprocess.run(args, check=True, timeout=120, **kwargs)
def audio(path, ticks):
    with wave.open(str(path), 'rb') as source:
        assert source.getparams()[:4] == (2, 2, RATE, ticks*800)
        return source.readframes(source.getnframes())
def encode(rows):
    return ''.join(f'{n} {a} {b}\n' for n,a,b in rows)
def write_wave(path,raw):
    with wave.open(str(path),'wb') as out:
        out.setparams((2,2,RATE,0,'NONE','not compressed'))
        out.writeframes(raw)
def stereo(raw):
    samples=array('h');samples.frombytes(raw)
    if sys.byteorder!='little':samples.byteswap()
    return samples

def verify_music_during_hitstop(signals):
    # The game's dry action sounds are centered. Away from SPU clipping,
    # subtracting the channels removes them and isolates the stereo music.
    idle=stereo(signals['idle'])
    differences=[a-b for a,b in zip(idle[::2],idle[1::2])]
    assert sum(d!=0 for d in differences)>len(differences)//2
    matched={}
    for name in ('jump-light-hit','jump-light-guard'):
        current=stereo(signals[name]);usable=0
        for i,(a,b) in enumerate(zip(current[::2],current[1::2])):
            if max(abs(a),abs(b),abs(idle[i*2]),abs(idle[i*2+1]))>32760:continue
            assert abs((a-b)-differences[i])<=2,(name,i)
            usable+=1
        assert usable>len(differences)*0.95
        matched[name]=usable
    return matched

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def verify_zan_clip(tmp, exe, record):
    # The warm-up ends mid-charge. Release, direction changes, and the second
    # A+B press all go through the same SDL event loop used for local play.
    prior=[(500,0,0),(75,128,0),(5,0,0),(100,768,0)]
    live=[(77,768,0),(8,0,0),(1,32,0),(1,160,0),(1,896,0),(330,0,0)]
    options=['--p1-spirit','zan']
    warm=sum(n for n,_,_ in prior)
    ticks=sum(n for n,_,_ in live)
    start,controls,reference=(tmp/name for name in ('zan-start.pad','zan-live.pad','zan-full.pad'))
    start.write_text(encode(prior))
    controls.write_text(encode(live))
    reference.write_text(encode(prior+live))
    per_tick=[(1,a,b) for n,a,b in live for _ in range(n)]
    trace=run([BUILD/'ss6-match-replay',ASSETS,'--mode','versus',*options,'--shin-fields'],
              input=encode(prior+per_tick),text=True,capture_output=True)
    rows=[line.split() for line in trace.stdout.splitlines()][len(prior)-1:]
    assert list(map(int,(rows[0][4],rows[0][39],rows[0][19])))==[46,0,200]
    def first(predicate):
        return next(int(row[0]) for row in rows if predicate(row))
    full=first(lambda row:int(row[39])==1)
    move=first(lambda row:int(row[4])==78 and int(row[5])==625)
    hit=first(lambda row:int(row[19])<200)
    def sword(row):
        return [weapon[0] for weapon in objects(row)[1][1]]
    launch=first(lambda row:sword(row)==[466])
    land=first(lambda row:sword(row)==[467])
    assert warm<full<move<hit==launch<land<warm+ticks
    assert all(sword(row)==([467] if int(row[0])>=land else [466] if int(row[0])>=launch else []) for row in rows)
    assert (int(rows[-1][19]),int(rows[-1][10]),int(rows[-1][11]))==(148,1,0)
    reference_wav,pcm,video=(tmp/name for name in ('zan-reference.wav','zan-live.pcm','zan-frames.rgba'))
    run([VIEWER,'--mode','versus',*options,'--match-replay',reference,'--audio-out',reference_wav],env=DUMMY)
    run([exe,ASSETS,start,controls,pcm,*options,*([video] if record else [])],env=DUMMY)
    expected=audio(reference_wav,warm+ticks)[warm*BYTES_PER_TICK:]
    heard=pcm.read_bytes()
    assert heard==expected
    channels=stereo(heard)
    assert max(map(abs,channels))>0 and any(l!=r for l,r in zip(channels[::2],channels[1::2]))
    report=dict(name='zan-weapon-hit',live_ticks=ticks,warm_ticks=warm,sample_rate=RATE,
                stereo_frames=len(heard)//4,pcm_sha256=sha(heard),defender_hp=148,
                match_ticks=dict(full_rage=full,weapon_flip=move,hit=hit,sword_flying=launch,sword_landed=land))
    if record:
        export_clip(tmp,'zan-weapon-hit.mp4',report,expected,video,pcm,options,prior,per_tick,
                    [warm+1,full,move,hit,(launch+land)//2,land,warm+ticks])
    return report

def export_clip(tmp,filename,report,expected,video,pcm,options,prior,per_tick,visible_ticks):
    warm=sum(n for n,_,_ in prior);ticks=len(per_tick);reference=tmp/'capture.pad'
    assert video.stat().st_size==ticks*640*480*4
    reference_frame=tmp/'frame.bmp'
    with video.open('rb') as rendered:
        for tick in visible_ticks:
            reference.write_text(encode(prior+per_tick[:tick-warm]))
            run([VIEWER,'--mode','versus',*options,'--match-replay',reference,'--snapshot',reference_frame],env=DUMMY)
            expected_frame=run(['ffmpeg','-v','error','-i',reference_frame,'-f','rawvideo',
                                '-pix_fmt','rgba','-'],capture_output=True).stdout
            rendered.seek((tick-warm-1)*640*480*4)
            assert rendered.read(640*480*4)==expected_frame,('video tick',tick)
    clip=tmp/'capture.mp4'
    run(['ffmpeg','-v','error','-y','-f','rawvideo','-pix_fmt','rgba','-video_size','640x480',
         '-framerate','60','-i',video,'-f','s16le','-ar',str(RATE),'-ac','2','-i',pcm,
         '-c:v','libx264','-crf','16','-preset','fast','-pix_fmt','yuv420p',
         '-c:a','alac','-movflags','+faststart',clip])
    # Check the movie's decoded lossless track, including its final partial
    # packet. Comparing the pre-encode buffer alone cannot catch a mux error.
    decoded=run(['ffmpeg','-v','error','-i',clip,'-map','0:a:0','-f','s16le','-'],capture_output=True).stdout
    assert decoded==expected
    info=json.loads(run(['ffprobe','-v','error','-select_streams','v:0','-show_entries',
                         'stream=width,height,nb_frames,avg_frame_rate','-of','json',clip],capture_output=True).stdout)
    assert info['streams']==[dict(width=640,height=480,avg_frame_rate='60/1',nb_frames=str(ticks))]
    target=OUTPUT/filename
    target.write_bytes(clip.read_bytes())
    report.update(clip=target.name,mp4_sha256=digest(target),mp4_decoded_pcm_sha256=sha(decoded),
                  exact_sdl_window_ticks=visible_ticks)

def verify_issen_clip(tmp,exe,spirit):
    if spirit=='ten':
        prior=[(500,0,0)]+[(65,0,64),(5,0,0),(1,0,1024),(88,0,0)]*3+[(75,64,128),(8,0,0)]
        live=[(1,1792,0),(130,0,0),(130,128,64),(10,0,0),(1,1792,0),(270,0,0)]
        hit,life=1333,149
        landmarks=[1061,1072,1114,1332,1333,1348,1500,1517]
    else:
        from validate_zero_specials import scenario
        prior,live=scenario(0,'hit')
        hit,life=4287,107
        landmarks=[4240,4252,4267,4278,4286,4287,4288,4360,4471]
    warm=sum(n for n,_,_ in prior);ticks=sum(n for n,_,_ in live)
    per_tick=[(1,a,b) for n,a,b in live for _ in range(n)]
    options=['--p1-spirit',spirit]
    start,controls,full,wav,pcm,video=(tmp/name for name in ('setup','inputs','full.pad','live.wav','live.pcm','live.rgba'))
    for path,seq in ((start,prior),(controls,live),(full,prior+live)):path.write_text(encode(seq))
    trace=run([BUILD/'ss6-match-replay',ASSETS,'--mode','versus',*options,'--sound-fields'],
              input=encode(prior+per_tick),text=True,capture_output=True)
    rows={int(row[0]):row for line in trace.stdout.splitlines() if (row:=list(map(float,line.split())))}
    music=[]
    for tick,row in rows.items():
        if tick<=warm:continue
        music += [(tick,list(map(int,row[j:j+3]))) for j in range(26,len(row),3) if row[j] in (5,6,7)]
    assert music==[(hit,[7,0,0]),(hit+1,[5,0,5]),(hit+184,[6,0,0x3200])],music
    assert rows[hit-1][19]==200 and rows[hit][19]==life
    run([VIEWER,'--mode','versus',*options,'--match-replay',full,'--audio-out',wav],env=DUMMY)
    run([exe,ASSETS,start,controls,pcm,*options,video],env=DUMMY)
    expected=audio(wav,warm+ticks)[warm*BYTES_PER_TICK:]
    assert pcm.read_bytes()==expected and any(expected)
    report=dict(name=spirit+'-issen',live_ticks=ticks,warm_ticks=warm,pcm_sha256=sha(expected),
                defender_hp=life,original_stage_music_requests=music)
    export_clip(tmp,spirit+'-issen.mp4',report,expected,video,pcm,options,prior,per_tick,
                [*landmarks,warm+ticks])
    return report

def main():
    args=argparse.ArgumentParser()
    args.add_argument('--clip',action='store_true',help='Record the jumping light hit as an audiovisual MP4.')
    args.add_argument('--zan-clip',action='store_true',help='Record Zan charging, hitting and disarming the defender.')
    args.add_argument('--ten-clip',action='store_true',help='Record the Ten explosion and Issen hit in live play.')
    args.add_argument('--zero-clip',action='store_true',help='Record a Zero concentration and Issen hit in live play.')
    options=args.parse_args()
    clip=options.clip
    with tempfile.TemporaryDirectory() as folder:
        tmp=Path(folder)
        flags=shlex.split(subprocess.check_output(['pkg-config','--cflags','--libs','sdl3'],text=True))
        exe=tmp/'audio-loop'
        run(['c++','-std=c++20','-ffp-contract=off','-O2','-I',ROOT/'src',HERE/'sdl_audio_input_test.cpp',BUILD/'libss6-runtime.a',*flags,'-o',exe])
        assert digest(VIEWER)==digest(BUILD/'ss6-viewer')
        start=tmp/'start.pad'
        neutral=[(500,0,0)]
        leap=[(1,144,0),(29,0,0),(1,256,0),(89,0,0)]
        guard=[(1,144,0),(24,0,0),(7,0,128),(1,256,128),(87,0,128)]
        slash=[(1,1024,0),(83,0,0)]
        cases=[('idle',neutral,[(120,0,0)],200,0),
               ('jump-light-hit',neutral,leap,191,0),
               ('jump-light-guard',neutral,guard,200,1),
               ('heavy-whiff',neutral+[(50,64,128),(1,0,0)],slash,200,0),
               ('heavy-hit',neutral+[(42,128,0),(1,0,0)],slash,162,0),
               # The live device starts mid-hit. Its first samples must continue the old sound.
               ('resume-hit-tail',neutral+leap[:3]+[(15,0,0)],[(74,0,0)],191,0)]
        menu=[tuple(map(int,line.split())) for line in (OUTPUT/'console-versus-rematch.replay').read_text().splitlines()]
        cases.extend([
            ('before-first-cue',[],[(60,0,0)],200,0),
            ('round-one-announcer',[(210,0,0)],[(220,0,0)],200,0),
            ('menu-confirm-rematch',menu+[(1,0,0)],[(1,1024,0),(100,0,0)],200,0),
        ])
        reports=[]
        signals={}
        for name,prior,live,hp,guards in cases:
            start.write_text(encode(prior))
            control=tmp/'live.pad';control.write_text(encode(live))
            reference=tmp/'reference.pad';reference.write_text(encode(prior+live))
            vs=run([BUILD/'ss6-match-replay',ASSETS,'--mode','versus'],input=reference.read_text(),capture_output=True,text=True)
            last=vs.stdout.splitlines()[-1].split()
            assert (int(last[19]),int(last[11]))==(hp,guards),(name,last)
            wav,pcm=tmp/'reference.wav',tmp/'keyboard.pcm'
            headless=dict(DUMMY,SDL_AUDIO_DRIVER='ss6-test-no-device',SDL_VIDEO_DRIVER='ss6-test-no-video')
            run([VIEWER,'--mode','versus','--match-replay',reference,'--audio-out',wav],env=headless)
            n=sum(r[0] for r in live);warm=sum(r[0] for r in prior)
            expected=audio(wav,n+warm)[BYTES_PER_TICK*warm:]
            capture=clip and name=='jump-light-hit'
            footage=tmp/'frames.rgba'
            run([exe,ASSETS,start,control,pcm,*([footage] if capture else [])],env=DUMMY)
            actual=pcm.read_bytes()
            assert actual==expected,(name,len(actual),len(expected))
            channel=stereo(actual)
            stereo_difference=sum(a!=b for a,b in zip(channel[::2],channel[1::2]))
            peak=max(map(abs,channel));signals[name]=actual
            assert (peak==0)==(name=='before-first-cue'),(name,peak)
            reports.append(dict(name=name,live_ticks=n,peak=peak,different_stereo_frames=stereo_difference,defender_hp=hp,guards=guards,pcm_sha256=sha(actual)))
            if capture:
                assert footage.stat().st_size==n*640*480*4
                excerpt=tmp/'audio.wav';write_wave(excerpt,actual)
                movie=tmp/'hit.mp4'
                run(['ffmpeg','-v','error','-y','-f','rawvideo','-pix_fmt','rgba','-video_size','640x480',
                     '-framerate','60','-i',footage,'-i',excerpt,'-c:v','libx264','-crf','16','-preset','fast',
                     '-pix_fmt','yuv420p','-c:a','aac','-b:a','192k','-movflags','+faststart',movie])
                (OUTPUT/'jump-light-hit.mp4').write_bytes(movie.read_bytes())
        music_matches=verify_music_during_hitstop(signals)
        assert len({reports[i]['pcm_sha256'] for i in (1,2,3,4)})==4
        assert signals['resume-hit-tail']==signals['jump-light-hit'][-74*BYTES_PER_TICK:]
        assert any(signals['resume-hit-tail'][:BYTES_PER_TICK])
        # Pause on frame 12, silently single-step 13, resume 16, fresh session 31.
        # R must discard the old hit tail and restart the original opening voices.
        start.write_text(encode(neutral+leap[:3]+[(15,0,0)]))
        live=tmp/'transport.pad';live.write_text('60 0 0\n')
        run([exe,ASSETS,start,live,pcm,'--transport'],env=DUMMY)
        fresh=tmp/'fresh.wav'
        run([VIEWER,'--mode','versus','--updates','29','--audio-out',fresh],env=DUMMY)
        old=signals['resume-hit-tail'];block=BYTES_PER_TICK
        assert pcm.read_bytes()==old[:12*block]+old[13*block:28*block]+audio(fresh,29)
        # Empty captures must still be valid WAVs; a malformed replay must
        # never truncate a previously published recording.
        empty=tmp/'empty.wav'
        run([VIEWER,'--mode','versus','--audio-out',empty],env=DUMMY)
        assert audio(empty,0)==b'' and empty.stat().st_size==44
        before=empty.read_bytes()
        for invalid in ['1 0 INVALID\n','+','99999999999999999999999','1 0']:
            start.write_text('2 0 0\n'+invalid)
            bad=subprocess.run([VIEWER,'--mode','versus','--match-replay',start,'--audio-out',empty],env=DUMMY,capture_output=True)
            assert bad.returncode and empty.read_bytes()==before and not list(tmp.glob("empty.wav.part.*"))
        reports.append(verify_zan_clip(tmp,exe,options.zan_clip))
        if options.ten_clip:reports.append(verify_issen_clip(tmp,exe,'ten'))
        if options.zero_clip:reports.append(verify_issen_clip(tmp,exe,'zero'))
        report=dict(status='passed',viewer_sha256=digest(VIEWER),bank_sha256=digest(ASSETS/'combat_sound_bank.bin'),
                    sample_rate=RATE,stereo=True,cases=reports,pause_single_step_restart='passed',stereo_music_during_hitstop=music_matches,
                    scope='Keyboard events through the packaged source event loop and a dummy SDL playback device; independent normalized replay and exact PCM. No PS2 hardware capture.')
        (OUTPUT/'live-combat-audio-validation.json').write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps(reports,indent=2))
if __name__=='__main__':main()
