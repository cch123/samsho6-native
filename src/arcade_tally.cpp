#include "arcade_tally.hpp"
#include <cstring>
#include <fstream>
#include <stdexcept>

namespace ss6 {
namespace {
// EE three-operand MULT keeps the low word; DIV truncates toward zero.
int32_t product(int32_t a,int32_t b) {return int32_t(uint32_t(a)*uint32_t(b));}
int32_t sub(int32_t a,int32_t b) {return int32_t(uint32_t(a)-uint32_t(b));}
int32_t add(int32_t a,int32_t b) {return int32_t(uint32_t(a)+uint32_t(b));}
// Share of `whole` paid at step n of 30: whole*n/30 - whole*(n-1)/30.
int32_t share(int32_t whole,int32_t n) {return sub(product(whole,n)/30,product(whole,n-1)/30);}
}

ArcadeTallyTables::ArcadeTallyTables(const std::filesystem::path& assets) {
    std::ifstream in(assets/"arcade_tally.bin",std::ios::binary);
    std::vector<char> raw((std::istreambuf_iterator<char>(in)),{});
    if(raw.size()!=932||std::memcmp(raw.data(),"ATLY\1\0\0\0",8))throw std::runtime_error("Missing or mismatched arcade_tally.bin");
    size_t at=8;
    auto take=[&](void* to,size_t n){std::memcpy(to,raw.data()+at,n);at+=n;};
    take(award.data(),96);take(finish.data(),24);
    for(auto& label:labels){char text[25]{};take(text,24);label=text;}
    take(scoreX.data(),8);take(scoreDigits.data(),240);take(panelPieces.data(),120);take(panelFloats.data(),120);
    take(promptPositions.data(),48);take(&promptDepth,4);take(promptRecords.data(),96);
}

int arcadeBodyHitKind(int category) {
    // Jump table 5eb398 of 157a58; classes outside 0..13 (including -1) use kind 5.
    constexpr int kinds[]={1,2,3,4,5,6,7,22,17,22,18,19,20,21};
    return category>=0&&category<14?kinds[category]:5;
}
int arcadeObjectHitKind(int category) {
    switch(category) {
    case 14:return 12;
    case 13:return 21;
    case 11:return 19;
    case 2:return 3;
    case 1:return 2;
    case 4:return 5;
    case 0:return 1;
    default:return 18;
    }
}
int arcadeItemKind(int itemId) {return itemId>=4&&itemId<=6?itemId+9:-1;}
int arcadeFinishClass(bool guarded,int outcome1c) {
    if(guarded)return 1;
    switch(outcome1c) {
    case 2:case 4:return 2;
    case 0:return 3;
    case 1:return 4;
    case 3:return 5;
    default:return 0;
    }
}
int32_t arcadeScoreAward(const ArcadeTallyTables& tables,int gameMode,int seat,int kind,int32_t comboCount0c,int32_t& score90) {
    kind=arcadeComboKind(kind,comboCount0c);
    if(!arcadeScoreSeat(gameMode,seat))return 0;
    const int32_t value=tables.award.at(size_t(kind));
    score90=add(score90,value);
    return value;
}
bool arcadeFinishBonus(const ArcadeTallyTables& tables,int gameMode,int seat,int finishClass,int32_t& finishBonus582950) {
    if(!arcadeScoreSeat(gameMode,seat))return false;
    finishBonus582950=tables.finish.at(size_t(finishClass));
    return true;
}

int arcadeDigits(int32_t value) {
    if(value==0)return 1;
    // 1b9838 divides by a wrapping 32-bit power of ten until the quotient is 0.
    int digits=0;
    for(int32_t power=1;value/power!=0;power=product(power,10)) {
        ++digits;
        if(product(power,10)==0)throw std::runtime_error("Original 1b9838 divides by zero");
    }
    return digits;
}
void arcadeLifeBarShrink(std::array<ArcadeLifeBar,2>& bars,int seat,int32_t amount) {
    auto& bar=bars.at(size_t(seat));
    // Kinds 2, 4 and 5 move the bar only while the life is above their mark.
    const int32_t* mark=bar.kind94==2?&bar.mark54:bar.kind94==4?&bar.mark68:bar.kind94==5?&bar.mark7c:nullptr;
    if(mark&&!(*mark<bar.life14))return;
    if(seat==0)bars[0].x00=add(bars[0].x00,amount);
    bar.width08=sub(bar.width08,amount);
}

int32_t ArcadeTallyWorld::secondsLeft() const {
    if(clockOption13c==3)return -1;
    return survival?add(roundClock114,0xb3ff)/0xb400:add(roundClock114,0x59ff)/0x5a00;
}

std::vector<ArcadeTallyText> ArcadeTallyDraw::texts(const ArcadeTallyTables& t) const {
    std::vector<ArcadeTallyText> out;
    if(!visible)return out;
    out.push_back({t.labels[0],0xd8,0x90});
    out.push_back({t.labels[1],0xd8,0xa8});
    out.push_back({t.labels[perfectLabel?2:3],0xd8,0xc0});
    if(straightRow)out.push_back({t.labels[5],0xd8,0xd8});
    out.push_back({t.labels[4],0xd8,0xf0});
    out.push_back({t.labels[6],0xd8,0x108});
    // Right-aligned at x = 0x1a8 with 12-pixel glyphs. Only the FINISH and
    // TOTAL rows reserve a column for the minus sign.
    auto number=[&](int32_t v,int y,bool sign){
        out.push_back({std::to_string(v),0x1a8-12*(arcadeDigits(v)+(sign&&v<0)),y});
    };
    if(valueRows>=1)number(finish,0x90,true);
    if(valueRows>=2)number(time,0xa8,false);
    if(valueRows>=3)number(life,0xc0,false);
    if(valueRows>=4&&straightRow)number(straight,0xd8,false);
    number(total,0x108,true);
    return out;
}

void ArcadeTally::enter(ArcadeTallyWorld& w) {
    // 1c7d48. The "straight" seat is derived from seat 0's record alone.
    straightSeat8c=w.wins28[0]<w.required2c[0];
    // 1c7ea0: the seat with more HUD life; a tie selects seat 1.
    seat88=!(w.life[0].life14>w.life[1].life14);
    active44=1;phase40=0;done48=0;exit4c=0;wait84=0;sound90=0;paused94=0;
    w.postMatchMenuA4=0;
    // 1c7e00
    seconds54=w.secondsLeft();
    finishLatch64=w.finishBonus582950;
    life58=w.life[size_t(seat88)].life14;
    straight5c=60000;
    finish6c=0;step68=1;life74=0;time70=0;total7c=0;straight78=0;
    perfect80=w.life[size_t(seat88)].life14==200; // 1c7ee0
    draw={};
}

bool ArcadeTally::straightHolds(const ArcadeTallyWorld& w) const {
    const size_t s=size_t(straightSeat8c);
    const int32_t required=w.seatRequired20[s];
    return required>=2&&!(w.wins28[s]<required)&&w.wins28[s^1]==0;
}
// The toggle word 582990 is cleared after every request, so each counted step sounds.
bool ArcadeTally::blip() {
    sound90^=1;
    if(sound90!=1)return false;
    sound90=0;
    return true;
}
int32_t ArcadeTally::finishStep(bool skip,ArcadeTallyWorld& w) {
    const int32_t left=w.finishBonus582950;
    if(left==0)return -1;
    if(skip){w.finishBonus582950=0;step68=1;return left;}
    const int32_t n=step68,v=share(finishLatch64,n);
    w.finishBonus582950=sub(left,v);
    if(n<30)step68=n+1;
    else{w.finishBonus582950=0;step68=1;}
    return v;
}
int32_t ArcadeTally::timeStep(bool skip,ArcadeTallyWorld& w) {
    if(add(w.roundClock114,0x59ff)/0x5a00==0)return -1; // 1c8448
    if(skip) {
        const int32_t seconds=w.secondsLeft();
        w.roundClock114=0;step68=1;
        return product(seconds,100);
    }
    const int32_t n=step68,v=share(seconds54,n);
    w.roundClock114=sub(w.roundClock114,product(v,0x5a00));
    if(n<30)step68=n+1;
    else{w.roundClock114=0;step68=1;}
    return product(v,100);
}
int32_t ArcadeTally::lifeStep(bool skip,ArcadeTallyWorld& w) {
    auto& bar=w.life[size_t(seat88)];
    if(bar.life14==0)return -1; // 1c85a8
    int32_t v;
    if(skip){v=bar.life14;bar.lag10=0;bar.life14=0;step68=1;}
    else {
        const int32_t n=step68;
        v=share(life58,n);
        bar.lag10=sub(bar.lag10,v);bar.life14=sub(bar.life14,v);
        if(n<30)step68=n+1;
        else{bar.life14=0;step68=1;} // +0x10 keeps its remainder
    }
    arcadeLifeBarShrink(w.life,seat88,v);
    return product(v,perfect80==1?200:100);
}
int32_t ArcadeTally::straightStep(bool skip,ArcadeTallyWorld& w) {
    const int32_t left=straight5c;
    if(left==0||!straightHolds(w))return -1;
    if(skip){straight5c=0;step68=1;return left;}
    straight5c=sub(left,2000);
    if(step68<30)++step68;
    else{straight5c=0;step68=1;}
    return 2000;
}
bool ArcadeTally::payoutStep(bool skip,ArcadeTallyWorld& w,int& sounds) {
    const int32_t left=total7c;
    if(left==0)return false;
    if(skip){total7c=0;w.score90=add(w.score90,left);step68=1;return true;}
    const int32_t n=step68,v=share(payout60,n);
    w.score90=add(w.score90,v);total7c=sub(left,v);
    if(blip())++sounds;
    if(n<30)step68=n+1;
    else{step68=1;total7c=0;}
    return true;
}

ArcadeTallyTick ArcadeTally::tick(std::array<uint32_t,2> pressed,ArcadeTallyWorld& w) {
    ArcadeTallyTick out;
    // 118128(seat)+4: any of the pressed bits 0x60f ends the current count.
    const bool skip=!paused94&&(pressed[size_t(seat88)]&0x60f);
    draw.visible=true;draw.perfectLabel=perfect80==1;draw.straightRow=straightHolds(w);
    auto count=[&](int32_t v,int32_t& row,int next){
        if(v==-1){phase40=next;return;}
        total7c=add(total7c,v);row=add(row,v);
        if(blip())++out.sounds;
    };
    const int phase=phase40;
    switch(phase) {
    case 0:if(!paused94)count(finishStep(skip,w),finish6c,1);break;
    case 1:if(!paused94) {
            // 1c8360 runs (and moves the clock and the step counter) even
            // when option byte 43d05d == 2 then discards its result.
            const int32_t v=timeStep(skip,w);
            count(w.timeOption43d05d==2?-1:v,time70,2);
        }break;
    case 2:if(!paused94)count(lifeStep(skip,w),life74,3);break;
    case 3:if(!paused94)count(straightStep(skip,w),straight78,4);break;
    case 4:if(!paused94) {
            ++wait84;
            if(!(wait84<30)||skip){payout60=total7c;phase40=5;}
        }break;
    case 5:if(!paused94&&!payoutStep(skip,w,out.sounds))phase40=6;break;
    case 6:if(!paused94) {
            if(w.sceneSwitch18==0)++exit4c;
            if(!(exit4c<30)){done48=1;active44=0;}
            if(!(exit4c<20))out.musicRelease=true;
        }break;
    default:break;
    }
    // The value rows follow the phase the handler dispatched on, not the new one.
    draw.valueRows=phase<=3?phase+1:phase<=6?4:0;
    draw.finish=finish6c;draw.time=time70;draw.life=life74;draw.straight=straight78;draw.total=total7c;
    return out;
}

bool FreeSeatPrompt::tick() {
    if(shown2234==0) {
        if(!(++count2230<60))shown2234=1;
    } else if(--count2230==0)shown2234=0;
    return shown2234==1;
}
}
