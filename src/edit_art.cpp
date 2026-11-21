#include "edit_art.hpp"
#include <algorithm>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <numeric>
#include <stdexcept>

namespace ss6 {
namespace {
std::vector<uint8_t> load(const std::filesystem::path& file,size_t expected=0) {
    std::ifstream in(file,std::ios::binary);
    std::vector<uint8_t> data((std::istreambuf_iterator<char>(in)),std::istreambuf_iterator<char>());
    if(!in.good()&&!in.eof())throw std::runtime_error("Unable to read "+file.string());
    if(data.empty()||(expected&&data.size()!=expected))throw std::runtime_error("Unexpected size of "+file.string());
    return data;
}
struct Reader {
    const std::vector<uint8_t>& data;size_t at=0;
    const uint8_t* take(size_t n) {
        if(at+n>data.size())throw std::runtime_error("Truncated edit_art.bin");
        const auto* p=data.data()+at;at+=n;return p;
    }
    template<class T> T value() {T v;std::memcpy(&v,take(sizeof v),sizeof v);return v;}
};
int trunc(float v) {return int(v);}   // cvt.w.s
void mix(uint8_t* dst,int r,int g,int b,int alpha) {
    const int source[3]={r,g,b};
    for(int c=0;c<3;++c)dst[c]=uint8_t(std::clamp(dst[c]+(((source[c]-dst[c])*alpha)>>7),0,255));
}
}

EditArtAssets::EditArtAssets(const std::filesystem::path& assets) {
    const auto blob=load(assets/"edit_art.bin");
    Reader in{blob};
    if(std::memcmp(in.take(4),"EAR1",4))throw std::runtime_error("Invalid edit_art.bin header");
    const auto count=in.value<uint32_t>();
    for(uint32_t i=0;i<count;++i) {const auto at=in.value<uint32_t>();floats_.emplace_back(at,in.value<float>());}
    std::sort(floats_.begin(),floats_.end());
    for(auto& v:slant)v=in.value<double>();
    icons.resize(in.value<uint32_t>());
    for(auto& r:icons) {r.u=in.value<int32_t>();r.v=in.value<int32_t>();r.w=in.value<int32_t>();r.h=in.value<int32_t>();r.slot=in.value<int32_t>();}
    for(auto& r:titles) {r.u=in.value<int32_t>();r.v=in.value<int32_t>();r.w=in.value<int32_t>();r.h=in.value<int32_t>();}
    summaryPlate.u=in.value<int32_t>();summaryPlate.v=in.value<int32_t>();summaryPlate.w=in.value<int32_t>();
    summaryPlate.h=in.value<int32_t>();summaryPlate.slot=in.value<int32_t>();
    std::copy_n(in.take(8),6,shade.begin());
    initialTextColour=in.value<uint32_t>();
    for(auto& v:colourButtons)v=in.value<int32_t>();
    strings.resize(in.value<uint32_t>());
    for(auto& s:strings) {const auto n=in.value<uint16_t>();s.assign(reinterpret_cast<const char*>(in.take(n)),n);}
    if(in.at!=blob.size()||strings.size()!=TextCount)throw std::runtime_error("Invalid edit_art.bin length");
    gauge=load(assets/"ps2_gage_1_2_3_all.tex",1024*1024);
    const auto pal=load(assets/"ps2_gage_1_2_3_all.pal",1024);
    for(unsigned i=0;i<256;++i)std::copy_n(pal.data()+4*i,4,gaugeSource[i].begin());
}
float EditArtAssets::f(uint32_t address) const {
    const auto it=std::lower_bound(floats_.begin(),floats_.end(),std::pair<uint32_t,float>(address,-1e30f));
    if(it==floats_.end()||it->first!=address)throw std::logic_error("Edit art constant is not extracted");
    return it->second;
}

// ---------------------------------------------------------------------
EditFrame::EditFrame(const EditArtAssets& art,const EditWidgetAssets& widgets,unsigned seat)
    :art_(&art),widgets_(&widgets),seat_(seat) {
    // 1822a0: every bar starts with a reset slide. The title constructor
    // already runs 181d70(-1), which configures its slide (17f428).
    for(Bar* bar:{&title,&message,static_cast<Bar*>(&keys),static_cast<Bar*>(&extra)})bar->slide.reset();
    title.slide.configure(0,-0x90,0,0x10,0x10);title.configured=1;
}
namespace {
// 17f410 replaces the end points of a configured slide without moving it.
void endpoints(EditFrame::Bar& bar,int ox,int oy,int ix,int iy) {
    if(bar.configured) {bar.slide.outX=ox;bar.slide.outY=oy;bar.slide.inX=ix;bar.slide.inY=iy;bar.slide.duration=0x10;}
    else bar.slide.configure(ox,oy,ix,iy,0x10);
    bar.configured=1;
}
}
void EditFrame::setTitle(int value) {
    if(title.layout==value)return;
    title.layout=value;
    endpoints(title,0,-0x90,0,0x10);
    hasTitleText=false;titleText.clear();
    // 181de8..181e3c: plate of each layout.
    static constexpr int plates[11]={2,7,0xc,0xc,6,9,0xe,0xd,0xf,0xf,0xa};
    if(unsigned(value)<11)titleRect=plates[value];
}
void EditFrame::setMessageLayout(int value) {
    if(message.layout==value)return;
    message.layout=value;
    if(unsigned(value)<11) {
        if(value==4||value==7)endpoints(message,0,0x1f6,0,0x156);
        else endpoints(message,0,0x21c,0,0x17c);
    }
    messageText=widgets_->help(0x22,value);hasMessage=true;
}
void EditFrame::setKeys(Keys& bar,int value) {
    if(bar.layout==value)return;
    bar.layout=value;
    if(unsigned(value)>=14)return;
    const bool second=seat_==1;
    const auto size=[&](EditArtAssets::Text text) {
        bar.w=0x140;bar.h=0x1c;bar.dx=0x1a;bar.dy=2;bar.text=art_->text(text);bar.hasText=true;
    };
    switch(value) {
    case 0:   // 181960: only the slide; size and text keep their values
        if(second)endpoints(bar,0,0x192,-0x190,0x192);else endpoints(bar,0x140,0x192,0x2d0,0x192);
        break;
    case 1:case 2:case 3:
        size(EditArtAssets::KeysDefault);endpoints(bar,0x2d0,0x158,0x140,0x158);
        break;
    case 4:case 7:
        size(EditArtAssets::KeysDefault);
        if(second)endpoints(bar,-0x190,0x192,0,0x192);else endpoints(bar,0x2d0,0x192,0x140,0x192);
        break;
    case 11:case 12:case 13:
        bar.w=0x140;bar.h=0x1c;bar.dx=0x1a;bar.dy=2;
        endpoints(bar,0x2d0,0x13c,0x140,0x13c);
        bar.text=art_->text(value==11?EditArtAssets::KeysReset:value==12?EditArtAssets::KeysCopy:EditArtAssets::KeysCancel);
        bar.hasText=true;
        break;
    default:  // 5, 6, 8, 9, 10
        size(value==9?EditArtAssets::KeysRestore:EditArtAssets::KeysDefault);
        if(second)endpoints(bar,-0x190,0x158,0,0x158);else endpoints(bar,0x2d0,0x158,0x140,0x158);
        break;
    }
}
void EditFrame::setLayout(int value) {
    if(layout==value)return;
    layout=value;
    if(unsigned(value)<11) {
        static constexpr int kinds[11]={1,0,0,0,-1,0,1,-1,1,1,1};
        backdrop=kinds[value];
        setTitle(value);setMessageLayout(value);setKeys(keys,value);
    }
    if(!initialised) {
        // 182770: all four bars snap to their retracted position.
        for(Bar* bar:{&title,&message,static_cast<Bar*>(&keys),static_cast<Bar*>(&extra)}) {
            bar->slide.snap(bar->slide.outX,bar->slide.outY);bar->open=0;
        }
        initialised=1;
    }
    setKeys(extra,0xb);
}
void EditFrame::tick() {
    title.slide.update();message.slide.update();keys.slide.update();extra.slide.update();
}
void EditFrame::open() {
    title.slide.slideIn();title.shown=title.open=1;
    message.slide.slideIn();message.shown=message.open=1;
    keys.slide.slideIn();keys.shown=keys.open=1;
    extra.slide.slideOut();extra.open=0;
}
void EditFrame::close() {
    for(Bar* bar:{&title,&message,static_cast<Bar*>(&keys),static_cast<Bar*>(&extra)}) {bar->slide.slideOut();bar->open=0;}
}
void EditFrame::setMessage(int id,int sub) {messageText=widgets_->help(id,sub);hasMessage=true;}
void EditFrame::openExtra() {extra.slide.slideIn();extra.open=extra.shown=1;}
void EditFrame::closeExtra() {extra.slide.slideOut();extra.open=0;}
void EditFrame::apply(const ColorEditEvent& e) {
    switch(e.kind) {
    case ColorEditEvent::FrameKind:setLayout(e.a);break;
    case ColorEditEvent::FrameOpen:open();break;
    case ColorEditEvent::FrameClose:close();break;
    case ColorEditEvent::HeaderHide:hideTitle();break;
    case ColorEditEvent::Help:setMessage(e.a,e.b);break;
    case ColorEditEvent::SecondHint:setExtraLayout(e.a);break;
    case ColorEditEvent::SecondHintShow:openExtra();break;
    case ColorEditEvent::SecondHintHide:closeExtra();break;
    case ColorEditEvent::KeyHint:
        setKeyText(art_->text(e.a?EditArtAssets::KeysSelectConfirm:EditArtAssets::KeysSelect));break;
    default:break;
    }
}
void EditFrame::follow(const SpiritsEdit& scene) {
    if(layout==-1)setLayout(1);       // 13ada0 prologue: 182318(frame, 1)
    if(scene.frameOpen!=spiritsOpen_) {
        if(scene.frameOpen)open();else close();
        spiritsOpen_=scene.frameOpen;
    }
    if(scene.helpId!=-1) {messageText=scene.helpText();hasMessage=true;}
}

// ---------------------------------------------------------------------
EditArt::EditArt(const std::filesystem::path& assets,const MenuCanvas& canvas):assets_(assets),canvas_(&canvas) {
    rebuildGauge();
}
void EditArt::setFade(bool enabled,int level,uint32_t colour) {
    fadeEnabled_=enabled;fadeLevel_=level;fadeColour_=colour;rebuildGauge();
}
void EditArt::rebuildGauge() {
    // 116588 as MenuCanvas::rebuildPalettes applies it to a 32-bit CLUT.
    const bool active=fadeEnabled_&&fadeLevel_>0;
    for(unsigned i=0;i<256;++i) {
        const auto& source=assets_.gaugeSource[i];
        auto& out=gaugeColours_[i];out={};
        if(!source[3])continue;
        out=source;
        if(active)for(int c=0;c<3;++c) {
            const int tone=int((fadeColour_>>(8*(2-c)))&255)>>3;
            out[size_t(c)]=uint8_t((((source[size_t(c)]>>3)*(256-fadeLevel_)+tone*fadeLevel_)>>8)<<3);
        }
    }
}

float EditArt::layer(Context& c,uint32_t constant) const {
    const float z=c.list.cursorBase-f(constant);
    const float out=z-c.list.cursor;
    c.list.cursor=c.list.cursor+f(0x5f1f08);
    return out;
}
void EditArt::focus(Context& c,EditBox& box,bool focused) const {
    if(focused) {box.fill=0xc0101010;box.inner=0xffffffff;box.outer=c.seat==1?0xff800000:0xff000080;}
    else {box.fill=0xc0000000;box.inner=0xffa0a0a0;box.outer=c.seat==1?0xff600000:0xff000060;}
}
void EditArt::cursorColours(Context& c,EditBox& box,bool focused) const {
    box.outer=!focused?0xff404040:c.seat!=0?0xffc04040:0xff4040c0;
    box.inner=0xffffffff;
}
void EditArt::quad(Context& c,uint32_t colour,float x0,float y0,float x1,float y1,float x2,float y2,
                   float x3,float y3,float z) const {
    // 114f20. The first test reads y3 where the fourth x belongs.
    if(x0<0&&x1<0&&x2<0&&y3<0)return;
    if(640.0f<x0&&640.0f<x1&&640.0f<x2&&640.0f<x3)return;
    if(y0<0&&y1<0&&y2<0&&y3<0)return;
    if(480.0f<y0&&480.0f<y1&&480.0f<y2&&480.0f<y3)return;
    // One four-vertex strip in the original queue: both triangles carry the
    // depth and colour of the single 114d88/117288 evaluation.
    canvas_->triangle(c.list,x0,y0,x1,y1,x2,y2,z,colour);
    MenuDrawRecord second=c.list.records.back();
    second.corner={float(trunc(x1)),float(trunc(y1)),float(trunc(x2)),float(trunc(y2)),float(trunc(x3)),float(trunc(y3)),0,0};
    c.list.records.push_back(second);
}
void EditArt::border(Context& c,uint32_t colour,float x,float y,float w,float h,float t) const {
    const int X=trunc(x),T=trunc(t),Y=trunc(y),H=trunc(h),W=trunc(w);
    const float right=x+w-t,bottom=y+h-t;
    canvas_->rectangle(c.list,X,Y,T,H,colour,layer(c,0x5f1f10));
    canvas_->rectangle(c.list,X,Y,W,T,colour,layer(c,0x5f1f10));
    canvas_->rectangle(c.list,trunc(right),Y,T,H,colour,layer(c,0x5f1f10));
    canvas_->rectangle(c.list,X,trunc(bottom),W,T,colour,layer(c,0x5f1f10));
}
void EditArt::diamondBorder(Context& c,uint32_t colour,float x,float y,float w,float h,float t) const {
    const float half=f(0x5f1f18);
    const float right=x+w,cx=x+w*half,top=y+t,left=x+t,cy=y+h*half,bottom=y+h,inRight=right-t,inBottom=bottom-t;
    quad(c,colour,x,cy,cx,y,left,cy,cx,top,layer(c,0x5f1f14));
    quad(c,colour,cx,y,right,cy,cx,top,inRight,cy,layer(c,0x5f1f14));
    quad(c,colour,x,cy,left,cy,cx,bottom,cx,inBottom,layer(c,0x5f1f14));
    quad(c,colour,cx,inBottom,inRight,cy,cx,bottom,right,cy,layer(c,0x5f1f14));
}
void EditArt::window(Context& c,const EditBox& b,int gutter) const {
    int inset=0;
    const auto strip=[&] {
        if(gutter<=0)return;
        const float z=layer(c,0x5f1f1c);
        canvas_->rectangle(c.list,trunc(b.x+b.w),trunc(b.y),gutter,trunc(b.h),b.outer,z);
    };
    if(b.style==1) {
        strip();
        border(c,b.outer,b.x+0.0f,b.y+0.0f,b.w,b.h,f(0x5f1f20));
        border(c,b.inner,b.x+f(0x5f1f20),b.y+f(0x5f1f20),b.w-f(0x5f1f28),b.h-f(0x5f1f28),f(0x5f1f24));
        border(c,b.outer,b.x+f(0x5f1f2c),b.y+f(0x5f1f2c),b.w-f(0x5f1f30),b.h-f(0x5f1f30),f(0x5f1f24));
        inset=9;
    } else if(b.style==0) {
        strip();
        border(c,b.outer,b.x+0.0f,b.y+0.0f,b.w,b.h,f(0x5f1f20));
        inset=5;
    } else if(b.style==2) {
        strip();
        border(c,b.outer,b.x+0.0f,b.y+0.0f,b.w,b.h,f(0x5f1f20));
        border(c,b.inner,b.x+f(0x5f1f20),b.y+f(0x5f1f20),b.w-f(0x5f1f28),b.h-f(0x5f1f28),f(0x5f1f20));
        border(c,b.outer,b.x+f(0x5f1f28),b.y+f(0x5f1f28),b.w-f(0x5f1f38),b.h-f(0x5f1f38),f(0x5f1f24));
        border(c,b.inner,b.x+f(0x5f1f3c),b.y+f(0x5f1f3c),b.w-f(0x5f1f40),b.h-f(0x5f1f40),f(0x5f1f34));
        border(c,b.outer,b.x+f(0x5f1f44),b.y+f(0x5f1f44),b.w-f(0x5f1f48),b.h-f(0x5f1f48),f(0x5f1f34));
        inset=14;
    }
    const float edge=float(inset),twice=float(inset*2);
    const int X=trunc(b.x+edge),Y=trunc(b.y+edge);
    const float z=layer(c,0x5f1f1c);
    canvas_->rectangle(c.list,X,Y,trunc(b.w-twice),trunc(b.h-twice),b.fill,z);
}
void EditArt::diamond(Context& c,const EditBox& b) const {
    int inset=0;
    if(b.style==1) {
        diamondBorder(c,b.outer,b.x+0.0f,b.y+0.0f,b.w,b.h,f(0x5f1f4c));
        diamondBorder(c,b.inner,b.x+f(0x5f1f4c),b.y+f(0x5f1f4c),b.w-f(0x5f1f54),b.h-f(0x5f1f54),f(0x5f1f50));
        diamondBorder(c,b.outer,b.x+f(0x5f1f58),b.y+f(0x5f1f58),b.w-f(0x5f1f5c),b.h-f(0x5f1f5c),f(0x5f1f50));
        inset=9;
    } else if(b.style==0) {
        diamondBorder(c,b.outer,b.x+0.0f,b.y+0.0f,b.w,b.h,f(0x5f1f4c));
        inset=5;
    } else if(b.style==2) {
        diamondBorder(c,b.outer,b.x+0.0f,b.y+0.0f,b.w,b.h,f(0x5f1f4c));
        diamondBorder(c,b.inner,b.x+f(0x5f1f4c),b.y+f(0x5f1f4c),b.w-f(0x5f1f54),b.h-f(0x5f1f54),f(0x5f1f4c));
        diamondBorder(c,b.outer,b.x+f(0x5f1f54),b.y+f(0x5f1f54),b.w-f(0x5f1f64),b.h-f(0x5f1f64),f(0x5f1f50));
        diamondBorder(c,b.inner,b.x+f(0x5f1f68),b.y+f(0x5f1f68),b.w-f(0x5f1f6c),b.h-f(0x5f1f6c),f(0x5f1f60));
        diamondBorder(c,b.outer,b.x+f(0x5f1f70),b.y+f(0x5f1f70),b.w-f(0x5f1f74),b.h-f(0x5f1f74),f(0x5f1f60));
        inset=14;
    }
    const float z=layer(c,0x5f1f78);
    const float half=f(0x5f1f7c),edge=float(inset);
    const float hw=b.w*half,hh=b.h*half,cx=b.x+hw;
    // 17cbd0: the lower point and the right point use the width, not the height.
    quad(c,b.fill,cx,b.y+edge,b.x+b.w-edge,b.y+hw,b.x+edge,b.y+hh,cx,b.y+b.w-edge,z);
}
void EditArt::tab(Context& c,const EditBox& b) const {
    // 17ce58 evaluates the slanted sides in double precision (311390,
    // 310ee0, 310f38, 310fa0) and narrows each point with 311510.
    const int X=trunc(b.x),Y=trunc(b.y),W=trunc(b.w),H=trunc(b.h);
    const double left=X,top=Y,right=X+W,bottom=Y+H,k1=assets_.slant[0],k2=assets_.slant[1];
    const auto n=[](double v) {return float(v);};
    {
        const float z=layer(c,0x5f1f90);
        const double e=12.0*k2;
        quad(c,b.outer,n(left+0.0),n(top+0.0),n(right),n(top+0.0),n(left+e),n(bottom),n(right-e),n(bottom),z);
    }
    {
        const float z=layer(c,0x5f1f90);
        const double e=13.0*k2;
        quad(c,b.inner,n(left+k1),n(top+k2),n(right-k1),n(top+k2),n(left+e),n(bottom-k2),n(right-e),n(bottom-k2),z);
    }
    {
        const float z=layer(c,0x5f1f90);
        const double a=2.0*k1,d=2.0*k2,e=14.0*k2;
        quad(c,b.outer,n(left+a+1.0),n(top+d),n(right-a-1.0),n(top+d),n(left+e),n(bottom-d),n(right-e),n(bottom-d),z);
    }
    {
        const float z=layer(c,0x5f1f90);
        const double a=7.0*k1,d=7.0*k2,e=19.0*k2;
        quad(c,b.inner,n(left+a+1.0),n(top+d),n(right-a-1.0),n(top+d),n(left+e),n(bottom-d),n(right-e),n(bottom-d),z);
    }
}
void EditArt::slider(Context& c,const EditBox& b) const {
    const float pad=f(0x5f1f94),two=f(0x5f1f9c),mid=f(0x5f1fa0),tall=f(0x5f1fa4);
    const auto wedge=[&](uint32_t colour,int tip,int base) {
        const float z=layer(c,0x5f1f98);
        canvas_->triangle(c.list,float(tip),b.y+mid,float(base),b.y,float(base),b.y+tall,z,colour);
    };
    int s=trunc(b.x+pad-two);
    wedge(b.outer,s-0xc,s);s+=3;
    wedge(b.inner,s-0xc,s);s+=1;
    wedge(b.outer,s-0xc,s);s+=1;
    wedge(b.inner,s-0xc,s);
    s=trunc(b.x+f(0x5f1fb0)+pad);
    wedge(b.outer,s+0xc,s);s-=3;
    wedge(b.inner,s+0xc,s);s-=1;
    wedge(b.outer,s+0xc,s);s-=1;
    wedge(b.inner,s+0xc,s);
    {
        const float z=layer(c,0x5f1f98);
        const float x=b.x+pad-f(0x5f1fa8),y=b.y+f(0x5f1fac);
        canvas_->rectangle(c.list,trunc(x),trunc(y),0xba,7,b.track,z);
    }
    if(b.value>0) {
        const float z=layer(c,0x5f1f98);
        const float x=b.x+pad-f(0x5f1fa8),y=b.y+f(0x5f1fac);
        canvas_->rectangle(c.list,trunc(x),trunc(y),b.value,7,b.bar,z);
    }
    const float wide=f(0x5f1fb4);
    border(c,b.outer,b.x+pad-two,b.y+f(0x5f1fb8),wide,f(0x5f1fbc),two);
    border(c,b.inner,b.x+pad-two,b.y+two,wide,f(0x5f1fc0),two);
    border(c,b.outer,b.x+pad-two,b.y+0.0f,wide,tall,two);
}
void EditArt::brackets(Context& c,const EditBox& b) const {
    const float arm=f(0x5f1fc8);
    const auto rect=[&](uint32_t colour,int x,int y,int w,int h) {
        const float z=layer(c,0x5f1fc4);
        canvas_->rectangle(c.list,x,y,w,h,colour,z);
    };
    int x=trunc(b.x),y=trunc(b.y);
    rect(b.outer,x,y,12,6);rect(b.outer,x,y,6,12);rect(b.inner,x+2,y+2,8,2);rect(b.inner,x+2,y+2,2,8);
    y=trunc(b.y);x=trunc(b.x+b.w-arm);
    rect(b.outer,x,y,12,6);rect(b.outer,x+6,y,6,12);rect(b.inner,x+2,y+2,8,2);rect(b.inner,x+8,y+2,2,8);
    x=trunc(b.x);y=trunc(b.y+b.h-arm);
    rect(b.outer,x,y+6,12,6);rect(b.outer,x,y,6,12);rect(b.inner,x+2,y+8,8,2);rect(b.inner,x+2,y+2,2,8);
    x=trunc(b.x+b.w-arm);y=trunc(b.y+b.h-arm);
    rect(b.outer,x,y+6,12,6);rect(b.outer,x+6,y,6,12);rect(b.inner,x+2,y+8,8,2);rect(b.inner,x+8,y+2,2,8);
}
void EditArt::arrow(Context& c,const EditBox& b,bool left) const {
    const float half=f(0x5f1fe4),rim=f(0x5f1fe8),deep=f(0x5f1fec),shallow=f(0x5f1ff0);
    if(left) {
        float z=layer(c,0x5f1fe0);
        canvas_->triangle(c.list,b.x,b.y+b.h*half,b.x+b.w,b.y,b.x+b.w,b.y+b.h,z,b.outer);
        const float tip=b.x+deep,base=b.x+b.w-shallow,low=b.y+b.h-rim,mid=b.y+b.h*half,high=b.y+rim;
        z=layer(c,0x5f1fe0);
        canvas_->triangle(c.list,tip,mid,base,high,base,low,z,b.inner);
    } else {
        float z=layer(c,0x5f1fe0);
        canvas_->triangle(c.list,b.x,b.y,b.x+b.w,b.y+b.h*half,b.x,b.y+b.h,z,b.outer);
        const float base=b.x+shallow,tip=b.x+b.w-deep,low=b.y+b.h-rim,mid=b.y+b.h*half,high=b.y+rim;
        z=layer(c,0x5f1fe0);
        canvas_->triangle(c.list,base,high,tip,mid,base,low,z,b.inner);
    }
}
void EditArt::shade(Context& c,float x,float y,float z,float w,float h) const {
    for(int i=0;i<6;++i) {
        const int d=3-i;
        const float off=float(d),grow=float(2*d);
        const int Y=trunc(y-off),H=trunc(h+grow),X=trunc(x-off),W=trunc(w+grow);
        const uint32_t colour=uint32_t(assets_.shade[size_t(i)])<<24;
        if(i==5) {canvas_->rectangle(c.list,X,Y,W+1,H+1,colour,z);continue;}
        canvas_->rectangle(c.list,X,Y,W,1,colour,z);
        canvas_->rectangle(c.list,X,Y+H,W,1,colour,z);
        canvas_->rectangle(c.list,X,Y+1,1,H-1,colour,z);
        canvas_->rectangle(c.list,X+W,Y+1,1,H-1,colour,z);
    }
}
void EditArt::scrollBar(Context& c,const EditBox& b,int count,int visible,int top,int scale) const {
    const float rim=f(0x5f205c),shrink=f(0x5f2060),edge=f(0x5f2064);
    float z=layer(c,0x5f2058);
    canvas_->rectangle(c.list,trunc(b.x+edge),trunc(b.y+edge),trunc(b.w-rim),trunc(b.h-rim),b.inner,z);
    z=layer(c,0x5f2058);
    canvas_->rectangle(c.list,trunc(b.x+rim),trunc(b.y+rim),trunc(b.w-shrink),trunc(b.h-shrink),0xff000000,z);
    if(!count)throw std::invalid_argument("Scroll bar over an empty list");
    const int track=trunc(b.h-shrink);
    int thumb=track*visible*scale/count;
    if(thumb<2)thumb=2;
    const int width=trunc(b.w-f(0x5f2068));
    const float y=b.y+rim,x=b.x+f(0x5f206c);
    int offset=track-thumb;
    if(visible+top<count) {
        const int o=track*top/count;
        offset=track<o+thumb?track-thumb:o;
    }
    if(scale>=2&&track<offset+thumb)thumb=track-offset;
    z=layer(c,0x5f2058);
    canvas_->rectangle(c.list,trunc(x),trunc(y+float(offset)),width,thumb,b.inner,z);
}

uint32_t EditArt::rowColour(bool active,bool selected) {
    return active?(selected?0xffff0000:0xffffffff):(selected?0xffa00000:0xffb0b0b0);
}
void EditArt::text(Context& c,std::string_view sjis,int x,int y,int mode) const {
    const uint32_t k=c.pen.front?0x5f1ff4:c.pen.middle?0x5f1ff8:0x5f1ffc;
    const int saved=c.list.textDepth;
    c.list.textDepth=trunc(canvas_->depth(c.list,c.list.cursorBase-f(k)));
    c.list.asciiDepth=layer(c,k);                       // 113828
    const uint32_t colour=c.pen.colour;
    if(mode==0)canvas_->ascii(c.list,sjis,x,y,colour);
    else if(mode==1)canvas_->text20(c.list,sjis,x,y,int(colour>>16&255),int(colour>>8&255),int(colour&255),int(colour>>24));
    else canvas_->text24(c.list,sjis,x,y,int(colour>>16&255),int(colour>>8&255),int(colour&255),int(colour>>24));
    c.list.asciiDepth=-200.0f;                          // 113838
    c.list.textDepth=saved;
}
int EditArt::sheet(Context& c,const EditArtAssets::Icon& r,float x,float y,float z) const {
    c.list.additive=false;c.list.colour=0xffffffff;     // 1142c8; 3db900
    canvas_->sprite(c.list,r.slot,x,y,z,float(r.w),float(r.h),float(r.u),float(r.v),float(r.w),float(r.h));
    return r.w;
}
int EditArt::icon(Context& c,int index,float x,float y,float z) const {
    if(index==-1||index==0x5d)return 0;
    if(index==0x2d&&!c.option7e)return 0;
    return sheet(c,assets_.icons.at(size_t(index)),x,y,z);
}
size_t EditArt::markup(Context& c,std::string_view s,int mode,bool plain,float x,float y) const {
    const uint32_t k=c.pen.front?0x5f2010:c.pen.middle?0x5f2014:0x5f2018;
    const int saved=c.list.textDepth;
    c.list.textDepth=trunc(canvas_->depth(c.list,c.list.cursorBase-f(k)));
    const int advance=mode==1?0x14:0x18;
    const int textMode=mode==1?1:2;
    bool skip=false;
    size_t at=0,result=std::string_view::npos;
    const auto byte=[&](size_t i)->unsigned {return i<s.size()?uint8_t(s[i]):0u;};
    for(;;) {
        const unsigned a=byte(at);
        if(!a)break;
        const unsigned b=byte(at+1);
        if(!b)break;
        at+=2;
        if(a=='C'&&b=='R') {result=at;break;}
        if(a=='M'&&b=='S') {if(!c.option7e)skip=true;continue;}
        if(skip)continue;
        if(a>=0x80) {
            const char pair[2]={char(a),char(b)};
            const uint32_t colour=c.pen.colour;
            const int r=int(colour>>16&255),g=int(colour>>8&255),bl=int(colour&255),al=int(colour>>24);
            // 10a710 / 10a1c0: one glyph of the string routines.
            if(mode==1)canvas_->text20(c.list,std::string_view(pair,2),trunc(x),trunc(y+f(0x5f201c)),r,g,bl,al);
            else canvas_->text24(c.list,std::string_view(pair,2),trunc(x),trunc(y),r,g,bl,al);
            x=x+float(advance);
            continue;
        }
        int index=-1,dx=0,dy=0;
        if(a==0x20) {
            text(c,assets_.text(EditArtAssets::Space),trunc(x),trunc(y),textMode);
            x=x+float(advance>>1);
        } else if(!plain) {
            if(a=='E'&&b=='X') {
                text(c,assets_.text(EditArtAssets::Exit),trunc(x+f(0x5f2020)),trunc(y+f(0x5f2024)),textMode);
                x=x+float(advance*2+1);
            } else if(a=='I') {
                if(b=='W')index=0xe;else if(b=='H')index=0xf;else if(b=='A')index=9;else if(b=='B')index=0xa;
                else if(b=='C')index=0xb;else if(b=='D')index=0xc;else if(b=='E')index=0xd;
                else {if(b-0x31<9)index=int(b)-0x31;if(b=='Z')index=0x27;}
            } else if(a=='G') {
                dx=-1;dy=-2;if(b-0x31<9)index=int(b)-0x21;
            } else if(a=='L') {
                if(b-0x31<2) {index=int(b)-0x12;dy=5;}
            } else if(a=='R') {
                if(b-0x31<2) {index=int(b)-0x10;dy=5;}
            } else if(a=='S'&&b=='C')index=0x2d;
            else if(a=='S'&&b=='T') {dx=3;dy=2;index=0x1e;}
            else if(a=='S'&&b=='L') {dx=3;dy=4;index=0x1d;}
            else if(a=='B'&&b=='O') {dx=2;dy=3;index=0x19;}
            else if(a=='B'&&b=='X') {dx=2;dy=3;index=0x1a;}
            else if(a=='B'&&b=='T') {dx=2;dy=3;index=0x1c;}
            else if(a=='B'&&b=='S') {dx=2;dy=3;index=0x1b;}
            else if(a=='B'&&b=='P') {dx=2;dy=1;index=0x23;}
            else if(a=='O'&&b=='R')index=0x2a;
            else if(a=='P'&&b=='L')index=0x29;
        }
        // A unit that is not an icon consumes a single byte.
        if(index==-1) {--at;continue;}
        const float z=layer(c,0x5f2018);
        const int width=icon(c,index,x+f(0x5f2020)+float(dx),y+float(dy),z);
        x=x+float(width);
        x=x+float(dx+3);
    }
    c.list.textDepth=saved;
    return result;
}

void EditArt::frame(Context& c,const EditFrame& g,MenuBackdrop* backdrop,GameRandom* random,const MenuChrome* chrome) const {
    // 1817f0 with 17ea48() != 0 (a menu scene without a battle behind it).
    if(g.backdrop==0)canvas_->backgroundPicture(c.list,false);
    else if(g.backdrop==1) {
        if(!backdrop||!random||!chrome)throw std::invalid_argument("Animated edit backdrop needs the page background state");
        canvas_->background(c.list,*backdrop,*random,*chrome);
    } else if(g.backdrop==2) {
        const float z=layer(c,0x5f22b8);
        canvas_->rectangle(c.list,0,0,0x280,0x1c0,0xff000040,z);
    }
    if(g.title.layout!=-1) {                           // 181e88
        const int x=g.title.slide.x,y=g.title.slide.y;
        float z=layer(c,0x5f23ac);
        shade(c,float(x),float(y),z,f(0x5f23b0),f(0x5f23b4));
        z=layer(c,0x5f23b8);
        const auto& r=assets_.titles.at(size_t(g.titleRect));
        sheet(c,{r.u,r.v,r.w,r.h,0x2e},float(x+0x10),float(y+0xc),z);
        if(g.hasTitleText) {c.pen.colour=0xffffffff;markup(c,g.titleText,2,false,float(x+0x168),float(y+0x24));}
    }
    if(g.message.layout!=-1) {                         // 182118
        const int x=g.message.slide.x,y=g.message.slide.y;
        const float z=layer(c,0x5f3ef4);
        shade(c,float(x),float(y),z,f(0x5f3ef8),f(0x5f3efc));
        if(g.hasMessage) {c.pen.colour=0xffffffff;markup(c,g.messageText,1,false,float(x+0x10),float(y+0xc));}
    }
    for(const EditFrame::Keys* bar:{&g.keys,&g.extra}) {   // 181c30
        if(bar->layout==-1)continue;
        const int x=bar->slide.x,y=bar->slide.y;
        const float z=layer(c,0x5f2378);
        shade(c,float(x),float(y),z,float(bar->w),float(bar->h));
        if(bar->hasText) {c.pen.colour=0xffffffff;markup(c,bar->text,1,false,float(x+bar->dx),float(y+bar->dy));}
    }
}

void EditArt::listBody(Context& c,const EditListView& v,bool large) const {
    EditBox box;
    focus(c,box,v.active);
    box.x=float(v.x);box.y=float(v.y);box.w=float(v.width);box.h=float(v.height);box.style=1;
    window(c,box,v.visibleRows<v.count?10:0);
    const float inset=f(0x664870);
    const int x=trunc(float(v.x)+inset),y=trunc(float(v.y)+inset);
    const int rows=std::min(v.count,v.visibleRows);
    for(int r=0;r<rows;++r) {
        const int item=v.scroll+r;
        c.pen.colour=rowColour(v.active,item==v.cursor);
        if(item<0||size_t(item)>=v.rows.size()||!v.rows[size_t(item)].data())continue;
        text(c,v.rows[size_t(item)],x,large?y+0x15*r:y+0x11*r,large?1:0);
    }
}
void EditArt::listMenu(Context& c,const EditListView& v) const {
    if(!v.visible)return;
    if(v.flags&0x10000)listBody(c,v,true);
    else if(v.flags&0x8000)listBody(c,v,false);
    else throw std::invalid_argument("Small-font list 20f050 is not ported");
    if(v.visibleRows<v.count) {
        EditBox bar;
        focus(c,bar,v.active);
        bar.x=float(v.x+v.width-9);bar.y=float(v.y+3);bar.w=f(0x664864);bar.h=float(v.height-6);
        scrollBar(c,bar,v.count,v.visibleRows,v.scroll,1);
    }
}
void EditArt::buttonListMenu(Context& c,const EditListView& v) const {
    listMenu(c,v);
    // The icon column is drawn even while the list itself is hidden.
    const int rows=std::min(v.count,v.visibleRows);
    const int x=trunc(float(v.x)+f(0x664878));
    int y=trunc(float(v.y)+f(0x664874)+f(0x66487c));
    for(int r=0;r<rows;++r,y+=0x15) {
        const int item=v.scroll+r;
        if(item>=5)continue;
        const float yf=float(r==4?y+1:y);
        const float z=layer(c,0x664880);
        icon(c,assets_.colourButtons.at(size_t(item)),r==4?float(x-3):float(x),yf,z);
    }
}

void EditArt::spiritPanel(Context& c,const SpiritPanel& p,bool raised) const {
    if(!p.visible)return;
    int visibleRows=p.visibleRows;
    if(raised)c.list.cursorBase=f(0x6647ac);            // 17c250
    EditBox box;
    focus(c,box,p.active);
    box.style=1;box.x=float(p.slide.x);box.y=float(p.slide.y);box.h=float(p.height);box.w=float(p.width+0xc);
    const int count=p.list.max;
    window(c,box,p.visibleRows<count?10:0);
    if(p.visibleRows<count) {
        EditBox bar=box;
        bar.x=float(p.slide.x+p.width+3);bar.y=float(p.slide.y+3);bar.h=float(p.height-6);bar.w=f(0x6647b0);
        scrollBar(c,bar,count,p.visibleRows,p.scroll,1);
    }
    visibleRows=std::min(visibleRows,count);
    // A panel without a value column (the option list) is drawn in the
    // focused colours whatever its focus; its cursor row is then marked
    // only while the panel is active.
    const bool values=!p.value[0].empty();
    const bool bright=values?p.active!=0:true;
    for(int r=0;r<visibleRows;++r) {
        const int y=trunc(float(p.slide.y+2)+f(0x6647b4)+float(r*0x15));
        const int x=trunc(float(p.slide.x+2)+f(0x6647b0));
        const int row=p.scroll+r;
        const bool cursor=row==p.list.cursor&&(values||p.active);
        const bool disabled=p.list.rowDisabled(row);
        if(cursor)c.pen.colour=disabled?(bright?0xff8080c0:0xff6060a0):(bright?0xffff0000:0xffa00000);
        else c.pen.colour=disabled?0xff606080:(bright?0xffffffff:0xffb0b0b0);
        const size_t i=size_t(row);
        if(i>=p.cost.size())throw std::out_of_range("Spirit panel row");
        char cost[16];
        if(p.cost[i]>=0)std::snprintf(cost,sizeof cost,assets_.text(EditArtAssets::Cost).c_str(),p.cost[i]);
        else std::snprintf(cost,sizeof cost,assets_.text(EditArtAssets::Refund).c_str(),-p.cost[i]);
        const bool value=!p.value[i].empty();
        text(c,cost,x+(p.nameChars+p.valueChars)*9+(value?0x21:0xd),y+3,0);
        c.pen.colour=rowColour(bright,cursor);
        text(c,p.label[i],x-2,y,1);
        if(value)text(c,p.value[i],x+p.nameChars*10+8,y,1);
    }
    c.list.cursorBase=0.0f;                             // 17c250(0)
}
void EditArt::spiritEditor(Context& c,const SpiritEditor& e) const {
    spiritPanel(c,e.categories,false);
    spiritPanel(c,e.options,true);
    const auto& p=e.categories;
    if(!p.visible)return;
    EditBox box;
    focus(c,box,p.active);
    box.x=float(p.slide.x+p.width-0xbc);box.y=float(p.slide.y-0x20);box.w=f(0x6647c4);box.h=f(0x6647c8);box.style=1;
    window(c,box,0);
    c.pen.colour=0xffffffff;
    text(c,p.title,trunc(box.x+f(0x6647cc)),trunc(box.y+f(0x6647d0)),0);
}
void EditArt::spiritSummary(Context& c,int x,int y,std::span<const SpiritIcon> icons) const {
    sheet(c,assets_.summaryPlate,float(x),float(y),layer(c,0x5f2028));
    int extras=y;
    for(size_t i=0;i<icons.size();++i) {
        const int group=icons[i].group;
        float column;int second;
        if(group==5) {
            // The fixed-option column stacks 17 pixels per entry.
            column=float(x+0x87);
            const int first=extras+5;second=extras+0x15;
            const float z=layer(c,0x5f202c);
            icon(c,group+0x33,column,float(first),z);
            extras+=0x11;
        } else {
            column=float(x+0xc);
            const int first=y+int(i)*0x22+5-(group==0x21?1:0);
            const float z=layer(c,0x5f202c);
            icon(c,group+0x33,column,float(first),z);
            second=first+0x10;
        }
        const float z=layer(c,0x5f202c);
        icon(c,icons[i].icon+0x33,column,float(second),z);
    }
}

void EditArt::tabRow(Context& c,int x,int y,int index,int part,int character,int active,bool selected) const {
    EditBox box;
    if(!active) {box.outer=0xff404040;box.inner=0xffa0a0a0;box.fill=0xc0000000;}
    else if(!selected) {box.outer=0xff000000;box.fill=0x80ffffff;box.inner=0xffffffff;}
    else focus(c,box,active);
    box.y=float(y+0x12c);box.w=f(0x6646fc);
    box.x=float(x)+float(index*0x38);
    box.h=part==4?f(0x664700):f(0x664704);
    box.inner=selected?0xffffffff:0xff808080;
    tab(c,box);
    if(active&&selected) {
        const float grow=f(0x664708),lift=f(0x66470c);
        box.h=box.h+grow;box.y=box.y-lift;
        cursorColours(c,box,active);
        brackets(c,box);
        box.h=box.h-grow;box.y=box.y+lift;
    }
    box.y=box.y-f(0x664710);
    if(part==3&&character==0xb)part=2;                  // Gaira's "other" part shows the weapon label
    const int dx=part==4||part==2?0x15:part==3?0xe:part==1?0x10:0x11;
    const float z=layer(c,0x664714);
    icon(c,part+0x2e,box.x+float(dx),box.y+box.h*f(0x664718)+f(0x66471c),z);
}
void EditArt::partSelector(Context& c,const ColorEdit& s) const {
    const auto& p=s.partPanel;
    EditBox box;
    if(!p.visible)return;
    if(p.active) {focus(c,box,true);box.fill=s.part()==4?0x80808080:0x80ffffff;}
    else {box.outer=0xff404040;box.inner=0xffa0a0a0;box.fill=0xc0000000;}
    box.x=float(p.slide.x);box.y=float(p.slide.y);box.w=f(0x6646f4);box.h=f(0x6646f8);box.style=1;
    window(c,box,0);
    const int cursor=p.list.cursor;
    for(int i=s.partRows-1;i>=0;--i)
        if(i!=cursor)tabRow(c,p.slide.x,p.slide.y,i,s.partId.at(size_t(i)),s.partCharacter,p.active,false);
    tabRow(c,p.slide.x,p.slide.y,cursor,s.partId.at(size_t(cursor)),s.partCharacter,p.active,true);
}
void EditArt::swatches(Context& c,const ColorEdit& s) const {
    const auto& p=s.swatchPanel;
    EditBox box;
    if(!p.visible)return;
    if(p.active) {focus(c,box,true);box.fill=0x80ffffff;}
    else {box.outer=0xff404040;box.inner=0xffa0a0a0;box.fill=0xc0000000;}
    box.x=float(p.slide.x);box.y=float(p.slide.y);box.w=f(0x66488c);box.h=f(0x664890);box.style=1;
    const float drop=f(0x664894),size=f(0x664898);
    window(c,box,0);
    for(int i=0;i<15;++i) {
        box.x=float(p.slide.x+0xc)+float(i*0x11);
        box.y=float(p.slide.y+0xc);
        if(!(i&1))box.y=box.y+drop;
        box.fill=s.swatch[size_t(i)];box.w=box.h=size;box.style=1;
        diamond(c,box);
    }
    const int cursor=p.list.cursor;
    box.x=float(p.slide.x+0xd)+float(cursor*0x11);
    box.y=float(p.slide.y+0xd);
    if(!(cursor&1))box.y=box.y+f(0x664894);
    box.w=box.h=f(0x66489c);
    cursorColours(c,box,p.active);
    brackets(c,box);
}
void EditArt::sliders(Context& c,const ColorEdit& s) const {
    const auto& p=s.sliderPanel;
    const int active=p.active,channel=p.list.cursor;
    EditBox box;
    if(!p.visible)return;
    if(active) {focus(c,box,true);box.fill=0x80ffffff;}
    else {box.outer=0xff404040;box.inner=0xffa0a0a0;box.fill=0xc0000000;}
    box.x=float(p.slide.x);box.y=float(p.slide.y);box.w=f(0x6648b4);box.h=f(0x6648b8);box.style=1;
    window(c,box,0);
    static constexpr uint32_t lit[3]={0xffff0000,0xff00ff00,0xff0000ff},dim[3]={0xff800000,0xff008000,0xff000080};
    static constexpr uint32_t label[3]={0xffff8080,0xff80ff80,0xff8080ff},faint[3]={0xffa06060,0xff60a060,0xff6060a0};
    for(int row=0;row<3;++row) {
        box.x=float(p.slide.x+0x24);box.y=float(p.slide.y+row*0x19+0xd);
        box.value=int(s.field[size_t(row)])*6;
        box.outer=active&&row==channel&&c.seat==0?0xff4040c0:active&&row==channel?0xffc04040:0xff404040;
        box.fill=row==channel?0xffffffff:0xff808080;
        box.bar=active&&row==channel?lit[row]:dim[row];
        slider(c,box);
        if(row==channel) {
            if(active) {box.outer=0xff000000;box.fill=0x80ffffff;box.inner=0xffffffff;}
            else {box.fill=0x80ffffff;box.outer=0xff404040;box.inner=0xffa0a0a0;}
            box.x=box.x-f(0x6648bc);box.y=box.y+f(0x6648c0);box.w=f(0x6648c4);box.h=f(0x6648c8);
            arrow(c,box,false);
        }
        c.pen.colour=row==channel?label[row]:faint[row];
        if(!active)c.pen.colour=0xffa0a0a0;
        const int value=s.field[size_t(row)];
        char digits[16];
        std::snprintf(digits,sizeof digits,assets_.text(value<10?EditArtAssets::OneDigit:EditArtAssets::TwoDigits).c_str(),value);
        box.x=float(p.slide.x+0xfc);box.y=float(p.slide.y+row*0x19+0xf);
        text(c,digits,trunc(box.x),trunc(box.y),0);
    }
    const int highlight=s.highlight;
    box.x=float(p.slide.x);box.y=float(p.slide.y);
    box.x=box.x+(highlight?f(0x6648d0):f(0x6648cc));
    box.h=box.w=f(0x6648d4);box.y=box.y+f(0x6648d8);box.style=1;
    if(highlight)focus(c,box,true);
    else if(active) {box.outer=0xff000000;box.fill=0x80ffffff;box.inner=0xffffffff;}
    else {box.fill=0x80ffffff;box.outer=0xff404040;box.inner=0xffa0a0a0;}
    box.fill=(s.clipboard&0xffffff)+0xff000000u;        // 20fa20
    diamond(c,box);
    box.x=box.x+f(0x6648dc);
    box.fill=s.sliderWord();                            // 20f9f0
    diamond(c,box);
    if(highlight) {
        box.outer=0xff000000;box.fill=0x80ffffff;box.inner=0xffffffff;
        box.w=f(0x6648d0);box.h=f(0x6648e0);
        box.x=box.x+(highlight==1?f(0x6648e4):f(0x6648e8));
        box.y=box.y+f(0x6648ec);
        arrow(c,box,highlight==2);
    }
}
void EditArt::dialog(Context& c,const ColorEdit::Panel& p,std::string_view message) const {
    if(!p.visible||!p.active)return;
    const float z=layer(c,0x665268);
    canvas_->rectangle(c.list,0,0xa0,0x280,0x6c,0xc0000000,z);
    c.pen.front=true;                                   // 17e1f0
    const int span=int(message.size())*0x16;
    c.pen.colour=0xffffffff;
    text(c,message,0x140-((span<0?span+3:span)>>2),0xbc,2);
    c.pen.colour=0xffffffff;
    c.pen.colour=rowColour(true,p.list.cursor==0);
    text(c,assets_.text(EditArtAssets::Yes),0xf8,0xe4,2);
    c.pen.colour=rowColour(true,p.list.cursor!=0);
    text(c,assets_.text(EditArtAssets::No),0x15e,0xe4,2);
    c.pen.front=c.pen.middle=false;                     // 17e210
}

void EditArt::rasterise(const MenuDrawList& list,std::span<uint8_t> rgba) const {
    std::vector<unsigned> order(list.records.size());
    std::iota(order.begin(),order.end(),0u);
    std::stable_sort(order.begin(),order.end(),[&](unsigned a,unsigned b) {return list.records[a].z<list.records[b].z;});
    MenuDrawList run;
    const auto flush=[&] {
        if(!run.records.empty()) {canvas_->rasterise(run,rgba);run.records.clear();}
    };
    for(const unsigned at:order) {
        const auto& q=list.records[at];
        if(!(q.kind==MenuPrimitive::Quad&&q.slot==5)) {run.records.push_back(q);continue;}
        flush();
        // Same sampling as MenuCanvas::rasterise for an axis-aligned sheet quad.
        const int x=int(q.x),y=int(q.y),w=int(q.w),h=int(q.h),u=int(q.u),v=int(q.v),uw=int(q.uw),vh=int(q.vh);
        if(q.x!=float(x)||q.y!=float(y)||q.w!=float(w)||q.h!=float(h))throw std::invalid_argument("Edit sheet quad needs integral geometry");
        if(!w||!h)continue;
        int mod[4];
        for(int ch=0;ch<4;++ch)mod[ch]=int((q.colour>>(8*ch))&255);
        const int left=std::min(x,x+w),top=std::min(y,y+h),nx=std::abs(w),ny=std::abs(h);
        for(int py=std::max(0,top);py<std::min(480,top+ny);++py) {
            const int j=h>0?py-top:ny-1-(py-top);
            const int tv=v+((2*j+1)*vh)/(2*ny);
            for(int px=std::max(0,left);px<std::min(640,left+nx);++px) {
                const int i=w>0?px-left:nx-1-(px-left);
                const int tu=u+((2*i+1)*uw)/(2*nx);
                if(tu<0||tv<0||tu>=1024||tv>=1024)continue;
                const auto& texel=gaugeColours_[assets_.gauge[size_t(tv)*1024+size_t(tu)]];
                int source[4];
                for(int ch=0;ch<4;++ch)source[ch]=std::min(255,texel[size_t(ch)]*mod[ch]/128);
                auto* dst=rgba.data()+4*(py*640+px);
                if(q.additive)for(int ch=0;ch<3;++ch)dst[ch]=uint8_t(std::min(255,dst[ch]+source[ch]));
                else mix(dst,source[0],source[1],source[2],source[3]);
            }
        }
    }
    flush();
}

// ---------------------------------------------------------------------
EditListView editListView(const EditListMenu& m) {
    EditListView v;
    v.width=m.width;v.height=m.height;v.visibleRows=m.visibleRows;v.scroll=m.scroll;v.visible=m.visible;v.active=m.active;
    v.x=m.slide.x;v.y=m.slide.y;v.count=m.list.max;v.cursor=m.list.cursor;v.flags=m.list.flags;
    v.rows.assign(m.rows.begin(),m.rows.begin()+std::min<size_t>(m.rows.size(),size_t(std::max(0,m.list.max))));
    return v;
}
namespace {
EditListView panelView(const ColorEdit::Panel& p) {
    EditListView v;
    v.visibleRows=p.visibleRows;v.scroll=p.scroll;v.visible=p.visible;v.active=p.active;
    v.x=p.slide.x;v.y=p.slide.y;v.count=p.list.max;v.cursor=p.list.cursor;v.flags=p.list.flags;
    // 20e5d8 for a large-row list; 20e7f8 widens it per row.
    v.width=0x92;v.height=p.visibleRows*0x15+0x1a;
    return v;
}
void addRow(EditListView& v,std::string_view text) {
    v.rows.push_back(text);
    v.width=std::max(v.width,int(text.size()>>1)*0x14+0x1c);
}
}
EditListView colorEditCharacterList(const ColorEdit& s,const EditWidgetAssets& widgets) {
    EditListView v=panelView(s.characterMenu);
    for(int row=0;row<v.count;++row) {
        const int id=s.characterIds.at(size_t(row));
        // 20eae0: 4d4bb0 below 50, then the EX labels.
        if(id>=0&&id<49)addRow(v,widgets.characterNames[size_t(id)]);
        else {
            const int ex=id-0x32;
            addRow(v,widgets.exNames[ex==0x17?1:ex==0x16?2:ex==0x19?3:ex==0x18?4:0]);
        }
    }
    return v;
}
EditListView colorEditColourList(const ColorEdit& s,const EditArtAssets& art) {
    EditListView v=panelView(s.colourMenu);
    for(int row=0;row<v.count&&row<5;++row)addRow(v,art.strings[size_t(EditArtAssets::ColourRow+row)]);
    return v;
}
EditListView colorEditCopyList(const ColorEdit& s,const EditArtAssets& art) {
    EditListView v=panelView(s.copyMenu);
    for(int row=0;row<v.count&&row<2;++row)addRow(v,art.strings[size_t(EditArtAssets::CopyRow+row)]);
    return v;
}

void drawSpiritsEdit(const EditArt& art,MenuDrawList& list,EditPen& pen,const SpiritsEdit& scene,
                     const EditFrame& frame,unsigned seat,bool option7e) {
    EditArt::Context c{list,pen,seat,option7e};
    list.resetCursor();                                 // 17c210
    art.spiritEditor(c,scene.editor);
    art.listMenu(c,editListView(scene.slots));
    art.frame(c,frame);
    const auto icons=scene.summaryIcons();
    art.spiritSummary(c,scene.summary.x,scene.summary.y,icons);
}

std::array<EditPreviewObject,3> colorEditPreview(const ColorEditTables& tables,const ColorEdit& scene,
                                                 const EditArt& art,MenuDrawList& list) {
    std::array<EditPreviewObject,3> out;
    const auto& v=scene.preview;
    const auto layer=[&](unsigned scalar) {
        const float z=list.cursorBase-tables.scalars.at(scalar);
        const float r=z-list.cursor;
        list.cursor=list.cursor+art.assets().f(0x5f1f08);
        return r;
    };
    // 13bf00: the large portrait. Hidden objects still take their depth step.
    auto& portrait=out[0];
    portrait.kind=EditPreviewObject::Portrait;
    portrait.hidden=!(v.portraitVisible&&scene.portraitEnabled);
    portrait.character=scene.character();
    portrait.x=400;portrait.y=0;                        // 11d668(object, id, 190, 0, 290000)
    portrait.depth=layer(0);
    portrait.paletteKey=uint32_t(v.colour);
    // 13bfd0
    const auto sprite=colorEditSprite(tables,scene.loadedCharacter,v.spriteVisible&&scene.spriteLoaded,v.part,v.colour,v.x0);
    auto& figure=out[1];
    figure.kind=EditPreviewObject::Sprite;
    figure.hidden=sprite.hidden;figure.flip=sprite.flip;figure.character=scene.loadedCharacter;
    figure.action=sprite.action;figure.record=sprite.record;figure.x=sprite.x;figure.y=sprite.y;
    figure.depth=layer(16);
    figure.paletteKey=sprite.paletteKey;
    // 13c4f8
    const auto pose=colorEditCheckPose(tables,scene.loadedCharacter,v.poseVisible&&scene.spriteLoaded,v.colour,v.pose,v.x0);
    auto& check=out[2];
    check.kind=EditPreviewObject::CheckPose;
    check.hidden=pose.hidden;check.character=scene.loadedCharacter;
    check.action=pose.action;check.record=pose.record;check.x=pose.x;check.y=pose.y;
    check.depth=layer(26);
    check.paletteKey=pose.paletteKey;
    return out;
}

std::array<EditPreviewObject,3> drawColorEdit(const EditArt& art,MenuDrawList& list,EditPen& pen,const ColorEdit& scene,
                                              const ColorEditTables& tables,const EditFrame& frame,
                                              const EditWidgetAssets& widgets,unsigned seat,bool option7e) {
    EditArt::Context c{list,pen,seat,option7e};
    list.resetCursor();                                 // 17c210
    const auto preview=colorEditPreview(tables,scene,art,list);
    art.partSelector(c,scene);
    art.swatches(c,scene);
    art.sliders(c,scene);
    art.listMenu(c,colorEditCharacterList(scene,widgets));
    art.buttonListMenu(c,colorEditColourList(scene,art.assets()));
    art.listMenu(c,colorEditCopyList(scene,art.assets()));
    art.frame(c,frame);
    art.dialog(c,scene.dialog,art.assets().text(EditArtAssets::ResetQuestion));
    return preview;
}
}
