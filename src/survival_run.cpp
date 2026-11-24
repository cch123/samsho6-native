#include "asset_files.hpp"
#include "survival_run.hpp"
#include <algorithm>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <iterator>
#include <stdexcept>

namespace ss6 {
SurvivalAssets::SurvivalAssets(const std::filesystem::path& assets) {
    std::ifstream in(resolveAsset(assets/"survival_run.bin"),std::ios::binary);
    if(!in)throw std::runtime_error("Missing asset: survival_run.bin");
    const std::vector<uint8_t> data{std::istreambuf_iterator<char>(in),{}};
    size_t at=0;
    auto byte=[&] {return data.at(at++);};
    auto half=[&] {const unsigned lo=byte();return uint16_t(lo|byte()<<8);};
    if(data.size()<4||std::memcmp(data.data(),"SSV1",4))throw std::runtime_error("Bad survival_run.bin");
    at=4;
    for(auto& v:rewardRule)v=byte();
    for(auto& v:missionKind)v=byte();
    for(auto& v:gains)v=half();
    for(auto* group:{&rewards,&missions,&fighters,&messages,&legends,&hud,&selector}) {
        group->resize(half());
        for(auto& s:*group) {
            const size_t n=half();
            if(at+n>data.size())throw std::runtime_error("Truncated survival_run.bin");
            s.assign(data.begin()+at,data.begin()+at+n);at+=n;
        }
    }
    if(rewards.size()!=9||missions.size()!=22||fighters.size()!=49||messages.size()!=14||legends.size()!=4||hud.size()!=8||
       selector.size()!=2)throw std::runtime_error("Bad survival_run.bin layout");
}

bool survivalUnarmedBoss(int c) {return c>=0x2b&&c<=0x2f;}
bool survivalNoDeflect(int c) {return c>=0x2c&&c<=0x2f;}

int survivalReward(const SurvivalAssets& assets,unsigned m,int sp,bool lifeTurn) {
    if(m>=0x16)return 8;
    const int strong=lifeTurn?2:6;
    switch(assets.rewardRule[m]) {
    case 0:return lifeTurn?0:4;
    case 1:return lifeTurn?1:5;
    case 2:return strong;
    case 3:return sp==1?3:strong;
    case 4:return sp==5?2:strong;
    case 5:return sp==4?3:strong;
    case 6:return 3;
    case 7:return 1;
    case 8:return 0;
    default:return 8;
    }
}
bool survivalAdmits(const SurvivalAssets& assets,int m,int sp,const std::array<SurvivalCandidate,3>& rows,int row) {
    // The clock reward of a mission also excludes its life counterpart.
    const int v=survivalReward(assets,unsigned(m),sp,false);
    const int alt=v==4?0:v==5?1:v==6?2:-1;
    for(int j=0;j<row;++j)if(rows[j].mission==m||rows[j].reward==v||rows[j].reward==alt)return false;
    return true;
}

int SurvivalTable::cpuLevel() const {
    const int n=wins;
    if(n>=0x30)return 7;
    if(n==0x2f)return 8;
    if(n==0x27||n==0x1d||n==0x13||n==9)return 6;
    if(n>=0x2e)return 3;
    if(n>=0x2b)return 4;
    if(n>=0x28)return 2;
    if(n>=0x24)return 4;
    if(n>=0x21)return 2;
    if(n>=0x1e)return 1;
    if(n>=0x1a)return 2;
    if(n>=0x17)return 1;
    if(n>=0x14)return 0;
    if(n>=0x10)return 2;
    if(n>=0xd)return 1;
    if(n>=0xa)return 0;
    if(n>=6)return 2;
    return n>=3;
}

int SurvivalTable::generate(const SurvivalAssets& assets,GameRandom& random,int n,int lastStage,int defeatedCharacter,
                            int hc,bool clockLow,std::array<SurvivalCandidate,3>& rows,bool* assertion) {
    wins=int16_t(n);
    if(n>0) {defeated.at(n-1)=int16_t(defeatedCharacter);stageHistory.at(n-1)=int16_t(lastStage);}
    std::array<int,3> list{-1,-1,-1};
    int k=0;
    bool boss=false;
    if(assertion)*assertion=false;
    if(n>=0x30) {list[0]=0x2b;k=1;}
    else if(n==0x2f||n==0x27||n==0x1d||n==0x13||n==9) {
        list[0]=n==0x2f?0x30:n==0x27?0x1a:n==0x1d?0xd:n==0x13?0x1b:0xb;k=1;boss=true;
    } else {
        // Ordinary fighters 0..27 for the first 40 opponents, the hidden
        // group 28..2f afterwards; the scheduled bosses never enter the pool.
        std::array<int,0x33> pool{};
        int count=0;
        for(int c=0;c<0x33&&n>=0;++c) {
            if(c==0x2b||c==0x30||c==0x1a||c==0xd||c==0x1b||c==0xb||c==0x31||c==0x32)continue;
            if(n<0x28?c>=0x28:c<0x28)continue;
            if(std::find(defeated.begin(),defeated.begin()+n,c)==defeated.begin()+n)pool[count++]=c;
        }
        if(count>=3) {
            // The bound stays the full pool size; a taken slot advances to
            // the next free one with wrap-around.
            for(int i=0;i<3;++i) {
                int r=random.bounded(count);
                while(pool[r]==-1)r=r+1<count?r+1:0;
                list[k++]=pool[r];pool[r]=-1;
            }
        } else for(int i=0;i<count;++i)list[k++]=pool[i];
    }
    for(auto& r:rows)r.character=-1;
    if(k==0) {if(assertion)*assertion=true;list[0]=0;k=1;}
    if(k==1)list[1]=list[2]=list[0];
    else if(k==2)list[2]=random.bounded(2)!=0?list[1]:list[0];
    for(int i=0;i<3;++i) {
        if(hc>=0x2c&&hc<=0x2f)rows[i].humanSpirit=8;
        else if(hc==0x2b)rows[i].humanSpirit=7;
        else for(;;) {
            int v=random.bounded(7);
            if(v>=6)v=7;
            rows[i].humanSpirit=v;
            bool repeated=false;
            for(int j=0;j<i;++j)repeated|=rows[j].humanSpirit==v;
            if(!repeated)break;
        }
    }
    bool lifeTurn=random.bounded(2)==0;
    for(int i=0;i<3;++i) {
        auto& row=rows[i];
        row.character=list[i];
        row.stage=random.bounded(0xb);
        row.colour=random.bounded(5);
        if(boss) {row.mission=0x15;row.reward=7;}
        else {
            const int sp=row.humanSpirit;
            std::array<int,32> q{};
            int count=0;
            auto add=[&](int m,int spirit) {if(survivalAdmits(assets,m,spirit,rows,i))q[count++]=m;};
            for(int m:{1,3,2,4,0xc,0xd})add(m,sp);
            if(!survivalUnarmedBoss(hc)&&hc!=0x30)add(0,sp);
            if(sp==0)add(5,0);
            if(sp==7)add(7,7);
            else if(sp!=1&&sp!=0)add(8,sp);
            if(sp==1) {add(0xe,1);add(9,1);}
            if(sp==3) {add(0xa,3);add(6,3);}
            if(sp==5||sp==8)add(0xf,sp);
            if(clockLow) {
                // Low clock: the first row offers no per-event mission and
                // its reward is a clock reward.
                clockLow=false;lifeTurn=false;
            } else {
                for(int m:{0x11,0x12,0x13})add(m,sp);
                if(!survivalNoDeflect(row.character))add(0x10,sp);
                if(sp==2)add(0x14,2);
                if(sp==5)add(9,5);
                if(sp==4)add(0xa,4);
                if(sp==1)add(7,1);
                if(sp==4)add(0xb,4);
            }
            row.mission=q.at(unsigned(random.bounded(count)));
            row.reward=survivalReward(assets,unsigned(row.mission),sp,lifeTurn);
            lifeTurn=row.reward>=4;
        }
        if(row.character==0x2b) {row.colour=0;row.stage=0xb;row.mission=0x15;row.reward=8;}
    }
    std::swap(rows[unsigned(random.bounded(3))],rows[1]);
    return 3;
}

int survivalCpuSpirit(int character,int drawn) {
    if(character==0x2b)return 7;
    return character>=0x2c&&character<=0x2f?8:drawn;
}
void survivalApplyCandidate(const SurvivalTable& table,GameRandom& random,int modeWord,
                            std::array<SurvivalSeatConfig,2>& config,SurvivalSetup& setup,bool inPlace) {
    const int h=modeWord==0xb?0:1,c=1-h;
    setup.level=table.cpuLevel();
    setup.stage=table.current.stage;
    setup.control[h]=0;
    config[h].spirit=setup.spirit[h]=table.current.humanSpirit;
    setup.control[c]=1;
    config[c].character=table.current.character;
    config[c].colour=table.current.colour;
    // RNG(6) is drawn even when the character dictates its spirit.
    const int drawn=random.bounded(6);
    config[c].spirit=setup.spirit[c]=survivalCpuSpirit(config[c].character,drawn);
    if(config[h].character==config[c].character&&config[h].colour==config[c].colour)config[c].colour=config[h].colour==0;
    for(int i=0;i<2;++i) {
        setup.character[i]=config[i].character;
        setup.colour[i]=config[i].colour;
        setup.rounds[i]=inPlace?1:config[i].roundsToWin;
    }
}

void SurvivalSlide::configure(int cx,int cy,int ox,int oy,int frames) {
    openY=oy;duration=frames;closedX=cx;closedY=cy;openX=ox;
    snap(cx,cy);
    closed=1;
}
void SurvivalSlide::snap(int px,int py) {
    toX=fromX=x=px;toY=fromY=y=py;remaining=0;
}
static void slideTo(SurvivalSlide& s,int tx,int ty) { // 17f3c0
    s.remaining=s.duration;s.toX=tx;s.toY=ty;s.fromX=s.x;s.fromY=s.y;
    if(s.x==tx&&s.y==ty)s.remaining=0;
    s.closed=0;
}
void SurvivalSlide::open() {
    // Compared with the current target: a slide already opening keeps its progress.
    if(toX!=openX||toY!=openY)slideTo(*this,openX,openY);
}
void SurvivalSlide::close() {
    if(toX==closedX&&toY==closedY)return;
    slideTo(*this,closedX,closedY);
    closed=1;
}
int SurvivalSlide::tick() {
    if(remaining>0) {
        const int r=--remaining;
        x=(r*fromX+(duration-r)*toX)/duration;
        y=(r*fromY+(duration-r)*toY)/duration;
        if(r>0)return 2;
    }
    return closed==0;
}
static int pageScroll(int code,int visible,int scroll,int rows) { // 17f528
    const int v=code==3?scroll+visible:code==2?scroll-visible:scroll;
    return v<0?0:std::min(v,rows-visible);
}
static int followScroll(int cursor,int visible,int scroll,int rows) { // 17f560
    int v=std::min(cursor,scroll);
    if(rows<v+visible)v=rows-visible;
    if(cursor>=v+visible)v=cursor-visible+1;
    return std::max(v,0);
}

SurvivalEvents SurvivalRun::begin(GameRandom& random,int modeWord,int humanCharacter) {
    SurvivalEvents events;
    events.pauseRequests=1;
    prev=-1;state=1;fade=0;delay=0;wins=0;elapsedFrames=0;
    // 1822a0 + 182318(7): every panel starts snapped to its closed position.
    title={};message={};legend={};extra={};
    title.slide.configure(0,-0x90,0,0x10,0x10);
    message.slide.configure(0,0x1f6,0,0x156,0x10);
    if(padPort(modeWord)==1)legend.slide.configure(-0x190,0x192,0,0x192,0x10);
    else legend.slide.configure(0x2d0,0x192,0x140,0x192,0x10);
    extra.slide.configure(0x2d0,0x13c,0x140,0x13c,0x10);
    messageText=SurvivalInitialText;legendText=2;
    cursor=scroll=selectorActive=selectorFocus=0;
    selectorSlide.configure(-0x248,0x70,0x38,0x70,0x10);
    table.generate(*assets_,random,0,0,0,humanCharacter,false,rows);
    humanSeat=modeWord==0xb||modeWord==1?0:1;
    table.wins=0;
    return events;
}

int SurvivalRun::grant() {
    lifeGain=clockGain=0;
    const unsigned r=unsigned(table.current.reward);
    if(r<4)lifeGain=assets_->gains[r];
    else if(r<7)clockGain=assets_->gains[r];
    else if(r==7) {lifeGain=assets_->gains[7];clockGain=assets_->gains[8];}
    return int(r);
}
static bool opponentWon(const SurvivalBattle& b) {return b.opponentWins>=b.opponentRequired;} // 14abb0

bool SurvivalRun::perEvent(const SurvivalHuman& human,const SurvivalBattle& battle) {
    if(human.flags23c&0x80||human.life<=0||human.life<human.lifeA38||opponentWon(battle))return false;
    const unsigned m=unsigned(table.current.mission);
    if(m-0x10>=5)return false;
    // A per-event mission is rewarded at once and can be earned repeatedly.
    if(mission[m]>0) {mission[m]=0;pendingReward=grant();}
    return true;
}
bool SurvivalRun::achieved(const SurvivalHuman& human,const SurvivalBattle& battle) const {
    if(state==5||prev==5||opponentWon(battle))return false;
    const unsigned m=unsigned(table.current.mission);
    switch(m<0x16?assets_->missionKind[m]:3) {
    case 0:return mission[m]!=0;
    case 1:return mission[m]>=3;
    case 2:return false;
    default:
        if(state>0)return true;
        if(battle.winner!=human.seat)return false;
        if(!(battle.round>0||battle.state>=4))return false; // 141820
        return battle.state!=4;
    }
}
void SurvivalRun::sample(SurvivalHuman& human,const SurvivalBattle& battle) {
    if(opponentWon(battle))return;
    auto bit=[&](int n) {return human.word248>>n&1;};
    mission[0]=bit(17);mission[1]=bit(18);mission[2]=bit(19);mission[3]=bit(21);
    mission[4]=battle.special==0;
    mission[5]=battle.finish==2;
    mission[6]=bit(22);
    mission[7]=mission[8]=battle.finish==1;
    mission[9]=battle.finish==0;
    mission[10]=battle.finish==3;
    mission[11]=bit(23);
    for(int i=0;i<9;++i)mission[12+i]=human.events[i];
    // The counters f22..f25 accumulate; the per-event bytes are consumed.
    for(int i=4;i<9;++i)human.events[i]=0;
    mission[21]=1;
}

int SurvivalRun::selectorUpdate(const SurvivalPad& pad,SurvivalEvents& events) {
    const int r=selectorSlide.tick();
    if(r==0) {selectorActive=selectorFocus=0;return 0;}
    if(r!=1||!selectorActive||!selectorFocus)return 0;
    // 20e128 with flags 25 (vertical, wrap, cancel refused), rows 0..2, no paging.
    int code=0;
    if(pad.pressed&0x20a) {events.sounds.push_back(0);code=4;}
    else if(pad.pressed&0x404) {events.sounds.push_back(0x24);code=6;}
    else {
        const int old=cursor;
        const int n=old+(pad.repeat&0x10?-1:pad.repeat&0x20?1:0);
        cursor=n>=3?0:n<0?2:n;
        if(cursor!=old) {events.sounds.push_back(0x20);code=1;}
    }
    scroll=followScroll(cursor,3,pageScroll(code,3,scroll,3),3);
    return code;
}

void SurvivalRun::fadeStep() {
    if(prev==5)fade=std::min(fade+8,0xff);
    else if(prev==1) {
        // The first candidate window hides the placeholder battle completely.
        if(table.wins==0)fade=0xff;
        else if(fade<0x81) {fade+=8;if(fade>=0x81)fade=0x80;}
        else {fade-=8;if(fade<0x80)fade=0x80;}
    } else fade=std::max(fade-8,0);
}

void SurvivalRun::drawHud(const SurvivalHuman& human,const SurvivalBattle& battle) {
    hud={};
    hud.boss=table.wins>=0x30;
    hud.reward=table.current.reward;hud.mission=table.current.mission;
    hud.hours=elapsedFrames/216000;hud.minutes=elapsedFrames/3600%60;hud.seconds=elapsedFrames/60%60;
    hud.x=human.seat!=0?0xe:0x12c;
    if(state==1&&table.wins==0)return;
    hud.progress=hud.mission>=0xc&&hud.mission<=0xf;
    hud.visible=true;
    hud.height=hud.boss?0x1c:hud.progress?0x58:0x44;
    if(hud.boss)return;
    // 180ef8 runs from the draw routine: this call is what grants per-event rewards.
    hud.line=perEvent(human,battle)?1:achieved(human,battle)?2:0;
    if(hud.progress)hud.progressValue=mission[unsigned(hud.mission)];
}

SurvivalEvents SurvivalRun::tick(bool skipped,const SurvivalPad& pad,SurvivalHuman& human,SurvivalBattle& battle,
                                 GameRandom& random,int modeWord,std::array<SurvivalSeatConfig,2>& config,SurvivalSetup& setup) {
    SurvivalEvents events;
    for(auto* p:{&title,&message,&legend,&extra})p->slide.tick(); // 1825b8
    const int selected=selectorUpdate(pad,events);
    sample(human,battle);
    if(battle.state==4&&!skipped)++elapsedFrames;
    auto addLife=[&] {
        human.life=std::min(human.life+lifeGain,0xc8);
        events.lifeEffect=true;events.lifeEffectX=int(human.x);
    };
    auto showMessage=[&] {message.slide.open();message.open=1;message.visible=1;};
    if(delay>0)--delay;
    else if(state!=prev) {
        switch(state) {
        case 0:
            pendingReward=-1;messageTimer=0;
            [[fallthrough]];
        case 5:
            for(auto* p:{&title,&message,&legend,&extra}) {p->slide.close();p->open=0;} // 1826b0
            selectorSlide.close();selectorFocus=0;
            break;
        case 1:
            events.continueFlag=true;
            for(auto* p:{&title,&message,&legend}) {p->slide.open();p->visible=p->open=1;} // 182648
            extra.slide.close();extra.open=0;
            messageText=SurvivalChoose;legendText=0;
            cursor=0;
            scroll=followScroll(cursor,3,scroll,3);
            selectorSlide.open();
            selectorActive=1;selectorFocus=0;
            break;
        case 2:
            legendText=1;
            selectorSlide.close();selectorFocus=0;
            messageText=table.wins>=0x31?SurvivalCleared:perEvent(human,battle)?SurvivalNext:
                        achieved(human,battle)?SurvivalAchieved:SurvivalFailed;
            showMessage();
            legend.slide.open();legend.open=1;legend.visible=1;
            break;
        case 3:
            selectorSlide.close();selectorFocus=0;
            messageText=SurvivalRewardText+grant();
            delay=0x1e;
            break;
        default:break;
        }
        prev=state;
        fadeStep();
    } else {
        switch(state) {
        case 0:
            if(pendingReward!=-1) {
                if(lifeGain>0)addLife();
                if(clockGain>0) {
                    const int32_t t=int32_t(battle.clock+clockGain*0xb400);
                    events.sounds.push_back(0x41);
                    battle.clock=t>0x459bff?0x459c00:t;
                }
                messageText=SurvivalRewardText+pendingReward;
                showMessage();
                pendingReward=-1;clockGain=0;messageTimer=0xb4;lifeGain=0;
            } else if(messageTimer>0)--messageTimer;
            else {message.slide.close();message.open=0;}
            break;
        case 1:
            if(selected==4) {
                table.confirm(table.wins,rows[unsigned(cursor)]);
                human.events={};mission={}; // 181548
                state=5;
            } else if(selectorSlide.settled())selectorFocus=1;
            break;
        case 2:
            if(pad.pressed&0x60e) {
                events.sounds.push_back(0);
                if(table.wins>=0x31||perEvent(human,battle)) {delay=0x1e;state=1;}
                else state=achieved(human,battle)?3:4;
            }
            break;
        case 3:
            if(lifeGain>0) {addLife();lifeGain=0;delay=10;}
            else if(clockGain>0) {
                // One count per step; holding a button removes the 3-frame gap.
                int32_t t=battle.clock;
                if(t>0x459bff) {clockGain=0;t=0x459c00;}
                else {
                    t+=0xb400;
                    events.sounds.push_back(0x42);
                    --clockGain;
                    if(t>0x459bff) {clockGain=0;t=0x459c00;}
                }
                battle.clock=t;
                delay=pad.held&0x60e?0:3;
            } else if(pad.pressed&0x60e) {events.sounds.push_back(0);state=1;}
            break;
        case 4:
            delay=0x1e;state=1;
            break;
        case 5:
            // The reload waits for the black fade and the title panel.
            if(fade>=0xff&&title.slide.settled()) {
                delay=4;state=0;
                savedLife=human.life;savedClock=battle.clock;
                events.reload=true;
                survivalApplyCandidate(table,random,modeWord,config,setup,true);
            }
            break;
        default:break;
        }
        if(state!=prev)selectorFocus=0;
        fadeStep();
    }
    // The battle stays frozen behind the candidate window and the reload;
    // the reward states 3 and 4 let it run even while a delay is pending.
    if(state==1||state==5||(state!=3&&state!=4&&delay>0))++events.pauseRequests;
    // 1810f8 is not called on a skipped frame: the panel is absent from it.
    if(skipped)hud={};
    else drawHud(human,battle);
    return events;
}

std::vector<std::string> SurvivalRun::hudLines() const {
    std::vector<std::string> lines;
    if(!hud.visible)return lines;
    const auto& a=*assets_;
    auto print=[&](const std::string& format,auto... values) {
        char text[0x60];
        std::snprintf(text,sizeof text,format.c_str(),values...);
        lines.emplace_back(text);
    };
    print(a.hud[0],hud.hours,hud.minutes,hud.seconds);
    if(hud.boss)return lines;
    print(a.hud[1],a.rewards.at(unsigned(hud.reward)).c_str());
    print(a.hud[hud.line==2?3:2],a.missions.at(unsigned(hud.mission)).c_str());
    if(hud.progress)print(a.hud[size_t(4+hud.mission-0xc)],hud.progressValue);
    return lines;
}

void SurvivalRun::defeated(GameRandom& random,int n,int stage,int character,int humanCharacter,int32_t clock) {
    table.generate(*assets_,random,n,stage,character,humanCharacter,clock/0xb400<0x28,rows);
    wins=n;
    if(n<0x31)state=2;
}

int survivalRoundTicks(int carried) {
    if(carried==-1)return 0x63*0xb4;
    int t=carried+0xff;
    if(t<0)t=carried+0x1fe;
    return t>>8;
}
int survivalRoundWinner(int lifeWinner,int loserLife,int modeWord) {
    return loserLife>0?(modeWord==0xb?1:0):lifeWinner;
}
SurvivalItemDrop survivalItemDrop(GameRandom& random,int stageKind) {
    SurvivalItemDrop drop;
    const int r=random.bounded(100);
    if(r<25)drop.kind=8;
    else if(r<50)drop.kind=7;
    else if(r<75)drop.kind=stageKind==0xff?8:stageKind;
    else drop.kind=random.bounded(100)<0x1e?1:3;
    drop.side=random.bounded(2);
    drop.where=random.bounded(4);
    return drop;
}

void survivalSessionFlags(const SystemData& data,int modeWord,int winnerSeat,int c,int count,SurvivalSessionFlags& flags) {
    if(!((modeWord==0xb&&winnerSeat==0)||(modeWord==0xc&&winnerSeat==1)))return;
    if(data.option(0x40)&&c==0x2a)flags[0]=1;
    if(data.option(0x46)&&count>=0x31)flags[7]=1;
    static constexpr int rule[6][2]={{0x3f,0x29},{0x3e,0x28},{0x42,0x2c},{0x43,0x2d},{0x45,0x2f},{0x44,0x2e}};
    for(int i=0;i<6;++i)if(data.option(size_t(rule[i][0]))&&c==rule[i][1])flags[size_t(1+i)]=1;
}

SurvivalMatchEnd survivalMatchEnd(SurvivalRun& run,GameRandom& random,const SystemData& data,int modeWord,int winnerSeat,
                                  std::array<SurvivalSeatConfig,2>& config,const SurvivalSetup& setup,int32_t clock,
                                  SurvivalSessionFlags& flags) {
    SurvivalMatchEnd end;
    end.modeWord=modeWord;
    const int n=run.table.wins;
    end.won=(modeWord==0xb&&winnerSeat==0)||(modeWord==0xc&&winnerSeat==1);
    if(end.won) {
        survivalSessionFlags(data,modeWord,winnerSeat,config[modeWord==0xb?1:0].character,n+1,flags);
        if(n+1>=0x31)end.finished=end.cleared=true;
        // 145d48: the defeated character is the setup entry of the other seat.
        run.defeated(random,n+1,setup.stage,setup.character[winnerSeat!=0?0:1],config[modeWord==0xb?0:1].character,clock);
    } else end.finished=true;
    if(end.finished) {
        // Game Over 138340 reads the arcade mode words 1/2.
        end.stage=setup.stage;
        config[0].arcadeProgress=config[1].arcadeProgress=0;
        end.modeWord=modeWord==0xb?1:2;
    }
    return end;
}

static constexpr size_t survivalScore=0x63fc;
int survivalRecordIndex(const SurvivalSeatConfig& seat) {
    return seat.version==1&&unsigned(seat.character-0x16)<4?seat.character+0x1b:seat.character;
}
SurvivalRecord survivalRecord(const SystemData& data,unsigned index) {
    const size_t at=survivalScore+8*index;
    return {int8_t(data.image()[at]),uint32_t(data.word(at+4))};
}
void survivalStoreRecord(SystemData& data,int modeWord,const std::array<SurvivalSeatConfig,2>& config,int wins,int seconds) {
    const size_t at=survivalScore+8*size_t(survivalRecordIndex(config[modeWord==2?1:0]));
    const int8_t count=int8_t(wins),stored=int8_t(data.image()[at]);
    // More wins replace the record; equal wins keep the shorter time.
    if(stored<count) {data.image()[at]=uint8_t(count);data.setWord(at+4,seconds);}
    else if(stored==count&&uint32_t(seconds)<uint32_t(data.word(at+4)))data.setWord(at+4,seconds);
}
}
