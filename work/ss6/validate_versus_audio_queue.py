#!/usr/bin/env python3
"""Exercise production playback on an actual SDL dummy audio device."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[2]
REPORT=ROOT/'outputs/ss6-feasibility/versus-audio-queue-validation.json'
DRIVER=r"""
#include <SDL3/SDL.h>
#include <algorithm>
#include <array>
#include <stdexcept>
#include <iostream>
#include <vector>

SDL_AudioStream* hardware=nullptr;
unsigned trims=0; bool emptyRead=false;
SDL_AudioStream* captureOpen(SDL_AudioDeviceID d,const SDL_AudioSpec* s,SDL_AudioStreamCallback c,void* u) {
    return hardware=SDL_OpenAudioDeviceStream(d,s,c,u);
}
int captureRead(SDL_AudioStream* s,void* d,int n) {
    ++trims;
    if(emptyRead){emptyRead=false;return 0;}
    return SDL_GetAudioStreamData(s,d,n);
}
#define SDL_OpenAudioDeviceStream captureOpen
#define SDL_GetAudioStreamData captureRead
#include "versus_audio_output.hpp"
#undef SDL_OpenAudioDeviceStream
#undef SDL_GetAudioStreamData

void require(bool x,const char* msg){if(!x)throw std::runtime_error(std::string(msg)+" "+SDL_GetError());}
using Block=std::array<int16_t,1600>;
Block packet(unsigned tick) {
    Block p{};
    for(unsigned i=0;i<p.size();i+=2) {
        p[i]=int16_t((7001*tick+i*83)%30001-15000);
        p[i+1]=int16_t(-p[i]);
    }
    return p;
}
std::vector<uint8_t> drain(SDL_AudioStream* s) {
    require(SDL_FlushAudioStream(s),"flush");
    int n=SDL_GetAudioStreamAvailable(s);require(n>=0,"available");
    std::vector<uint8_t> result(n);
    require(SDL_GetAudioStreamData(s,result.data(),n)==n,"readback");
    return result;
}
int main() {
    ss6::VersusPlayback player;player.open();require(hardware,"open");
    SDL_AudioSpec source{SDL_AUDIO_S16,2,48000},device{};int quantum=0;
    const auto dev=SDL_GetAudioStreamDevice(hardware);
    require(SDL_GetAudioDeviceFormat(dev,&device,&quantum),"device format");
    std::unique_ptr<SDL_AudioStream,decltype(&SDL_DestroyAudioStream)> baseline(
        SDL_OpenAudioDeviceStream(SDL_AUDIO_DEVICE_DEFAULT_PLAYBACK,&source,nullptr,nullptr),SDL_DestroyAudioStream);
    require(bool(baseline),"reference open");
    auto plain=[&](const Block& b){require(SDL_PutAudioStreamData(baseline.get(),b.data(),3200),"baseline write");};
    require(SDL_PauseAudioStreamDevice(hardware),"pause actual sink");
    const int target=std::max(9600,int((int64_t(quantum)*48000+device.freq-1)/device.freq)*4);
    const int cap=target+9600;
    for(unsigned i=0;i<3;++i){auto b=packet(i);player.write(b);plain(b);}
    require(trims==0,"unexpected correction below watermark");
    require(drain(hardware)==drain(baseline.get()),"normal playback differs from reference");
    require(SDL_GetAudioStreamFrequencyRatio(hardware)==1.0f,"playback pitch changed");

    // Hold the real consumer still to verify the peak for every single submit.
    // Its surviving output must be the end of the original stereo waveform.
    int burstMax=0;
    for(unsigned i=0;i<48;++i) {
        auto b=packet(i);player.write(b);plain(b);
        const auto q=SDL_GetAudioStreamQueued(hardware);require(q>=0&&q<=cap,"burst exceeded bound");
        burstMax=std::max(burstMax,q);
    }
    auto after=drain(hardware),full=drain(baseline.get());
    require(!after.empty()&&after.size()<full.size(),"burst did not trim");
    require(std::equal(after.rbegin(),after.rend(),full.rbegin()),"most recent stereo samples lost");

    // A conversion boundary may legally give no output. Retain the current
    // packet and keep accepting the subsequent packet on the same device.
    for(int i=0;i<cap/3200;++i)player.write(packet(i));
    emptyRead=true;
    auto current=packet(50);player.write(current);plain(current);
    require(!emptyRead,"zero-read fallback was not reached");
    auto following=packet(51);player.write(following);plain(following);
    require(drain(hardware)==drain(baseline.get()),"zero-read muted the device or lost fresh packets");
    require(SDL_ResumeAudioStreamDevice(hardware)&&SDL_ResumeAudioStreamDevice(baseline.get()),"resume sinks");
    uint64_t start=SDL_GetTicksNS(),previous=start,remainder=0;
    const uint64_t period=1000000000ull/60;
    unsigned tick=0;int dryPeak=0,realPeak=0,oldPeak=0,before=-1,oldBefore=-1,burst=-1,oldBurst=-1,last=-1,oldLast=-1;
    bool stalled=false;int submitted=0;
    for(;;) {
        const auto now=SDL_GetTicksNS(),ms=(now-start)/1000000;
        remainder+=std::min(now-previous,uint64_t(250000000));previous=now;
        while(remainder>=period) {
            auto b=packet(++tick);player.write(b);plain(b);++submitted;
            int x=SDL_GetAudioStreamQueued(hardware),y=SDL_GetAudioStreamQueued(baseline.get());
            require(x>=0&&x<=cap&&y>=0,"real-time queue bound");
            realPeak=std::max(realPeak,x);oldPeak=std::max(oldPeak,y);
            if(!stalled)dryPeak=std::max(dryPeak,x);
            remainder-=period;
        }
        if(!stalled && ms>=650) {
            before=SDL_GetAudioStreamQueued(hardware);oldBefore=SDL_GetAudioStreamQueued(baseline.get());
            SDL_Delay(236);stalled=true;continue;
        }
        if(stalled && burst==-1) {
            burst=SDL_GetAudioStreamQueued(hardware);oldBurst=SDL_GetAudioStreamQueued(baseline.get());
        }
        if(ms>=3100) {last=SDL_GetAudioStreamQueued(hardware);oldLast=SDL_GetAudioStreamQueued(baseline.get());break;}
        SDL_Delay(4);
    }
    require(oldBurst>cap && burst<=cap && oldPeak>realPeak,"uncorrected stall was not reproduced");
    require(submitted>=160,"insufficient real-time playback");
    int data[]={quantum,device.freq,target,cap,burstMax,int(after.size()),int(tick),dryPeak,before,oldBefore,burst,oldBurst,last,oldLast,realPeak,oldPeak};
    for(int v:data)std::cout<<v<<' ';
}
"""


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--report',type=Path,default=REPORT);args=ap.parse_args()
    pkg=shlex.split(subprocess.check_output(['pkg-config','--libs','--cflags','sdl3'],text=True))
    runs={}
    with tempfile.TemporaryDirectory() as d:
        temp=Path(d);src=temp/'run.cpp';exe=temp/'run';src.write_text(DRIVER)
        subprocess.run(['c++','-std=c++20','-O2','-I',str(ROOT/'src'),str(src),*pkg,'-o',str(exe)],check=True)
        for name,frames in [('standard','512'),('long_device_period','4096')]:
            env=dict(os.environ,SDL_AUDIO_DRIVER='dummy',SDL_AUDIO_DEVICE_SAMPLE_FRAMES=frames)
            values=list(map(int,subprocess.check_output([str(exe)],env=env,text=True,timeout=30).split()))
            keys=['device_period_frames','device_rate','low_water_bytes','max_queue_bytes','blocked_sink_peak_bytes',
                  'retained_converted_bytes','submitted_ticks','steady_peak','before_stall','unbounded_before_stall',
                  'after_stall','unbounded_after_stall','at_3s','unbounded_at_3s','peak','unbounded_peak']
            data=dict(zip(keys,values,strict=True))
            data['queue_ms']={k:round(data[k]/192,2) for k in keys[7:]}
            runs[name]=data
    report=dict(status='passed',front_end_sha256=hashlib.sha256((ROOT/'src/versus_audio_output.hpp').read_bytes()).hexdigest(),
                ticks_per_second=60,sample_frames_per_tick=800,bytes_per_tick=3200,stall_ms=236,
                zero_read_recovery='stale queue cleared; next two submitted packets reproduced exactly',
                normal_device_output='byte-identical to unmodified SDL, rate 1.0',
                overloaded_device_output='retained exact suffix of the original converted stereo waveform',runs=runs)
    text=json.dumps(report,indent=2);args.report.write_text(text+'\n');print(text)


if __name__=='__main__':main()
