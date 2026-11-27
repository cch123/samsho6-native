#pragma once
#include "character_draw.hpp"
#include "scheduled_opening.hpp"
#include "color_edit.hpp"
#include <span>

namespace ss6 {
//The24 cache entries borrow the same reservation/use words as captions.
//RGBA values retain PS2 channel/alpha units; they are not display RGB255.
class CharacterPaletteBank {
public:
    explicit CharacterPaletteBank(const std::filesystem::path&);
    std::array<uint16_t,1024> raw16{};
    std::array<uint32_t,1024> raw32{},format{},rgba{};
    int resolve(uint32_t key,unsigned bank,EffectPalettes&);
    void colorize(uint32_t flags,uint32_t fadeColor,uint32_t fadeAmount,std::span<const uint16_t,1024> tones);
    const std::vector<uint8_t>& source() const {return source_;}
    // 115f08 clears the first colour of a group in its source table, so the arena is mutable.
    std::vector<uint8_t>& mutableSource() {return source_;}
    // Sources of 115d40 for keys with an owner bit (10000 / 20000): the edit
    // block of the save image and, with 40000, the runtime tables 3ec740 /
    // 3f28c0. Unbound, such keys are rejected.
    void bindEdited(const ColorEditTables* tables,SystemData* data,std::array<std::span<uint8_t>,2> runtime) {
        editTables_=tables;editData_=data;runtime_=runtime;
    }
private:
    std::vector<uint8_t> source_;
    const ColorEditTables* editTables_=nullptr;
    SystemData* editData_=nullptr;
    std::array<std::span<uint8_t>,2> runtime_{};
};
struct CharacterTileQuad {
    //Four original108910 vertices: x,y,z,u,v,color. The rotated layout
    //uses a different vertex order; preserving it matters for UV sampling.
    std::array<uint32_t,24> vertices{};
    // Optional 2x artwork for this 16x16 group. The image table owns the
    // samples for the lifetime of CharacterTiles, including the paint pass.
    const uint8_t* inkGroup=nullptr;
    bool inkFlipX=false,inkFlipY=false;
    uint32_t paletteArgument=0,blendMode=0,additive=0;
};
struct CharacterTileState {
    std::array<uint8_t,131072> atlas{}; //512x512, packed4bpp, retained each frame
    uint32_t groups=0,depthCounter=0,primitiveColor=0,blendMode=0;
    uint32_t disabled=0,tintFlags=0,tintColor=0,tintAmount=0;
    void beginFrame(){groups=depthCounter=0;} //Storage and palette residency persist.
};
class CharacterTiles {
public:
    CharacterTiles(std::filesystem::path assets,std::array<unsigned,3> slots);
    CharacterPaletteBank palettes;
    void submit(const CharacterSprite&,EffectPalettes&,CharacterTileState&,std::vector<CharacterTileQuad>&);
    void submitObject(CharacterDraws&,CharacterDrawState&,const ObjectDrawQueue::Record&,
                      const CharacterDrawContext&,EffectPalettes&,CharacterTileState&,std::vector<CharacterTileQuad>&);
private:
    struct Resource {std::vector<uint8_t> idx,map,chr;};
    std::filesystem::path assets_;
    std::array<unsigned,3> slots_;
    struct InkImage {unsigned width=0,height=0;std::vector<size_t> offsets;};
    std::map<unsigned,InkImage> inkImages_;
    std::vector<uint8_t> inkData_;
    std::map<unsigned,Resource> resources_;
    const Resource& resource(unsigned slot);
};
}
