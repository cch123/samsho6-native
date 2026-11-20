#!/usr/bin/env python3
"""Compare title BGM/announcement stereo output to both Japanese EE/IOP configurations."""
import argparse
import json
import os
from pathlib import Path
import struct
import subprocess
import tempfile
import wave

import numpy as np

from validate_combat_audio import ELF, ISO, PIN, RES, ROOT, SOURCE, Iso, OriginalDriver, sha
from validate_battle_sound import frame_events
from validate_selected_combat import BUILD
from validate_combat_music import HALF, MusicDriver, decoded
from validate_selected_stage_music import source_gain

OUT = ROOT/'outputs/ss6-feasibility'
CPP = r"""
#include "combat_audio.hpp"
#include <array>
#include <fstream>
int main(int argc,char** argv) {
    ss6::CombatAudio audio(argv[1]);
    int variant=std::stoi(argv[3]), ticks=std::stoi(argv[4]);
    std::ofstream out(argv[2],std::ios::binary);
    std::array<int16_t,1600> buf{};
    for(int tick=0;tick<ticks;++tick) {
        if(tick==0)audio.playMusic(variant,1,0x3200);
        if(tick==30&&audio.playVoice(49,0,variant)!=-1)return 2;
        audio.tick();audio.render(buf);
        out.write(reinterpret_cast<const char*>(buf.data()),sizeof(buf));
    }
    return !out;
}
"""


def title_music(iso, variant, assets):
    d = MusicDriver(iso)
    d.ee.write(0x43d056, variant, 1)
    d.call(0x1e7c00, 1, 0)
    assert [d.ee.read(a,4) for a in (0x5850e0,0x1553b40,0x1553b54,0x5a9e80,0x1553b58)] == [0,2,variant,0,0]
    for visit in range(6):
        d.call(0x2142c0)
        assert d.state() == (0x1000 if visit==5 else 0)
    for state in (0x2000,0x3000,0x5000):
        d.service()
        assert d.state() == state
    assert d.delays == [100000,100000] and d.switches[-1] == (0x1501,3)
    assert [d.registers[i] for i in (1,0x101,3,0x103,0x201,0x203)] == [0x3200,0,0,0x3200,0x761,0x761]
    while d.state()==0x5000:
        d.service()
    assert d.state()==0x6000 and len(d.transfers)==48
    d.service()
    assert d.state()==0 and d.switches[-1]==(0x1601,3)
    sides, files = [], []
    for side, name in enumerate('LR'):
        path = f'/BGM{3 if variant else 1}/BGM01_{name}.VB'
        disc = iso.read(path)
        assert disc == (assets/f'bgm01_{name.lower()}.vb').read_bytes()
        assert d.reads[side] == (iso.by_path[path]['lba'],160)
        address = 0x1e0000 + side*2*HALF
        wire = bytearray().join(b for dest,b in d.transfers if dest in (address,address+HALF))
        assert len(wire)==len(disc)==25*HALF
        # The IOP rewrites only the transport flags (byte 1 per ADPCM block).
        for byte in (0,*range(2,16)):
            assert wire[byte::16] == disc[byte::16]
        files.append(dict(path=path,sha256=sha(disc),dma_sha256=sha(wire)))
        sides.append(np.asarray(decoded(wire),dtype=np.int64))
    return sides, np.asarray(d.table,dtype=np.int64), dict(variant=variant,files=files,sector_reads=d.reads)


def title_voice(iso, variant):
    d = OriginalDriver(iso)
    d.ee.write(0x43d055,variant,1)
    header = iso.read('/VOICE/NAL.MSH')
    sector,_,size,_ = struct.unpack_from('<4I',header,variant*0x210)
    bank = iso.read_at((iso.by_path['/VOICE/NAL.MSB']['lba']+sector)*2048,size)
    d.ee.memory[0x1373980:0x1373980+size] = bank
    assert d.call(0x1e7d60,49,0)==-1
    for service in range(3):
        d.call(0x213660)
        assert set(d.voices)==({4} if service==2 else set())
    voice = d.voices[4]
    dry = []
    while (sample := voice.next(d.table)) is not None:
        dry.append(sample)
    size,offset = struct.unpack_from('<2I',header,variant*0x210+16)
    return np.asarray(dry,dtype=np.int64), dict(variant=variant,channel=4,sample_bytes=size,
        sample_sha256=sha(bank[offset:offset+size]),frames=len(dry),pitch=voice.pitch,volume=voice.volume)


def reference_mix(iso,variant,assets):
    music,taps,track = title_music(iso,variant,assets)
    speech,line = title_voice(iso,variant)
    # After 24 audible halves the IRQ keys off both voices while half 25
    # is still ahead of the read head. Keep silence afterwards to catch wrap.
    stop = 17*800 + (24*HALF//16*28*4096+1888)//1889
    count = (stop//800+4)*800
    wet = np.zeros((count,2),dtype='<i2')
    for at in range(0,count,65536):
        hi = min(count,at+65536)
        time = np.arange(at,hi)
        dry = np.zeros((hi-at,2),dtype=np.int64)
        active = (time>=17*800)&(time<stop)
        dry[active] = source_gain(music,taps,time[active]-17*800)
        # Title update 31 queues the line. The third EE voice service keys
        # it, before the stereo channel sums are clamped and master gain applied.
        speaking = (time>=32*800)&(time<32*800+len(speech))
        dry[speaking] += speech[time[speaking]-32*800,None]
        wet[at:hi] = np.clip(dry,-32768,32767)*32766//32768
    return wet, dict(music=track,voice=line,frames=count,keyoff_sample=stop,pcm_sha256=sha(wet.tobytes()))


def viewer_mix(assets, viewer, tmp, expected):
    # Stay on the initial title page until after the complete announcement
    # has played. All frames originate from the regular SDL viewer entry.
    ticks = 600
    events = subprocess.run([BUILD/'ss6-match-replay',assets,'--mode','title','--sound-fields'],
                            input='1 0 0\n'*ticks,text=True,capture_output=True,check=True)
    heard = [(i+1,e) for i,row in enumerate(events.stdout.splitlines()) for e in frame_events(row.split())]
    assert heard==[(1,(3,0,1)),(1,(9,51,0)),(1,(8,0x3200,1)),(31,(1,49,0))]
    pad = tmp/'pads'
    pad.write_text(f'{ticks} 0 0\n')
    wav = tmp/'viewer.wav'
    subprocess.run([viewer,'--assets',assets,'--mode','title','--match-replay',pad,'--audio-out',wav],
                   check=True,env=dict(os.environ,SDL_VIDEODRIVER='dummy',SDL_AUDIODRIVER='dummy'))
    with wave.open(str(wav),'rb') as rec:
        assert rec.getparams()[:3]==(2,2,48000) and rec.getnframes()==ticks*800
        actual = rec.readframes(rec.getnframes())
    assert actual==expected[:ticks*800].tobytes()
    with wave.open(str(OUT/'title-audio-preview.wav'),'wb') as preview:
        preview.setparams((2,2,48000,0,'NONE','not compressed'))
        preview.writeframes(actual[:6*48000*4])
    return dict(frames=ticks*800,pcm_sha256=sha(actual),viewer_sha256=sha(viewer.read_bytes()),events=heard)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--package',action='store_true')
    args = parser.parse_args()
    assets = OUT/'native-viewer/assets' if args.package else RES
    assert sha(ELF.read_bytes())==PIN
    iso = Iso(ISO)
    reports = []
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        src,exe,pcm = tmp/'title.cpp',tmp/'title',tmp/'title.pcm'
        src.write_text(CPP)
        subprocess.run(['c++','-std=c++20','-ffp-contract=off','-O2','-I',SOURCE,src,SOURCE/'combat_audio.cpp',
                        SOURCE/'combat_music.cpp',SOURCE/'combat_sound_bank.cpp','-o',exe],check=True)
        for variant in (0,1):
            expected,report = reference_mix(iso,variant,assets)
            subprocess.run([exe,assets,pcm,str(variant),str(len(expected)//800)],check=True)
            actual = np.fromfile(pcm,dtype='<i2').reshape(-1,2)
            if not np.array_equal(actual,expected):
                first = np.flatnonzero(np.any(actual!=expected,axis=1))[0]
                raise AssertionError((variant,first,actual[first],expected[first]))
            assert np.any(actual[:96000]) and not np.any(actual[report['keyoff_sample']:])
            if variant==0:
                viewer = OUT/'native-viewer/ss6-viewer' if args.package else BUILD/'ss6-viewer'
                report['viewer'] = viewer_mix(assets,viewer,tmp,expected)
            reports.append(report)
    assert reports[0]['voice']['sample_sha256']!=reports[1]['voice']['sample_sha256']
    (OUT/'title-audio-validation.json').write_text(json.dumps(dict(status='passed',elf_sha256=PIN,
        comparisons=reports,scope='Original title audio wrappers, EE queues, IOP and disc transfers through one-shot EOF. Both settings, full PCM comparison and a six-second SDL viewer preview. Ready-disc latency fixture.'),indent=2)+'\n')
    print('Both title audio variants matched through keyoff:',sum(r['frames'] for r in reports),'stereo frames')


if __name__ == '__main__':
    main()
