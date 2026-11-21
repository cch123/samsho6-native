#include "menu_canvas.hpp"
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
// Indices into the constant block of menu_canvas.bin (extract_menu_canvas.py FLOATS).
enum Constant:unsigned {
    ConfirmZ,CancelZ,PageIconZ,PageLabelZ,BackgroundZ,PictureZ,
    FallTop,FallBottom,DriftTop,DriftBottom,IntroZ,IntroScale,IntroLimit,FallScale,FallZ,
    DriftScale,DriftZ,Half,MarkerW,MarkerH,CursorStep,CursorFar,MarkerMid,MarkerInsetY,
    MarkerInsetWide,MarkerInsetNarrow,DialogStripZ,DialogTextZ,TexelInset,ConstantCount
};
enum Text:unsigned { Confirm,Cancel,PageFeed,Number,Slash,NeoGeoLand,Reselect,Title,Yes,No,TextCount };

std::vector<uint8_t> load(const std::filesystem::path& file,size_t size=0) {
    std::ifstream in(file,std::ios::binary|std::ios::ate);
    if(!in||(size&&in.tellg()!=static_cast<std::streamoff>(size)))
        throw std::runtime_error("Invalid menu resource: "+file.string());
    std::vector<uint8_t> bytes(static_cast<size_t>(in.tellg()));
    in.seekg(0);
    if(!in.read(reinterpret_cast<char*>(bytes.data()),std::streamsize(bytes.size())))
        throw std::runtime_error("Truncated menu resource: "+file.string());
    return bytes;
}
struct Reader {
    const std::vector<uint8_t>& data;size_t at=0;
    const uint8_t* take(size_t n) {
        if(n>data.size()-at)throw std::runtime_error("Truncated menu_canvas.bin");
        at+=n;return data.data()+at-n;
    }
    uint32_t word() {const auto* p=take(4);return p[0]|p[1]<<8|p[2]<<16|uint32_t(p[3])<<24;}
    int integer() {return std::bit_cast<int32_t>(word());}
    float real() {return std::bit_cast<float>(word());}
    unsigned half() {const auto* p=take(2);return p[0]|p[1]<<8;}
};
int trunc(float value) {return int(value);}  // cvt.w.s
// EE single-precision arithmetic (results round toward zero), one operation each.
ScalarFloat scalar(float v) {return ScalarFloat{std::bit_cast<uint32_t>(v)};}
float add(float a,float b) {return std::bit_cast<float>(scalar(a).add(scalar(b)).bits);}
float sub(float a,float b) {return std::bit_cast<float>(scalar(a).sub(scalar(b)).bits);}
float mul(float a,float b) {return std::bit_cast<float>(scalar(a).mul(scalar(b)).bits);}
float div(float a,float b) {return std::bit_cast<float>(scalar(a).div(scalar(b)).bits);}
void mix(uint8_t* dst,int r,int g,int b,int alpha) {
    const int source[3]={r,g,b};
    for(int c=0;c<3;++c)dst[c]=uint8_t(std::clamp(dst[c]+(((source[c]-dst[c])*alpha)>>7),0,255));
}
}

MenuCanvas::MenuCanvas(const std::filesystem::path& assets) {
    const auto blob=load(assets/"menu_canvas.bin");
    Reader in{blob};
    if(std::memcmp(in.take(4),"MCV1",4))throw std::runtime_error("Invalid menu_canvas.bin header");
    for(auto& table:bands_)for(auto& value:table)value=in.integer();
    for(auto& legend:legends_) {for(auto& x:legend.x)x=in.integer();legend.z=in.real();}
    const auto rects=[&](std::vector<MenuSheetRect>& list,unsigned count) {
        for(unsigned i=0;i<count;++i) {
            MenuSheetRect r;r.u=in.integer();r.v=in.integer();r.w=in.integer();r.h=in.integer();list.push_back(r);
        }
    };
    rects(icons_,12);rects(banners_,9);rects(petals_,6);
    for(auto& value:backgroundRect_)value=in.integer();
    for(unsigned i=0;i<ConstantCount;++i)floats_[i]=in.real();
    for(unsigned i=0;i<TextCount;++i) {
        const unsigned n=in.half();
        strings_.emplace_back(reinterpret_cast<const char*>(in.take(n)),n);
    }
    for(auto& x:dialogX_)x=in.integer();
    for(auto& entry:textClut_)std::copy_n(in.take(4),4,entry.begin());
    defaultTextClut_=textClut_;
    for(auto& entry:trig_) {entry[0]=in.real();entry[1]=in.real();}
    const auto bytes=[&](size_t n) {const auto* p=in.take(n);return std::vector<uint8_t>(p,p+n);};
    half_=bytes(32768);
    glyphIndex_.resize(42*192);
    for(auto& value:glyphIndex_)value=uint16_t(in.half());
    glyphCount_=in.word();
    if(glyphCount_==0||glyphCount_>4096)throw std::runtime_error("Invalid menu glyph count");
    index20_=bytes(glyphCount_*200);
    index24_=bytes(glyphCount_*288);
    if(in.at!=blob.size())throw std::runtime_error("Invalid menu_canvas.bin length");

    font_=load(assets/"obj0_16.tex",512*512+1024);
    for(unsigned i=0;i<256;++i) {
        // Slot 1 carries an embedded 16x16 CLUT; CSM1 exchanges index bits 3/4.
        const unsigned j=(i&~24u)|((i&8u)<<1)|((i&16u)>>1);
        std::copy_n(font_.data()+512*512+4*j,4,fontColours_[i].begin());
    }
    font_.resize(512*512);
    // 1ce478 binds PS2_menu_bg00_00.pvr/.pvp, not the VS result board
    // menu_bg00_00; it zeroes the first colour and uploads at palette 0x200.
    background_=load(assets/"PS2_menu_bg00_00.tex",1024*1024);
    const auto pal=load(assets/"PS2_menu_bg00_00.pal",512);
    for(unsigned i=1;i<256;++i)backgroundSource_[i]=uint16_t(pal[2*i]|pal[2*i+1]<<8);
    icon_=load(assets/"ps2_common_icon.tex",512*512);
    const auto iconPal=load(assets/"ps2_common_icon.pal",1024);
    for(unsigned i=0;i<256;++i)std::copy_n(iconPal.data()+4*i,4,iconSource_[i].begin());
    rebuildPalettes();
}

void MenuCanvas::setFade(bool enabled,int level,uint32_t colour) {
    if(level<0||level>256)throw std::invalid_argument("Invalid menu fade level");
    fadeEnabled_=enabled;fadeLevel_=level;fadeColour_=colour;
    rebuildPalettes();
}

void MenuCanvas::rebuildPalettes() {
    // 116588 interpolates every CLUT in 5-bit RGB while a fade is running;
    // the fade colour 3ec730 is AARRGGBB like every colour argument here.
    // Entries with zero alpha are written as zero, and at level 0 the
    // 32-bit icon colours pass through without the 5-bit truncation.
    const bool active=fadeEnabled_&&fadeLevel_>0;
    const auto channel=[&](int five,int c) {
        const int tone=int((fadeColour_>>(8*(2-c)))&255)>>3;
        return uint8_t((active?(five*(256-fadeLevel_)+tone*fadeLevel_)>>8:five)<<3);
    };
    for(unsigned i=0;i<256;++i) {
        const auto v=backgroundSource_[i];
        auto& out=backgroundColours_[i];out={};
        if(v&0x8000) {
            for(int c=0;c<3;++c)out[c]=channel((v>>(10-5*c))&31,c);
            out[3]=128;
        }
        const auto& source=iconSource_[i];
        auto& icon=iconColours_[i];icon={};
        if(source[3]) {
            icon=source;
            if(active)for(int c=0;c<3;++c)icon[c]=channel(source[c]>>3,c);
        }
    }
}

uint32_t MenuCanvas::fade(uint32_t colour) const {
    if(!fadeEnabled_)return colour;
    uint32_t out=colour&0xff000000u;
    for(int c=0;c<3;++c) {
        const int v=int((colour>>(8*c))&255),tone=int((fadeColour_>>(8*c))&255);
        out|=uint32_t(((v*(256-fadeLevel_)+tone*fadeLevel_)>>8)&255)<<(8*c);
    }
    return out;
}
void MenuCanvas::fade(int& r,int& g,int& b) const {
    if(!fadeEnabled_)return;
    int* channels[3]={&r,&g,&b};
    for(int c=0;c<3;++c)
        *channels[c]=(*channels[c]*(256-fadeLevel_)+int((fadeColour_>>(8*(2-c)))&255)*fadeLevel_)>>8;
}
uint32_t MenuCanvas::flatColour(uint32_t colour) const {
    // 114c10 halves only the alpha. 105790 scales RGB by BRIGHT and moves
    // bits 16..23 of the argument to the queue word's low byte: flat
    // colours are passed as AARRGGBB, unlike the AABBGGRR sprite colour.
    uint32_t out=(((colour>>24)+1)>>1)<<24;
    for(int c=0;c<3;++c)out|=((((colour>>(8*c))&255)*uint32_t(brightness_))>>8&255)<<(8*(2-c));
    return out;
}
uint32_t MenuCanvas::quadColour(uint32_t colour,int blend) const {
    // 1149d0: blend 1 halves all four channels; any other selector forces
    // alpha 80. 108118/1085e0 then scale RGB by BRIGHT and store the
    // AARRGGBB argument in the queue's AABBGGRR order.
    uint32_t out=blend==1?(((colour>>24)+1)>>1)<<24:0x80000000u;
    for(int c=0;c<3;++c) {
        const uint32_t halved=(((colour>>(8*c))&255)+1)>>1;
        out|=((halved*uint32_t(brightness_))>>8&255)<<(8*(2-c));
    }
    return out;
}

float MenuCanvas::depth(MenuDrawList& list,float z) const {
    return add(sub(10000000.0f,mul(z,100.0f)),float(list.depth++));
}

namespace {
// 114e98 against the 640x480 window.
bool culled(float x0,float x1,float y0,float y1) {
    if(x0<0&&x1<0)return true;
    if(640.0f<x0&&640.0f<x1)return true;
    if(y0<0&&y1<0)return true;
    return 480.0f<y0&&480.0f<y1;
}
}

void MenuCanvas::rectangle(MenuDrawList& list,int x,int y,int w,int h,uint32_t colour,float z) const {
    if(culled(float(x),float(x+w),float(y),float(y+h)))return;
    MenuDrawRecord r;
    r.kind=MenuPrimitive::Flat;r.z=float(trunc(depth(list,z)));r.colour=flatColour(fade(colour));
    r.x=float(x);r.y=float(y);r.w=float(w);r.h=float(h);
    list.records.push_back(r);
}

void MenuCanvas::triangle(MenuDrawList& list,float x0,float y0,float x1,float y1,float x2,float y2,
                          float z,uint32_t colour) const {
    MenuDrawRecord r;
    r.kind=MenuPrimitive::Triangle;r.z=float(trunc(depth(list,z)));r.colour=flatColour(fade(colour));
    // 105790 converts each coordinate with cvt.w.s before scaling.
    const float points[6]={x0,y0,x1,y1,x2,y2};
    for(int i=0;i<6;++i)r.corner[i]=float(trunc(points[i]));
    list.records.push_back(r);
}

void MenuCanvas::quad(MenuDrawList& list,int slot,uint32_t colour,int blend,float z,float x,float y,float w,float h,
                      float u,float v,float uw,float vh) const {
    MenuDrawRecord r;
    r.kind=MenuPrimitive::Quad;r.slot=uint8_t(slot);r.blend=uint8_t(blend);r.additive=list.additive;
    r.colour=quadColour(colour,blend);r.z=z;
    r.x=x;r.y=y;r.w=w;r.h=h;r.u=u;r.v=v;r.uw=uw;r.vh=vh;
    list.records.push_back(r);
}

void MenuCanvas::sprite(MenuDrawList& list,int slot,float x,float y,float z,float w,float h,
                        float u,float v,float uw,float vh) const {
    if(culled(x,add(x,w),y,add(y,h)))return;
    // Slot 0x28 bypasses the fade modulation.
    const uint32_t colour=slot==0x28?list.colour:fade(list.colour);
    quad(list,slot,colour,list.blend,depth(list,z),x,y,w,h,u,v,uw,vh);
}

void MenuCanvas::sprite(MenuDrawList& list,const MenuSheetRect& rect,int slot,unsigned flags,uint32_t colour,
                        bool mirror,float x,float y,float z,float w,float h) const {
    if(slot<=0||(flags&0x100))return;
    list.blend=(flags&0x200)?0:1;
    if(colour)list.colour=colour;else list.additive=true;
    if(mirror)sprite(list,slot,add(x,w),y,z,-w,h,float(rect.u),float(rect.v),float(rect.w),float(rect.h));
    else sprite(list,slot,x,y,z,w,h,float(rect.u),float(rect.v),float(rect.w),float(rect.h));
    if(!colour)list.additive=false;
}

void MenuCanvas::picture(MenuDrawList& list,const MenuSheetRect& rect,int slot,unsigned,uint32_t colour,
                         float x,float y,float z) const {
    if(slot<=0)return;
    list.blend=1;
    if(colour)list.colour=colour;else list.additive=true;
    sprite(list,slot,x,y,z,float(rect.w),float(rect.h),float(rect.u),float(rect.v),float(rect.w),float(rect.h));
    if(!colour)list.additive=false;
}

void MenuCanvas::rotated(MenuDrawList& list,int slot,int degrees,float x,float y,float z,float w,float h,
                         float u,float v,float uw,float vh,float scale) const {
    if(culled(x,add(x,w),y,add(y,h)))return;
    const uint32_t colour=slot==0x28?list.colour:fade(list.colour);
    const float half=floats_[Half],inset=floats_[TexelInset];
    const float su=mul(u,scale);
    const float hh=mul(h,half);
    const float depthValue=depth(list,z);
    const float hw=mul(w,half);
    const float sv=mul(v,scale);
    const float cy=add(y,hh);
    const float suw=mul(sub(uw,inset),scale);
    const float svh=mul(sub(vh,inset),scale);
    const float cx=add(x,hw);
    const auto [cosine,sine]=trig(degrees);
    const float a=mul(hh,cosine),b=mul(hw,sine);
    const float nhw=mul(-w,half),nhh=mul(-h,half);
    const float c=mul(hh,sine);
    const float d=mul(nhw,sine),e=mul(nhh,cosine),f=mul(nhw,cosine),g=mul(nhh,sine);
    const float hwc=mul(hw,cosine);
    MenuDrawRecord r;
    r.kind=MenuPrimitive::Rotated;r.slot=uint8_t(slot);r.blend=uint8_t(list.blend);r.additive=list.additive;
    r.colour=quadColour(colour,list.blend);r.z=depthValue;
    r.corner={add(sub(f,g),cx),add(add(d,e),cy),add(sub(f,c),cx),add(add(d,a),cy),
              add(sub(hwc,g),cx),add(add(b,e),cy),add(sub(hwc,c),cx),add(add(b,a),cy)};
    // The queue stores texel units: 1085e0 multiplies the scaled UV by 512.
    const float size=slot==4||slot==5?1024.0f:512.0f;
    r.u=mul(su,size);r.v=mul(sv,size);r.uw=sub(mul(add(su,suw),size),r.u);r.vh=sub(mul(add(sv,svh),size),r.v);
    r.x=x;r.y=y;r.w=w;r.h=h;
    list.records.push_back(r);
}

void MenuCanvas::ascii(MenuDrawList& list,std::string_view text,int x,int y,uint32_t colour) const {
    const int start=x;
    for(const char raw:text) {
        const unsigned ch=uint8_t(raw);
        if(!ch)break;
        if(ch==0x0a) {x=start;y+=0x10;continue;}
        if(ch<0x80&&ch>=0x20) {
            // 113690: 30 cells per row at pitch 17 from (2,2), drawn 15x15
            // at the fixed depth 3d3aac without a tie-break increment.
            const int cell=int(ch)-0x20;
            const float z=sub(10000000.0f,mul(list.asciiDepth,100.0f));
            MenuDrawRecord r;
            r.kind=MenuPrimitive::Quad;r.slot=1;r.blend=1;r.additive=list.additive;
            r.colour=quadColour(fade(colour),1);r.z=z;
            r.x=float(x);r.y=float(y);r.w=r.h=15;r.u=float(2+17*(cell%30));r.v=float(2+17*(cell/30));r.uw=r.vh=15;
            list.records.push_back(r);
        }
        x+=0xe;  // Every byte advances, including bytes of 0x80 and above.
    }
}

void MenuCanvas::glyph(MenuDrawList& list,MenuFont font,int record,int x,int y,int w,int h,int u,int v,
                       int r,int g,int b,int alpha) const {
    fade(r,g,b);
    MenuDrawRecord q;
    q.kind=MenuPrimitive::Glyph;q.font=font;q.glyph=uint16_t(record);
    // 108c98: (c+1)*BRIGHT>>9 per colour channel, (alpha+1)>>1.
    const auto channel=[&](int c) {return uint32_t(((c+1)*brightness_)>>9)&255;};
    q.colour=channel(r)|channel(g)<<8|channel(b)<<16|(uint32_t((alpha+1)>>1)&255)<<24;
    q.z=float(list.textDepth);
    q.x=float(x);q.y=float(y);q.w=float(w);q.h=float(h);q.u=float(u);q.v=float(v);q.uw=float(w);q.vh=float(h);
    list.records.push_back(q);
}

void MenuCanvas::text(MenuDrawList& list,bool large,std::string_view sjis,int x,int y,int r,int g,int b,int alpha) const {
    const int start=x,cell=large?24:20,halfWidth=large?12:10;
    for(size_t i=0;i<sjis.size();++i) {
        const unsigned ch=uint8_t(sjis[i]);
        if(!ch)break;
        if(ch==0x0a) {x=start;y+=cell;continue;}
        if(ch<0x80) {
            if(ch>=0x21&&ch<0x7f) {
                const int index=int(ch)-0x20;
                if(large)glyph(list,MenuFont::Half,0,x,y,12,24,(index%20)*12,(index/20)*26+0x59,r,g,b,alpha);
                else glyph(list,MenuFont::Half,0,x,y,10,20,(index%24)*10,(index/24)*22+1,r,g,b,alpha);
            } else if(ch==0x7f) {
                // 10a568/10a010 route 7f through the three-vertex emitter 108e68 (tag ff5).
                throw std::invalid_argument("Menu text character 7f is not ported");
            }
            x+=halfWidth;
            continue;
        }
        if(++i>=sjis.size())break;
        const unsigned trail=uint8_t(sjis[i]);
        const int lead=int(ch>=0xa0?ch-0x40:ch)-0x81;
        const int index=lead*192+int(trail)-0x40;
        if(index<0||index>=int(glyphIndex_.size()))throw std::invalid_argument("Menu text code outside the glyph table");
        // 10a710/10a1c0 copy the record into the next 24-texel cache cell,
        // twenty cells per row; the cursor 345180 is shared by both sizes.
        const int n=list.glyphs++;
        glyph(list,large?MenuFont::Goth24:MenuFont::Goth20,glyphIndex_[size_t(index)],x,y,cell,cell,
              (n%20)*24,(n/20)*24,r,g,b,alpha);
        x+=cell;
    }
}
void MenuCanvas::text20(MenuDrawList& list,std::string_view sjis,int x,int y,int r,int g,int b,int alpha) const {
    text(list,false,sjis,x,y,r,g,b,alpha);
}
void MenuCanvas::text24(MenuDrawList& list,std::string_view sjis,int x,int y,int r,int g,int b,int alpha) const {
    text(list,true,sjis,x,y,r,g,b,alpha);
}

void MenuCanvas::marker(MenuDrawList& list,std::string_view text,int x,int y,int frame) const {
    // Visible for 39 of every 64 frames.
    if(frame%64<25)return;
    float fx=float(x-0x14);
    const float fy=float(y-1),w=floats_[MarkerW],h=floats_[MarkerH],mid=floats_[MarkerMid];
    const float insetY=floats_[MarkerInsetY],wide=floats_[MarkerInsetWide],narrow=floats_[MarkerInsetNarrow];
    // 17c228: each element sits one cursor step in front of the previous.
    const auto next=[&] {
        const float z=sub(sub(list.cursorBase,floats_[CursorFar]),list.cursor);
        list.cursor=add(list.cursor,floats_[CursorStep]);
        return z;
    };
    // 17dd88 with the three colours of the frame record forced to white:
    // an outer triangle and an inset one, pointing left and then right.
    const float middle=add(fy,mul(h,mid)),bottom=add(fy,h);
    float z=next();
    triangle(list,fx,middle,add(fx,w),fy,add(fx,w),bottom,z,0xffffffff);
    z=next();
    triangle(list,add(fx,wide),middle,sub(add(fx,w),narrow),add(fy,insetY),sub(add(fx,w),narrow),sub(bottom,insetY),z,0xffffffff);
    fx=add(fx,float(unsigned(text.size())*14u+27u));
    z=next();
    triangle(list,fx,fy,add(fx,w),middle,fx,bottom,z,0xffffffff);
    z=next();
    triangle(list,add(fx,narrow),add(fy,insetY),sub(add(fx,w),wide),middle,add(fx,narrow),sub(bottom,insetY),z,0xffffffff);
}

void MenuCanvas::dialog(MenuDrawList& list,int cursor,int kind,bool neoGeoLand) const {
    rectangle(list,0,0x64,0x280,0xf0,0xc0000000,floats_[DialogStripZ]);
    const int saved=list.textDepth;
    list.textDepth=trunc(depth(list,floats_[DialogTextZ]));
    if(neoGeoLand)text24(list,strings_[NeoGeoLand],0x9a,0xc8,255,255,255,255);
    else if(kind==1)text24(list,strings_[Reselect],0x80,0xc8,255,255,255,255);
    else text24(list,strings_[Title],0xbe,0xc8,255,255,255,255);
    for(int i=0;i<2;++i) {
        const int other=i==cursor?0:255;
        text24(list,strings_[Yes+unsigned(i)],dialogX_[size_t(i)],0xf8,255,other,other,255);
    }
    list.textDepth=saved;
}

void MenuCanvas::backgroundPicture(MenuDrawList& list,bool withOverlay) const {
    const MenuSheetRect rect{backgroundRect_[0],backgroundRect_[1],backgroundRect_[2],backgroundRect_[3]};
    picture(list,rect,backgroundRect_[5],0x20,0xffffffff,0,0,floats_[withOverlay?BackgroundZ:PictureZ]);
}
void MenuCanvas::background(MenuDrawList& list,MenuBackdrop& backdrop,GameRandom& random,const MenuChrome& chrome,
                            int overrideVariant) const {
    backgroundPicture(list);
    backdrop.draw(*this,list,random,chrome.variant,overrideVariant);
}

void MenuCanvas::frame(MenuDrawList& list,const MenuChrome& chrome,bool showPage,int page,int pages,bool legend) const {
    const int t=chrome.band,slide=t*0x280/15;
    const auto band=[&](int x,int w,unsigned y) {
        for(unsigned i=0;i<11;++i)
            rectangle(list,x,bands_[y][i],w,bands_[y+1][i],uint32_t(bands_[0][i]*t/15)<<24,-50.0f);
    };
    band(slide-0x280,0x280,1);
    band(0x1e,0x244,3);
    band(0x280-slide,0x280,5);
    if(legend)this->legend(list,chrome,0,0x15e);
    if(showPage)pageIndicator(list,chrome,0,0x27,page,pages);
}

void MenuCanvas::label(MenuDrawList& list,unsigned text,float z,int x,int y,int alpha) const {
    const int saved=list.textDepth;
    list.textDepth=trunc(depth(list,z));
    text20(list,strings_[text],x,y,255,255,255,alpha);
    list.textDepth=saved;
}
void MenuCanvas::legendIcons(MenuDrawList& list,const MenuChrome& chrome,unsigned table,unsigned first,unsigned count,
                             int x,int y,bool confirm,bool cancel) const {
    const int alpha=chrome.legend*0x33;
    const uint32_t saved=list.colour;
    list.colour=uint32_t(alpha)<<24|0xffffff;list.blend=1;
    // 1cefc8 keeps the positions the cancel icons have in the full legend.
    for(unsigned k=first;k<first+count;++k) {
        const auto& rect=icons_[k];
        sprite(list,0x2e,float(x+0x16*int(k)+legends_[table].x[k]),float(y),legends_[table].z,
               float(rect.w),float(rect.h),float(rect.u),float(rect.v),float(rect.w),float(rect.h));
    }
    if(confirm)label(list,Confirm,floats_[ConfirmZ],x+0x185,y,alpha);
    if(cancel)label(list,Cancel,floats_[CancelZ],x+0x1ed,y,alpha);
    list.colour=saved;
}
void MenuCanvas::legend(MenuDrawList& list,const MenuChrome& chrome,int x,int y) const {
    legendIcons(list,chrome,0,0,4,x,y,true,true);
}
void MenuCanvas::legendConfirm(MenuDrawList& list,const MenuChrome& chrome,int x,int y) const {
    legendIcons(list,chrome,1,0,2,x,y,true,false);
}
void MenuCanvas::legendCancel(MenuDrawList& list,const MenuChrome& chrome,int x,int y) const {
    legendIcons(list,chrome,2,2,2,x,y,false,true);
}

void MenuCanvas::pageIndicator(MenuDrawList& list,const MenuChrome& chrome,int x,int y,int page,int pages) const {
    const int alpha=chrome.legend*0x33;
    const uint32_t saved=list.colour;
    list.colour=uint32_t(alpha)<<24|0xffffff;list.blend=1;
    const float z=floats_[PageIconZ];
    for(const auto [index,dx]:{std::pair{6u,0x19a},std::pair{8u,0x1be}}) {
        const auto& rect=icons_[index];
        sprite(list,0x2e,float(x+dx),float(y),z,float(rect.w),float(rect.h),float(rect.u),float(rect.v),
               float(rect.w),float(rect.h));
    }
    label(list,PageFeed,floats_[PageLabelZ],x+0x1dd,y,alpha);
    list.colour=saved;
    const int depthSaved=list.textDepth;
    list.textDepth=trunc(depth(list,z));
    const int shown=page+1;
    text20(list,std::to_string(shown),shown<10?x+0x24b:x+0x241,y,255,255,255,alpha);
    text20(list,strings_[Slash],x+0x256,y,255,255,255,alpha);
    text20(list,std::to_string(pages),x+0x264,y,255,255,255,alpha);
    list.textDepth=depthSaved;
}

void MenuCanvas::banner(MenuDrawList& list,const MenuSheetRect& rect,int alpha,float x,float y,float z) const {
    const uint32_t saved=list.colour;
    list.colour=uint32_t(alpha)<<24|0xffffff;list.blend=1;
    sprite(list,0x2e,x,y,z,float(rect.w),float(rect.h),float(rect.u),float(rect.v),float(rect.w),float(rect.h));
    list.colour=saved;
}

void MenuCanvas::helpText(MenuDrawList& list,MenuChrome& chrome,std::string_view sjis,bool scroll,int alpha,
                          int y,float z) const {
    const int saved=list.textDepth;
    list.textDepth=trunc(depth(list,z));
    const int length=int(sjis.size());
    // Both copies of a scrolling line step the shared delay counter.
    int x=chrome.helpPosition(scroll,length,0);
    if(x<0x280)text20(list,sjis,x,y,255,255,255,alpha);
    if(scroll) {
        x=chrome.helpPosition(true,length,1);
        if(x<0x280)text20(list,sjis,x,y,255,255,255,alpha);
    }
    list.textDepth=saved;
}

// ---------------------------------------------------------------------
MenuBackdrop::MenuBackdrop() {previous.fill(-1);next.fill(-1);}
void MenuBackdrop::link(int node,int before) {
    next[size_t(node)]=before;previous[size_t(node)]=previous[size_t(before)];
    next[size_t(previous[size_t(before)])]=node;previous[size_t(before)]=node;
}
void MenuBackdrop::unlink(int node) {
    next[size_t(previous[size_t(node)])]=next[size_t(node)];
    previous[size_t(next[size_t(node)])]=previous[size_t(node)];
    next[size_t(node)]=previous[size_t(node)]=-1;
}
namespace {
int draw15(GameRandom& random) {return int(random.nextLibrary()&0x7fff);}
void commonRespawn(MenuBackdrop::Sprite& s,GameRandom& random,int durationRange,int durationBase) {
    s.tick=0;s.w=s.h=float((draw15(random)>>11)+0x10);
    s.frame=s.frameTick=0;s.duration=((draw15(random)*durationRange)>>15)+durationBase;
    s.framePeriod=((draw15(random)*0xc)>>15)+3;
    s.angle=(draw15(random)*0x168)>>15;
    s.spin=(draw15(random)*5)>>15;
}
}
int MenuBackdrop::enter(GameRandom& random) {
    previous.fill(-1);next.fill(-1);
    next[200]=201;previous[201]=200;next[202]=203;previous[203]=202;
    for(int i=0;i<200;++i) {
        auto& s=sprites[size_t(i)];
        s.x0=float(((draw15(random)*0x300)>>15)+0x200);
        s.y0=float(-0x78-((draw15(random)*0x78)>>15));
        s.x1=float(0x12c-((draw15(random)*0x300)>>15));
        s.y1=float(((draw15(random)*0x78)>>15)+0x1e0);
        commonRespawn(s,random,0xf0,0xf0);
        link(i,201);
    }
    const int variant=int(random.nextLibrary());
    target=((draw15(random)*0x64)>>15)+0x64;shown=10;clock=0;
    return variant;
}
void MenuBackdrop::respawnFalling(const MenuCanvas& canvas,Sprite& s,GameRandom& random) const {
    const int column=(draw15(random)*0x280)>>15;
    s.y0=canvas.constant(FallTop);s.y1=canvas.constant(FallBottom);s.x1=s.x0=float(column);
    commonRespawn(s,random,0xa0,0xc8);
}
void MenuBackdrop::respawnDrifting(const MenuCanvas& canvas,Sprite& s,GameRandom& random) const {
    s.y0=canvas.constant(DriftTop);
    s.x0=float((draw15(random)*0x280)>>15);
    const int right=(draw15(random)*0x32)>>15;
    const int left=(draw15(random)*-0x32)>>15;
    s.y1=canvas.constant(DriftBottom);s.x1=add(s.x0,float(right+left));
    commonRespawn(s,random,0xa0,0xc8);
}
void MenuBackdrop::submit(const MenuCanvas& canvas,MenuDrawList& list,Sprite& s,float z,float scale) const {
    const float t=float(s.tick),d=float(s.duration);
    s.x=add(s.x0,div(mul(sub(s.x1,s.x0),t),d));
    s.y=add(s.y0,div(mul(sub(s.y1,s.y0),t),d));
    const auto& rect=canvas.petals()[size_t(s.frame)];
    canvas.rotated(list,0x2e,s.angle,s.x,s.y,z,s.w,s.h,float(rect.u),float(rect.v),float(rect.w),float(rect.h),scale);
}
void MenuBackdrop::animate(Sprite& s) const {
    if(s.framePeriod<++s.frameTick) {s.frame=(s.frame+1)%6;s.frameTick=0;}
    s.angle+=s.spin;
    if(!(s.angle<0x168))s.angle=0;
}
void MenuBackdrop::intro(const MenuCanvas& canvas,MenuDrawList& list,GameRandom& random) {
    list.colour=0xffffffff;list.blend=1;
    for(int n=next[200];next[size_t(n)]!=-1;) {
        auto& s=sprites[size_t(n)];
        submit(canvas,list,s,canvas.constant(IntroZ),canvas.constant(IntroScale));
        animate(s);
        if(s.duration<++s.tick)s.tick=s.duration;
        const int following=next[size_t(n)];
        // Once below the screen the sprite joins the endless stream; its
        // first respawn there always uses the falling parameters.
        if(canvas.constant(IntroLimit)<s.y) {unlink(n);link(n,203);respawnFalling(canvas,s,random);}
        n=following;
    }
}
void MenuBackdrop::stream(const MenuCanvas& canvas,MenuDrawList& list,GameRandom& random,int variant) {
    list.colour=0xffffffff;list.blend=1;
    int count=0;
    for(int n=next[202];next[size_t(n)]!=-1;n=next[size_t(n)]) {
        auto& s=sprites[size_t(n)];
        submit(canvas,list,s,canvas.constant(variant==1?FallZ:DriftZ),canvas.constant(variant==1?FallScale:DriftScale));
        animate(s);
        if(s.duration<++s.tick) {
            if(variant==1)respawnFalling(canvas,s,random);else respawnDrifting(canvas,s,random);
        }
        // The comparison follows the increment, so shown+1 sprites run.
        if(shown<++count)break;
    }
}
void MenuBackdrop::draw(const MenuCanvas& canvas,MenuDrawList& list,GameRandom& random,int variant,int overrideVariant) {
    if(!overrideVariant)intro(canvas,list,random);
    const int selected=overrideVariant?overrideVariant:variant;
    if(selected!=1&&selected!=2)return;
    // 1e1ff0: five more sprites every 60 visits up to the drawn target.
    if(shown!=target&&++clock%60==0)shown=std::min(shown+5,target);
    stream(canvas,list,random,selected);
}

// ---------------------------------------------------------------------
void MenuCanvas::rasterise(const MenuDrawList& list,std::span<uint8_t> rgba) const {
    if(rgba.size()!=size_t(width)*height*4)throw std::invalid_argument("Expected a 640x480 menu surface");
    std::vector<unsigned> order(list.records.size());
    std::iota(order.begin(),order.end(),0u);
    std::stable_sort(order.begin(),order.end(),[&](unsigned a,unsigned b) {return list.records[a].z<list.records[b].z;});
    const auto integral=[](float value) {
        if(value!=std::floor(value)||std::abs(value)>32768)throw std::invalid_argument("Menu quad needs integral geometry");
        return int(value);
    };
    struct Sheet { const uint8_t* indices;int size;const std::array<std::array<uint8_t,4>,256>* colours; };
    const auto sheet=[&](int slot)->Sheet {
        switch(slot) {
        case 1:return {font_.data(),512,&fontColours_};
        case 4:return {background_.data(),1024,&backgroundColours_};
        case 0x2e:return {icon_.data(),512,&iconColours_};
        default:throw std::invalid_argument("Menu sheet slot is not loaded");
        }
    };
    for(const unsigned at:order) {
        const auto& q=list.records[at];
        int mod[4];
        for(int c=0;c<4;++c)mod[c]=int((q.colour>>(8*c))&255);
        const auto textured=[&](uint8_t* dst,const std::array<uint8_t,4>& texel) {
            int source[4];
            for(int c=0;c<4;++c)source[c]=std::min(255,texel[size_t(c)]*mod[c]/128);
            // ALPHA preset 348bc0 (A=Cd, B=0, C=FIX 80, D=Cs) adds the
            // modulated source; the ordinary preset blends by source alpha.
            if(q.additive)for(int c=0;c<3;++c)dst[c]=uint8_t(std::min(255,dst[c]+source[c]));
            else mix(dst,source[0],source[1],source[2],source[3]);
        };
        switch(q.kind) {
        case MenuPrimitive::Flat: {
            const int x0=std::max(0,integral(q.x)),y0=std::max(0,integral(q.y));
            const int x1=std::min(width,integral(q.x+q.w)),y1=std::min(height,integral(q.y+q.h));
            for(int y=y0;y<y1;++y) {
                auto* dst=rgba.data()+4*(y*width+x0);
                for(int x=x0;x<x1;++x,dst+=4)mix(dst,mod[0],mod[1],mod[2],mod[3]);
            }
            break;
        }
        case MenuPrimitive::Triangle: {
            // Top-left fill rule on integer sample positions: a scanline y
            // covers the pixels x with xa <= x < xb, for ymin <= y < ymax.
            long long px[3],py[3];
            for(int i=0;i<3;++i) {px[i]=integral(q.corner[size_t(2*i)]);py[i]=integral(q.corner[size_t(2*i+1)]);}
            const long long top=std::min({py[0],py[1],py[2]}),bottom=std::max({py[0],py[1],py[2]});
            for(long long y=std::max(0ll,top);y<std::min<long long>(height,bottom);++y) {
                long long left=0,right=0;bool any=false;
                for(int i=0;i<3;++i) {
                    const int j=(i+1)%3;
                    if(py[i]==py[j]||y<std::min(py[i],py[j])||y>std::max(py[i],py[j]))continue;
                    // x = px[i] + (y-py[i])*(px[j]-px[i])/(py[j]-py[i]), rounded up.
                    long long num=px[i]*(py[j]-py[i])+(y-py[i])*(px[j]-px[i]),den=py[j]-py[i];
                    if(den<0) {num=-num;den=-den;}
                    const long long edge=num>=0?(num+den-1)/den:-((-num)/den);
                    if(!any) {left=right=edge;any=true;}
                    else {left=std::min(left,edge);right=std::max(right,edge);}
                }
                if(!any)continue;
                for(long long x=std::max(0ll,left);x<std::min<long long>(width,right);++x)
                    mix(rgba.data()+4*(y*width+x),mod[0],mod[1],mod[2],mod[3]);
            }
            break;
        }
        case MenuPrimitive::Quad: {
            const auto source=sheet(q.slot);
            const int x=integral(q.x),y=integral(q.y),w=integral(q.w),h=integral(q.h);
            const int u=integral(q.u),v=integral(q.v),uw=integral(q.uw),vh=integral(q.vh);
            if(!w||!h)break;
            const int left=std::min(x,x+w),top=std::min(y,y+h),nx=std::abs(w),ny=std::abs(h);
            for(int py=std::max(0,top);py<std::min(height,top+ny);++py) {
                const int j=h>0?py-top:ny-1-(py-top);
                const int tv=v+((2*j+1)*vh)/(2*ny);
                for(int px=std::max(0,left);px<std::min(width,left+nx);++px) {
                    const int i=w>0?px-left:nx-1-(px-left);
                    const int tu=u+((2*i+1)*uw)/(2*nx);
                    if(tu<0||tv<0||tu>=source.size||tv>=source.size)continue;
                    textured(rgba.data()+4*(py*width+px),(*source.colours)[source.indices[tv*source.size+tu]]);
                }
            }
            break;
        }
        case MenuPrimitive::Rotated: {
            // Inverse affine mapping sampled at pixel centres. This is a
            // presentation model; GS triangle coverage is not verified.
            const auto source=sheet(q.slot);
            const double ox=q.corner[0],oy=q.corner[1];
            const double ax=q.corner[4]-ox,ay=q.corner[5]-oy,bx=q.corner[2]-ox,by=q.corner[3]-oy;
            const double det=ax*by-ay*bx;
            if(det==0)break;
            const float xs[4]={q.corner[0],q.corner[2],q.corner[4],q.corner[6]};
            const float ys[4]={q.corner[1],q.corner[3],q.corner[5],q.corner[7]};
            const int x0=std::max(0,int(std::floor(*std::min_element(xs,xs+4))));
            const int x1=std::min(width-1,int(std::ceil(*std::max_element(xs,xs+4))));
            const int y0=std::max(0,int(std::floor(*std::min_element(ys,ys+4))));
            const int y1=std::min(height-1,int(std::ceil(*std::max_element(ys,ys+4))));
            for(int py=y0;py<=y1;++py)for(int px=x0;px<=x1;++px) {
                const double dx=px+0.5-ox,dy=py+0.5-oy;
                const double s=(dx*by-dy*bx)/det,t=(ax*dy-ay*dx)/det;
                if(s<0||s>=1||t<0||t>=1)continue;
                const int tu=int(std::floor(double(q.u)+s*double(q.uw))),tv=int(std::floor(double(q.v)+t*double(q.vh)));
                if(tu<0||tv<0||tu>=source.size||tv>=source.size)continue;
                textured(rgba.data()+4*(py*width+px),(*source.colours)[source.indices[tv*source.size+tu]]);
            }
            break;
        }
        case MenuPrimitive::Glyph: {
            const int x=integral(q.x),y=integral(q.y),w=integral(q.w),h=integral(q.h);
            const int u=integral(q.u),v=integral(q.v);
            const uint8_t* rows=nullptr;int pitch=0;
            if(q.font==MenuFont::Half) {rows=half_.data()+size_t(v)*128;pitch=128;}
            else if(q.font==MenuFont::Goth20) {rows=index20_.data()+size_t(q.glyph)*200;pitch=10;}
            else if(q.font==MenuFont::Goth24) {rows=index24_.data()+size_t(q.glyph)*288;pitch=12;}
            else throw std::invalid_argument("Menu glyph without a font");
            if(q.glyph>=glyphCount_)throw std::invalid_argument("Menu glyph record out of range");
            const int base=q.font==MenuFont::Half?u:0;
            for(int row=0;row<h;++row) {
                const int py=y+row;
                if(py<0||py>=height)continue;
                for(int col=0;col<w;++col) {
                    const int px=x+col;
                    if(px<0||px>=width)continue;
                    const int tx=base+col;
                    const unsigned index=(rows[row*pitch+tx/2]>>(4*(tx&1)))&15;
                    textured(rgba.data()+4*(py*width+px),textClut_[index]);
                }
            }
            break;
        }
        }
    }
}
}
