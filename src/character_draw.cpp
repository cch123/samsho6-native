#include "asset_files.hpp"
#include "character_draw.hpp"
#include "action_runtime.hpp"
#include <algorithm>
#include <bit>
#include <fstream>
#include "fighter_resource_path.hpp"
#include <stdexcept>

namespace ss6 {
namespace {
using F=ScalarFloat;
std::vector<uint8_t> read(const std::filesystem::path& path) {
    std::ifstream in(resolveAsset(path),std::ios::binary|std::ios::ate);
    if(!in)throw std::runtime_error("Missing character draw resource: "+path.string());
    const auto n=in.tellg();if(n<0||n>32*1024*1024)throw std::runtime_error("Invalid character draw resource size");
    std::vector<uint8_t> out(static_cast<size_t>(n));in.seekg(0);
    if(!in.read(reinterpret_cast<char*>(out.data()),n))throw std::runtime_error("Truncated character draw resource");
    return out;
}
uint32_t word(const std::vector<uint8_t>& data,size_t at,unsigned n) {
    uint32_t v=0;for(unsigned i=0;i<n;++i)v|=uint32_t(data.at(at+i))<<(i*8);return v;
}
int16_t half(const std::vector<uint8_t>& data,size_t at){return std::bit_cast<int16_t>(uint16_t(word(data,at,2)));}
F number(float v){return {std::bit_cast<uint32_t>(v)};}
F integer(uint32_t v){return F::integer(std::bit_cast<int32_t>(v));}
F twice(F v){return v.add(v);}
F quantize(F v) {
    //310be0/30bb20/311510 floor(scale*128), then multiply by1/128.
    //Truncation is wrong for negative values and would move a mirrored quad.
    const auto scaled=v.mul(F{0x43000000});auto n=scaled.truncate();
    if(scaled.less(F::integer(n)))--n;
    return F::integer(n).mul(F{0x3c000000});
}
uint32_t capAlpha(uint32_t color,uint32_t part) {
    return (color&0xffffff)|(std::min(color>>24,part>>24)<<24);
}
}
const CharacterDraws::Resource& CharacterDraws::resource(unsigned slot) {
    const auto id=slots_.at(slot);auto found=resources_.find(id);
    if(found==resources_.end()) {
        Resource r{read(characterResourcePath(assets_,"aid",id)),read(characterResourcePath(assets_,"act",id)),read(characterResourcePath(assets_,"pil",id))};
        if(r.aid.size()!=0x1800||r.act.size()%60||r.pil.size()%16)throw std::runtime_error("Invalid character draw record layout");
        found=resources_.emplace(id,std::move(r)).first;
    }
    return found->second;
}
void CharacterDraws::submit(const ObjectDrawQueue::Record& o,const CharacterDrawContext& c,
                           CharacterDrawState& state,std::vector<CharacterSprite>& out) {
    if(o[0x144/4])throw std::runtime_error("Character draw requires queue kind0");
    const auto slot=o[0xc/4],action=o[0x24/4],step=o[0x28/4];const auto& r=resource(slot);
    if(action>=2048)throw std::runtime_error("Invalid queued character action");
    const size_t at=size_t(fighterActionRecord(slots_.at(slot),action,half(r.aid,action*2),r.aid.at(0x1000+action),std::bit_cast<int32_t>(step)))*60;
    std::array<int16_t,5> refs;for(unsigned i=0;i<5;++i)refs[i]=half(r.act,at+4+i*2);
    if(o[0x104/4]&2)return; //Hidden objects leave the shared render state intact.
    const auto originalFlags=o[0x38/4];
    const auto offsetX=integer(o[0xe4/4]).add(F{o[0xec/4]});
    F x=originalFlags&0x80000?F{o[0x40/4]}.sub(offsetX):F{o[0x40/4]}.add(offsetX);
    F y=F{o[0x44/4]}.add(F{o[0xf0/4]}).add(integer(o[0xe8/4]));
    const auto dx=F::integer(std::bit_cast<int16_t>(uint16_t(o[0x4c/4]>>16)));
    const auto dy=F::integer(std::bit_cast<int16_t>(uint16_t(o[0x58/4]>>16)));
    x=originalFlags&0x80000?x.sub(dx):x.add(dx);
    y=originalFlags&0x40000?y.sub(dy):y.add(dy);
    state.primitiveColor=0xffffffff;state.flags=originalFlags;state.color=o[0x8c/4];
    auto clocks=c.clockFlags;if(slot<2)clocks[slot]=0;
    if(((clocks[0]|clocks[1])&1)||(c.focus!=-2&&uint32_t(c.focus)!=o[0x10/4])) {
        state.flags=(originalFlags&~0x40000000u)|0x800000;
        if(!(originalFlags&0x40000000))state.color=0xff808080;
    }
    state.depthOffset={o[0xb0/4]};
    //1041000 changes the part-facing argument AFTER the anchored position
    //has been calculated with the original orientation. Do not recompute X.
    const auto flags=(o[0x104/4]&0x1000)?originalFlags&~0x80000u:originalFlags;
    const auto palette=o[0x1c/4]+o[0x20/4];const F z{o[0x48/4]},scale{o[0x70/4]};
    auto emitParts=[&](F px,F py,F pz,F sx,F sy,uint32_t orientation,bool shadow,bool black) {
        //PIL's16 layers are traversed before the five ACT references. Both
        //duplicate references and relative order within a layer are visible.
        for(unsigned layer=0;layer<16;++layer)for(auto ref:refs) {
            if(!ref)continue;if(ref<0)throw std::runtime_error("Negative queued PIL reference");
            const auto part=size_t(ref-1)*16;const auto partFlags=word(r.pil,part+12,2);
            if((partFlags&15)!=layer)continue;const auto image=half(r.pil,part);
            if(!image)continue;if(image<0)throw std::runtime_error("Negative queued image reference");
            const auto tint=word(r.pil,part+8,4);
            if(shadow&&((partFlags&0x20)||(tint>>24)!=255))continue;
            const auto ox=twice(F::integer(half(r.pil,part+2)).mul(sx));
            const auto oy=twice(F::integer(half(r.pil,part+4)).mul(sy));
            if(shadow)state.mode=3;
            else if((partFlags&0x20)&&!black) {
                if(state.flags&0x8000)continue;
                state.mode=2;state.primitiveColor=tint;state.additive=1;
            }else {
                state.mode=1;state.additive=0;
                if(state.flags&0x40000000)state.primitiveColor=capAlpha(state.color,tint);
                else if(state.flags&0x800000)state.primitiveColor=capAlpha((state.color&0xff000000)|((state.color>>1)&0x007f7f7f),tint);
                else if(orientation&0x10000)state.primitiveColor=0xff808080;
                else state.primitiveColor=tint;
            }
            out.push_back({slot,palette,uint32_t(image-1),(orientation&0xffff0000)|partFlags,uint32_t(shadow),
                (orientation&0x80000)?px.sub(ox):px.add(ox),(orientation&0x40000)?py.add(oy):py.sub(oy),
                pz,sx,sy,state.mode,state.primitiveColor,state.flags,state.color,state.additive,state.depthOffset});
        }
    };
    const auto& camera=c.camera;
    auto project=[&](F px,F py,F pz) {
        const auto s=scale.mul(number(camera.depthOffset).sub(number(camera.depth)).div(pz.sub(number(camera.depth))));
        const auto xx=px.sub(number(camera.projectionX)).mul(s).sub(F{0xc3200000}); //global4a2a64=-160
        const auto yy=py.sub(number(camera.projectionY)).mul(s).sub(number(camera.verticalOffset)).add(s.mul(F{0x41400000}));
        return std::array<F,3>{twice(xx),F{0x43e00000}.sub(twice(yy)),quantize(s)};
    };
    F screenX=x,screenY=y,displayScale=scale;
    if(!(flags&0x100000)) {
        if(!(flags&0x200000)) {
            const auto shadowZ=z.add(F{0x40a00000});const auto q=project(x,F{o[0xb4/4]},shadowZ);
            state.primitiveColor=(state.flags&0x800000)?((state.color>>1)&0x7f000000):0x80000000;
            emitParts(q[0],q[1],shadowZ,q[2],q[2].mul(F{0x3e19999a}),flags^0x40000,true,false);
        }
        const auto q=project(x,y,z);screenX=q[0];screenY=q[1];displayScale=q[2];
    }else {screenX=twice(x);screenY=F{0x43e00000}.sub(twice(y));}
    if(flags&0x20000000) {
        const auto one=F{0x3f800000},fourHundred=F{0x43c80000};
        displayScale=quantize(displayScale.mul(one.sub(fourHundred.div(z.add(fourHundred))).add(one)));
    }
    const bool black=((flags&0x1000)&&!(state.color&0xffffff))||((flags&0x10000)&&(c.stage==15||c.stage==16));
    emitParts(screenX,screenY,z,displayScale,displayScale,flags,false,black);
    //121734 tail-calls1142c8 even when the last part was additive or no
    //part survived filtering. Otherwise blending leaks into the next draw.
    state.additive=0;state.primitiveColor=0xffffffff;
}
}
