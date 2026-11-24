#include "asset_files.hpp"
#include "arcade_talk.hpp"
#include "scalar_float.hpp"
#include "soft_double.hpp"
#include "system_data.hpp"
#include "game_random.hpp"

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
using Op=ArcadeTalkDrawOp;
using Event=ArcadeTalkEvent;

std::vector<uint8_t> load(const std::filesystem::path& file,size_t size=0) {
    std::ifstream in(resolveAsset(file),std::ios::binary|std::ios::ate);
    if(!in||(size&&in.tellg()!=std::streamoff(size)))throw std::runtime_error("Invalid arcade talk resource: "+file.string());
    std::vector<uint8_t> bytes(size_t(in.tellg()));
    in.seekg(0);
    if(!in.read(reinterpret_cast<char*>(bytes.data()),std::streamsize(bytes.size())))
        throw std::runtime_error("Truncated arcade talk resource: "+file.string());
    return bytes;
}
int sheetSize(int slot) {return slot==5?1024:slot==0x22||slot==0x23?256:512;}
// 108118 (10849c..108514): texel coordinates above size-1 are replaced by size-1.
void clampSpan(MenuDrawRecord& r) {
    const float limit=float(sheetSize(r.slot)-1);
    const float u1=std::min(r.u+r.uw,limit),v1=std::min(r.v+r.vh,limit);
    r.u=std::min(r.u,limit);r.v=std::min(r.v,limit);r.uw=u1-r.u;r.vh=v1-r.v;
}
void sprite(const MenuCanvas& canvas,MenuDrawList& list,int slot,float x,float y,float z,float w,float h,
            float u,float v,float uw,float vh) {
    const size_t before=list.records.size();
    canvas.sprite(list,slot,x,y,z,w,h,u,v,uw,vh);
    if(list.records.size()!=before)clampSpan(list.records.back());
}
// 1149d0 colour word of 3db900 without the 117288 fade (114118 path).
uint32_t queueColour(const MenuCanvas& canvas,MenuDrawList& list) {
    const int depth=list.depth;
    canvas.sprite(list,0x28,0,0,0,1,1,0,0,1,1);
    const uint32_t colour=list.records.back().colour;
    list.records.pop_back();list.depth=depth;
    return colour;
}
// 114118: four explicit corners, texels (u,v), (u,v+vh), (u+uw,v), (u+uw,v+vh).
void quad4(const MenuCanvas& canvas,MenuDrawList& list,int slot,float x0,float y0,float x1,float y1,float x2,float y2,
           float x3,float y3,float z,float u,float v,float uw,float vh) {
    const float xs[4]={x0,x1,x2,x3},ys[4]={y0,y1,y2,y3};
    const auto all=[](const float* p,auto test) {return test(p[0])&&test(p[1])&&test(p[2])&&test(p[3]);};
    if(all(xs,[](float c){return c<0;})||all(xs,[](float c){return 640.0f<c;})||
       all(ys,[](float c){return c<0;})||all(ys,[](float c){return 480.0f<c;}))return;
    MenuDrawRecord r;
    r.kind=MenuPrimitive::Rotated;r.slot=uint8_t(slot);r.blend=uint8_t(list.blend);r.additive=list.additive;
    r.colour=queueColour(canvas,list);r.z=canvas.depth(list,z);
    r.corner={x0,y0,x1,y1,x2,y2,x3,y3};
    r.u=u;r.v=v;r.uw=uw;r.vh=vh;r.x=x0;r.y=y0;r.w=x2-x0;r.h=y1-y0;
    clampSpan(r);
    list.records.push_back(r);
}
int leading(const ArcadeTalkTables::Message& m,int limit) {
    int n=0;
    while(n<limit&&m.line[size_t(n)]>=0)++n;
    return n;
}
// 311510 (fp-bit truncdfsf2) truncates toward zero.
float narrowDouble(double v) {
    float r=float(v);
    if(std::fabs(double(r))>std::fabs(v))r=std::nextafter(r,0.0f);
    return r;
}
// 1040a0 seeds the 90 records of the effect pool 114ecb0 from the C library
// generator (103b30: one velocity branch takes an extra draw); 104510 then
// disables the pool, so only the generator state survives. Same sequence as
// selectConsoleVersusStage (console_versus_session.cpp).
void seedEffectPool(GameRandom& random) {
    for(unsigned i=0;i<90;++i) {
        random.nextLibrary();random.nextLibrary();
        if(random.nextLibrary()&0x4000)random.nextLibrary();
        for(unsigned k=0;k<6;++k)random.nextLibrary();
    }
}
int quarter(int value) {return (value<0?value+3:value)>>2;}
}

// ---------------------------------------------------------------------
ArcadeTalkTables::ArcadeTalkTables(const std::filesystem::path& assets) {
    const auto raw=load(assets/"arcade_talk.bin");
    size_t at=0;
    const auto take=[&](void* to,size_t n) {
        if(at+n>raw.size())throw std::runtime_error("Truncated arcade_talk.bin");
        std::memcpy(to,raw.data()+at,n);at+=n;
    };
    const auto word=[&] {uint32_t v;take(&v,4);return v;};
    char magic[8];take(magic,8);
    if(std::memcmp(magic,"ATLK\1\0\0\0",8))throw std::runtime_error("Mismatched arcade_talk.bin");
    take(portrait.data(),56);take(openingCamera.data(),40);take(talkCamera.data(),20);take(talkActions.data(),8);
    take(talkPan.data(),20);take(preFinalCamera.data(),20);take(preFinal.data(),116);
    take(sheets.data(),96);take(balloons.data(),216);take(ease.data(),360);
    strings.resize(word());
    for(auto& s:strings) {uint16_t n;take(&n,2);s.resize(n);take(s.data(),n);if(n&1)throw std::runtime_error("Odd arcade talk string");}
    messages.resize(word());
    for(auto& m:messages)take(&m,20);
    for(auto& lines:openingLines) {lines.resize(word());take(lines.data(),4*lines.size());}
    for(auto& v:versions) {take(v.characters.data(),49*100);take(v.kinds.data(),80);}
    const uint32_t count=word();
    for(uint32_t i=0;i<count;++i) {uint16_t record;take(&record,2);take(glyphs[record].data(),288);}
    if(at!=raw.size())throw std::runtime_error("Invalid arcade_talk.bin length");
}
int ArcadeTalkTables::message(bool alternate,int character,int group,int n) const {
    // 1a3070 returns 0 for characters 43 and >= 49; other arguments outside the
    // extracted records are reads the original performs on unrelated memory.
    if(character<0||character>=49||n<0||n>3)return -1;
    const auto& row=versions[alternate].characters[size_t(character)];
    if(group==0)return row[0];
    if(group<3||group>8)return -1;
    return row[size_t(1+4*(group-3)+n)];
}
int ArcadeTalkTables::kindMessage(bool alternate,int kind,int page) const {
    if(kind<0||kind>4||page<0||page>3)return -1;
    return versions[alternate].kinds[size_t(kind)][size_t(page)];
}

// ---------------------------------------------------------------------
void ArcadeFade::range(int first,int count,uint16_t flag) {
    const int end=std::min(first+count,0x400);
    for(int i=std::max(first,0);i<end;++i)flags[size_t(i)]=flag;
}
void ArcadeFade::beginTransition(int kind) {
    if(kind!=1&&kind!=2)return;
    // 125340: 1170d8(kind 1: -1, kind 2: ff000000); 1170e8(0); 117140(100, 0); 3ebf18 |= 2.
    colour=kind==1?0xffffffffu:0xff000000u;level=0;maximum=256;minimum=0;mode|=2;
}
void ArcadeFade::endFrame() {
    level+=speed;
    if(speed>0&&maximum<level)level=maximum;
    if(speed<0&&level<minimum)level=minimum;
}
namespace {
std::array<uint8_t,4> process(const ArcadeFade& fade,int selector,int r,int g,int b,uint8_t alpha) {
    // A zero level masks the fade bit (116610..116618).
    if(fade.level==0)selector&=~2;
    if(selector&5)r=g=b=(r*10+g*16+b*6)>>5;
    if(selector&2) {
        const int keep=256-fade.level;
        r=((r*keep+int((fade.colour>>19)&31)*fade.level)>>8)&31;
        g=((g*keep+int((fade.colour>>11)&31)*fade.level)>>8)&31;
        b=((b*keep+int((fade.colour>>3)&31)*fade.level)>>8)&31;
    }
    return {uint8_t(r<<3),uint8_t(g<<3),uint8_t(b<<3),alpha};
}
}
std::array<uint8_t,4> ArcadeFade::resident(unsigned index,uint16_t source) const {
    if(!(source&0x8000))return {};
    return process(*this,flags.at(index)|mode,(source>>10)&31,(source>>5)&31,source&31,0x80);
}
std::array<uint8_t,4> ArcadeFade::glyph(unsigned index) const {
    // 112f58 keeps entry 0 clear; 116774: alpha (1 + 17 k) >> 1, no per-entry flags.
    if(index==0||index>15)return {};
    return process(*this,mode,int((textColour>>19)&31),int((textColour>>11)&31),int((textColour>>3)&31),uint8_t((1+17*index)>>1));
}

// ---------------------------------------------------------------------
void ArcadeTalkScene::event(Event kind,std::array<int32_t,7> a,std::array<float,3> f) {events.push_back({kind,a,f});}
Op& ArcadeTalkScene::op(Op::Kind kind,const ArcadeFade& fade) {
    Op o;o.kind=kind;o.fade=fade.vertexFade();o.fadeLevel=fade.level;o.fadeColour=fade.colour;
    ops.push_back(o);
    return ops.back();
}
const ArcadeTalkTables::Message& ArcadeTalkScene::message(int index) const {
    if(index<0)throw std::invalid_argument("Arcade talk message outside the original tables");
    return tables_.messages.at(size_t(index));
}
void ArcadeTalkScene::text(const ArcadeFade& fade,int string,int x,int y,uint32_t colour) {
    // 1131d8: a glyph is submitted and counted while the limit 3d3aa0 is
    // negative or above the counter 3d3ab0; the pen advances either way.
    const int glyphs=int(tables_.strings.at(size_t(string)).size()/2);
    const int visible=revealLimit<0?glyphs:std::clamp(revealLimit-revealCount,0,glyphs);
    revealCount+=visible;
    if(!visible)return;
    auto& o=op(Op::Text,fade);
    o.a=string;o.b=x;o.c=y;o.d=visible;o.colour=colour;
}
void ArcadeTalkScene::portrait(int side,int id) {
    auto& slot=portraits[size_t(side-1)];
    const int old=slot;
    slot=id;
    if(uint32_t(id)<0x31&&id!=old)event(Event::LoadPortrait,{side,id});
}
void ArcadeTalkScene::portraitQuads(const ArcadeFade& fade,bool left,bool right) {
    if(left)op(Op::PortraitLeft,fade).a=portraits[0];
    if(right)op(Op::PortraitRight,fade).a=portraits[1];
}
bool ArcadeTalkScene::lines(const ArcadeFade& fade,const ArcadeTalkTables::Message& m,int x,int base) {
    const int n=leading(m,4);
    revealCount=0;
    for(int i=0;i<n;++i)text(fade,m.line[size_t(i)],x,(4-n)*0xe +base+0x1c*i,0xffffffffu);
    return revealed();
}
bool ArcadeTalkScene::centred(const ArcadeFade& fade,const ArcadeTalkTables::Message& m) {
    const int n=leading(m,3);
    revealCount=0;
    for(int i=0;i<n;++i) {
        const int length=int(tables_.strings.at(size_t(m.line[size_t(i)])).size());
        text(fade,m.line[size_t(i)],0x140-6*length,(3-n)*0xc+0x16e +0x18*i,0xffffffffu);
    }
    return revealed();
}
bool ArcadeTalkScene::balloon(const ArcadeFade& fade,const ArcadeTalkTables::Message& m,bool alpha,uint32_t colour) {
    const int n=leading(m,3);
    int id=m.balloon;
    const bool mirrored=id>=6;
    if(mirrored)id-=5;
    if(id<1||id>5)throw std::invalid_argument("Arcade talk balloon outside table 4eeef8");
    const auto& r=tables_.balloons[size_t(id)];
    auto& o=op(Op::Balloon,fade);
    o.a=id;o.b=mirrored;o.c=alpha;o.colour=colour;
    revealCount=0;
    for(int i=0;i<n;++i)
        text(fade,m.line[size_t(i)],r.textX+r.x,r.textY+r.y+(3-n)*0xe +0x18*i,alpha?colour:0xffffffffu);
    return revealed();
}

void ArcadeTalkScene::draw(MenuCanvas& canvas,MenuDrawList& list) const {
    const auto& p=tables_.portrait;
    for(const auto& o:ops) {
        canvas.setFade(o.fade,o.fadeLevel,o.fadeColour);
        switch(o.kind) {
        case Op::Colour:list.colour=o.colour;break;
        case Op::Rect:canvas.rectangle(list,o.a,o.b,o.c,o.d,o.colour,o.f[0]);break;
        case Op::PortraitLeft:
            // 1a22a8: backing band 1148f0(c0404040; 0, 40, -100, 640, 140), then 170x140 of slot 0x22.
            list.blend=1;
            canvas.rectangle(list,0,int(p[1]),int(p[3]),int(p[0]),0xc0404040u,p[2]);
            if(o.a<0x31)sprite(canvas,list,0x22,0,p[1],p[2],p[4],p[0],0,0,p[4],p[0]);
            break;
        case Op::PortraitRight:
            // 1a2380: band at y 280; slot 0x23 mirrored (u 170, span -170) at x 470.
            list.blend=1;
            canvas.rectangle(list,0,int(p[6]),int(p[8]),int(p[5]),0xc0404040u,p[7]);
            if(o.a<0x31)sprite(canvas,list,0x23,p[10],p[6],p[7],p[9],p[5],p[9],0,p[11],p[5]);
            break;
        case Op::Text: {
            // 1131d8: text depth 348a8c = trunc(114e40(3d3aac)) for the glyph, restored afterwards.
            const int saved=list.textDepth;
            list.textDepth=int(std::bit_cast<float>(ScalarFloat{std::bit_cast<uint32_t>(10000000.0f)}
                .sub(ScalarFloat{std::bit_cast<uint32_t>(list.asciiDepth)}.mul(ScalarFloat{std::bit_cast<uint32_t>(100.0f)})).bits));
            const auto& s=tables_.strings.at(size_t(o.a));
            canvas.text24(list,std::string_view(s).substr(0,size_t(2*o.d)),o.b,o.c,int((o.colour>>16)&255),int((o.colour>>8)&255),
                          int(o.colour&255),int(o.colour>>24));
            list.textDepth=saved;
            break;
        }
        case Op::Balloon: {
            const auto& r=tables_.balloons.at(size_t(o.a));
            const uint32_t saved=list.colour;
            if(o.c)list.colour=o.colour;   // 1a2948: 3db900 = colour around the call, 10add8(slot, 0)
            const float w=float(r.w);
            sprite(canvas,list,r.slot,float(r.x),float(r.y),p[o.c?13:12],w,float(r.h),o.b?float(r.u+r.w):float(r.u),float(r.v),
                   o.b?float(-r.w):w,float(r.h));
            list.colour=saved;
            break;
        }
        case Op::Sheet: {
            const auto& r=tables_.sheets.at(size_t(o.a));
            const size_t before=list.records.size();
            canvas.sprite(list,MenuSheetRect{r.u,r.v,r.w,r.h},r.slot,0,o.colour,false,o.f[0],o.f[1],o.f[2],float(r.w),float(r.h));
            if(list.records.size()!=before)clampSpan(list.records.back());
            break;
        }
        case Op::Backdrop: {
            // 1c7848: 3db8fc = 0 and 3db900 = -1 around two 114118 quads of slot 5 at depth 0.
            const auto& f=tables_.preFinal;
            const auto& a=tables_.sheets[2];const auto& b=tables_.sheets[3];
            const uint32_t saved=list.colour;
            list.blend=0;list.colour=0xffffffffu;
            const float s=o.f[0];
            const float y0=eeAdd(o.f[2],s),y1=eeAdd(o.f[4],s);
            quad4(canvas,list,a.slot,o.f[1],y0,o.f[1],y1,o.f[3],y0,o.f[3],y1,0,f[24],float(a.v),f[23],float(a.h));
            // The strip is a quarter turned: texel v runs along screen x.
            const float t0=eeAdd(o.f[6],s),t1=eeAdd(o.f[8],s);
            quad4(canvas,list,b.slot,o.f[5],t0,o.f[7],t0,o.f[5],t1,o.f[7],t1,0,float(b.u),float(b.v+0x60),float(b.w),f[23]);
            list.colour=saved;list.blend=1;
            break;
        }
        }
    }
}

// ---------------------------------------------------------------------
// Opening
void ArcadeOpening::enter(ArcadeRun& run,ArcadeFade&,uint32_t held) {
    events.clear();ops.clear();
    auto& g=run.game;
    seedEffectPool(run.random());
    // 1c6328: only modes 1 / 2 draw a schedule; g+98 is set in every mode.
    if(g.mode==1||g.mode==2)run.buildSchedule(run.players[size_t(g.mode-1)].character,true,held);
    g.scheduleValid=1;
    run.prepareFight();                                    // 1c2420
    event(Event::MapIcon,{g.stage<10?g.stage:9});          // 1c1ec8
    // 1c6388
    event(Event::LoadCharacter,{0,run.players[0].character});
    event(Event::LoadCharacter,{1,run.players[1].character});
    latch=0;
    // 1c6a68: map task 1c6b10, its camera, 1c1e30
    const auto& c=tables_.openingCamera;
    event(Event::CameraPosition,{},{c[5],c[6],c[7]});event(Event::CameraOffset,{},{c[8],c[9],0});
    event(Event::MapResources);
    event(Event::CameraPosition,{},{c[0],c[1],c[2]});event(Event::CameraOffset,{},{c[3],c[4],0});
    event(Event::Music,{0x16,0});
}
void ArcadeOpening::handOff(ArcadeRun& run) {
    // 1c1ac0(1c61b8, 1c1b20) wakes the task 1c1ae8; 1c6a30 marks the opening as shown.
    event(Event::HandOff,{int32_t(destructor),int32_t(ArcadeScene::Map)});
    handedOff=true;
    if(run.game.mode==1||run.game.mode==2)run.players[size_t(run.game.mode-1)].progress=1;
}
bool ArcadeOpening::openingText(const ArcadeFade& fade,bool alternate) {
    revealCount=0;
    const auto& rows=tables_.openingLines[alternate];
    for(size_t i=0;i<rows.size();++i) {
        const int length=int(tables_.strings.at(size_t(rows[i])).size());
        text(fade,rows[i],0x140-(length/2)*0xc,0xb4+0x18*int(i),0xffffffffu);
    }
    return revealed();
}
void ArcadeOpening::leave(ArcadeRun& run,ArcadeFade& fade) {
    events.clear();ops.clear();
    // 1c1de8 and this destructor clear the transition lock; 117180(200, 200, 0).
    fade.range(0x200,0x200,0);
    run.game.transitionLock=0;
}
void ArcadeOpening::tick(ArcadeRun& run,ArcadeFade& fade,ArcadeTalkObjects& objects,const ArcadeTalkInput& input) {
    events.clear();ops.clear();
    auto& g=run.game;
    const uint32_t pressed=input.pressed[g.mode==1?0:1];
    const bool alternate=run.system().setting(2)!=0;
    const auto step=[&] {objects.step(0);event(Event::ObjectStep,{0});};
    const auto animate=[&] {
        if(!object)return;
        if(objects.finished(0)) {objects.action(0,0x703);event(Event::ObjectAction,{0,0x703});}
        step();
    };
    if(!started) {
        started=true;
        if(g.mode==1||g.mode==2) {
            // The human's fighter walks in: action 704 at x f0, or mirrored at x 190 for seat 1.
            const int seat=g.mode-1,x=seat?0x190:0xf0,flags=seat?0x80000:0;
            const auto& player=run.players[size_t(seat)];
            object=true;character=player.character;
            objects.create(0,seat,0x704,x,0,uint32_t(flags),player.colour);
            event(Event::ObjectCreate,{0,seat,0x704,x,0,flags,player.colour});
        }
        fade.textColour=0xffffff;fade.textShadow=0x404040;   // 112f30
    }
    for(;;) switch(phase) {
    case Phase::Wait:
        // 0x22 visits behind the incoming fade; g+2c keeps the challenger out.
        g.transitionLock=1;
        if(wait>0) {--wait;return;}
        phase=Phase::Dim;
        continue;
    case Phase::Dim:
        // The map palette (entries 200..3ff) sinks to half black in eight steps.
        if(dim<0x80) {
            dim+=0x10;
            fade.set(0,dim);fade.range(0x200,0x200,2);
            return;
        }
        phase=Phase::Text;
        continue;
    case Phase::Text:
        if(hold>0) {
            colour(fade,0xffffffffu);
            revealLimit=quarter(reveal);++reveal;
            const bool done=openingText(fade,alternate);
            if(done)--hold;
            if(pressed&0x607) {if(done)hold=0;else reveal=0x2710;}
            if(!(pressed&8))return;
            skipped=1;
        }
        fade.range(0x200,0x200,0);
        g.transitionLock=0;
        if(skipped==1&&g.challengerFreeze==0)handOff(run);
        phase=Phase::Object;
        continue;
    case Phase::Object:
        if(object) {
            if(objects.finished(0)) {
                // 1c66ac: black text for the balloon; the seat-0 balloon is the mirrored record.
                fade.textColour=0;fade.textShadow=0xffffff;
                list=message(tables_.message(alternate,character,0,0));
                if(g.mode==1)list.balloon+=5;
                reveal=0;hold=0xb4;
                phase=Phase::Balloon;
                continue;
            }
            step();
        }
        if((pressed&8)&&g.challengerFreeze==0)handOff(run);
        return;
    case Phase::Balloon:
        if(hold>0) {
            colour(fade,0xffffffffu);
            revealLimit=quarter(reveal);++reveal;
            const bool done=balloon(fade,list,false,0);
            if(done)--hold;
            if(pressed&0x607) {if(done)hold=0;else reveal=0x2710;}
            if((pressed&8)&&g.challengerFreeze==0)handOff(run);
            animate();
            return;
        }
        phase=Phase::Fade;
        continue;
    case Phase::Fade:
        revealLimit=0x2710;
        colour(fade,0xffffffffu);
        balloon(fade,list,true,uint32_t(alpha)<<24|0xffffffu);
        animate();
        if(fadeCount>0) {
            if(g.challengerFreeze==0) {fadeCount-=8;alpha=fadeCount&0xff;}
        } else fadeCount=alpha=0;
        if(g.challengerFreeze==0&&latch==0&&fadeCount<=0) {handOff(run);latch=1;}
        return;
    }
}

// ---------------------------------------------------------------------
// Dialogue
std::array<int,2> ArcadeDialogue::select(int stage,int postFight) {
    if(stage==3&&postFight==0)return {3,4};
    if(stage==4&&postFight==1)return {4,3};
    if(stage==5&&postFight==0)return {5,4};
    if(stage==6&&postFight==1)return {6,4};
    if(stage==6&&postFight==0)return {7,4};
    if(stage==7&&postFight==1)return {8,1};
    return {0,0};
}
int ArcadeDialogue::bossKind(int character) {return character==0xd?2:character==0x1a?3:character==0x1b?1:0;}
int ArcadeDialogue::textType(int stage,int postFight,int page) {
    if(stage==3&&postFight==0)return page==1||page==3?1:page==0||page==2?2:0;
    if(stage==4&&postFight==1)return page==0||page==2?1:page==1?2:0;
    if(stage==5&&postFight==0)return page==1||page==3?1:page==0||page==2?2:0;
    if(stage==6&&postFight==1)return page==0||page==2||page==3?1:page==1?2:0;
    if(stage==6&&postFight==0)return page==3?1:uint32_t(page)<3?2:0;
    if(stage==7&&postFight==1)return page==0?1:0;
    return 0;
}
void ArcadeDialogue::enter(ArcadeRun& run,ArcadeFade& fade) {
    events.clear();ops.clear();
    auto& g=run.game;
    event(Event::StageBackground,{g.stage});
    const int index=g.mode==1?run.players[0].stageIndex:g.mode==2?run.players[1].stageIndex:0;
    const auto& c=tables_.talkCamera;
    event(Event::CameraPosition,{},{c[0],c[1],c[2]});event(Event::CameraOffset,{},{c[3],c[4],0});
    // 1c5438: 1828c0 (portraits unbound, balloons loaded, 182858 text colours), both fighters.
    portraits={-1,-1};
    fade.textColour=0xffffff;fade.textShadow=0x404040;
    event(Event::LoadCharacter,{0,run.players[0].character});
    event(Event::LoadCharacter,{1,run.players[1].character});
    // Jump table 655364 on the stage index.
    const int track=index==3||index==4?0x11:index==5?0x12:index==6?(run.dialoguePostFight==1?0x12:0x13):index==7?0x13:-1;
    if(track>=0)event(Event::Music,{track,1});
}
void ArcadeDialogue::leave(ArcadeRun& run,ArcadeFade&) {
    events.clear();ops.clear();
    run.dialoguePostFight=0;
    event(Event::StopMusic);
    event(Event::FreeStage);
}
void ArcadeDialogue::objectsStep(ArcadeTalkObjects& objects) {
    for(int k=0;k<2;++k) {
        if(objects.finished(k)) {objects.action(k,actions[size_t(k)]);event(Event::ObjectAction,{k,actions[size_t(k)]});}
        objects.step(k);event(Event::ObjectStep,{k});
    }
}
void ArcadeDialogue::request(ArcadeRun& run,ArcadeFade& fade,int kind,int speed,ArcadeScene next) {
    run.request(kind,speed,destructor,next);
    fade.beginTransition(kind);
    event(Event::Exit,{kind,speed,int32_t(destructor),int32_t(next)});
    leaving=1;
}
void ArcadeDialogue::exitToMap(ArcadeRun& run,ArcadeFade& fade) {
    // 17a548: the intruder banner replaces the black fade.
    if(run.intruderDue())request(run,fade,4,1,ArcadeScene::Map);
    else request(run,fade,2,0,ArcadeScene::Map);
}
void ArcadeDialogue::tick(ArcadeRun& run,ArcadeFade& fade,ArcadeTalkObjects& objects,const ArcadeTalkInput& input) {
    events.clear();ops.clear();
    auto& g=run.game;
    const int post=run.dialoguePostFight;
    const uint32_t pressed=input.pressed[g.mode==1?0:1];
    const bool alternate=run.system().setting(2)!=0;
    const float flashDepth=tables_.talkPan[1];
    const auto flash=[&] {auto& o=op(Op::Rect,fade);o.c=0x280;o.d=0x1e0;o.colour=0xffffffffu;o.f[0]=flashDepth;};
    const auto find=[&]() -> int {
        // 1c5dc0
        if(stage==6&&post==0) {
            if(page==3)return tables_.message(alternate,player,group,kind);
            return uint32_t(page)<3?tables_.kindMessage(alternate,kind,page):-1;
        }
        return tables_.message(alternate,player,group,stage==7&&post==1?kind:page);
    };
    const auto show=[&](int shownPage) {
        // 1c5e58
        const int type=textType(stage,post,shownPage);
        if(type==0)return false;
        const auto& m=message(list);
        return type==1?lines(fade,m,portraits[0]<0x34?0xd5:0x2b,0x36):lines(fade,m,0x2b,0x126);
    };
    if(!started) {
        started=true;
        actions=tables_.talkActions;
        // The loser of the fight just won stands in action 401.
        if(post==1) {if(g.mode==1)actions[1]=0x401;else if(g.mode==2)actions[0]=0x401;}
        for(int k=0;k<2;++k) {
            const int x=k?0x190:0xf0,flags=k?0x80000:0,tint=run.players[size_t(k)].colour;
            objects.create(k,k,actions[size_t(k)],x,0,uint32_t(flags),tint);
            event(Event::ObjectCreate,{k,k,actions[size_t(k)],x,0,flags,tint});
        }
        if(g.mode==1) {player=run.players[0].character;stage=run.players[0].stageIndex;opponent=run.players[1].character;}
        else if(g.mode==2) {opponent=run.players[0].character;stage=run.players[1].stageIndex;player=run.players[1].character;}
        const auto chosen=select(stage,post);
        group=chosen[0];pages=chosen[1];
        if((stage==6&&post==0)||(stage==7&&post==1))kind=bossKind(opponent);
        pan=tables_.talkPan[0];
        if(pages<=0) {lastPage=-1;phase=Phase::Post;}
    }
    // 1c59e0: the final boss has no portrait of its own after the fight.
    const bool single=stage==7&&post!=0;
    bool resume=false;
    const auto nextPage=[&] {
        ++page;
        if(page<pages)pageOpen=false;
        else {lastPage=page-1;phase=Phase::Post;}
    };
    for(;;) switch(phase) {
    case Phase::Page:
        if(!resume) {
            // Behind the yield of the previous frame: bgtz s5.
            if(pageOpen&&hold<=0) {nextPage();continue;}
            if(!pageOpen) {
                pageOpen=true;reveal=0;hold=0x10e;
                portrait(1,player);portrait(2,opponent);
                flashCount=0;list=find();
            }
            colour(fade,0xffffffffu);
            if(stage==6&&post==1&&flashArmed) {
                if(page==3) {
                    // 1c57f8: three white frames, one clear frame, three white frames.
                    g.transitionLock=1;
                    if(flashCount<3) {++flashCount;flash();}
                    else {++flashRounds;flashCount=0;flashArmed=flashRounds<2;}
                }
                if(!flashArmed) {
                    if(whiteArmed)phase=Phase::WhiteOut;
                    else {phase=Phase::WhiteHold;whiteHold=-1;}
                    continue;
                }
            }
        }
        resume=false;
        {
            portraitQuads(fade,true,!single);
            revealLimit=quarter(reveal);
            const bool done=show(page);
            ++reveal;
            if(done)--hold;
            if(pressed&0x607) {if(done)hold=0;else reveal=0x2710;}
            if((pressed&8)&&g.challengerFreeze==0&&!leaving) {
                if(post==0)request(run,fade,2,0,ArcadeScene::Battle);
                else if(stage==7) {
                    // 1c5d18: START ends the page at once; the pan cannot be skipped.
                    nextPage();
                    continue;
                }
                else exitToMap(run,fade);
            }
            objectsStep(objects);
            return;
        }
    case Phase::WhiteOut:
        portraitQuads(fade,true,true);
        objectsStep(objects);
        fade.setMode(2);fade.set(0xffffffffu,white);
        white+=8;
        whiteArmed=white<0x101;
        if(white>=0xf0)flash();
        if(!whiteArmed) {phase=Phase::WhiteHold;whiteHold=-1;}
        return;
    case Phase::WhiteHold:
        if(whiteHold<0) {
            // 1c5904: the arena is replaced behind the white screen.
            event(Event::FreeStage);event(Event::StopMusic);event(Event::StageBackground,{10});
            whiteHold=0x2d;
        }
        if(whiteHold>0) {
            fade.setMode(2);--whiteHold;fade.set(0xffffffffu,0x100);
            return;
        }
        phase=Phase::WhiteIn;
        continue;
    case Phase::WhiteIn:
        if(white>=0) {
            portraitQuads(fade,true,true);
            objectsStep(objects);
            fade.setMode(2);fade.set(0xffffffffu,white);
            white-=8;
            return;
        }
        whiteArmed=white<0x101;
        g.transitionLock=0;
        phase=Phase::Page;resume=true;
        continue;
    case Phase::Post:
        colour(fade,0xffffffffu);
        portraitQuads(fade,true,!single);
        revealLimit=0x2710;
        show(lastPage);
        objectsStep(objects);
        if(g.challengerFreeze==0&&!leaving) {
            if(post==0)request(run,fade,2,0,ArcadeScene::Battle);
            else if(stage!=7)exitToMap(run,fade);
            else {
                // 1c5c54: the camera pans down the arena before the pre-final demo.
                phase=Phase::Pan;
                continue;
            }
        }
        return;
    case Phase::Pan:
        event(Event::CameraLook,{},{tables_.talkPan[4],pan,0});
        pan=eeAdd(pan,tables_.talkPan[2]);
        objectsStep(objects);
        if(g.challengerFreeze==0&&!leaving&&tables_.talkPan[3]<=pan)request(run,fade,1,1,ArcadeScene::PreFinal);
        return;
    }
}

// ---------------------------------------------------------------------
// Pre-final demo
void ArcadePreFinal::enter(ArcadeRun& run,ArcadeFade&) {
    events.clear();ops.clear();
    auto& g=run.game;
    const auto& c=tables_.preFinalCamera;
    event(Event::CameraPosition,{},{c[0],c[1],c[2]});event(Event::CameraOffset,{},{c[3],c[4],0});
    if(g.mode==1||g.mode==2)run.players[size_t(g.mode-1)].preFinalSeen=0;   // 1c7cb0(0)
    run.prepareFight();
    event(Event::Music,{0x14,1});
}
void ArcadePreFinal::leave(ArcadeRun&,ArcadeFade& fade) {
    events.clear();ops.clear();
    event(Event::StopMusic);
    fade.range(0x200,0x200,0);
}
bool ArcadePreFinal::ease(std::array<float,12>& block,int32_t& steps) const {
    if(steps>=0x2d)return true;
    ++steps;
    // value = to - (to - from) * 30bd00(pi/2 - steps * pi / 45 / 2) through libgcc fp-bit
    // (310be0 widening, 310fa0 product, 310f38 difference, 311510 narrowing), all of
    // which truncate toward zero; the four components use the same sine.
    const double s=tables_.ease[size_t(steps-1)];
    const auto value=[&](float to,float from) {return narrowDouble(softAdd(double(to),-softMul(double(eeSub(to,from)),s)));};
    block[0]=value(block[6],block[4]);block[1]=value(block[7],block[5]);
    block[2]=value(block[10],block[8]);block[3]=value(block[11],block[9]);
    return steps>=0x2d;
}
void ArcadePreFinal::backdrop(const ArcadeFade& fade,float offset) {
    auto& o=op(Op::Backdrop,fade);
    o.f[0]=offset;
    for(size_t i=0;i<4;++i) {o.f[1+i]=first[i];o.f[5+i]=second[i];}
}
void ArcadePreFinal::exit(ArcadeRun& run,ArcadeFade& fade) {
    auto& g=run.game;
    run.request(1,2,destructor,ArcadeScene::Battle);
    fade.beginTransition(1);
    event(Event::Exit,{1,2,int32_t(destructor),int32_t(ArcadeScene::Battle)});
    fade.range(0x200,0x200,0);
    if(g.mode==1||g.mode==2)run.players[size_t(g.mode-1)].preFinalSeen=1;   // 1c7cb0(1)
}
bool ArcadePreFinal::start(const ArcadeRun& run,const ArcadeTalkInput& input) const {
    return run.game.challengerFreeze==0&&(input.pressed[run.game.mode==1?0:1]&8);
}
void ArcadePreFinal::advanceScroll() {
    const auto& f=tables_.preFinal;
    scroll=scroll<f[13]?eeAdd(scroll,f[14]):f[13];
}
void ArcadePreFinal::tick(ArcadeRun& run,ArcadeFade& fade,const ArcadeTalkInput& input) {
    events.clear();ops.clear();
    const auto& f=tables_.preFinal;
    const bool alternate=run.system().setting(2)!=0;
    const auto caption=[&](int record,uint32_t tint,float x,float y) {
        auto& o=op(Op::Sheet,fade);o.a=record;o.colour=tint;o.f={x,y,f[6]};
    };
    const auto box=[&] {
        auto& o=op(Op::Rect,fade);
        o.a=0;o.b=int(f[15]);o.c=int(f[5]);o.d=int(f[16]);o.colour=uint32_t(boxAlpha)|0x404040u;o.f[0]=f[6];
    };
    const auto skip=[&] {
        if(start(run,input)&&skipIssued==0) {exit(run,fade);skipIssued=1;}
    };
    if(!started) {
        started=true;
        fade.textColour=0xffffff;fade.textShadow=0x404040;
        first={f[1],f[2],f[3],f[4]};
        second={0,f[0],f[5],eeSub(f[0],float(tables_.sheets[3].w))};
        event(Event::Voice,{0x31,0x35});
        count=0x3c;
    }
    for(;;) switch(phase) {
    case Phase::Captions:
        if(count>0) {
            // The picture palette (200..2ff) is held at full white; the incoming
            // transition lowers the level once this phase stops rewriting it.
            fade.setMode(0);fade.set(0xffffffffu,0x100);fade.range(0x200,0x200,2);
            backdrop(fade,0);
            caption(0,0xffffffffu,f[7],f[8]);caption(1,0xffffffffu,f[9],f[10]);
            --count;
            return;
        }
        phase=Phase::CaptionFade;count=0x3c;
        continue;
    case Phase::CaptionFade:
        if(count>0) {
            backdrop(fade,0);
            if(fadeStep!=0x1e) {
                const uint32_t tint=uint32_t((fadeStep*-0xff)/0x1e +0xff)<<24|0xffffffu;
                ++fadeStep;
                caption(0,tint,f[7],f[8]);caption(1,tint,f[9],f[10]);
            }
            --count;
            return;
        }
        phase=Phase::Zoom;count=0;
        first[4]=f[1];first[5]=f[2];first[6]=0;first[7]=f[11];first[8]=f[3];first[9]=f[4];first[10]=f[5];first[11]=f[12];
        continue;
    case Phase::Zoom:
        if(!ease(first,count)) {backdrop(fade,0);return;}
        phase=Phase::Rest;count=10;
        continue;
    case Phase::Rest:
        if(count>0) {backdrop(fade,0);--count;return;}
        phase=Phase::Box;count=0x1e;boxStep=0;
        continue;
    case Phase::Box:
        if(count>0) {
            backdrop(fade,scroll);
            advanceScroll();
            boxAlpha=int32_t(uint32_t(boxStep*0xc0/0x1e)<<24);
            ++boxStep;
            box();
            if(boxStep>=0x1f)boxStep=0x1e;
            --count;
            return;
        }
        phase=Phase::Text;page=0;fresh=true;
        continue;
    case Phase::Text:
        if(fresh) {fresh=false;list=tables_.kindMessage(alternate,4,page);reveal=0;count=0xb4;}
        if(count>0) {
            colour(fade,0xffffffffu);
            box();
            revealLimit=quarter(reveal);++reveal;
            if(centred(fade,message(list)))--count;
            skip();
            backdrop(fade,scroll);
            advanceScroll();
            return;
        }
        if(++page<3) {fresh=true;continue;}
        phase=Phase::Scroll;
        continue;
    case Phase::Scroll:
        if(scroll<f[13]) {
            backdrop(fade,scroll);
            advanceScroll();
            skip();
            return;
        }
        phase=Phase::Pause;count=0x1e;
        continue;
    case Phase::Pause:
        if(count>0) {
            backdrop(fade,scroll);
            --count;
            skip();
            return;
        }
        // 1c7618: both quads leave from where the scroll put them.
        first[4]=first[0];first[5]=eeAdd(first[1],scroll);first[6]=f[17];first[7]=f[19];
        first[8]=first[2];first[9]=eeAdd(first[3],scroll);first[10]=f[18];first[11]=f[20];
        second[4]=0;second[5]=eeAdd(second[1],scroll);second[6]=f[17];second[7]=f[21];
        second[8]=f[5];second[9]=eeAdd(second[3],scroll);second[10]=f[18];second[11]=f[22];
        count=count2=0;
        phase=Phase::Leave;
        continue;
    case Phase::Leave:
        // The exit is requested on the first visit; the move runs under the fade.
        if(ease(first,count)||ease(second,count2)) {phase=Phase::Still;continue;}
        backdrop(fade,0);
        if(run.game.challengerFreeze==0&&exitIssued==0) {exit(run,fade);exitIssued=1;}
        if(start(run,input))exit(run,fade);   // 1c77b4: no latch on this path
        return;
    case Phase::Still:
        backdrop(fade,0);
        return;
    }
}

// ---------------------------------------------------------------------
ArcadeTalkArt::ArcadeTalkArt(const std::filesystem::path& assets,const ArcadeTalkTables& tables):assets_(assets),tables_(tables) {
    const char* names[4]={"hukidasi.tex","hukidasi2.tex","moji4.tex","moji5.tex"};
    for(size_t i=0;i<4;++i)sheets_[i]=load(assets/names[i],512*512/2);
    picture_=load(assets/"demo_mga.tex",1024*1024);
    const auto pal=load(assets/"demo_mga.pal",512);
    for(unsigned i=1;i<256;++i)pictureSource_[i]=uint16_t(pal[2*i]|pal[2*i+1]<<8);
    // 113890: obj0.pal entries 0..7f with entry 0 of each bank cleared.
    const auto resident=load(assets/"obj0.pal",512);
    for(unsigned i=0;i<128;++i)residentSource_[i]=i%16?uint16_t(resident[2*i]|resident[2*i+1]<<8):uint16_t(0);
}
const ArcadeTalkArt::Portrait& ArcadeTalkArt::portrait(int id) {
    auto found=portraits_.find(id);
    if(found!=portraits_.end())return found->second;
    char name[32];
    std::snprintf(name,sizeof name,"demo_%02d",id);
    Portrait p;
    p.pixels=load(assets_/(std::string(name)+".tex"),256*256);
    // 1a19c0: 0x40 colours from file entry c0 to resident entries c0 / 1c0.
    const auto pal=load(assets_/(std::string(name)+".pal"),512);
    for(unsigned i=0;i<64;++i)p.palette[i]=uint16_t(pal[2*(0xc0+i)]|pal[2*(0xc0+i)+1]<<8);
    return portraits_.emplace(id,std::move(p)).first->second;
}

void ArcadeTalkArt::rasterise(const MenuCanvas& canvas,const MenuDrawList& list,std::span<uint8_t> rgba,const ArcadeFade& fade,
                              std::array<int32_t,2> portraits) {
    if(rgba.size()!=size_t(width)*height*4)throw std::invalid_argument("Expected a 640x480 arcade talk surface");
    using Colour=std::array<uint8_t,4>;
    // Resident CLUT views of this frame.
    std::array<Colour,16> bank{},glyphs{};
    for(unsigned i=0;i<16;++i) {bank[i]=fade.resident(i,residentSource_[i]);glyphs[i]=fade.glyph(i);}
    std::array<Colour,256> picture{};
    for(unsigned i=0;i<256;++i)picture[i]=fade.resident(0x200+i,pictureSource_[i]);
    std::array<std::array<Colour,256>,2> face{};
    std::array<const Portrait*,2> faces{};
    for(unsigned side=0;side<2;++side) {
        if(uint32_t(portraits[side])>=0x31||portraits[side]==43)continue;
        faces[side]=&portrait(portraits[side]);
        for(unsigned i=0;i<256;++i) {
            // Slot 0x22 is bound with bank 0, slot 0x23 with bank 0x10 (1828c0).
            const uint16_t source=i>=0xc0?faces[side]->palette[i-0xc0]:side==0&&i<128?residentSource_[i]:uint16_t(0);
            face[side][i]=fade.resident(0x100*side+i,source);
        }
    }
    const auto texel=[&](int slot,int tu,int tv,Colour& out) {
        const int size=sheetSize(slot);
        if(tu<0||tv<0||tu>=size||tv>=size)return false;
        switch(slot) {
        case 5:out=picture[picture_[size_t(tv)*1024+size_t(tu)]];return true;
        case 0x22:case 0x23: {
            const unsigned side=unsigned(slot-0x22);
            if(!faces[side])return false;
            out=face[side][faces[side]->pixels[size_t(tv)*256+size_t(tu)]];return true;
        }
        default: {
            const auto& sheet=sheets_[slot==0x1f?0:slot==0x20?1:slot==0xc?2:3];
            out=bank[(sheet[size_t(tv)*256+size_t(tu/2)]>>(4*(tu&1)))&15];return true;
        }
        }
    };
    const auto put=[&](int px,int py,const Colour& source,uint32_t tint,bool additive) {
        int s[4];
        for(int c=0;c<4;++c)s[c]=std::min(255,int(source[size_t(c)])*int((tint>>(8*c))&255)/128);
        auto* dst=rgba.data()+4*(size_t(py)*width+size_t(px));
        // Tag 2ff2: ALPHA preset 348bc0, Cd + Cs.
        if(additive)for(int c=0;c<3;++c)dst[c]=uint8_t(std::min(255,dst[c]+s[c]));
        else for(int c=0;c<3;++c)dst[c]=uint8_t(std::clamp(dst[c]+(((s[c]-dst[c])*s[3])>>7),0,255));
    };
    const auto floorDiv=[](long long a,long long b) {
        long long q=a/b;
        if((a%b!=0)&&((a<0)!=(b<0)))--q;
        return q;
    };
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
        if(q.kind==MenuPrimitive::Glyph) {
            flush();
            if(q.font!=MenuFont::Goth24)throw std::invalid_argument("Arcade talk text uses GOTH_24 glyphs only");
            const auto found=tables_.glyphs.find(q.glyph);
            if(found==tables_.glyphs.end())throw std::invalid_argument("Glyph row missing from arcade_talk.bin");
            const int x=int(q.x),y=int(q.y);
            for(int j=0;j<24;++j)for(int i=0;i<24;++i) {
                const int px=x+i,py=y+j;
                if(px<0||py<0||px>=width||py>=height)continue;
                put(px,py,glyphs[(found->second[size_t(j)*12+size_t(i/2)]>>(4*(i&1)))&15],q.colour,false);
            }
            continue;
        }
        if(q.kind!=MenuPrimitive::Quad&&q.kind!=MenuPrimitive::Rotated) {pending.records.push_back(q);continue;}
        flush();
        // Vertex order of 113f98 / 114118: (u0,v0), (u0,v1), (u1,v0), (u1,v1).
        float vx[4],vy[4];
        const float tu[4]={q.u,q.u,q.u+q.uw,q.u+q.uw},tv[4]={q.v,q.v+q.vh,q.v,q.v+q.vh};
        if(q.kind==MenuPrimitive::Quad) {
            vx[0]=vx[1]=q.x;vx[2]=vx[3]=q.x+q.w;vy[0]=vy[2]=q.y;vy[1]=vy[3]=q.y+q.h;
        } else for(int i=0;i<4;++i) {vx[i]=q.corner[size_t(2*i)];vy[i]=q.corner[size_t(2*i+1)];}
        bool aligned=vx[0]==vx[1]&&vy[0]==vy[2]&&vx[3]==vx[2]&&vy[3]==vy[1];
        for(int i=0;i<4&&aligned;++i)
            aligned=vx[i]==std::floor(vx[i])&&vy[i]==std::floor(vy[i])&&tu[i]==std::floor(tu[i])&&tv[i]==std::floor(tv[i]);
        Colour source;
        if(aligned) {
            // Texel under each pixel centre, integer form of the reference painter.
            const long long x0=(long long)vx[0],y0=(long long)vy[0],x1=(long long)vx[2],y1=(long long)vy[1];
            const long long u0=(long long)tu[0],v0=(long long)tv[0],u1=(long long)tu[2],v1=(long long)tv[1];
            if(x0==x1||y0==y1)continue;
            for(long long py=std::max(0LL,std::min(y0,y1));py<std::min<long long>(height,std::max(y0,y1));++py) {
                const int sv=int(v0+floorDiv((2*py+1-2*y0)*(v1-v0),2*(y1-y0)));
                for(long long px=std::max(0LL,std::min(x0,x1));px<std::min<long long>(width,std::max(x0,x1));++px) {
                    const int su=int(u0+floorDiv((2*px+1-2*x0)*(u1-u0),2*(x1-x0)));
                    if(texel(q.slot,su,sv,source))put(int(px),int(py),source,q.colour,q.additive);
                }
            }
            continue;
        }
        // Inverse-affine pixel-centre model of validate_menu_canvas.py.
        const float minX=std::min({vx[0],vx[1],vx[2],vx[3]}),maxX=std::max({vx[0],vx[1],vx[2],vx[3]});
        const float minY=std::min({vy[0],vy[1],vy[2],vy[3]}),maxY=std::max({vy[0],vy[1],vy[2],vy[3]});
        const int left=std::max(0,int(std::floor(minX))),right=std::min(width-1,int(std::ceil(maxX)));
        const int top=std::max(0,int(std::floor(minY))),bottom=std::min(height-1,int(std::ceil(maxY)));
        const double ax=double(vx[2])-vx[0],ay=double(vy[2])-vy[0],bx=double(vx[1])-vx[0],by=double(vy[1])-vy[0];
        const double det=ax*by-ay*bx;
        if(det==0)continue;
        for(int py=top;py<=bottom;++py)for(int px=left;px<=right;++px) {
            const double dx=px+0.5-double(vx[0]),dy=py+0.5-double(vy[0]);
            const double s=(dx*by-dy*bx)/det,t=(ax*dy-ay*dx)/det;
            if(!(s>=0&&s<1&&t>=0&&t<1))continue;
            const double fu=std::floor(double(tu[0])+s*(double(tu[2])-double(tu[0])));
            const double fv=std::floor(double(tv[0])+t*(double(tv[1])-double(tv[0])));
            if(texel(q.slot,int(fu),int(fv),source))put(px,py,source,q.colour,q.additive);
        }
    }
    flush();
}
}
