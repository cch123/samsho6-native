#include "pause_art.hpp"
#include "scalar_float.hpp"

#include <algorithm>
#include <bit>
#include <cmath>
#include <cstring>
#include <fstream>
#include <numeric>
#include <stdexcept>

namespace ss6 {
namespace {
constexpr int width=640,height=480;
int trunc(float value) {return int(value);}   // cvt.w.s
float real(int value) {return float(value);}  // cvt.s.w
// The marker of the four-colour strip (see pause_art.hpp).
bool strip(const MenuDrawRecord& r) {return r.kind==MenuPrimitive::Flat&&r.glyph==1;}
int floorDivide(int a,int b) {const int q=a/b;return (a%b!=0&&((a<0)!=(b<0)))?q-1:q;}
}

PauseArtTables::PauseArtTables(const std::filesystem::path& assets) {
    const auto file=assets/"pause_art.bin";
    std::ifstream in(file,std::ios::binary);
    char head[8];
    if(!in.read(head,8)||std::memcmp(head,"PAR1",4))throw std::runtime_error("Invalid pause art resource: "+file.string());
    uint32_t count;std::memcpy(&count,head+4,4);
    if(count!=ConstantCount)throw std::runtime_error("Unexpected pause_art.bin constant count");
    if(!in.read(reinterpret_cast<char*>(value.data()),std::streamsize(sizeof(float)*ConstantCount))||in.peek()!=EOF)
        throw std::runtime_error("Invalid pause_art.bin length");
}

PauseArt::PauseArt(const MenuCanvas& canvas,GalleryArt& library,const std::filesystem::path& assets)
    :canvas_(canvas),library_(library),tables_(assets) {}

float PauseArt::cursor(MenuDrawList& list,PauseArtTables::Constant layer) const {
    const float z=eeSub(eeSub(list.cursorBase,tables_[layer]),list.cursor);
    list.cursor=eeAdd(list.cursor,tables_[PauseArtTables::CursorStep]);
    return z;
}

void PauseArt::edge(MenuDrawList& list,int x,int y,int w,int h,uint32_t first,uint32_t second,PauseEdgePulse& pulse,
                    int period) const {
    const uint32_t alpha=((first>>24)+(second>>24))>>1;
    pulse.counter+=pulse.reverse?-1:1;
    // Each channel runs from `first` (counter 0) to `second` (counter =
    // period): a -/+ (|a - b| / period) * counter, truncated.
    const auto channel=[&](unsigned shift) {
        const int a=int(first>>shift&255),b=int(second>>shift&255);
        const auto step=ScalarFloat::integer(a>=b?a-b:b-a).div(ScalarFloat::integer(period)).mul(ScalarFloat::integer(pulse.counter));
        const auto from=ScalarFloat::integer(a);
        return uint32_t((a>=b?from.sub(step):from.add(step)).truncate())&255u;
    };
    const uint32_t r=channel(16),g=channel(8),b=channel(0);
    if(!pulse.reverse) {
        if(pulse.counter>=period) {pulse.reverse=1;pulse.counter=period;}
    } else if(pulse.counter<=0) {pulse.reverse=0;pulse.counter=0;}
    canvas_.rectangle(list,x,y,w,h,alpha<<24|r<<16|g<<8|b,tables_[PauseArtTables::EdgeZ]);
}

void PauseArt::drawPauseMenu(MenuDrawList& list,const PauseMenuAssets& assets,const PauseMenuDraw& draw,const MenuChrome& chrome,
                             bool neoGeoLand,PauseEdgePulse& pulse) const {
    using T=PauseArtTables;
    if(draw.menu) {
        // 1daca8: box and the four pulsing edges in the owner's colour.
        const int h=draw.frameHeight;
        const uint32_t first=draw.owner?0xc0ff0000u:0xc00000ffu,second=draw.owner?0xc0400000u:0xc0000040u;
        canvas_.rectangle(list,0xb4,0x78,0x118,h,0xc0000000,tables_[T::BoxZ]);
        edge(list,0xb0,0x74,0x120,4,first,second,pulse,0x78);
        edge(list,0xb0,h+0x78,0x120,4,first,second,pulse,0x78);
        edge(list,0xb0,0x78,4,h,first,second,pulse,0x78);
        edge(list,0x1cc,0x78,4,h,first,second,pulse,0x78);
        // 1da918: title plate 5 of the banner sheet; the blend word stays 1.
        {
            const auto& r=canvas_.banners()[5];
            const uint32_t saved=list.colour;
            list.blend=1;list.colour=0xffffffff;
            canvas_.sprite(list,0x2e,tables_[T::TitleX],tables_[T::TitleY],tables_[T::TitleZ],real(r.w),real(r.h),
                           real(r.u),real(r.v),real(r.w),real(r.h));
            list.colour=saved;
        }
        // 1da9c0: rows in the 15-dot ASCII font; the cursor row is red.
        list.asciiDepth=tables_[T::RowsZ];                       // 113828
        for(int i=0;i<draw.rows;++i) {
            const auto& text=neoGeoLand?assets.items5.at(size_t(i)):assets.items.at(size_t(i));
            canvas_.ascii(list,text,0xcc,0xb4+0x18*i,i==draw.cursor?0xffff0000u:0xffffffffu);
        }
        list.asciiDepth=-200.0f;                                 // 113838
        // 1dab38: the text depth is taken before the bar is submitted. The
        // marquee position was stepped by the logic (1ceb10).
        {
            const int saved=list.textDepth;
            list.textDepth=trunc(canvas_.depth(list,tables_[T::HelpTextZ]));
            canvas_.rectangle(list,0,0x174,0x280,0x24,0xc0000000,tables_[T::HelpBarZ]);
            const auto& help=neoGeoLand?assets.help5.at(size_t(draw.cursor)):assets.help.at(size_t(draw.cursor));
            if(draw.helpX<0x280)canvas_.text20(list,help,draw.helpX,0x17a,255,255,255,255);
            list.textDepth=saved;
        }
        // 1dae00.
        canvas_.rectangle(list,0x14c,0x19a,0x134,0x1c,0xc0000000,tables_[T::LegendBoxZ]);
        canvas_.legend(list,chrome,0,0x19d);
    }
    if(draw.dialog)canvas_.dialog(list,draw.choice,draw.dialog==2?1:0,neoGeoLand);
}

void PauseArt::brackets(MenuDrawList& list,float x,float y,float w,float h,uint32_t outer,uint32_t inner) const {
    const float arm=tables_[PauseArtTables::BracketArm];
    const auto rect=[&](uint32_t colour,int px,int py,int pw,int ph) {
        const float z=cursor(list,PauseArtTables::BracketZ);
        canvas_.rectangle(list,px,py,pw,ph,colour,z);
    };
    int px=trunc(x),py=trunc(y);
    rect(outer,px,py,12,6);rect(outer,px,py,6,12);rect(inner,px+2,py+2,8,2);rect(inner,px+2,py+2,2,8);
    py=trunc(y);px=trunc(eeSub(eeAdd(x,w),arm));
    rect(outer,px,py,12,6);rect(outer,px+6,py,6,12);rect(inner,px+2,py+2,8,2);rect(inner,px+8,py+2,2,8);
    px=trunc(x);py=trunc(eeSub(eeAdd(y,h),arm));
    rect(outer,px,py+6,12,6);rect(outer,px,py,6,12);rect(inner,px+2,py+8,8,2);rect(inner,px+2,py+2,2,8);
    px=trunc(eeSub(eeAdd(x,w),arm));py=trunc(eeSub(eeAdd(y,h),arm));
    rect(outer,px,py+6,12,6);rect(outer,px+6,py,6,12);rect(inner,px+2,py+8,8,2);rect(inner,px+8,py+2,2,8);
}

void PauseArt::apply(const PauseWindowContext& context) const {
    library_.gameMode=int(context.gameMode);library_.seat=context.seat;library_.extraIcons=context.unlocks.matsuri;
}

void PauseArt::drawKeyWidget(MenuDrawList& list,const KeyConfigAssets& assets,const KeyConfigDraw& draw) const {
    using T=PauseArtTables;
    if(!draw.visible)return;
    // The box keeps the colours of 17c260 apart from the fill: black
    // border, white line; it is not tinted by the operating seat.
    GalleryArt::Frame f;
    f.style=1;f.x=real(draw.boxX);f.y=real(draw.boxY);f.w=tables_[T::KeyBoxW];f.h=tables_[T::KeyBoxH];f.fill=0xc0000000;
    library_.frame(list,f,0);
    library_.textColour=0xffffffff;
    library_.markup(list,assets.legend,1,false,real(draw.legendX),real(draw.legendY));
    for(size_t row=0;row<draw.labelY.size();++row) {
        library_.textColour=draw.labelColour[row];
        library_.label(list,assets.rows[row],draw.labelX,draw.labelY[row],0);
    }
    for(const auto& column:draw.cells)for(const auto& cell:column) {
        if(cell.glyph<0) {
            library_.textColour=0xffffffff;
            library_.label(list,assets.unset,cell.x,cell.y,0);
        } else {
            // The button icons lie on the frame layer (800), not on the text layer.
            const float z=cursor(list,T::KeyIconZ);
            library_.icon(list,cell.glyph,real(cell.x),real(cell.y),z);
        }
        if(cell.cursor)
            brackets(list,real(cell.cursorX),real(cell.cursorY),tables_[T::KeyCursorW],tables_[T::KeyCursorH],cell.cursorColour,
                     0xffffffff);
    }
}

bool PauseArt::drawKeyConfig(MenuDrawList& list,const KeyConfigAssets& assets,const KeyConfigWindow& window,
                             const SystemData& system,const PauseWindowContext& context,MenuBackdrop& backdrop,
                             GameRandom& random,const MenuChrome& chrome) const {
    apply(context);
    list.resetCursor();                                          // 17c210
    library_.drawGuide(list,window.guide,backdrop,random,chrome);
    drawKeyWidget(list,assets,window.widget.draw(system));
    return window.guide.backdrop!=-1&&!GuideWindow::menuBackdrop(context.gameMode);
}

void PauseArt::headingBar(MenuDrawList& list,const SkillListData& data,int type,int w,int h,float x,float y,float z) const {
    if(type==0xff||type==6)return;
    const auto& table=data.barColour.at(size_t(type));
    // 114c10 halves the alpha; 105790 scales RGB by BRIGHT and stores the
    // AARRGGBB argument in AABBGGRR order. No 117288: the scene fade does
    // not reach this strip, and 114e98 is not consulted either.
    const auto queue=[&](uint32_t alpha,const uint8_t* rgb) {
        std::array<uint32_t,4> out{};
        for(unsigned c=0;c<3;++c)out[c]=(uint32_t(rgb[c])*uint32_t(brightness_))>>8&255u;
        out[3]=(alpha+1)>>1;
        return out;
    };
    const auto left=queue(0xc0,table.data()),right=queue(0x40,table.data()+3);
    MenuDrawRecord r;
    r.kind=MenuPrimitive::Flat;r.glyph=1;
    r.z=real(trunc(canvas_.depth(list,z)));
    r.colour=left[3]<<24|left[2]<<16|left[1]<<8|left[0];
    const int x0=trunc(x),y0=trunc(y),x1=trunc(eeAdd(x,real(w))),y1=trunc(eeAdd(y,real(h)));
    r.x=real(x0);r.y=real(y0);r.w=real(x1-x0);r.h=real(y1-y0);
    for(unsigned c=0;c<4;++c)r.corner[c]=real(int(right[c]));
    list.records.push_back(r);
}

void PauseArt::skillPage(MenuDrawList& list,const SkillListData& data,int table,int first,int id,int x,int y,int scroll,
                         int lines,int gap,const SkillUnlocks& unlocks) const {
    using T=PauseArtTables;
    if(first<0)return;
    const auto& records=data.tables.at(size_t(table));
    const auto word=[](const uint8_t* rgb) {return 0xff000000u|uint32_t(rgb[0])<<16|uint32_t(rgb[1])<<8|rgb[2];};
    for(size_t r=size_t(first);r<records.size()&&(records[r].id==id||records[r].id==-1);++r) {
        const auto& rec=records[r];
        if(scroll<=0&&rec.type!=0xff&&rec.type!=6) {
            // 13d548: the strip, then the heading icons, each on its own cursor step.
            {
                const float z=cursor(list,T::SkillBarZ);
                headingBar(list,data,rec.type,0x220,(rec.flags&8?4:0)+0x11,tables_[T::SkillBarX],real(y+8),z);
            }
            const auto icon=[&](int which,int px,int py) {
                const float z=cursor(list,T::SkillIconZ);
                library_.icon(list,which,real(px),real(py),z);
            };
            int left=0;
            if(rec.flags&2) {left=-0x16;icon(0xf,x-0x16,y+3);}
            if(rec.flags&1) {left-=0x16;icon(0xe,x+left,y+3);}
            if(rec.flags&4)icon(0x2d,x+0x208,y+2);
            int px=x+0x1fe;
            for(int bit=8;bit>=0;--bit) {
                if(!(rec.spirits>>bit&1))continue;
                if(bit==6?!unlocks.ma:bit==7?!unlocks.kemono:bit==8?!unlocks.matsuri:false)continue;
                px-=0x18;
                icon(0x10+bit,px,y);
            }
        }
        for(unsigned column=0;column<3;++column) {
            // A type-6 record shows its middle column only.
            const std::string_view text=rec.type==6&&column!=1?std::string_view():data.text(rec,column);
            if(text.empty())continue;
            for(size_t at=0;;) {
                size_t next;
                if(scroll>0) {next=skillNextLine(text,at);--scroll;}
                else {
                    --lines;
                    const std::string_view line=text.substr(at);
                    const auto run=[&](uint32_t colour,int mode,bool plain,int px,int py) {
                        library_.textColour=colour;                       // 17db28
                        const size_t end=library_.markup(list,line,mode,plain,real(px),real(py));
                        return end==GalleryArt::noBreak?std::string_view::npos:at+end;
                    };
                    if(column==0) {
                        // Name: two offset passes with icons, then the
                        // coloured pass, which skips every ASCII unit.
                        const uint32_t shadow=word(data.shadowColour[rec.type==1?0:1].data());
                        run(shadow,2,false,x+1,y+1);
                        run(shadow,2,false,x+3,y+2);
                        next=run(word(data.nameColour.at(rec.type).data()),2,true,x,y);
                    } else next=run(0xffffffffu,1,false,x,y);
                    y+=0x1b;
                }
                if(lines<=0)return;
                if(next==std::string_view::npos)break;
                at=next;
            }
        }
        if(scroll<=0) {y+=gap;if(rec.flags&8)y-=0xe;}
    }
}

bool PauseArt::drawSkillList(MenuDrawList& list,const SkillListWindow& window,const PauseWindowContext& context,
                             MenuBackdrop& backdrop,GameRandom& random,const MenuChrome& chrome) const {
    using T=PauseArtTables;
    apply(context);
    list.resetCursor();                                          // 17c210
    if(window.dim>0) {
        // Submitted before the guide, hence behind every bar and list.
        const float z=cursor(list,T::SkillDimZ);
        canvas_.rectangle(list,0,0,0x280,0x1c0,uint32_t(window.dim)<<24,z);
    }
    library_.drawGuide(list,window.guide,backdrop,random,chrome);
    library_.drawList(list,window.list);
    library_.drawList(list,window.sub);
    const auto& d=window.detail;
    if(d.drawn()) {
        skillPage(list,*d.data,d.table,d.first,d.selection,SkillDetail::pageX,SkillDetail::pageY,d.top,SkillDetail::pageLines,
                  SkillDetail::recordGap,context.unlocks);
        if(d.scrollBar()) {
            // 17c260 colours: the bar is not tinted by the operating seat.
            GalleryArt::Frame f;
            f.x=real(d.panel.x+0x268);f.y=real(d.panel.y+0x28);f.w=tables_[T::SkillScrollW];f.h=tables_[T::SkillScrollH];
            library_.scrollBar(list,f,d.scrollTotal(),d.visible,d.top,0xc);
        }
    }
    return window.guide.backdrop!=-1&&!GuideWindow::menuBackdrop(context.gameMode);
}

void PauseArt::rasterise(const MenuDrawList& list,std::span<uint8_t> rgba) const {
    if(rgba.size()!=size_t(width)*height*4)throw std::invalid_argument("Expected a 640x480 menu surface");
    std::vector<unsigned> order(list.records.size());
    std::iota(order.begin(),order.end(),0u);
    std::stable_sort(order.begin(),order.end(),[&](unsigned a,unsigned b) {return list.records[a].z<list.records[b].z;});
    // Runs between two strips are already in depth order, which the stable
    // sort of the library rasteriser keeps.
    MenuDrawList run;
    const auto flush=[&] {
        if(run.records.empty())return;
        library_.rasterise(run,rgba);
        run.records.clear();
    };
    for(const unsigned at:order) {
        const auto& q=list.records[at];
        if(!strip(q)) {run.records.push_back(q);continue;}
        flush();
        const int x=int(q.x),y=int(q.y),w=int(q.w),h=int(q.h);
        if(w<=0||h<=0)continue;
        int from[4],to[4];
        for(int c=0;c<4;++c) {from[c]=int(q.colour>>(8*c)&255);to[c]=int(q.corner[size_t(c)]);}
        for(int px=std::max(0,x);px<std::min(width,x+w);++px) {
            // Colour at the pixel centre of the horizontal ramp.
            int value[4];
            for(int c=0;c<4;++c)value[c]=from[c]+floorDivide((2*(px-x)+1)*(to[c]-from[c]),2*w);
            for(int py=std::max(0,y);py<std::min(height,y+h);++py) {
                auto* dst=rgba.data()+4*(py*width+px);
                for(int c=0;c<3;++c)dst[c]=uint8_t(std::clamp(dst[c]+(((value[c]-dst[c])*value[3])>>7),0,255));
            }
        }
    }
    flush();
}
}
