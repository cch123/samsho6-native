#include "versus_draw_stage.hpp"
#include <utility>

namespace ss6 {
VersusDrawStage::VersusDrawStage(const std::filesystem::path& assets)
    :raster_(assets) {
    const auto bytes=readStageFile(assets/"versus_draw_stage.bin",32*1024*1024);
    StageReader input{bytes};
    if(input.word()!=0x47545356 || input.word()!=1)throw std::runtime_error("Invalid draw-stage header");
    const auto count=input.word(),unique=input.word();
    if(count!=336 || unique>bytes.size()/60)throw std::runtime_error("Invalid draw-stage table dimensions");
    strips_.resize(unique);
    for(auto& s:strips_) {
        s.slot=input.word();s.color=input.word();const auto n=input.word();
        if(s.slot<4||s.slot>7 || n<3||n>128 || (s.color!=0xffffffffu&&s.color!=0x60000000))
            throw std::runtime_error("Invalid draw-stage strip");
        s.vertices.resize(n);
        for(auto& v:s.vertices) {
            v={input.value(),input.value(),input.value(),input.value()};
            if(std::abs(v.x)>32768 || std::abs(v.y)>32768 || std::abs(v.u)>2 || std::abs(v.v)>2)
                throw std::runtime_error("Invalid draw-stage coordinates");
        }
    }
    frames_.resize(count);
    for(auto& frame:frames_) {
        const auto n=input.word();
        if(n>input.bytes.size()/4)throw std::runtime_error("Truncated stage draw list");
        frame.resize(n);
        for(auto& id:frame) {id=input.word();if(id>=unique)throw std::runtime_error("Invalid stage draw index");}
    }
    if(!input.bytes.empty())throw std::runtime_error("Trailing draw-stage data");
}

void VersusDrawStage::paint(unsigned tick,std::span<uint8_t> dest) const {
    if(dest.size()!=640*480*4)throw std::invalid_argument("Expected a 640x480 stage framebuffer");
    const auto& frame=frames_.at(tick);
    StageRaster::clear(dest);
    // 138880 sets tone 1 for entries 256..1023 before this frame's upload,
    // including both of the stage banks used by all four texture surfaces.
    for(auto id:frame) {
        const auto& s=strips_[id];
        raster_.paint(dest,s.slot,s.color,s.vertices,raster_.grayPalette());
    }
}
}
