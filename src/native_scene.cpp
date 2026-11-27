#include "native_scene.hpp"
#include "asset_files.hpp"
#include <fstream>
#include <limits>
#include "native_match.hpp"
#include <algorithm>
#include <bit>
#include <cmath>
#include <stdexcept>

namespace ss6 {
namespace {
// 1419b0 submits a solid rectangle at z=45 with order offset 256.
// GS TEST uses GEQUAL, so the referee can disappear while a fighter in
// front of the same rectangle and an overlapping hit spark remain visible.
constexpr float backdropDepth=9995756.0f;
struct Texel {std::array<int,3> rgb{};int alpha=0;};

// The sheet has a common foot anchor at (128,236). Its 256 texels cover
// 128 original world units at the native two screen pixels per world unit.
void paintInkIdle(const std::vector<uint8_t>& atlas,unsigned pose,unsigned palette,uint32_t tint,
                  const CharacterPlacement& p,std::span<uint8_t> rgba) {
    const float scale=std::bit_cast<float>(p.scale.bits);
    if(scale<=0)return;
    const float left=std::bit_cast<float>(p.x.bits)-128*scale;
    const float top=std::bit_cast<float>(p.y.bits)-236*scale;
    const int rows=int(rgba.size()/(NativeScene::width*4));
    for(int y=std::max(0,int(std::floor(top)));y<std::min(rows,int(std::ceil(top+256*scale)));++y) {
        const int v=int(std::floor((y+0.5f-top)/scale));
        if(v<0||v>=256)continue;
        for(int x=std::max(0,int(std::floor(left)));x<std::min(NativeScene::width,int(std::ceil(left+256*scale)));++x) {
            int u=int(std::floor((x+0.5f-left)/scale));
            if(u<0||u>=256)continue;
            if(p.mirrored)u=255-u;
            const auto* texel=&atlas[((pose*256+v)*256+u)*4];
            if(!texel[3])continue;
            auto* dest=&rgba[(y*NativeScene::width+x)*4];
            std::array<unsigned,3> color={texel[0],texel[1],texel[2]};
            // Give alternate costumes a blue sash while retaining skin and steel.
            if(palette && color[0]>2*color[1] && color[0]>3*color[2])
                std::swap(color[0],color[2]);
            for(int c=0;c<3;++c) {
                const unsigned channel=(tint>>(8*c))&255;
                dest[c]=uint8_t(std::min(255u,color[c]*channel/128+dest[c]*(255-texel[3])/255));
            }
        }
    }
}
void paintQuad(const CharacterTileQuad& q,const CharacterTileState& state,const CharacterPaletteBank& palettes,
               std::span<uint8_t> rgba,unsigned& alternativeCount,bool backdrop) {
    const bool highlight=q.blendMode==3;
    if((q.blendMode!=0&&!highlight)||q.additive>1) throw std::runtime_error("Unsupported character GS blend state");
    const int fixedAlpha=(q.paletteArgument>>8)&255;
    // 108c40 requests one alternate CLUT per quad. 117608 allows 72 per
    // frame, then uses the original palette. 117678 preserves entry zero
    // and replaces the alpha of *all* other entries, including black ones.
    const bool replaceAlpha=fixedAlpha<128 && alternativeCount<72;
    if(replaceAlpha) ++alternativeCount;
    // The GS depth test follows allocation of the alternate palette.
    if(backdrop&&std::bit_cast<float>(q.vertices[2])<backdropDepth)return;
    std::array<Texel,16> texels;
    const uint32_t mod=q.vertices[5];
    const int vertexAlpha=mod>>24;
    for(unsigned i=0;i<texels.size();++i) {
        const auto color=palettes.rgba.at((q.paletteArgument&255)*16+i);
        const int textureAlpha=replaceAlpha && i?fixedAlpha:int(color>>24);
        auto& texel=texels[i];
        // TEX0 TCC=1: HIGHLIGHT2 adds vertex alpha to modulated RGB,
        // but its output alpha comes directly from the selected CLUT.
        texel.alpha=highlight?textureAlpha:std::min(255,textureAlpha*vertexAlpha/128);
        for(unsigned c=0;c<3;++c) {
            const int product=int((color>>(8*c))&255)*int((mod>>(8*c))&255);
            texel.rgb[c]=std::min(255,product/128+(highlight?vertexAlpha:0));
        }
    }
    const auto f=[&](unsigned i){return double(std::bit_cast<float>(q.vertices[i]));};
    const double x0=f(0),y0=f(1),x1=f(18),y1=f(19);
    if(x0==x1||y0==y1) return;
    // Transposed tiles swap which strip edge carries U. Keep signed axes
    // for the half-open bounds and reversed UVs of a mirrored strip.
    const bool acrossFirst=f(6)!=x0;
    const unsigned xVertex=acrossFirst?6:12,yVertex=acrossFirst?12:6;
    const double u0=f(3),v0=f(4),ux=f(xVertex+3)-u0,vx=f(xVertex+4)-v0;
    const double uy=f(yVertex+3)-u0,vy=f(yVertex+4)-v0;
    const int left=int(std::clamp(std::floor(std::min(x0,x1)),0.,double(NativeScene::width)));
    const int right=int(std::clamp(std::ceil(std::max(x0,x1)),0.,double(NativeScene::width)));
    const double framebufferHeight=double(rgba.size()/(4*NativeScene::width));
    const int top=int(std::clamp(std::floor(std::min(y0,y1)),0.,framebufferHeight));
    const int bottom=int(std::clamp(std::ceil(std::max(y0,y1)),0.,framebufferHeight));
    for(int y=top;y<bottom;++y) {
        const auto ty=(y+.5-y0)/(y1-y0);
        if(ty<0||ty>=1)continue;
        for(int x=left;x<right;++x) {
            const auto tx=(x+.5-x0)/(x1-x0);
            if(tx<0||tx>=1)continue;
            const int u=std::clamp(int((u0+tx*ux+ty*uy)*512),0,511);
            const int v=std::clamp(int((v0+tx*vx+ty*vy)*512),0,511);
            const auto index=(state.atlas[v*256+u/2]>>((u%2)*4))&15;
            Texel texel=texels[index];
            if(q.inkGroup) {
                // Reuse the original GS UV orientation, palette residency, per-seat
                // recolours and blend state. Only the intra-tile sampling is denser.
                int hx=std::clamp(int((u0+tx*ux+ty*uy)*1024),0,1023)%32;
                int hy=std::clamp(int((v0+tx*vx+ty*vy)*1024),0,1023)%32;
                if(q.inkFlipX)hx=31-hx;
                if(q.inkFlipY)hy=31-hy;
                const uint8_t* sample=q.inkGroup+2*(hy*32+hx);
                const auto& a=texels[sample[0]&15];
                const auto& b=texels[sample[0]>>4];
                const int mix=sample[1]&15,coverage=sample[1]>>4;
                texel.alpha=((15-mix)*a.alpha+mix*b.alpha)*coverage/225;
                for(int c=0;c<3;++c) {
                    const int color=((15-mix)*a.rgb[c]+mix*b.rgb[c]+7)/15;
                    texel.rgb[c]=q.additive?color*coverage/15:color;
                }
            }
            if(!texel.alpha)continue;
            auto pixel=rgba.subspan((y*NativeScene::width+x)*4,3);
            for(unsigned c=0;c<3;++c) {
                const int dst=pixel[c],src=texel.rgb[c];
                const int value=q.additive?dst+src:dst+(((src-dst)*texel.alpha)>>7);
                pixel[c]=uint8_t(std::clamp(value,0,255));
            }
        }
    }
}
}

NativeScene::NativeScene(const std::filesystem::path& assets,std::array<unsigned,3> resources)
    :resources_(resources),draws_(assets,resources),tiles_(assets,resources),effects_(assets),noticeArt_(assets) {
    const auto path=resolveAsset(assets/"haohmaru_idle.rgba");
    if(std::filesystem::exists(path)) {
        std::ifstream input(path,std::ios::binary|std::ios::ate);
        constexpr size_t bytes=9*256*256*4;
        if(input.tellg()!=std::streamoff(bytes))throw std::runtime_error("Invalid ink idle atlas size");
        inkIdle_.resize(bytes);
        input.seekg(0);
        if(!input.read(reinterpret_cast<char*>(inkIdle_.data()),bytes))throw std::runtime_error("Truncated ink idle atlas");
    }
    cache_[0].fill(0xffffffff);
}
void NativeScene::paint(const NativeMatch& match,std::span<uint8_t> rgba,const EffectPainter& paintEffect,unsigned nextDepth,
                        const ObjectDrawQueue* presentation) {
    if(rgba.size()!=size_t(width)*height*4)throw std::invalid_argument("Expected a 640x448 battle stage");
    if(match.mikiriWhiteFrame()){std::fill(rgba.begin(),rgba.end(),255);return;}
    const auto& battle=match.battle();
    const auto& gauges=battle.gauges;
    if(const auto& edited=match.editedPalettes())
        tiles_.palettes.bindEdited(&edited->tables,&match.system(),{edited->runtime[0],edited->runtime[1]});
    // The super's startup highlights its owner after the queue was submitted.
    // Sample the displayed focus here so both the opponent and referee use
    // the same value seen by the original sprite callback.
    const CharacterDrawContext context{battle.camera,{gauges.words910[2],gauges.words910[3]},gauges.focus46a948,int(battle.matchEnd.metadataStage04)};
    paint(presentation?*presentation:match.objectDraws(),context,battle.paletteState,gauges.paletteTones,rgba,paintEffect,match.battleBackdropColor(),battle.itemNotices.draws(),nextDepth);
}
void NativeScene::paint(const ObjectDrawQueue& queue,const CharacterDrawContext& context,const EffectPalettes& battlePalettes,
                       std::span<const uint16_t,1024> tones,std::span<uint8_t> rgba,const EffectPainter& paintEffect,uint32_t backdrop,
                       std::span<const StageItemNoticeQuad> notices,unsigned nextDepth) {
    if(rgba.size()!=size_t(width)*height*4 && rgba.size()!=size_t(width)*480*4)
        throw std::invalid_argument("Expected a 640x448 or 640x480 RGBA stage");
    if(backdrop) {
        // All stage-zero strips are behind this rectangle. The host footer
        // occupies a separate viewport below the battle framebuffer.
        for(size_t i=0;i<rgba.size();i+=4) {
            rgba[i]=uint8_t(backdrop);rgba[i+1]=uint8_t(backdrop>>8);
            rgba[i+2]=uint8_t(backdrop>>16);rgba[i+3]=255;
        }
    }
    tileState_.beginFrame();
    tileState_.depthCounter=100; // 10722c seeds independent character order each frame.
    quads_.clear();
    cache_[1].fill(0);
    cache_[2]=battlePalettes[2];
    // Caption allocation reuses character CLUT memory. A key must be
    // invalidated even when the same character needs its colors next frame.
    for(unsigned i=0;i<cache_[2].size();++i)if(cache_[2][i])cache_[0][i]=0xffffffff;
    struct IdleDraw {size_t row,firstBody;CharacterPlacement placement;unsigned pose,palette;uint32_t tint;};
    std::vector<IdleDraw> idleDraws;
    size_t row=0;
    for(const auto handle:queue.sorted()) {
        const auto& object=queue.slots.at(handle-1);
        const auto slot=object[0xc/4],action=object[0x24/4],pose=object[0x28/4];
        // In resource 00 the nine armed idle bodies are images 0,2,...,16.
        // Their layered replacements take precedence over the early whole-pose preview.
        if(!inkIdle_.empty() && object[0x144/4]==0 && slot<2 && resources_[slot]==0 &&
           (action==0 || action==2) && pose<9 && !tiles_.hasInkImage(pose*2) && !(object[0x104/4]&2)) {
            // Preserve the original shadow, CLUT allocation and depth visits. Substitute
            // the illustration once where the first visible body tile would be painted.
            drawState_.primitiveColor=tileState_.primitiveColor;
            std::vector<CharacterSprite> sprites;
            CharacterPlacement placement;
            draws_.submit(object,context,drawState_,sprites,&placement);
            bool first=true;
            for(const auto& sprite:sprites) {
                if(first && !sprite.shadow) {
                    first=false;
                    // Full rage cycles through neutral modulation once per pulse.
                    // Keep the same silhouette across the cycle and tint its RGB.
                    const bool rageModulation=(sprite.contextFlags&0x40010000u)==0x40010000u &&
                        (sprite.color>>24)==255 && (sprite.color&255)<=128 &&
                        ((sprite.color>>8)&255)<=128 && ((sprite.color>>16)&255)<=128;
                    if(sprite.mode==1 && (sprite.color==0xff808080 || rageModulation) && sprite.palette<=4)
                        idleDraws.push_back({row,quads_.size(),placement,pose,sprite.palette,sprite.color});
                }
                tiles_.submit(sprite,cache_,tileState_,quads_);
            }
            tileState_.primitiveColor=drawState_.primitiveColor;
        } else if(object[0x144/4]==0)tiles_.submitObject(draws_,drawState_,object,context,cache_,tileState_,quads_);
        else if(object[0x144/4]!=1)throw std::runtime_error("Unexpected battle draw kind");
        ends_.at(row++)=quads_.size();
    }
    // The source resolves and uploads palettes after packet construction.
    // The second pass preserves mixed object/effect order during painting.
    tiles_.palettes.colorize(tileState_.tintFlags,tileState_.tintColor,tileState_.tintAmount,tones);
    // Labels are submitted by priority 20 after the arena and before the
    // fighters. Their GS depth places them behind the frontmost floor items.
    size_t notice=0;
    const auto paintNoticesThrough=[&](float depth){
        if(depthHook)depthHook(depth);
        while(notice<notices.size()&&notices[notice].depth+float(nextDepth-100)<=depth)
            noticeArt_.paint(notices[notice++],rgba);
    };
    unsigned alternateCount=0;
    size_t firstQuad=0,idleIndex=0;
    row=0;
    for(const auto handle:queue.sorted()) {
        const auto& object=queue.slots.at(handle-1);
        while(firstQuad<ends_[row]) {
            const auto& quad=quads_[firstQuad++];
            paintNoticesThrough(std::bit_cast<float>(quad.vertices[2]));
            if(idleIndex<idleDraws.size() && idleDraws[idleIndex].row==row &&
               firstQuad>idleDraws[idleIndex].firstBody) {
                const auto& idle=idleDraws[idleIndex];
                if(firstQuad==idle.firstBody+1 && (!backdrop || std::bit_cast<float>(quad.vertices[2])>=backdropDepth))
                    paintInkIdle(inkIdle_,idle.pose,idle.palette,idle.tint,idle.placement,rgba);
                continue;
            }
            paintQuad(quad,tileState_,tiles_.palettes,rgba,alternateCount,backdrop!=0);
        }
        if(object[0x144/4]==1) {
            const auto draw=decodeEffectDraw(object,effects_);
            // 123a38 uses 114e40: effects have no character-order offset.
            const float depth=10000000.0f-draw.state.z*100.0f;
            paintNoticesThrough(depth);
            if(!backdrop||depth>=backdropDepth)paintEffect(draw);
        }
        if(idleIndex<idleDraws.size() && idleDraws[idleIndex].row==row)++idleIndex;
        ++row;
    }
    while(notice<notices.size())noticeArt_.paint(notices[notice++],rgba);
    if(depthHook)depthHook(std::numeric_limits<float>::infinity());
}
}
