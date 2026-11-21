#include "arcade_results.hpp"
#include "scalar_float.hpp"
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
constexpr int width=640,height=480;
constexpr int boardSlot=4,faceSlot=5,portraitSlot=8,digitSlot=0x0c,coinSlot=0x28;
constexpr uint32_t white=0xffffffffu;

std::vector<uint8_t> load(const std::filesystem::path& file,size_t size) {
    std::ifstream in(file,std::ios::binary|std::ios::ate);
    if(!in||(size&&in.tellg()!=static_cast<std::streamoff>(size)))
        throw std::runtime_error("Invalid arcade result resource: "+file.string());
    std::vector<uint8_t> bytes(size_t(in.tellg()));
    in.seekg(0);
    if(!in.read(reinterpret_cast<char*>(bytes.data()),std::streamsize(bytes.size())))
        throw std::runtime_error("Truncated arcade result resource: "+file.string());
    return bytes;
}
ScalarFloat sf(float v) {return ScalarFloat{std::bit_cast<uint32_t>(v)};}
float real(ScalarFloat v) {return std::bit_cast<float>(v.bits);}
float mul(float a,float b) {return real(sf(a).mul(sf(b)));}
float fl(int32_t v) {return real(ScalarFloat::integer(v));}
int trunc(float v) {return sf(v).truncate();}
MenuSheetRect rect(const ArcadeResultRecord& r) {return {r.u,r.v,r.w,r.h};}
int sheetSize(int slot) {return slot==boardSlot||slot==faceSlot?1024:512;}

// 108118 (10849c..108514, word 3db908 != 1): vertex texels above size-1 are
// replaced by size-1. Applies to the last record of the list.
void clampSpan(MenuDrawRecord& r) {
    const float limit=float(sheetSize(r.slot)-1);
    const float u1=std::min(r.u+r.uw,limit),v1=std::min(r.v+r.vh,limit);
    r.u=std::min(r.u,limit);r.v=std::min(r.v,limit);r.uw=u1-r.u;r.vh=v1-r.v;
}
// 117de8 for the sheets of this module; 10add8 keeps `flags & ~0x200` as the
// CLUT bank of the 4-bit sheet in slot 0xc.
void sheet(const MenuCanvas& canvas,MenuDrawList& list,const ArcadeResultRecord& r,unsigned flags,uint32_t colour,
           float x,float y,float z,float w,float h,bool clamp=true) {
    const size_t before=list.records.size();
    canvas.sprite(list,rect(r),r.slot,flags,colour,false,x,y,z,w,h);
    if(list.records.size()==before)return;
    auto& q=list.records.back();
    if(q.slot==digitSlot)q.glyph=uint16_t(flags&0xffu&~0x200u);
    if(clamp)clampSpan(q);
}
// 1149d0 colour word of 3db900 without the 117288 fade (slot 0x28 is the one
// path of the public 113f98 emitter that skips it).
uint32_t queueColour(const MenuCanvas& canvas,MenuDrawList& list) {
    const int depth=list.depth;
    canvas.sprite(list,coinSlot,0,0,0,1,1,0,0,1,1);
    const uint32_t colour=list.records.back().colour;
    list.records.pop_back();list.depth=depth;
    return colour;
}
// 113f98 with the far corners kept as the EE sums x + w / y + h (the quad
// record would re-add them in host arithmetic). Emits a Rotated record.
void spriteExact(const MenuCanvas& canvas,MenuDrawList& list,int slot,float x,float y,float z,float w,float h,
                 float u,float v,float uw,float vh) {
    const size_t before=list.records.size();
    canvas.sprite(list,slot,x,y,z,w,h,u,v,uw,vh);
    if(list.records.size()==before)return;
    auto& q=list.records.back();
    const float x1=eeAdd(x,w),y1=eeAdd(y,h);
    q.kind=MenuPrimitive::Rotated;
    q.corner={x,y,x,y1,x1,y,x1,y1};
    clampSpan(q);
}
// 114118: textured quad through four explicit corners; texel (u,v) at P0,
// (u,v+vh) at P1, (u+uw,v) at P2 and (u+uw,v+vh) at P3. Colour 3db900 as it
// stands (no 117288 fade), blend 3db8fc.
void quad4(const MenuCanvas& canvas,MenuDrawList& list,int slot,float x0,float y0,float x1,float y1,float x2,float y2,
           float x3,float y3,float z,float u,float v,float uw,float vh) {
    // 114f20: the left test reads y3 in place of x3 (original defect, kept).
    if((x0<0&&x1<0&&x2<0&&y3<0)||(640.0f<x0&&640.0f<x1&&640.0f<x2&&640.0f<x3)||
       (y0<0&&y1<0&&y2<0&&y3<0)||(480.0f<y0&&480.0f<y1&&480.0f<y2&&480.0f<y3))return;
    MenuDrawRecord r;
    r.kind=MenuPrimitive::Rotated;r.slot=uint8_t(slot);r.blend=uint8_t(list.blend);r.additive=list.additive;
    r.colour=queueColour(canvas,list);r.z=canvas.depth(list,z);
    r.corner={x0,y0,x1,y1,x2,y2,x3,y3};
    r.u=u;r.v=v;r.uw=uw;r.vh=vh;r.x=x0;r.y=y0;r.w=x2-x0;r.h=y1-y0;
    clampSpan(r);
    list.records.push_back(r);
}
// 113028(text, x, y, ffffffff) under the reveal limit 3d3aa0 (counter 3d3ab0).
// Returns the number of characters submitted.
void revealLine(const MenuCanvas& canvas,MenuDrawList& list,const std::string& line,int x,int y,int limit,int& counter) {
    for(size_t i=0;i<line.size();) {
        const size_t n=uint8_t(line[i])<0x80?1:2;
        if(limit>=0&&counter>=limit)return;
        canvas.text24(list,std::string_view(line).substr(i,n),x,y,255,255,255,255);
        ++counter;
        x+=n==1?12:24;i+=n;
    }
}
int textDepth(const MenuDrawList& list) {
    // 114e40(3d3aac): the depth conversion without the tie-break increment.
    return int(real(sf(10000000.0f).sub(sf(list.asciiDepth).mul(sf(100.0f)))));
}
// 1c1528: one pulsing frame edge; the shared counter moves once per edge.
void edge(const MenuCanvas& canvas,MenuDrawList& list,int x,int y,int w,int h,uint32_t first,uint32_t second,
          ArcadeEdgePulse& pulse,int period,float z) {
    const uint32_t alpha=((first>>24)+(second>>24))>>1;
    pulse.counter+=pulse.reverse?-1:1;
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
    canvas.rectangle(list,x,y,w,h,alpha<<24|r<<16|g<<8|b,z);
}
int lineCount(const std::string& text) {return 1+int(std::count(text.begin(),text.end(),'\n'));} // 1e2950
bool same(const std::array<char,4>& glyph,const char* text) {return std::strncmp(glyph.data(),text,4)==0;}
}

// ---------------------------------------------------------------------
ArcadeResultsTables::ArcadeResultsTables(const std::filesystem::path& assets) {
    const auto raw=load(assets/"arcade_results.bin",0);
    if(raw.size()<8||std::memcmp(raw.data(),"ARES\1\0\0\0",8))throw std::runtime_error("Mismatched arcade_results.bin");
    size_t at=8;
    const auto take=[&](void* to,size_t n) {
        if(at+n>raw.size())throw std::runtime_error("Truncated arcade_results.bin");
        std::memcpy(to,raw.data()+at,n);at+=n;
    };
    static_assert(sizeof(ArcadeResultRecord)==24);
    take(backgroundFloats.data(),28);take(rows.data(),11*10*24);take(&picture,24);
    take(quoteFloats.data(),92);take(resultEntry.data(),28);take(resultFloats.data(),24);take(resultShake.data(),64);
    take(faceFloats.data(),20);take(resultDigits.data(),240);take(&resultDigitBefore,24);take(&resultLabel,24);take(&resultMark,24);
    take(faces.data(),312);take(banner.data(),48);take(bannerFloats.data(),12);
    take(entryDigits.data(),240);take(&entryBack,24);take(&entryEnd,24);take(entryFloats.data(),16);
    take(unlockFloats.data(),12);
    for(auto& text:unlockTexts) {
        uint16_t n;take(&n,2);
        text.resize(n);take(text.data(),n);
    }
    for(auto& table:quotes)for(auto& character:table)for(auto& quote:character) {
        uint8_t lines;take(&lines,1);
        if(lines>3)throw std::runtime_error("Invalid quote record");
        quote.resize(lines);
        for(auto& line:quote) {
            uint8_t n;take(&n,1);
            line.resize(n);take(line.data(),n);
        }
    }
    if(at!=raw.size())throw std::runtime_error("Unexpected trailing data in arcade_results.bin");
}
const ArcadeResultsTables::Quote* ArcadeResultsTables::quote(const SystemData& system,int character,int index) const {
    if(character<0||character>=0x31||character==0x2b||index<0||index>=16)return nullptr;
    const auto& q=quotes[system.setting(2)!=0][size_t(character)][size_t(index)];
    return q.empty()?nullptr:&q;
}

// --- unlock predicates ------------------------------------------------
int unlockEndingCount(const SystemData& system) {
    int n=0;
    for(unsigned i=0;i<0x31;++i)n+=system.option(0x47+i)!=0;
    return n;
}
int unlockSpiritCount(const SystemData& system) {
    int n=0;
    for(unsigned i=0;i<9;++i)n+=system.option(0x81+i)!=0;
    return n;
}
bool unlockPredicate(unsigned index,const SystemData& system,const UnlockSessionFlags& session,int endings,int spirits,int force) {
    const auto o=[&](size_t offset) {return int(system.option(offset));};
    // g_GameOption+90: more than 0x2bf1f unlocks everything.
    const bool total=uint32_t(system.word(SystemData::gameOption+0x90))>0x2bf1fu;
    // Lock bytes +3e..+46 are nonzero while the fighter is locked.
    const auto locked=[&](size_t lock) {return o(lock)!=0||force==1;};
    // Flag bytes are nonzero once the item is unlocked.
    const auto missing=[&](size_t flag) {return o(flag)==0||force==1;};
    const bool base=o(0x40)==0&&o(0x3e)==0&&o(0x3f)==0; // fighters 2a, 28 and 29 are available
    // 1e3ed0 / 1e3790: all four of +65..+68 with +7f lower the ending threshold.
    const auto spiritRule=[&] {
        const bool four=o(0x65)&&o(0x66)&&o(0x67)&&o(0x68);
        return endings>=(four&&o(0x7f)?0x18:0x20)||spirits>=8||total;
    };
    switch(index) {
    case 0:return locked(0x40)&&(o(0x48)!=0||endings>=3||session[0]!=0||total);
    case 1:return locked(0x3f)&&(o(0x4b)!=0||endings>=6||session[1]!=0||total);
    case 2:return locked(0x3e)&&(o(0x51)!=0||endings>=9||session[2]!=0||total);
    case 3:return locked(0x42)&&((base&&o(0x4b)!=0)||session[3]!=0||total);
    case 4:return locked(0x43)&&((base&&o(0x5a)!=0)||session[4]!=0||total);
    case 5:return locked(0x45)&&((base&&o(0x56)!=0&&o(0x69)!=0)||session[5]!=0||total);
    case 6:return locked(0x44)&&((base&&o(0x5f)==1)||session[6]!=0||total);
    case 7:return locked(0x46)&&(endings>=(o(0x6e)&&o(0x7e)?0x20:0x28)||session[7]!=0||total);
    case 8:return missing(0x80)&&((o(0x73)==1&&(uint32_t(system.word(SystemData::gameOption+0x74))&0xffffffu)==0x010101u)||total);
    case 9: {
        if(!missing(0x7f))return false;
        // 1e3e88: at least one of the fighters 2c, 2d, 2f, 2e is no longer locked.
        const bool any=!(o(0x42)&&o(0x43)&&o(0x45)&&o(0x44));
        const bool four=o(0x52)&&o(0x62)&&o(0x54)&&o(0x61);
        return endings>=(four&&any?0x10:0x18)||total;
    }
    case 10:return missing(0x7e)&&spiritRule();
    case 11:return missing(0x95)&&(endings==0x30||total);
    case 12:return missing(0x8a)&&(endings==1||total);
    case 13:return missing(0x8b)&&spiritRule();
    case 14:return missing(0x8c)&&(endings==1||total);
    case 15:return missing(0x94)&&(endings==0x30||total);
    }
    throw std::out_of_range("Unlock predicate index");
}
void unlockSetter(unsigned index,SystemData& system,int value) {
    // Entries 0..7 clear a lock byte, the others raise a flag byte.
    constexpr std::array<uint8_t,16> offset={0x40,0x3f,0x3e,0x42,0x43,0x45,0x44,0x46,0x80,0x7f,0x7e,0x95,0x8a,0x8b,0x8c,0x94};
    const bool unlocked=value==1;
    system.option(offset.at(index))=index<8?!unlocked:unlocked;
}
void unlockRecompute(SystemData& system,const UnlockSessionFlags& session) {
    const int endings=unlockEndingCount(system),spirits=unlockSpiritCount(system);
    for(unsigned i=0;i<16;++i)unlockSetter(i,system,unlockPredicate(i,system,session,endings,spirits,1));
}
bool unlockPending(const SystemData& system,const UnlockSessionFlags& session) {
    const int endings=unlockEndingCount(system),spirits=unlockSpiritCount(system);
    for(unsigned i=0;i<16;++i)if(unlockPredicate(i,system,session,endings,spirits,0))return true;
    return false;
}
std::vector<int> unlockCollect(SystemData& system,const UnlockSessionFlags& session) {
    const int endings=unlockEndingCount(system),spirits=unlockSpiritCount(system);
    std::vector<int> out;
    for(unsigned i=0;i<16;++i)
        if(unlockPredicate(i,system,session,endings,spirits,0)) {unlockSetter(i,system,1);out.push_back(int(i));}
    return out;
}

// --- background 135438 / 135de0 ----------------------------------------
void drawResultBackground(const MenuCanvas& canvas,MenuDrawList& list,const ArcadeResultsTables& t,int variant,int frame) {
    const auto& c=t.backgroundFloats;
    if(variant==1) {
        sheet(canvas,list,t.picture,unsigned(t.picture.flags),white,0,0,c[6],fl(t.picture.w),fl(t.picture.h));
        return;
    }
    if(variant!=0)return;
    // Each band scrolls by a fraction of the frame counter and rotates its
    // ten records by the whole tile steps. Records with flag 0x100 are holes.
    const auto band=[&](unsigned row,int period,float rate,bool negate,float y) {
        const auto& records=t.rows[row];
        const int q=frame/period,r=frame%period;
        const int shift=negate?trunc(-fl(r)):trunc(mul(fl(r),rate));
        const unsigned start=unsigned(q)%10u;
        for(unsigned i=0;i<10;++i) {
            const auto& rec=records[(i+start)%10];
            sheet(canvas,list,rec,unsigned(rec.flags),white,fl(records[0].w*int(i)+shift),y,c[2],fl(records[i].w),fl(records[i].h));
        }
    };
    list.colour=white;list.blend=0;
    band(0,ScalarFloat::integer(t.rows[0][0].w).div(sf(c[0])).truncate(),c[1],false,0);
    list.blend=1;
    const int period=sf(fl(t.rows[1][0].w)).div(sf(c[3])).truncate();
    int y=0;
    for(unsigned row=1;row<=6;++row) {
        band(row,period,c[4],false,fl(y));
        y+=t.rows[row][0].h;
    }
    const int tile=trunc(fl(t.rows[7][0].w));
    band(7,tile,0,true,c[5]);
    y=t.rows[7][0].h+0x106;
    for(unsigned row=8;row<=10;++row) {
        band(row,tile,0,true,fl(y));
        y+=t.rows[row][0].h;
    }
}

// --- win quote ---------------------------------------------------------
int ArcadeWinQuote::glyphCount(const ArcadeResultsTables::Quote& quote) {
    int n=0;
    for(const auto& line:quote)for(size_t i=0;i<line.size();i+=uint8_t(line[i])<0x80?1:2)++n;
    return n;
}
ArcadeResultEvents ArcadeWinQuote::enter(ArcadeRun& run,const ArcadeResultsTables& tables) {
    *this={};
    const auto& g=run.game;
    draw.winner=g.winner;
    draw.character=run.players.at(size_t(g.winner)).character;
    draw.quote=tables.quote(run.system(),draw.character,g.endingChoice);
    ArcadeResultEvents events;
    events.music=music;
    return events;
}
ArcadeResultEvents ArcadeWinQuote::tick(ArcadeRun& run,std::array<uint32_t,2> pressed,uint32_t held) {
    ArcadeResultEvents events;
    auto& g=run.game;
    const uint32_t pad=pressed.at(size_t(g.winner));
    const auto leaveScene=[&] {run.winQuoteExit(held);latch=1;events.exit=true;};
    if(frame>=0x10&&latch==0&&(pad&8)&&g.challengerFreeze==0)leaveScene();
    if(frame>=0x3c&&endFrame<0x1c2&&latch==0&&(pad&0x607)) {
        if(messageDone==0) {revealLimit=0x100;messageFrame=0x400;}
        if(messageDone==1)endFrame=0x1c2;
    }
    draw.frame=frame;draw.backgroundFrame=backgroundFrame;draw.revealLimit=revealLimit;
    // 136a28: 1a2870 reports whether every character lies below the limit.
    if(frame>=0x3c)messageDone=draw.quote&&glyphCount(*draw.quote)<revealLimit;
    if(g.challengerFreeze==0) {
        ++frame;++backgroundFrame;
        if(frame>0x3c) {revealLimit=messageFrame/4;++messageFrame;}
        if(messageDone==1)++endFrame;
    } else revealLimit=0x400;
    if(endFrame==0x1e0&&latch==0&&g.challengerFreeze==0)leaveScene();
    return events;
}
void drawArcadeWinQuote(const MenuCanvas& canvas,MenuDrawList& list,const ArcadeResultsTables& t,const ArcadeWinQuoteDraw& d) {
    const auto& q=t.quoteFloats;
    const int f=d.frame;
    // 136500: entrance of the portrait. It crosses the screen twice, then
    // shrinks from three times its size into place.
    bool show=true;
    float scale=q[3],x=0,y=0;
    if(f<10)x=fl(-((d.winner==0?f:10-f)<<7));
    else if(f>=20&&f<30) {x=fl(-((d.winner==0?10-(f-20):f-20)<<7));y=q[4];}
    else if(f>=40&&f<60) {
        scale=eeSub(q[3],mul(fl(f-40),q[5]));
        y=-eeSub(mul(mul(scale,q[7]),q[6]),q[9]);
        x=-eeSub(mul(mul(scale,q[8]),q[6]),q[10]);
    } else if(f>=60)scale=q[11];
    else show=false;
    // 136930: four white frames when the portrait lands.
    if(f>=0x3c&&f<0x40)canvas.rectangle(list,0,0,640,480,white,q[18]);
    // 1364a8: black until the landing, then the scrolling board.
    if(f<0x3c)canvas.rectangle(list,0,0,int(q[1]),int(q[2]),0xff000000u,q[0]);
    else drawResultBackground(canvas,list,t,0,d.backgroundFrame);
    if(show) {
        // 1366e0: the sheet holds the picture in two pieces; the second one
        // (130 x 380, stored turned) continues the first to the left.
        list.colour=white;list.blend=1;
        const float one=q[12],strip=q[13],tall=q[14],wide=q[15],grow=eeSub(scale,one);
        spriteExact(canvas,list,portraitSlot,eeAdd(x,eeAdd(mul(grow,strip),strip)),eeAdd(y,0),q[16],mul(scale,wide),mul(scale,tall),
                    one,0,wide,tall);
        const float bottom=eeAdd(eeAdd(y,tall),mul(grow,tall));
        float right=eeAdd(eeAdd(x,strip),mul(grow,strip));
        // Before the landing the right edge is one unit further out (136808).
        if(f<0x3c)right=eeAdd(right,one);
        const float left=eeAdd(x,0),top=eeAdd(y,0);
        quad4(canvas,list,portraitSlot,left,bottom,right,bottom,left,top,right,top,q[16],one,q[17],tall,strip);
    }
    if(f>=0x3c) {
        // 1369b0: the strip behind the text.
        list.blend=0;list.colour=white;
        canvas.rectangle(list,0,int(q[19]),int(q[21]),int(q[22]),0xff000000u,q[20]);
        // 136a28 -> 1a2870: lines centred on x 320, 24 pixels apart.
        if(d.quote) {
            const int saved=list.textDepth;
            list.textDepth=textDepth(list);
            int counter=0,ty=0x16e +(3-int(d.quote->size()))*12;
            for(const auto& line:*d.quote) {
                revealLine(canvas,list,line,0x140-int(line.size())*6,ty,d.revealLimit,counter);
                ty+=0x18;
            }
            list.textDepth=saved;
        }
    }
}

// --- VS result ---------------------------------------------------------
ArcadeResultEvents ArcadeVersusResult::enter(const ArcadeRun& run,const ArcadeResultsTables& tables) {
    *this={};
    const auto& g=run.game;
    const auto& player=run.players.at(size_t(g.winner));
    fighter.seat=g.winner;fighter.character=player.character;fighter.colour=player.colour;
    fighter.x=trunc(tables.resultEntry[g.winner!=0]);fighter.flags=g.winner!=0?0x80000:0;fighter.action=0;
    ArcadeResultEvents events;
    events.music=music;
    return events;
}
ArcadeResultEvents ArcadeVersusResult::tick(ArcadeRun& run,std::array<uint32_t,2> pressed,uint32_t held,int32_t poseHeld) {
    ArcadeResultEvents events;
    auto& g=run.game;
    const uint32_t pad=pressed.at(size_t(g.winner));
    const auto leaveScene=[&] {run.versusResultExit(held);latch=1;events.exit=true;};
    if(frame>=0x1f&&latch==0&&(pad&8)&&g.challengerFreeze==0)leaveScene();
    const bool pose=fighter.action==0x1fb;
    if(pose&&poseHeld!=0&&endFrame<0xd2&&latch==0&&(pad&0x607))endFrame=0xd2;
    draw.frame=frame;draw.streak=g.versusStreak;draw.defeated=g.defeated;
    if(g.challengerFreeze==0) {
        ++frame;
        if(pose&&poseHeld==1)++endFrame;
    }
    if(frame==0x64) {fighter.action=0x1fb;events.objectAction=true;events.action=0x1fb;}
    if(endFrame==0xf0&&latch==0&&g.challengerFreeze==0)leaveScene();
    return events;
}
void drawArcadeVersusResult(const MenuCanvas& canvas,MenuDrawList& list,const ArcadeResultsTables& t,const ArcadeVersusResultDraw& d) {
    const auto& c=t.resultFloats;
    const int f=d.frame;
    drawResultBackground(canvas,list,t,1,f);
    // 137100: one white frame when the count steps.
    if(f==0x64)canvas.rectangle(list,0,0,640,480,white,c[0]);
    // 137150: the streak, shown one short until frame 0x64.
    {
        const int value=(d.streak<0x3e8?d.streak:0x3e7)-(f<0x64);
        list.colour=white;list.blend=1;
        const auto digit=[&](int n,float x) {
            const auto& r=n<0?t.resultDigitBefore:t.resultDigits[size_t(n)];
            sheet(canvas,list,r,1,white,x,c[1],c[2],fl(t.resultDigits[0].w),fl(t.resultDigits[0].h));
        };
        digit(value/100,c[1]);
        digit(value%100/10,c[3]);
        digit(value%10,c[4]);
        sheet(canvas,list,t.resultLabel,1,white,c[5],c[1],c[2],fl(t.resultLabel.w),fl(t.resultLabel.h));
    }
    // 137320: the defeated fighters, newest first, five to a row.
    list.colour=white;
    const int count=d.streak<0x14?d.streak:0x14;
    if(count<=0)return;
    list.blend=1;
    const auto& k=t.faceFloats;
    for(int i=0;i<count;++i) {
        const int x=i%5*0x70+0x30,y=i/5*0x60+0x30;
        const auto& face=t.faces.at(size_t(d.defeated[size_t((d.streak-i+0x13)%0x14)]));
        const float u=fl(face[1]*0x55),v=fl(face[2]*0x42);
        const auto submit=[&](int px,int py) {
            const size_t before=list.records.size();
            canvas.sprite(list,face[0],fl(px),fl(py),k[3],k[0],k[1],u,v,k[0],k[1]);
            if(list.records.size()!=before)clampSpan(list.records.back());
        };
        bool mark=true;
        if(i==0) {
            if(f<0x3c) {
                // Fades in over sixty frames.
                list.colour=uint32_t(trunc(mul(fl(f),k[2])))<<24|0xffffffu;
                submit(x,y);
            } else {
                int dx=0,dy=0;
                if(f>=0x64&&f-0x64<0x18) {dx=t.resultShake[size_t((f-0x64)%8)][0];dy=t.resultShake[size_t((f-0x64)%8)][1];}
                submit(x+dx,y+dy);
            }
            list.colour=white;
            mark=f>=0x64;
        } else submit(x,y);
        if(mark)sheet(canvas,list,t.resultMark,0,white,fl(x-0x10),fl(y-0xc),k[4],fl(t.resultMark.w),fl(t.resultMark.h));
    }
}

// --- challenger banner -------------------------------------------------
ArcadeBannerFrame ArcadeChallengerBanner::tick(bool hidden) {
    ArcadeBannerFrame out;
    switch(state) {
    case 1:
        out.banner=!hidden;
        out.voice=age==0;
        if(age>=0x5b)out.curtain=age-0x5a;
        // 125778 returns zero on its fifteenth step.
        if(age>=0x5b&&age-0x5a>=0xe) {state=2;age=0;} else ++age;
        break;
    case 2:
        out.curtain=0xf+age;
        out.stopSound=age==0;
        if(age>=2) {out.swap=true;state=3;age=0;} else ++age;
        break;
    case 3:
        out.curtain=0x12+age;
        if(age>=0xe) {out.finished=true;state=0;age=0;} else ++age;
        break;
    default:break;
    }
    return out;
}
void drawArcadeBanner(const MenuCanvas& canvas,MenuDrawList& list,const ArcadeResultsTables& t) {
    // 125c68 runs with word 3db908 = 1: 108118 then skips the size-1 clamp and
    // submits normalised STQ coordinates inset by half a texel on every side
    // (u + 0.5 .. u + w - 0.5). The record keeps those texel positions.
    const auto& f=t.bannerFloats;
    for(unsigned i=0;i<2;++i) {
        const auto& r=t.banner[i];
        const size_t before=list.records.size();
        sheet(canvas,list,r,i?3u:0u,white,f[0],f[1],f[2],fl(r.w),fl(r.h),false);
        if(list.records.size()==before)continue;
        auto& q=list.records.back();
        q.u=eeAdd(q.u,0.5f);q.v=eeAdd(q.v,0.5f);q.uw=eeSub(q.uw,1.0f);q.vh=eeSub(q.vh,1.0f);
        q.kind=MenuPrimitive::Rotated;
        q.corner={q.x,q.y,q.x,eeAdd(q.y,q.h),eeAdd(q.x,q.w),q.y,eeAdd(q.x,q.w),eeAdd(q.y,q.h)};
    }
}

// --- name entry overlay ------------------------------------------------
void drawArcadeNameCountdown(const MenuCanvas& canvas,MenuDrawList& list,const ArcadeResultsTables& t,
                             const ArcadeNameEntry& entry,int gameMode) {
    if(entry.finished!=0)return;
    int x=gameMode==1?0xc6:0x246,value=entry.seconds;
    for(int divisor=10;divisor>0;divisor/=10) {
        const int quotient=value/divisor;
        const auto& r=t.entryDigits[size_t(quotient<=0?0:quotient%10)];
        sheet(canvas,list,r,0,white,fl(x),t.entryFloats[2],t.entryFloats[3],fl(r.w),fl(r.h));
        x+=0xe;value%=divisor;
    }
}
void drawArcadeNameEntry(const MenuCanvas& canvas,MenuDrawList& list,const ArcadeResultsTables& t,const ArcadeTables& glyphs,
                         const ArcadeNameEntry& entry,int gameMode) {
    const int labelX=gameMode==1?0x20:0x1a0,nameX=gameMode==1?0x66:0x1e6;
    const bool blink=entry.blinkShown==1;
    canvas.ascii(list,"NAME>",labelX,0x18,white);
    // Position of the glyph being chosen: the cursor, or the fourth cell once the name is full.
    const int cell=entry.cursor==2&&entry.name[2]!=0?3:entry.cursor;
    if(entry.finished==0)
        // Placeholders for the open positions from the right; the one under the cursor blinks.
        for(int k=2;k>=cell;--k)
            if(k!=cell||blink)canvas.ascii(list,"_",nameX+0xe*k,0x1d,white);
    if(entry.finished==0||blink)canvas.ascii(list,entry.name.data(),nameX,0x18,white);
    if(blink&&entry.finished==0) {
        const auto& glyph=glyphs.glyphs.at(size_t(entry.glyph));
        const int x=nameX+0xe*cell;
        if(same(glyph,"END"))sheet(canvas,list,t.entryEnd,0,white,fl(x),t.entryFloats[0],t.entryFloats[1],fl(t.entryEnd.w),fl(t.entryEnd.h));
        else if(same(glyph,"<-"))sheet(canvas,list,t.entryBack,0,white,fl(x),t.entryFloats[0],t.entryFloats[1],fl(t.entryBack.w),fl(t.entryBack.h));
        else canvas.ascii(list,glyph.data(),x,0x18,white);
    }
}

// --- unlock notice -----------------------------------------------------
ArcadeResultEvents ArcadeUnlockNotice::enter(ArcadeRun& run,const UnlockSessionFlags& session) {
    *this={};
    items=unlockCollect(run.system(),session);
    run.game.challengerInhibit=1;
    ArcadeResultEvents events;
    events.music=0x33; // 1e79c8(0, 33)
    return events;
}
ArcadeResultEvents ArcadeUnlockNotice::tick(ArcadeRun& run,std::array<uint32_t,2> pressed) {
    ArcadeResultEvents events;
    const int count=int(items.size()),mode=run.game.mode;
    // 1e6640: any of the buttons 60e of the arcade seat, from frame 3c.
    const uint32_t pad=mode==1?pressed[0]:mode==2?pressed[1]:0;
    if(frame>=0x3c&&(pad&0x60e)&&index<count) {frame=0;fading=1;}
    int alpha;
    if(fading!=0) {
        if(frame==0) {events.sound=true;events.soundA=-1;events.soundB=0;}
        alpha=frame*-0xff/0x3c+0xff;
    } else {
        if(frame==0&&index<count) {events.sound=true;events.soundA=0;events.soundB=1;}
        alpha=frame*0xff/0x3c;
    }
    draw.item=index<count?items[size_t(index)]:-1;draw.alpha=alpha;
    if(frame<0x3c&&++frame==0x3c) {
        if(fading==1) {frame=0;++index;}
        fading=0;
    }
    if(index==count&&latch==0) {
        events.autosave=true;
        run.request(1,1,0x1e6130,ArcadeScene::Ranking);
        latch=1;events.exit=true;
    }
    return events;
}
void ArcadeUnlockNotice::leave(ArcadeRun& run) {
    run.game.clear();
    run.game.transitionLock=1;run.game.challengerInhibit=0;
}
void drawArcadeUnlockNotice(const MenuCanvas& canvas,MenuDrawList& list,const ArcadeResultsTables& t,const ArcadeUnlockDraw& d,
                            ArcadeEdgePulse& pulse) {
    if(d.item<0)return;
    const auto& text=t.unlockTexts.at(size_t(d.item));
    const int lines=lineCount(text),top=(lines&1?0xd4:0xe0)-(lines>>1)*0x18;
    // 1e63c8: the text and its shadow at one tie-broken depth.
    const int saved=list.textDepth;
    list.textDepth=trunc(canvas.depth(list,t.unlockFloats[0]));
    canvas.text24(list,text,0x46,top+2,0,0,0,d.alpha);
    canvas.text24(list,text,0x44,top,0xff,0xff,0xff,d.alpha);
    list.textDepth=saved;
    // 1e64a8: the panel and its four pulsing edges at half the text alpha.
    const uint32_t alpha=uint32_t(d.alpha>>1)<<24;
    const int height=lines*0x18+0x30;
    canvas.rectangle(list,0x18,top-0x18,0x250,height,alpha+0xfcfcfcu,t.unlockFloats[1]);
    const uint32_t first=alpha+0xff8020u,second=alpha+0x802020u;
    const float z=t.unlockFloats[2];
    edge(canvas,list,0x14,top-0x1c,0x258,4,first,second,pulse,0x78,z);
    edge(canvas,list,0x14,top+lines*0x18+0x14,0x258,4,first,second,pulse,0x78,z);
    edge(canvas,list,0x14,top-0x18,4,height,first,second,pulse,0x78,z);
    edge(canvas,list,0x268,top-0x18,4,height,first,second,pulse,0x78,z);
}

// --- sheets ------------------------------------------------------------
ArcadeResultsArt::ArcadeResultsArt(const std::filesystem::path& assets):assets_(assets) {
    // Slot 4, variant 0: the appended 16x16 CLUT (CSM1 exchanges index bits 3 / 4).
    board_=load(assets/"menu_bg00_00.tex",1024*1024+1024);
    for(unsigned i=0;i<256;++i) {
        const unsigned j=(i&~24u)|((i&8u)<<1)|((i&16u)>>1);
        std::copy_n(board_.data()+1024*1024+4*j,4,boardColours_[i].begin());
    }
    board_.resize(1024*1024);
    // Slot 4, variant 1: bank 0. 135d88 uploads only entries 80..ff of
    // menu_bg01_00.pvp; 00..7f stay the resident obj0 CLUT (113890 clears
    // entry 0 of each of its banks).
    picture_=load(assets/"menu_bg01_00.tex",1024*1024);
    const auto resident=load(assets/"obj0.pal",512),own=load(assets/"menu_bg01_00.pal",512);
    pictureBank_.source.resize(256);
    for(unsigned i=0;i<256;++i) {
        const auto& from=i<128?resident:own;
        pictureBank_.source[i]=i<128&&i%16==0?uint16_t(0):uint16_t(from[2*i]|from[2*i+1]<<8);
    }
    // Slot 0xc: 4-bit sheet coloured by banks 0 and 1 of the resident CLUT.
    digits_=load(assets/"font_otherscene2_16.tex",512*512/2);
    digitBank_.source.assign(pictureBank_.source.begin(),pictureBank_.source.begin()+32);
    // Slot 5: 32-bit palette at bank 0x20.
    faces_=load(assets/"char_face_1024.tex",1024*1024);
    const auto palette=load(assets/"char_face_1024.pal",1024);
    faceBank_.source.resize(512);
    std::memcpy(faceBank_.source.data(),palette.data(),1024);
    rebuild(pictureBank_);rebuild(digitBank_);
    setFade(false,0,0);
}
void ArcadeResultsArt::bindBackground(int variant) {background_=variant;}
void ArcadeResultsArt::bindPortrait(int character) {
    if(character==portrait_)return;
    if(character<0||character>=0x31||character==0x2b)throw std::invalid_argument("No win portrait for this character");
    char name[16];
    std::snprintf(name,sizeof name,"win_%02d",character);
    portraitTexels_=load(assets_/(std::string(name)+".tex"),512*512);
    const auto pal=load(assets_/(std::string(name)+".pal"),0);
    if(pal.size()!=512&&pal.size()!=1024)throw std::runtime_error("Invalid win portrait palette: "+std::string(name));
    // win_40, 41 and 44..48 carry 32-bit palettes: 116478 then copies the parallel
    // buffer, so the halfword 135f70 clears in the 16-bit buffer has no effect.
    portrait32_=pal.size()==1024;
    portraitBank_.source.resize(pal.size()/2);
    std::memcpy(portraitBank_.source.data(),pal.data(),pal.size());
    if(!portrait32_)portraitBank_.source[0]=0; // 135f70 clears the first entry
    portrait_=character;
    setFade(fadeEnabled_,fadeLevel_,fadeColour_);
}
void ArcadeResultsArt::setFade(bool enabled,int level,uint32_t colour) {
    if(level<0||level>256)throw std::invalid_argument("Invalid arcade result fade level");
    fadeEnabled_=enabled;fadeLevel_=level;fadeColour_=colour;
    rebuild(pictureBank_);rebuild(digitBank_);
    // 32-bit entries pass through at level 0 and are interpolated in 5-bit RGB otherwise.
    const bool active=fadeEnabled_&&fadeLevel_>0;
    const auto wide=[&](Bank& bank) {
        bank.colours.assign(256,{});
        for(unsigned i=0;i<256;++i) {
            const uint8_t* s=reinterpret_cast<const uint8_t*>(bank.source.data())+4*i;
            if(!s[3])continue;
            auto& out=bank.colours[i];
            std::copy_n(s,4,out.begin());
            if(active)for(int c=0;c<3;++c) {
                const int tone=int((fadeColour_>>(8*(2-c)))&255)>>3;
                out[size_t(c)]=uint8_t((((s[c]>>3)*(256-fadeLevel_)+tone*fadeLevel_)>>8)<<3);
            }
        }
    };
    wide(faceBank_);
    if(portrait32_)wide(portraitBank_);else rebuild(portraitBank_);
}
void ArcadeResultsArt::rebuild(Bank& bank) const {
    // 116588: 5-bit interpolation toward 3ec730 while a fade runs; entries
    // without the 0x8000 bit stay fully transparent.
    const bool active=fadeEnabled_&&fadeLevel_>0;
    bank.colours.assign(bank.source.size(),{});
    for(size_t i=0;i<bank.source.size();++i) {
        const auto v=bank.source[i];
        if(!(v&0x8000))continue;
        auto& out=bank.colours[i];
        for(int c=0;c<3;++c) {
            const int five=(v>>(10-5*c))&31,tone=int((fadeColour_>>(8*(2-c)))&255)>>3;
            out[size_t(c)]=uint8_t((active?(five*(256-fadeLevel_)+tone*fadeLevel_)>>8:five)<<3);
        }
        out[3]=128;
    }
}
void ArcadeResultsArt::rasterise(const MenuCanvas& canvas,const MenuDrawList& list,std::span<uint8_t> rgba) const {
    if(rgba.size()!=size_t(width)*height*4)throw std::invalid_argument("Expected a 640x480 arcade result surface");
    std::vector<unsigned> order(list.records.size());
    std::iota(order.begin(),order.end(),0u);
    std::stable_sort(order.begin(),order.end(),[&](unsigned a,unsigned b) {return list.records[a].z<list.records[b].z;});
    MenuDrawList pending;
    const auto flush=[&] {
        if(pending.records.empty())return;
        canvas.rasterise(pending,rgba);pending.records.clear();
    };
    for(const unsigned at:order) {
        const auto& q=list.records[at];
        const bool textured=q.kind==MenuPrimitive::Quad||q.kind==MenuPrimitive::Rotated;
        const bool own=textured&&(q.slot==boardSlot||q.slot==faceSlot||q.slot==portraitSlot||q.slot==digitSlot);
        if(!own) {pending.records.push_back(q);continue;}
        flush();
        const int size=sheetSize(q.slot);
        const auto texel=[&](int tu,int tv)->const uint8_t* {
            const size_t offset=size_t(tv)*size_t(size)+size_t(tu);
            switch(q.slot) {
            case boardSlot:
                if(background_==0)return boardColours_[board_[offset]].data();
                if(background_==1)return pictureBank_.colours[picture_[offset]].data();
                throw std::logic_error("No result background is bound");
            case faceSlot:return faceBank_.colours[faces_[offset]].data();
            case portraitSlot:
                if(portrait_<0)throw std::logic_error("No win portrait is bound");
                return portraitBank_.colours[portraitTexels_[offset]].data();
            default:
                return digitBank_.colours[size_t(q.glyph&1u)*16+((digits_[size_t(tv)*256+size_t(tu/2)]>>(4*(tu&1)))&15)].data();
            }
        };
        int mod[4];
        for(int c=0;c<4;++c)mod[c]=int((q.colour>>(8*c))&255);
        const auto plot=[&](int px,int py,int tu,int tv) {
            const uint8_t* t=texel(tu,tv);
            int source[4];
            for(int c=0;c<4;++c)source[c]=std::min(255,t[c]*mod[c]/128);
            auto* dst=rgba.data()+4*(size_t(py)*width+size_t(px));
            // Tag 2ff2 (latch 348b10): ALPHA preset 348bc0, Cd + Cs.
            for(int c=0;c<3;++c)
                dst[c]=q.additive?uint8_t(std::min(255,dst[c]+source[c]))
                                 :uint8_t(std::clamp(dst[c]+(((source[c]-dst[c])*source[3])>>7),0,255));
        };
        // Corners in 113f98 order: (u,v), (u,v+vh), (u+uw,v), (u+uw,v+vh).
        std::array<float,8> p;
        if(q.kind==MenuPrimitive::Rotated)p=q.corner;
        else p={q.x,q.y,q.x,q.y+q.h,q.x+q.w,q.y,q.x+q.w,q.y+q.h};
        const float u0=q.u,v0=q.v,u1=q.u+q.uw,v1=q.v+q.vh;
        const auto whole=[](float v) {return v==std::floor(v)&&std::abs(v)<=32768;};
        const bool aligned=p[0]==p[2]&&p[1]==p[5]&&p[6]==p[4]&&p[7]==p[3]&&
            std::all_of(p.begin(),p.end(),whole)&&whole(u0)&&whole(v0)&&whole(u1)&&whole(v1);
        if(aligned) {
            const int x0=int(p[0]),y0=int(p[1]),x1=int(p[4]),y1=int(p[3]);
            const int iu0=int(u0),iv0=int(v0),iu1=int(u1),iv1=int(v1);
            if(x0==x1||y0==y1)continue;
            // Texel under each pixel centre, floor division as the reference painter.
            const auto floorDiv=[](long long a,long long b) {
                long long d=a/b;
                if((a%b!=0)&&((a<0)!=(b<0)))--d;
                return d;
            };
            for(int py=std::max(0,std::min(y0,y1));py<std::min(height,std::max(y0,y1));++py) {
                const int tv=iv0+int(floorDiv((2LL*py+1-2LL*y0)*(iv1-iv0),2LL*(y1-y0)));
                for(int px=std::max(0,std::min(x0,x1));px<std::min(width,std::max(x0,x1));++px) {
                    const int tu=iu0+int(floorDiv((2LL*px+1-2LL*x0)*(iu1-iu0),2LL*(x1-x0)));
                    if(tu<0||tv<0||tu>=size||tv>=size)continue;
                    plot(px,py,tu,tv);
                }
            }
            continue;
        }
        // Inverse-affine sampling at pixel centres (parallelogram of the first three corners).
        const double xs[4]={p[0],p[2],p[4],p[6]},ys[4]={p[1],p[3],p[5],p[7]};
        const int left=std::max(0,int(std::floor(*std::min_element(xs,xs+4)))),right=std::min(width-1,int(std::ceil(*std::max_element(xs,xs+4))));
        const int top=std::max(0,int(std::floor(*std::min_element(ys,ys+4)))),bottom=std::min(height-1,int(std::ceil(*std::max_element(ys,ys+4))));
        if(right<left||bottom<top)continue;
        const double ax=double(p[4])-p[0],ay=double(p[5])-p[1],bx=double(p[2])-p[0],by=double(p[3])-p[1];
        const double det=ax*by-ay*bx;
        if(det==0)continue;
        for(int py=top;py<=bottom;++py)for(int px=left;px<=right;++px) {
            const double dx=px+0.5-double(p[0]),dy=py+0.5-double(p[1]);
            const double s=(dx*by-dy*bx)/det,t=(ax*dy-ay*dx)/det;
            if(!(s>=0&&s<1&&t>=0&&t<1))continue;
            const int tu=int(std::floor(double(u0)+s*(double(u1)-double(u0)))),tv=int(std::floor(double(v0)+t*(double(v1)-double(v0))));
            if(tu<0||tv<0||tu>=size||tv>=size)continue;
            plot(px,py,tu,tv);
        }
    }
    flush();
}
}
