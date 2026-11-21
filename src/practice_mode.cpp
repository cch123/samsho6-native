#include "practice_mode.hpp"
#include <algorithm>
#include <cstring>
#include <fstream>
#include <stdexcept>

namespace ss6 {
// Each predicate first tests one byte of the edited descriptor, then falls
// back to the stock system id (which is 6 for an edited system, so the
// fallback is false there).
bool PracticeSystem::hyperSlash() const {const auto* d=descriptor();return (d&&d[3]==0xb)||id==0;}
bool PracticeSystem::comboSlash() const {const auto* d=descriptor();return (d&&d[3]==0xd)||id==3;}
bool PracticeSystem::rageSkills() const {
    const auto* d=descriptor();
    if(d&&d[1]!=4)return true;
    return id==7||id==8||(id>=1&&id<=5);
}
bool PracticeSystem::systemSkills() const {
    const auto* d=descriptor();
    if(d&&d[2]!=7)return true;
    return id==1||id==5;
}
bool PracticeSystem::freeSystemSkill() const {const auto* d=descriptor();return (d&&d[2]==8)||id==1;}
bool PracticeSystem::hasSpiritGauge() const {
    const auto* d=descriptor();
    return (d&&(d[3]==0xe||d[5]==0x18||d[5]==0x19))||id==4;
}
bool PracticeSystem::hasTimeGauge() const {const auto* d=descriptor();return (d&&d[2]==9)||id==5;}

PracticeTables::PracticeTables(const std::filesystem::path& assets) {
    std::ifstream in(assets/"practice_mode.bin",std::ios::binary);
    std::vector<uint8_t> raw((std::istreambuf_iterator<char>(in)),std::istreambuf_iterator<char>());
    size_t at=0;
    auto need=[&](size_t n){if(at+n>raw.size())throw std::runtime_error("practice_mode.bin is truncated");};
    auto u16=[&]{need(2);uint16_t v;std::memcpy(&v,&raw[at],2);at+=2;return v;};
    auto u32=[&]{need(4);uint32_t v;std::memcpy(&v,&raw[at],4);at+=4;return v;};
    if(raw.size()<8||std::memcmp(raw.data(),"PRC1",4))throw std::runtime_error("practice_mode.bin is missing or foreign");
    at=4;
    strings_.resize(u32());
    for(auto& s:strings_){const size_t n=u16();need(n);s.assign(reinterpret_cast<const char*>(&raw[at]),n);at+=n;}
    groups_.resize(u32());
    for(auto& g:groups_){g.resize(u16());for(auto& v:g)v=u16();}
    skills_.resize(u32());
    for(auto& s:skills_) {
        need(12);
        std::memcpy(&s.id,&raw[at],2);s.technique=raw[at+2];s.kind=raw[at+3];s.type=raw[at+4];at+=8;s.name=u32();
    }
    for(auto& row:caps_)for(auto& v:row)v=int32_t(u32());
    if(at!=raw.size()||groups_.size()!=Misc+1)throw std::runtime_error("practice_mode.bin has an unexpected layout");
}
int PracticeTables::listStart(int id) const {
    for(size_t i=0;i<skills_.size();++i)if(skills_[i].id==id)return int(i);
    return -1;
}
int PracticeTables::listCount(int id) const {
    const int first=listStart(id);
    if(first<0)return 0;
    // 15f590: the list runs while the following ids repeat the head or are -1.
    size_t i=size_t(first)+1;
    while(i<skills_.size()&&(skills_[i].id==id||skills_[i].id==-1))++i;
    return int(i)-first;
}
int PracticeTables::skillIndex(int id,int n) const {const int first=listStart(id);return first<0?-1:first+n;}
int PracticeTables::swordCap(int system,int rageState) const {
    const auto& row=caps_.at(system);
    return rageState==2?row[2]:rageState==1?row[1]:row[0];
}

void PracticeSettings::reset() {
    a.fill(0);committedA=a;
    b.fill(0);b[10]=b[11]=99;committedB=b;
}
void PracticeSettings::commit() {committedA=a;committedB=b;}
void PracticeSettings::enterBattle() {
    if(b[0]==9)b[0]=committedB[0]=0;
    b[5]=committedB[5]=0;
}
int PracticeSettings::optionSlot(int row,int value) {
    if(row==2)return value>=0&&value<=5?value:-1;
    if(row==4)return value>=0&&value<=5?value+6:-1;
    return -1;
}
int PracticeSettings::behaviour(const PracticeSystem& dummy) const {
    switch(uint32_t(committedA[2])) {
    case 0:return committedB[0]==9&&dummy.comboSlash()?10:committedB[0];
    case 1:return committedB[1]+11;
    case 2:return committedB[2]+20;
    case 3:return committedB[3]+25;
    case 4:return committedB[4]+30;
    case 5:return actions.at(committedB[5])+0x26;
    case 6:return 0x23;
    case 7:return 0x24;
    case 8:return 0x25;
    default:return -1;
    }
}
int practiceLocalSeat(int mode,int versusSeat,int linkSeat) {
    if(mode==3)return versusSeat;
    if(mode==13||mode==14)return linkSeat;
    return mode==2||mode==5||mode==8||mode==10||mode==12||mode==16||mode==18;
}
int PracticeState::humanSeat() const {return mode==9?recording:mode==10?!recording:otherModeSeat;}
int PracticeState::dummySeat() const {return mode==9?!recording:mode==10?recording:(otherModeSeat+1)%2;}
int PracticeState::behaviour(const PracticeSystem& dummy) const {
    if(!practice())return 0x23;
    int code=settings.behaviour(dummy);
    // The practising player's own fighter is the CPU while recording: no ACTION, no HYPER/COMBO SLASH.
    if(recordingActive()&&((code>=0x26&&code<0x46)||code==9||code==10))code=0;
    return code;
}

void PracticeSelector::init() {value=0;flags=5;setRange(0,1,1,0);}
void PracticeSelector::setRange(int lo,int hi,int stepSize,int pageSize) {
    if(lo==hi)++hi;
    if(hi<lo)std::swap(lo,hi);
    min=lo;max=hi;step=stepSize?stepSize:1;page=pageSize<hi?pageSize:0;
    setValue(value);
}
void PracticeSelector::setValue(int v) {
    // 20e0d0: with the wrap flag the wrapped value is stored and then
    // overwritten by the raw argument, so an out-of-range value survives.
    if(v<min){if(!(flags&4))v=min;}
    else if(v>=max){if(!(flags&4))v=max-1;}
    value=v;
}
int PracticeSelector::input(const MenuPad& pad,std::vector<int>& sounds) {
    const uint32_t f=flags;
    const int old=value;
    bool confirm=false,cancel=false;
    if(!(f&0x20000)&&(pad.pressed&8))confirm=true;
    else if(pad.pressed&0x202)confirm=true;
    else cancel=(pad.pressed&0x404)!=0;
    if(confirm) {
        bool refused=(f&0x10)!=0;
        if(!refused&&(f&0x800)&&disabled)refused=(disabled[(old<0?old+31:old)>>5]>>(old&31))&1;
        if(!(f&0x300))sounds.push_back(refused?0x24:0);
        return refused?6:4;
    }
    if(cancel) {
        if(!(f&0x500))sounds.push_back(0x24);
        return f&0x20?6:5;
    }
    int delta=0;
    if(f&2){if(pad.repeat&0x40)delta=-step;else if(pad.repeat&0x80)delta=step;}
    if((f&1)&&delta==0){if(pad.repeat&0x10)delta=-step;else if(pad.repeat&0x20)delta=step;}
    if(f&8)delta=-delta;
    if(f&0x40000)delta=0;
    value=old+delta;
    if(value>=max)value=f&4?min:max-1;
    else if(value<min)value=f&4?max-1:min;
    const auto moveSound=[&]{if(!(f&0x80))sounds.push_back(0x20);};
    if(value!=old){moveSound();return 1;}
    if(page<0)return 0;
    // The page keys sound even when the value cannot change; 0x200000 and
    // 0x800000 (first/last) work with a zero page size and jump to 0, not min.
    int code=1;
    if(page>0&&(pad.repeat&0x100000)){moveSound();value=std::max(0,value-page*step);code=2;}
    else if(page>0&&(pad.repeat&0x400000)){moveSound();value=std::min(max-1,value+page*step);code=3;}
    else if(pad.repeat&0x200000){moveSound();value=0;}
    else if(pad.repeat&0x800000){moveSound();value=max-1;}
    return value!=old?code:0;
}

void PracticeSlide::set(int cx,int cy,int ox,int oy,int frameCount) {
    closedX=cx;closedY=cy;openX=ox;openY=oy;duration=frameCount;
    snap(cx,cy);closed=1;
}
void PracticeSlide::snap(int px,int py) {targetX=startX=x=px;targetY=startY=y=py;frames=0;}
void PracticeSlide::move(int tx,int ty,int frameCount) {
    duration=frames=frameCount;targetX=tx;targetY=ty;startX=x;startY=y;
    if(x==tx&&y==ty)frames=0;
    closed=0;
}
void PracticeSlide::open() {if(targetX!=openX||targetY!=openY)move(openX,openY,duration);}
void PracticeSlide::close() {if(targetX!=closedX||targetY!=closedY){move(closedX,closedY,duration);closed=1;}}
int PracticeSlide::step() {
    if(frames>0) {
        --frames;
        x=(frames*startX+(duration-frames)*targetX)/duration;
        y=(frames*startY+(duration-frames)*targetY)/duration;
        if(frames>0)return 2;
    }
    return closed==0;
}
int practiceScrollPage(int code,int visible,int scroll,int count) {
    int v=code==2?scroll-visible:code==3?scroll+visible:scroll;
    if(v<0)return 0;
    return std::min(v,count-visible);
}
int practiceScrollFollow(int cursor,int visible,int scroll,int count) {
    int v=std::min(cursor,scroll);
    if(count<v+visible)v=count-visible;
    if(cursor>=v+visible)v=cursor-visible+1;
    return std::max(v,0);
}

void PracticeMenu::init(PracticeSettings& settings,std::vector<PracticeHelp>& help) {
    settings.enterBattle();
    visible=12;scroll=active=focused=0;
    slide.set(0,0,0,0,1);
    rows.init();rows.setRange(0,12,1,0);
    values.init();values.setFlag(1,true);values.setFlag(0,false);
    prevLevel=-1;level=0;
    // 2111e8 with a default dummy: level 0 never reads it.
    help.push_back({PracticeHelp::Text,0,rows.value});
}
void PracticeMenu::describe(const PracticeSettings& settings,const PracticeFighter& dummy,const PracticeTables& tables,
                            std::vector<PracticeHelp>& help) const {
    const int row=rows.value;
    // The option slot comes from the committed CPU TYPE / gauge cursor.
    const int slot=PracticeSettings::optionSlot(row,settings.committedA.at(row));
    const int value=values.value;
    if(level==2) {
        switch(slot) {
        case 0:
            if(value!=9)help.push_back({PracticeHelp::Text,7,value});
            else help.push_back({PracticeHelp::Text,dummy.system.comboSlash()?9:8,0});
            break;
        case 1:case 2:case 3:case 4:help.push_back({PracticeHelp::Text,9+slot,value});break;
        case 5:help.push_back({PracticeHelp::Skill,tables.skillIndex(dummy.listId(),settings.actions.at(value)),0});break;
        default:break;
        }
    } else if(level==1) {
        static constexpr int ids[7]={-1,-1,1,2,0xe,6,3};
        if(row<7&&ids[row]>=0)help.push_back({PracticeHelp::Text,ids[row],value});
    } else help.push_back({PracticeHelp::Text,0,row});
}
void PracticeMenu::enterValue(const PracticeSettings& settings,int row) {
    static constexpr int counts[7]={0,0,9,4,6,14,2};
    if(row<7&&counts[row])values.setRange(0,counts[row],1,0);
    values.value=settings.a.at(row);
    // GAUGE SETTING is a vertical list; every other row edits left/right.
    values.setFlag(1,row!=4);values.setFlag(0,row==4);
}
void PracticeMenu::enterOption(PracticeSettings& settings,const PracticeFighter& dummy,const PracticeTables& tables,int row) {
    const int slot=PracticeSettings::optionSlot(row,settings.a.at(row));
    switch(slot) {
    case 0:
        // 59cdec is patched in place: the tenth STAND name persists until the next patch.
        if(dummy.system.hyperSlash()){standOptions=10;standNinth=PracticeTables::HyperSlash;}
        else if(dummy.system.comboSlash()){standOptions=10;standNinth=PracticeTables::ComboSlash;}
        values.setRange(0,dummy.system.hyperSlash()||dummy.system.comboSlash()?10:9,1,0);
        break;
    case 1:values.setRange(0,9,1,0);break;
    case 2:case 3:case 4:values.setRange(0,5,1,0);break;
    case 5: {
        const int id=dummy.listId(),first=tables.listStart(id),n=tables.listCount(id);
        const bool type1=dummy.system.systemSkills(),type2=dummy.system.rageSkills();
        int count=0;
        for(int i=0;i<n;++i) {
            const auto type=tables.skill(first+i).type;
            if((type==1&&!type1)||(type==2&&!type2))continue;
            settings.actions.at(count++)=uint8_t(i);
        }
        values.setRange(0,count,1,0);
        break;
    }
    case 6:case 7:values.setRange(0,3,1,0);break;
    case 8:case 9:values.setRange(0,0x65,1,10);break;
    case 10:case 11:values.setRange(0,0x64,1,10);break;
    default:break;
    }
    if(slot!=-1)values.value=settings.b.at(slot);
    values.setFlag(1,true);values.setFlag(0,false);
}
int PracticeMenu::update(const MenuPad& pad,PracticeSettings& settings,const PracticeFighter& dummy,const PracticeTables& tables,
                         std::vector<int>& sounds,std::vector<PracticeHelp>& help) {
    const int moving=slide.step();
    int row=rows.value;
    if(moving!=1){if(moving==0)active=focused=0;return 0;}
    if(!active||!focused)return 0;
    int event=0;
    if(level!=prevLevel) {
        // Every level change commits; a cancel restored the working value beforehand.
        settings.commit();
        if(level==1)enterValue(settings,row);
        else if(level==2)enterOption(settings,dummy,tables,row);
        if(level>=0&&level<=2)describe(settings,dummy,tables,help);
        prevLevel=level;
    } else if(level==0) {
        const int k=rows.input(pad,sounds);
        scroll=practiceScrollPage(k,visible,scroll,rows.max);
        scroll=practiceScrollFollow(rows.value,visible,scroll,rows.max);
        row=rows.value;
        if(k==4) {
            static constexpr int events[12]={1,2,0,0,0,0,0,4,5,6,7,8};
            if(events[row])event=events[row];else level=1;
        } else if(k==5)event=3;
        else if(k>=1&&k<=3)describe(settings,dummy,tables,help);
    } else if(level==1) {
        const int k=values.input(pad,sounds);
        const int slot=PracticeSettings::optionSlot(row,settings.a.at(row));
        if(k==4)level=slot==-1?0:2;
        else if(k==5){level=0;settings.a.at(row)=settings.committedA.at(row);}
        else if(k>=1&&k<=3){settings.a.at(row)=values.value;describe(settings,dummy,tables,help);}
    } else if(level==2) {
        const int k=values.input(pad,sounds);
        const int slot=PracticeSettings::optionSlot(row,settings.a.at(row));
        if(k==4)level=gaugeWindow();
        else if(k==5){level=1;settings.b.at(slot)=settings.committedB.at(slot);}
        else if(k>=1&&k<=3){settings.b.at(slot)=values.value;describe(settings,dummy,tables,help);}
    }
    ++counter;
    return event;
}

void PracticeConfirm::init() {
    visible=1;scroll=active=focused=0;
    slide.set(1,0,0,0,0x10);
    choice.init();choice.setRange(0,2,1,0);
    choice.setFlag(0,false);choice.setFlag(1,true);
    prompt=PracticeTables::ConfirmCaption;
}
int PracticeConfirm::update(const MenuPad& pad,std::vector<int>& sounds) {
    const int moving=slide.step();
    if(moving!=1){if(moving==0)active=focused=0;return 0;}
    if(!active||!focused)return 0;
    int k=choice.input(pad,sounds);
    scroll=practiceScrollPage(k,visible,scroll,choice.max);
    scroll=practiceScrollFollow(choice.value,visible,scroll,choice.max);
    if(k==4&&choice.value)k=5;
    return k;
}
bool PracticeSubWindow::gate() {
    const int moving=slide.step();
    if(moving!=1){if(moving==0)active=focused=0;return false;}
    return active&&focused;
}

void PracticeWindow::init(PracticeState& practice,std::vector<PracticeHelp>& help) {
    const int seat=practice.localSeat();
    resetDamage=true;
    state=1;lastState=-1;   // the battle starts with the menu open; 12d3864 (dim) keeps its value
    menu.init(practice.settings,help);
    menu.slide.set(seat?0x294:-0x26c,0x4c,0x14,0x4c,0x10);
    keyConfig.slide.set(seat?-0x230:0x2d0,0x5e,0x50,0x5e,0x10);
    list.active=list.focused=0;
    list.slide.set(seat?0x34c:-0x180,0x50,seat?0x1bc:0x10,0x50,0x10);
    subList.active=subList.focused=0;
    subList.slide.set(seat?0x360:-0x180,0x98,seat?0x1d0:0x10,0x98,0x10);
    detailActive=detailFocused=0;
    confirm.init();
    pendingKind=startCode=-1;
    practice.replay=practice.recording=false;
}
std::array<bool,4> PracticeWindow::begin(const MenuPad& pad,PracticeState& practice,const PracticeFighter& dummy,const PracticeTables& tables) {
    out_=PracticeWindowResult{};
    menuEvent_=menu.update(pad,practice.settings,dummy,tables,out_.sounds,out_.help);
    confirmEvent_=confirm.update(pad,out_.sounds);
    const bool key=keyConfig.gate(),first=list.gate(),second=subList.gate();
    return {key,first,second,detailActive&&detailFocused};
}
PracticeWindowResult PracticeWindow::finish(const MenuPad& pad,const PracticeSubEvents& sub,PracticeState& practice,const PracticeFighter& dummy) {
    auto& help=out_.help;
    const int seat=practice.localSeat();
    const auto closeOthers=[&](bool keyToo) {
        if(keyToo){keyConfig.slide.close();keyConfig.focused=0;list.slide.close();list.focused=0;subList.slide.close();subList.focused=0;}
        confirm.slide.close();confirm.focused=0;
    };
    if(state!=lastState) {
        switch(state) {
        case 0:
            menu.slide.close();menu.focused=0;help.push_back({PracticeHelp::Close,0,0});
            if(lastState==2) {
                // The hidden window is not slid out: it is placed at its closed position at once.
                menu.slide.snap(menu.slide.closedX,menu.slide.closedY);menu.focused=0;help.push_back({PracticeHelp::Snap,0,0});
            }
            break;
        case 1:
            help.push_back({PracticeHelp::Page,4,0});help.push_back({PracticeHelp::Open,0,0});
            if(state<lastState)help.push_back({PracticeHelp::Text,0,menu.rows.value});
            menu.slide.open();menu.focused=menu.active=1;
            closeOthers(true);
            break;
        case 2:menu.focused=0;break;
        case 3:
            list.focused=0;
            confirm.prompt=pendingKind==7?PracticeTables::PromptSelect:PracticeTables::PromptTitle;
            confirm.slide.open();confirm.focused=confirm.active=1;
            confirm.choice.setValue(1);
            confirm.scroll=practiceScrollFollow(confirm.choice.value,confirm.visible,confirm.scroll,confirm.choice.max);
            break;
        case 4:
            help.push_back({PracticeHelp::Close,0,0});
            menu.slide.close();menu.focused=0;
            closeOthers(true);
            break;
        case 5:
            help.push_back({PracticeHelp::Page,0,0});help.push_back({PracticeHelp::Open,0,0});
            keyConfig.slide.open();keyConfig.focused=keyConfig.active=1;
            closeOthers(false);
            break;
        case 6:
            help.push_back({PracticeHelp::Page,5,0});help.push_back({PracticeHelp::Open,0,0});
            list.slide.open();list.focused=list.active=1;
            subList.slide.close();subList.focused=0;
            menu.slide.close();menu.focused=0;
            help.push_back({PracticeHelp::List,0x29,sub.listCursor});
            break;
        case 7:
            help.push_back({PracticeHelp::Open,0,0});
            if(lastState<state) {
                out_.fillSubList=true;
                // The sub-list of the practising player on the right slides in from the right edge.
                if(sub.listCursor==0){if(seat==1){subList.slide.closedX=0x360;subList.slide.openX=0x1d0;}}
                else {
                    if(seat==1){subList.slide.closedX=0x2e8;subList.slide.openX=0x158;}
                    help.push_back({PracticeHelp::List,0x2b,0});
                }
            }
            list.slide.open();list.focused=0;list.active=1;
            subList.slide.open();subList.focused=subList.active=1;
            break;
        case 8:
            if(lastState<state)out_.openDetail=true;
            help.push_back({PracticeHelp::Close,0,0});
            list.slide.close();list.focused=0;
            subList.slide.close();subList.focused=0;
            break;
        default:break;
        }
        lastState=state;
        detailActive=detailFocused=state==8;
    } else {
        switch(state) {
        case 0:
            if(menu.slide.idle()&&(pad.pressed&0x80000))state=1;
            break;
        case 1:case 2: {
            bool start=false,record=false;
            if(menu.slide.idle()) {
                if(menuEvent_==1)start=true;
                else if(menuEvent_==2)record=true;
                else if(menuEvent_==3||(pad.pressed&0x80000)) {
                    // Closing restarts the round only when it changes whether the dummy replays or is human-driven.
                    const int code=practice.behaviour(dummy.system);
                    if(practice.recordingActive())start=true;
                    else if((startCode==0x25)!=(code==0x25))start=true;
                    else if((startCode==0x24)!=(code==0x24))start=true;
                    state=0;
                } else if(state==2&&(pad.pressed&0xf006fe))state=1;
            }
            if(start||record)out_.clearLockCounters=true;
            if(start) {
                practice.settings.commit();
                startCode=practice.behaviour(dummy.system);
                practice.replay=startCode==0x25;practice.recording=false;
                out_.reset=true;state=0;
            } else if(record) {
                practice.settings.commit();
                startCode=practice.behaviour(dummy.system);   // read before the recording word is set
                practice.recording=true;practice.replay=false;
                out_.clearRecording=true;out_.reset=true;state=0;
            } else switch(menuEvent_) {
                // Evaluated even after a close request in the same frame.
                case 4:state=6;break;
                case 5:state=5;break;
                case 6:state=2;break;
                case 7:case 8:pendingKind=menuEvent_;state=3;break;
                default:break;
            }
            break;
        }
        case 3:
            if(confirmEvent_==4) {
                out_.exit=pendingKind==7?1:2;
                if(pendingKind==7)practice.recording=false;
                state=4;
            } else if(confirmEvent_==5)state=1;
            break;
        case 5:if(sub.keyConfig==4||sub.keyConfig==5)state=1;break;
        case 6:
            if(sub.list==4)state=7;
            else if(sub.list==5)state=1;
            else if(sub.list>=1&&sub.list<=3)help.push_back({PracticeHelp::List,0x29,sub.listCursor});
            break;
        case 7:if(sub.subList==4)state=8;else if(sub.subList==5)state=6;break;
        case 8:if(sub.detail==4||sub.detail==5)state=7;break;
        default:break;
        }
        if(state!=lastState)menu.focused=keyConfig.focused=list.focused=subList.focused=detailFocused=confirm.focused=0;
    }
    out_.pause=state>0;
    dim=lastState==8?std::min(dim+8,0xa0):std::max(dim-8,0);
    return out_;
}

void practiceEnforceGauges(PracticeGaugeActor& actor,const PracticeState& practice,const PracticeTables& tables,bool paused) {
    bool needRage=false,needTime=false;
    if(actor.controlKind==1&&actor.behaviour>=0x26&&actor.behaviour<0x46) {
        // The dummy's ACTION must always be available: its gauge is supplied.
        const auto& skill=tables.skill(tables.skillIndex(actor.character+(actor.alternate?0x32:0),actor.behaviour-0x26));
        if(skill.type==2)needRage=true;
        else if(skill.type==1){if(actor.system.freeSystemSkill())actor.flags244&=~0x40u;else needTime=true;}
    }
    const int maximum=(practice.lifePercent(actor.seat)*200+99)/100;
    actor.maxLife=maximum;
    if(actor.life>=maximum)actor.life=maximum;
    auto& rage=actor.rage;
    if(rage[0]==3){rage.fill(0);actor.flags248&=~4u;}
    if(rage[0]!=2) {
        // INFINITY refills every frame, MAX only on frames the battle is paused (menu open or hit-stop).
        const int setting=practice.settings.spiritGauge(actor.seat);
        if(needRage||setting==2||(setting==1&&paused)){rage[3]=0;rage[0]=1;rage[1]=0xb800;rage[2]=0;}
    }
    // 14f220 is not a refill: it re-derives the sword-gauge cap from the rage state and clamps the gauge to it.
    actor.sword[2]=tables.swordCap(actor.system.id,rage[0])<<8;
    if(actor.sword[2]<actor.sword[1])actor.sword[1]=actor.sword[2];
    if(actor.system.hasSpiritGauge()) {
        auto& s=actor.spirit;
        if(s[0]==4){s[0]=2;actor.flags248&=~0x10008u;}
        if(s[0]!=3){s[2]=s[3]=0;s[1]=practice.settings.mikiri(actor.seat)<<9;}
    }
    if(actor.system.hasTimeGauge()) {
        auto& t=actor.timeGauge;
        if(needTime){t[1]=0;t[3]=0xc800;t[0]=0;}
        else if(t[0]==0){t[1]=0;t[3]=practice.settings.mikiri(actor.seat)<<9;}
    }
}

PracticeLifeCommit practiceCommitLife(int32_t life,int32_t pending,int32_t maxLife,bool practice) {
    const bool arm=pending!=0;
    life-=pending;
    if(life>0)return {std::min(life,maxLife),0,arm};
    return practice?PracticeLifeCommit{1,-1,arm}:PracticeLifeCommit{0,1,arm};
}
bool practiceRefillsLife(const PracticeState& practice,int timer28,int character,int bodyAction) {
    return practice.practice()&&timer28==0&&(character!=0xc||bodyAction!=0x279);
}
int practiceTimeMode(const PracticeState& practice,int timeOption,bool linkSubmode) {
    if(practice.survival())return 2;
    if(practice.mode==0||practice.practice())return 3;
    if(linkSubmode)return 0;
    return timeOption==0?0:timeOption==1?1:3;
}
int practiceItemDelivery(const PracticeState& practice,GameRandom& random) {
    const int kind=practice.itemKind();
    return kind==0x13?random.bounded(0x13):kind;
}
void practiceGetUp(int32_t& getUpType,uint32_t& flags248,int controlKind,const PracticeState& practice,
                   const PracticeSystem& dummy,GameRandom& random) {
    if(!practice.practice()||controlKind!=1||(flags248&0x20000000))return;
    const int code=practice.behaviour(dummy);
    if(code!=0x24&&code!=0x25) {
        int type=practice.ukemi();
        if(type==3){const int roll=random.bounded(100);type=roll<0x22?3:roll<0x43?2:1;}
        if(type==1||type==2)getUpType=type;
    }
    flags248|=0x20000000;
}
void PracticeDamage::add(int32_t damage) {
    if(frameFlag){frameFlag=0;last=0;}   // first hit of this outer frame
    if(newCombo){newCombo=0;total=0;}
    total+=damage;last+=damage;
    if(total>=1000)total=999;
    maxDamage=std::max(maxDamage,total);
}
void PracticeKeyHistory::clear() {neutral=index=0;held.fill(0);shown.fill(0);}
void PracticeKeyHistory::push(uint32_t mask) {
    mask&=0xffff;
    if(mask==0x10)++neutral;
    else {
        // Two seconds of neutral input empty the display before the next entry.
        if(neutral>=0x78)clear();
        neutral=0;
    }
    const int next=index+1<24?index+1:0;
    // An unchanged direction/attack part is not repeated: only the held-button bits are shown.
    const uint32_t entry=(held[index]&0x1ff)==(mask&0x1ff)?mask&0xfe00:mask;
    if(entry){held[next]=uint16_t(mask);shown[next]=uint16_t(entry);index=next;}
}
uint32_t practiceKeyMask(const PracticeKeyFeatures& f) {
    uint32_t mask=0;
    for(int i=0;i<6;++i)if(f.buttons[i])mask|=0x200u<<i;
    for(int i=0;i<9;++i)if(f.motions[i])mask|=1u<<i;
    return mask;
}
PracticeClock practiceClock(const PracticeState& practice,const std::array<int,2>& index) {
    const bool play=practice.replayActive();
    if(!play&&!practice.recordingActive())return {false,false,0,0};
    const int left=600-index[play?1:0];
    return {true,play,std::max(0,left/60),std::max(0,left%60*1000/60)};
}
bool practiceResetControl(PracticeRecordActor& actor,const PracticeState& practice) {
    if(!practice.practice()&&!practice.survival())return false;
    if(practice.recordingActive()) {
        actor.flags240|=8;
        actor.controlKind=(actor.controlKind+1)%2;
        if(actor.controlKind==0)actor.flags240|=2;
    } else if(practice.replayActive()&&actor.controlKind==1)actor.flags240|=4;
    return true;
}
PracticeSampling practiceSampling(const PracticeRecordActor& actor) {
    const bool playback=(actor.flags240>>2)&1;
    return {actor.flags240&8?(actor.seat+1)%2:actor.seat,(actor.flags240&2)||playback?actor.index:-1,playback};
}
void practiceAdvanceRecording(PracticeRecordActor& actor,bool roundRunning) {
    if(!roundRunning)return;
    ++actor.index;
    if(actor.flags240&4)actor.index%=0x2d0;
}
int PracticeSelectRouting::characterPort(int mode,int seat,const std::array<int,2>& committed) {
    if(mode!=9&&mode!=10)return seat;
    const int own=mode==10;                 // the practising seat chooses first
    if(seat!=own&&committed[own]==0)return -1;
    // Counted on every visit once the practising seat has committed, also after it reached zero.
    if(committed[own]==1&&--delay>0)return -1;
    return own;
}
int PracticeSelectRouting::spiritPort(int mode,int seat,const std::array<int,2>& progress,const std::array<int,2>& spirit) {
    if(mode!=9&&mode!=10)return seat;
    const int own=mode==10;
    if(seat!=own) {
        // The dummy's spirit waits until the practising seat has chosen; spirit 6 holds it through its second step.
        if(progress[own]!=1&&progress[own]!=2)return -1;
        if(progress[own]==1&&spirit[own]==6)return -1;
    }
    return own;
}
}
