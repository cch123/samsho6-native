#include <SDL3/SDL.h>
#include <SDL3/SDL_main.h>
#include <array>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <vector>

namespace {
using Pads=std::array<uint32_t,2>;
std::vector<Pads> script;
size_t nextTick=0;
uint64_t clockTicks=0,wallStart=0;
std::ofstream pcm,video;
bool captureVideo=false,transport=false;
size_t submitted=0,images=0;
constexpr std::array<uint32_t,10> masks{8,16,32,64,128,256,512,1024,2048,4096};
constexpr std::array<std::array<SDL_Keycode,10>,2> keys{{
    {SDLK_T,SDLK_W,SDLK_S,SDLK_A,SDLK_D,SDLK_J,SDLK_U,SDLK_L,SDLK_M,SDLK_F},
    {SDLK_RETURN,SDLK_UP,SDLK_DOWN,SDLK_LEFT,SDLK_RIGHT,SDLK_O,SDLK_LEFTBRACKET,SDLK_I,SDLK_RIGHTBRACKET,SDLK_BACKSLASH}
}};

// Supply one clock period and real key edges per turn through the production
// loop. The stream still receives and queues each block on SDL's dummy device.
uint64_t nextTime() {
    if(!clockTicks)wallStart=SDL_GetTicksNS();
    return clockTicks++*(1000000000ull/60);
}
void pace(Uint32) {
    const auto target=wallStart+images*1000000000ull/60;
    const auto now=SDL_GetTicksNS();
    if(target>now)SDL_DelayNS(target-now);
}
bool poll(SDL_Event* event) {
    if(nextTick<clockTicks && nextTick<script.size()) {
        const Pads old=nextTick?script[nextTick-1]:Pads{};
        for(unsigned p=0;p<2;++p)for(unsigned i=0;i<masks.size();++i) {
            if(!((script[nextTick][p]^old[p])&masks[i]))continue;
            SDL_Event key{};
            key.key.down=(script[nextTick][p]&masks[i])!=0;
            key.type=key.key.down?SDL_EVENT_KEY_DOWN:SDL_EVENT_KEY_UP;
            key.key.key=keys[p][i];
            key.key.scancode=SDL_GetScancodeFromKey(key.key.key,nullptr);
            if(!SDL_PushEvent(&key))throw std::runtime_error(SDL_GetError());
        }
        if(transport) {
            SDL_Keycode key=0;
            if(nextTick==12 || nextTick==16)key=SDLK_SPACE;
            if(nextTick==13)key=SDLK_N;
            if(nextTick==31)key=SDLK_R;
            if(key)for(bool down:{true,false}) {
                SDL_Event control{};
                control.type=down?SDL_EVENT_KEY_DOWN:SDL_EVENT_KEY_UP;
                control.key.down=down;control.key.key=key;
                if(!SDL_PushEvent(&control))throw std::runtime_error(SDL_GetError());
            }
        }
        ++nextTick;
    }
    return SDL_PollEvent(event);
}
bool put(SDL_AudioStream* stream,const void* data,int size) {
    if(size!=3200 || !SDL_PutAudioStreamData(stream,data,size))throw std::runtime_error("Unexpected SDL audio submission");
    pcm.write(static_cast<const char*>(data),size);++submitted;
    return static_cast<bool>(pcm);
}
bool present(SDL_Renderer* renderer) {
    if(captureVideo) {
        SDL_Surface* raw=SDL_RenderReadPixels(renderer,nullptr);
        SDL_Surface* pixels=raw?SDL_ConvertSurface(raw,SDL_PIXELFORMAT_RGBA32):nullptr;
        if(!pixels || pixels->w!=640 || pixels->h!=480)throw std::runtime_error("Cannot read 640x480 live frame");
        for(int y=0;y<pixels->h;++y)
            video.write(static_cast<char*>(pixels->pixels)+pixels->pitch*y,pixels->w*4);
        SDL_DestroySurface(pixels);SDL_DestroySurface(raw);
    }
    ++images;
    return SDL_RenderPresent(renderer);
}
bool window(const char* title,int,int,SDL_WindowFlags flags,SDL_Window** w,SDL_Renderer** r) {
    return SDL_CreateWindowAndRenderer(title,640,480,flags,w,r);
}
}
#define SDL_CreateWindowAndRenderer windowForAudioCapture
#define SDL_GetTicksNS nextTime
#define SDL_Delay pace
#define SDL_PollEvent poll
#define SDL_PutAudioStreamData put
#define SDL_RenderPresent presentForAudioCapture
#define main viewerMain
static constexpr auto windowForAudioCapture=window;
static constexpr auto presentForAudioCapture=present;
#include "viewer.cpp"
#undef main

int main(int argc,char** argv) {
    if(argc<5)return 2;
    std::ifstream in(argv[3]);unsigned count;Pads pads;
    while(in>>count>>pads[0]>>pads[1])script.insert(script.end(),count,pads);
    if(!in.eof() || script.empty())return 2;
    pcm.open(argv[4],std::ios::binary);
    std::string length=std::to_string(script.size());
    std::vector<std::string> args={argv[0],"--mode","versus","--assets",argv[1],"--match-replay",argv[2],"--smoke-updates",length};
    for(int i=5;i<argc;++i) {
        const std::string option=argv[i];
        if(option=="--transport")transport=true;
        else if(option=="--p1-spirit" && i+1<argc) {
            args.push_back(option);
            args.emplace_back(argv[++i]);
        } else if(!option.starts_with("--") && !captureVideo) {
            video.open(option,std::ios::binary);
            captureVideo=true;
        } else return 2;
    }
    std::vector<char*> raw;for(auto& arg:args)raw.push_back(arg.data());
    const int result=viewerMain(raw.size(),raw.data());
    pcm.close();if(captureVideo)video.close();
    if(submitted+(transport?4:0)!=script.size() || images!=script.size() || !pcm || (captureVideo&&!video)) {
        std::cerr<<"Expected "<<script.size()<<" live ticks, got "<<submitted<<" audio and "<<images<<" video\n";
        return 1;
    }
    return result;
}
