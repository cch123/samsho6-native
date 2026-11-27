#pragma once
#include "character_tiles.hpp"
#include "effect_snapshot.hpp"
#include "stage_item_notices.hpp"
#include <functional>

namespace ss6 {
class NativeMatch;
class NativeScene {
public:
    using EffectPainter=std::function<void(const EffectDraw&)>;
    // Called before each battle draw with its depth key, and finally with
    // infinity: lets the caller paint stage strips that lie in front of the
    // fighters' plane in depth order with the character and effect draws.
    std::function<void(float)> depthHook;
    static constexpr int width=640,height=448;
    explicit NativeScene(const std::filesystem::path& assets,std::array<unsigned,3> resources={0,0,51});
    // The RGBA destination already contains the stage. Effects paint into
    // that same destination at their position in the original queue.
    void paint(const NativeMatch&,std::span<uint8_t> rgba,const EffectPainter&,unsigned nextDepth=100,
               const ObjectDrawQueue* presentation=nullptr);
    // Owner-bit palette keys (10000 / 20000): the edit block of the save image (115d40).
    void bindEdited(const ColorEditTables* tables,SystemData* data) {tiles_.palettes.bindEdited(tables,data,{});}
    // Forget the resident CLUT rows, so a colour edited since the last frame is read again.
    void resetPalettes() {cache_={};cache_[0].fill(0xffffffff);}
    void paint(const ObjectDrawQueue&,const CharacterDrawContext&,const EffectPalettes&,
               std::span<const uint16_t,1024> tones,std::span<uint8_t> rgba,const EffectPainter&,uint32_t backdrop=0,
               std::span<const StageItemNoticeQuad> notices={},unsigned nextDepth=100);
private:
    std::array<unsigned,3> resources_;
    std::vector<uint8_t> inkIdle_;
    CharacterDraws draws_;
    CharacterTiles tiles_;
    EffectBank effects_;
    StageItemNoticeArt noticeArt_;
    CharacterDrawState drawState_;
    CharacterTileState tileState_;
    EffectPalettes cache_{};
    std::vector<CharacterTileQuad> quads_;
    std::array<size_t,511> ends_{};
};
}
