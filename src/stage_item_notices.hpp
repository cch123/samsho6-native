#pragma once
#include "stage_camera.hpp"
#include <filesystem>
#include <span>

namespace ss6 {
struct StageItemNoticeQuad {
    float left=0,top=0,right=0,bottom=0,depth=0;
    int u=0,v=0,width=0,height=0,alpha=0;
};
enum class StageItemLabel { Heal, DefenseDown, Bomb };
class StageItemNotices {
public:
    bool show(StageItemLabel label,int x);
    bool heal(int x){return show(StageItemLabel::Heal,x);} // Only an allocated heal plays common SE65.
    void visit(uint32_t rawDelta,const StageCamera&,std::array<int,2> groundedWeaponX={-1,-1},
               std::array<bool,2> cpu={false,false},unsigned depthCounter=100);
    std::span<const StageItemNoticeQuad> draws() const {return {draws_.data(),drawCount_};}
private:
    struct Notice {
        int kind=-1;float x=0,y=0;
        uint32_t elapsed=0,animation=0;
    };
    // The ten records are shared by item labels and weapon markers.
    // Dropping an eleventh label must also suppress its associated sound.
    std::array<Notice,10> pool_{};
    std::array<int,2> weaponSlot_{-1,-1};
    std::array<StageItemNoticeQuad,10> draws_{};
    unsigned drawCount_=0;
    int allocate(int kind,int x,int y);
};
class StageItemNoticeArt {
public:
    explicit StageItemNoticeArt(const std::filesystem::path&);
    void paint(const StageItemNoticeQuad&,std::span<uint8_t> rgba) const;
private:
    std::vector<uint8_t> atlas_;
};
}
