#pragma once
#include "object_frame.hpp"
#include "stage_camera.hpp"
#include "scalar_float.hpp"
#include <filesystem>
#include <map>
#include <string>
#include <vector>

namespace ss6 {
// Resource "99a" of the ending scenes (182968 binds it to both slots). Its
// files carry the suffix 99a; the other resources are numbered 00..51.
constexpr unsigned endingObjectResource=0x99a;
inline std::filesystem::path characterResourcePath(const std::filesystem::path& assets,const char* kind,unsigned resource) {
    if(resource==endingObjectResource)return assets/(std::string(kind)+"_99a.bin");
    return assets/(std::string(kind)+"_"+(resource<10?"0":"")+std::to_string(resource)+".bin");
}
}

namespace ss6 {
//Arguments at the original121b80 boundary, before tile/palette resolution
//and GS packet construction. Coordinates use the original640-wide space.
struct CharacterSprite {
    uint32_t slot=0,palette=0,image=0,flags=0,shadow=0;
    ScalarFloat x{},y{},z{},scaleX{},scaleY{};
    uint32_t mode=0,color=0,contextFlags=0,contextColor=0;
    //These globals belong to this submission. Later queued objects can
    //overwrite them before a buffered native backend consumes this sprite.
    uint32_t additive=0;
    ScalarFloat depthOffset{};
};
struct CharacterDrawState {
    uint32_t flags=0,color=0,primitiveColor=0,mode=0,additive=0;
    ScalarFloat depthOffset{};
};
struct CharacterDrawContext {
    const StageCamera& camera;
    //1208b0 reads the current globals, not queue138/13c. Common slot2
    //does not exclude either player's clock when deciding whether to dim.
    std::array<uint32_t,2> clockFlags{};
    int32_t focus=-2,stage=0;
};
struct CharacterPlacement {
    ScalarFloat x{}, y{}, scale{};
    bool mirrored=false;
};
class CharacterDraws {
public:
    CharacterDraws(std::filesystem::path assets,std::array<unsigned,3> resources)
        :assets_(std::move(assets)),slots_(resources) {}
    void submit(const ObjectDrawQueue::Record&,const CharacterDrawContext&,
                CharacterDrawState&,std::vector<CharacterSprite>&,CharacterPlacement* placement=nullptr);
private:
    struct Resource {std::vector<uint8_t> aid,act,pil;};
    std::filesystem::path assets_;
    std::array<unsigned,3> slots_;
    std::map<unsigned,Resource> resources_;
    const Resource& resource(unsigned slot);
};
}
