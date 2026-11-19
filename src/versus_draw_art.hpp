#pragma once
#include "native_scene.hpp"

namespace ss6 {
class VersusDrawArt {
public:
    explicit VersusDrawArt(const std::filesystem::path& assets);
    // The caller supplies the complete stage and applies the global screen
    // fade afterwards. Skipping ahead advances the title clock only.
    void paint(unsigned frame,unsigned objectTick,unsigned characterSlot,std::span<uint8_t> rgba);
private:
    NativeScene scene_;
    ObjectDrawQueue queue_;
    std::vector<AuxiliaryObject> poses_;
    std::vector<uint8_t> atlas_;
    std::array<std::array<std::array<uint8_t,4>,16>,2> palettes_{};
    std::array<uint16_t,1024> tones_{};
    void caption(std::span<uint8_t>,unsigned palette,int u,int v,int texWidth,int texHeight,
                 int x,int y,int width,int height,int alpha) const;
};
}
