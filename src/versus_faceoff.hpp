#pragma once
#include "input_features.hpp"
#include "sound_selection.hpp"
#include <filesystem>
#include <vector>

namespace ss6 {
struct VersusFaceoff {
    int frame=0,background=0,drawFrame=0,drawBackground=0;
    bool white=false,flashNext=false,requested=false,complete=false;
    unsigned transitionTick=0;
    void tick(const std::array<uint32_t,2>& physicalPressed,
              const std::array<unsigned,2>& characters,SoundSelection&);
};

class VersusFaceoffArt {
public:
    VersusFaceoffArt(const std::filesystem::path&,const std::array<unsigned,2>& characters);
    void paint(const VersusFaceoff&,std::span<uint8_t>) const;
private:
    struct Rect {unsigned slot,alpha;int x0,y0,x1,y1,u0,v0,u1,v1;};
    struct Frame {unsigned background;std::vector<unsigned> rects;};
    struct Texture {int size=0;std::vector<uint8_t> indices;std::array<uint32_t,256> clut{};};
    std::vector<Rect> rects_;
    std::vector<Frame> frames_;
    std::array<Texture,13> textures_{};
    void draw(const Rect&,std::span<uint8_t>) const;
};
}
