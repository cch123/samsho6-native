#include "character_select_art.hpp"
#include <algorithm>
#include <bit>
#include <fstream>
#include <stdexcept>
#include <string>

namespace ss6 {
namespace {
unsigned read(std::istream& input,unsigned bytes) {
    unsigned value=0;
    for(unsigned i=0;i<bytes;++i) {
        int next=input.get();
        if(next<0)throw std::runtime_error("Truncated character select art");
        value|=unsigned(next)<<(8*i);
    }
    return value;
}
constexpr std::array<int,12> lastCount{0,59,69,9,9,14,9,5,14,14,0,14};
}

CharacterSelectArt::CharacterSelectArt(const std::filesystem::path& assets):assets_(assets),menu_(assets) {
    std::ifstream in(assets/"character_select_art.bin",std::ios::binary);
    if(read(in,4)!=0x31305343)throw std::runtime_error("Invalid character selection layout");
    const unsigned count=read(in,4),lists=read(in,4),frames=read(in,4);
    for(auto& xy:faces_)for(auto& v:xy)v=int(read(in,2));
    for(auto& xy:names_)for(auto& v:xy)v=int(read(in,2));
    loadPages(in,count,lists,frames,0);
    for(auto& value:headers_)value=read(in,4);
    if(in.peek()!=EOF)throw std::runtime_error("Trailing character selection data");
    std::ifstream spirits(assets/"spirit_select_art.bin",std::ios::binary);
    if(read(spirits,4)!=0x31305353)throw std::runtime_error("Invalid spirit selection layout");
    const auto spiritQuads=read(spirits,4),spiritLists=read(spirits,4),spiritPages=read(spirits,4);
    loadPages(spirits,spiritQuads,spiritLists,spiritPages,2);
    // Stage names use GOTH_24. Their atlas has eleven original 24px rows.
    Atlas labels{512,std::vector<uint8_t>(512*24*11),{}};
    for(unsigned i=0;i<16;++i)labels.palette[i]=read(spirits,4);
    if(!spirits.read(reinterpret_cast<char*>(labels.indices.data()),labels.indices.size())||spirits.peek()!=EOF)
        throw std::runtime_error("Invalid stage names");
    fixed_.emplace(63,std::move(labels));
    fixed_.emplace(46,loadAtlas("ps2_common_icon",512,false));
    fixed_.emplace(6,loadAtlas("ps2_gage_1_2_3_all",1024,false));
    fixed_.emplace(2,loadAtlas("obj1_16",512,true));
    fixed_.emplace(5,loadAtlas("char_face_1024",1024,false));
    fixed_.emplace(12,loadAtlas("vs_obj",512,true));
}

void CharacterSelectArt::loadPages(std::istream& in,unsigned count,unsigned lists,unsigned frames,unsigned family) {
    if(count>100000||lists>20000||frames>12000)throw std::runtime_error("Invalid selection layout counts");
    const unsigned firstQuad=unsigned(quads_.size());
    auto shortValue=[&](){return int(std::bit_cast<int16_t>(uint16_t(read(in,2))));};
    for(unsigned i=0;i<count;++i) {
        Quad q;
        q.depth=int(read(in,4));q.x=shortValue();q.y=shortValue();q.right=shortValue();q.bottom=shortValue();
        q.u=shortValue();q.v=shortValue();q.endU=shortValue();q.endV=shortValue();
        q.slot=read(in,1);q.substitution=read(in,1);q.cell=read(in,1);q.blend=read(in,1);q.color=read(in,4);
        if(q.cell>=CharacterSelect::cells||q.substitution>3||q.blend!=1)throw std::runtime_error("Unsupported character select draw");
        quads_.push_back(q);
    }
    const unsigned firstList=unsigned(lists_.size());
    for(unsigned j=0;j<lists;++j) {
        auto& group=lists_.emplace_back();
        const unsigned size=read(in,2);
        for(unsigned i=0;i<size;++i) {
            unsigned index=read(in,4);
            if(index>=count)throw std::runtime_error("Invalid character select quad index");
            group.push_back(firstQuad+index);
        }
    }
    for(unsigned i=0;i<frames;++i) {
        std::array<unsigned,4> key;
        for(auto& value:key)value=read(in,1);
        const unsigned list=read(in,4);
        if(list>=lists)throw std::runtime_error("Invalid selection list index");
        key[0]+=family;pages_.emplace(key,firstList+list);
    }
}

CharacterSelectArt::Atlas CharacterSelectArt::loadAtlas(const std::string& name,int width,bool embedded) const {
    const int count=width*width;
    Atlas out{width,std::vector<uint8_t>(count),{}};
    std::ifstream tex(assets_/(name+".tex"),std::ios::binary);
    if(!tex.read(reinterpret_cast<char*>(out.indices.data()),count))
        throw std::runtime_error("Missing selection texture "+name);
    std::ifstream pal;
    if(!embedded)pal.open(assets_/(name+".pal"),std::ios::binary);
    auto& input=embedded?tex:pal;
    for(unsigned i=0;i<256;++i) {
        // Embedded CLUTs use a single 16x16 upload. Separate 32-bit palettes
        // pass through 116478 and retain their linear indices and 7-bit alpha.
        const unsigned index=embedded?(i&~24u)|((i&8u)<<1)|((i&16u)>>1):i;
        const auto color=read(input,4);
        out.palette[index]=(color>>24)?color:0;
    }
    return out;
}

const CharacterSelectArt::Atlas& CharacterSelectArt::portrait(int id) const {
    auto found=portraits_.find(id);
    if(found!=portraits_.end())return found->second;
    if(id<0||id>48)throw std::runtime_error("Invalid confirmed character portrait");
    return portraits_.emplace(id,loadAtlas("bup_"+(id<10?std::string("0"):"")+std::to_string(id),512,false)).first->second;
}

void CharacterSelectArt::raster(const Draw& draw,std::span<uint8_t> rgba) {
    const auto& q=draw.quad;
    const int left=std::max(0,std::min(q.x,q.right)),right=std::min(640,std::max(q.x,q.right));
    const int top=std::max(0,std::min(q.y,q.bottom)),bottom=std::min(480,std::max(q.y,q.bottom));
    if(left>=right||top>=bottom)return;
    const int modulation=(int(q.color>>24)+1)/2;
    for(int y=top;y<bottom;++y) {
        auto* dest=rgba.data()+4*(y*640+left);
        const double v=q.v+(y+.5-q.y)*(q.endV-q.v)/(q.bottom-q.y);
        for(int x=left;x<right;++x,dest+=4) {
            uint32_t source=0x80000000|(q.color&0xffffff);
            if(draw.atlas) {
                const auto& at=*draw.atlas;
                const double u=q.u+(x+.5-q.x)*(q.endU-q.u)/(q.right-q.x);
                const int s=std::clamp(int(u),0,at.width-1),t=std::clamp(int(v),0,at.width-1);
                source=at.palette[at.indices[t*at.width+s]];
                if((q.color&0xffffff)!=0xffffff) {
                    uint32_t modulated=source&0xff000000;
                    for(unsigned shift=0;shift<24;shift+=8) {
                        const unsigned scale=(unsigned(uint8_t(q.color>>shift))+1)/2;
                        modulated|=(unsigned(uint8_t(source>>shift))*scale/128)<<shift;
                    }
                    source=modulated;
                }
            }
            const int alpha=(int(source>>24)*modulation)>>7;
            for(int c=0;c<3;++c)dest[c]+=((int(uint8_t(source>>(c*8)))-dest[c])*alpha)>>7;
        }
    }
}

void CharacterSelectArt::spiritSeat(const CharacterSelect& state,unsigned side,std::vector<Draw>& draws) const {
    const auto& seat=state.spirits[side];
    const unsigned phase=unsigned(seat.drawPhase);
    if(!phase)return;
    const unsigned tick=unsigned(std::max(0,seat.drawCount));
    const unsigned cursor=unsigned(seat.drawCursor);
    const auto pulse=tick<70?tick:20+(tick-20)%50;
    const auto submit=[&](unsigned family,unsigned selection,unsigned ph,unsigned t) {
        const auto group=pages_.at({family+2,selection,ph,t});
        for(auto index:lists_[group]) {
            auto q=quads_[index];
            const Atlas* tex=q.slot?&fixed_.at(q.slot==5?6:q.slot):nullptr;
            q.depth+=int(draws.size());
            draws.push_back({q,tex});
        }
    };
    // The two factory seats share the stage carousel. The seat that owns the
    // stage choice draws it once, in front of the two locked-in spirit panels.
    // 12f8e8 gives 44..47 a seventh entry (spirit 8); the panel layout differs for every cursor,
    // so those seats use their own page family (extracted groups 5/6).
    const unsigned family=side+(seat.choiceCount==7?5u:0u);
    if(phase<=5) {
        constexpr unsigned limits[]{0,10,69,9,9,5};
        submit(family,cursor,phase,phase==2?pulse:std::min(tick,limits[phase]));
        return;
    }
    submit(family,cursor,14,0);
    if(phase==13||phase==17)
        submit(2+side,unsigned(state.stageOption),phase,phase==13?pulse:std::min(tick,5u));
    else if(phase==20||phase==22||phase==23||phase==24||phase==25) {
        const unsigned last=phase==20?30u:phase==24?5u:phase==25?0u:29u;
        submit(4,unsigned(state.stageCursor),phase,std::min(tick,last));
    }
}

void CharacterSelectArt::paint(const CharacterSelect& state,std::span<uint8_t> rgba) const {
    const bool spirits=state.spiritDirectorVisible;
    if(spirits)menu_.paintMenuBackground(unsigned(state.spiritDrawFrame),rgba);
    if(!spirits||state.characterDirectorVisible)
        menu_.paintMenuBackground(unsigned(std::max(0,state.drawFrame)),rgba,!spirits);
    std::vector<Draw> draws;draws.reserve(210);
    if(spirits) {
        // 112838 dispatches spirit P2/P1 before the director. The original
        // timer uses the same three texture rectangles at its own depth.
        spiritSeat(state,1,draws);spiritSeat(state,0,draws);
        for(auto index:lists_.at(headers_.at(std::clamp(state.drawRemaining/60,0,30)))) {
            auto q=quads_[index];q.depth+=10900+int(draws.size());draws.push_back({q,&fixed_.at(q.slot)});
        }
    }
    for(unsigned side=0;side<2;++side) {
        const auto& seat=state.seats[side];
        const unsigned phase=unsigned(seat.drawPhase);
        if(!phase)continue;
        if(phase>=lastCount.size()||seat.cell<0||seat.cell>=CharacterSelect::cells)throw std::runtime_error("Invalid selection animation state");
        int tick=std::max(0,seat.drawCount);
        // In phase 2 the third ring starts on tick 20. Subsequent frames use
        // the 50-update rings from 12bfa0 indefinitely while awaiting input.
        if(phase==2&&tick>69)tick=20+(tick-20)%50;
        tick=std::min(tick,lastCount[phase]);
        const auto page=pages_.at({side,unsigned(seat.cell%6),phase,unsigned(tick)});
        for(auto index:lists_.at(page)) {
            auto q=quads_[index];const Atlas* atlas=nullptr;
            if(q.substitution==1) {
                const unsigned cell=(q.cell+6*(seat.cell/6))%CharacterSelect::cells;
                // Faces draw 5e0530[cells[face]]; Kuroko's face 0x31 reads the word after
                // the 48 cells, 0x30, so a Kuroko cell shows character 48's tile.
                const auto& off=faces_.at(state.kurokoCell(side,int(cell))?48:state.roster[cell]);
                q.u+=off[0];q.endU+=off[0];q.v+=off[1];q.endV+=off[1];
            } else if(q.substitution==2||q.substitution==3) {
                const int id=state.kurokoCell(side,seat.cell)?48:state.roster[seat.cell];
                if(id==53||seat.controls)continue;
                if(q.substitution==3) {
                    const auto& off=names_.at(id);
                    q.u+=off[0];q.endU+=off[0];q.v+=off[1];q.endV+=off[1];
                }
            }
            if(q.slot==7||q.slot==8)atlas=&portrait(seat.selected>=0?seat.selected:seat.character);
            else if(q.slot)atlas=&fixed_.at(q.slot);
            q.depth+=int(draws.size());
            draws.push_back({q,atlas});
        }
    }
    if(!spirits||state.characterDirectorVisible)for(auto index:lists_.at(headers_.at(std::clamp(state.drawRemaining/60,0,30)))) {
        auto q=quads_[index];q.depth+=int(draws.size());draws.push_back({q,&fixed_.at(q.slot)});
    }
    std::stable_sort(draws.begin(),draws.end(),[](const Draw& a,const Draw& b){return a.quad.depth<b.quad.depth;});
    for(const auto& draw:draws)raster(draw,rgba);
}
}
