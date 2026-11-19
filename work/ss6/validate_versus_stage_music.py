#!/usr/bin/env python3
"""Compare the complete original stereo stream, including the first rewind, for all ten Japanese VS stages."""
import argparse
from concurrent.futures import ProcessPoolExecutor
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import tempfile

import numpy as np
from validate_combat_music import capture, PITCH, RES, ROOT, SOURCE
from validate_combat_audio import ELF, PIN, sha
from validate_stage_music_events import source as original_round_calls

CPP=r"""
#include "combat_audio.hpp"
#include <algorithm>
#include <fstream>
int main(int argc,char**argv) {
    ss6::CombatAudio audio(argv[1]);const int track=std::stoi(argv[2]);
    unsigned long frames=std::stoul(argv[3]);std::ofstream pcm(argv[4],std::ios::binary);
    audio.preloadMusic(0,track);
    for(int n=0;n<30;++n)audio.tick();
    std::array<int16_t,4096> buf;audio.render(buf);
    if(std::any_of(buf.begin(),buf.end(),[](auto value){return value!=0;}))return 2;
    audio.startMusic(0x3200);audio.tick();
    while(frames) {
        auto n=std::min(frames,buf.size()/2);audio.render(std::span(buf.data(),n*2));
        pcm.write(reinterpret_cast<const char*>(buf.data()),n*4);frames-=n;
    }
    audio.stopMusic();audio.render(buf);
    return !pcm||std::any_of(buf.begin(),buf.end(),[](auto value){return value!=0;});
}
"""


def stage_case(arg):
    root,assets,stage=arg;tone=stage+5;exe=root/'mixer'
    sides,traces,weights=capture(tone,assets)
    # Verify the IOP not only opened the ELF catalog entry but performed the
    # first reads from each channel's actual sector, not its identically-sized mate.
    reads=traces['sector_reads'];assert reads[0][0]<reads[1][0]
    assert reads[1][0]-reads[0][0]==traces['L']['file_bytes']//2048
    assert len(sides[0])==len(sides[1]);period=len(sides[0]);frames=(period*4096+PITCH-1)//PITCH+800
    raw=root/f'{stage}.pcm'
    subprocess.run([exe,assets,str(tone),str(frames),raw],check=True)
    table=np.array(weights,dtype=np.int64);wave=np.memmap(raw,'<i2','r',shape=(frames,2))
    pcm=[np.frombuffer(side,dtype='<i2') for side in sides];digest=sha256()
    for offset in range(0,frames,32768):
        t=np.arange(offset,min(offset+32768,frames),dtype=np.int64)
        pos=t*PITCH;indexes=(pos//4096)%period;phase=(pos//16)%256
        # These follow the actual sound-register values traced at KEYON.
        # The independent four-tap table is pinned to the PS2 interpolation coefficients.
        level=np.minimum(32767,16383+4*((t-3)//32768))
        if not offset:level[:3]=[14336,28672,32767]
        expected=np.empty((len(t),2),dtype='<i2')
        for seat in (0,1):
            four_taps=sum(table[phase,k]*pcm[seat][(indexes+k)%period]//32768 for k in range(4))
            voice=(four_taps*level//32768)*(2*0x3200)//32768
            expected[:,seat]=np.clip(voice,-32768,32767)*32766//32768
        got=wave[offset:offset+len(t)]
        if not np.array_equal(expected,got):
            at,channel=np.argwhere(expected!=got)[0]
            raise AssertionError((stage,'PCM frame',offset+at,'channel',channel,int(expected[at,channel]),int(got[at,channel])))
        digest.update(expected.tobytes())
    del wave;raw.unlink()
    result=dict(stage=stage,tone=tone,stereo_frames_48000=frames,pcm_sha256=digest.hexdigest(),
                source_samples_per_side=period,ee_instructions=traces['ee_instructions'],iop_instructions=traces['iop_instructions'],
                io_sector_reads=len(reads),rewind_sector=reads[0],channels=[traces[k] for k in 'LR'])
    print(f'Stage {stage} / BGM{tone:02} / {frames:,} full stereo frames',flush=True)
    return result


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--assets',type=Path,default=RES);ap.add_argument('--workers',type=int,default=3)
    opt=ap.parse_args();assert sha(ELF.read_bytes())==PIN
    rounds=original_round_calls()
    with tempfile.TemporaryDirectory() as td:
        tmp=Path(td);source=tmp/'compare.cpp';source.write_text(CPP)
        subprocess.run(['c++','-std=c++20','-O2','-I',SOURCE,source,*(SOURCE/s for s in
                        ('combat_audio.cpp','combat_music.cpp','combat_sound_bank.cpp')),'-o',tmp/'mixer'],check=True)
        with ProcessPoolExecutor(max_workers=opt.workers) as pool:
            cases=list(pool.map(stage_case,[(tmp,opt.assets,stage) for stage in range(10)]))
    assert len({r['pcm_sha256'] for r in cases})==10
    report=dict(status='passed',source_elf_sha256=PIN,default_soundtrack=0,round_ee_instructions=rounds,
                native_sources={s:sha((SOURCE/s).read_bytes()) for s in ('combat_music.cpp','combat_music.hpp','combat_audio.cpp','combat_sound_bank.cpp')},
                stereo_frames=sum(r['stereo_frames_48000'] for r in cases),cases=cases,
                scope='Original 13abb0 stage routing, EE service, original IRX CD DMA and SPU registers on left and right voices; each complete dry stream plus 800 host frames after rewind through the production 48 kHz mixer. Includes preload silence, release, immediate stop. The disc and DMA devices in the original-code runner are memory-backed.')
    (ROOT/'outputs/ss6-feasibility/versus-stage-music-validation.json').write_text(json.dumps(report,indent=2)+'\n')
    print(report['stereo_frames'],'stereo frames verified')


if __name__=='__main__':main()
