#include "asset_files.hpp"
#include "versus_result_art.hpp"
#include <algorithm>
#include <bit>
#include <cmath>
#include <fstream>
#include <stdexcept>
#include <string>

namespace ss6 {
namespace {
constexpr int width=640;
std::vector<uint8_t> load(const std::filesystem::path& path,size_t size) {
    std::ifstream input(resolveAsset(path),std::ios::binary|std::ios::ate);
    if(!input || input.tellg()!=static_cast<std::streamoff>(size))
        throw std::runtime_error("Missing or invalid result resource: "+path.string());
    std::vector<uint8_t> bytes(size);
    input.seekg(0);
    if(!input.read(reinterpret_cast<char*>(bytes.data()),size)) throw std::runtime_error("Short read: "+path.string());
    return bytes;
}

unsigned read(const uint8_t*& ptr,unsigned bytes) {
    unsigned value=0;
    for(unsigned i=0;i<bytes;++i) value|=unsigned(*ptr++)<<(8*i);
    return value;
}

void blend(uint8_t* dst,uint32_t color) {
    const int alpha=int(color>>24);
    for(int c=0;c<3;++c) dst[c]+=((int(uint8_t(color>>(8*c)))-dst[c])*alpha)>>7;
}
void clear(std::span<uint8_t> dst,uint8_t value) {
    for(size_t i=0;i<dst.size();i+=4) {dst[i]=value;dst[i+1]=value;dst[i+2]=value;dst[i+3]=255;}
}
}

VersusResultArt::VersusResultArt(const std::filesystem::path& assets) {
    const auto layout=load(assets/"versus_result_layout.bin",17432);
    const auto* ptr=layout.data();
    if(read(ptr,4)!=0x52415356 || read(ptr,4)!=1) throw std::runtime_error("Invalid result layout");
    for(auto& row:rows_) for(auto& tile:row) {
        tile={read(ptr,2),read(ptr,2),read(ptr,2),read(ptr,2),read(ptr,2),read(ptr,2)};
        if(tile.w!=83 || tile.u+tile.w>1024 || tile.v+tile.h>1024 || tile.y+tile.h>480)
            throw std::runtime_error("Invalid result background tile bounds");
    }
    for(auto& side:poses_) for(auto& pose:side) {
        pose.count=read(ptr,4);
        if(pose.count>2) throw std::runtime_error("Invalid result portrait slice count");
        for(auto& quad:pose.slices) for(auto& vertex:quad) {
            vertex={std::bit_cast<float>(read(ptr,4)),std::bit_cast<float>(read(ptr,4)),
                    std::bit_cast<float>(read(ptr,4)),std::bit_cast<float>(read(ptr,4))};
            if(!std::isfinite(vertex.x)||!std::isfinite(vertex.y)||std::abs(vertex.x)>4096 ||
               std::abs(vertex.y)>4096 || !(vertex.u>=0&&vertex.u<=512&&vertex.v>=0&&vertex.v<=512))
                throw std::runtime_error("Invalid result portrait projection");
        }
    }

    const auto board=load(assets/"menu_bg00_00.tex",1024*1024+1024);
    background_.resize(1024*1024);
    std::array<uint32_t,256> colors;
    for(unsigned i=0;i<256;++i) {
        // 1162f0 uses the file's appended CLUT. 109598 transfers it in a
        // single 16x16 rectangle, so logical PSMT8 indices use CSM1 order.
        const auto j=(i&~24u)|((i&8u)<<1)|((i&16u)>>1);
        const uint8_t* entry=board.data()+1024*1024+j*4;
        colors[i]=read(entry,4);
    }
    std::transform(board.begin(),board.begin()+background_.size(),background_.begin(),
                   [&](uint8_t index){return colors[index];});
    const auto face=load(assets/"win_00.tex",512*512);
    const auto palette=load(assets/"win_00.pal",512);
    ptr=palette.data();
    for(auto& color:colors) {
        // This atlas uses a separate 1555 palette. 109398 uploads its
        // 8x2 strips in CSM1 order already, unlike the embedded CLUT above.
        const auto p=read(ptr,2);
        color=(p&0x8000)?0x80000000u|((p&31)<<19)|(((p>>5)&31)<<11)|(((p>>10)&31)<<3):0;
    }
    colors[0]=0;  // 135f70 clears the first copied entry.
    portrait_.resize(face.size());
    std::transform(face.begin(),face.end(),portrait_.begin(),[&](uint8_t index){return colors[index];});
}

void VersusResultArt::drawBackground(unsigned tick,std::span<uint8_t> target,int height) const {
    for(unsigned row=0;row<rows_.size();++row) {
        // 135438 scrolls three banks independently. EE truncation of
        // 83/0.1 and 83/0.4 gives periods of 829 and 207 ticks per tile.
        const unsigned period=row==0?829:row<=6?207:83;
        const unsigned remaining=tick%period;
        const int shift=int(row==0?remaining/10:row<=6?remaining*2/5:remaining);
        const unsigned first=(tick/period)%10;
        for(unsigned i=0;i<10;++i) {
            const auto& tile=rows_[row][(first+i)%10];
            if(tile.flags&0x100) continue; // 117e3c suppresses this source cell.
            const int left=int(i)*83-shift;
            const int start=std::max(left,0),end=std::min(left+83,width);
            if(start>=end) continue;
            // 135438 rotates the source descriptor but reads quad dimensions
            // from the unrotated column. Two pieces of row 3 are 82 pixels
            // high; they stretch slightly when crossing an 80-pixel column.
            const auto projectedHeight=rows_[row][i].h;
            for(int y=int(tile.y);y<std::min(height,int(tile.y+projectedHeight));++y) {
                const auto v=tile.v+((2*(y-tile.y)+1)*tile.h)/(2*projectedHeight);
                const auto* source=background_.data()+v*1024+tile.u+start-left;
                auto* dst=target.data()+(y*width+start)*4;
                for(int x=start;x<end;++x,dst+=4) blend(dst,*source++);
            }
        }
    }
}

void VersusResultArt::drawPortrait(const Pose& pose,std::span<uint8_t> target,int height) const {
    for(unsigned n=0;n<pose.count;++n) {
        const auto& q=pose.slices[n];
        const auto [left,right]=std::minmax(q[0].x,q[3].x);
        const auto [top,bottom]=std::minmax(q[0].y,q[3].y);
        if(left==right || top==bottom)continue;
        // Rotation is already encoded in the geometry and UVs of slice 1.
        // Identify each edge by its coordinates to preserve either ordering.
        const auto& xVertex=q[q[1].x!=q[0].x?1:2];
        const auto& yVertex=q[q[1].y!=q[0].y?1:2];
        for(int y=std::max(0,int(std::ceil(top-.5)));y<std::min(height,int(std::ceil(bottom-.5)));++y) {
            const double fy=(y+.5-q[0].y)/(double(yVertex.y)-q[0].y);
            for(int x=std::max(0,int(std::ceil(left-.5)));x<std::min(width,int(std::ceil(right-.5)));++x) {
                const double fx=(x+.5-q[0].x)/(double(xVertex.x)-q[0].x);
                const int u=int(q[0].u+(xVertex.u-q[0].u)*fx+(yVertex.u-q[0].u)*fy);
                const int v=int(q[0].v+(xVertex.v-q[0].v)*fx+(yVertex.v-q[0].v)*fy);
                blend(target.data()+(y*width+x)*4,portrait_[std::clamp(v,0,511)*512+std::clamp(u,0,511)]);
            }
        }
    }
}

void VersusResultArt::paintMenuBackground(unsigned tick,std::span<uint8_t> target,bool clearFirst) const {
    if(target.size()!=640*480*4)throw std::invalid_argument("Expected a 640x480 menu framebuffer");
    if(clearFirst)clear(target,0);
    drawBackground(tick,target,480);
}

void VersusResultArt::paint(unsigned winner,unsigned tick,unsigned backgroundTick,std::span<uint8_t> target) const {
    if(winner>1 || (target.size()!=640*448*4 && target.size()!=640*480*4))
        throw std::invalid_argument("VS result art requires a winner and a 640x448 or 640x480 RGBA framebuffer");
    const int height=int(target.size()/(4*width));
    // 136930's opaque white quad is in front of every non-text layer.
    if(tick>=60&&tick<64) {clear(target,255);return;}
    clear(target,0);
    if(tick>=60) drawBackground(backgroundTick,target,height);
    drawPortrait(poses_[winner][std::min(tick,60u)],target,height);
    if(tick>=60) clear(target.subspan(364*width*4,(std::min(height,464)-364)*width*4),0);
}
}
