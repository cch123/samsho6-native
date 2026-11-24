#include "asset_files.hpp"
#include "arcade_map.hpp"
#include "scalar_float.hpp"
#include "soft_double.hpp"
#include "system_data.hpp"

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
using T=ArcadeMapTables;
constexpr int width=640,height=480;
constexpr int nameSlotA=0x1e,nameSlotB=0x2b,balloonSlotA=0x1f,balloonSlotB=0x20,iconSlot=0x22,mapSlot=0x29,cloudSlot=0x2a;
constexpr uint32_t magic=0x50414d41u; // 'AMAP'

std::vector<uint8_t> load(const std::filesystem::path& file,size_t size) {
    std::ifstream in(resolveAsset(file),std::ios::binary|std::ios::ate);
    if(!in||(size&&in.tellg()!=static_cast<std::streamoff>(size)))
        throw std::runtime_error("Invalid arcade map resource: "+file.string());
    std::vector<uint8_t> bytes(static_cast<size_t>(in.tellg()));
    in.seekg(0);
    if(!in.read(reinterpret_cast<char*>(bytes.data()),std::streamsize(bytes.size())))
        throw std::runtime_error("Truncated arcade map resource: "+file.string());
    return bytes;
}
ScalarFloat scalar(float v) {return ScalarFloat{std::bit_cast<uint32_t>(v)};}
float real(ScalarFloat v) {return std::bit_cast<float>(v.bits);}
float mul(float a,float b) {return real(scalar(a).mul(scalar(b)));}
float div(float a,float b) {return real(scalar(a).div(scalar(b)));}
float fl(int v) {return real(ScalarFloat::integer(v));}
int trunc(float v) {return scalar(v).truncate();}
double softSub(double a,double b) {return softAdd(a,-b);}   // 310f38
// 311510 (fp-bit truncdfsf2) truncates toward zero.
float narrow(double v) {
    float r=float(v);
    if(std::fabs(double(r))>std::fabs(v))r=std::nextafter(r,0.0f);
    return r;
}

// Argument of 30bd00 in 1c3608 / 1c3888 / 1c4118 / 1c4230: quarter - step * pi / steps * half
// in EE single precision, widened by 310be0. The sine itself is the value
// the original C library returned for that argument (table of the asset).
double sine(const T& t,int step,T::Constant pi) {
    const float argument=eeSub(t.floats[pi+3],mul(div(mul(fl(step),t.floats[pi]),t.floats[pi+1]),t.floats[pi+2]));
    const auto& row=t.sine.at(size_t(step-1));
    if(std::bit_cast<uint64_t>(double(argument))!=std::bit_cast<uint64_t>(row[0]))
        throw std::logic_error("Arcade map sine argument differs from the extracted table");
    return row[1];
}
// 1c4118 / 1c4230: `out` runs from `from` to `to` over 60 calls.
bool ease(const T& t,T::Constant pi,int32_t& step,float& out,float from,float to) {
    if(step>=60)return true;
    ++step;
    const double target=double(to),span=double(eeSub(to,from));
    out=narrow(softSub(target,softMul(span,sine(t,step,pi))));
    return step>=60;
}
// 114e98 against the 640x480 window.
bool culled(float x0,float x1,float y0,float y1) {
    if(x0<0&&x1<0)return true;
    if(640.0f<x0&&640.0f<x1)return true;
    if(y0<0&&y1<0)return true;
    return 480.0f<y0&&480.0f<y1;
}
int sheetSize(int slot) {return slot==mapSlot||slot==cloudSlot?1024:slot==iconSlot?256:512;}
bool ownSlot(int slot) {
    return slot==nameSlotA||slot==nameSlotB||slot==balloonSlotA||slot==balloonSlotB||slot==iconSlot||slot==mapSlot||slot==cloudSlot;
}
// 108118 (10849c..108514) clamps every texel coordinate to size-1; the far
// screen corner is kept as the EE computed it (x + w, y + h).
void finish(MenuDrawRecord& r) {
    const float limit=float(sheetSize(r.slot)-1);
    const float u1=std::min(r.u+r.uw,limit),v1=std::min(r.v+r.vh,limit);
    r.u=std::min(r.u,limit);r.v=std::min(r.v,limit);r.uw=u1-r.u;r.vh=v1-r.v;
    r.corner[0]=eeAdd(r.x,r.w);r.corner[1]=eeAdd(r.y,r.h);
}
unsigned speedDraw(GameRandom& random,unsigned scale) {return (((random.nextLibrary()&0x7fffu)*scale)>>15)+1;}
constexpr std::array<unsigned,4> speedScale={3,5,6,10};
}

// ---------------------------------------------------------------------
ArcadeMapTables::ArcadeMapTables(const std::filesystem::path& assets) {
    const auto raw=load(assets/"arcade_map.bin",0);
    size_t at=0;
    const auto take=[&](void* to,size_t n) {
        if(at+n>raw.size())throw std::runtime_error("Truncated arcade_map.bin");
        std::memcpy(to,raw.data()+at,n);at+=n;
    };
    const auto word=[&] {uint32_t v;take(&v,4);return v;};
    if(word()!=magic||word()!=1)throw std::runtime_error("Mismatched arcade_map.bin");
    if(word()!=ConstantCount)throw std::runtime_error("Unexpected arcade map constant count");
    take(floats.data(),sizeof floats);
    if(word()!=DoubleCount)throw std::runtime_error("Unexpected arcade map immediate count");
    take(doubles.data(),sizeof doubles);
    take(sine.data(),sizeof sine);
    take(&tile,24);take(clouds.data(),sizeof clouds);take(&map,24);
    take(markers.data(),sizeof markers);take(markerX.data(),44);take(markerY.data(),44);
    take(labels.data(),sizeof labels);take(labelX.data(),44);take(labelY.data(),44);
    take(nameFirst.data(),sizeof nameFirst);take(nameFirstX.data(),36);take(nameFirstY.data(),36);
    take(nameSecond.data(),sizeof nameSecond);take(nameSecondX.data(),36);take(nameSecondY.data(),36);
    take(nameCommon.data(),sizeof nameCommon);
    take(mapVoices.data(),32);take(stageVoices.data(),44);
    take(arrivalX.data(),48);take(arrivalY.data(),48);
    take(balloons.data(),sizeof balloons);
    strings.resize(word());
    for(auto& s:strings) {uint16_t n;take(&n,2);s.resize(n);take(s.data(),n);}
    messages.resize(word());
    for(auto& m:messages) {
        take(&m,24);
        for(const int32_t s:m.text)if(s>=int32_t(strings.size()))throw std::runtime_error("Arcade map message names a missing string");
    }
    for(auto& table:speakers) {
        table.resize(word());
        for(auto& s:table) {
            take(&s,sizeof s);
            for(const int32_t m:s.generic)if(m>=int32_t(messages.size()))throw std::runtime_error("Invalid arcade map message index");
            for(const int32_t m:s.pair)if(m>=int32_t(messages.size()))throw std::runtime_error("Invalid arcade map message index");
        }
    }
    if(at!=raw.size())throw std::runtime_error("Unexpected trailing arcade map data");
    // 1c1c78..1c1d38 store the sheet slots of the name records on every map
    // entry; 1c31f0 / 1c3260 store slot 0x22 into the marker records.
    for(auto& r:nameFirst)r.texture=nameSlotA;
    for(auto& r:nameSecond)r.texture=nameSlotB;
    nameCommon[0].texture=nameSlotA;nameCommon[1].texture=nameSlotB;
    for(auto& r:markers)r.texture=iconSlot;
    for(auto& r:labels)r.texture=iconSlot;
}

// ---------------------------------------------------------------------
void ArcadeMapState::reset(const ArcadeMapTables& t,GameRandom& random) {
    *this=ArcadeMapState{};
    // 1c1f88
    viewC=t.f(T::InitC);viewD=t.f(T::InitD);viewE=t.f(T::InitE);
    // 1c2010: the position is stored before the speed is drawn.
    layerY={0.0f,t.f(T::Layer1Y),t.f(T::Layer2Y),t.f(T::Layer3Y)};
    word648=t.f(T::Word648);
    const std::array<float,4> step={t.f(T::Layer0Step),t.f(T::Layer1Step),t.f(T::Layer2Step),t.f(T::Layer3Step)};
    for(unsigned layer=0;layer<4;++layer)
        for(unsigned i=T::layerFirst[layer],k=1;i<T::layerFirst[layer+1];++i,++k) {
            cloudX[i]=mul(fl(int(k)),step[layer]);
            cloudSpeed[i]=mul(fl(int(speedDraw(random,speedScale[layer]))),t.f(T::SpeedUnit));
            cloudH[i]=fl(t.clouds[i].h);
        }
}
bool ArcadeMapState::advancePath(const ArcadeMapTables& t) {
    if(pathStep>=60)return true;
    ++pathStep;
    const double s=sine(t,pathStep,T::PathPi);
    const auto& d=t.doubles;
    viewA=narrow(softSub(d[T::PathA],softMul(s,d[T::PathA])));
    viewB=narrow(softSub(d[T::PathB],softMul(s,d[T::PathB])));
    viewC=narrow(softSub(d[T::PathCBase],softMul(s,d[T::PathCScale])));
    viewD=narrow(softSub(d[T::PathDBase],softMul(s,d[T::PathDScale])));
    viewE=narrow(softSub(d[T::PathEBase],softMul(s,d[T::PathEScale])));
    return pathStep>=60;
}
bool ArcadeMapState::advanceArrival(const ArcadeMapTables& t,int stage) {
    if(arrivalStep>=60)return true;
    ++arrivalStep;
    const double s=sine(t,arrivalStep,T::ArrivalPi);
    const double x=double(t.arrivalX.at(size_t(stage))),y=double(t.arrivalY.at(size_t(stage)));
    const auto& d=t.doubles;
    offsetX=narrow(softSub(x,softMul(x,s)));
    offsetY=narrow(softSub(y,softMul(y,s)));
    viewC=eeAdd(div(mul(fl(arrivalStep),t.f(T::ArrivalScale)),t.f(T::ArrivalSteps)),t.f(T::ArrivalBase));
    viewD=narrow(softSub(d[T::ArrivalDBase],softMul(s,d[T::ArrivalDScale])));
    viewE=narrow(softSub(d[T::ArrivalEBase],softMul(s,d[T::ArrivalEScale])));
    return arrivalStep>=60;
}
void ArcadeMapState::openClouds(const ArcadeMapTables& t) {
    if(cloudsOpened)return;
    ease(t,T::EasePi,layerStep[0],layerY[0],0.0f,t.f(T::OpenY0));
    ease(t,T::EasePi,layerStep[1],layerY[1],t.f(T::OpenY1From),t.f(T::OpenY1To));
    ease(t,T::EasePi,layerStep[2],layerY[2],t.f(T::OpenY2From),t.f(T::OpenY2To));
    ease(t,T::EasePi,layerStep[3],layerY[3],t.f(T::OpenY3From),t.f(T::OpenY3To));
    unsigned done=0;
    for(unsigned i=0;i<T::cloudCount;++i) {
        const float h=fl(t.clouds[i].h);
        done+=ease(t,T::Ease2Pi,cloudStep[i],cloudH[i],h,mul(h,t.f(T::OpenShrink)));
    }
    // The four layer totals are tested separately; they complete together.
    if(done!=T::cloudCount)return;
    cloudsOpened=1;
    layerStep={};cloudStep={};
}
void ArcadeMapState::closeClouds(const ArcadeMapTables& t) {
    ease(t,T::EasePi,layerStep[0],layerY[0],t.f(T::CloseY0),0.0f);
    ease(t,T::EasePi,layerStep[1],layerY[1],t.f(T::CloseY1From),t.f(T::CloseY1To));
    ease(t,T::EasePi,layerStep[2],layerY[2],t.f(T::CloseY2From),t.f(T::CloseY2To));
    ease(t,T::EasePi,layerStep[3],layerY[3],t.f(T::CloseY3From),t.f(T::CloseY3To));
    for(unsigned i=0;i<T::cloudCount;++i) {
        const float h=fl(t.clouds[i].h);
        ease(t,T::Ease2Pi,cloudStep[i],cloudH[i],mul(h,t.f(T::CloseShrink)),h);
    }
}
void ArcadeMapState::moveClouds(const ArcadeMapTables& t,GameRandom& random) {
    const std::array<float,4> respawn={t.f(T::Respawn0),t.f(T::Respawn1),t.f(T::Respawn2),t.f(T::Respawn3)};
    for(unsigned layer=0;layer<4;++layer) {
        const unsigned first=T::layerFirst[layer],last=T::layerFirst[layer+1];
        unsigned gone=0;
        for(unsigned i=first;i<last;++i) {
            if(layer<2) {
                cloudX[i]=eeAdd(cloudX[i],cloudSpeed[i]);
                gone+=t.f(T::CloudLimit)<cloudX[i];
            } else {
                cloudX[i]=eeSub(cloudX[i],cloudSpeed[i]);
                gone+=cloudX[i]<eeSub(t.f(T::CloudLeft),fl(t.clouds[i].w));
            }
        }
        // A layer restarts only when every one of its clouds has left.
        if(gone!=last-first)continue;
        for(unsigned i=first,k=1;i<last;++i,++k) {
            cloudX[i]=mul(fl(int(k)),respawn[layer]);
            cloudSpeed[i]=mul(fl(int(speedDraw(random,speedScale[layer]))),t.f(T::RespawnUnit));
        }
    }
}
void ArcadeMapFrame::capture(const ArcadeMapState& s) {
    viewA=s.viewA;viewB=s.viewB;viewD=s.viewD;viewE=s.viewE;offsetX=s.offsetX;offsetY=s.offsetY;
    layerY=s.layerY;cloudX=s.cloudX;cloudH=s.cloudH;pathStep=s.pathStep;
}

// ---------------------------------------------------------------------
ArcadeMapArt::ArcadeMapArt(const std::filesystem::path& assets):tables_(assets),assets_(assets) {
    map_=load(assets/"map_main.tex",1024*1024);
    cloud_=load(assets/"map_cloud.tex",1024*1024);
    moji4_=load(assets/"moji4.tex",512*512/2);
    moji5_=load(assets/"moji5.tex",512*512/2);
    balloon1_=load(assets/"hukidasi.tex",512*512/2);
    balloon2_=load(assets/"hukidasi2.tex",512*512/2);
    // 113980: map_main.pal becomes the 32-bit CLUT 3101 of slots 0x29 and
    // 0x2a (10add8 pins both to it). Entry 0 is cleared, the others are
    // opaque; 116588 never touches this CLUT.
    const auto pal=load(assets/"map_main.pal",512);
    for(unsigned i=1;i<256;++i) {
        const unsigned v=pal[2*i]|pal[2*i+1]<<8;
        mapColours_[i]={uint8_t(((v>>10)&31)<<3),uint8_t(((v>>5)&31)<<3),uint8_t((v&31)<<3),128};
    }
    // 4-bit sheets use bank 0 of the resident obj0 CLUT (113890 clears entry 0).
    const auto obj=load(assets/"obj0.pal",512);
    for(unsigned i=1;i<16;++i)bankSource_[i]=uint16_t(obj[2*i]|obj[2*i+1]<<8);
    rebuild();
}
void ArcadeMapArt::bindIcon(int stage) {
    const int index=stage<10?stage:9;   // 1c1f08
    if(index<0)throw std::invalid_argument("Invalid arcade map stage");
    char name[32];
    std::snprintf(name,sizeof name,"map_icon_%02d",index);
    iconIndices_=load(assets_/(std::string(name)+".tex"),256*256);
    const auto pal=load(assets_/(std::string(name)+".pal"),512);
    // 1c1f4c clears the first colour before 116478(0x300, 0x100).
    for(unsigned i=0;i<256;++i)iconSource_[i]=i?uint16_t(pal[2*i]|pal[2*i+1]<<8):uint16_t(0);
    icon_=index;
    rebuild();
}
void ArcadeMapArt::setFade(bool enabled,int level,uint32_t colour) {
    if(level<0||level>256)throw std::invalid_argument("Invalid arcade map fade level");
    fadeEnabled_=enabled;fadeLevel_=level;fadeColour_=colour;
    rebuild();
}
void ArcadeMapArt::rebuild() {
    // 116588: 5-bit interpolation toward 3ec730 while a fade runs; entries
    // without the 0x8000 bit stay fully transparent.
    const bool active=fadeEnabled_&&fadeLevel_>0;
    const auto convert=[&](uint16_t v) {
        std::array<uint8_t,4> out{};
        if(!(v&0x8000))return out;
        for(int c=0;c<3;++c) {
            const int five=(v>>(10-5*c))&31,tone=int((fadeColour_>>(8*(2-c)))&255)>>3;
            out[size_t(c)]=uint8_t((active?(five*(256-fadeLevel_)+tone*fadeLevel_)>>8:five)<<3);
        }
        out[3]=128;
        return out;
    };
    for(unsigned i=0;i<16;++i)bankColours_[i]=convert(bankSource_[i]);
    for(unsigned i=0;i<256;++i)iconColours_[i]=convert(iconSource_[i]);
}
uint32_t ArcadeMapArt::queueColour(const MenuCanvas& canvas,MenuDrawList& list) const {
    // Slot 0x28 is the path of the public emitter without the 117288 fade:
    // the 1149d0 conversion of 3db900 under 3db8fc alone.
    const int depth=list.depth;
    canvas.sprite(list,0x28,0,0,0,1,1,0,0,1,1);
    const uint32_t colour=list.records.back().colour;
    list.records.pop_back();list.depth=depth;
    return colour;
}
void ArcadeMapArt::plain(const MenuCanvas& canvas,MenuDrawList& list,const ArcadeSpriteRecord& r,uint32_t colour,
                         float x,float y) const {
    // 117760 -> 113be0: no fade of the vertex colour and the bare tie-break
    // counter as depth (114d78), which puts these sprites behind every
    // 114d88 submission.
    if(r.texture<=0)return;
    list.blend=1;list.colour=colour;
    const float w=fl(r.w),h=fl(r.h);
    if(culled(x,eeAdd(x,w),y,eeAdd(y,h)))return;
    MenuDrawRecord q;
    q.kind=MenuPrimitive::Quad;q.slot=uint8_t(r.texture);q.blend=1;q.additive=list.additive;
    q.colour=queueColour(canvas,list);q.z=fl(list.depth++);
    q.x=x;q.y=y;q.w=w;q.h=h;q.u=fl(r.u);q.v=fl(r.v);q.uw=w;q.vh=h;
    finish(q);
    list.records.push_back(q);
}
void ArcadeMapArt::sheet(const MenuCanvas& canvas,MenuDrawList& list,const ArcadeSpriteRecord& r,unsigned flags,
                         uint32_t colour,float x,float y,float z,float w,float h) const {
    const size_t before=list.records.size();
    canvas.sprite(list,MenuSheetRect{r.u,r.v,r.w,r.h},r.texture,flags,colour,false,x,y,z,w,h);
    if(list.records.size()!=before)finish(list.records.back());
}

void ArcadeMapArt::ground(const MenuCanvas& canvas,MenuDrawList& list,const ArcadeMapFrame& f) const {
    const auto& t=tables_;
    // 1c2860: 4 x 6 tiles at depths 1..24; the counter then continues from
    // its previous value plus the number of tiles.
    const int saved=list.depth;
    list.depth=1;
    for(int row=0;row<6;++row)
        for(int column=0;column<4;++column)
            plain(canvas,list,t.tile,0xffffffffu,fl(column*t.tile.w),fl(row*t.tile.h));
    list.depth=saved+list.depth-1;

    // 1c2920: the picture as a quadrilateral whose top edge is inset by
    // viewA and dropped by viewB.
    const float drop=eeSub(f.viewE,t.f(T::MeshE));
    float y0=eeSub(f.viewB,drop);
    float x2=eeSub(f.viewD,f.viewA);
    float y1=eeAdd(f.viewE,0.0f);
    y0=eeAdd(y0,f.offsetY);
    const float over=eeSub(f.viewD,t.f(T::MeshD));
    y1=eeAdd(y1,f.offsetY);
    x2=eeAdd(x2,f.offsetX);
    float x3=eeAdd(f.viewD,0.0f);
    float x0=eeSub(f.viewA,over);
    float x1=eeSub(0.0f,over);
    x3=eeAdd(x3,f.offsetX);
    x0=eeAdd(x0,f.offsetX);
    x1=eeAdd(x1,f.offsetX);
    list.colour=0xffffffffu;list.blend=0;

    // 1c32c8: vertex fade toward 3ec730 (the CLUT of slot 0x29 is not
    // processed by 116588), then a 9 x 9 grid submitted as eight strips.
    uint32_t colour=list.colour;
    if(fadeEnabled_) {
        const int k=0x100-fadeLevel_;
        uint32_t mixed=colour&0xff000000u;
        for(int c=0;c<3;++c)
            mixed|=((uint32_t(int((colour>>(8*c))&255)*k+int((fadeColour_>>(8*c))&255)*fadeLevel_)>>8)&255u)<<(8*c);
        colour=mixed;
    }
    list.colour=colour;
    const uint32_t queue=queueColour(canvas,list);
    list.colour=0xffffffffu;
    const float z=fl(list.depth++);
    const float scale=t.f(T::MeshScale),eighth=t.f(T::MeshEighth);
    // The right corners share the heights of the left ones (f18 = f16, f19 = f17).
    const float topX=eeSub(x2,x0),bottomX=eeSub(x3,x1),topY=eeSub(y0,y0),bottomY=eeSub(y1,y1);
    const float u0=mul(fl(t.map.u),scale),v0=mul(fl(t.map.v),scale),du=mul(fl(t.map.w),scale),dv=mul(fl(t.map.h),scale);
    struct Vertex {float x,y,u,v;};
    std::array<std::array<Vertex,9>,9> grid; // [s][t]
    const float texels=float(sheetSize(mapSlot)),last=texels-1.0f;
    for(int s=0;s<9;++s) {
        const float fs=fl(s);
        const float ax=eeAdd(x0,mul(mul(topX,fs),eighth)),bx=eeAdd(x1,mul(mul(bottomX,fs),eighth));
        const float ay=eeAdd(y0,mul(mul(topY,fs),eighth)),by=eeAdd(y1,mul(mul(bottomY,fs),eighth));
        const float u=eeAdd(u0,mul(mul(du,fs),eighth));
        const float spanX=eeSub(bx,ax),spanY=eeSub(by,ay);
        for(int k=0;k<9;++k) {
            const float fk=fl(k);
            const float v=eeAdd(v0,mul(mul(dv,fk),eighth));
            grid[size_t(s)][size_t(k)]={eeAdd(ax,mul(mul(spanX,fk),eighth)),eeAdd(ay,mul(mul(spanY,fk),eighth)),
                                        std::min(mul(u,texels),last),std::min(mul(v,texels),last)};
        }
    }
    for(int s=0;s<8;++s)
        for(int k=0;k<8;++k) {
            const auto& a=grid[size_t(s)][size_t(k)];const auto& b=grid[size_t(s)][size_t(k+1)];
            const auto& c=grid[size_t(s+1)][size_t(k)];const auto& d=grid[size_t(s+1)][size_t(k+1)];
            MenuDrawRecord q;
            q.kind=MenuPrimitive::Rotated;q.slot=mapSlot;q.blend=0;q.additive=list.additive;q.colour=queue;q.z=z;
            q.corner={a.x,a.y,b.x,b.y,c.x,c.y,d.x,d.y};
            q.u=a.u;q.v=a.v;q.uw=c.u-a.u;q.vh=b.v-a.v;
            q.x=a.x;q.y=a.y;q.w=c.x-a.x;q.h=b.y-a.y;
            list.records.push_back(q);
        }
}
void ArcadeMapArt::markers(const MenuCanvas& canvas,MenuDrawList& list,int stage) const {
    const auto& t=tables_;
    const size_t s=size_t(stage);
    if(stage<0||s>=t.markers.size())throw std::invalid_argument("No arcade map marker exists for this stage");
    plain(canvas,list,t.markers[s],0xffffffffu,fl(t.markerX[s]),fl(t.markerY[s]));
    plain(canvas,list,t.labels[s],0xffffffffu,fl(t.labelX[s]),fl(t.labelY[s]));
}
void ArcadeMapArt::clouds(const MenuCanvas& canvas,MenuDrawList& list,const ArcadeMapFrame& f) const {
    const auto& t=tables_;
    for(unsigned layer=0;layer<4;++layer)
        for(unsigned i=T::layerFirst[layer];i<T::layerFirst[layer+1];++i)
            sheet(canvas,list,t.clouds[i],0x20,0x80ffffffu,f.cloudX[i],f.layerY[layer],t.f(T::CloudZ),fl(t.clouds[i].w),f.cloudH[i]);
}
void ArcadeMapArt::names(const MenuCanvas& canvas,MenuDrawList& list,const ArcadeMapFrame& f) const {
    const auto& t=tables_;
    // Fades out while the path advances: alpha 255 - 4.25 * step.
    const int alpha=trunc(eeSub(t.f(T::NameAlpha),mul(fl(f.pathStep),t.f(T::NameAlphaStep))));
    const uint32_t colour=uint32_t(alpha)<<24|0x00ffffffu;
    const size_t index=f.stage==3?8:size_t(f.stageIndex);
    if(index>=t.nameFirst.size())throw std::invalid_argument("No arcade map name exists for this stage index");
    const float z=t.f(T::NameZ);
    const auto show=[&](const ArcadeSpriteRecord& r,float x,float y) {sheet(canvas,list,r,0,colour,x,y,z,fl(r.w),fl(r.h));};
    show(t.nameFirst[index],fl(t.nameFirstX[index]),fl(t.nameFirstY[index]));
    show(t.nameSecond[index],fl(t.nameSecondX[index]),fl(t.nameSecondY[index]));
    if(index<4) {
        show(t.nameCommon[0],t.f(T::NameCommonX0),t.f(T::NameCommonY0));
        show(t.nameCommon[1],t.f(T::NameCommonX1),t.f(T::NameCommonY1));
    }
}
int ArcadeMapArt::glyphs(const ArcadeBalloon& b) const {
    int count=0;
    for(int i=0;i<b.lines;++i) {
        const auto& text=tables_.strings.at(size_t(b.text[size_t(i)]));
        for(size_t k=0;k<text.size();++k) {
            const unsigned ch=uint8_t(text[k]);
            if(ch==0x0a)continue;
            if(ch>=0x80)++k;
            ++count;
        }
    }
    return count;
}
int ArcadeMapArt::balloon(const MenuCanvas& canvas,MenuDrawList& list,const ArcadeBalloon& b) const {
    const auto& t=tables_;
    int id=b.balloon;
    const bool mirror=id>=6;
    if(mirror)id-=5;
    const auto& row=t.balloons.at(size_t(id));
    const float w=fl(row[5]),h=fl(row[6]);
    const size_t before=list.records.size();
    // The mirrored sheet starts at u + w with a negative texel width.
    canvas.sprite(list,row[0],fl(row[1]),fl(row[2]),t.f(T::BalloonZ),w,h,mirror?fl(row[3]+row[5]):fl(row[3]),fl(row[4]),
                  mirror?fl(-row[5]):w,h);
    if(list.records.size()!=before)finish(list.records.back());
    // 113028 with colour -1: every glyph counts against the limit 3d3aa0
    // and is drawn at the depth 114e40(3d3aac).
    const int saved=list.textDepth;
    list.textDepth=trunc(eeSub(10000000.0f,mul(list.asciiDepth,100.0f)));
    int count=0;
    const int textX=row[7]+row[1];
    int y=row[8]+row[2]+(3-b.lines)*0xe;
    for(int i=0;i<b.lines;++i,y+=0x18) {
        const auto& text=t.strings.at(size_t(b.text[size_t(i)]));
        int x=textX,lineY=y;
        for(size_t k=0;k<text.size();) {
            const unsigned ch=uint8_t(text[k]);
            if(ch==0x0a) {x=textX;lineY+=0x18;++k;continue;}
            const size_t n=ch<0x80?1:2;
            if(b.limit<0||count<b.limit) {
                canvas.text24(list,std::string_view(text).substr(k,n),x,lineY,255,255,255,255);
                ++count;
            }
            x+=n==1?0xc:0x18;
            k+=n;
        }
    }
    list.textDepth=saved;
    return count;
}

void ArcadeMapArt::rasterise(const MenuCanvas& canvas,const MenuDrawList& list,std::span<uint8_t> rgba) const {
    if(rgba.size()!=size_t(width)*height*4)throw std::invalid_argument("Expected a 640x480 arcade map surface");
    std::vector<unsigned> order(list.records.size());
    std::iota(order.begin(),order.end(),0u);
    std::stable_sort(order.begin(),order.end(),[&](unsigned a,unsigned b) {return list.records[a].z<list.records[b].z;});
    MenuDrawList pending;
    const auto flush=[&] {
        if(pending.records.empty())return;
        canvas.rasterise(pending,rgba);pending.records.clear();
    };
    const auto texel=[&](int slot,int tu,int tv)->const uint8_t* {
        const auto nibble=[&](const std::vector<uint8_t>& s) {return (s[size_t(tv)*256+size_t(tu/2)]>>(4*(tu&1)))&15;};
        switch(slot) {
        case mapSlot:return mapColours_[map_[size_t(tv)*1024+size_t(tu)]].data();
        case cloudSlot:return mapColours_[cloud_[size_t(tv)*1024+size_t(tu)]].data();
        case iconSlot:
            if(icon_<0)throw std::invalid_argument("No map icon is bound to slot 0x22");
            return iconColours_[iconIndices_[size_t(tv)*256+size_t(tu)]].data();
        case nameSlotA:return bankColours_[size_t(nibble(moji4_))].data();
        case nameSlotB:return bankColours_[size_t(nibble(moji5_))].data();
        case balloonSlotA:return bankColours_[size_t(nibble(balloon1_))].data();
        default:return bankColours_[size_t(nibble(balloon2_))].data();
        }
    };
    const auto floorDiv=[](long long a,long long b) {
        long long q=a/b;
        if((a%b)!=0&&((a<0)!=(b<0)))--q;
        return q;
    };
    for(const unsigned at:order) {
        const auto& q=list.records[at];
        const bool own=ownSlot(q.slot)&&(q.kind==MenuPrimitive::Quad||q.kind==MenuPrimitive::Rotated);
        if(!own) {pending.records.push_back(q);continue;}
        flush();
        const int size=sheetSize(q.slot);
        int mod[4];
        for(int c=0;c<4;++c)mod[c]=int((q.colour>>(8*c))&255);
        const auto put=[&](int px,int py,int tu,int tv) {
            const uint8_t* t=texel(q.slot,tu,tv);
            int source[4];
            for(int c=0;c<4;++c)source[c]=std::min(255,t[c]*mod[c]/128);
            auto* dst=rgba.data()+4*(size_t(py)*width+size_t(px));
            for(int c=0;c<3;++c) {
                // Tag 2ff2 (latch 348b10): ALPHA preset 348bc0, Cd + Cs.
                const int value=q.additive?dst[c]+source[c]:dst[c]+(((source[c]-dst[c])*source[3])>>7);
                dst[c]=uint8_t(std::clamp(value,0,255));
            }
        };
        if(q.kind==MenuPrimitive::Rotated) {
            // One cell of the 1c32c8 strip: triangles (P0, P2, P1) and
            // (P2, P1, P3) in strip order, sampled at pixel centres with
            // affine texel interpolation and a half-open edge rule.
            const double px[4]={q.corner[0],q.corner[2],q.corner[4],q.corner[6]};
            const double py[4]={q.corner[1],q.corner[3],q.corner[5],q.corner[7]};
            const double pu[4]={q.u,q.u,double(q.u)+double(q.uw),double(q.u)+double(q.uw)};
            const double pv[4]={q.v,double(q.v)+double(q.vh),q.v,double(q.v)+double(q.vh)};
            const int tris[2][3]={{0,2,1},{2,1,3}};
            for(const auto& tri:tris) {
                int a=tri[0],b=tri[1],c=tri[2];
                double area=(px[b]-px[a])*(py[c]-py[a])-(py[b]-py[a])*(px[c]-px[a]);
                if(area==0)continue;
                if(area<0) {std::swap(b,c);area=-area;}
                const double minX=std::min({px[a],px[b],px[c]}),maxX=std::max({px[a],px[b],px[c]});
                const double minY=std::min({py[a],py[b],py[c]}),maxY=std::max({py[a],py[b],py[c]});
                const int left=std::max(0,int(std::floor(minX))),right=std::min(width-1,int(std::ceil(maxX)));
                const int top=std::max(0,int(std::floor(minY))),bottom=std::min(height-1,int(std::ceil(maxY)));
                const auto tie=[](double dx,double dy) {return dy>0||(dy==0&&dx<0);};
                const bool tie0=tie(px[c]-px[b],py[c]-py[b]),tie1=tie(px[a]-px[c],py[a]-py[c]),tie2=tie(px[b]-px[a],py[b]-py[a]);
                for(int y=top;y<=bottom;++y) {
                    const double sy=double(y)+0.5;
                    for(int x=left;x<=right;++x) {
                        const double sx=double(x)+0.5;
                        const double w0=(px[c]-px[b])*(sy-py[b])-(py[c]-py[b])*(sx-px[b]);
                        const double w1=(px[a]-px[c])*(sy-py[c])-(py[a]-py[c])*(sx-px[c]);
                        const double w2=(px[b]-px[a])*(sy-py[a])-(py[b]-py[a])*(sx-px[a]);
                        if(!(w0>0||(w0==0&&tie0))||!(w1>0||(w1==0&&tie1))||!(w2>0||(w2==0&&tie2)))continue;
                        const double fu=((w0*pu[a]+w1*pu[b])+w2*pu[c])/area,fv=((w0*pv[a]+w1*pv[b])+w2*pv[c])/area;
                        const int tu=int(std::floor(fu)),tv=int(std::floor(fv));
                        if(tu<0||tv<0||tu>=size||tv>=size)continue;
                        put(x,y,tu,tv);
                    }
                }
            }
            continue;
        }
        const float fx1=q.corner[0],fy1=q.corner[1],fu1=q.u+q.uw,fv1=q.v+q.vh;
        const float values[8]={q.x,q.y,fx1,fy1,q.u,q.v,fu1,fv1};
        const bool aligned=std::all_of(std::begin(values),std::end(values),[](float v) {return v==std::floor(v)&&std::abs(v)<32768;});
        if(aligned) {
            // Texel under each pixel centre, as MenuCanvas::rasterise samples a quad.
            const int x0=int(q.x),y0=int(q.y),x1=int(fx1),y1=int(fy1),u0=int(q.u),v0=int(q.v),u1=int(fu1),v1=int(fv1);
            if(x0==x1||y0==y1)continue;
            for(int py=std::max(0,std::min(y0,y1));py<std::min(height,std::max(y0,y1));++py) {
                const int tv=v0+int(floorDiv((2ll*py+1-2ll*y0)*(v1-v0),2ll*(y1-y0)));
                for(int px=std::max(0,std::min(x0,x1));px<std::min(width,std::max(x0,x1));++px) {
                    const int tu=u0+int(floorDiv((2ll*px+1-2ll*x0)*(u1-u0),2ll*(x1-x0)));
                    if(tu<0||tv<0||tu>=size||tv>=size)continue;
                    put(px,py,tu,tv);
                }
            }
            continue;
        }
        // Fractional rectangle: the pixel centres inside [x, x1) x [y, y1).
        const double x0=q.x,y0=q.y,x1=fx1,y1=fy1;
        const double minX=std::min(x0,x1),maxX=std::max(x0,x1),minY=std::min(y0,y1),maxY=std::max(y0,y1);
        const int left=std::max(0,int(std::floor(minX))),right=std::min(width-1,int(std::ceil(maxX)));
        const int top=std::max(0,int(std::floor(minY))),bottom=std::min(height-1,int(std::ceil(maxY)));
        const double ax=x1-x0,by=y1-y0,det=ax*by;
        if(det==0)continue;
        for(int py=top;py<=bottom;++py) {
            const double dy=double(py)+0.5-y0;
            for(int px=left;px<=right;++px) {
                const double dx=double(px)+0.5-x0;
                const double s=(dx*by-dy*0.0)/det,t=(ax*dy-0.0*dx)/det;
                if(!(s>=0&&s<1&&t>=0&&t<1))continue;
                const int tu=int(std::floor(double(q.u)+s*(double(fu1)-double(q.u))));
                const int tv=int(std::floor(double(q.v)+t*(double(fv1)-double(q.v))));
                if(tu<0||tv<0||tu>=size||tv>=size)continue;
                put(px,py,tu,tv);
            }
        }
    }
    flush();
}

// ---------------------------------------------------------------------
ArcadeSceneEvents ArcadeMapScene::enter(ArcadeRun& run,ArcadeMapState& state,ArcadeMapArt& art,ArcadeObjectHost& objects) {
    ArcadeSceneEvents events;
    const auto& t=art.tables();
    const int mode=run.game.mode;
    object=-1;
    if(mode==1||mode==2) {
        const unsigned h=mode==2;
        auto& human=run.players[h];
        if(human.progress!=1) {
            // 1c1e30, 1c2420, 1c1ec8, 1e7c00(0x16, 0).
            state.reset(t,run.random());
            run.prepareFight();
            art.bindIcon(run.game.stage);
            events.music=0x16;
        }
        human.progress=2;
        // 1c25a0 (11d488 for both characters, 10b640(3)) is the caller's resource load.
        if(human.stageIndex==0)object=objects.create(0x1770,int(h),0x703,h?0x190:0xf0,h?0x80000:0,human.colour);
    }
    for(unsigned i=0;i<5;++i)camera[i]=t.floats[T::MapCamera0+i];
    frame=ArcadeMapFrame{};
    return events;
}
ArcadeSceneEvents ArcadeMapScene::tick(ArcadeRun& run,ArcadeMapState& state,const ArcadeMapArt& art,ArcadeObjectHost& objects) {
    ArcadeSceneEvents events;
    const auto& t=art.tables();
    const int mode=run.game.mode,stage=run.game.stage,stageIndex=run.mapStageIndex;
    const bool frozen=run.game.challengerFreeze!=0;
    if((mode==1||mode==2)&&run.players[mode==2].stageIndex==0) {
        if(objects.finished(object))objects.restart(object,0x703);
        objects.step(object);
    }
    if(state.frame>=0x5b) {
        state.pathDone=state.advancePath(t);
        state.openClouds(t);
    }
    if(state.frame>=0x97&&state.pathDone) {
        state.arrived=state.advanceArrival(t,stage);
        state.closeClouds(t);
    }
    frame.capture(state);
    frame.stage=stage;frame.stageIndex=stageIndex;frame.markers=false;frame.names=false;
    if(state.arrived) {
        run.game.transitionLock=1;
        if(state.postArrival>=0xb) {
            if(!state.exitState)state.exitState=1;
            frame.markers=true;
        }
        if(!frozen)++state.postArrival;
    }
    state.moveClouds(t,run.random());
    if(state.frame>=0x1e) {
        // The request repeats while a challenger freeze holds the frame at 0x1e.
        if(state.frame==0x1e)events.voice=t.mapVoices.at(size_t(stage==3?7:stageIndex));
        frame.names=true;
    }
    if(state.exitState&&!frozen) {
        events.exit={true,true,0,0,destructor,ArcadeScene::WalkIn};
        state.exitState=2;
    }
    if(!frozen)++state.frame;
    return events;
}
void ArcadeMapScene::draw(const ArcadeMapArt& art,const MenuCanvas& canvas,MenuDrawList& list) const {
    art.ground(canvas,list,frame);
    if(frame.markers)art.markers(canvas,list,frame.stage);
    art.clouds(canvas,list,frame);
    if(frame.names)art.names(canvas,list,frame);
}

// ---------------------------------------------------------------------
void ArcadeWalkInScene::enter(ArcadeRun& run,const ArcadeMapArt& art) {
    // 10add8(0x10000..0x10002, 0x10) returns without a write (ids above 0x1ff).
    *this=ArcadeWalkInScene{};
    for(unsigned i=0;i<5;++i) {
        redrawCamera[i]=art.tables().floats[T::RedrawCamera0+i];
        camera[i]=art.tables().floats[T::WalkCamera0+i];
    }
    // 1c4530
    run.startHoldCounter=run.startHoldFlag?0xf:0;
}
bool ArcadeWalkInScene::dialogueStage(const ArcadeRun& run) {
    const int mode=run.game.mode;
    if(mode!=1&&mode!=2)return false;
    const int index=run.players[mode==2].stageIndex;
    return index==3||(index>=5&&index<=7);
}
int ArcadeWalkInScene::message(const ArcadeMapTables& tables,int language,int listener,int speaker,GameRandom& random) {
    const auto& table=tables.speakers[language?1:0];
    if(speaker<0||size_t(speaker)>=table.size()||listener<0||listener>=int(T::pairCount))
        throw std::invalid_argument("No arcade pair message table for this character");
    const auto& entry=table[size_t(speaker)];
    int index=entry.pair[size_t(listener)];
    // 1a31a8: bit 14 of one library draw selects between the two generic lists.
    if(index<0)index=entry.generic[(random.nextLibrary()>>14)&1];
    if(index<0)throw std::invalid_argument("The speaker has no generic arcade message");
    return index;
}
void ArcadeWalkInScene::animate(ArcadeObjectHost& objects,unsigned seat,bool latch) {
    // Every finished action, 0x704 included, is followed by the loop 0x703.
    if(objects.finished(object[seat])) {
        if(latch)finished_[seat]=1;
        objects.restart(object[seat],0x703);
    }
    objects.step(object[seat]);
}
void ArcadeWalkInScene::startHold(ArcadeRun& run,uint32_t held) {
    if(!(held&8))return;
    if(run.startHoldFlag) {
        if(--run.startHoldCounter<=0)run.startHoldFlag=0;
    } else if(++run.startHoldCounter>=0xf)run.startHoldFlag=1;
}
bool ArcadeWalkInScene::revealed(const ArcadeMapArt& art,bool fadeComplete) const {
    // 1130f8 / 1131d8 neither draw nor count once 3ec73c is set.
    const int total=fadeComplete?0:art.glyphs(balloon);
    const int drawn=balloon.limit<0?total:std::min(total,balloon.limit);
    return drawn<balloon.limit;
}
ArcadeSceneEvents ArcadeWalkInScene::tick(ArcadeRun& run,ArcadeMapState& state,const ArcadeMapArt& art,ArcadeObjectHost& objects,
                                          uint32_t held,uint32_t pressed,int language,bool fadeComplete) {
    ArcadeSceneEvents events;
    const auto& t=art.tables();
    // Task 1c43f0 (priority 0xa) runs before the coroutine (priority 0x14).
    frame.capture(state);
    frame.stage=run.game.stage;frame.stageIndex=run.mapStageIndex;frame.markers=true;frame.names=false;
    state.moveClouds(t,run.random());
    balloon.visible=false;

    const int mode=run.game.mode;
    const unsigned h=mode==2,c=h^1;
    auto& players=run.players;
    const bool frozen=run.game.challengerFreeze!=0;
    const bool button=(pressed&0x60f)!=0;
    const auto request=[&](ArcadeScene next) {
        run.request(2,0,destructor,next);
        events.exit={true,false,2,0,destructor,next};
        exitLatch=1;
    };
    const auto solo=[&] {
        // Phase A: only a fighter on its first stage (action 0x703) moves.
        if(mode==1) {if(players[0].stageIndex==0)animate(objects,0,true);}
        else if(mode==2) {if(players[1].stageIndex==0)animate(objects,1,true);}
        --countdown_;
        if(button)countdown_=0;
    };
    const auto speak=[&] {
        balloon.visible=true;
        balloon.limit=messageFrame_/4;
        ++messageFrame_;
        const bool done=revealed(art,fadeComplete);
        if(done&&!frozen)--messageHold_;
        // A button completes the text; a second one ends the hold.
        if(!frozen&&button) {
            if(done)messageHold_=0;
            else messageFrame_=0x2710;
        }
        animate(objects,0,false);animate(objects,1,false);
    };

    bool fresh=false;
    if(phase_==Phase::Start) {
        const int index=mode==1?players[0].stageIndex:mode==2?players[1].stageIndex:0;
        // 1c4634..1c4678: the CPU never shares the human's colour.
        if(players[h].character!=players[c].character)players[c].colour=0;
        else if(players[h].colour==players[c].colour)players[c].colour=players[h].colour!=0?0:1;
        limit_=0x3c;
        if(index==5||index==6)limit_=run.system().option(3)?0x96:0x78;
        const bool first0=mode==1&&players[0].stageIndex==0,first1=mode==2&&players[1].stageIndex==0;
        object[0]=objects.create(0x1772,0,first0?0x703:0x704,0xf0,0,players[0].colour);
        object[1]=objects.create(0x1772,1,first1?0x703:0x704,0x190,0x80000,players[1].colour);
        // A fighter that starts in the loop action counts as arrived.
        finished_={first0?1:0,first1?1:0};
        delay_={};
        if(mode==1) {if(players[0].stageIndex!=0)delay_[1]=0x1e;}
        else if(mode==2) {if(players[1].stageIndex!=0)delay_[0]=0x1e;}
        // 10add8(0x17, 0), 10add8(0x18, 0), 112f08(8), 112f30(0, 0xffffff): text sheet setup.
        events.voice=t.stageVoices.at(size_t(run.game.stage));
        countdown_=0x3c;
        phase_=Phase::Solo;fresh=true;
    }
    if(phase_==Phase::Solo) {
        if(fresh||countdown_>0) {solo();return events;}
        phase_=Phase::Pair;
    }
    if(phase_==Phase::Message) {
        if(messageHold_>0) {speak();return events;}
        phase_=Phase::Hold;holdVisited_=false;
    }
    if(phase_==Phase::Pair) {
        for(unsigned seat=0;seat<2;++seat) {
            if(delay_[seat]) {if(!frozen)--delay_[seat];}
            else animate(objects,seat,true);
        }
        if(frozen)return events;
        if(button)wait=limit_;
        if(finished_[0]!=1||finished_[1]!=1)return events;
        if(dialogueStage(run)&&run.intruderFight!=1) {
            if(++wait<limit_)return events;
            startHold(run,held);
            if(!exitLatch)request(ArcadeScene::Dialogue);
            return events;
        }
        // The CPU fighter speaks; with the human in seat 1 the balloon is mirrored.
        const int index=mode==1?message(t,language,players[0].character,players[1].character,run.random())
                               :message(t,language,players[1].character,players[0].character,run.random());
        const auto& m=t.messages.at(size_t(index));
        balloon.balloon=m.balloon+(mode==1?0:5);
        balloon.lines=0;
        while(balloon.lines<3&&m.text[size_t(balloon.lines)]>=0)++balloon.lines;
        balloon.text={m.text[0],m.text[1],m.text[2]};
        messageFrame_=0;messageHold_=0xb4;
        phase_=Phase::Message;
        speak();
        return events;
    }
    // Final loop: the text is hidden (limit 0), the balloon stays.
    if(holdVisited_&&!frozen&&!exitLatch)request(ArcadeScene::Battle);
    startHold(run,held);
    balloon.visible=true;balloon.limit=0;
    animate(objects,0,false);animate(objects,1,false);
    holdVisited_=true;
    return events;
}
void ArcadeWalkInScene::draw(const ArcadeMapArt& art,const MenuCanvas& canvas,MenuDrawList& list) const {
    art.ground(canvas,list,frame);
    art.markers(canvas,list,frame.stage);
    art.clouds(canvas,list,frame);
    if(balloon.visible) {
        list.colour=0xffffffffu;
        art.balloon(canvas,list,balloon);
    }
}
}
