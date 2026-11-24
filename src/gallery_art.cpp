#include "asset_files.hpp"
#include "gallery_art.hpp"
#include "scalar_float.hpp"

#include <algorithm>
#include <bit>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <numeric>
#include <stdexcept>

namespace ss6 {
namespace {
constexpr int width=640,height=480;
std::vector<uint8_t> load(const std::filesystem::path& file,size_t size=0) {
    std::ifstream in(resolveAsset(file),std::ios::binary|std::ios::ate);
    if(!in||(size&&in.tellg()!=static_cast<std::streamoff>(size)))
        throw std::runtime_error("Invalid gallery resource: "+file.string());
    std::vector<uint8_t> bytes(static_cast<size_t>(in.tellg()));
    in.seekg(0);
    if(!in.read(reinterpret_cast<char*>(bytes.data()),std::streamsize(bytes.size())))
        throw std::runtime_error("Truncated gallery resource: "+file.string());
    return bytes;
}
struct Reader {
    const std::vector<uint8_t>& data;size_t at=0;
    const uint8_t* take(size_t n) {
        if(n>data.size()-at)throw std::runtime_error("Truncated gallery_art.bin");
        at+=n;return data.data()+at-n;
    }
    uint32_t word() {const auto* p=take(4);return p[0]|p[1]<<8|p[2]<<16|uint32_t(p[3])<<24;}
    std::string text() {const auto* p=take(2);const size_t n=p[0]|p[1]<<8;return {reinterpret_cast<const char*>(take(n)),n};}
};
int trunc(float value) {return int(value);}   // cvt.w.s
float real(int value) {return float(value);}  // cvt.s.w
struct Channels { int r,g,b,a; };
Channels channels(uint32_t argb) {return {int(argb>>16&255),int(argb>>8&255),int(argb&255),int(argb>>24)};}
}

GalleryArt::GalleryArt(const MenuCanvas& canvas,const std::filesystem::path& assets):canvas_(canvas),assets_(assets) {
    const auto blob=load(assets/"gallery_art.bin");
    Reader in{blob};
    if(std::memcmp(in.take(4),"GAR1",4)||in.word()!=ConstantCount)throw std::runtime_error("Invalid gallery_art.bin header");
    for(auto& value:floats_)value=std::bit_cast<float>(in.word());
    const unsigned count=in.word();
    if(count<0x33||count>256)throw std::runtime_error("Invalid gallery_art.bin icon table");
    for(unsigned i=0;i<count;++i) {
        MenuSheetRect r;
        r.u=int(in.word());r.v=int(in.word());r.w=int(in.word());r.h=int(in.word());
        icons_.push_back(r);
    }
    std::copy_n(in.take(6),6,edge_.begin());
    space_=in.text();exit_=in.text();
    if(in.at!=blob.size())throw std::runtime_error("Invalid gallery_art.bin length");
}

float GalleryArt::cursor(MenuDrawList& list,Constant layer) const {
    const float z=eeSub(eeSub(list.cursorBase,floats_[layer]),list.cursor);
    list.cursor=eeAdd(list.cursor,floats_[CursorStep]);
    return z;
}
GalleryArt::Constant GalleryArt::textLayer(Constant front) const {
    // The label and the markup routine keep separate copies of 1000/520/900.
    return Constant(unsigned(front)+(frontText?0u:middleText?1u:2u));
}

void GalleryArt::softBar(MenuDrawList& list,float x,float y,float z,float w,float h) const {
    for(int i=0;i<6;++i) {
        const float d=real(3-i),grow=real(2*(3-i));
        const int top=trunc(eeSub(y,d)),tall=trunc(eeAdd(h,grow));
        const int left=trunc(eeSub(x,d)),wide=trunc(eeAdd(w,grow));
        const uint32_t colour=uint32_t(edge_[size_t(i)])<<24;
        if(i==5) {canvas_.rectangle(list,left,top,wide+1,tall+1,colour,z);break;}
        canvas_.rectangle(list,left,top,wide,1,colour,z);
        canvas_.rectangle(list,left,top+tall,wide,1,colour,z);
        canvas_.rectangle(list,left,top+1,1,tall-1,colour,z);
        canvas_.rectangle(list,left+wide,top+1,1,tall-1,colour,z);
    }
}

void GalleryArt::border(MenuDrawList& list,uint32_t colour,float x,float y,float w,float h,float t) const {
    const int left=trunc(x),top=trunc(y),thick=trunc(t),tall=trunc(h),wide=trunc(w);
    const float right=eeSub(eeAdd(x,w),t),bottom=eeSub(eeAdd(y,h),t);
    float z=cursor(list,BorderZ);
    canvas_.rectangle(list,left,top,thick,tall,colour,z);
    z=cursor(list,BorderZ);
    canvas_.rectangle(list,left,top,wide,thick,colour,z);
    z=cursor(list,BorderZ);
    canvas_.rectangle(list,trunc(right),top,thick,tall,colour,z);
    z=cursor(list,BorderZ);
    canvas_.rectangle(list,left,trunc(bottom),wide,thick,colour,z);
}

void GalleryArt::tint(Frame& frame,bool focused) const {
    // The border carries the colour of the operating seat: blue for the
    // first, red for the second.
    if(focused) {frame.fill=0xc0101010;frame.line=0xffffffff;frame.border=seat==1?0xff800000:0xff000080;}
    else {frame.fill=0xc0000000;frame.line=0xffa0a0a0;frame.border=seat==1?0xff600000:0xff000060;}
}

void GalleryArt::frame(MenuDrawList& list,const Frame& f,int gutter) const {
    int inset=0;
    if(f.style>=0&&f.style<=2) {
        if(gutter>0) {
            // A strip to the right of the frame, behind the scroll bar.
            const float z=cursor(list,FrameZ);
            canvas_.rectangle(list,trunc(eeAdd(f.x,f.w)),trunc(f.y),gutter,trunc(f.h),f.border,z);
        }
        const auto ring=[&](uint32_t colour,float in,float shrink,float t) {
            border(list,colour,eeAdd(f.x,in),eeAdd(f.y,in),eeSub(f.w,shrink),eeSub(f.h,shrink),t);
        };
        border(list,f.border,eeAdd(f.x,0.0f),eeAdd(f.y,0.0f),f.w,f.h,floats_[Five]);
        if(f.style==0)inset=5;
        else if(f.style==1) {
            ring(f.line,floats_[Five],floats_[Ten],floats_[Two]);
            ring(f.border,floats_[Seven],floats_[Fourteen],floats_[Two]);
            inset=9;
        } else {
            ring(f.line,floats_[Five],floats_[Ten],floats_[Five]);
            ring(f.border,floats_[Ten],floats_[Twenty],floats_[Two]);
            ring(f.line,floats_[Twelve],floats_[TwentyFour],floats_[One]);
            ring(f.border,floats_[Thirteen],floats_[TwentySix],floats_[One]);
            inset=14;
        }
    }
    const float in=real(inset),shrink=real(2*inset);
    const int x=trunc(eeAdd(f.x,in)),y=trunc(eeAdd(f.y,in));
    const float z=cursor(list,FrameZ);
    canvas_.rectangle(list,x,y,trunc(eeSub(f.w,shrink)),trunc(eeSub(f.h,shrink)),f.fill,z);
}

void GalleryArt::scrollBar(MenuDrawList& list,const Frame& f,int count,int visible,int top,int scale) const {
    const float four=floats_[ScrollFour],eight=floats_[ScrollEight],two=floats_[ScrollTwo];
    float z=cursor(list,ScrollZ);
    canvas_.rectangle(list,trunc(eeAdd(f.x,two)),trunc(eeAdd(f.y,two)),trunc(eeSub(f.w,four)),trunc(eeSub(f.h,four)),f.line,z);
    z=cursor(list,ScrollZ);
    canvas_.rectangle(list,trunc(eeAdd(f.x,four)),trunc(eeAdd(f.y,four)),trunc(eeSub(f.w,eight)),trunc(eeSub(f.h,eight)),
                      0xff000000,z);
    if(!count)throw std::invalid_argument("Scroll bar of an empty list");   // break 7 in the original
    const int track=trunc(eeSub(f.h,eight)),wide=trunc(eeSub(f.w,floats_[ScrollTwelve]));
    int thumb=std::max(track*visible*scale/count,2);
    int offset=track-thumb;                       // list end
    if(top+visible<count) {
        const int o=track*top/count;
        if(!(track<o+thumb))offset=o;
    }
    if(scale>=2&&track<offset+thumb)thumb=track-offset;
    const int x=trunc(eeAdd(f.x,floats_[ScrollSix])),y=trunc(eeAdd(eeAdd(f.y,four),real(offset)));
    z=cursor(list,ScrollZ);
    canvas_.rectangle(list,x,y,wide,thumb,f.line,z);
}

void GalleryArt::label(MenuDrawList& list,std::string_view text,int x,int y,int mode) const {
    const Constant layer=textLayer(LabelFront);
    const int saved=list.textDepth;
    list.textDepth=trunc(canvas_.depth(list,eeSub(list.cursorBase,floats_[layer])));
    list.asciiDepth=cursor(list,layer);              // 113828
    const auto c=channels(textColour);
    if(mode==0)canvas_.ascii(list,text,x,y,textColour);
    else if(mode==1)canvas_.text20(list,text,x,y,c.r,c.g,c.b,c.a);
    else canvas_.text24(list,text,x,y,c.r,c.g,c.b,c.a);
    list.asciiDepth=-200.0f;                         // 113838
    list.textDepth=saved;
}

void GalleryArt::smallText(MenuDrawList& list,std::string_view text,int x,int y) const {
    const uint32_t saved=list.colour;
    list.colour=textColour;
    list.additive=false;
    const int start=x;
    for(const char raw:text) {
        const int ch=uint8_t(raw);
        if(!ch)break;
        if(ch==0x0a) {x=start;y+=8;continue;}
        if(ch>=0x20) {
            // 17dc90: thirty cells per row at pitch 17 from (2,2) of slot 1.
            const int cell=ch-0x20;
            const float z=cursor(list,SmallZ);
            canvas_.sprite(list,1,real(x),real(y),z,floats_[SmallW],floats_[SmallH],real(cell%30*17+2),real(cell/30*17+2),
                           floats_[SmallUw],floats_[SmallVh]);
        }
        x+=10;
    }
    list.colour=saved;
}

int GalleryArt::sheet(MenuDrawList& list,int slot,const MenuSheetRect& rect,float x,float y,float z) const {
    list.additive=false;
    list.colour=0xffffffff;
    canvas_.sprite(list,slot,x,y,z,real(rect.w),real(rect.h),real(rect.u),real(rect.v),real(rect.w),real(rect.h));
    return rect.w;
}
int GalleryArt::icon(MenuDrawList& list,int index,float x,float y,float z) const {
    if(index==-1||index==0x5d)return 0;
    if(index==0x2d&&!extraIcons)return 0;
    return sheet(list,index<0x33?0x2e:5,icons_.at(size_t(index)),x,y,z);
}

size_t GalleryArt::markup(MenuDrawList& list,std::string_view text,int mode,bool plain,float x,float y) const {
    const int saved=list.textDepth;
    list.textDepth=trunc(canvas_.depth(list,eeSub(list.cursorBase,floats_[textLayer(MarkupFront)])));
    const int advance=mode==1?0x14:0x18,style=mode==1?1:2;
    const auto c=channels(textColour);
    const auto byte=[&](size_t k)->unsigned {return k<text.size()?uint8_t(text[k]):0u;};
    bool skip=false;
    for(size_t i=0;;) {
        // The text is read in two-byte units; a zero in either ends the line.
        const unsigned a=byte(i),b=a?byte(i+1):0u;
        if(!a||!b)break;
        i+=2;
        if(a=='C'&&b=='R')return i;
        if(a=='M'&&b=='S') {if(!extraIcons)skip=true;continue;}
        if(skip)continue;
        if(a>=0x80) {
            const char code[2]={char(a),char(b)};
            if(mode==1)canvas_.text20(list,{code,2},trunc(x),trunc(eeAdd(y,floats_[GlyphDrop])),c.r,c.g,c.b,c.a);  // 10a710
            else canvas_.text24(list,{code,2},trunc(x),trunc(y),c.r,c.g,c.b,c.a);                               // 10a1c0
            x=eeAdd(x,real(advance));
            continue;
        }
        int index=-1,dx=0,dy=0;
        if(a==0x20) {
            label(list,space_,trunc(x),trunc(y),style);
            x=eeAdd(x,real(advance>>1));
        } else if(!plain) {
            const auto pick=[&](int n,int ox,int oy) {index=n;dx=ox;dy=oy;};
            if(a=='E'&&b=='X') {
                label(list,exit_,trunc(eeAdd(x,floats_[IconInset])),trunc(eeAdd(y,floats_[ExitDrop])),style);
                x=eeAdd(x,real(advance*2+1));
            } else if(a=='I') {
                if(b=='W')index=0xe;
                else if(b=='H')index=0xf;
                else if(b>='A'&&b<='E')index=int(b)-'A'+9;
                else {
                    if(b-0x31<9)index=int(b)-0x31;
                    if(b=='Z')index=0x27;
                }
            } else if(a=='G') {
                dx=-1;dy=-2;
                if(b-0x31<9)index=int(b)-0x21;
            } else if(a=='L') {
                if(b-0x31<2)pick(int(b)-0x12,0,5);
            } else if(a=='R') {
                if(b-0x31<2)pick(int(b)-0x10,0,5);
            } else if(a=='S') {
                if(b=='C')pick(0x2d,0,0);
                else if(b=='T')pick(0x1e,3,2);
                else if(b=='L')pick(0x1d,3,4);
            } else if(a=='B') {
                if(b=='O')pick(0x19,2,3);
                else if(b=='X')pick(0x1a,2,3);
                else if(b=='T')pick(0x1c,2,3);
                else if(b=='S')pick(0x1b,2,3);
                else if(b=='P')pick(0x23,2,1);
            } else if(a=='O') {
                if(b=='R')pick(0x2a,0,0);
            } else if(a=='P') {
                if(b=='L')pick(0x29,0,0);
            }
        }
        // Anything that is not an icon consumes a single byte.
        if(index==-1) {--i;continue;}
        const float z=cursor(list,MarkupZ);
        const int wide=icon(list,index,eeAdd(eeAdd(x,floats_[IconInset]),real(dx)),eeAdd(y,real(dy)),z);
        x=eeAdd(eeAdd(x,real(wide)),real(dx+3));
    }
    list.textDepth=saved;
    return noBreak;
}

void GalleryArt::drawList(MenuDrawList& list,const ListWidget& w) {
    if(!w.shown)return;
    const bool large=w.selector.flag(MenuSelector::LargeText),medium=w.selector.flag(MenuSelector::MediumText);
    const int count=w.count();
    const bool scrolls=w.visible<count;
    Frame f;
    tint(f,w.active!=0);
    f.style=1;f.x=real(w.panel.x);f.y=real(w.panel.y);f.w=real(w.width);f.h=real(w.height);
    frame(list,f,scrolls?10:0);
    const float inset=floats_[large||medium?RowInset:SmallInset];
    const int x=trunc(eeAdd(real(w.panel.x),inset)),y=trunc(eeAdd(real(w.panel.y),inset));
    const int rows=std::min(count,w.visible),pitch=large?21:medium?17:9;
    for(int r=0;r<rows;++r) {
        const int i=w.top+r;
        // The selection is shown by the row colour alone.
        textColour=ListWidget::rowColour(w.active!=0,i==w.selector.current);
        if(unsigned(i)>=ListWidget::capacity||!w.items[size_t(i)].data())continue;
        const auto text=w.items[size_t(i)];
        if(large)label(list,text,x,y+pitch*r,1);
        else if(medium)label(list,text,x,y+pitch*r,0);
        else smallText(list,text,x,y+pitch*r);
    }
    if(scrolls) {
        Frame bar;
        tint(bar,w.active!=0);
        bar.x=real(w.panel.x+w.width-9);bar.y=real(w.panel.y+3);bar.h=real(w.height-6);bar.w=floats_[ScrollW];
        scrollBar(list,bar,count,w.visible,w.top,1);
    }
}

void GalleryArt::drawBackdrop(MenuDrawList& list,const GuideWindow& guide,MenuBackdrop& backdrop,GameRandom& random,
                              const MenuChrome& chrome) const {
    if(guide.backdrop==-1)return;
    // 109de8 (the battle scene stays visible behind the window) is outside this module.
    if(!GuideWindow::menuBackdrop(unsigned(gameMode)))return;
    if(guide.backdrop==0)canvas_.backgroundPicture(list,false);
    else if(guide.backdrop==1)canvas_.background(list,backdrop,random,chrome);
    else if(guide.backdrop==2) {
        const float z=cursor(list,BackdropZ);
        canvas_.rectangle(list,0,0,0x280,0x1c0,0xff000040,z);
    }
}

void GalleryArt::drawGuide(MenuDrawList& list,const GuideWindow& guide,MenuBackdrop& backdrop,GameRandom& random,
                           const MenuChrome& chrome) {
    drawBackdrop(list,guide,backdrop,random,chrome);
    // The bars are drawn at their panel position whether open or not; a
    // closed bar is off screen and culled by the rectangle submitter.
    if(guide.title.layout!=-1) {
        const int x=guide.title.panel.x,y=guide.title.panel.y;
        float z=cursor(list,TitleZ);
        softBar(list,real(x),real(y),z,floats_[TitleW],floats_[TitleH]);
        z=cursor(list,TitleSpriteZ);
        const auto& r=guide.data->titleRects.at(size_t(guide.titleRect));
        sheet(list,0x2e,{r.u,r.v,r.w,r.h},real(x+0x10),real(y+0xc),z);
    }
    if(guide.message.layout!=-1) {
        const int x=guide.message.panel.x,y=guide.message.panel.y;
        const float z=cursor(list,MessageZ);
        softBar(list,real(x),real(y),z,floats_[MessageW],floats_[MessageH]);
        textColour=0xffffffff;
        markup(list,guide.messageText(),1,false,real(x+0x10),real(y+0xc));
    }
    for(const GuideKeys* keys:{&guide.keys,&guide.extra}) {
        if(keys->layout==-1||(keys->layout==0&&gameMode==0x11))continue;
        const int x=keys->panel.x,y=keys->panel.y;
        const float z=cursor(list,KeysZ);
        softBar(list,real(x),real(y),z,real(keys->width),real(keys->height));
        if(keys->text<0)continue;
        textColour=0xffffffff;
        markup(list,guide.data->keyHelp.at(size_t(keys->text)),1,false,real(x+keys->textX),real(y+keys->textY));
    }
}

void GalleryArt::bind(int id) {
    if(id==picture_)return;
    char name[16];
    std::snprintf(name,sizeof name,"gl_%02d",id);
    indices_=load(assets_/(std::string(name)+".tex"),1024*1024);
    const auto pal=load(assets_/(std::string(name)+".pal"),512);
    // 17eda0 clears the first colour before the upload to palette 0x300.
    source_[0]=0;
    for(unsigned i=1;i<256;++i)source_[i]=uint16_t(pal[2*i]|pal[2*i+1]<<8);
    picture_=id;
    rebuildPalette();
}
void GalleryArt::setFade(bool enabled,int level,uint32_t colour) {
    if(level<0||level>256)throw std::invalid_argument("Invalid gallery fade level");
    fadeEnabled_=enabled;fadeLevel_=level;fadeColour_=colour;
    rebuildPalette();
}
void GalleryArt::rebuildPalette() {
    // 116588, as MenuCanvas::rebuildPalettes treats the 16-bit background CLUT.
    const bool active=fadeEnabled_&&fadeLevel_>0;
    for(unsigned i=0;i<256;++i) {
        const auto v=source_[i];
        auto& out=colours_[i];out={};
        if(!(v&0x8000))continue;
        for(int c=0;c<3;++c) {
            const int five=(v>>(10-5*c))&31,tone=int((fadeColour_>>(8*(2-c)))&255)>>3;
            out[size_t(c)]=uint8_t((active?(five*(256-fadeLevel_)+tone*fadeLevel_)>>8:five)<<3);
        }
        out[3]=128;
    }
}
void GalleryArt::picture(MenuDrawList& list,int id,int size,float x,float y,float z) {
    bind(id);
    list.additive=false;
    list.colour=0xffffffff;
    const float side=real(size);
    const size_t before=list.records.size();
    canvas_.sprite(list,5,x,y,z,side,side,0.0f,0.0f,floats_[PictureSpan],floats_[PictureSpan]);
    if(list.records.size()!=before) {
        // 108118 (10848c) converts the normalised UV to texels and clamps
        // each to size-1: the far edge of the whole sheet becomes 1023.
        auto& r=list.records.back();
        r.uw=std::min(r.u+r.uw,1023.0f)-r.u;r.vh=std::min(r.v+r.vh,1023.0f)-r.v;
    }
}

void GalleryArt::drawGalleryTop(MenuDrawList& list,MenuBackdrop& backdrop,GameRandom& random,const MenuChrome& before,
                                const GalleryTopMenu& top,const GalleryData& data) const {
    canvas_.background(list,backdrop,random,before);
    canvas_.frame(list,before,false,0,0);
    const int alpha=top.alpha;
    // 1d2620: plate 8 of the banner sheet.
    canvas_.banner(list,canvas_.banners()[8],alpha,floats_[TopPlateX],floats_[TopPlateY],floats_[TopPlateZ]);
    // 1d26d0: the cursor row is red.
    int saved=list.textDepth;
    list.textDepth=trunc(canvas_.depth(list,floats_[TopRowsZ]));
    for(int i=0;i<4;++i) {
        const int other=i==top.row?0:255;
        canvas_.text20(list,data.topLabels[size_t(i)],0x44,0x58+0x18*i,255,other,other,alpha);
    }
    list.textDepth=saved;
    // 1d27c8: tick() has already stepped the marquee.
    saved=list.textDepth;
    list.textDepth=trunc(canvas_.depth(list,floats_[TopHelpZ]));
    const auto& help=data.topHelp[size_t(top.row)];
    if(top.helpX[0]<0x280)canvas_.text20(list,help,top.helpX[0],0x198,255,255,255,alpha);
    if(data.topHelpScroll[size_t(top.row)]==1&&top.helpX[1]<0x280)
        canvas_.text20(list,help,top.helpX[1],0x198,255,255,255,alpha);
    list.textDepth=saved;
}

void GalleryArt::drawIllustrationViewer(MenuDrawList& list,MenuBackdrop& backdrop,GameRandom& random,
                                        const MenuChrome& chrome,const IllustrationViewer& v) {
    list.resetCursor();
    if(v.imageVisible()) {
        // Submitted before the background; the cursor layers 520 and 700 put it in front.
        const int half=v.size/2,x=v.centreX-half,y=v.centreY-half;
        float z=cursor(list,ViewerBackingZ);
        canvas_.rectangle(list,x-3,y-3,v.size+6,v.size+6,0x40000000,z);
        z=cursor(list,ViewerPictureZ);
        picture(list,v.imageId(),v.size,real(x),real(y),z);
    }
    if(!v.uiVisible()) {drawBackdrop(list,v.guide,backdrop,random,chrome);return;}
    drawGuide(list,v.guide,backdrop,random,chrome);
    drawList(list,v.list);
}

void GalleryArt::drawLyrics(MenuDrawList& list,const SoundTest& s,const GalleryData& data) {
    // 114d88 runs on every visit; the depth word is restored only after a drawn overlay.
    const int saved=list.textDepth;
    list.textDepth=trunc(canvas_.depth(list,eeSub(list.cursorBase,floats_[LyricTextZ])));
    const int alpha=s.lyricAlpha;
    if(!alpha||(s.lyricSet!=0&&s.lyricSet!=1))return;
    float z=cursor(list,LyricZ);
    canvas_.rectangle(list,0,0,0x280,0x1c0,(uint32_t(alpha/8)<<24)+0x00ffffffu,z);
    for(const auto& g:s.lyricGlyphs()) {
        const char code[2]={char(g.code>>8),char(g.code)};
        canvas_.text20(list,{code,2},g.x,g.y,g.r,g.g,g.b,alpha);   // 10a710
    }
    if(alpha>0) {
        // The key bar rises from below the screen as the overlay fades in.
        textColour=0xffffffff;
        const int drop=0xff-alpha;
        z=cursor(list,LyricZ);
        softBar(list,floats_[LyricBarX],real(drop+0x188),z,floats_[LyricBarW],floats_[LyricBarH]);
        markup(list,data.lyricKeys,1,false,floats_[LyricKeysX],real(drop+0x18c));
    }
    list.textDepth=saved;
}

void GalleryArt::drawSoundTest(MenuDrawList& list,MenuBackdrop& backdrop,GameRandom& random,const MenuChrome& chrome,
                               const SoundTest& s,const GalleryData& data) {
    list.resetCursor();
    drawGuide(list,s.guide,backdrop,random,chrome);
    for(const auto& w:s.lists)drawList(list,w);
    drawLyrics(list,s,data);
}

void GalleryArt::drawEndingSelect(MenuDrawList& list,MenuBackdrop& backdrop,GameRandom& random,const MenuChrome& chrome,
                                  const EndingViewer& e) {
    list.resetCursor();   // 17c210 opens every visit, also the one that returns the choice
    if(e.chosen)return;
    drawGuide(list,e.guide,backdrop,random,chrome);
    drawList(list,e.list);
}

void GalleryArt::rasterise(const MenuDrawList& list,std::span<uint8_t> rgba) const {
    if(rgba.size()!=size_t(width)*height*4)throw std::invalid_argument("Expected a 640x480 menu surface");
    std::vector<unsigned> order(list.records.size());
    std::iota(order.begin(),order.end(),0u);
    std::stable_sort(order.begin(),order.end(),[&](unsigned a,unsigned b) {return list.records[a].z<list.records[b].z;});
    // Runs between two pictures go through the canvas; they are already in
    // depth order, which its stable sort keeps.
    MenuDrawList run;
    const auto flush=[&] {
        if(run.records.empty())return;
        canvas_.rasterise(run,rgba);
        run.records.clear();
    };
    const auto integral=[](float value) {
        if(value!=std::floor(value)||std::abs(value)>32768)throw std::invalid_argument("Picture quad needs integral geometry");
        return int(value);
    };
    for(const unsigned at:order) {
        const auto& q=list.records[at];
        if(q.kind!=MenuPrimitive::Quad||q.slot!=5) {run.records.push_back(q);continue;}
        if(picture_<0)throw std::invalid_argument("No picture is bound to slot 5");
        flush();
        int mod[4];
        for(int c=0;c<4;++c)mod[c]=int((q.colour>>(8*c))&255);
        const int x=integral(q.x),y=integral(q.y),w=integral(q.w),h=integral(q.h);
        const int u=integral(q.u),v=integral(q.v),uw=integral(q.uw),vh=integral(q.vh);
        if(!w||!h)continue;
        const int left=std::min(x,x+w),top=std::min(y,y+h),nx=std::abs(w),ny=std::abs(h);
        for(int py=std::max(0,top);py<std::min(height,top+ny);++py) {
            const int j=h>0?py-top:ny-1-(py-top);
            // Texel under the pixel centre, as MenuCanvas::rasterise samples a quad.
            const int tv=v+int((2ll*j+1)*vh/(2ll*ny));
            for(int px=std::max(0,left);px<std::min(width,left+nx);++px) {
                const int i=w>0?px-left:nx-1-(px-left);
                const int tu=u+int((2ll*i+1)*uw/(2ll*nx));
                if(tu<0||tv<0||tu>=1024||tv>=1024)continue;
                const auto& texel=colours_[indices_[size_t(tv)*1024+size_t(tu)]];
                int source[4];
                for(int c=0;c<4;++c)source[c]=std::min(255,texel[size_t(c)]*mod[c]/128);
                uint8_t* dst=rgba.data()+4*(py*width+px);
                for(int c=0;c<3;++c) {
                    const int value=q.additive?dst[c]+source[c]:dst[c]+(((source[c]-dst[c])*source[3])>>7);
                    dst[c]=uint8_t(std::clamp(value,0,255));
                }
            }
        }
    }
    flush();
}

void enterGalleryBackdrop(MenuBackdrop& backdrop,MenuChrome& chrome,GameRandom& random,uint64_t seedBeforeEnter) {
    random.librarySeed=seedBeforeEnter;
    const int variant=backdrop.enter(random);
    chrome.variant=((variant&0x7fff)>>14)+1;
}
}
