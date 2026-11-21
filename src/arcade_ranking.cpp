#include "arcade_ranking.hpp"
#include "arcade_run.hpp"
#include "game_random.hpp"
#include "system_data.hpp"

#include <algorithm>
#include <bit>
#include <cstring>
#include <fstream>
#include <numeric>
#include <stdexcept>
#include <string>

namespace ss6 {
namespace {
constexpr int width=640,height=480;
constexpr int rankSlot=0x08,faceSlot=0x0a,cloudLeftSlot=0x1e,cloudRightSlot=0x2b;
constexpr uint32_t literalBase=0x6632c0;
// Record indices: 4c7c18 + 0x18 * index.
enum Record : unsigned {
    ScoreDigit=0,Filler=10,Prefix=11,Mark=12,ScoreSuffix=13,RankDigit=15,RankSuffix=25,RankSuffixOverseas=26,
    TopRank=27,TopRankOverseas=30,ScoreHeader=33,StreakHeader=35,FrameFront=37,FrameBack=38,StreakSuffix=39,
    Spirit=41,CloudLeft=58,CloudRight=59
};

std::vector<uint8_t> load(const std::filesystem::path& file,size_t size) {
    std::ifstream in(file,std::ios::binary|std::ios::ate);
    if(!in||in.tellg()!=static_cast<std::streamoff>(size))
        throw std::runtime_error("Invalid ranking resource: "+file.string());
    std::vector<uint8_t> bytes(size);
    in.seekg(0);
    if(!in.read(reinterpret_cast<char*>(bytes.data()),std::streamsize(size)))
        throw std::runtime_error("Truncated ranking resource: "+file.string());
    return bytes;
}
std::vector<uint8_t> unpack4(const std::vector<uint8_t>& packed) {
    std::vector<uint8_t> out(packed.size()*2);
    for(size_t i=0;i<packed.size();++i) {out[2*i]=packed[i]&15;out[2*i+1]=packed[i]>>4;}
    return out;
}
ScalarFloat scalar(float v) {return ScalarFloat{std::bit_cast<uint32_t>(v)};}
float real(ScalarFloat v) {return std::bit_cast<float>(v.bits);}
int32_t clampByte(int32_t v) {return v>255?255:v<0?0:v;}
// 1ea730(a, r, g, b): AARRGGBB with every channel clamped to 0..255.
uint32_t colour(int32_t a,int32_t r,int32_t g,int32_t b) {
    return uint32_t(clampByte(a))<<24|uint32_t(clampByte(r))<<16|uint32_t(clampByte(g))<<8|uint32_t(clampByte(b));
}
// 1ea460(n, k): the k-th decimal digit from the right, signed division.
int32_t digit(int32_t n,int k) {
    for(int i=1;i<k;++i)n/=10;
    return n%10;
}
// 108118 (10849c..108514): texel coordinates above size-1 become size-1.
void clampSpan(MenuDrawRecord& r,int size) {
    const float limit=float(size-1);
    const float u1=std::min(r.u+r.uw,limit),v1=std::min(r.v+r.vh,limit);
    r.u=std::min(r.u,limit);r.v=std::min(r.v,limit);r.uw=u1-r.u;r.vh=v1-r.v;
}
void mix(uint8_t* dst,const int* source) {
    for(int c=0;c<3;++c)dst[c]=uint8_t(std::clamp(dst[c]+(((source[c]-dst[c])*source[3])>>7),0,255));
}
}

ArcadeRankingArt::ArcadeRankingArt(const std::filesystem::path& assets) {
    constexpr size_t size=8+60*24+93*4+20+512+1024+1024+64+52*64;
    const auto raw=load(assets/"arcade_ranking.bin",size);
    if(std::memcmp(raw.data(),"RNKA\1\0\0\0",8))throw std::runtime_error("Mismatched arcade_ranking.bin");
    size_t at=8;
    const auto take=[&](void* to,size_t n) {std::memcpy(to,raw.data()+at,n);at+=n;};
    take(records_.data(),sizeof records_);take(floats_.data(),sizeof floats_);
    take(&mapSlot_,4);take(mapRect_.data(),16);take(glyphs_.data(),512);
    take(rankColours_.data(),1024);take(mapColours_.data(),1024);take(cloudColours_.data(),64);
    take(faceColours_.data(),sizeof faceColours_);
    // rank_obj and map_main hold 8-bit indices; rank_obj appends its CLUT.
    rank_={512,512,load(assets/"rank_obj.tex",512*512+1024)};rank_.indices.resize(512*512);
    map_={1024,1024,load(assets/"map_main.tex",1024*1024)};
    cloudLeft_={512,512,unpack4(load(assets/"cloud_l.tex",512*256))};
    cloudRight_={512,512,unpack4(load(assets/"cloud_r.tex",512*256))};
    face_={512,512,unpack4(load(assets/"face.tex",512*256))};
}

ScalarFloat ArcadeRankingArt::literal(uint32_t address) const {
    if(address==0x66357c)return ScalarFloat{floats_[90]};
    if(address==0x5df490)return ScalarFloat{floats_[91]};
    if(address==0x5df494)return ScalarFloat{floats_[92]};
    const uint32_t index=(address-literalBase)/4;
    if(address<literalBase||index>=90||address%4)throw std::invalid_argument("Unknown ranking literal");
    return ScalarFloat{floats_[index]};
}

RankingTable ArcadeRankingArt::table(const SystemData& system) const {
    RankingTable t;
    const auto image=system.image();
    const size_t streaks=SystemData::ranking,scores=SystemData::ranking+0x28;
    t.overseas=system.setting(2)!=0;
    const auto word=[&](size_t at) {int32_t v;std::memcpy(&v,image.data()+at,4);return v;};
    for(int i=0;i<5;++i) {
        auto& r=t.rows[size_t(i)];
        const size_t at=streaks+8*size_t(i);
        r={i,word(at),image[at+5],image[at+4],{}};
    }
    for(int i=0;i<20;++i) {
        auto& r=t.rows[size_t(5+i)];
        const size_t at=scores+12*size_t(i);
        r={i,word(at),image[at+9],image[at+4],{}};
        // 1ea578 + strcpy: two SJIS bytes per character up to the first NUL,
        // which the original searches for past the four name bytes.
        size_t n=0;
        for(size_t p=at+5;p<image.size()&&image[p];++p) {
            const auto& code=glyphs_[image[p]];
            if(!code[0]||n+2>=r.name.size())throw std::invalid_argument("Ranking name byte without a ported glyph");
            r.name[n++]=code[0];r.name[n++]=code[1];
        }
    }
    return t;
}

bool ArcadeRankingArt::bezier(std::array<ScalarFloat,2>& out,unsigned at,int steps,int t) const {
    if(steps<=0||t<0||t>=steps)return false;  // out is left as it was
    // Operation order of 1ea4a8; MULA / MADDA / MADD round each product and sum.
    const auto one=literal(0x663420),three=literal(0x663424);
    const auto f0=one.div(ScalarFloat::integer(steps-1));
    const auto f4=ScalarFloat::integer(t).mul(f0),f5=one.sub(f4);
    for(unsigned k=0;k<2;++k) {
        const auto p=[&](unsigned i) {return literal(literalBase+4*(at+i+k));};
        auto a=p(0).mul(f5),b=p(2).mul(three),c=p(4).mul(three),d=p(6);
        b=b.mul(f4);c=c.mul(f4);d=d.mul(f4);
        a=a.mul(f5);b=b.mul(f5);c=c.mul(f4);d=d.mul(f4);
        auto acc=a.mul(f5);
        acc=acc.add(b.mul(f5));
        acc=acc.add(c.mul(f5));
        out[k]=acc.add(d.mul(f4));
    }
    return true;
}

// 117a00(record, record.flags, 3db900, x, y, z).
void ArcadeRankingArt::picture(const MenuCanvas& canvas,MenuDrawList& list,unsigned index,int x,int y,float z) const {
    const auto& r=records_.at(index);
    const size_t before=list.records.size();
    canvas.picture(list,{r.u,r.v,r.w,r.h},r.slot,unsigned(r.flags),list.colour,float(x),float(y),z);
    if(list.records.size()!=before)clampSpan(list.records.back(),512);
}

// 1ea3d8 -> 113be0: the whole 1024x818 map at (x, y), scaled, at the plain
// depth-counter value (114d78, no 10000000 bias) and with the unfaded 3db900.
void ArcadeRankingArt::map(const MenuCanvas& canvas,MenuDrawList& list,int x,int y,ScalarFloat scale) const {
    const int h=scale.mul(literal(0x663418)).truncate(),w=scale.mul(literal(0x66341c)).truncate();
    const int depth=list.depth;
    const size_t before=list.records.size();
    // Slot 0x28 is the one 113f98 path without the 117288 fade; the record
    // then takes the map slot and the counter depth of 113be0.
    canvas.sprite(list,0x28,float(x),float(y),0,float(w),float(h),std::bit_cast<float>(mapRect_[0]),
                  std::bit_cast<float>(mapRect_[1]),std::bit_cast<float>(mapRect_[2]),std::bit_cast<float>(mapRect_[3]));
    if(list.records.size()==before)return;
    auto& q=list.records.back();
    q.slot=uint8_t(mapSlot_);q.z=float(depth);
    clampSpan(q,1024);
}

// 1e9870: rear frame, 122ab8 face, front frame.
void ArcadeRankingArt::face(const MenuCanvas& canvas,MenuDrawList& list,int character,int x,int y) const {
    picture(canvas,list,FrameBack,x,y,real(literal(0x6633f0)));
    if(character<0||character>=int(faceColours_.size()))throw std::invalid_argument("Ranking face character outside the ported CLUTs");
    // 122ab8: 64x64 cell (character % 8, character / 8) of slot 0xa at (x - 28, y - 28).
    const auto size=literal(0x5df490),offset=literal(0x5df494);
    const auto fx=ScalarFloat::integer(x+0x1c).sub(offset),fy=ScalarFloat::integer(y+0x1c).sub(offset);
    const auto u=ScalarFloat::integer(character%8).mul(size),v=ScalarFloat::integer(character/8).mul(size);
    const size_t before=list.records.size();
    canvas.sprite(list,faceSlot,real(fx),real(fy),real(literal(0x6633f4)),real(size),real(size),real(u),real(v),real(size),real(size));
    if(list.records.size()!=before) {list.records.back().glyph=uint16_t(character);clampSpan(list.records.back(),512);}
    picture(canvas,list,FrameFront,x,y,real(literal(0x6633f8)));
}

// 1e99c0 (streak rows) and the part of 1e9c40 after its colour prologue.
void ArcadeRankingArt::ordinal(const MenuCanvas& canvas,MenuDrawList& list,int x,int y,int index,bool overseas,float z) const {
    if(index<3) {
        // The overseas record keeps the flags word of the Japanese record (lw -0x38).
        const auto& r=records_.at(unsigned((overseas?TopRankOverseas:TopRank)+index));
        const size_t before=list.records.size();
        canvas.picture(list,{r.u,r.v,r.w,r.h},r.slot,unsigned(records_.at(unsigned(TopRank+index)).flags),
                       list.colour,float(x+9),float(y-12),z);
        if(list.records.size()!=before)clampSpan(list.records.back(),512);
        return;
    }
    int drawn=0;bool seen=false;
    for(int k=2,at=x;k>0;--k,at+=0x18) {
        const int d=digit(index+1,k);
        if(d<0)throw std::invalid_argument("Negative ranking ordinal");
        if(!d&&!seen)continue;
        seen=true;++drawn;
        picture(canvas,list,unsigned(RankDigit+d),overseas?at+0x20:at,y,z);
    }
    if(!overseas)picture(canvas,list,RankSuffix,x+0x30,y,z);
    else {
        const int t=2-drawn;
        picture(canvas,list,RankSuffixOverseas,t==1?x+0x13:x+t*0x18,y-5,z);
    }
}

// 1e9768: ordinal (1e99c0), streak (1e9f98), face (1e9870).
void ArcadeRankingArt::streakRow(const MenuCanvas& canvas,MenuDrawList& list,const RankingDisplayRow& row,int x,int y,
                                 bool overseas) const {
    ordinal(canvas,list,x+0x10,y+0xc,row.index,overseas,real(literal(0x663400)));
    const float z=real(literal(0x663408));
    const int left=x+0xd8;
    picture(canvas,list,Prefix,left-10,y,z);
    // Seven positions: the upper four are always the filler record.
    for(int k=7,at=left;k>0;--k,at+=0x20) {
        const int d=digit(row.value,k);
        if(k<4&&d<0)throw std::invalid_argument("Negative ranking streak");
        picture(canvas,list,k>=4?unsigned(Filler):unsigned(ScoreDigit+d),at,y,z);
    }
    picture(canvas,list,unsigned(StreakSuffix+overseas),left+0xe0,y,z);
    picture(canvas,list,Mark,left+0x120,y-7,z);
    face(canvas,list,row.character,x+0x75,y-4);
}

// 1e97d8: rank (1e9c40), spirit (1e9958), score (1ea160), name (1ea2e8), face.
void ArcadeRankingArt::scoreRow(const MenuCanvas& canvas,MenuDrawList& list,const RankingDisplayRow& row,int x,int y,
                                bool overseas,int32_t highlight,RankingPulse pulse) const {
    const uint32_t saved=list.colour;
    if(highlight==row.index) {
        // 1e9c40 replaces RGB by a grey derived from the blue byte of 3db900.
        const int32_t level=pulse.level(int32_t(list.colour&255));
        list.colour=colour(int32_t(list.colour>>24),level,level,level);
    }
    ordinal(canvas,list,x+8,y+0xc,row.index,overseas,real(literal(0x663404)));
    list.colour=saved;
    const float z=real(literal(0x6633fc));
    const unsigned spirit=unsigned(row.spirit+(overseas?6:0));
    if(row.spirit<0||Spirit+spirit>=CloudLeft)throw std::invalid_argument("Ranking spirit outside the record table");
    picture(canvas,list,Spirit+spirit,x+0xb0,y,z);
    const float zs=real(literal(0x66340c));
    const int left=x+0xfa;
    picture(canvas,list,Prefix,left-10,y,zs);
    for(int k=7,at=left;k>0;--k,at+=0x20) {
        const int d=digit(row.value,k);
        if(d<0)throw std::invalid_argument("Negative ranking score");
        picture(canvas,list,unsigned(ScoreDigit+d),at,y,zs);
    }
    picture(canvas,list,unsigned(ScoreSuffix+overseas),left+0xe0,y,zs);
    picture(canvas,list,Mark,left+0xf8,y-7,zs);
    // 113028 -> 1130f8 -> 10a1c0: Goth24 glyphs at the depth 114e40(3d3aac).
    const int savedDepth=list.textDepth;
    list.textDepth=int(real(scalar(10000000.0f).sub(scalar(list.asciiDepth).mul(scalar(100.0f)))));
    const auto c=list.colour;
    const auto name=reinterpret_cast<const char*>(row.name.data());
    canvas.text24(list,std::string_view(name,strnlen(name,row.name.size())),x+0x217,y+0xc,
                  int((c>>16)&255),int((c>>8)&255),int(c&255),int(c>>24));
    list.textDepth=savedDepth;
    face(canvas,list,row.character,x+0x6e,y-4);
}

void ArcadeRankingArt::draw(const MenuCanvas& canvas,MenuDrawList& list,const RankingFrame& frame,const RankingTable& table,
                            int32_t highlight,RankingPulse pulse) const {
    // 1e8b38: blend 1, white 3db900 for the callback, 3db900 restored after it.
    const uint32_t saved=list.colour;
    list.blend=1;list.colour=0xffffffffu;
    const int t=int(frame.tick);
    const bool ov=table.overseas;
    const auto header=[&](unsigned base,int x,int y) {picture(canvas,list,base+ov,x,y,real(literal(base==StreakHeader?0x663410:0x663414)));};
    std::array<ScalarFloat,2> p{ScalarFloat{0},ScalarFloat{0}};
    switch(frame.phase) {
    case 2:case 4:   // 1e8c88 / 1e8f78: the streak header drops in / leaves
        bezier(p,frame.phase==2?0:(0x663370-literalBase)/4,60,t);
        header(StreakHeader,160,p[1].truncate()+24);
        break;
    case 3: {        // 1e8d00
        const int stage=t<120?0:t<240?1:2;
        const int age0=stage==0?t:stage==1?0:t-240;
        header(StreakHeader,160,24);
        for(int i=0;i<5;++i) {
            const int age=std::min(std::max(age0-(4-i)*12,0),59);
            uint32_t strip;
            if(stage==1) {strip=colour(128,255,255,255);p[1]=ScalarFloat{0};}
            else {
                const auto fade=ScalarFloat::integer(age).mul(literal(0x663360));
                strip=colour(stage==0?fade.truncate():literal(0x663364).sub(fade).truncate(),255,255,255);
                const uint32_t table=stage==0?(i&1?0x663300:0x6632e0):(i&1?0x663340:0x663320);
                bezier(p,(table-literalBase)/4,60,age);
            }
            const int x=p[1].truncate()+40;
            canvas.rectangle(list,0,72*i+100,640,40,strip,real(literal(0x663368)));
            streakRow(canvas,list,table.rows.at(frame.firstRow+unsigned(i)),x,72*i+96,ov);
        }
        break;
    }
    case 6:          // 1e90a8: white fade over the battle
        canvas.rectangle(list,0,0,640,480,colour(4*t,255,255,255),real(literal(0x66357c)));
        break;
    case 7:          // 1e9140 after the optical loads
        canvas.rectangle(list,0,0,640,480,colour(255,255,255,255),real(literal(0x66357c)));
        break;
    case 8: {        // 1e91a0: map and clouds, then the map zooms in
        const float cy=real(literal(0x6633d0)),cz=real(literal(0x6633d4));
        const auto cloud=[&](unsigned index,float x) {
            const auto& r=records_[index];
            const size_t before=list.records.size();
            canvas.picture(list,{r.u,r.v,r.w,r.h},r.slot,unsigned(r.flags),list.colour,x,cy,cz);
            if(list.records.size()!=before)clampSpan(list.records.back(),512);
        };
        if(t<60) {
            map(canvas,list,0,0,literal(0x6633d8));
            cloud(CloudLeft,0);cloud(CloudRight,real(literal(0x6633dc)));
            canvas.rectangle(list,0,0,640,480,colour(255,255,255,255),real(literal(0x66357c)));
        } else if(t<180) {
            const int age=std::min(t-60,119);
            bezier(p,(0x663390-literalBase)/4,120,age);
            map(canvas,list,0,0,literal(0x6633d8));
            list.colour=colour(p[0].truncate(),255,255,255);
            const int dx=p[1].truncate();
            cloud(CloudLeft,float(-dx));cloud(CloudRight,float(dx+0xa0));
            canvas.rectangle(list,0,0,640,480,colour(255-4*age,255,255,255),real(literal(0x66357c)));
        } else {
            const int age=std::min(t-180,119);
            std::array<ScalarFloat,2> q{ScalarFloat{0},ScalarFloat{0}};
            bezier(q,(0x6633b0-literalBase)/4,60,age);
            const auto hundred=literal(0x6633e0);
            // 1e9418: the position term is multiplied by zero before truncation.
            const int xy=q[0].div(hundred).mul(ScalarFloat{0}).truncate();
            map(canvas,list,xy,xy,q[1].div(hundred));
        }
        break;
    }
    case 9:          // 1e9438: zoomed map, score header fades in
        map(canvas,list,0,0,literal(0x6633e4));
        list.colour=colour(5*t,255,255,255);
        header(ScoreHeader,160,24);
        break;
    case 10: {       // 1e94d0: score rows scroll up
        const auto layout=frame.rowLayout();
        const int elapsed=t-72*(19-int(frame.firstRow));
        const int brightness=elapsed>72&&elapsed>=300?1455-4*elapsed:255;
        list.colour=colour(255,brightness,brightness,brightness);
        // 1e9580: the diagonal scroll restarts at zero once it passes -462.
        const auto scroll=ScalarFloat::integer(-(t>>2));
        const int offset=scroll.less(literal(0x6633e8))?0:scroll.truncate();
        map(canvas,list,offset,offset,literal(0x6633ec));
        header(ScoreHeader,160,24);
        for(unsigned i=0;i<layout.count;++i) {
            const auto& r=layout.rows[i];
            list.colour=colour(r.alpha,brightness,brightness,brightness);
            scoreRow(canvas,list,table.rows.at(5+r.index),r.x,r.y,ov,highlight,pulse);
        }
        break;
    }
    default:break;   // 0, 1, 5: no draw (1 and 5 fade the battle CLUTs); 11, 12: none
    }
    list.colour=saved;
}

void ArcadeRankingArt::rasterise(const MenuCanvas& canvas,const MenuDrawList& list,std::span<uint8_t> rgba) const {
    if(rgba.size()!=size_t(width)*height*4)throw std::invalid_argument("Expected a 640x480 ranking surface");
    std::vector<unsigned> order(list.records.size());
    std::iota(order.begin(),order.end(),0u);
    std::stable_sort(order.begin(),order.end(),[&](unsigned a,unsigned b) {return list.records[a].z<list.records[b].z;});
    MenuDrawList pending;
    const auto flush=[&] {
        if(pending.records.empty())return;
        canvas.rasterise(pending,rgba);pending.records.clear();
    };
    const auto integral=[](float value) {
        if(value!=float(int(value))||value<-32768||value>32768)throw std::invalid_argument("Ranking quad needs integral geometry");
        return int(value);
    };
    for(const unsigned at:order) {
        const auto& q=list.records[at];
        const Sheet* sheet=nullptr;const Colour* clut=nullptr;
        if(q.kind==MenuPrimitive::Quad) {
            if(q.slot==rankSlot) {sheet=&rank_;clut=rankColours_.data();}
            else if(q.slot==mapSlot_) {sheet=&map_;clut=mapColours_.data();}
            else if(q.slot==cloudLeftSlot) {sheet=&cloudLeft_;clut=cloudColours_.data();}
            else if(q.slot==cloudRightSlot) {sheet=&cloudRight_;clut=cloudColours_.data();}
            else if(q.slot==faceSlot) {sheet=&face_;clut=faceColours_.at(q.glyph).data();}
        }
        if(!sheet) {pending.records.push_back(q);continue;}
        flush();
        const int x=integral(q.x),y=integral(q.y),w=integral(q.w),h=integral(q.h);
        const int u=integral(q.u),v=integral(q.v),uw=integral(q.uw),vh=integral(q.vh);
        if(w<=0||h<=0)continue;
        int mod[4];
        for(int c=0;c<4;++c)mod[c]=int((q.colour>>(8*c))&255);
        for(int py=std::max(0,y);py<std::min(height,y+h);++py) {
            const int tv=std::clamp(v+((2*(py-y)+1)*vh)/(2*h),0,sheet->h-1);
            for(int px=std::max(0,x);px<std::min(width,x+w);++px) {
                const int tu=std::clamp(u+((2*(px-x)+1)*uw)/(2*w),0,sheet->w-1);
                const auto& texel=clut[sheet->indices[size_t(tv)*size_t(sheet->w)+size_t(tu)]];
                int source[4];
                for(int c=0;c<4;++c)source[c]=std::min(255,texel[size_t(c)]*mod[c]/128);
                auto* dst=rgba.data()+4*(size_t(py)*width+size_t(px));
                if(q.additive)for(int c=0;c<3;++c)dst[c]=uint8_t(std::min(255,dst[c]+source[c]));
                else mix(dst,source);
            }
        }
    }
    flush();
}

RankingDemoMatch ArcadeRanking::enter(const ArcadeRankingArt& art,const SystemData& system,GameRandom& random,
                                      int32_t highlightRow,uint32_t held) {
    const auto demo=selectRankingDemo(random,held);
    control=ConsoleAttractRanking{};
    table=art.table(system);
    highlight=highlightRow;
    pulse=drawPulse=RankingPulse{};
    return demo;
}

RankingDestination ArcadeRanking::tick(bool startPressed,bool& alternateDemo) {
    const auto destination=control.tick(startPressed,alternateDemo,table.overseas);
    drawPulse=pulse;
    // 1e9c40 steps the pulse whenever it draws the highlighted row.
    if(control.draw.phase==10) {
        const auto layout=control.draw.rowLayout();
        for(unsigned i=0;i<layout.count;++i)
            if(int32_t(layout.rows[i].index)==highlight) {pulse.advance();break;}
    }
    return destination;
}

void ArcadeRanking::leave(ArcadeRun& run) {run.rankingHighlight=-1;}
}
