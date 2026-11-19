#include "versus_faceoff.hpp"
#include <algorithm>
#include <bit>
#include <fstream>
#include <stdexcept>

namespace ss6 {
namespace {
using Bytes=std::vector<uint8_t>;
Bytes read(const std::filesystem::path& path) {
    std::ifstream stream(path,std::ios::binary|std::ios::ate);
    if(!stream||stream.tellg()<0||stream.tellg()>2*1024*1024)throw std::runtime_error("Invalid versus asset: "+path.string());
    Bytes result(static_cast<size_t>(stream.tellg()));
    stream.seekg(0);
    if(!stream.read(reinterpret_cast<char*>(result.data()),result.size()))throw std::runtime_error("Truncated versus asset: "+path.string());
    return result;
}
uint32_t word(const Bytes& bytes,size_t offset,unsigned count) {
    uint32_t n=0;
    for(unsigned i=0;i<count;++i)n|=uint32_t(bytes.at(offset+i))<<(8*i);
    return n;
}
}
void VersusFaceoff::tick(const std::array<uint32_t,2>& pressed,const std::array<unsigned,2>& characters,SoundSelection& sound) {
    white=flashNext;flashNext=false;
    const auto edge=pressed[0]|pressed[1];
    // Start queues the fight directly. Face buttons fast-forward only the
    // foreground to 480 and let the background and announcer keep their clocks.
    if(!requested&&frame>=31&&(edge&8))requested=true;
    if(!requested&&frame>=30&&frame<480&&(edge&0x607)) {
        if(frame<290)flashNext=true;
        frame=480;sound.stopGroup(2);
    }
    drawFrame=frame;drawBackground=background++;
    if(frame==16||frame==18||frame==20||frame==275||frame==277||frame==279)flashNext=true;
    if(frame==31||frame==290) {
        const auto id=characters[frame==290];
        sound.voice(49,id==42?100:int(id)+(id<44?2:45));
    } else if(frame==191)sound.voice(49,76);
    if(++frame==500&&!requested){sound.stopMusic();sound.stopGroup(2);requested=true;}
    if(requested)++transitionTick;
}

VersusFaceoffArt::VersusFaceoffArt(const std::filesystem::path& path,const std::array<unsigned,2>& characters) {
    auto layout=read(path/"vs_faceoff_layout.bin");
    size_t pos=0;
    auto take=[&](unsigned bytes){const auto n=word(layout,pos,bytes);pos+=bytes;return n;};
    if(take(4)!=0x4f465356||take(4)!=1)throw std::runtime_error("Invalid VS face-off layout");
    const auto frames=take(4),rects=take(4);
    if(frames!=540||rects>65535)throw std::runtime_error("Invalid VS face-off timeline");
    for(unsigned i=0;i<rects;++i) {
        const auto slot=take(1),alpha=take(1);
        if(slot!=0&&slot!=4&&slot!=6&&slot!=8&&slot!=12)throw std::runtime_error("Invalid VS texture slot");
        std::array<int,8> sides;
        for(auto& value:sides)value=std::bit_cast<int16_t>(uint16_t(take(2)));
        rects_.push_back({slot,alpha,sides[0],sides[1],sides[2],sides[3],sides[4],sides[5],sides[6],sides[7]});
    }
    for(unsigned i=0;i<frames;++i) {
        auto& f=frames_.emplace_back();f.background=take(2);
        const auto count=take(1);
        if(f.background>=rects||count>90)throw std::runtime_error("Invalid VS draw list");
        for(unsigned j=0;j<count;++j){auto at=take(2);if(at>=rects)throw std::runtime_error("Invalid VS rectangle");f.rects.push_back(at);}
    }
    if(pos!=layout.size())throw std::runtime_error("Trailing VS timeline data");
    auto& backdrop=textures_[4];backdrop.size=1024;backdrop.indices=read(path/"vs_back.tex");
    const auto lower=read(path/"vs_obj.pal"),upper=read(path/"vs_back.pal");
    for(unsigned i=0;i<256;++i) {
        // 125edc replaces entries 128..255 with the second half of the
        // background CLUT. Slot 12 instead carries its own embedded palette.
        const auto v=word(i<128?lower:upper,i*2,2);
        backdrop.clut[i]=(v&0x8000)?0x80000000u|((v&31)<<19)|(((v>>5)&31)<<11)|(((v>>10)&31)<<3):0;
    }
    backdrop.clut[0]=0;
    auto& trim=textures_[12];trim.size=512;trim.indices=read(path/"vs_obj.tex");
    for(unsigned i=0;i<256;++i) {
        const unsigned swapped=(i&~24u)|((i&8)<<1)|((i&16)>>1);
        trim.clut[i]=word(trim.indices,512*512+swapped*4,4);
    }
    trim.indices.resize(512*512);
    for(unsigned side=0;side<2;++side) {
        auto& face=textures_[side?6:8];face.size=512;
        const auto id=std::to_string(characters[side]);
        const auto stem=std::string("bup_")+(id.size()==1?"0":"")+id;
        face.indices=read(path/(stem+".tex"));auto colors=read(path/(stem+".pal"));
        for(unsigned i=0;i<256;++i)face.clut[i]=word(colors,i*4,4);
    }
    for(const auto& texture:textures_)if(texture.indices.size()!=size_t(texture.size*texture.size))
        throw std::runtime_error("Invalid VS texture dimensions");
}
void VersusFaceoffArt::draw(const Rect& r,std::span<uint8_t> rgba) const {
    const int left=std::max(0,r.x0),right=std::min(640,r.x1),top=std::max(0,r.y0),bottom=std::min(480,r.y1);
    if(left>=right||top>=bottom)return;
    const auto& tex=textures_[r.slot];
    // Pixel centers match the original screen-aligned strips, including
    // reversed UVs on the incoming portrait and the independently zooming sky.
    auto coordinate=[](int pixel,int start,int end,int uv,int uvEnd,int size){
        const int denominator=2*(end-start);
        return std::clamp((uv*denominator+(2*(pixel-start)+1)*(uvEnd-uv))/denominator,0,size-1);
    };
    for(int y=top;y<bottom;++y) {
        const int v=r.slot?coordinate(y,r.y0,r.y1,r.v0,r.v1,tex.size):0;
        auto dst=rgba.data()+(640*y+left)*4;
        for(int x=left;x<right;++x,dst+=4) {
            uint32_t color=0;int alpha=(r.alpha+1)/2;
            if(r.slot) {
                const int u=coordinate(x,r.x0,r.x1,r.u0,r.u1,tex.size);
                color=tex.clut[tex.indices[v*tex.size+u]];
                alpha=(int(color>>24)*alpha)>>7;
            }
            for(unsigned ch=0;ch<3;++ch)dst[ch]=uint8_t(std::clamp(int(dst[ch])+(((int(uint8_t(color>>(8*ch)))-dst[ch])*alpha)>>7),0,255));
        }
    }
}
void VersusFaceoffArt::paint(const VersusFaceoff& state,std::span<uint8_t> rgba) const {
    if(rgba.size()!=640*480*4)throw std::invalid_argument("VS face-off requires a 640x480 surface");
    if(state.white){std::fill(rgba.begin(),rgba.end(),255);return;}
    for(size_t i=0;i<rgba.size();i+=4){rgba[i]=rgba[i+1]=rgba[i+2]=0;rgba[i+3]=255;}
    draw(rects_[frames_.at(state.drawBackground).background],rgba);
    for(auto index:frames_.at(state.drawFrame).rects)draw(rects_[index],rgba);
}
}
