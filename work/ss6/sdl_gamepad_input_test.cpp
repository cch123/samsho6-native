#include <SDL3/SDL.h>
#include <SDL3/SDL_main.h>
#include "native_match.hpp"
#include "native_scene.hpp"
#include <array>
#include <fstream>
#include <iostream>
#include <map>
#include <memory>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

namespace {
std::vector<std::string> steps;
unsigned shown = 0;
std::map<unsigned,std::string> screenshots;
SDL_WindowID windowId{};
bool fixedHostTime=false;
Uint64 testClock() { return fixedHostTime ? 1 : SDL_GetTicksNS(); }
struct Injector { SDL_JoystickID id{}; SDL_Joystick* stick{}; };
std::array<Injector,3> devices;
std::array<unsigned,5> eventCounts{};

void require(bool ok) {
    if(!ok)throw std::runtime_error(SDL_GetError());
}

bool SDLCALL countDeviceEvents(void*,SDL_Event* e) {
    switch(e->type) {
    case SDL_EVENT_GAMEPAD_ADDED: ++eventCounts[0];break;
    case SDL_EVENT_GAMEPAD_REMOVED: ++eventCounts[1];break;
    case SDL_EVENT_GAMEPAD_BUTTON_DOWN: ++eventCounts[2];break;
    case SDL_EVENT_GAMEPAD_BUTTON_UP: ++eventCounts[3];break;
    case SDL_EVENT_GAMEPAD_AXIS_MOTION: ++eventCounts[4];break;
    }
    return true;
}

void connect(unsigned i) {
    auto& d=devices.at(i);
    if(d.id)throw std::runtime_error("Test device already attached");
    SDL_VirtualJoystickDesc desc{};
    SDL_INIT_INTERFACE(&desc);
    desc.type=SDL_JOYSTICK_TYPE_GAMEPAD;
    desc.nbuttons=SDL_GAMEPAD_BUTTON_COUNT;
    desc.naxes=SDL_GAMEPAD_AXIS_COUNT;
    desc.name="SS6 virtual pad";
    d.id=SDL_AttachVirtualJoystick(&desc);
    require(d.id!=0 && SDL_IsGamepad(d.id));
    d.stick=SDL_OpenJoystick(d.id);
    require(d.stick!=nullptr);
    for(auto axis:{SDL_GAMEPAD_AXIS_LEFT_TRIGGER,SDL_GAMEPAD_AXIS_RIGHT_TRIGGER})
        require(SDL_SetJoystickVirtualAxis(d.stick,axis,SDL_MIN_SINT16));
    SDL_UpdateJoysticks();
}

void disconnect(unsigned i) {
    auto& d=devices.at(i);
    if(!d.id)throw std::runtime_error("Test device already detached");
    require(SDL_DetachVirtualJoystick(d.id));
    SDL_CloseJoystick(d.stick);
    d={};
}

void key(SDL_Keycode code,bool down) {
    SDL_Event e{};
    e.type=down?SDL_EVENT_KEY_DOWN:SDL_EVENT_KEY_UP;
    e.key.key=code;e.key.scancode=SDL_GetScancodeFromKey(code,nullptr);
    e.key.down=down;e.key.windowID=windowId;
    require(SDL_PushEvent(&e));
}

void physicalButton(unsigned device,unsigned ps2,int value) {
    // The test describes the original 16-bit physical port word. Only SDL
    // creates the resulting GAMEPAD events and resolves a virtual mapping.
    static constexpr SDL_GamepadButton buttons[]={
        SDL_GAMEPAD_BUTTON_INVALID,SDL_GAMEPAD_BUTTON_INVALID,
        SDL_GAMEPAD_BUTTON_LEFT_SHOULDER,SDL_GAMEPAD_BUTTON_RIGHT_SHOULDER,
        SDL_GAMEPAD_BUTTON_NORTH,SDL_GAMEPAD_BUTTON_EAST,
        SDL_GAMEPAD_BUTTON_SOUTH,SDL_GAMEPAD_BUTTON_WEST,
        SDL_GAMEPAD_BUTTON_BACK,SDL_GAMEPAD_BUTTON_LEFT_STICK,
        SDL_GAMEPAD_BUTTON_RIGHT_STICK,SDL_GAMEPAD_BUTTON_START,
        SDL_GAMEPAD_BUTTON_DPAD_UP,SDL_GAMEPAD_BUTTON_DPAD_RIGHT,
        SDL_GAMEPAD_BUTTON_DPAD_DOWN,SDL_GAMEPAD_BUTTON_DPAD_LEFT
    };
    auto stick=devices.at(device).stick;
    if(!stick || ps2>=std::size(buttons))throw std::runtime_error("Unknown physical control");
    if(ps2<2) {
        auto axis=ps2?SDL_GAMEPAD_AXIS_RIGHT_TRIGGER:SDL_GAMEPAD_AXIS_LEFT_TRIGGER;
        require(SDL_SetJoystickVirtualAxis(stick,axis,static_cast<Sint16>(value)));
    } else require(SDL_SetJoystickVirtualButton(stick,buttons[ps2],value!=0));
    // Flushing the virtual joystick between transitions allows a fast tap
    // to produce two real events before a single battle update.
    SDL_UpdateJoysticks();SDL_PumpEvents();
}

void inject(const std::string& line) {
    std::istringstream input(line);
    std::string word;
    while(input>>word) {
        if(word[0]=='+')connect(std::stoul(word.substr(1)));
        else if(word[0]=='-')disconnect(std::stoul(word.substr(1)));
        else if(word[0]=='N'){
            for(int i=0;i<std::stoi(word.substr(1));++i){key(SDLK_N,true);key(SDLK_N,false);}
        } else if(word[0]=='K'){
            const auto code=SDL_GetKeyFromName(word.substr(1,word.size()-2).c_str());
            if(!code)throw std::runtime_error("Unknown key "+word);
            key(code,word.back()=='+');
        } else {
            const auto dot=word.find('.'),eq=word.find('=');
            physicalButton(std::stoul(word.substr(0,dot)),std::stoul(word.substr(dot+1,eq-dot-1)),std::stoi(word.substr(eq+1)));
        }
    }
}

bool makeWindow(const char* title,int,int,SDL_WindowFlags flags,SDL_Window** window,SDL_Renderer** renderer) {
    require(SDL_CreateWindowAndRenderer(title,640,480,flags,window,renderer));
    windowId=SDL_GetWindowID(*window);
    int count=0;SDL_free(SDL_GetGamepads(&count));
    if(count)throw std::runtime_error("Run this isolated test without preconnected hardware controllers");
    require(SDL_AddEventWatch(countDeviceEvents,nullptr));
    connect(0); // Startup enumeration. The second device arrives through hotplug.
    SDL_Event e{};e.type=SDL_EVENT_WINDOW_FOCUS_LOST;e.window.windowID=windowId;
    return SDL_PushEvent(&e);
}

bool inspectGamepadPresent(SDL_Renderer* renderer) {
    if(auto shot=screenshots.find(shown);shot!=screenshots.end()) {
        using Surface=std::unique_ptr<SDL_Surface,decltype(&SDL_DestroySurface)>;
        Surface pixels(SDL_RenderReadPixels(renderer,nullptr),SDL_DestroySurface);
        if(!pixels)throw std::runtime_error(SDL_GetError());
        Surface rgba(SDL_ConvertSurface(pixels.get(),SDL_PIXELFORMAT_RGBA32),SDL_DestroySurface);
        require(rgba&&SDL_SaveBMP(rgba.get(),shot->second.c_str()));
    }
    if(shown<steps.size())inject(steps[shown]);
    else {
        SDL_RemoveEventWatch(countDeviceEvents,nullptr);
        for(unsigned i=0;i<devices.size();++i)if(devices[i].id)disconnect(i);
    }
    ++shown;
    return SDL_RenderPresent(renderer);
}
}

namespace ss6 {
class PadObservedScene : public NativeScene {
public:
    using NativeScene::NativeScene;
    void paint(const NativeMatch& match,std::span<uint8_t> rgba,const EffectPainter& effects,unsigned nextDepth,
               const ObjectDrawQueue* presentation=nullptr) {
        NativeScene::paint(match,rgba,effects,nextDepth,presentation);
        std::cout<<"render "<<shown<<' '<<match.updates;
        for(unsigned i=0;i<2;++i) {
            const auto& f=match.fighter(i);
            const auto& words=f.input.sampledFeatures;
            auto pack=[&](unsigned offset,unsigned count) {
                uint32_t result=0;
                for(unsigned j=0;j<count;++j)result|=(words[offset/4+j]!=0)<<j;
                return result;
            };
            std::cout<<' '<<f.actor.stateTable()<<' '<<f.actor.stateIndex()<<' '<<f.body.timeline.action().id()
                     <<' '<<f.actor.fieldA30<<' '<<f.hits<<' '<<f.guards
                     <<' '<<pack(0x16c,6)<<' '<<pack(0x18,6)<<' '<<pack(0x14c,8);
        }
        const auto& battle=match.battle();
        const auto& pools=battle.entry.tasks;
        for(unsigned side=0;side<2;++side) {
            const auto& f=match.fighter(side);
            unsigned weaponAction=0;
            for(auto task:f.storage.objectTasks)if(task) {
                const auto& object=pools.objects.at(pools.tasks.at(task-1)[7]-1);
                if(object[0xcc/4]==4)weaponAction=object[0x24/4];
            }
            std::cout<<' '<<f.config.system<<' '<<f.actor.rageState120<<' '<<f.actor.rageAmount124
                     <<' '<<bool(f.actor.flags23c&0x1000)<<' '<<weaponAction;
        }
        if(match.fighter(0).config.system==5||match.fighter(1).config.system==5) {
            std::cout<<' '<<match.fighter(0).actor.systemMeter158
                     <<' '<<match.fighter(1).actor.systemMeter158;
        }
        std::cout<<'\n';
        const auto& menu=battle.consoleMenu;
        std::cout<<"menu "<<shown<<' '<<match.updates<<' '<<menu.active<<' '<<menu.draw.visible
                 <<' '<<menu.draw.selection<<' '<<menu.draw.dialog<<' '<<menu.draw.choice
                 <<' '<<unsigned(menu.pending)<<' '<<unsigned(menu.destination)<<' '<<menu.fadeAlpha;
        for(unsigned side=0;side<2;++side)
            std::cout<<' '<<menu.session.wins[side]<<' '<<menu.session.losses[side];
        std::cout<<' '<<battle.remainingSeconds()<<' '<<battle.match.players[0].wins
                 <<' '<<battle.match.players[1].wins<<'\n';
    }
};
}

#define NativeScene PadObservedScene
#define SDL_CreateWindowAndRenderer makeWindow
#define SDL_RenderPresent inspectGamepadPresent
#define SDL_GetTicksNS testClock
#define main viewerMain
#include "viewer.cpp"
#undef main
#undef SDL_GetTicksNS
#undef SDL_RenderPresent
#undef SDL_CreateWindowAndRenderer
#undef NativeScene

int main(int argc,char** argv) {
    if(argc<4)return 2;
    std::ifstream sequence(argv[3]);
    if(!sequence)return 2;
    for(std::string line;std::getline(sequence,line);)if(!line.empty())steps.push_back(line);
    SDL_SetHint(SDL_HINT_JOYSTICK_ALLOW_BACKGROUND_EVENTS,"1");
    std::vector<std::string> args={argv[0],"--assets",argv[1],"--mode","versus","--match-replay",argv[2],
                                   "--smoke-updates",std::to_string(steps.size()+1)};
    for(int i=4;i<argc;++i) {
        if(std::string(argv[i])=="--fixed-host-time") {
            // Resume after the last manual step without admitting an extra
            // host-clock-dependent update before the unpaused screenshot.
            fixedHostTime=true;
        } else if(std::string(argv[i])=="--capture") {
            if(i+2>=argc)return 2;
            const unsigned frame=std::stoul(argv[++i]);
            screenshots.emplace(frame,argv[++i]);
        } else args.emplace_back(argv[i]);
    }
    std::vector<char*> raw;
    for(auto& s:args)raw.push_back(s.data());
    raw.push_back(nullptr);
    const int result=viewerMain(static_cast<int>(args.size()),raw.data());
    std::cout<<"events";
    for(auto n:eventCounts)std::cout<<' '<<n;
    std::cout<<'\n';
    return result?result:shown==steps.size()+1?0:1;
}
