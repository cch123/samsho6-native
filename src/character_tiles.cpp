#include "character_tiles.hpp"
#include <algorithm>
#include <bit>
#include <fstream>
#include "fighter_resource_path.hpp"
#include <stdexcept>

namespace ss6 {
namespace {
using F=ScalarFloat;
std::vector<uint8_t> read(const std::filesystem::path& path) {
    std::ifstream f(path,std::ios::binary|std::ios::ate);if(!f)throw std::runtime_error("Missing tile resource: "+path.string());
    const auto n=f.tellg();if(n<0||n>32*1024*1024)throw std::runtime_error("Invalid tile resource size");
    std::vector<uint8_t> bytes(static_cast<size_t>(n));f.seekg(0);if(!f.read(reinterpret_cast<char*>(bytes.data()),n))throw std::runtime_error("Truncated tile resource");return bytes;
}
uint32_t word(const std::vector<uint8_t>& b,size_t at,unsigned n) {uint32_t v=0;for(unsigned i=0;i<n;++i)v|=uint32_t(b.at(at+i))<<(i*8);return v;}
uint32_t shift8(uint32_t v){return uint32_t(std::bit_cast<int32_t>(v)>>8);}
F floor(F v) {auto n=v.truncate();if(v.less(F::integer(n)))--n;return F::integer(n);}
uint32_t tint(uint32_t color,const CharacterTileState& state) {
    if(!(state.tintFlags&2))return color;
    uint32_t out=color&0xff000000;
    //117288 uses wrapped32-bit products and an arithmetic shift, not
    //clamped host interpolation. Ordinary fade amounts are0..256.
    for(unsigned i=0;i<3;++i)out+=shift8(((color>>(i*8))&255)*(256-state.tintAmount)+((state.tintColor>>(i*8))&255)*state.tintAmount)<<(i*8);
    return out;
}
constexpr std::array<unsigned,24> paletteSlots={16,17,18,19,20,21,22,23,24,25,26,27,28,29,30,31,12,13,14,15,8,9,10,11};
}
CharacterPaletteBank::CharacterPaletteBank(const std::filesystem::path& assets):source_(read(assets/"pal_all.bin")) {
    if(source_.size()!=266240)throw std::runtime_error("Unexpected original palette arena");
}
int CharacterPaletteBank::resolve(uint32_t key,unsigned bank,EffectPalettes& cache) {
    if((key>>16)&3)throw std::runtime_error("Alternate palette-source mode not yet implemented");
    const auto logical=(key&0xffff)*32+bank;
    const auto tag=logical+0x10000;
    for(unsigned i=0;i<24;++i)if(!cache[2][i]&&cache[0][i]==tag){cache[1][i]=1;return int(paletteSlots[i]);}
    unsigned slot=24;
    for(unsigned i=0;i<24;++i)if(!cache[2][i]&&cache[0][i]==0xffffffff){slot=i;break;}
    if(slot==24)for(unsigned i=0;i<24;++i)if(!cache[2][i]&&!cache[1][i]){slot=i;break;}
    if(slot==24)return -1;
    const auto offset=size_t(logical)*32;
    if(offset+32>source_.size())throw std::runtime_error("Palette group outside resident arena");
    //115f08 mutates the source palette's first color before the copy.
    //Clearing only the displayed alpha would miss the retained arena state.
    source_[offset]=source_[offset+1]=0;
    const auto target=paletteSlots[slot]*16;
    for(unsigned i=0;i<16;++i){raw16[target+i]=uint16_t(word(source_,offset+i*2,2));format[target+i]=0;}
    cache[0][slot]=tag;cache[1][slot]=1;return int(paletteSlots[slot]);
}
void CharacterPaletteBank::colorize(uint32_t flags,uint32_t fadeColor,uint32_t amount,std::span<const uint16_t,1024> tones) {
    const uint32_t mask=amount?0xffffffff:~2u;
    for(unsigned i=0;i<1024;++i) {
        const auto color=format[i]?raw32[i]:uint32_t(raw16[i]);
        if(format[i]?!(color&0xff000000):!(color&0x8000)){rgba[i]=0;continue;}
        const uint32_t mode=(tones[i]|flags)&mask;
        uint32_t r=format[i]?(color>>3)&31:(color>>10)&31;
        uint32_t g=format[i]?(color>>11)&31:(color>>5)&31;
        uint32_t b=format[i]?(color>>19)&31:color&31;
        if(mode&5)r=g=b=(r*10+g*16+b*6)>>5;
        if(mode&2) {
            r=shift8(r*(256-amount)+((fadeColor>>19)&31)*amount)&31;
            g=shift8(g*(256-amount)+((fadeColor>>11)&31)*amount)&31;
            b=shift8(b*(256-amount)+((fadeColor>>3)&31)*amount)&31;
        }
        //Untinted32-bit entries keep their low three channel bits. Applying
        //any tone selects the original5-bit conversion, even unknown bits.
        rgba[i]=(format[i]&&!mode)?color:((format[i]?color&0xff000000:0x80000000)|(b<<19)|(g<<11)|(r<<3));
    }
}
const CharacterTiles::Resource& CharacterTiles::resource(unsigned slot) {
    const auto id=slots_.at(slot);auto found=resources_.find(id);
    if(found==resources_.end()) {
        found=resources_.emplace(id,Resource{read(fighterResourcePath(assets_,"idx",id)),read(fighterResourcePath(assets_,"map",id)),read(fighterResourcePath(assets_,"chr",id))}).first;
    }
    return found->second;
}
void CharacterTiles::submitObject(CharacterDraws& prepare,CharacterDrawState& drawState,const ObjectDrawQueue::Record& object,
                                  const CharacterDrawContext& context,EffectPalettes& cache,CharacterTileState& state,
                                  std::vector<CharacterTileQuad>& out) {
    drawState.primitiveColor=state.primitiveColor;
    std::vector<CharacterSprite> sprites;prepare.submit(object,context,drawState,sprites);
    for(const auto& sprite:sprites)submit(sprite,cache,state,out);
    //1208b0 restores the primitive-color override after all nested parts.
    //An invisible object instead preserves the incoming value unchanged.
    state.primitiveColor=drawState.primitiveColor;
}
void CharacterTiles::submit(const CharacterSprite& s,EffectPalettes& cache,CharacterTileState& state,std::vector<CharacterTileQuad>& out) {
    //The caller publishes primitiveColor even when121b80's own disable gate
    //returns immediately. Other packet globals retain their previous values.
    state.primitiveColor=s.color;if(state.disabled)return;
    auto x=s.x,y=s.y,sx=s.scaleX,sy=s.scaleY;const auto& r=resource(s.slot);
    if(sx.bits==0x3f800000||sx.bits==0x3f000000)x=floor(x.add(F{0x3f000000}));
    if(sy.bits==0x3f800000||sy.bits==0x3f000000)y=floor(y.add(F{0x3f000000}));
    const auto entry=word(r.idx,size_t(s.image)*4,4);if(entry==0xffffffff)return;
    auto bank=(entry>>24)&31,flags=s.flags;const auto id=slots_.at(s.slot);
    if(flags&0x80000000) {
        if(id==12&&bank==21)bank=20;else if(id==11&&bank==1)bank=3;else if(id==33&&bank==1)bank=5;
        else if(id==48){if(bank==0)bank=6;else if(bank==1)bank=7;else if(bank==16||bank==26||bank==28)bank=28;}
    }
    const auto at=entry&0xffffff;const auto width=word(r.map,at,1),height=word(r.map,at+1,1);
    if(!width||!height||(width&1)||(height&1))throw std::runtime_error("Unsupported character tile dimensions");
    if(uint64_t(at)+2+uint64_t(width)*height*3>r.map.size())throw std::runtime_error("Truncated character tile map");
    sx=sx.mul(F{0x42000000});sy=sy.mul(F{0x42000000});const bool rotated=flags&0x2000;
    if(flags&0x80000){flags^=rotated?0x4000:0x8000;x=x.sub(F::integer(int32_t((rotated?height:width)/2)).mul(sx));}
    if(flags&0x40000){flags^=rotated?0x8000:0x4000;y=y.sub(F::integer(int32_t((rotated?width:height)/2)).mul(sy));}
    uint32_t color=s.color,fixedAlpha=128;state.blendMode=0;
    if(s.mode==1) {
        if((s.contextFlags&0x10000)&&bank>=2)color=(color&0xff000000)|0x808080;
        if((flags&0x80000000)&&(s.contextFlags&0x2000)&&bank==5)color=(s.color&0xff000000)|0xc8c8c8;
        state.primitiveColor=color;
        if((color&255)>128&&((color>>8)&255)>128&&((color>>16)&255)>128) {
            state.blendMode=3;fixedAlpha=((color>>24)+1)/2;color=0xffffff|((((color>>16)&255)-128)<<24);
        }else color=(color&0xffffff)|(((color>>24)+1)/2<<24);
    }else {
        color=tint(color,state);uint32_t converted=0;
        for(unsigned i=0;i<4;++i)converted|=(((color>>(i*8)&255)+1)/2)<<(i*8);
        color=converted;
    }
    const auto palette=palettes.resolve(s.palette,bank,cache);if(palette<0)return;
    const auto z=F{0x4b189680}.sub(s.z.add(s.depthOffset).mul(F{0x42c80000})).add(F::integer(std::bit_cast<int32_t>(state.depthCounter++)));
    const bool fx=flags&0x8000,fy=flags&0x4000;
    for(unsigned group=0;group<width*height/4;++group) {
        if(state.groups>=1024)return; //Original stops before reading the next tile.
        std::array<uint32_t,4> tiles;bool nonempty=false;
        for(unsigned j=0;j<4;++j){tiles[j]=word(r.map,at+2+(group*4+j)*3,3)&0xfffff;nonempty|=tiles[j]!=0;}
        if(!nonempty)continue;
        const auto col=group%(width/2),row=group/(width/2);
        auto gx=x.add(F::integer(int32_t(rotated?(fy?height/2-row:row):(fx?width/2-col:col))).mul(sx));
        auto gy=y.add(F::integer(int32_t(rotated?(fx?width/2-col:col):(fy?height/2-row:row))).mul(sy));
        F x0=gx,x1=gx.add(sx),y0=gy,y1=gy.add(sy);
        const auto atlas=state.groups;const auto u=F::integer(int32_t(atlas%32*16)).mul(F{0x3b000000});
        const auto v=F::integer(int32_t(atlas/32*16)).mul(F{0x3b000000});
        auto u0=u,u1=u.add(F{0x3d000000}),v0=v,v1=v.add(F{0x3d000000});
        const F epsilon{0x3a800000},small{0x39000000};
        if(rotated) {
            if(fy)x1=gx.sub(sx);if(fx)y1=gy.sub(sy);
            u0=u0.add(fy?small:epsilon);u1=u1.sub(fy?epsilon:small);
            v0=v0.add(fx?small:epsilon);v1=v1.sub(fx?epsilon:small);
            if((x0.less(F{0})&&x1.less(F{0}))||(F{0x44200000}.less(x0)&&F{0x44200000}.less(x1))||
               (y0.less(F{0})&&y1.less(F{0}))||(F{0x43e00000}.less(y0)&&F{0x43e00000}.less(y1)))continue;
        }else {
            if(fx){x0=gx.sub(sx);x1=gx;}if(fy){y0=gy.sub(sy);y1=gy;}
            if(sx.bits!=0x42000000&&sx.bits!=0x41800000){u0=u0.add(epsilon);u1=u1.sub(epsilon);}
            if(sy.bits!=0x42000000&&sy.bits!=0x41800000){v0=v0.add(epsilon);v1=v1.sub(epsilon);}
            if(x1.less(F{0})||F{0x44200000}.less(x0)||y1.less(F{0})||F{0x43e00000}.less(y0))continue;
        }
        CharacterTileQuad q;q.paletteArgument=uint32_t(palette)|(fixedAlpha<<8);q.blendMode=state.blendMode;q.additive=s.additive;
        auto vertex=[&](unsigned i,F xx,F yy,F uu,F vv){const std::array<uint32_t,6> w={xx.bits,yy.bits,z.bits,uu.bits,vv.bits,color};std::copy(w.begin(),w.end(),q.vertices.begin()+i*6);};
        vertex(0,x0,y0,u0,v0);
        if(rotated){vertex(1,x1,y0,u0,v1);vertex(2,x0,y1,u1,v0);}else{vertex(1,x0,y1,u0,v1);vertex(2,x1,y0,u1,v0);}
        vertex(3,x1,y1,u1,v1);out.push_back(q);
        //Nonrotated sprites physically mirror the four tiles and their
        //nibbles in the atlas. The rotated branch instead changes vertices
        //and UV orientation, so its atlas copy must remain unflipped.
        for(unsigned yy=0;yy<16;++yy)for(unsigned xx=0;xx<16;++xx) {
            const unsigned tx=!rotated&&fx?15-xx:xx,ty=!rotated&&fy?15-yy:yy;
            const auto tile=tiles[(ty/8)*2+tx/8];uint8_t value=0;
            if(tile){const auto byte=r.chr.at(size_t(tile)*32+(ty%8)*4+(tx%8)/2);value=(byte>>((tx%2)*4))&15;}
            const size_t dst=(atlas/32*16+yy)*256+(atlas%32*16+xx)/2;
            const auto shift=(xx%2)*4;state.atlas[dst]=uint8_t((state.atlas[dst]&~(15u<<shift))|(value<<shift));
        }
        ++state.groups;
    }
}
}
