#include "arcade_art.hpp"
#include "scalar_float.hpp"

#include <algorithm>
#include <bit>
#include <cmath>
#include <cstring>
#include <fstream>
#include <numeric>
#include <stdexcept>
#include <string>

namespace ss6 {
namespace {
constexpr int width=640,height=480;
constexpr int hudSlot=0x0a,sceneSlot=0x0c,coinSlot=0x28;

std::vector<uint8_t> load(const std::filesystem::path& file,size_t size) {
    std::ifstream in(file,std::ios::binary|std::ios::ate);
    if(!in||in.tellg()!=static_cast<std::streamoff>(size))
        throw std::runtime_error("Invalid arcade art resource: "+file.string());
    std::vector<uint8_t> bytes(size);
    in.seekg(0);
    if(!in.read(reinterpret_cast<char*>(bytes.data()),std::streamsize(size)))
        throw std::runtime_error("Truncated arcade art resource: "+file.string());
    return bytes;
}
ScalarFloat scalar(float v) {return ScalarFloat{std::bit_cast<uint32_t>(v)};}
float real(ScalarFloat v) {return std::bit_cast<float>(v.bits);}
float mul(float a,float b) {return real(scalar(a).mul(scalar(b)));}
MenuSheetRect rect(const ArcadeSpriteRecord& r) {return {r.u,r.v,r.w,r.h};}
int sheetSize(int slot) {return slot==coinSlot?128:512;}

// 108118 (10849c..108514): after scaling to texels every vertex coordinate
// above size-1 is replaced by size-1. Applies to the last record of the list.
void clampSpan(MenuDrawRecord& r) {
    const float limit=float(sheetSize(r.slot)-1);
    const float u1=std::min(r.u+r.uw,limit),v1=std::min(r.v+r.vh,limit);
    r.u=std::min(r.u,limit);r.v=std::min(r.v,limit);r.uw=u1-r.u;r.vh=v1-r.v;
}
// 117de8 for the sheets of this module. 10add8 stores `flags & ~0x200` as the
// CLUT bank of a 4-bit sheet (type 0x14); 8-bit sheets (type 0x13) keep bank
// flags / 16, which is zero for every caller here.
void sheet(const MenuCanvas& canvas,MenuDrawList& list,const ArcadeSpriteRecord& r,unsigned flags,uint32_t colour,
           bool mirror,float x,float y,float z,float w,float h) {
    const size_t before=list.records.size();
    canvas.sprite(list,rect(r),r.texture,flags,colour,mirror,x,y,z,w,h);
    if(list.records.size()==before)return;
    auto& q=list.records.back();
    if(q.slot==sceneSlot)q.glyph=uint16_t(flags&0xffu&~0x200u);
    clampSpan(q);
}
// 1149d0 colour word of 3db900 without the 117288 fade: slot 0x28 is the one
// path of the public 113f98 emitter that skips the fade.
uint32_t queueColour(const MenuCanvas& canvas,MenuDrawList& list) {
    const int depth=list.depth;
    canvas.sprite(list,coinSlot,0,0,0,1,1,0,0,1,1);
    const uint32_t colour=list.records.back().colour;
    list.records.pop_back();list.depth=depth;
    return colour;
}
// 114118: textured quad through four explicit corners; texel (u,v) at P0,
// (u,v+vh) at P1, (u+uw,v) at P2 and (u+uw,v+vh) at P3. The colour is 3db900
// as it stands (no 117288 fade), the blend selector 3db8fc.
void quad4(const MenuCanvas& canvas,MenuDrawList& list,int slot,float x0,float y0,float x1,float y1,float x2,float y2,
           float x3,float y3,float z,float u,float v,float uw,float vh) {
    // 114f20, the four-corner form of the 114e98 window test.
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
void mix(uint8_t* dst,const int* source) {
    for(int c=0;c<3;++c)dst[c]=uint8_t(std::clamp(dst[c]+(((source[c]-dst[c])*source[3])>>7),0,255));
}
}

ArcadeArtTables::ArcadeArtTables(const std::filesystem::path& assets) {
    const auto raw=load(assets/"arcade_art.bin",700);
    if(std::memcmp(raw.data(),"AART\1\0\0\0",8))throw std::runtime_error("Mismatched arcade_art.bin");
    size_t at=8;
    const auto take=[&](void* to,size_t n) {std::memcpy(to,raw.data()+at,n);at+=n;};
    take(&continueTitle,24);take(continueDigits.data(),240);take(continueFloats.data(),44);
    take(&gameOverText,24);take(&gameOverTitle,24);take(gameOverFloats.data(),28);
    take(gameOverShake.data(),64);take(gameOverTail.data(),28);take(scoreNegative.data(),216);
}

ArcadeArt::ArcadeArt(const std::filesystem::path& assets):tables_(assets) {
    hud_=load(assets/"obj2_16.tex",512*512+1024);
    for(unsigned i=0;i<256;++i) {
        // Slot 0xa carries an appended 16x16 CLUT like slot 1; CSM1 exchanges index bits 3/4.
        const unsigned j=(i&~24u)|((i&8u)<<1)|((i&16u)>>1);
        std::copy_n(hud_.data()+512*512+4*j,4,hudColours_[i].begin());
    }
    hud_.resize(512*512);
    // Slot 0x28: 1099f0 uploads the appended CLUT in 8x2 strips, which keeps the file order.
    coin_=load(assets/"font_coin.tex",128*128+1024);
    for(unsigned i=0;i<256;++i)std::copy_n(coin_.data()+128*128+4*i,4,coinColours_[i].begin());
    coin_.resize(128*128);
    // Slot 0xc: two 4-bit texels per byte, low nibble first, coloured by banks
    // 0 and 1 of the resident obj0 CLUT; 113890 clears entry 0 of each bank.
    scene_=load(assets/"font_otherscene16.tex",512*512/2);
    const auto pal=load(assets/"obj0.pal",512);
    for(unsigned i=0;i<32;++i)bankSource_[i]=i%16?uint16_t(pal[2*i]|pal[2*i+1]<<8):uint16_t(0);
    rebuildBanks();
}

void ArcadeArt::setFade(bool enabled,int level,uint32_t colour) {
    if(level<0||level>256)throw std::invalid_argument("Invalid arcade art fade level");
    fadeEnabled_=enabled;fadeLevel_=level;fadeColour_=colour;
    rebuildBanks();
}
void ArcadeArt::rebuildBanks() {
    // 116588: 5-bit interpolation toward 3ec730 while a fade runs; entries
    // without the 0x8000 bit stay fully transparent.
    const bool active=fadeEnabled_&&fadeLevel_>0;
    for(unsigned i=0;i<32;++i) {
        const auto v=bankSource_[i];
        auto& out=bankColours_[i/16][i%16];out={};
        if(!(v&0x8000))continue;
        for(int c=0;c<3;++c) {
            const int five=(v>>(10-5*c))&31,tone=int((fadeColour_>>(8*(2-c)))&255)>>3;
            out[size_t(c)]=uint8_t((active?(five*(256-fadeLevel_)+tone*fadeLevel_)>>8:five)<<3);
        }
        out[3]=128;
    }
}

void ArcadeArt::rasterise(const MenuCanvas& canvas,const MenuDrawList& list,std::span<uint8_t> rgba,
                          size_t first,size_t count) const {
    if(rgba.size()!=size_t(width)*height*4)throw std::invalid_argument("Expected a 640x480 arcade overlay surface");
    first=std::min(first,list.records.size());
    count=std::min(count,list.records.size()-first);
    std::vector<unsigned> order(count);
    std::iota(order.begin(),order.end(),unsigned(first));
    std::stable_sort(order.begin(),order.end(),[&](unsigned a,unsigned b) {return list.records[a].z<list.records[b].z;});
    MenuDrawList pending;
    const auto flush=[&] {
        if(pending.records.empty())return;
        canvas.rasterise(pending,rgba);pending.records.clear();
    };
    const auto integral=[](float value) {
        if(value!=std::floor(value)||std::abs(value)>32768)throw std::invalid_argument("Arcade quad needs integral geometry");
        return int(value);
    };
    for(const unsigned at:order) {
        const auto& q=list.records[at];
        const bool own=q.kind==MenuPrimitive::Quad&&(q.slot==hudSlot||q.slot==sceneSlot||q.slot==coinSlot);
        if(!own) {pending.records.push_back(q);continue;}
        flush();
        const int x=integral(q.x),y=integral(q.y),w=integral(q.w),h=integral(q.h);
        const int u=integral(q.u),v=integral(q.v),uw=integral(q.uw),vh=integral(q.vh);
        if(!w||!h)continue;
        const int size=sheetSize(q.slot);
        int mod[4];
        for(int c=0;c<4;++c)mod[c]=int((q.colour>>(8*c))&255);
        const int left=std::min(x,x+w),top=std::min(y,y+h),nx=std::abs(w),ny=std::abs(h);
        for(int py=std::max(0,top);py<std::min(height,top+ny);++py) {
            const int j=h>0?py-top:ny-1-(py-top);
            const int tv=v+((2*j+1)*vh)/(2*ny);
            for(int px=std::max(0,left);px<std::min(width,left+nx);++px) {
                const int i=w>0?px-left:nx-1-(px-left);
                const int tu=u+((2*i+1)*uw)/(2*nx);
                if(tu<0||tv<0||tu>=size||tv>=size)continue;
                const uint8_t* texel;
                if(q.slot==hudSlot)texel=hudColours_[hud_[size_t(tv)*512+size_t(tu)]].data();
                else if(q.slot==coinSlot)texel=coinColours_[coin_[size_t(tv)*128+size_t(tu)]].data();
                else texel=bankColours_[q.glyph&1u][(scene_[size_t(tv)*256+size_t(tu/2)]>>(4*(tu&1)))&15].data();
                int source[4];
                for(int c=0;c<4;++c)source[c]=std::min(255,texel[c]*mod[c]/128);
                auto* dst=rgba.data()+4*(size_t(py)*width+size_t(px));
                // Tag 2ff2 (latch 348b10): ALPHA preset 348bc0, Cd + Cs.
                if(q.additive)for(int c=0;c<3;++c)dst[c]=uint8_t(std::min(255,dst[c]+source[c]));
                else mix(dst,source);
            }
        }
    }
    flush();
}

// ---------------------------------------------------------------------
void drawArcadeScore(const MenuCanvas& canvas,MenuDrawList& list,const ArcadeTallyTables& tally,const ArcadeArtTables& art,
                     int hudMode,int submode,int32_t score) {
    // 1bac20..1bac44: skipped in sub-mode 5 and outside modes 1 / 2.
    if(submode==5||(hudMode!=1&&hudMode!=2))return;
    // 1bc098 -> 1ba768(x, y 0x10, depth -0x12d, value, pitch = digit 0 width, records 4c5ae8, flags 0).
    int x=tally.scoreX[size_t(hudMode-1)];
    const int pitch=tally.scoreDigits[0].w,count=arcadeDigits(score);
    int64_t power=1;
    for(int i=0;i<count;++i,power*=10) {
        // (value / 10^i) % 10 with truncating division: a negative score
        // selects the records in front of the table.
        const int digit=int((int64_t(score)/int32_t(power))%10);
        const auto& r=digit<0?art.scoreNegative[size_t(digit+9)]:tally.scoreDigits[size_t(digit)];
        sheet(canvas,list,r,0,0xffffffffu,false,float(x),16.0f,-301.0f,float(r.w),float(r.h));
        x-=pitch;
    }
}

bool drawFreeSeatPrompt(const MenuCanvas& canvas,MenuDrawList& list,const ArcadeTallyTables& tally,FreeSeatPrompt& clock,
                        int gameMode,int submode,bool enabled,bool latched) {
    if(!enabled||(gameMode!=0&&submode==5))return false;
    if(!clock.tick())return false;
    const float z=tally.promptDepth;
    // 1b8e28 always submits through slot 0x28, whatever the record names.
    const auto piece=[&](const ArcadeSpriteRecord& r,int x,int y) {
        list.blend=1;list.colour=0xffffffffu;
        const size_t count=list.records.size();
        canvas.sprite(list,coinSlot,float(x),float(y),z,float(r.w),float(r.h),float(r.u),float(r.v),float(r.w),float(r.h));
        if(list.records.size()!=count)clampSpan(list.records.back());
    };
    const auto legend=[&](int x,int y) {
        for(unsigned i=0;i<3;++i) {piece(tally.promptRecords[i],x,y);x+=tally.promptRecords[i].w;}
    };
    const size_t before=list.records.size();
    if(gameMode==0) {
        // 1ba228: the attract demo's single centred legend.
        if(latched)piece(tally.promptRecords[3],tally.promptPositions[1][0],tally.promptPositions[1][1]);
        else legend(tally.promptPositions[0][0],tally.promptPositions[0][1]);
        return list.records.size()!=before;
    }
    // 1ba448. The two status bytes it tests are left unwritten by the empty
    // platform hooks 110ae8 / 110af0; a zeroed stack selects the drawn branch.
    for(int seat=0;seat<2;++seat) {
        if(!(FreeSeatPrompt::seats(gameMode)&(1<<seat)))continue;
        if(latched) {
            const auto& at=tally.promptPositions[size_t(4+seat)];
            piece(tally.promptRecords[3],at[0],at[1]);
            continue;
        }
        const auto& at=tally.promptPositions[size_t(2+seat)];
        // 1b9880 submits the first piece once more before the three-piece loop.
        piece(tally.promptRecords[0],at[0],at[1]);
        legend(at[0],at[1]);
    }
    return list.records.size()!=before;
}

void drawArcadeTally(const MenuCanvas& canvas,MenuDrawList& list,const ArcadeTallyTables& tally,const ArcadeTallyDraw& draw) {
    if(!draw.visible)return;
    const auto& f=tally.panelFloats;
    const auto& p=tally.panelPieces;
    const auto fl=[](int32_t v) {return float(v);};
    const uint32_t white=0xffffffffu;
    // 1c8bf8 top edge; the piece's +0x10 word (5) is passed as the flag argument.
    const auto top=[&](const ArcadeSpriteRecord& r,float x,bool mirror) {
        sheet(canvas,list,r,5,white,mirror,x,f[1],f[2],fl(r.w),fl(r.h));
    };
    top(p[0],f[0],false);
    float x=f[3];
    for(int i=0;i<8;++i) {top(p[1],x,false);x=eeAdd(x,f[4]);}
    top(p[2],x,false);
    for(int i=0;i<8;++i) {x=eeAdd(x,f[4]);top(p[1],x,false);}
    x=eeAdd(x,f[4]);
    top(p[0],x,true);
    // 1c8df0 left edge: pieces turned through 114118, one texel short in u.
    list.blend=1;list.colour=white;
    float y=f[5];
    const auto left=[&](const ArcadeSpriteRecord& r) {
        const float previous=y;
        y=eeAdd(y,f[7]);
        quad4(canvas,list,r.texture,f[6],y,f[8],y,f[6],previous,f[8],previous,f[9],fl(r.u),fl(r.v),eeSub(fl(r.w),f[10]),fl(r.h));
    };
    for(int i=0;i<5;++i)left(p[1]);
    left(p[2]);
    for(int i=0;i<5;++i)left(p[1]);
    // 1c9040 right edge.
    list.blend=1;list.colour=white;
    y=f[11];
    const auto right=[&](const ArcadeSpriteRecord& r) {
        const float previous=y;
        y=eeAdd(y,f[14]);
        quad4(canvas,list,r.texture,f[12],previous,f[13],previous,f[12],y,f[13],y,f[15],fl(r.u),fl(r.v),fl(r.w),fl(r.h));
    };
    for(int i=0;i<5;++i)right(p[1]);
    right(p[2]);
    for(int i=0;i<5;++i)right(p[1]);
    // 1c9258 bottom edge: one texel short in both directions.
    const auto bottom=[&](const ArcadeSpriteRecord& r,float xa,float xb) {
        quad4(canvas,list,r.texture,xa,f[18],xa,f[20],xb,f[18],xb,f[20],f[21],fl(r.u),fl(r.v),
              eeSub(fl(r.w),f[16]),eeSub(fl(r.h),f[16]));
    };
    // The first corner alone runs its u axis downwards.
    quad4(canvas,list,p[0].texture,f[17],f[18],f[19],f[18],f[17],f[20],f[19],f[20],f[21],fl(p[0].u),fl(p[0].v),
          eeSub(fl(p[0].w),f[16]),eeSub(fl(p[0].h),f[16]));
    x=f[19];
    for(int i=0;i<8;++i) {const float next=eeAdd(x,f[22]);bottom(p[1],next,x);x=next;}
    bottom(p[2],eeAdd(x,f[22]),x);
    for(int i=0;i<8;++i) {x=eeAdd(x,f[22]);bottom(p[1],eeAdd(x,f[22]),x);}
    x=eeAdd(x,f[22]);
    bottom(p[0],eeAdd(x,f[22]),x);
    // 1c95a0 interior: eleven rows of 9 + 8 translucent tiles in a checker pattern.
    for(int row=0;row<11;++row) {
        const int first=row&1?3:4,second=first==4?3:4;
        const float base=mul(float(row),f[25]);
        for(int i=0;i<9;++i)
            sheet(canvas,list,p[size_t(first)],0,0xa0ffffffu,false,eeAdd(mul(float(i),f[23]),f[24]),eeAdd(base,f[26]),f[27],
                  fl(p[size_t(first)].w),fl(p[size_t(first)].h));
        for(int i=0;i<8;++i)
            sheet(canvas,list,p[size_t(second)],0,0xa0ffffffu,false,eeAdd(mul(float(i),f[23]),f[28]),eeAdd(base,f[26]),f[27],
                  fl(p[size_t(second)].w),fl(p[size_t(second)].h));
    }
    // 113028 -> 1130f8 -> 10a010: half-width 12x24 glyphs at the depth 114e40(3d3aac),
    // which has no tie-break increment; 0x0a returns to x and adds 0x18.
    const int saved=list.textDepth;
    list.textDepth=int(real(scalar(10000000.0f).sub(scalar(list.asciiDepth).mul(scalar(100.0f)))));
    for(const auto& text:draw.texts(tally))
        canvas.text24(list,text.text,text.x,text.y,int((text.colour>>16)&255),int((text.colour>>8)&255),
                      int(text.colour&255),int(text.colour>>24));
    list.textDepth=saved;
}

int32_t arcadeArtCubic(int32_t step,int32_t total,int32_t p0,int32_t p1,int32_t p2,int32_t p3,float one,float three) {
    using F=ScalarFloat;
    // Instruction order of 1382a8; MULA / MADDA / MADD round the product and
    // the accumulation separately in the finite model.
    const F t=F::integer(step).div(F::integer(total));
    F f5=t.mul(t);
    const F s=scalar(one).sub(t);
    f5=f5.mul(t);
    F f1=s.mul(scalar(three));
    F f4=s.mul(s);
    F f3=f1.mul(s);
    f4=f4.mul(s);
    f1=f1.mul(t);
    f3=f3.mul(t);
    F acc=f4.mul(F::integer(p0));
    f1=f1.mul(t);
    acc=acc.add(f3.mul(F::integer(p1)));
    acc=acc.add(f1.mul(F::integer(p2)));
    return acc.add(f5.mul(F::integer(p3))).truncate();
}

ArcadeFighterRequest drawArcadeContinue(const MenuCanvas& canvas,MenuDrawList& list,const ArcadeArtTables& art,
                                        const ArcadeContinueDraw& draw) {
    const auto& c=art.continueFloats;
    const auto fl=[](int32_t v) {return float(v);};
    // 137d40: the title through CLUT bank 1 (flag argument 1).
    const auto& title=art.continueTitle;
    sheet(canvas,list,title,1,0xffffffffu,false,c[0],c[1],c[2],fl(title.w),fl(title.h));
    // 137db8. Every digit uses the size of record 0.
    const uint32_t remaining=draw.remaining;
    if(remaining) {
        list.colour=0xffffffffu;list.blend=1;
        const uint32_t seconds=remaining/60;
        const int phase=int(remaining%60);
        const int w=art.continueDigits[0].w,h=art.continueDigits[0].h;
        // Scaled variant of the last 21 frames of a second: the width runs
        // w, w/16, 10w, 10w and the height h, 2h, 0, 0 over 20 steps while the
        // alpha falls 11 per frame.
        const auto digit=[&](uint32_t value,int column,bool tens) {
            const auto& r=art.continueDigits[value];
            if(phase>=0x15) {
                if(tens)sheet(canvas,list,r,1,0xffffffffu,false,c[3],c[4],c[5],fl(r.w),fl(r.h));
                else sheet(canvas,list,r,1,uint32_t(int(c[8]))<<24|0xffffffu,false,fl(column),220.0f,c[5],fl(w),fl(h));
                return;
            }
            const int step=20-phase;
            const int sw=arcadeArtCubic(step,20,w,w>>4,w*10,w*10,c[9],c[10]);
            const int sh=arcadeArtCubic(step,20,h,h<<1,0,0,c[9],c[10]);
            const int x=column-((sw-w)>>1),y=0xdc-((sh-h)>>1);
            const int alpha=scalar(c[4]).sub(scalar(c[6]).sub(ScalarFloat::integer(phase)).mul(scalar(c[7]))).truncate();
            sheet(canvas,list,r,1,uint32_t(alpha)<<24|0xffffffu,false,fl(x),fl(y),c[5],fl(sw),fl(sh));
        };
        if(seconds>=10)digit(remaining/600,0x172,true);
        digit(seconds%10,0x1b8,false);
    }
    ArcadeFighterRequest object;
    object.visible=draw.loserSeat>=0;object.seat=draw.loserSeat;object.character=draw.loserCharacter;
    object.colourSet=true;object.colour=draw.loserColour;object.action=0x700;object.frame=draw.frame;
    return object;
}

ArcadeFighterRequest drawArcadeGameOver(const MenuCanvas& canvas,MenuDrawList& over,const ArcadeArtTables& art,
                                        const ArcadeGameOverDraw& draw,bool levelEnding) {
    const auto& o=art.gameOverFloats;
    const auto& t=art.gameOverTail;
    const auto fl=[](int32_t v) {return float(v);};
    const int frame=draw.frame;
    // 138b50: black backdrop far behind the object when the level-ending flag gameData+0x34 is set.
    const size_t before=over.records.size();
    if(levelEnding)canvas.rectangle(over,0,0,int(o[1]),int(o[2]),0xff000000u,o[0]);
    const size_t underRecords=over.records.size()-before;
    // 138ba8: "GAME OVER" text line fading in over 60 frames from frame 0x88.
    if(frame>=0x88) {
        const int n=frame-0x88;
        const int alpha=n<0x3c?scalar(float(n)).mul(scalar(o[3])).truncate():0xff;
        const auto& r=art.gameOverText;
        sheet(canvas,over,r,1,uint32_t(alpha)<<24|0xffffffu,false,o[4],o[5],o[6],fl(r.w),fl(r.h));
    }
    // 138c70: the title shrinks from five times its size over 50 frames,
    // shakes for 56 frames and then rests at (0x48, 0x9a).
    if(frame>=0x1e) {
        const auto& r=art.gameOverTitle;
        const int n=frame-0x1e;
        int x=0x48,y=0x9a,w=r.w,h=r.h;
        if(n<0x32) {
            w=arcadeArtCubic(n,0x32,5*r.w,5*r.w,5*r.w,r.w,t[5],t[6]);
            h=arcadeArtCubic(n,0x32,5*r.h,5*r.h,5*r.h,r.h,t[5],t[6]);
            x-=(w-r.w)>>1;y-=(h-r.h)>>1;
        } else if(n<0x6a) {
            const auto& offset=art.gameOverShake[size_t((frame-0x50)%8)];
            x+=offset[0];y+=offset[1];
        }
        sheet(canvas,over,r,0,0xffffffffu,false,fl(x),fl(y),t[0],fl(w),fl(h));
    }
    // 138e18: black strip behind the title from frame 0x51; frame 0x50 requests the fade instead.
    if(frame>0x50) {
        over.colour=0xffffffffu;over.blend=1;
        canvas.rectangle(over,0,int(t[1]),int(t[3]),int(t[4]),0xff000000u,t[2]);
    }
    ArcadeFighterRequest object;
    object.visible=draw.loserSeat>=0;object.seat=draw.loserSeat;object.character=draw.loserCharacter;
    object.action=0x701;object.frame=frame;object.underRecords=underRecords;
    return object;
}
}
