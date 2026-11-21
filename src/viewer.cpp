#include <SDL3/SDL.h>
#include <SDL3/SDL_main.h>
#include "action_runtime.hpp"
#include "judgment.hpp"
#include "collision.hpp"
#include "combat_decision.hpp"
#include "contact_trial.hpp"
#include "trial_script.hpp"
#include "local_versus.hpp"
#include "arcade_art.hpp"
#include "arcade_presentation.hpp"
#include "fighter_roster.hpp"
#include "character_select_art.hpp"
#include "console_title_art.hpp"
#include "vs_curtain.hpp"
#include "combat_audio.hpp"
#include "versus_audio_output.hpp"
#include "versus_gamepads.hpp"
#include "console_versus_art.hpp"
#include "combat_stage.hpp"
#include "versus_result_art.hpp"
#include "versus_draw_art.hpp"
#include "versus_result_text.hpp"
#include "native_scene.hpp"
#include <cmath>
#include <algorithm>
#include <bit>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <memory>
#include <optional>
#include <stdexcept>
#include <string>
#include <vector>

using Bytes = std::vector<uint8_t>;
namespace fs = std::filesystem;

Bytes readFile(const fs::path& path) {
    std::ifstream in(path, std::ios::binary | std::ios::ate);
    if (!in) throw std::runtime_error("Cannot open " + path.string());
    auto size = in.tellg();
    if (size < 0 || size > 64 * 1024 * 1024) throw std::runtime_error("Invalid asset size");
    Bytes result(static_cast<size_t>(size));
    in.seekg(0);
    if (!in.read(reinterpret_cast<char*>(result.data()), size)) throw std::runtime_error("Short read");
    return result;
}

uint32_t le(const Bytes& bytes, size_t offset, size_t count) {
    if (count > 4 || offset > bytes.size() || count > bytes.size() - offset)
        throw std::runtime_error("Truncated resource field");
    uint32_t value = 0;
    for (size_t i = 0; i < count; ++i) value |= uint32_t(bytes[offset + i]) << (i * 8);
    return value;
}

struct Frame { int width, height; Bytes rgba; };

void writeRgba(const fs::path& path,const Frame& frame) {
    std::ofstream out(path,std::ios::binary);
    for(uint32_t n:{uint32_t(frame.width),uint32_t(frame.height)})
        for(unsigned j=0;j<32;j+=8)out.put(char(n>>j));
    out.write(reinterpret_cast<const char*>(frame.rgba.data()),std::streamsize(frame.rgba.size()));
    if(!out)throw std::runtime_error("Cannot write frame: "+path.string());
}

class CharacterSample {
    Bytes tiles, maps, indices, palettes, parts;
public:
    std::vector<unsigned> supported;
    explicit CharacterSample(const fs::path& dir)
        : tiles(readFile(dir / "chr_00.bin")), maps(readFile(dir / "map_00.bin")),
          indices(readFile(dir / "idx_00.bin")), palettes(readFile(dir / "pal_all.bin")),
          parts(readFile(dir / "pil_00.bin")) {
        if (indices.size() % 4 || tiles.size() % 32 || palettes.size() < 32)
            throw std::runtime_error("Unsupported sample asset layout");
        for (size_t i = 0; i < indices.size() / 4; ++i) {
            uint32_t entry = le(indices, i * 4, 4);
            // Preserve the legacy raw-cell view. The composed idle additionally
            // uses bank 1 for its weapon; other visual states remain unverified.
            if ((entry >> 24) != 0 || (entry == 0 && i != 0)) continue;
            uint32_t w = le(maps, entry, 1), h = le(maps, entry + 1, 1);
            if (w && h && w % 2 == 0 && h % 2 == 0) supported.push_back(unsigned(i));
        }
        if (supported.empty()) throw std::runtime_error("No supported sample frames");
    }

    Frame decode(unsigned index) const {
        uint32_t entry = le(indices, size_t(index) * 4, 4);
        const auto bank = entry >> 24;
        if (bank > 1&&bank!=26) throw std::runtime_error("Palette state outside the admitted character subset");
        // Original 0x121cd8/0x121d34: palette bank in the upper five bits of
        // metadata, map offset in the low 24 bits. Bank 26 is the far-slash
        // effect palette; resource00's ordinary palette group starts at zero.
        entry &= 0x00ffffff;
        unsigned tw = le(maps, entry, 1), th = le(maps, entry + 1, 1);
        if (!tw || !th || tw % 2 || th % 2) throw std::runtime_error("Unsupported tile-map dimensions");
        if (uint64_t(entry) + 2 + uint64_t(tw) * th * 3 > maps.size())
            throw std::runtime_error("Tile map exceeds resource");
        Frame frame{int(tw * 8), int(th * 8), Bytes(size_t(tw) * th * 64 * 4)};
        for (unsigned by = 0; by < th; by += 2) {
            for (unsigned bx = 0; bx < tw; bx += 2) {
                // Observed map storage is 2x2 tile groups, not row-major tiles.
                size_t group = size_t(by) * tw + bx * 2;
                for (unsigned cell = 0; cell < 4; ++cell) {
                    uint32_t tile = le(maps, entry + 2 + (group + cell) * 3, 3);
                    if (uint64_t(tile) * 32 + 32 > tiles.size()) throw std::runtime_error("Tile exceeds graphics data");
                    unsigned tx = bx + cell % 2, ty = by + cell / 2;
                    for (unsigned y = 0; y < 8; ++y) {
                        for (unsigned x = 0; x < 8; ++x) {
                            uint8_t packed = tiles[size_t(tile) * 32 + y * 4 + x / 2];
                            unsigned color = (packed >> ((x % 2) * 4)) & 15;
                            uint32_t c = le(palettes, (bank*16+color) * 2, 2);
                            size_t out = (size_t(ty * 8 + y) * frame.width + tx * 8 + x) * 4;
                            // This sample's palette is ARGB1555. The separately
                            // decoded 32-bit UI palettes use another channel layout.
                            frame.rgba[out] = uint8_t(((c >> 10) & 31) * 255 / 31);
                            frame.rgba[out + 1] = uint8_t(((c >> 5) & 31) * 255 / 31);
                            frame.rgba[out + 2] = uint8_t((c & 31) * 255 / 31);
                            frame.rgba[out + 3] = c & 0x8000 ? 255 : 0;
                        }
                    }
                }
            }
        }
        return frame;
    }

    Frame compose(const ss6::ActionRecord& record, bool mirror=false) const {
        constexpr int width = 200, height = 140, originX = 90, originY = 128;
        Frame canvas{width,height,Bytes(width*height*4)};
        // 0x1215f0 scans five one-based PIL references for each of 16 layers.
        // Keep slot order within a layer; sorting by image number is incorrect.
        for (unsigned layer=0; layer<16; ++layer) for (auto reference : record.parts) {
            if (!reference) continue;
            if (reference < 0) throw std::runtime_error("Negative PIL reference");
            const size_t offset = size_t(reference-1)*16;
            const auto flags = le(parts,offset+12,2);
            if ((flags&15) != layer) continue;
            if ((flags&0x7ff0) != 0x10 || le(parts,offset+8,4) != 0xff808080)
                throw std::runtime_error("PIL effect/tint outside the implemented action subset");
            const auto image = std::bit_cast<int16_t>(uint16_t(le(parts,offset,2)));
            if (!image) continue;
            if (image < 0) throw std::runtime_error("Negative image reference");
            const int x = std::bit_cast<int16_t>(uint16_t(le(parts,offset+2,2)));
            const int y = std::bit_cast<int16_t>(uint16_t(le(parts,offset+4,2)));
            const auto sprite = decode(unsigned(image-1));
            // 0x12162c..0x121660 applies +X and -Y in the ordinary facing state.
            // The preview origin is fixed for every step; no per-cell recentering.
            for (int sy=0; sy<sprite.height; ++sy) for (int sx=0; sx<sprite.width; ++sx) {
                const size_t source = size_t(sy*sprite.width+sx)*4;
                if (!sprite.rgba[source+3]) continue;
                // 0x121f84/0x121fd0 reflect tile positions and texture UVs.
                // PIL bit 15 flips the image inside its own rectangle; the
                // actor-facing offset adjustment is a separate operation.
                const int dx = originX+x+((flags&0x8000) ? sprite.width-1-sx : sx), dy = originY-y+sy;
                if (dx<0 || dy<0 || dx>=width || dy>=height)
                    throw std::runtime_error("Action pixel exceeds fixed preview canvas");
                const size_t dest = size_t(dy*width+dx)*4;
                std::copy_n(sprite.rgba.data()+source,4,canvas.rgba.data()+dest);
            }
        }
        if (mirror) {
            // 0x121858 negates the PIL offset; 0x121d70 subtracts the cell
            // width and XORs its local flip. For this ordinary layered subset
            // that is exactly a reflection of the final canvas. Its origin
            // moves from x=90 to x=110 (the pixel boundary, not pixel 109).
            for (int y=0;y<height;++y) for (int x=0;x<width/2;++x)
                for (int c=0;c<4;++c) std::swap(canvas.rgba[(y*width+x)*4+c],canvas.rgba[(y*width+width-1-x)*4+c]);
        }
        return canvas;
    }
    void paintOn(Frame& canvas,const ss6::ActionRecord& record,int originX,int originY,bool mirror,float scale=1) const {
        // Compose directly onto an opaque scene so translucent weapon parts
        // blend against the body/background in their actual PIL layer order.
        // Flattening each actor to an opaque sprite loses those overlaps.
        for (unsigned layer=0;layer<16;++layer) for (auto reference:record.parts) {
            if (!reference) continue;
            if (reference<0) throw std::runtime_error("Negative PIL reference");
            const size_t offset=size_t(reference-1)*16;
            const unsigned flags=le(parts,offset+12,2);
            if ((flags&15)!=layer) continue;
            const uint32_t tint=le(parts,offset+8,4);
            const bool additive=(flags&0x3ff0)==0x30;
            if ((!additive&&(flags&0x3ff0)!=0x10)||(!additive&&(tint&0xffffff)!=0x808080))
                throw std::runtime_error("PIL effect/tint not implemented in contact trial");
            const int referenceImage=std::bit_cast<int16_t>(uint16_t(le(parts,offset,2)));
            if (!referenceImage) continue;
            if (referenceImage<0) throw std::runtime_error("Negative image reference");
            const int px=std::bit_cast<int16_t>(uint16_t(le(parts,offset+2,2)));
            const int py=std::bit_cast<int16_t>(uint16_t(le(parts,offset+4,2)));
            const auto sprite=decode(unsigned(referenceImage-1));
            // 0x122944 converts PIL alpha to (a+1)/2; GS unit alpha is 128.
            // RGB remains the existing decoded preview palette. Hardware
            // color expansion/rounding still needs an original GS comparison.
            const unsigned alpha=((tint>>24)+1)/2;
            // Preview rasterizer: inverse nearest sampling avoids blending
            // several source texels into one pixel when the camera zooms
            // out. GS subpixel coverage is still a separate unverified path.
            const float left=originX+(mirror ? -px-sprite.width : px)*scale;
            const float top=originY-py*scale;
            const int firstX=std::max(0,int(std::ceil(left-.5f))),firstY=std::max(0,int(std::ceil(top-.5f)));
            const int lastX=std::min(canvas.width,int(std::ceil(left+sprite.width*scale-.5f)));
            const int lastY=std::min(canvas.height,int(std::ceil(top+sprite.height*scale-.5f)));
            for (int dy=firstY;dy<lastY;++dy) for (int dx=firstX;dx<lastX;++dx) {
                int x=std::clamp(int((dx+.5f-left)/scale),0,sprite.width-1);
                int y=std::clamp(int((dy+.5f-top)/scale),0,sprite.height-1);
                if (bool(flags&0x8000)!=mirror) x=sprite.width-1-x;
                //121f8c/121fd8 reverse tile rows and UVs for PIL bit14.
                // This is a local image flip, so the part's anchor stays put.
                // Final victory499 uses it for the rotating weapon.
                if(flags&0x4000)y=sprite.height-1-y;
                const size_t src=size_t(y*sprite.width+x)*4;
                if (!sprite.rgba[src+3]) continue;
                const size_t dst=size_t(dy*canvas.width+dx)*4;
                for (int c=0;c<3;++c) {
                    if (additive) {
                        // 0x122974 halves each tint channel, then the GS
                        // MODULATE unit uses 128 as identity. The packet at
                        // 0x348bc0 sets ALPHA=0x8000000029: Cs + Cd, with
                        // fixed 128 rather than source alpha as its factor.
                        const unsigned channel=(tint>>(c*8))&255;
                        const int lit=int(sprite.rgba[src+c])*int((channel+1)/2)/128;
                        canvas.rgba[dst+c]=uint8_t(std::min(255,int(canvas.rgba[dst+c])+lit));
                        continue;
                    }
                    const int diff=int(sprite.rgba[src+c])-int(canvas.rgba[dst+c]);
                    // Signed shift preserves the GS-style negative rounding;
                    // division toward zero would brighten some dark edges.
                    canvas.rgba[dst+c]=uint8_t(int(canvas.rgba[dst+c])+((diff*int(alpha))>>7));
                }
                canvas.rgba[dst+3]=255;
            }
        }
    }
};

void check(bool ok) { if (!ok) throw std::runtime_error(SDL_GetError()); }
void color(SDL_Renderer* r, uint8_t a, uint8_t b, uint8_t c) { check(SDL_SetRenderDrawColor(r, a, b, c, 255)); }
void text(SDL_Renderer* r, float x, float y, const std::string& s) { check(SDL_RenderDebugText(r, x, y, s.c_str())); }

struct ContactScene {
    ss6::CollisionPlayer a,b;
    std::vector<ss6::ContactEvent> events;
    std::vector<ss6::ContactDecision> decisions;
    Frame frame;
    float camera;
    unsigned defensePreset=0;
};
ContactScene contactScene(const CharacterSample& sample,const ss6::ActionRecord& a,
                          const ss6::MotionState& motion,const ss6::ActionRecord& b,
                          const ss6::JudgmentData& judgments,const ss6::CollisionTables& tables,
                          const ss6::CombatTables& combatTables,float targetX,unsigned defensePreset,
                          unsigned sourceActionId,unsigned targetActionId) {
    ContactScene scene{};
    scene.a.owner=0;scene.b.owner=1;
    scene.a.x=motion.x;scene.a.y=motion.y;scene.b.x=targetX;scene.b.mirrorX=true;
    scene.defensePreset=defensePreset;
    scene.b.stateIndex=defensePreset==1 ? 6 : defensePreset==2 ? 7 : 0;
    if (defensePreset==2) scene.b.actorFlags|=8;
    scene.a.judgmentFlags=a.judgmentFlags;scene.b.judgmentFlags=b.judgmentFlags;
    scene.a.judgments=judgments.forRecord(a);scene.b.judgments=judgments.forRecord(b);
    // Fixed armed, ordinary player snapshots. Input/state dispatch, automatic
    // facing, push correction and resolution side effects are not simulated.
    ss6::ContactRegistry registry;
    ss6::ContactMarks marksA{0,scene.a.objectFlags104,scene.a.objectFlags108,0};
    ss6::ContactMarks marksB{1,scene.b.objectFlags104,scene.b.objectFlags108,0};
    // Resource-00 objects enter in their actual action state. The list keeps
    // original A->B then B->A collection order for this two-object fixture.
    registry.add(0,0,sourceActionId,marksA);registry.add(1,0,targetActionId,marksB);
    scene.a.objectFlags104=marksA.flags104;scene.b.objectFlags104=marksB.flags104;
    for (const auto source:registry.objects()) for (const auto target:registry.objects()) {
        if (source==target) continue;
        ss6::collectContacts(tables,source==0 ? scene.a : scene.b,target==0 ? scene.a : scene.b,
                             uint8_t(source),uint8_t(target),scene.events);
    }
    ss6::orderContacts(scene.events);
    for (const auto& event:scene.events) {
        const auto& source=event.a.player==0 ? scene.a : scene.b;
        const auto& target=event.b.player==0 ? scene.a : scene.b;
        ss6::DefenseSnapshot defense;
        defense.actorFlags23c=target.actorFlags;defense.stateTable=target.stateTable;
        defense.stateIndex=target.stateIndex;defense.stateFlags=target.stateFlags;
        // Do not consume candidates here: 0x154678 commits those marks only
        // after running the still-unported reaction/damage/effect handlers.
        const ss6::ContactMarks sourceMarks{event.a.player,source.objectFlags104,source.objectFlags108,0};
        const ss6::ContactMarks targetMarks{event.b.player,target.objectFlags104,target.objectFlags108,0};
        scene.decisions.push_back(ss6::inspectContactDecision(combatTables,event,source,defense,sourceMarks,targetMarks));
    }
    scene.camera=(motion.x+targetX)/2;
    scene.frame={288,140,Bytes(288*140*4)};
    for (unsigned player=0;player<2;++player) {
        const auto sprite=sample.compose(player ? b : a,player!=0);
        const auto& p=player ? scene.b : scene.a;
        const int ox=int(144+p.x-scene.camera)-(player ? 110 : 90),oy=int(-p.y);
        for (int y=0;y<sprite.height;++y) for (int x=0;x<sprite.width;++x) {
            const int dx=ox+x,dy=oy+y;
            // This clips only the inspection viewport, never the source cell.
            if (dx<0 || dx>=288 || dy<0 || dy>=140) continue;
            const size_t src=size_t(y*sprite.width+x)*4,dst=size_t(dy*288+dx)*4;
            if (sprite.rgba[src+3]) std::copy_n(sprite.rgba.data()+src,4,scene.frame.rgba.data()+dst);
        }
    }
    return scene;
}
void drawContacts(SDL_Renderer* r,ContactScene& scene,const ss6::ActionClip& action,
                  const ss6::ActionTimeline& timeline,bool playing,bool boxes) {
    color(r,15,21,30);check(SDL_RenderClear(r));
    color(r,103,222,202);text(r,32,28,"SAMURAI SHODOWN VI / NATIVE CONTACT INSPECTOR");
    color(r,192,203,216);text(r,32,56,"1: idle  2: forward  3: backward  4: attack 185  |  LEFT/RIGHT: target position");
    text(r,32,80,"G: defender preset   H: boxes   SPACE: pause/play   N: step   R: reset   C: single actor");
    for (int y=100;y<532;y+=16) for (int x=32;x<928;x+=16) {
        uint8_t v=((x/16+y/16)%2) ? 29 : 34;
        color(r,v,uint8_t(v+6),uint8_t(v+12));
        SDL_FRect cell{float(x),float(y),16,16};check(SDL_RenderFillRect(r,&cell));
    }
    auto surface=std::unique_ptr<SDL_Surface,decltype(&SDL_DestroySurface)>(
        SDL_CreateSurfaceFrom(288,140,SDL_PIXELFORMAT_RGBA32,scene.frame.rgba.data(),288*4),SDL_DestroySurface);
    if (!surface) throw std::runtime_error(SDL_GetError());
    auto texture=std::unique_ptr<SDL_Texture,decltype(&SDL_DestroyTexture)>(SDL_CreateTextureFromSurface(r,surface.get()),SDL_DestroyTexture);
    if (!texture) throw std::runtime_error(SDL_GetError());
    check(SDL_SetTextureScaleMode(texture.get(),SDL_SCALEMODE_NEAREST));
    check(SDL_SetTextureBlendMode(texture.get(),SDL_BLENDMODE_BLEND));
    SDL_FRect dest{48,108,864,420};check(SDL_RenderTexture(r,texture.get(),nullptr,&dest));
    const auto sx=[&](float x){return 480+(x-scene.camera)*3;};
    const auto sy=[](float y){return 492-y*3;};
    color(r,83,103,121);check(SDL_RenderLine(r,32,492,928,492));
    const SDL_Rect clip{32,100,896,432};check(SDL_SetRenderClipRect(r,&clip));
    for (const auto* p:{&scene.a,&scene.b}) {
        color(r,192,203,216);text(r,sx(p->x)-8,510,p==&scene.a ? "P1" : "P2");
        if (boxes) for (const auto& j:p->judgments) {
            const auto box=ss6::worldRect(j,p->x,p->y,p->mirrorX,p->mirrorY);
            if (j.type()==0) color(r,235,195,95);
            else if (j.type()<=3) color(r,88,192,244);
            else color(r,255,106,119);
            SDL_FRect outline{sx(float(box.left)),sy(float(box.top)),float(box.right-box.left+1)*3,float(box.top-box.bottom+1)*3};
            check(SDL_RenderRect(r,&outline));
        }
    }
    unsigned hitBranches=0,guardBranches=0;
    for (size_t i=0;i<scene.events.size();++i) {
        const auto& event=scene.events[i];
        const auto& decision=scene.decisions[i];
        if (decision.kind==ss6::DecisionKind::HitBranch) ++hitBranches;
        if (decision.kind==ss6::DecisionKind::GuardBranch) ++guardBranches;
        if (decision.kind==ss6::DecisionKind::GuardBranch) color(r,103,222,202);
        else color(r,255,130,145);
        const float x=sx(float(event.centerX)),y=sy(float(event.centerY));
        check(SDL_RenderLine(r,x-4,y,x+4,y));check(SDL_RenderLine(r,x,y-4,x,y+4));
    }
    check(SDL_SetRenderClipRect(r,nullptr));
    color(r,224,233,243);
    text(r,32,550,"Action "+std::to_string(action.id())+" | step "+std::to_string(timeline.clock().step+1)+"/"+std::to_string(action.size())+
         " | separation "+std::to_string(scene.b.x-scene.a.x)+" | "+(playing ? "PLAY" : "PAUSE"));
    constexpr const char* presets[]={"NEUTRAL","STANDING GUARD","CROUCHING GUARD"};
    text(r,32,574,"Defender: "+std::string(presets[scene.defensePreset])+" | G: cycle preset and restart fixture");
    text(r,32,598,"Candidates: "+std::to_string(scene.events.size())+" | branch preview: hit "+std::to_string(hitBranches)+
         " / guard "+std::to_string(guardBranches));
    color(r,155,169,187);
    text(r,32,626,"Branch inspection | Damage/reaction/hitstop/input pending | Audio muted");
    text(r,32,650,"Ordinary state snapshots | C++ + SDL3 | Preview: 60 updates/s | ESC: quit");
    check(SDL_RenderPresent(r));
}

void draw(SDL_Renderer* r, Frame& frame, unsigned index, size_t count,
          const ss6::ActionClip& action, const ss6::ActionTimeline& timeline,
          const ss6::JudgmentData& judgments, bool idle, bool playing, bool boxes) {
    const auto& clock=timeline.clock();
    const auto& motion=timeline.motion();
    // Inspection camera only; no arena boundaries or battle camera behavior
    // are inferred from this convenience viewport.
    const float camera=idle ? std::max(0.0f,motion.x-80.0f)+std::min(0.0f,motion.x+80.0f) : 0;
    color(r, 15, 21, 30); check(SDL_RenderClear(r));
    color(r, 103, 222, 202); text(r, 32, 28, "SAMURAI SHODOWN VI / NATIVE ACTION PROBE");
    color(r, 192, 203, 216); text(r, 32, 56, "SLPS-25559 | C++ + SDL3 | Original asset data");
    text(r,32,80,"1: idle   2: forward   3: backward   4: attack 185   H: judgment boxes");
    for (int y = 100; y < 548; y += 16) for (int x = 32; x < 928; x += 16) {
        uint8_t v = ((x / 16 + y / 16) % 2) ? 29 : 34;
        color(r, v, uint8_t(v + 6), uint8_t(v + 12));
        SDL_FRect rect{float(x), float(y), 16, 16}; check(SDL_RenderFillRect(r, &rect));
    }
    auto surface = std::unique_ptr<SDL_Surface, decltype(&SDL_DestroySurface)>(
        SDL_CreateSurfaceFrom(frame.width, frame.height, SDL_PIXELFORMAT_RGBA32,
                              frame.rgba.data(), frame.width * 4), SDL_DestroySurface);
    if (!surface) throw std::runtime_error(SDL_GetError());
    auto texture = std::unique_ptr<SDL_Texture, decltype(&SDL_DestroyTexture)>(
        SDL_CreateTextureFromSurface(r, surface.get()), SDL_DestroyTexture);
    if (!texture) throw std::runtime_error(SDL_GetError());
    check(SDL_SetTextureScaleMode(texture.get(), SDL_SCALEMODE_NEAREST));
    check(SDL_SetTextureBlendMode(texture.get(), SDL_BLENDMODE_BLEND));
    int scale = std::max(1, std::min({3, 864 / frame.width, 432 / frame.height}));
    SDL_FRect dest{float(480 - frame.width * scale / 2), float(324 - frame.height * scale / 2),
                  float(frame.width * scale), float(frame.height * scale)};
    if (idle) dest.x+=(motion.x-camera)*scale;
    check(SDL_RenderTexture(r, texture.get(), nullptr, &dest));
    if (idle) {
        color(r,83,103,121);
        const float ground=dest.y+128*scale;
        check(SDL_RenderLine(r,32,ground,928,ground));
        for (int marker=-10; marker<=10; ++marker) {
            const float x=dest.x+90*scale+(marker*32-motion.x)*scale;
            if (x>=32 && x<=928) check(SDL_RenderLine(r,x,ground,x,ground+5));
        }
        if (boxes) for (const auto& judgment:judgments.forRecord(action.record(clock.step))) {
            const auto box=ss6::worldRect(judgment,motion.x,motion.y);
            // Colors identify raw JDG type groups. Their damage/guard/cancel
            // semantics are not inferred from rectangle geometry alone.
            if (judgment.type()==0) color(r,235,195,95);
            else if (judgment.type()<=3) color(r,88,192,244);
            else color(r,255,106,119);
            SDL_FRect outline{dest.x+float(90+box.left-motion.x)*scale,
                              dest.y+float(128-box.top+motion.y)*scale,
                              float(box.right-box.left+1)*scale,float(box.top-box.bottom+1)*scale};
            check(SDL_RenderRect(r,&outline));
            text(r,outline.x+2,outline.y+2,"t"+std::to_string(judgment.type()));
        }
    }
    color(r, 224, 233, 243);
    if (idle) {
        text(r,32,568,"Action " + std::to_string(action.id()) + " | step " + std::to_string(clock.step+1) + "/" + std::to_string(action.size()) +
             " | hold " + std::to_string(action.record(clock.step).duration) +
             " | length " + std::to_string(action.cycleTicks()) + " updates | " +
             (clock.endReached && action.record(clock.step).endKind==1 ? "ENDED" : playing?"PLAY":"PAUSE"));
        text(r,32,592,"SPACE: pause/play  N: step  R: reset  C: contact pair  TAB: raw cells  ESC: quit");
        text(r,32,640,"X="+std::to_string(motion.x)+" | VX="+std::to_string(motion.vx)+
             "/65536 | sound events="+std::to_string(timeline.soundEvents())+
             " | last command="+std::to_string(timeline.lastSoundCommand()));
    } else {
        text(r,32,568,"Resource 00 | idx " + std::to_string(index) + " | " + std::to_string(count) + " raw cells");
        text(r,32,592,"LEFT / RIGHT: browse cells    TAB: idle action    ESC: quit");
    }
    color(r, 155, 169, 187);
    text(r,32,616,"Action inspection | Audio muted | Hit resolution/input rules pending | Preview: 60 updates/s");
    check(SDL_RenderPresent(r));
}

class EffectTextures {
    Bytes palette;
    std::map<unsigned,Bytes> textures;
public:
    explicit EffectTextures(const fs::path& assets):palette(readFile(assets/"effect_pal_data.bin")) {
        for(const auto& [id,name]:std::array<std::pair<unsigned,const char*>,18>{{
            {1,"effect01.tex"},{2,"effect02.tex"},{3,"effect03.tex"},{4,"effect04.tex"},{5,"effect05.tex"},{9,"effect09.tex"},{6,"effect06.tex"},{7,"effect07.tex"},{8,"effect08.tex"},{12,"hanabi1.tex"},{13,"hanabi2.tex"},{14,"moji_e.tex"},
            {15,"moji1.tex"},{16,"moji2.tex"},{17,"moji3.tex"},{20,"ougi1.tex"},{21,"ougi2.tex"},{22,"sakura.tex"}}}) {
            auto bytes=readFile(assets/name);
            if(bytes.size()!=512*512/2)throw std::runtime_error("Invalid effect texture size");
            textures.emplace(id,std::move(bytes));
        }
        if(palette.size()!=11*16*4)throw std::runtime_error("Invalid PS2 effect palette size");
    }
    void paint(Frame& frame,const ss6::EffectDraw& draw,const ss6::StageCamera& camera,bool fullViewport=false) const {
        const auto q=ss6::projectEffect(draw,camera);const auto& tex=textures.at(q.asset);
        if(q.palette>=11||q.u<0||q.v<0||q.textureWidth<0||q.textureHeight<0||
           q.u+q.textureWidth>512||q.v+q.textureHeight>512)
            throw std::runtime_error("Effect quad outside admitted texture/palette bounds");
        // Match the existing inspection crop and nearest sampling. This is
        // not a replacement for GS subpixel coverage, filtering or blending.
        const double scale=fullViewport?1:.5,xOffset=fullViewport?0:40,yOffset=fullViewport?0:-68;
        const double w=(double(q.right)-q.left)*scale,h=(double(q.bottom)-q.top)*scale;
        // Some original records queue a zero-area quad. Keep the callback
        // visit and draw snapshot, but there are no pixels to fill.
        if(w<=0||h<=0||!q.textureWidth||!q.textureHeight)return;
        const double left=xOffset+double(q.left)*scale,top=yOffset+double(q.top)*scale;
        auto coordinates=[&](double px,double py)->std::optional<std::array<double,2>> {
            if(!q.rotated)return std::array{(px-left)/w,(py-top)/h};
            // Rounded strip vertices need not form a perfect parallelogram.
            // Use both original triangles instead of replacing vertex3 with
            // the result of an ideal inverse rotation.
            constexpr unsigned triangles[2][3]={{0,1,2},{2,1,3}};
            for(const auto& ids:triangles) {
                std::array<std::array<double,2>,3> v;
                for(unsigned i=0;i<3;++i)v[i]={xOffset+double(q.vertices[ids[i]][0])*scale,yOffset+double(q.vertices[ids[i]][1])*scale};
                const double ax=v[1][0]-v[0][0],ay=v[1][1]-v[0][1];
                const double bx=v[2][0]-v[0][0],by=v[2][1]-v[0][1],det=ax*by-ay*bx;
                if(!det)continue;
                const double dx=px-v[0][0],dy=py-v[0][1];
                const double na=dx*by-dy*bx,nb=ax*dy-ay*dx;
                const double a=na/det,b=nb/det;
                if(a<0||b<0||a+b>1)continue;
                auto axis=[&](unsigned bit,int extent) {
                    const int origin=bool(ids[0]&bit);
                    // Scale the affine numerator BEFORE division. Computing
                    // normalized weights first can turn an exact texel edge
                    // into115.999999..., selecting the preceding texel.
                    return (origin*det+(int(bool(ids[1]&bit))-origin)*na+
                            (int(bool(ids[2]&bit))-origin)*nb)*extent/det;
                };
                return std::array{axis(2,q.textureWidth),axis(1,q.textureHeight)};
            }
            return std::nullopt;
        };
        for(int y=std::max(0,int(std::ceil(top-.5f)));y<std::min(frame.height,int(std::ceil(top+h-.5f)));++y)
            for(int x=std::max(0,int(std::ceil(left-.5f)));x<std::min(frame.width,int(std::ceil(left+w-.5f)));++x) {
                const auto uv=coordinates(x+.5,y+.5);if(!uv)continue;
                int u=q.rotated ? int((*uv)[0]) : int((x+.5-left)*q.textureWidth/w);
                int v=q.rotated ? int((*uv)[1]) : int((y+.5-top)*q.textureHeight/h);
                if(u<0||v<0||u>=q.textureWidth||v>=q.textureHeight)continue;
                if(q.mirrorX)u=q.textureWidth-1-u;
                if(q.mirrorY)v=q.textureHeight-1-v;
                const unsigned pixel=unsigned((q.v+v)*512+q.u+u);
                const unsigned index=(tex[pixel/2]>>((pixel&1)*4))&15;
                //1003dc loads this PS2-specific32-bit CLUT.116588 copies it
                // unchanged without a global tint/fade;1094f4 uploads its11
                // banks to3105+. The generic obj0.pal arena is different.
                const auto c=le(palette,(q.palette*16+index)*4,4);
                if(!(c>>24))continue;
                if((c>>24)!=128)throw std::runtime_error("Effect CLUT alpha outside opaque preview subset");
                const size_t out=size_t(y*frame.width+x)*4;
                // 123a38 computes object color but writes ffffffff into the
                // four vertices. Do not invent an object-alpha fade here.
                const bool additive=fullViewport&&(draw.state.flags&0x08000000);
                for(unsigned channel=0;channel<3;++channel) {
                    const auto src=uint8_t(c>>(channel*8));
                    frame.rgba[out+channel]=additive?uint8_t(std::min(255,int(frame.rgba[out+channel])+src)):src;
                }
                frame.rgba[out+3]=255;
            }
    }
};
Frame trialFrame(const CharacterSample& sample,const EffectTextures& effectTextures,const ss6::ContactTrial& trial) {
    Frame frame{400,160,Bytes(400*160*4)};
    for (int y=0;y<frame.height;++y) for (int x=0;x<frame.width;++x) {
        const unsigned v=((x/8+y/8)%2) ? 29 : 34;const size_t p=size_t(y*frame.width+x)*4;
        frame.rgba[p]=uint8_t(v);frame.rgba[p+1]=uint8_t(v+6);frame.rgba[p+2]=uint8_t(v+12);frame.rgba[p+3]=255;
    }
    // Keep this 400x160 inspection crop until the full GS scene is ported,
    // but follow the actual camera state rather than snapping to the mean.
    for (unsigned i=0;i<2;++i) {
        const auto& t=trial.actor(i).object.timeline;
        const auto p=trial.camera.project(t.motion().x,t.motion().y);
        // PIL 0x1214bc quantizes sprite scale down to 1/128. Actor anchors
        // use unquantized projection; the crop is 40px wider/68px higher
        // than the half-resolution original viewport for inspection.
        sample.paintOn(frame,t.record(),int(40+p.x*.5f),int(p.y*.5f-68),t.clock().objectFlags&0x80000,
                       std::floor(p.scale*128)/128);
    }
    // Preserve the existing preview's world/UI layers. The complete GS
    // queue ordering and blend state are still a documented rendering gap.
    for(bool screen:{false,true})for(const auto& draw:trial.effects.draws())
        if(bool(draw.state.flags&0x100000)==screen)effectTextures.paint(frame,draw,trial.camera);
    return frame;
}
void drawTrial(SDL_Renderer* renderer,const CharacterSample& sample,const EffectTextures& effectTextures,const ss6::ContactTrial& trial,bool paused,bool boxes) {
    color(renderer,15,21,30);check(SDL_RenderClear(renderer));
    color(renderer,103,222,202);text(renderer,32,24,trial.knockoutPreview ?
        "SAMURAI SHODOWN VI / KO CALLBACK PREVIEW" : "SAMURAI SHODOWN VI / NATIVE CONTACT TRIAL");
    color(renderer,192,203,216);
    if (trial.knockoutPreview) {
        text(renderer,32,48,"Original KO character animation: fall, landing, bounce, final pose");
        text(renderer,32,68,"This preview starts directly in a KO action; combat controls are inactive");
    } else {
        text(renderer,32,48,"P1 A/D: move   S: crouch   J: light   L: heavy   K: guard");
        text(renderer,32,68,"P2 LEFT/RIGHT: move   DOWN: crouch   O: light   I: heavy   P: guard");
    }
    text(renderer,32,88,"R: restart match   SPACE: pause   N: step   H: boxes   ESC: exit");
    auto frame=trialFrame(sample,effectTextures,trial);
    auto surface=std::unique_ptr<SDL_Surface,decltype(&SDL_DestroySurface)>(SDL_CreateSurfaceFrom(frame.width,frame.height,SDL_PIXELFORMAT_RGBA32,frame.rgba.data(),frame.width*4),SDL_DestroySurface);
    if(!surface)throw std::runtime_error(SDL_GetError());
    auto texture=std::unique_ptr<SDL_Texture,decltype(&SDL_DestroyTexture)>(SDL_CreateTextureFromSurface(renderer,surface.get()),SDL_DestroyTexture);
    if(!texture)throw std::runtime_error(SDL_GetError());
    check(SDL_SetTextureScaleMode(texture.get(),SDL_SCALEMODE_NEAREST));
    SDL_FRect dest{32,172,896,358.4f};check(SDL_RenderTexture(renderer,texture.get(),nullptr,&dest));
    for (unsigned i=0;i<2;++i) {
        const auto& a=trial.actor(i);const float x=i ? 520 : 32;
        color(renderer,57,64,78);SDL_FRect base{x,124,408,16};check(SDL_RenderFillRect(renderer,&base));
        color(renderer,i ? 238 : 103,i ? 157 : 222,i ? 105 : 202);
        SDL_FRect hp{x,124,408*float(a.life.life)/float(a.life.maximum),16};check(SDL_RenderFillRect(renderer,&hp));
        text(renderer,x,148,"P"+std::to_string(i+1)+"  "+std::to_string(a.life.life)+" / 200   WINS "+std::to_string(trial.match.players[i].wins));
        color(renderer,192,203,216);
        text(renderer,x,550,"Action "+std::to_string(a.object.timeline.action().id())+"  hits "+std::to_string(a.hitCount)+"  guards "+std::to_string(a.guardCount));
        const float sword=float(a.damage.swordCurrent)/a.damage.swordMaximum;
        const float rage=float(a.damage.rageAmount)/0xb800;
        color(renderer,57,64,78);SDL_FRect sb{x,574,180,6},rb{x+224,574,180,6};
        check(SDL_RenderFillRect(renderer,&sb));check(SDL_RenderFillRect(renderer,&rb));
        color(renderer,126,182,255);sb.w*=sword;check(SDL_RenderFillRect(renderer,&sb));
        color(renderer,246,106,97);rb.w*=rage;check(SDL_RenderFillRect(renderer,&rb));
        color(renderer,192,203,216);text(renderer,x,586,"SWORD "+std::to_string(a.damage.swordCurrent/256));
        text(renderer,x+224,586,a.damage.rageState ? "RAGE ACTIVE" : "RAGE");
    }
    if (boxes) {
        SDL_Rect clip{32,172,896,359};check(SDL_SetRenderClipRect(renderer,&clip));
        for (unsigned i=0;i<2;++i) {
            auto p=trial.collisionPlayer(i);
            for (const auto& j:p.judgments) {
                const auto b=ss6::worldRect(j,p.x,p.y,p.mirrorX);
                // The playable light and heavy slashes use raw JDG types 10 and 12.
                const bool slash = j.type() == 10 || j.type() == 12;
                if (slash) color(renderer,250,112,96);
                else color(renderer,120,199,245);
                const auto tl=trial.camera.project(float(b.left),float(b.top));
                const auto br=trial.camera.project(float(b.right),float(b.bottom));
                SDL_FRect r{32+(40+tl.x*.5f)*2.24f,172+(tl.y*.5f-68)*2.24f,
                            (br.x-tl.x)*1.12f,(br.y-tl.y)*1.12f};
                check(SDL_RenderRect(renderer,&r));
            }
        }
        check(SDL_SetRenderClipRect(renderer,nullptr));
    }
    color(renderer,255,214,135);
    if (trial.knockoutPreview) {
        const auto& a=trial.actor(trial.actor(0).life.life ? 1 : 0);
        constexpr const char* phases[]={"INACTIVE","FIRST FALL","BOUNCE","FINAL POSE","COMPLETE"};
        text(renderer,32,612,std::string(phases[int(a.knockout.phase)])+" | landing events "+std::to_string(a.landingDustEvents));
    } else if (trial.winner>=0) text(renderer,32,612,
        (trial.winner==2 ? std::string("DOUBLE KO") : "P"+std::to_string(trial.winner+1)+" WINS")+
        (trial.matchFinished ? " / MATCH COMPLETE" : trial.roundEndingReady&&trial.continueRounds ? " / NEXT ROUND" : trial.roundEndingReady ? " / R: replay" : " / FINISHING"));
    else text(renderer,32,612,paused ? "PAUSED" : trial.roundState<4 ? "ROUND OPENING" : "RUNNING");
    color(renderer,155,169,187);
    text(renderer,32,634,trial.knockoutPreview ?
        "KO body and landing effect / audio muted / round transitions pending" :
        "Limited Haohmaru trial / standing + crouching slashes / audio muted");
    text(renderer,520,612,"Update "+std::to_string(trial.updates)+"  |  Native C++ + SDL3");
    check(SDL_RenderPresent(renderer));
}
int runTrial(const fs::path& assets,const CharacterSample& sample,const fs::path& snapshot,
             const fs::path& dump,unsigned updates,unsigned smokeUpdates,unsigned defensePreset,bool boxes,bool scripted,
             float targetDistance,bool mirroredAttacker,const fs::path& scriptPath,bool koPreview,unsigned koAction) {
    ss6::ContactTrial trial(assets);
    EffectTextures effectTextures(assets);
    auto reset=[&] {
        const bool continuing=trial.continueRounds;
        const bool introduction=trial.firstRoundIntroduction;
        if (koPreview) trial.startKnockoutPreview(mirroredAttacker ? 1 : 0,koAction ? koAction : 400);
        else {
            trial.reset();
            if(introduction)trial.startMatch();
            else if(continuing){trial.enableRoundContinuation();trial.startOpeningFixture(1);}
        }
    };
    reset();
    if (koPreview&&(scripted||!scriptPath.empty())) throw std::runtime_error("KO preview cannot run a contact script");
    if (scripted) {
        trial.place(280,280+targetDistance);
        const unsigned attacker=mirroredAttacker ? 1 : 0;
        trial.command(1-attacker,defensePreset==1 ? ss6::TrialCommand::StandGuard : defensePreset==2 ? ss6::TrialCommand::CrouchGuard : ss6::TrialCommand::Idle);
        trial.tick();trial.command(attacker,ss6::TrialCommand::LightSlash);
    }
    if (!scriptPath.empty()) {
        std::ifstream script(scriptPath);
        if (!script) throw std::runtime_error("Cannot open trial script");
        while (ss6::readTrialCommand(trial,script)) {}
    }
    for (unsigned i=0;i<updates;++i)trial.tick();
    if(!dump.empty()) {
        const auto frame=trialFrame(sample,effectTextures,trial);std::ofstream out(dump,std::ios::binary);
        for(uint32_t v:{uint32_t(frame.width),uint32_t(frame.height)})for(unsigned shift=0;shift<32;shift+=8)out.put(char(v>>shift));
        out.write(reinterpret_cast<const char*>(frame.rgba.data()),std::streamsize(frame.rgba.size()));
        if(!out)throw std::runtime_error("Cannot write trial frame");return 0;
    }
    if(!snapshot.empty()) {
        auto canvas=std::unique_ptr<SDL_Surface,decltype(&SDL_DestroySurface)>(SDL_CreateSurface(960,672,SDL_PIXELFORMAT_RGBA32),SDL_DestroySurface);
        if(!canvas)throw std::runtime_error(SDL_GetError());
        auto r=std::unique_ptr<SDL_Renderer,decltype(&SDL_DestroyRenderer)>(SDL_CreateSoftwareRenderer(canvas.get()),SDL_DestroyRenderer);
        if(!r)throw std::runtime_error(SDL_GetError());
        drawTrial(r.get(),sample,effectTextures,trial,true,boxes);check(SDL_SaveBMP(canvas.get(),snapshot.string().c_str()));return 0;
    }
    check(SDL_Init(SDL_INIT_VIDEO));SDL_Window* window=nullptr;SDL_Renderer* renderer=nullptr;
    check(SDL_CreateWindowAndRenderer("SS6 Native Contact Trial",960,672,SDL_WINDOW_RESIZABLE,&window,&renderer));
    check(SDL_SetRenderLogicalPresentation(renderer,960,672,SDL_LOGICAL_PRESENTATION_LETTERBOX));
    bool running=true,paused=false;unsigned renders=0;
    uint64_t previous=SDL_GetTicksNS(),remainder=0;constexpr uint64_t period=1000000000ull/60;
    auto tick=[&] {
        const bool* keys=SDL_GetKeyboardState(nullptr);
        for(unsigned i=0;i<2;++i) {
            const bool left=keys[i ? SDL_SCANCODE_LEFT : SDL_SCANCODE_A];
            const bool right=keys[i ? SDL_SCANCODE_RIGHT : SDL_SCANCODE_D];
            const bool guard=keys[i ? SDL_SCANCODE_P : SDL_SCANCODE_K];
            const bool down=keys[i ? SDL_SCANCODE_DOWN : SDL_SCANCODE_S];
            auto command=ss6::TrialCommand::Idle;
            if(guard)command=down ? ss6::TrialCommand::CrouchGuard : ss6::TrialCommand::StandGuard;
            else if(down)command=ss6::TrialCommand::Crouch;
            else if(left!=right) {
                const bool mirror=trial.actor(i).object.timeline.clock().objectFlags&0x80000;
                command=(right!=mirror) ? ss6::TrialCommand::Forward : ss6::TrialCommand::Backward;
            }
            trial.command(i,command);
        }
        trial.tick();
    };
    while(running) {
        SDL_Event event;
        while(SDL_PollEvent(&event)) {
            if(event.type==SDL_EVENT_QUIT)running=false;
            if(event.type==SDL_EVENT_WINDOW_FOCUS_LOST){paused=true;remainder=0;trial.discardAttackPresses();}
            if(event.type==SDL_EVENT_KEY_DOWN&&!event.key.repeat) {
                if(event.key.key==SDLK_ESCAPE)running=false;
                else if(event.key.key==SDLK_R){reset();remainder=0;}
                else if(event.key.key==SDLK_SPACE){paused=!paused;remainder=0;trial.discardAttackPresses();}
                else if(event.key.key==SDLK_H)boxes=!boxes;
                else if(event.key.key==SDLK_N){paused=true;remainder=0;tick();}
                else if(event.key.key==SDLK_J)trial.command(0,ss6::TrialCommand::LightSlash);
                else if(event.key.key==SDLK_O)trial.command(1,ss6::TrialCommand::LightSlash);
                else if(event.key.key==SDLK_L)trial.command(0,ss6::TrialCommand::HeavySlash);
                else if(event.key.key==SDLK_I)trial.command(1,ss6::TrialCommand::HeavySlash);
            }
        }
        const uint64_t now=SDL_GetTicksNS();if(!paused)remainder+=std::min(now-previous,uint64_t(250000000));previous=now;
        while(remainder>=period){tick();remainder-=period;}
        if(running){drawTrial(renderer,sample,effectTextures,trial,paused,boxes);if(smokeUpdates&&++renders>=smokeUpdates)running=false;}
        SDL_Delay(8);
    }
    SDL_DestroyRenderer(renderer);SDL_DestroyWindow(window);SDL_Quit();return 0;
}

struct VersusControls {
    std::array<ss6::NormalizedPadSample,2> pads{};
    std::array<bool,2> guard{};
    std::array<uint32_t,2> keyboard{},gamepad{};
    void merge(unsigned slot) {
        auto& pad=pads[slot];
        const uint32_t held=keyboard[slot]|gamepad[slot];
        // Releasing one device must not release a button still held on
        // the other, or synthesize a second press during the next tick.
        pad.pressed|=held&~pad.held;
        pad.held=held;
    }
    void useGamepads(const std::array<uint32_t,2>& held) {
        gamepad=held;
        for(unsigned i=0;i<pads.size();++i)merge(i);
    }
    void clearPresses() {for(auto& pad:pads)pad.pressed=0;}
    void key(SDL_Keycode key,bool down) {
        struct Binding {SDL_Keycode key;unsigned player,mask;};
        static constexpr Binding keys[]={
            {SDLK_W,0,ss6::PadUp},{SDLK_A,0,ss6::PadLeft},{SDLK_S,0,ss6::PadDown},{SDLK_D,0,ss6::PadRight},
            {SDLK_J,0,ss6::PadLight},{SDLK_U,0,ss6::PadMedium},{SDLK_L,0,ss6::PadHeavy},{SDLK_M,0,ss6::PadKick},
            {SDLK_F,0,ss6::PadSystem},{SDLK_T,0,ss6::PadStart},{SDLK_TAB,0,ss6::PadSelect},
            {SDLK_UP,1,ss6::PadUp},{SDLK_LEFT,1,ss6::PadLeft},{SDLK_DOWN,1,ss6::PadDown},{SDLK_RIGHT,1,ss6::PadRight},
            {SDLK_O,1,ss6::PadLight},{SDLK_LEFTBRACKET,1,ss6::PadMedium},{SDLK_I,1,ss6::PadHeavy},{SDLK_RIGHTBRACKET,1,ss6::PadKick},
            {SDLK_BACKSLASH,1,ss6::PadSystem},{SDLK_RETURN,1,ss6::PadStart},{SDLK_BACKSPACE,1,ss6::PadSelect}};
        if(key==SDLK_K||key==SDLK_P)guard[key==SDLK_P]=down;
        for(const auto& b:keys)if(b.key==key) {
            if(down)keyboard[b.player]|=b.mask;
            else keyboard[b.player]&=~b.mask;
            merge(b.player);
        }
    }
    void tick(ss6::LocalVersus& session) {
        const auto& match=session.match();
        auto sampled=pads;
        for(unsigned i=0;i<2;++i) {
            if(guard[i])sampled[i].held|=match.fighter(i).sampling.expectedFacing?ss6::PadRight:ss6::PadLeft;
            pads[i].pressed=0;
        }
        session.tick(sampled);
    }
};
class VersusScreen {
    std::optional<ss6::CombatStage> stage_;
    ss6::CombatStage::Foreground stageForeground_;
    unsigned renderedStage_=~0u;
    std::optional<ss6::NativeScene> scene_;
    std::array<unsigned,3> sceneSlots_{~0u,~0u,51};
    EffectTextures textures_;
    ss6::RageGaugeRenderer rage_;
    ss6::FighterIdentityHud identity_;
    ss6::ObjectDrawQueue presentationDraws_;
    fs::path assets_;
    std::optional<ss6::VersusResultArt> winnerArt_;
    std::optional<ss6::VersusResultText> winnerText_;
    std::optional<ss6::VersusDrawArt> drawArt_;
    Frame frame_{640,448,Bytes(640*448*4)};
    Frame result_{640,480,Bytes(640*480*4)};
    std::optional<ss6::ConsoleVersusArt> consoleArt_;
    std::optional<ss6::ConsoleTitleArt> titleArt_;
    std::optional<ss6::CharacterSelectArt> selectArt_;
    std::optional<ss6::VersusFaceoffArt> faceoffArt_;
    std::optional<ss6::VsCurtain> curtain_;
    const ss6::CombatStage& stageArt(const ss6::NativeMatch& match) {
        // RANDOM stores its cursor separately. Load the art for the result of the draw.
        const unsigned arena=match.combatStage().stage;
        if(arena!=renderedStage_){stage_.emplace(assets_,arena);renderedStage_=arena;}
        return *stage_;
    }
    void paintCurtain(int frame) {
        if(frame<0)return;
        if(!curtain_)curtain_.emplace(assets_);
        curtain_->paint(unsigned(frame),result_.rgba);
    }
    std::array<unsigned,2> portraitIds_{~0u,~0u};
    std::unique_ptr<SDL_Surface,decltype(&SDL_DestroySurface)> hudSurface_{nullptr,SDL_DestroySurface};
    std::unique_ptr<SDL_Renderer,decltype(&SDL_DestroyRenderer)> hudRenderer_{nullptr,SDL_DestroyRenderer};
    void present(SDL_Renderer* r,const ss6::VersusResultState& result,bool paused,int consoleFade=0) {
        const int alpha=std::max(result.fadeAlpha,consoleFade);
        if(alpha>0) {
            // The original fade clock is authoritative. Intermediate colors
            // currently blend on the completed framebuffer; the PS2 updates
            // texture CLUTs and untextured vertex colors separately.
            const Uint8 tone=result.fadeWhite?255:0;
            check(SDL_SetRenderDrawBlendMode(r,SDL_BLENDMODE_BLEND));
            check(SDL_SetRenderDrawColor(r,tone,tone,tone,Uint8(std::min(alpha,255))));
            check(SDL_RenderFillRect(r,nullptr));
            check(SDL_SetRenderDrawBlendMode(r,SDL_BLENDMODE_NONE));
        }
        if(paused){color(r,242,237,218);text(r,272,120,"PAUSED");}
        // Provisional notices for scenes whose original picture is not ported.
        if(!overlay.empty()) {
            color(r,25,24,27);SDL_FRect banner{0,480.f-22.f*overlay.size()-14,640,22.f*overlay.size()+14};check(SDL_RenderFillRect(r,&banner));
            color(r,255,255,255);
            for(size_t i=0;i<overlay.size();++i)text(r,20,480.f-22.f*(overlay.size()-i),overlay[i]);
        }
        check(SDL_RenderPresent(r));
    }
    std::vector<uint8_t> menuPixels_,overlayPixels_,windowPixels_,fadePixels_,scenePixels_=std::vector<uint8_t>(640*480*4);
public:
    static bool arcadeScene(const ss6::ArcadeSession* arcade) {
        using S=ss6::ArcadeScene;
        return arcade&&arcade->presentation&&(ss6::ArcadePresentation::presents(arcade->scene)||
               ((arcade->scene==S::Continue||arcade->scene==S::GameOver)&&arcade->presentation->current==arcade->scene));
    }
    // The 640x480 picture of the running arcade scene (--dump).
    const std::vector<uint8_t>& arcadePicture(const ss6::ArcadeSession& arcade) {
        arcade.presentation->paint(arcade,scenePixels_);
        return scenePixels_;
    }
private:
    std::optional<ss6::MenuCanvas> overlayCanvas_;
    std::optional<ss6::ArcadeArt> arcadeArt_;
    std::optional<ss6::ArcadeTallyTables> overlayTables_;
    ss6::MenuDrawList overlayList_;
    ss6::FreeSeatPrompt freeSeatPrompt_;
    void arcadeOverlay(const ss6::NativeMatch& match,const ss6::ArcadeSession& arcade,bool scene) {
        if(!overlayCanvas_){overlayCanvas_.emplace(assets_);arcadeArt_.emplace(assets_);overlayTables_.emplace(assets_);}
        auto& canvas=*overlayCanvas_;auto& list=overlayList_;
        canvas.setBrightness(match.system().brightness());
        overlayPixels_.assign(640*480*4,0);
        for(size_t i=3;i<overlayPixels_.size();i+=4)overlayPixels_[i]=255;
        list.beginFrame();
        const auto& run=arcade.run;
        if(scene) {
            if(arcade.scene==ss6::ArcadeScene::Continue)
                ss6::drawArcadeContinue(canvas,list,arcadeArt_->tables(),arcade.continueScene.draw);
            else ss6::drawArcadeGameOver(canvas,list,arcadeArt_->tables(),arcade.gameOver.draw,run.game.levelEnding!=0);
        } else {
            std::copy_n(frame_.rgba.begin(),std::min(frame_.rgba.size(),overlayPixels_.size()),overlayPixels_.begin());
            const auto& b=match.battle();
            const bool latched=b.matchEnd.continue2c==1||(match.pauseMenu()&&match.pauseMenu()->active);
            ss6::drawArcadeScore(canvas,list,*overlayTables_,arcadeArt_->tables(),b.gameMode,b.matchEnd.submodeA0,match.arcadeScore());
            ss6::drawFreeSeatPrompt(canvas,list,*overlayTables_,freeSeatPrompt_,b.gameMode,b.matchEnd.submodeA0,true,latched);
            if(match.arcadeTally().active())ss6::drawArcadeTally(canvas,list,*overlayTables_,match.arcadeTally().draw);
        }
        arcadeArt_->rasterise(canvas,list,overlayPixels_);
        for(size_t i=3;i<overlayPixels_.size();i+=4)overlayPixels_[i]=255;
    }
public:
    const ss6::LocalVersus* session=nullptr;
    std::vector<std::string> overlay;
private:
    static void paintJudgments(SDL_Renderer* r,const ss6::NativeMatch& match) {
        const auto& camera=match.battle().camera;
        for(unsigned side=0;side<2;++side) {
            const auto player=match.collisionPlayer(side);
            for(const auto& judgment:player.judgments) {
                const auto bounds=ss6::worldRect(judgment,player.x,player.y,player.mirrorX,player.mirrorY);
                const auto tl=camera.project(float(bounds.left),float(bounds.top));
                const auto br=camera.project(float(bounds.right),float(bounds.bottom));
                const bool attack=judgment.type()>=10&&judgment.type()<=32;
                color(r,attack?255:114,attack?104:198,attack?98:231);
                SDL_FRect rect{tl.x,tl.y,br.x-tl.x,br.y-tl.y};check(SDL_RenderRect(r,&rect));
            }
        }
    }
    void paintDebugOverlay(const ss6::NativeMatch& match) {
        if(!hudRenderer_) {
            hudSurface_.reset(SDL_CreateSurfaceFrom(frame_.width,frame_.height,SDL_PIXELFORMAT_RGBA32,
                                                     frame_.rgba.data(),frame_.width*4));
            if(hudSurface_)hudRenderer_.reset(SDL_CreateSoftwareRenderer(hudSurface_.get()));
            if(!hudRenderer_)throw std::runtime_error(SDL_GetError());
        }
        paintJudgments(hudRenderer_.get(),match);
        check(SDL_FlushRenderer(hudRenderer_.get()));
    }
    void paintHud(const ss6::NativeMatch& match,bool boxes) {
        if(match.hudClock().visible) {
            rage_.paint(match.rageGauge(),frame_.rgba);
            identity_.paint(match.identityHud(),frame_.rgba);
            rage_.paintClock(match.hudClock(),frame_.rgba);
        }
        if(boxes)paintDebugOverlay(match);
        if(match.battle().consoleMenu.draw.visible) {
            if(!consoleArt_)consoleArt_.emplace(assets_);
            consoleArt_->paint(match.battle().consoleMenu.draw,frame_.rgba);
        }
    }
public:
    explicit VersusScreen(const fs::path& assets):textures_(assets),rage_(assets),identity_(assets),assets_(assets) {}
    const Frame& paint(const ss6::NativeMatch& match,const fs::path& stageDump={},bool includeHudPortraits=false) {
        if(match.menuScene()!=ss6::NativeMatch::MenuScene::None) {
            match.rasteriseMenu(result_.rgba);
            return result_;
        }
        if(match.title() || match.characterSelect()) {
            const auto& selection=match.characterSelect();
            if(const auto& title=match.title()) {
                if(!titleArt_)titleArt_.emplace(assets_);
                const auto& d=title->draw;
                auto prompt=ss6::ConsoleTitlePrompt::Hidden;
                if(!d.modeMenu && match.titlePromptVisible())
                    prompt=match.battle().matchEnd.continue2c?ss6::ConsoleTitlePrompt::Wait:ss6::ConsoleTitlePrompt::Start;
                const auto white=match.selectWhiteLevel();
                const auto level=white?white:match.battle().consoleMenu.fadeAlpha;
                titleArt_->paint(d.modeMenu,d.firstRow,d.scrollDirection,d.scrollTick,d.titleTick,d.idleTick,result_.rgba,prompt,level,white>0,d.unlock);
                return result_;
            } else if(const auto& preview=match.faceoff()) {
                const auto picks=match.selectedLineup();
                const std::array<unsigned,2> ids{picks[0].character,picks[1].character};
                if(ids!=portraitIds_){faceoffArt_.emplace(assets_,ids);portraitIds_=ids;}
                faceoffArt_->paint(*preview,result_.rgba);
            } else {
                if(!selectArt_)selectArt_.emplace(assets_);
                selectArt_->paint(*selection,result_.rgba);
            }
            const auto white=match.selectWhiteLevel();
            if(white)for(size_t n=0;n<result_.rgba.size();n+=4)
                for(unsigned c=0;c<3;++c)result_.rgba[n+c]+=((255-result_.rgba[n+c])*white)>>8;
            paintCurtain(match.curtainFrame());
            // ARCADE challenger: the shutter of the kind-4 scene switch opens over the select.
            if(session&&session->arcade()&&session->arcade()->transitionActive()) {
                const auto& t=session->arcade()->transitionTask();
                if(t.request.kind==4)paintCurtain(t.frame.curtain);
            }
            return result_;
        }
        // The stage packets use their priority-10 projection. Fighters and hit
        // sparks use the later camera published by the battle task in this tick.
        unsigned nextDepth=100;
        if(match.mikiriWhiteFrame()) {
            // 113aa8 suppresses normal draw submissions; 113b28 replaces
            // the entire game image at presentation, including its HUD.
            std::fill(frame_.rgba.begin(),frame_.rgba.end(),255);
        } else nextDepth=stageArt(match).paint(match.combatStage(),match.battle().gauges.paletteTones,frame_.rgba,&stageForeground_);
        if(!stageDump.empty())writeRgba(stageDump,frame_);
        auto effect=[&](const ss6::EffectDraw& d){textures_.paint(frame_,d,match.battle().camera,true);};
        const std::array<unsigned,3> slots{match.lineup()[0].character,match.lineup()[1].character,51};
        if(slots!=sceneSlots_){scene_.emplace(assets_,slots);sceneSlots_=slots;}
        if(includeHudPortraits)match.buildPresentationDraws(presentationDraws_);
        scene_->depthHook=[&](float depth){if(!match.mikiriWhiteFrame())stageArt(match).paintForeground(stageForeground_,depth,frame_.rgba);};
        scene_->paint(match,frame_.rgba,effect,nextDepth,includeHudPortraits?&presentationDraws_:nullptr);
        if(!match.mikiriWhiteFrame())for(const auto& d:match.effectDraws())effect(d);
        return frame_;
    }
    void show(SDL_Renderer* r,SDL_Texture* texture,const ss6::NativeMatch& match,bool paused,bool boxes) {
        const auto& battle=match.battle();
        const auto& result=battle.resultScreen;
        const auto& menu=battle.consoleMenu;
        if(match.menuScene()!=ss6::NativeMatch::MenuScene::None) {
            // The menu pages are 448-line frames. The video output shows them
            // over the whole 4:3 picture; the scaling belongs to presentation
            // and leaves the rasterised frame (--dump) untouched.
            const auto& image=paint(match);
            check(SDL_UpdateTexture(texture,nullptr,image.rgba.data(),image.width*4));
            const SDL_FRect lines{0,0,640,448};
            check(SDL_SetTextureScaleMode(texture,SDL_SCALEMODE_LINEAR));
            check(SDL_RenderTexture(r,texture,&lines,nullptr));
            check(SDL_SetTextureScaleMode(texture,SDL_SCALEMODE_NEAREST));
            // The art modules already apply the scene fade to their colours.
            present(r,{},paused);
            return;
        }
        if(match.title() || match.characterSelect()) {
            const auto& image=paint(match);
            check(SDL_UpdateTexture(texture,nullptr,image.rgba.data(),image.width*4));
            check(SDL_RenderTexture(r,texture,nullptr,nullptr));
            if(match.title() && match.title()->unavailableMode) {
                color(r,25,24,27);SDL_FRect banner{0,422,640,58};check(SDL_RenderFillRect(r,&banner));
                color(r,255,255,255);text(r,20,443,"MODE IN DEVELOPMENT / SELECT VS MODE TO PLAY");
            } else if(match.selectionUnavailable()) {
                color(r,25,24,27);SDL_FRect banner{0,422,640,58};check(SDL_RenderFillRect(r,&banner));
                color(r,255,255,255);const auto stage=match.unavailableStage();
                if(!match.missingMove().empty())text(r,20,437,match.missingMove());
                else if(stage>=0&&!ss6::CombatStageState::supports(stage))text(r,20,437,"STAGE "+std::to_string(stage)+" IS IN DEVELOPMENT / CHOOSE ANOTHER STAGE");
                else text(r,20,437,"FIGHTER IN DEVELOPMENT / CHOOSE HAOHMARU, NAKORURU, RIMURURU, HANZO, RASETSUMARU, MINA, GAOH OR EARTHQUAKE");
                text(r,20,459,"PRESS AN ATTACK BUTTON TO RETURN TO CHARACTER SELECT");
            }
            if(match.title())present(r,{},paused);
            else present(r,result,paused,menu.fadeAlpha);
            return;
        }
        if(result.presentationReady) {
            if(result.scene==ss6::VersusScene::Winner) {
                if(!winnerArt_)winnerArt_.emplace(assets_);
                if(!winnerText_)winnerText_.emplace(assets_);
                winnerArt_->paint(unsigned(result.winner),result.draw.frame,result.draw.backgroundFrame,result_.rgba);
                if(result.draw.frame>=60)
                    winnerText_->paint(result.quoteIndex,result.draw.glyphLimit,result_.rgba);
            } else {
                if(!drawArt_)drawArt_.emplace(assets_);
                stageArt(match).paint(match.combatStage(),battle.gauges.paletteTones,result_.rgba);
                drawArt_->paint(result.draw.frame,result.draw.backgroundFrame,result.lastEntrant^1u,result_.rgba);
                if(result.draw.whiteFlash)std::fill(result_.rgba.begin(),result_.rgba.end(),255);
            }
            check(SDL_UpdateTexture(texture,nullptr,result_.rgba.data(),result_.width*4));
            check(SDL_RenderTexture(r,texture,nullptr,nullptr));
            present(r,result,paused);
            return;
        }
        if(result.scene==ss6::VersusScene::AfterWinner || result.scene==ss6::VersusScene::AfterDraw) {
            color(r,23,26,29);check(SDL_RenderClear(r));
            color(r,242,237,218);text(r,172,226,"END OF NATIVE PREVIEW");
            text(r,172,250,"R  NEW MATCH     ESC  EXIT");
            present(r,result,paused);
            return;
        }
        const auto* arcade=session?session->arcade():nullptr;
        if(arcadeScene(arcade)) {
            // The ARCADE presentation scenes, CONTINUE and GAME OVER with their objects.
            arcade->presentation->paint(*arcade,scenePixels_);
            check(SDL_UpdateTexture(texture,nullptr,scenePixels_.data(),640*4));
            check(SDL_RenderTexture(r,texture,nullptr,nullptr));
            present(r,{},paused);
            return;
        }
        if(arcade&&(arcade->scene==ss6::ArcadeScene::Continue||arcade->scene==ss6::ArcadeScene::GameOver)) {
            // Task_Continue / Task_GameOver. The stage picture and the
            // loser's fighter object behind the art are not drawn yet.
            arcadeOverlay(match,*arcade,true);
            check(SDL_UpdateTexture(texture,nullptr,overlayPixels_.data(),640*4));
            check(SDL_RenderTexture(r,texture,nullptr,nullptr));
            present(r,{},paused);
            return;
        }
        paint(match,{},true);
        if(match.mikiriWhiteFrame()) {
            color(r,255,255,255);check(SDL_RenderClear(r));check(SDL_RenderPresent(r));return;
        }
        // The scene-only dump remains the input to the sprite comparison.
        // The player-facing framebuffer composites the HUD above the arena.
        paintHud(match,boxes);
        if(const int curtain=match.curtainFrame();curtain>=0) {
            // The PS2 draws sliding panels above the complete new arena and
            // HUD. The native controls footer resumes after the panels open.
            std::fill(result_.rgba.begin(),result_.rgba.end(),0);
            for(size_t i=3;i<result_.rgba.size();i+=4)result_.rgba[i]=255;
            std::copy(frame_.rgba.begin(),frame_.rgba.end(),result_.rgba.begin());
            paintCurtain(curtain);
            check(SDL_UpdateTexture(texture,nullptr,result_.rgba.data(),result_.width*4));
            check(SDL_RenderTexture(r,texture,nullptr,nullptr));
            present(r,result,paused);return;
        }
        const SDL_Rect arenaPixels{0,0,frame_.width,frame_.height};
        {
            const uint8_t* pixels=frame_.rgba.data();
            if(arcade&&match.arcadeTables()&&frame_.width==640) {
                // Score, the free seat's PRESS START legend and the round tally
                // are composed over the finished arena and HUD.
                arcadeOverlay(match,*arcade,false);
                pixels=overlayPixels_.data();
            }
            if(arcade&&arcade->presentation&&frame_.width==640) {
                // The fade of the arcade scene switch (1252f0) into or out of the fight.
                const auto& f=arcade->presentation->fadeShown;
                if(f.vertexFade()&&f.level>0) {
                    fadePixels_.assign(pixels,pixels+size_t(frame_.width)*frame_.height*4);
                    const int level=std::min(f.level,256);
                    const std::array<int,3> target{int((f.colour>>16)&0xff),int((f.colour>>8)&0xff),int(f.colour&0xff)};
                    for(size_t i=0;i<fadePixels_.size();i+=4)for(unsigned c=0;c<3;++c)
                        fadePixels_[i+c]=uint8_t((fadePixels_[i+c]*(256-level)+target[c]*level)>>8);
                    pixels=fadePixels_.data();
                }
            }
            if(frame_.width==640) {
                // Pause menu, its key-configuration / skill-list windows and the
                // PRACTICE window are drawn last, over everything else. The
                // overlay works on a 640x480 surface; only the arena rows are shown.
                windowPixels_.assign(640*480*4,0);
                std::copy_n(pixels,size_t(frame_.width)*frame_.height*4,windowPixels_.begin());
                if(match.composeBattleOverlay(windowPixels_))pixels=windowPixels_.data();
            }
            check(SDL_UpdateTexture(texture,&arenaPixels,pixels,frame_.width*4));
        }
        color(r,23,26,29);check(SDL_RenderClear(r));
        SDL_FRect stage{0,0,640,448};check(SDL_RenderTexture(r,texture,&stage,&stage));
        color(r,242,237,218);
        if(menu.active) {
            text(r,20,453,"MOVE  D-PAD / ARROWS / WASD      CONFIRM  CIRCLE / TRIANGLE / START");
            text(r,20,468,"P1 CONFIRM L  CANCEL M           P2 CONFIRM I  CANCEL ]");
        } else {
        text(r,20,453,"P1 WASD  J/U/L/M  E:F  START:T     P2 ARROWS  O/[/I/]  E:\\  START:ENTER");
        text(r,20,468,"LIGHT / MEDIUM / HEAVY / KICK     SPACE PAUSE    H BOXES");
        }
        // 1806e4: the survival controller covers the arena with a black rectangle of alpha 12d4cc8.
        present(r,result,paused,std::max(menu.fadeAlpha,match.survivalFade()));
    }
};
// Session-wide save data options (--save FILE, --unlock-modes yes).
fs::path saveFile;
bool unlockModes=false;

// Text lines for session states that have no ported picture yet.
std::vector<std::string> sessionOverlay(const ss6::LocalVersus& session) {
    std::vector<std::string> lines;
    const auto& match=session.match();
    // The pause menu family and the PRACTICE window are drawn with the
    // original art by NativeMatch::composeBattleOverlay.
    // SURVIVAL MODE: the candidate window 211e18, the message window 182600, the panel 1810f8
    // and the defeated count of the HUD header 1bb2c8 have no ported art.
    for(auto& line:match.survivalOverlay())lines.push_back(std::move(line));
    const auto* arcade=session.arcade();
    if(!arcade)return lines;
    if(!session.arcadeNotice().empty())lines.push_back(session.arcadeNotice());
    if(!arcade->notice.empty())lines.push_back(arcade->notice);
    if(arcade->presentation)for(const auto& line:arcade->presentation->notices)
        if(std::find(lines.begin(),lines.end(),line)==lines.end())lines.push_back(line);
    return lines;
}

int runVersus(const fs::path& assets,const fs::path& replay,const fs::path& snapshot,const fs::path& dump,
              const fs::path& stageDump,
              unsigned updates,unsigned smoke,bool boxes,int roundTime,ss6::VersusMode mode,const fs::path& audioOut={},std::array<unsigned,2> spirits={},ss6::VersusEntry entry=ss6::VersusEntry::Fight,
              std::array<bool,2> cpuSeats={},int stage=0,bool items=false) {
    ss6::LocalVersus session(assets,roundTime,mode,spirits,entry,cpuSeats);
    if(!saveFile.empty()||unlockModes) {
        auto& data=session.system();
        // The native file replaces the memory card; a missing or corrupt
        // file leaves the factory image, as a failed card read does.
        data.file=saveFile;data.loadFile();
        if(unlockModes) {
            // Byte 43d0d6 lists SURVIVAL and SPIRITS EDIT; one seen ending lists GALLERY.
            data.option(0x7e)=1;
            if(!data.modeMenuUnlock()||!(data.modeMenuUnlock()&2))data.markEndingSeen(0);
        }
        session.restart(); // the title reads the unlock state at entry
    }
    if(stage)session.fixedStage(stage);
    if(items)session.stageItems(true);
    auto screen=std::make_unique<VersusScreen>(assets);
    const bool interactive=snapshot.empty() && dump.empty() && stageDump.empty() && audioOut.empty();
    std::optional<ss6::CombatAudio> mixer;
    ss6::VersusPlayback playback;
    std::optional<ss6::VersusWaveFile> recording;
    if(!audioOut.empty())recording.emplace(audioOut);
    if(recording || interactive) {
        mixer.emplace(assets);
        session.onTick([&](const ss6::NativeMatch& match) {
            for(const auto& event:match.soundEvents()) {
                switch(event.kind) {
                case ss6::BattleSoundKind::BindPlayers:mixer->bindPlayers({unsigned(event.bank),unsigned(event.tone)});break;
                case ss6::BattleSoundKind::Sample:mixer->play(event.bank,event.tone);break;
                case ss6::BattleSoundKind::Voice:mixer->playVoice(event.bank,event.tone);break;
                case ss6::BattleSoundKind::ResidentJingle:mixer->playResidentJingle(event.tone,event.bank);break;
                case ss6::BattleSoundKind::Stop:mixer->stop(event.tone);break;
                case ss6::BattleSoundKind::StopGroup:mixer->stopGroup(event.tone);break;
                case ss6::BattleSoundKind::MusicPreload:mixer->preloadMusic(event.bank,event.tone);break;
                case ss6::BattleSoundKind::MusicStart:mixer->startMusic(event.tone);break;
                case ss6::BattleSoundKind::MusicStop:mixer->stopMusic();break;
                case ss6::BattleSoundKind::MusicPlay:mixer->playMusic(0,event.tone,event.bank);break;
                }
            }
            mixer->tick();
            std::array<int16_t,2*800> pcm;
            mixer->render(pcm);
            if(recording)recording->write(pcm);
            else playback.write(pcm);
        });
    }
    if(mixer)session.onSceneSounds([&](const std::vector<ss6::ArcadeSceneSound>& sounds) {
        // The arcade scenes' own music (1e7c00 ids 11..1b), the scene voice bank 31
        // and their sound banks are not packaged; only the resident menu sounds
        // (1e7b70 group -1) and the music stop reach the mixer.
        for(const auto& e:sounds) {
            if(e.kind==ss6::ArcadeSceneSound::MusicStop)mixer->stopMusic();
            else if(e.kind==ss6::ArcadeSceneSound::Sound&&e.a==-1&&e.b>=0)mixer->play(-1,e.b);
        }
        // A scene frame does not tick the match, so the mixer advances here.
        mixer->tick();
        std::array<int16_t,2*800> pcm;
        mixer->render(pcm);
        if(recording)recording->write(pcm);
        else playback.write(pcm);
    });
    if(!replay.empty()) {
        std::ifstream in(replay);if(!in)throw std::runtime_error("Cannot open match replay");
        std::array<uint32_t,2> previous{};unsigned count;
        std::array<uint32_t,2> held;
        while(ss6::readVersusReplaySegment(in,count,held)) {
            for(unsigned j=0;j<count;++j) {
                std::array<ss6::NormalizedPadSample,2> pads;
                for(unsigned i=0;i<2;++i)pads[i]={held[i],held[i]&~previous[i]};
                session.tick(pads);previous=held;
            }
        }
    }
    for(unsigned i=0;i<updates;++i)session.tick({});
    if(recording){recording->finish();if(snapshot.empty() && dump.empty() && stageDump.empty())return 0;}
    if(!dump.empty() && VersusScreen::arcadeScene(session.arcade())) {
        Frame frame;frame.width=640;frame.height=480;frame.rgba=screen->arcadePicture(*session.arcade());
        writeRgba(dump,frame);
        if(snapshot.empty())return 0;
    }
    if(!dump.empty() || !stageDump.empty()) {
        const auto& frame=screen->paint(session.match(),stageDump);
        if(!dump.empty())writeRgba(dump,frame);
        if(snapshot.empty())return 0;
    }
    using Window=std::unique_ptr<SDL_Window,decltype(&SDL_DestroyWindow)>;
    using Surface=std::unique_ptr<SDL_Surface,decltype(&SDL_DestroySurface)>;
    using Renderer=std::unique_ptr<SDL_Renderer,decltype(&SDL_DestroyRenderer)>;
    using Texture=std::unique_ptr<SDL_Texture,decltype(&SDL_DestroyTexture)>;
    Window window(nullptr,SDL_DestroyWindow);Surface canvas(nullptr,SDL_DestroySurface);
    Renderer renderer(nullptr,SDL_DestroyRenderer);
    if(snapshot.empty()) {
        check(SDL_Init(SDL_INIT_VIDEO));
        // Keyboard matches remain available if the host has no joystick backend.
        SDL_InitSubSystem(SDL_INIT_GAMEPAD);
        SDL_Window* win=nullptr;SDL_Renderer* rend=nullptr;
        check(SDL_CreateWindowAndRenderer("Samurai Shodown VI - Local Versus",960,720,SDL_WINDOW_RESIZABLE,&win,&rend));
        window.reset(win);renderer.reset(rend);
    } else {
        canvas.reset(SDL_CreateSurface(640,480,SDL_PIXELFORMAT_RGBA32));
        if(canvas)renderer.reset(SDL_CreateSoftwareRenderer(canvas.get()));
    }
    if(!renderer)throw std::runtime_error(SDL_GetError());
    check(SDL_SetRenderLogicalPresentation(renderer.get(),640,480,SDL_LOGICAL_PRESENTATION_LETTERBOX));
    Texture texture(SDL_CreateTexture(renderer.get(),SDL_PIXELFORMAT_RGBA32,SDL_TEXTUREACCESS_STREAMING,640,480),SDL_DestroyTexture);
    if(!texture)throw std::runtime_error(SDL_GetError());
    check(SDL_SetTextureScaleMode(texture.get(),SDL_SCALEMODE_NEAREST));
    if(canvas) {
        screen->overlay=sessionOverlay(session);screen->session=&session;
        screen->show(renderer.get(),texture.get(),session.match(),false,boxes);
        check(SDL_SaveBMP(canvas.get(),snapshot.string().c_str()));return 0;
    }
    // Replay warm-up advanced the mixer already. Only live ticks enter the device.
    playback.open();
    ss6::VersusGamepads gamepads;
    VersusControls controls;
    controls.useGamepads(gamepads.held());
    uint64_t previous=SDL_GetTicksNS(),remainder=0;
    constexpr uint64_t period=1000000000ull/60;
    bool paused=false,running=true,redraw=true;unsigned shown=0;
    while(running) {
        SDL_Event e;
        while(SDL_PollEvent(&e)) {
            // Expose and resize events also need the current image when paused.
            if(e.type>=SDL_EVENT_WINDOW_FIRST && e.type<=SDL_EVENT_WINDOW_LAST)redraw=true;
            if(e.type==SDL_EVENT_QUIT)running=false;
            if(e.type>=SDL_EVENT_GAMEPAD_AXIS_MOTION && e.type<=SDL_EVENT_GAMEPAD_REMAPPED) {
                gamepads.event(e);
                controls.useGamepads(gamepads.held());
            }
            if(e.type==SDL_EVENT_WINDOW_FOCUS_LOST){controls={};paused=true;playback.pause(true);remainder=0;}
            if(e.type==SDL_EVENT_WINDOW_FOCUS_GAINED){controls.useGamepads(gamepads.held());controls.clearPresses();}
            if(e.type!=SDL_EVENT_KEY_DOWN&&e.type!=SDL_EVENT_KEY_UP)continue;
            const bool down=e.type==SDL_EVENT_KEY_DOWN;
            if(down&&e.key.repeat)continue;
            redraw=true;
            if(down&&e.key.key==SDLK_ESCAPE)running=false;
            else if(down&&e.key.key==SDLK_R){session.restart();mixer->reset();playback.clear();playback.pause(false);controls={};controls.useGamepads(gamepads.held());controls.clearPresses();remainder=0;paused=false;}
            else if(down&&e.key.key==SDLK_SPACE){paused=!paused;playback.pause(paused);remainder=0;controls.clearPresses();}
            else if(down&&e.key.key==SDLK_N){paused=true;playback.pause(true);playback.clear();remainder=0;controls.tick(session);}
            else if(down&&e.key.key==SDLK_H)boxes=!boxes;
            else controls.key(e.key.key,down);
        }
        const auto now=SDL_GetTicksNS();
        if(!paused)remainder+=std::min(now-previous,uint64_t(250000000));previous=now;
        while(remainder>=period){controls.tick(session);remainder-=period;redraw=true;}
        // The original display advances at the battle cadence. Poll input
        // between ticks without rasterizing the same arena several times.
        if(running&&(redraw||smoke)){
            screen->overlay=sessionOverlay(session);screen->session=&session;
            screen->show(renderer.get(),texture.get(),session.match(),paused,boxes);
            redraw=false;
            if(smoke&&++shown>=smoke)running=false;
        }
        SDL_Delay(4);
    }
    return 0;
}
int main(int argc, char** argv) {
    try {
        fs::path assets = fs::absolute(argv[0]).parent_path() / "assets", dump, snapshot,trialScript,matchReplay,stageDump,audioOut;
        int fixedStage=0;
        bool stageItems=false;
        unsigned index = 0, updates = 0, smokeUpdates = 0, actionId=0;
        int roundTime=-1;
        std::array<unsigned,2> spirits{};
        std::array<bool,2> cpuSeats{};
        bool versus=false;
        auto entry=ss6::VersusEntry::Fight;
        auto versusMode=ss6::VersusMode::Console;
        bool idle = true, rawRequested = false, boxes=false,contacts=false,dumpMirror=false,trial=false,scripted=false,koPreview=false;
        float targetX=64;
        unsigned defensePreset=0;
        for (int i = 1; i < argc; ++i) {
            std::string arg = argv[i];
            if (i + 1 >= argc) throw std::runtime_error("Expected option value");
            if (arg == "--assets") assets = argv[++i];
            else if (arg == "--cpu") cpuSeats=ss6::versusCpuSeats(argv[++i]);
            else if (arg == "--save") saveFile=argv[++i];
            else if (arg == "--unlock-modes") unlockModes=std::string(argv[++i])=="yes";
            else if (arg == "--dump") dump = argv[++i];
            else if (arg=="--p1-spirit" || arg=="--p2-spirit") {
                if(i+1==argc)throw std::invalid_argument(arg+" requires a spirit name");
                spirits[arg=="--p2-spirit"]=ss6::versusSpirit(argv[++i]);
            }
            else if (arg=="--p1-character" || arg=="--p2-character") {
                // Debug, not an original path: the fighter chosen on the select screen is replaced by this
                // id (e.g. Makai Gaoh 43, an arcade boss without a grid cell). See LocalVersus::substituteCharacter.
                const unsigned character=unsigned(std::stoul(argv[++i]));
                if(!ss6::playableFighter(character))throw std::invalid_argument(arg+" expects a ported fighter id");
                const std::string pair=std::to_string(arg=="--p2-character")+":"+std::to_string(character);
                const char* old=std::getenv("SS6_SUBSTITUTE");
                setenv("SS6_SUBSTITUTE",(old&&*old?std::string(old)+","+pair:pair).c_str(),1);
            }
            else if (arg == "--audio-out") audioOut=argv[++i];
            else if (arg == "--dump-stage") stageDump=argv[++i];
            else if (arg == "--items") stageItems=std::stoul(argv[++i])!=0;
            else if (arg == "--stage") {
                fixedStage=std::stoi(argv[++i]);
                if(fixedStage<0||fixedStage>=int(ss6::CombatStageState::stageCount)||!ss6::CombatStageState::supports(unsigned(fixedStage)))
                    throw std::invalid_argument("--stage expects a ported stage number 0..11");
            }
            else if (arg == "--snapshot") snapshot = argv[++i];
            else if (arg == "--round-time") {
                const std::string value=argv[++i];
                if(value!="60"&&value!="90"&&value!="99"&&value!="0")throw std::runtime_error("Round time must be 60, 90, 99 or 0");
                roundTime=std::stoi(value);
            }
            else if (arg == "--match-replay") matchReplay=argv[++i];
            else if (arg == "--trial-script") trialScript = argv[++i];
            else if (arg == "--frame") { index = unsigned(std::stoul(argv[++i])); rawRequested = true; }
            else if (arg == "--idle-updates") updates = unsigned(std::stoul(argv[++i]));
            else if (arg == "--updates") updates = unsigned(std::stoul(argv[++i]));
            else if (arg == "--action") actionId = unsigned(std::stoul(argv[++i]));
            else if (arg == "--boxes") boxes=std::stoul(argv[++i])!=0;
            else if (arg == "--target-x") targetX=std::stof(argv[++i]);
            else if (arg == "--defense") {
                const std::string value=argv[++i];
                if (value!="neutral" && value!="stand" && value!="crouch") throw std::runtime_error("Defense must be neutral, stand or crouch");
                defensePreset=value=="stand" ? 1 : value=="crouch" ? 2 : 0;
            }
            else if (arg == "--scripted-contact") scripted=std::stoul(argv[++i])!=0;
            else if (arg == "--dump-mirror") dumpMirror=std::stoul(argv[++i])!=0;
            else if (arg == "--smoke-updates") smokeUpdates = unsigned(std::stoul(argv[++i]));
            else if (arg == "--mode") {
                std::string mode = argv[++i];
                if (mode != "idle" && mode != "cells" && mode != "contacts" && mode != "trial" && mode!="knockout" && mode!="versus" && mode!="fixed-versus" && mode!="select" && mode!="title" && mode!="arcade")
                    throw std::runtime_error("Unknown mode (expected title, select, versus, fixed-versus, idle, cells, contacts, trial or knockout)");
                entry=mode=="title"?ss6::VersusEntry::Title:mode=="select"?ss6::VersusEntry::CharacterSelect:
                      mode=="arcade"?ss6::VersusEntry::Arcade:ss6::VersusEntry::Fight;
                versus=entry!=ss6::VersusEntry::Fight||mode=="versus"||mode=="fixed-versus";
                versusMode=mode=="fixed-versus"?ss6::VersusMode::FixedMatch:ss6::VersusMode::Console;
                rawRequested = mode == "cells";
                contacts = mode == "contacts";koPreview=mode=="knockout";trial=mode=="trial"||koPreview;
            }
            else throw std::runtime_error("Unknown option " + arg);
        }
        if(updates>1000000)throw std::runtime_error("Too many updates");
        if(!stageDump.empty()&&(!versus||!trialScript.empty()))throw std::runtime_error("--dump-stage requires a versus match");
        if(!audioOut.empty()&&(!versus||!trialScript.empty()))throw std::runtime_error("--audio-out requires a versus match");
        if((cpuSeats[0]||cpuSeats[1])&&(!versus||!trialScript.empty()))throw std::runtime_error("--cpu requires a versus match");
        if(versus&&trialScript.empty())return runVersus(assets,matchReplay,snapshot,dump,stageDump,updates,smokeUpdates,boxes,roundTime,versusMode,audioOut,spirits,entry,cpuSeats,fixedStage,stageItems);
        if(!matchReplay.empty())throw std::runtime_error("--match-replay requires versus mode");
        CharacterSample sample(assets);
        if(trial||(versus&&!trialScript.empty()))return runTrial(assets,sample,snapshot,dump,updates,smokeUpdates,defensePreset,boxes,scripted,targetX,dumpMirror,trialScript,koPreview,actionId);
        if (!std::isfinite(targetX) || targetX<-160 || targetX>160) throw std::runtime_error("Target X must be finite and within -160..160");
        if (dumpMirror && (dump.empty() || rawRequested || contacts)) throw std::runtime_error("--dump-mirror requires a single-action pixel dump");
        auto action=std::make_unique<ss6::ActionClip>(assets,actionId,true);
        auto timeline=std::make_unique<ss6::ActionTimeline>(*action);
        ss6::JudgmentData judgments(assets);
        ss6::CollisionTables collisionTables(assets);
        ss6::CombatTables combatTables(assets);
        constexpr unsigned targetActions[]={0,286,290};
        auto targetAction=std::make_unique<ss6::ActionClip>(assets,targetActions[defensePreset],true);
        auto targetTimeline=std::make_unique<ss6::ActionTimeline>(*targetAction);
        auto advance=[&]{timeline->advance(256);targetTimeline->advance(256);};
        if (updates>1000000) throw std::runtime_error("Too many preview updates");
        for (unsigned i=0; i<updates; ++i) advance();
        idle = !rawRequested;
        auto found = std::find(sample.supported.begin(), sample.supported.end(), index);
        if (found == sample.supported.end()) throw std::runtime_error("Unsupported sample index");
        size_t cursor = size_t(found - sample.supported.begin());
        auto makeScene=[&]{return contactScene(sample,action->record(timeline->clock().step),timeline->motion(),
            targetAction->record(targetTimeline->clock().step),judgments,collisionTables,combatTables,targetX,defensePreset,
            action->id(),targetAction->id());};
        Frame frame = contacts ? makeScene().frame : idle ? sample.compose(action->record(timeline->clock().step),dumpMirror) : sample.decode(index);
        auto render=[&](SDL_Renderer* renderer,bool playing){
            if (idle && contacts) { auto scene=makeScene();drawContacts(renderer,scene,*action,*timeline,playing,boxes); }
            else draw(renderer,frame,index,sample.supported.size(),*action,*timeline,judgments,idle,playing,boxes);
        };
        if (!dump.empty()) {
            std::ofstream out(dump, std::ios::binary);
            for (uint32_t v : {uint32_t(frame.width), uint32_t(frame.height)})
                for (unsigned shift = 0; shift < 32; shift += 8) out.put(char((v >> shift) & 255));
            out.write(reinterpret_cast<const char*>(frame.rgba.data()), std::streamsize(frame.rgba.size()));
            if (!out) throw std::runtime_error("Cannot write pixel dump");
            return 0;
        }
        if (!snapshot.empty()) {
            auto canvas = std::unique_ptr<SDL_Surface, decltype(&SDL_DestroySurface)>(
                SDL_CreateSurface(960, 672, SDL_PIXELFORMAT_RGBA32), SDL_DestroySurface);
            if (!canvas) throw std::runtime_error(SDL_GetError());
            auto renderer = std::unique_ptr<SDL_Renderer, decltype(&SDL_DestroyRenderer)>(
                SDL_CreateSoftwareRenderer(canvas.get()), SDL_DestroyRenderer);
            if (!renderer) throw std::runtime_error(SDL_GetError());
            render(renderer.get(),false);
            check(SDL_SaveBMP(canvas.get(), snapshot.string().c_str()));
            return 0;
        }
        check(SDL_Init(SDL_INIT_VIDEO));
        SDL_Window* window = nullptr; SDL_Renderer* renderer = nullptr;
        check(SDL_CreateWindowAndRenderer("SS6 Native Action Probe", 960, 672, SDL_WINDOW_RESIZABLE, &window, &renderer));
        check(SDL_SetRenderLogicalPresentation(renderer, 960, 672, SDL_LOGICAL_PRESENTATION_LETTERBOX));
        bool running = true, playing = true;
        unsigned rendered = 0;
        uint64_t previous = SDL_GetTicksNS(), remainder = 0;
        // This is the inspection tool's preview cadence, not a claim that the
        // original PS2 scheduler has already been measured at exactly 60 Hz.
        constexpr uint64_t previewPeriod = 1000000000ull/60;
        while (running) {
            SDL_Event event;
            while (SDL_PollEvent(&event)) {
                if (event.type == SDL_EVENT_QUIT) running = false;
                if (event.type == SDL_EVENT_KEY_DOWN && !event.key.repeat) {
                    if (event.key.key == SDLK_ESCAPE) running = false;
                    if (event.key.key == SDLK_TAB) { idle=!idle; remainder=0; }
                    if (event.key.key == SDLK_H) boxes=!boxes;
                    if (event.key.key == SDLK_C) { contacts=!contacts;idle=true;remainder=0; }
                    if (idle && contacts && event.key.key==SDLK_G) {
                        defensePreset=(defensePreset+1)%3;
                        auto next=std::make_unique<ss6::ActionClip>(assets,targetActions[defensePreset],true);
                        targetTimeline=std::make_unique<ss6::ActionTimeline>(*next);targetAction=std::move(next);
                        timeline->reset();remainder=0;
                    }
                    if (idle && contacts && event.key.key==SDLK_LEFT) targetX=std::max(-160.0f,targetX-4);
                    if (idle && contacts && event.key.key==SDLK_RIGHT) targetX=std::min(160.0f,targetX+4);
                    if (event.key.key>=SDLK_1 && event.key.key<=SDLK_4) {
                        constexpr unsigned ids[]={0,10,12,185};
                        // Selection restarts a standalone inspection fixture;
                        // these keys do not implement the original pad parser.
                        auto next=std::make_unique<ss6::ActionClip>(assets,ids[event.key.key-SDLK_1],true);
                        timeline=std::make_unique<ss6::ActionTimeline>(*next);
                        action=std::move(next);
                        targetTimeline->reset();
                        idle=true; playing=true; remainder=0;
                    }
                    if (idle && event.key.key == SDLK_SPACE) { playing=!playing; remainder=0; }
                    if (idle && event.key.key == SDLK_N) { playing=false; remainder=0; advance(); }
                    if (idle && event.key.key == SDLK_R) { timeline->reset();targetTimeline->reset();remainder=0; }
                    if (!idle && event.key.key == SDLK_RIGHT) cursor = (cursor+1)%sample.supported.size();
                    if (!idle && event.key.key == SDLK_LEFT) cursor = (cursor+sample.supported.size()-1)%sample.supported.size();
                }
            }
            const uint64_t now = SDL_GetTicksNS();
            if (idle && playing) remainder += std::min(now-previous,uint64_t(250000000));
            previous = now;
            while (remainder >= previewPeriod) { advance(); remainder-=previewPeriod; }
            if (running) {
                index = sample.supported[cursor];
                frame = idle ? sample.compose(action->record(timeline->clock().step)) : sample.decode(index);
                render(renderer,playing);
                if (smokeUpdates && ++rendered>=smokeUpdates) running=false;
            }
            SDL_Delay(8);
        }
        SDL_DestroyRenderer(renderer); SDL_DestroyWindow(window); SDL_Quit();
        return 0;
    } catch (const std::exception& e) { std::cerr << e.what() << '\n'; return 1; }
}
