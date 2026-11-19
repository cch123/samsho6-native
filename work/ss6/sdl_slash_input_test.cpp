#include <SDL3/SDL.h>
#include <SDL3/SDL_main.h>
#include "native_match.hpp"
#include "native_scene.hpp"
#include <filesystem>
#include <iostream>
#include <memory>
#include <stdexcept>
#include <string>
#include <vector>

namespace {
std::vector<std::string> keys;
std::filesystem::path output;
unsigned presented{};
bool versus{};
SDL_WindowID testWindow{};

void pushKey(SDL_Keycode key, bool down, bool repeat = false) {
    SDL_Event event{};
    event.type = down ? SDL_EVENT_KEY_DOWN : SDL_EVENT_KEY_UP;
    event.key.windowID = testWindow;
    event.key.key = key;
    event.key.scancode = SDL_GetScancodeFromKey(key, nullptr);
    event.key.down = down;
    event.key.repeat = repeat;
    if (!SDL_PushEvent(&event)) throw std::runtime_error(SDL_GetError());
}

void pushSequence() {
    for (const std::string& token : keys) {
        if (token == "Space") {
            pushKey(SDLK_SPACE, true);
            pushKey(SDLK_SPACE, false);
            continue;
        }
        // Brackets are literal SDL key names for player two's medium slash and kick.
        const auto end=token.find_first_of("+-~0123456789");
        const auto name=token.substr(0,end);
        const auto key=SDL_GetKeyFromName(name.c_str());
        if(!key)throw std::runtime_error("Unknown key: "+token);
        const auto suffix=end==std::string::npos?std::string():token.substr(end);
        if (suffix == "~") {
            pushKey(key, true, true);
        } else if (suffix == "+") {
            pushKey(key, true);
        } else if (suffix == "-") {
            pushKey(key, false);
        } else {
            const unsigned count = suffix.empty() ? 1 : std::stoul(suffix);
            for (unsigned i = 0; i < count; ++i) {
                pushKey(key, true);
                pushKey(key, false);
            }
        }
    }
}

bool makeTestWindow(const char* title, int w, int h, SDL_WindowFlags flags,
                    SDL_Window** window, SDL_Renderer** renderer) {
    if (!SDL_CreateWindowAndRenderer(title, versus?640:w, versus?480:h, flags, window, renderer)) return false;
    testWindow = SDL_GetWindowID(*window);
    // The real focus-loss handler pauses before the first simulation tick,
    // independent of scheduler timing. N then goes through the viewer's own
    // single-step branch, including polling the keyboard before trial.tick().
    SDL_Event event{};
    event.type = SDL_EVENT_WINDOW_FOCUS_LOST;
    event.window.windowID = testWindow;
    return SDL_PushEvent(&event);
}

bool inspectPresent(SDL_Renderer* renderer) {
    if (presented == 0) {
        pushSequence();
    } else if (presented == 1) {
        using Surface = std::unique_ptr<SDL_Surface, decltype(&SDL_DestroySurface)>;
        Surface image(SDL_RenderReadPixels(renderer, nullptr), SDL_DestroySurface);
        if (!image) throw std::runtime_error(SDL_GetError());
        Surface rgba(SDL_ConvertSurface(image.get(), SDL_PIXELFORMAT_RGBA32), SDL_DestroySurface);
        if (!rgba || !SDL_SaveBMP(rgba.get(), output.c_str())) throw std::runtime_error(SDL_GetError());
    }
    ++presented;
    return SDL_RenderPresent(renderer);
}
}

namespace ss6 {
class ObservedScene : public NativeScene {
public:
    using NativeScene::NativeScene;
    void paint(const NativeMatch& match,std::span<uint8_t> rgba,const EffectPainter& effects,unsigned nextDepth,
               const ObjectDrawQueue* presentation=nullptr) {
        // Inspect the same simulation snapshot used by the shipping scene.
        // A shared sprite can otherwise mask a wrong callback or a lost edge.
        NativeScene::paint(match,rgba,effects,nextDepth,presentation);
        if(presented!=1)return;
        std::cout<<"observed "<<match.updates;
        for(unsigned i=0;i<2;++i) {
            const auto& fighter=match.fighter(i);
            const auto& a=fighter.actor;
            const auto& body=fighter.body.timeline;
            std::cout<<' '<<a.stateTable()<<' '<<a.stateIndex()<<' '<<body.action().id()
                     <<' '<<body.clock().step<<' '<<a.fieldA30<<' '<<fighter.hits<<' '<<fighter.guards
                     <<' '<<a.timers[0]<<' '<<a.timers[1];
        }
        const auto& c=match.battle().camera;
        std::cout<<'\n'<<"camera "<<c.shakeY48<<' '<<c.projectionY<<' '
                 <<match.combatStage().camera.projectionY<<'\n';
    }
};
}

// Compile the unmodified production event handler into this separate test
// program. SDL wrappers schedule events and read the actual rendered frame.
#define NativeScene ObservedScene
#define SDL_CreateWindowAndRenderer makeTestWindow
#define SDL_RenderPresent inspectPresent
#define main viewerMain
#include "viewer.cpp"
#undef main
#undef SDL_RenderPresent
#undef SDL_CreateWindowAndRenderer
#undef NativeScene

int main(int argc, char** argv) {
    if (argc < 5) {
        std::cerr << "usage: sdl-key-loop ASSET_DIR INIT_SCRIPT OUTPUT_BMP KEY...\n";
        return 2;
    }
    output = argv[3];
    versus=std::string(argv[4])=="--versus";
    int firstKey=versus?5:4;
    std::vector<std::string> args{argv[0], "--mode", versus?"versus":"trial", "--assets", argv[1],
                                   versus?"--match-replay":"--trial-script", argv[2], "--smoke-updates", "2"};
    while(versus&&firstKey+1<argc) {
        const std::string flag=argv[firstKey];
        if(flag!="--p1-spirit"&&flag!="--p2-spirit")break;
        args.emplace_back(argv[firstKey++]);args.emplace_back(argv[firstKey++]);
    }
    keys.assign(argv+firstKey,argv+argc);
    std::vector<char*> raw;
    for (auto& arg : args) raw.push_back(arg.data());
    raw.push_back(nullptr);
    const int result = viewerMain(static_cast<int>(args.size()), raw.data());
    return result != 0 ? result : presented == 2 ? 0 : 1;
}
