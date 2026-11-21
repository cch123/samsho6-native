#!/usr/bin/env python3
"""Play a whole ARCADE MODE run with the viewer's audio routing and check every scene's sound.

The route is validate_arcade_session.py's (title -> select -> opening -> map -> walk-in ->
fights -> dialogue -> CONTINUE -> challenger -> VS result -> pre-final -> ending -> staff roll
-> GAME OVER -> unlock notice -> ranking -> title), recorded with ss6-match-replay and replayed
through ss6-scene-audio-probe, which routes the same requests to the same CombatAudio as the
viewer (src/audio_routing.cpp) and prints, per mixer frame, the requests and every keyed
physical voice with a hash of the sample it reads and its peak output.

Each scene request is resolved independently from the disc (inspect_iso.py, no native tables):
  Sound 1e7b70(g, t)     BVOICE2[bank of group g + 1] tone t, the bank tracked from the
                         1e79c8 / 212dd8 loads and the battle's player banks; SE voices 14..21
  Voice 1e7d60(0x31, t)  NAL[language][t or t - 42] (21358c names: the fighter's last two
                         BVOICE1 lines); streamed voices 2..4 after the 213660 queue stages
  Music 1e7c00(n, f)     BGMd/BGMnn_L.VB and _R.VB (214210 directory rule) on voices 0 / 1,
                         decoded prefix; 213ff0 track 23 is BVOICE1[49] tone 12 (212d80)
and must be read by a keyed voice that outputs non-zero PCM within the original latency.
The documented scene tracks (docs/mode-arcade-*.txt) must each be requested in their scene.
The 50 ending scripts are also played through the GALLERY routing (selectEndingSounds: script
1e7b70 into bank 49 / the common bank, object 1e8298 commands, the ending and staff-roll music)."""
import argparse
from collections import Counter,defaultdict
import json
import struct
import subprocess
import tempfile
from pathlib import Path

from extract_combat_sound_bank import ISO
from extract_stage_music import directory
from inspect_iso import Iso
from validate_arcade_session import ROOT,OUT,S,play

NAMES={v:k for k,v in S.items()}
SCENE_KINDS=('Music','MusicStop','Sound','Voice','ObjectSound','LoadBank','EffectsStop')
BATTLE_KINDS=('Sample','Voice','Stop','StopGroup','ResidentJingle','MusicPreload','MusicStart','MusicStop','MusicPlay',
              'BindPlayers','MusicRequest','LoadBank')
# Scene music of the original entries (docs/mode-arcade-flow.txt, -talk, -results, -demos).
SCENE_MUSIC={'map':{0x16},'winquote':{0x19},'result':{0x19},'cont':{0x1a},'gameover':{0x1b},'prefinal':{0x14},
             'dialogue':{0x11,0x12,0x13},'ending':{3,4}}
VOICE_LATENCY=4      # 213378 queue: IOP ready, SIF transfer, completion (213660 one stage a visit)
ONSET=8           # frames a keyed sample may stay silent before its first audible block
MUSIC_LATENCY=60     # 213ff0 request machine plus the IRX's two initial reads (CombatMusic: 18 visits)


def fnv(data):
    h=1469598103934665603
    for b in data:h=((h^b)*1099511628211)&0xffffffffffffffff
    return h


def decode(data):
    out=[];p1=p2=0
    for block in range(0,len(data),16):
        header=data[block]
        a,b=((0,0),(60,0),(115,-52),(98,-55),(122,-60))[header>>4]
        for byte in data[block+2:block+16]:
            for nib in (byte%16,byte//16):
                v=((nib-16 if nib>=8 else nib)*4096>>(header%16))+(a*p1+b*p2+32)//64
                p2,p1=p1,max(-32768,min(32767,v));out.append(p1)
    return out


class Disc:
    """Sample identities read straight from the Japanese disc."""
    def __init__(self):
        self.iso=Iso(ISO);self.cache={}

    def entry(self,name,index,stride,tone):
        key=(name,index,tone)
        if key not in self.cache:
            header=self.iso.read(f'/VOICE/{name}.MSH')[index*stride:(index+1)*stride]
            sector,count,size,_=struct.unpack_from('<4I',header)
            if tone>=count:self.cache[key]=None
            else:
                word,offset=struct.unpack_from('<2I',header,16+8*tone)
                length=word>>16 if name=='BVOICE2' else word
                body=self.iso.by_path[f'/VOICE/{name}.MSB']
                self.cache[key]=fnv(self.iso.read_at((body['lba']+sector)*self.iso.block+offset,length))
        return self.cache[key]

    def count(self,name,index,stride):
        return struct.unpack_from('<4I',self.iso.read(f'/VOICE/{name}.MSH')[index*stride:(index+1)*stride])[1]

    def effect(self,bank,tone):return self.entry('BVOICE2',bank,0x250,tone)

    def music(self,variant,track):
        n=directory(track,variant)
        return [fnv(struct.pack('<112h',*decode(self.iso.read(f'/BGM{n}/BGM{track:02}_{s}.VB')[:64]))) for s in 'LR']

    def voice(self,character,tone,language,groups):
        """213378: (expected identity, channel set) or (None, reason)."""
        if character==49:
            if 2<=tone<44 or 89<=tone<94 or tone==100:
                c=42 if tone==100 else tone-45 if tone>=89 else tone-2
                if c not in groups[1:]:return None,'name of a fighter whose voices are not loaded'
                return self.entry('BVOICE1',c,0x110,self.count('BVOICE1',c,0x110)-2+language),{2,3}
            return self.entry('NAL',language,0x210,tone if tone<44 else tone-42),{4}
        if character==50:return self.entry('BVOICE1',49,0x110,tone),set(range(14,22))
        if character not in groups[1:]:return None,'voice bank of the character not loaded'
        if character==29 and tone<8:return self.entry('BVOICE1',49,0x110,tone+4),set(range(14,22))
        return self.entry('BVOICE1',character,0x110,tone-8 if character==29 else tone),{2,3}


def parse(text):
    frames=[]
    for line in text.splitlines():
        if not line.startswith('F '):continue
        head,_,chans=line.partition(' |')
        f=head.split()
        reqs=[tuple(int(x) for x in t.split(',')) for t in f[4:]]
        voices={}
        for t in chans.split():
            i,h,peak=t.split(':');voices[int(i)]=(int(h,16),int(peak))
        frames.append(dict(tick=int(f[1]),scene=f[2],kind=f[3],requests=reqs,voices=voices))
    return frames


def heard(frames,start,stop,identity,channels):
    """First frame in [start, stop) keying a voice of `channels` on `identity`, provided that
    voice reaches non-zero output within ONSET frames (samples may open with silent blocks)."""
    for k in range(start,min(stop,len(frames))):
        for ch,(h,_) in frames[k]['voices'].items():
            if ch in channels and h==identity:
                for j in range(k,min(k+ONSET,len(frames))):
                    v=frames[j]['voices'].get(ch)
                    if not v or v[0]!=identity:break
                    if v[1]>0:return k
    return None


def check(frames,disc,language,variant):
    groups=[50,0,0]
    per=defaultdict(Counter);silent=defaultdict(Counter);latency=defaultdict(list)
    music_seen=defaultdict(set);failures=[]
    for k,fr in enumerate(frames):
        name=NAMES.get(fr['scene'],fr['scene'])
        if fr['kind']=='B':
            for kind,a,b,c in fr['requests']:
                if BATTLE_KINDS[kind]=='BindPlayers':groups[1:]=[a,b]
                elif BATTLE_KINDS[kind]=='LoadBank':groups[a+1]=b
            continue
        for kind,a,b,c in fr['requests']:
            kind=SCENE_KINDS[kind];per[name][kind]+=1
            if kind=='LoadBank':groups[a+1]=b
            elif kind=='Sound':
                ident=disc.effect(groups[a+1],b)
                if ident is None:silent[name]['Sound: tone beyond the bank']+=1;continue
                got=heard(frames,k,k+1,ident,range(14,22))
                if got is None:failures.append((k,name,'Sound',a,b,groups[a+1]))
                else:latency[name+' Sound'].append(got-k)
            elif kind=='Voice':
                ident,where=disc.voice(a,b,language,groups)
                if ident is None:silent[name][f'Voice: {where}']+=1;continue
                got=heard(frames,k,k+VOICE_LATENCY,ident,where)
                if got is None:failures.append((k,name,'Voice',a,b))
                else:latency[name+' Voice'].append(got-k)
            elif kind=='Music':
                music_seen[name].add(a)
                if a==23:
                    got=heard(frames,k,k+1,disc.entry('BVOICE1',49,0x110,12),range(14,22))
                    if got is None:failures.append((k,name,'Jingle',a,b))
                    continue
                # A later stop or request before the key-on supersedes this one.
                end=k+MUSIC_LATENCY
                for j in range(k+1,min(end,len(frames))):
                    if frames[j]['kind']=='S' and any(SCENE_KINDS[r[0]] in ('Music','MusicStop','LoadBank') for r in frames[j]['requests']):end=j;break
                left,right=disc.music(variant,a)
                gl=heard(frames,k,end,left,{0});gr=heard(frames,k,end,right,{1})
                if gl is None or gr is None:
                    if end<k+MUSIC_LATENCY:silent[name]['Music: superseded before the key-on']+=1
                    else:failures.append((k,name,'Music',a,b))
                else:latency[name+' Music'].append(gl-k)
    for name,tracks in SCENE_MUSIC.items():
        if per.get(name) and not music_seen[name]&tracks:failures.append(('missing music',name,sorted(tracks),sorted(music_seen[name])))
    return per,silent,latency,failures


def check_endings(frames,disc,variant):
    """GALLERY ending playback of all 50 scripts: script 1e7b70 / 1e7c00 and object 1e8298 requests."""
    counts=Counter();failures=[];silent=Counter();music=Counter()
    groups=[50,0,0];last=None
    for k,fr in enumerate(frames):
        if fr['scene']!=last:groups=[50,0,0];last=fr['scene']
        for kind,a,b,c in fr['requests']:
            kind=BATTLE_KINDS[kind];counts[kind]+=1
            if kind=='LoadBank':groups[a+1]=b
            elif kind=='Sample':
                ident=disc.effect(groups[a],b)
                if ident is None:silent['Sample: tone beyond the bank']+=1
                elif heard(frames,k,k+1,ident,range(14,22)) is None:failures.append(('ending',fr['scene'],k,'Sample',a,b))
            elif kind=='MusicRequest':
                music[b]+=1;end=k+MUSIC_LATENCY
                for j in range(k+1,min(end,len(frames))):
                    if frames[j]['scene']!=fr['scene'] or any(BATTLE_KINDS[r[0]] in ('MusicRequest','MusicStop','LoadBank') for r in frames[j]['requests']):end=j;break
                left,right=disc.music(variant,b)
                if heard(frames,k,end,left,{0}) is None or heard(frames,k,end,right,{1}) is None:
                    if end<k+MUSIC_LATENCY:silent['Music: superseded before the key-on']+=1
                    else:failures.append(('ending',fr['scene'],k,'Music',b))
            elif kind=='Voice':
                ident,where=disc.voice(a,b,0,groups)
                if ident is None:silent[f'Voice: {where}']+=1
                elif heard(frames,k,k+VOICE_LATENCY,ident,where) is None:failures.append(('ending',fr['scene'],k,'Voice',a,b))
    return counts,silent,music,failures


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--build',default='work/ss6/build-audio')
    parser.add_argument('--assets',default='outputs/ss6-feasibility/native-viewer/assets')
    args=parser.parse_args()
    build=ROOT/args.build;assets=ROOT/args.assets
    with tempfile.TemporaryDirectory() as tmp:
        tmp=Path(tmp);dump=tmp/'frames';dump.mkdir()
        L,log,_=play(build/'ss6-match-replay',assets,dump)
    replay=''.join(f'1 {a} {b}\n' for a,b in L.pads)
    out=subprocess.run([str(build/'ss6-scene-audio-probe'),str(assets),'--mode','title','--unlock-modes'],
                       input=replay,text=True,capture_output=True,check=True).stdout
    frames=parse(out)
    # The replay and the probe run the same session: the scene of every frame agrees.
    scene_rows={i:r[23] if len(r)>23 else '-' for i,r in enumerate(L.rows)}
    mismatch=[f['tick'] for f in frames if f['kind']=='S' and scene_rows.get(f['tick'])!=(f['scene'] if f['scene']!='0' else '-1')]
    assert not mismatch,('probe and replay disagree on the scene',mismatch[:5])
    disc=Disc()
    per,silent,latency,failures=check(frames,disc,language=0,variant=0)
    ends=parse(subprocess.run([str(build/'ss6-scene-audio-probe'),str(assets),'--endings'],text=True,capture_output=True,check=True).stdout)
    ecounts,esilent,emusic,efail=check_endings(ends,disc,variant=0)
    failures+=efail
    report=dict(build=str(args.build),ticks=len(L.pads),mixer_frames=len(frames),
                gallery_endings=dict(scripts=len({f['scene'] for f in ends}),visits=len(ends),requests=dict(ecounts),
                                     music_tracks={str(k):v for k,v in sorted(emusic.items())},expected_silent=dict(esilent)),
                requests={k:dict(v) for k,v in per.items()},expected_silent={k:dict(v) for k,v in silent.items()},
                latency_frames={k:dict(Counter(v)) for k,v in latency.items()},failures=failures[:20],
                scope='Viewer routing (src/audio_routing.cpp) of the shipping session on the arcade route of validate_arcade_session.py; '
                      'sample identities from the disc (MSH/MSB extents, BGM file prefixes) with the factory soundtrack and narration language; '
                      'a request passes when a keyed physical voice reads that sample with non-zero output within the original latency.')
    report['passed']=not failures
    (OUT/'scene_audio_validation.json').write_text(json.dumps(report,indent=1)+'\n')
    assert not failures,failures[:10]
    total=sum(sum(v.values()) for v in per.values())
    print(f'scene audio: {len(frames)} mixer frames, {total} scene requests, {len(ends)} ending visits '
          f'({sum(ecounts.values())} requests), every audible request heard')


if __name__=='__main__':main()
