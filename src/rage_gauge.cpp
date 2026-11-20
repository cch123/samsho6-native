#include "rage_gauge.hpp"
#include "battle_clock.hpp"
#include <algorithm>
#include "hud_sprite.hpp"
#include <stdexcept>

namespace ss6 {
namespace {
using hud::screenWidth; using hud::screenHeight; using hud::loadAtlas; using hud::Sprite; using hud::sprite;
constexpr int meterWidth=184;

bool flashing(int state) { return state==1 || state==2; }

// 1c0718 and 1c0920 select the spirit independently for each side. The
// emblem has its own placement while its shared frame is drawn without a flip.
constexpr Sprite backdrop{1,198,208,16},frame{1,130,208,16},flame{1,147,208,16};
constexpr Sprite exhaustedFrame{1,181,208,16};
constexpr Sprite exhaustedEmblem{395,152,38,38};
constexpr Sprite concentrationFrame{1,164,208,16};
// slot1: system 8 (the companion fighters 44..47) draws its frame and emblem from texture
// slot 1 (obj0_16) rather than the stock spirits' slot 10 (obj2_16); 1c0718 / 1c0920.
struct SpiritArt { Sprite base,emblem; int x,y; std::array<int,3> start,end; bool slot1=false; };
constexpr std::array<SpiritArt,9> spirits{{
    {{1,334,60,64},{350,280,53,53},9,389,{255,128,0},{255,0,0}},
    {{62,334,60,64},{404,280,53,53},10,386,{255,200,0},{255,80,0}},
    {{123,334,60,64},{458,280,53,53},9,385,{128,255,128},{0,255,0}},
    {{245,334,60,64},{350,334,53,53},10,384,{128,128,255},{0,0,255}},
    {{1,269,60,64},{404,334,53,53},8,384,{200,255,255},{255,255,0}},
    {{184,334,60,64},{458,334,53,53},10,385,{255,255,128},{255,255,0}},
    {},{}, // systems 6 / 7 are option-gated and not offered by the console VS select
    {{217,421,60,64},{1,421,53,53},9,384,{128,255,128},{0,255,0},true} // 0x4c5380 / 0x4c53b0; Zan's gradient
}};

void fill(std::span<uint8_t> pixels,const RageGaugePlayer& p,int side) {
    const bool concentration=p.system==4 && p.lifeGauge.phase==3;
    const int width=concentration?((p.lifeGauge.remaining>>8)*184/200):p.displayed;
    if(!width) return;
    const int x=side?572-width:68;
    const auto& art=spirits.at(p.system);
    std::array<int,3> left=art.start,right{};
    for(unsigned c=0;c<3;++c)
        right[c]=(width*art.end[c]+(meterWidth-width)*art.start[c])/meterWidth;
    if(side)std::swap(left,right);
    // 1c1300 uses single-precision arithmetic and CVT.W.S on the triangle
    // counter. The ordinary gradient instead uses integer endpoint colors.
    constexpr std::array<int,16> pulseLevels{0,5,10,15,21,26,31,37,42,47,53,58,63,69,74,79};
    const int pulse=pulseLevels[p.pulse];
    for(int col=0;col<width;++col) {
        std::array<uint8_t,3> rgb{255,uint8_t(pulse),uint8_t(pulse)};
        if(concentration)rgb={uint8_t(pulse),uint8_t(pulse),255};
        else if(p.system==5&&!flashing(p.state)&&width>=40)rgb={255,255,uint8_t(17*p.guardPulse)};
        else if(!flashing(p.state))for(unsigned c=0;c<3;++c)
            rgb[c]=uint8_t((left[c]*(2*width-2*col-1)+right[c]*(2*col+1))/(2*width));
        for(int row=426;row<434;++row) {
            auto* pixel=pixels.data()+(row*screenWidth+x+col)*4;
            std::copy(rgb.begin(),rgb.end(),pixel);pixel[3]=255;
        }
    }
}

void pulseTick(int& counter,int& direction,int end) {
    counter+=direction;
    if(counter==end||counter==0)direction=-direction;
}

void bar(std::span<uint8_t> dst,int x,int y,int w,int h,int r,int g,int b,int alpha=128) {
    const std::array<int,3> color{r,g,b};
    // 1145c0 emits both endpoint coordinates, including a reversed width.
    const int left=std::max(0,std::min(x,x+w)),right=std::min(screenWidth,std::max(x,x+w));
    for(int row=std::max(0,y);row<std::min(screenHeight,y+h);++row)for(int col=left;col<right;++col) {
        auto* pixel=dst.data()+(row*screenWidth+col)*4;
        for(unsigned c=0;c<3;++c)pixel[c]=uint8_t(pixel[c]+((color[c]-pixel[c])*alpha>>7));
        pixel[3]=255;
    }
}

void paintCombo(std::span<uint8_t> dst,const std::vector<uint8_t>& labels,
                const std::vector<uint8_t>& numbers,const ComboFrame& f,int side) {
    if(f.count<2)return;
    constexpr Sprite slash{449,75,62,58},caption{163,215,62,24};
    constexpr std::array<int,9> shakeX{0,0,-2,2,-2,2,2,-2,0};
    constexpr std::array<int,9> shakeY{-2,2,0,0,-2,2,-2,2,0};
    const int base=80+490*side;
    auto glyph=[&](const std::vector<uint8_t>& atlas,Sprite tile,int x,int y,int extraW,int extraH,int alpha) {
        sprite(dst,atlas,tile,x-extraW/2,y-extraH/2,tile.w+extraW,tile.h+extraH,(alpha+1)/2);
    };
    auto digits=[&](int value,int x,int y,int w,int h,int alpha,bool unitsOnly,bool skipTens) {
        int place=0;
        do {
            const Sprite tile{1+37*(value%10),51,36,48};
            if(place!=1 || !skipTens)glyph(numbers,tile,x,y,w,h,alpha);
            x-=36;
            ++place;
            value/=10;
        } while(value && !unitsOnly);
    };
    // The Japanese label and digits have different motion curves. The previous
    // ones digit remains under the growing replacement on hits three and up.
    if(f.exit>=0) {
        const int spread=std::max(0,5-f.exit);
        const int alpha=255-51*std::max(0,f.exit-5);
        glyph(labels,slash,base,110,4*spread,2*spread,alpha);
        glyph(labels,caption,base,158,4*spread,2*spread,alpha);
        digits(f.count,base-36,110,4*spread,2*spread,alpha,false,false);
        return;
    }
    const int enter=2-f.entry;
    const bool multi=f.count>=3;
    glyph(labels,slash,base+(multi?shakeX[f.bounce]:18*enter),
          110+(multi?shakeY[f.bounce]:-24*enter),0,0,255);
    glyph(labels,caption,base-(multi?0:40*enter),158,0,0,255);
    const int x=base-36-18*enter,y=110+24*enter;
    // The steady tens column sits behind both animating unit digits in GS depth.
    if(f.fixedTens && f.count>=10) {
        const Sprite tens{1+37*((f.count/10)%10),51,36,48};
        glyph(numbers,tens,x-36+shakeX[f.tensStep],110+shakeY[f.tensStep],0,0,255);
    }
    if(multi && f.digit<10)digits(f.previous,x,y,0,0,255,f.fixedTens,false);
    const int grow=multi?10-f.digit:0;
    digits(f.count,x,y,16*grow,12*grow,multi?255*f.digit/10:255,false,f.fixedTens);
}

void paintLifePlate(std::span<uint8_t> dst,const std::vector<uint8_t>& atlas,int side) {
    sprite(dst,atlas,{1,73,228,56},side?352:59,29,228,56,80,false,side);
    // The frame has a lower GS depth than the fill and sword even though
    // 1bab38 calls its draw routine (1bae60) after both. Its transparent
    // center reveals the separate, dimmer background from 1bada0.
    sprite(dst,atlas,{1,1,228,56},side?352:59,29,228,56,128,false,side);
}

void paintLifeGauge(std::span<uint8_t> dst,const RageGaugePlayer& p,int side) {
    const auto& z=p.lifeGauge;
    const int life=p.lifeHealing?p.lifeTrail:z.life,reserve=z.reserve>>8,covered=std::min(reserve,life);
    const auto lifeBar=[&](int from,int to,int r,int g,int b,int alpha=128){
        if(to>from)bar(dst,side?366+from:273-to,45,to-from,16,r,g,b,alpha);
    };
    if(p.woundWidth>0)bar(dst,p.woundX,45,p.woundWidth,16,255,0,0,64);
    if(p.system==0||p.system==1||p.system==3||p.system==8) {
        // The HUD grows its own geometry one pixel at a time on healing.
        // The actor has already received the full amount at this point.
        bar(dst,p.lifeX,45,p.lifeWidth,16,255,255,32);
    } else if(p.system==2) {
        // 1bf790 splits off the last twenty points for Zan. On crossing
        // that threshold the warning starts at its retained pulse phase.
        lifeBar(20,life,255,255,32);
        const int critical=std::min(20,life);
        if(life>20)lifeBar(0,critical,255,160,0);
        else {
            constexpr std::array<int,16> red{255,247,240,232,225,218,210,203,195,188,181,173,166,158,151,144};
            constexpr std::array<int,16> green{176,170,165,160,154,149,144,138,133,128,122,117,112,106,101,96};
            lifeBar(0,critical,red[p.zanLifePulse],green[p.zanLifePulse],32);
        }
    } else if(p.system==5) {
        lifeBar(covered,life,255,255,32);
        // 1bf4d0 makes the whole remaining life pulse when the secret is
        // usable. Until that threshold only the stored portion is green.
        constexpr std::array<int,16> red{200,186,173,160,146,133,120,106,93,80,66,53,40,26,13,0};
        constexpr std::array<int,16> green{255,251,247,244,240,236,233,229,225,222,218,214,211,207,203,200};
        if(reserve>=life)lifeBar(0,covered,red[p.lifePulse],green[p.lifePulse],red[p.lifePulse]);
        else lifeBar(0,covered,0,255,0);
    } else {
        // 1bf28c uses the HUD's retained geometry. Lowering the reserve
        // while the life display crosses it can leave an offset different
        // from simply subtracting the reserve from the fighter's live HP.
        if(reserve<life)bar(dst,p.lifeX+(side?reserve:0),45,p.lifeWidth-reserve,16,255,255,32);
        // Life and stored meditation share one bar. The empty part of the
        // reserve only appears once the delayed wound display passes it.
        constexpr std::array<int,31> blink{0,4,8,12,17,21,25,29,34,38,42,46,51,55,59,63,
            68,72,76,81,85,89,93,98,102,106,110,115,119,123,127};
        const int green=z.phase==2&&reserve>=life?blink[p.lifePulse]:
            z.phase==1||z.phase==2?80:164;
        if(z.phase==4)lifeBar(0,covered,255,255,32);
        else {
            lifeBar(0,covered,0,green,255);
            if(p.lifeTrail<reserve) {
                // 1bf380 uses the saved wound length on the right-hand side.
                // It can outlive the visible red overlay during overlapping hits.
                const int rightStart=p.lifeHealing?p.lifeTrail:z.life+p.storedWoundWidth;
                bar(dst,side?366+rightStart:273-reserve,45,reserve-p.lifeTrail,16,0,0,128,64);
            }
        }
    }
    const int sword=z.sword>>8,capacity=z.swordMax>>8,edge=side?370:270-capacity;
    bar(dst,edge-2,67,2,8,0,0,0);bar(dst,edge+capacity,67,2,8,0,0,0);
    bar(dst,edge,67,capacity,2,0,0,0);bar(dst,edge,73,capacity,2,0,0,0);
    const int left=side?370:270-sword;
    if(sword>=capacity) {
        constexpr std::array<int,16> dim{64,59,55,51,46,42,38,34,29,25,21,17,12,8,4,0};
        bar(dst,left,69,sword,4,255-17*p.swordPulse,dim[p.swordPulse],dim[p.swordPulse]);
    } else if(sword>=capacity-10)bar(dst,left,69,sword,4,255,160,64);
    else bar(dst,left,69,sword,4,0,255,0);
}
}

namespace {
void updateLifeGauge(RageGaugePlayer& p,const LifeGaugeInput& sample,int side) {
    int target=p.lifeGauge.life;
    int threshold=p.system==2?20:sample.reserve>>8;
    const bool split=p.system==2||p.system==4||p.system==5;
    // 1bee40 consults the threshold published on the previous HUD visit;
    // 1be1a8 initializes it from the fighter on the first round visit.
    if(p.lifeThreshold<0)p.lifeThreshold=threshold;
    const auto adjustWidth=[&](int loss) {
        if(split&&target<=p.lifeThreshold)return;
        p.lifeWidth-=loss;
        if(!side)p.lifeX+=loss;
    };

    // 1beaa8 animates recovery independently of combat speed. Being hit
    // during recovery first completes the green/yellow foreground, so that
    // the next red section begins at the recovered endpoint.
    if(!sample.holdLifeSampling&&target>0) {
        if(sample.life>target) {
            if(p.woundActive) { p.lifeTrail=target;p.woundActive=false; }
            p.lifeWidth=p.lifeTrail;
            target=sample.life;
            p.lifeHealing=true;
        }
        if(p.lifeHealing) {
            if(p.lifeTrail!=target) { ++p.lifeTrail;adjustWidth(-1); }
            if(p.lifeTrail==target)p.lifeHealing=false;
            else if(sample.inPersistentHurt) {
                adjustWidth(p.lifeTrail-target);
                if(!side)p.lifeX=273-target;
                p.lifeTrail=target;
                p.lifeHealing=false;
            }
        }
    }
    if(target>0) {
        const int loss=target-std::max(0,sample.life);
        if(loss>0&&!p.lifeHealing&&!sample.holdLifeSampling) {
            if(sample.opponentHits==1) {
                p.lifeTrail=target;
                p.storedWoundWidth=loss;
            } else {
                p.storedWoundWidth+=loss;
            }
            target-=loss;
            p.woundX=side?366+target:273-p.lifeTrail;
            adjustWidth(loss);
            p.woundActive=true;
            p.lifeDelay=30;
        }
        if(sample.inPersistentHurt) { p.woundActive=true;p.lifeDelay=30; }
    }
    p.woundWidth=0;
    if(p.woundActive) {
        if(--p.lifeDelay<=0&&p.lifeTrail!=target) {
            --p.lifeTrail;--p.storedWoundWidth;
            if(!side)++p.woundX;
        }
        // The original submits the rectangle before clearing its storage.
        p.woundWidth=p.storedWoundWidth;
    }
    if(p.lifeTrail==target) { p.storedWoundWidth=0;p.woundActive=false; }
    p.sampledLife=sample.life;
    p.lifeGauge=sample;
    p.lifeGauge.life=target;
    const int visibleLife=p.lifeHealing?p.lifeTrail:target;
    if(split&&visibleLife<=threshold) {
        if(!side&&(p.system==4||p.lifeHealing))p.lifeX=273-threshold;
        if(p.system==2)pulseTick(p.zanLifePulse,p.zanLifeDirection,15);
        if(p.system==5)pulseTick(p.lifePulse,p.lifePulseDirection,15);
        if(p.system==4&&sample.phase==2)pulseTick(p.lifePulse,p.lifePulseDirection,30);
    }
    p.lifeThreshold=threshold;
    if((sample.sword>>8)>=(sample.swordMax>>8))pulseTick(p.swordPulse,p.swordPulseDirection,15);
}
}

void ComboHud::advance(bool defenderStillHurt,bool frozen) {
    if(requested>=2 && (requested!=next.count || next.exit>=0)) {
        next.previous=next.exit>=0?0:next.count;
        next.count=requested;
        next.bounce=next.digit=held=0;
        next.exit=-1;
        if(next.count%10<=1)next.fixedTens=next.count%10==1;
    }
    requested=0;
    draw=next;
    draw.tensStep=std::min(8,next.bounce+int(!frozen));
    if(next.count<2||frozen)return;
    if(next.exit>=0) {
        if(++next.exit>10)next={};
        return;
    }
    next.entry=std::min(2,next.entry+1);
    if(next.count>=3) {
        next.bounce=std::min(8,next.bounce+1);
        next.digit=std::min(10,next.digit+1);
    }
    // 1bc580 retains the last number until the 61st visit AND until the
    // victim leaves sustained hitstun. Ten more visits shrink/fade the label.
    held=std::min(61,held+1);
    if(held==61 && !defenderStillHurt) {
        next.exit=0;
        next.entry=0;
        next.fixedTens=false;
    }
}

void RageGaugeState::reset(const std::array<int32_t,2>& amount124) {
    for(int side=0;side<2;++side) {
        // 1be1a8 clears the six-draw delay but preserves the cell index at
        // 132f578. A rage carried through a round continues its fire cycle.
        const int fireFrame=players[side].fireFrame;
        players[side]={};
        players[side].lifeX=side?366:73;
        players[side].fireFrame=fireFrame;
        players[side].displayed=std::clamp(amount124[side]>>8,0,meterWidth);
    }
}

void RageGaugeState::advance(const std::array<int32_t,2>& state120,const std::array<int32_t,2>& amount124,
                             const std::array<int32_t,2>& systems,const std::array<uint32_t,2>& flags23c,
                             const std::array<LifeGaugeInput,2>& lifeGauges,bool comboFrozen) {
    for(int side=0;side<2;++side) {
        auto& p=players[side];
        p.combo.advance(lifeGauges[1-side].inPersistentHurt,comboFrozen);
        p.system=systems[side];
        p.state=state120[side];
        updateLifeGauge(p,lifeGauges[side],side);
        if(p.system==4&&p.lifeGauge.phase==3&&++p.concentrationTicks==6) {
            p.concentrationTicks=0;p.concentrationCell=(p.concentrationCell+1)%4;
        }
        const int target=std::clamp(amount124[side]>>8,0,meterWidth);
        p.emblemExpansion=0;
        if(flashing(p.state)) {
            // 1c0d08 advances the eight common fire cells on every sixth
            // active draw. Both counters stay where they were between rages.
            if(++p.fireTicks==6) { p.fireTicks=0;p.fireFrame=(p.fireFrame+1)%8; }
            p.displayed=target;

            p.emblemExpansion=25-p.emblemCounter;
            p.emblemCounter=p.emblemCounter==25?0:p.emblemCounter+1;
        } else if(p.system==2 && !p.state && (flags23c[side]&0x10000)) {
            // 1c0684 displays Zan's held charge immediately. Later in the
            // hold, its accelerated gain exceeds the normal one-pixel step.
            p.displayed=target;
        } else {
            // 1c0700 eases gains by one pixel but accepts decreases on the
            // same tick. The two flash counters retain their last phase.
            p.displayed=std::min(target,p.displayed+1);
        }
        if(p.system==5&&!flashing(p.state)&&p.displayed>=40)pulseTick(p.guardPulse,p.guardPulseDirection,15);
        if(flashing(p.state)||(p.system==4 && p.lifeGauge.phase==3))pulseTick(p.pulse,p.pulseDirection,15);
    }
}

RageGaugeRenderer::RageGaugeRenderer(const std::filesystem::path& assets)
    :gaugeAtlas_(loadAtlas(assets/"obj2_16.tex")),commonAtlas_(loadAtlas(assets/"obj1_16.tex")),slotOneAtlas_(loadAtlas(assets/"obj0_16.tex")) {}

void RageGaugeRenderer::paintClock(const BattleClockState& clock,std::span<uint8_t> pixels) const {
    if(pixels.size()!=screenWidth*screenHeight*4)
        throw std::invalid_argument("Expected a 640x448 RGBA framebuffer for the round clock");
    if(!clock.visible)return;
    // 1baff0 submits this translucent backing even during Issen, when
    // 141cf8 suppresses the ornamental front plate and turns the digits red.
    sprite(pixels,gaugeAtlas_,{230,67,82,65},279,28,82,65,64);
    if(!clock.stopped)sprite(pixels,gaugeAtlas_,{230,1,82,65},279,28,82,65);
    // 1bb0b0 prints both positions even below ten. The two halves of
    // infinity are separate atlas entries one scanline above the digits.
    for(int i=0;i<2;++i) {
        const int finite=std::max(0,clock.seconds);
        const int glyph=clock.seconds==-1?10+i:(i?finite%10:finite/10%10);
        const Sprite cell{1+glyph*31,glyph<10?1:0,30,49};
        sprite(pixels,commonAtlas_,cell,290+i*30,32,30,49,128,false,false,clock.stopped);
    }
}

void RageGaugeRenderer::paint(const RageGaugeState& state,std::span<uint8_t> pixels) const {
    if(pixels.size()!=screenWidth*screenHeight*4)
        throw std::invalid_argument("Expected a 640x448 RGBA framebuffer for the combat HUD");
    // The first bounce crosses the life plate. Its PS2 draw priority leaves
    // the plate and its contents in front of the moving label.
    for(int side=0;side<2;++side)paintCombo(pixels,gaugeAtlas_,commonAtlas_,state.players[side].combo.draw,side);
    paintLife(state,pixels);
    paintRage(state,pixels);
}

void RageGaugeRenderer::paintLife(const RageGaugeState& state,std::span<uint8_t> pixels) const {
    if(pixels.size()!=screenWidth*screenHeight*4)
        throw std::invalid_argument("Expected a 640x448 RGBA framebuffer for the life gauge");
    for(int side=0;side<2;++side)paintLifePlate(pixels,gaugeAtlas_,side);
    for(int side=0;side<2;++side)paintLifeGauge(pixels,state.players[side],side);
}

void RageGaugeRenderer::paintRage(const RageGaugeState& state,std::span<uint8_t> pixels) const {
    if(pixels.size()!=screenWidth*screenHeight*4)
        throw std::invalid_argument("Expected a 640x448 RGBA framebuffer for the rage HUD");
    for(int side=0;side<2;++side) {
        const auto& p=state.players[side];
        const auto& art=spirits.at(p.system);
        if(p.system==6||p.system==7)throw std::runtime_error("Spirit 6/7 HUD art is not ported");
        const auto& spiritAtlas=art.slot1?slotOneAtlas_:gaugeAtlas_;
        const bool mu=p.system==4&&p.lifeGauge.phase==3;
        const bool spent=p.system==4&&p.lifeGauge.phase==4;
        const int x=side?376:56;
        if(p.state!=3) sprite(pixels,spiritAtlas,art.base,side?574:6,378,60,64);
        sprite(pixels,gaugeAtlas_,backdrop,x,422,208,16,64);
        if(flashing(p.state)) sprite(pixels,gaugeAtlas_,flame,x,422,208,16);
        if(mu)sprite(pixels,gaugeAtlas_,concentrationFrame,x,422,208,16);
        sprite(pixels,gaugeAtlas_,p.state==3||spent?exhaustedFrame:frame,x,422,208,16,p.state==3||spent?64:128);
        if(flashing(p.state)) {
            // 1c0d08 subtracts one U texel from each 4c57b8/4c5878
            // descriptor and submits signed widths on the right side.
            const int i=p.fireFrame;
            sprite(pixels,commonAtlas_,{93*(i%3),131+127*(i/3),92,126},
                   side?566:-13,314,92,126,128,true,side);
            if(p.state==2)
                sprite(pixels,commonAtlas_,{304,191+40*i,206,39},
                       side?378:66,397,206,39,128,true,side);
        }
        if(mu) {
            sprite(pixels,gaugeAtlas_,{62+61*p.concentrationCell,269,60,64},side?574:6,378,60,64);
            sprite(pixels,gaugeAtlas_,art.emblem,art.x+568*side,art.y,53,53,64);
        } else if(p.state==3||(spent&&!flashing(p.state))) {
            sprite(pixels,commonAtlas_,p.system==4?Sprite{434,152,38,38}:exhaustedEmblem,side?585:17,396,38,38);
        } else {
            const int extra=p.emblemExpansion;
            sprite(pixels,spiritAtlas,art.emblem,art.x+568*side-extra/2,art.y-extra/2,53+extra,53+extra);
        }
        // 1c1160 / 1c1300 submit the fill closer than the frame and emblem.
        fill(pixels,p,side);
    }
}

}
