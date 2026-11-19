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
    static constexpr int width=640,height=448;
    explicit NativeScene(const std::filesystem::path& assets,std::array<unsigned,3> resources={0,0,51});
    // The RGBA destination already contains the stage. Effects paint into
    // that same destination at their position in the original queue.
    void paint(const NativeMatch&,std::span<uint8_t> rgba,const EffectPainter&,unsigned nextDepth=100,
               const ObjectDrawQueue* presentation=nullptr);
    void paint(const ObjectDrawQueue&,const CharacterDrawContext&,const EffectPalettes&,
               std::span<const uint16_t,1024> tones,std::span<uint8_t> rgba,const EffectPainter&,uint32_t backdrop=0,
               std::span<const StageItemNoticeQuad> notices={},unsigned nextDepth=100);
private:
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
