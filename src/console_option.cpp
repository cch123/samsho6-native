#include "console_option.hpp"
#include "scalar_float.hpp"
#include <algorithm>
#include <fstream>
#include <stdexcept>

namespace ss6 {
namespace {
using T=ConsoleOptionTables;
constexpr uint32_t white=0xffffff,red=0xff0000;
constexpr int rowX=0x44,rowY=0x58,rowStep=0x18,valueX=0x12c;

// sprintf with the two original formats "%d" and "%d%s".
std::string formatValue(const std::string& fmt,int value,const std::string& suffix) {
    std::string out;
    for(size_t i=0;i<fmt.size();++i) {
        if(fmt[i]!='%'||i+1==fmt.size()){out+=fmt[i];continue;}
        const char c=fmt[++i];
        if(c=='d')out+=std::to_string(value);
        else if(c=='s')out+=suffix;
        else out+=c;
    }
    return out;
}
// Value tables are indexed by an unchecked byte. The original reads past
// its stack copy for an out-of-range byte; that garbage is not reproduced.
const std::string& pick(const std::vector<std::string>& table,unsigned index) {
    static const std::string none;
    return index<table.size()?table[index]:none;
}
uint32_t argb(int alpha,uint32_t colour) {return (uint32_t(alpha)<<24)+colour;}

unsigned topInput(const MenuPad& p) {             // 1d0060
    unsigned v=0;
    if(p.pressed&0x404)v=8;
    if(p.pressed&0x20a)v|=4;
    if(p.repeat&0x10)v|=1;
    if(p.repeat&0x20)v|=2;
    return v;
}
unsigned gameInput(const MenuPad& p) {            // 1d2238
    unsigned v=0;
    if(p.pressed&0x404)v=0x400;
    if(p.pressed&0x20a)v|=0x100;
    if(p.repeat&0x10)v|=0x2000|0x01|0x10;
    if(p.repeat&0x20)v|=0x4000|0x02|0x20;
    if(p.repeat&0x40)v|=0x04|0x80;
    if(p.repeat&0x80)v|=0x08|0x40;
    if(p.pressed&0x100000)v|=0x800;
    if(p.pressed&0x400000)v|=0x1000;
    return v;
}
unsigned soundInput(const MenuPad& p) {           // 1dcbd8
    unsigned v=0;
    if(p.pressed&0x404)v=0x200;
    if(p.pressed&0x20a)v|=0x100;
    if(p.repeat&0x10)v|=0x400|0x10;
    if(p.repeat&0x20)v|=0x800|0x20;
    if(p.pressed&0x10)v|=1;
    if(p.pressed&0x20)v|=2;
    if(p.pressed&0x40)v|=8;
    if(p.pressed&0x80)v|=4;
    if(p.repeat&0x80)v|=0x40;
    if(p.repeat&0x40)v|=0x80;
    return v;
}
}

ConsoleOptionTables::ConsoleOptionTables(const std::filesystem::path& assets) {
    const auto file=assets/"console_option.bin";
    std::ifstream in(file,std::ios::binary);
    std::vector<uint8_t> raw((std::istreambuf_iterator<char>(in)),std::istreambuf_iterator<char>());
    size_t at=0;
    auto need=[&](size_t n){if(at+n>raw.size())throw std::runtime_error("Truncated option tables: "+file.string());};
    auto u16=[&]{need(2);const unsigned v=raw[at]|raw[at+1]<<8;at+=2;return v;};
    auto u32=[&]{need(4);const uint32_t v=raw[at]|raw[at+1]<<8|raw[at+2]<<16|uint32_t(raw[at+3])<<24;at+=4;return v;};
    if(!in||raw.size()<10||u32()!=0x4e54504f||u32()!=1||u16()!=GroupCount)
        throw std::runtime_error("Invalid option tables: "+file.string());
    for(auto& group:text) {
        group.resize(u16());
        for(auto& s:group){const size_t n=u16();need(n);s.assign(raw.begin()+at,raw.begin()+at+n);at+=n;}
    }
    static constexpr std::array<size_t,GroupCount> sizes{5,5,15,15,3,2,15,3,3,3,6,6,2,2,2,2,4,4,2};
    for(size_t g=0;g<GroupCount;++g)if(text[g].size()!=sizes[g])throw std::runtime_error("Unexpected option table layout");
    static constexpr std::array<Group,4> helps{TopHelp,GameHelp,SoundHelp,SaveHelp};
    for(size_t h=0;h<4;++h) {
        helpScroll[h].resize(text[helps[h]].size());
        for(auto& f:helpScroll[h]){need(1);f=raw[at++];}
    }
    for(auto& c:gameColour)c=u32();
    for(auto& c:soundColour)c=u32();
    need(2);mikiriDefault=raw[at++];kyouchiDefault=raw[at++];
    mixerDefault=int32_t(u32());
    for(auto& s:scalar)s=u32();
    if(at!=raw.size())throw std::runtime_error("Trailing option table data");
}

ConsoleOption::ConsoleOption(const ConsoleOptionTables& tables,SystemData& data):tables_(tables),data_(data) {
    mixerVolume=unpackedMixerVolume(tables,data.setting(4));
}
int32_t ConsoleOption::volumeWord(uint8_t volume,T::Scalar scale,T::Scalar unit) const {
    // Two separate mul.s, then cvt.w.s: (int)(volume * 0.32f * 512.0f).
    return ScalarFloat::integer(volume).mul({tables_.scalar[scale]}).mul({tables_.scalar[unit]}).truncate();
}
int32_t ConsoleOption::unpackedMixerVolume(const ConsoleOptionTables& tables,uint8_t volume) {
    // 1b8bc0 uses 0.25f where the SOUND SETTING page uses 0.32f.
    return ScalarFloat::integer(volume).mul({tables.scalar[T::LoadScale]}).mul({tables.scalar[T::LoadUnit]}).truncate();
}
int ConsoleOption::cursor() const {
    switch(scene_) {
    case OptionScene::Top:return topCursor_;
    case OptionScene::GameOption:return gameCursor_;
    case OptionScene::Sound:return soundCursor_;
    case OptionScene::SaveLoad:return saveCursor_;
    default:return 0;
    }
}
int ConsoleOption::state() const {
    switch(scene_) {
    case OptionScene::Top:return topState_;
    case OptionScene::GameOption:return gameState_;
    case OptionScene::Sound:return soundState_;
    case OptionScene::SaveLoad:return saveState_;
    default:return 0;
    }
}

void ConsoleOption::setHelp(T::Group group,unsigned scrollTable,int index) {
    help_=&tables_.text[group].at(index);
    helpScroll_=tables_.helpScroll[scrollTable].at(index)==1;
    chrome.setHelp(int(help_->size()));
}
void ConsoleOption::enter(OptionScene scene,int libraryRandom) {
    scene_=scene;
    chrome.enter(libraryRandom);
    switch(scene) {
    case OptionScene::Top:                         // 1cfa88; the cursor survives sub-scenes
        topState_=0;
        setHelp(T::TopHelp,0,topCursor_);
        break;
    case OptionScene::GameOption: {                // 1d0130
        gameCursor_=gameState_=0;
        const auto live=data_.image().subspan(SystemData::gameOption,0x98);
        std::copy(live.begin(),live.end(),gameWork_.begin());
        page_=0;slideState_=2;slideCounter_=0;frame_=0;
        setHelp(T::GameHelp,1,0);
        break;
    }
    case OptionScene::Sound: {                     // 1dbaa8
        soundCursor_=0;
        for(unsigned i=0;i<7;++i)soundWork_[i]=data_.setting(i);
        soundState_=0;frame_=0;
        setHelp(T::SoundHelp,2,0);
        break;
    }
    case OptionScene::SaveLoad:                    // 1d3110
        autoSaveWork_=data_.autoSave();
        saveCursor_=saveState_=0;frame_=0;
        setHelp(T::SaveHelp,3,0);
        break;
    default:
        throw std::invalid_argument("Scene is not owned by ConsoleOption");
    }
    draw=OptionDraw{};
    draw.scene=scene;
}

ConsoleOption::Tick ConsoleOption::tick(const std::array<MenuPad,2>& pads) {
    Tick result;
    draw.texts.clear();
    draw.scene=scene_;
    draw.frameDrawn=draw.showPage=draw.sliding=false;
    switch(scene_) {
    case OptionScene::Top:tickTop(pads,result);break;
    case OptionScene::GameOption:tickGame(pads,result);break;
    case OptionScene::Sound:tickSound(pads,result);break;
    case OptionScene::SaveLoad:tickSave(pads,result);break;
    default:throw std::logic_error("ConsoleOption::tick without a scene");
    }
    return result;
}
void ConsoleOption::drawFrame(bool showPage,int page,int total) {
    draw.frameDrawn=true;draw.showPage=showPage;draw.page=page;draw.pageTotal=total;
    draw.band=chrome.band;draw.legend=chrome.legend;
    chrome.advance();
}
void ConsoleOption::drawHelp() {
    // 1ceb10 is called once per submitted copy, so a scrolling string
    // decrements the shared delay twice per visit.
    const int length=int(help_->size());
    draw.help=help_;
    draw.helpCopies=helpScroll_?2:1;
    draw.helpX[0]=chrome.helpPosition(helpScroll_,length,0);
    draw.helpVisible[0]=draw.helpX[0]<0x280;
    draw.helpX[1]=0;draw.helpVisible[1]=false;
    if(helpScroll_) {
        draw.helpX[1]=chrome.helpPosition(true,length,1);
        draw.helpVisible[1]=draw.helpX[1]<0x280;
    }
}
void ConsoleOption::leave(Tick& r,int& state) {   // 1d0800 / 1dbea8 / 1d3458
    r.request=OptionScene::Top;
    state=4;
}
void ConsoleOption::exitToTitle(Tick& r) {
    // 1cfc88: 124d50 clears g_GameData (the caller owns it), the title
    // scene is requested, and the auto-save check is deferred one visit.
    r.request=OptionScene::Title;
    topState_=2;
    draw.whiteScreen=true;
}

// ---- OPTION top page, 1cfa98 ------------------------------------------
void ConsoleOption::tickTop(const std::array<MenuPad,2>& pads,Tick& r) {
    if(topState_==2) {
        // 10f158: the flag is tested here, not when EXIT was chosen.
        if(data_.autoSave()!=0){r.autoSave=true;if(save)save();}
        topState_=3;
    }
    draw.whiteScreen=topState_==3;
    for(unsigned seat=0;seat<2;++seat) {
        unsigned in=0;
        if(chrome.inputReady()&&topState_==0)in=topInput(pads[seat]);
        if(in&3) {
            topCursor_=(topCursor_+(in&1?4:1))%5;
            setHelp(T::TopHelp,0,topCursor_);
            r.sounds.push_back(0x20);
        } else if(in&0x18) {
            exitToTitle(r);
            r.sounds.push_back(0x25);
        } else if(in&4) {
            // 1cfcf0, jump table 656c58.
            static constexpr std::array<OptionScene,4> next{OptionScene::GameOption,OptionScene::KeyConfig,
                                                            OptionScene::Sound,OptionScene::SaveLoad};
            if(topCursor_<4){r.request=next[topCursor_];topState_=1;}
            else exitToTitle(r);
            r.sounds.push_back(0);
        }
    }
    drawFrame(false,0,0);
    const int a=chrome.contentAlpha();
    draw.cursor=topCursor_;draw.state=topState_;draw.frame=0;draw.alpha=a;draw.banner=0;
    for(int i=0;i<5;++i)
        draw.texts.push_back({tables_.text[T::TopLabel][i],rowX,rowY+rowStep*i,argb(a,i==topCursor_?red:white),false});
    drawHelp();
}

// ---- GAME OPTION, 1d01b8 ----------------------------------------------
void ConsoleOption::gameIncrement() {             // 1d0920, jump table 656de4
    auto& w=gameWork_;
    switch(gameCursor_) {
    case 0:w[4]=uint8_t((w[4]&7)+1);break;
    case 1:w[5]=uint8_t((w[5]+1)%3);break;
    case 2:w[6]^=1;break;
    case 3:w[7]=uint8_t((w[7]+1)%15);break;
    case 4:w[8]=uint8_t(w[8]%5+1);break;
    case 5:w[9]=uint8_t((w[9]+10)%210);break;
    case 6: {
        // BRIGHT is edited in the live word so the screen previews it.
        int32_t v=int32_t(uint32_t(brightness())*100u+200u)/100;
        if(v>0x100)v=0x38;
        setBrightness(v);
        break;
    }
    case 7:w[0x10]=uint8_t((w[0x10]+1)%3);break;
    case 10:w[0x13]=uint8_t((w[0x13]+1)%3);break;
    }
}
void ConsoleOption::gameDecrement() {             // 1d0ad8, jump table 656e10
    auto& w=gameWork_;
    switch(gameCursor_) {
    case 0:w[4]=uint8_t(((w[4]+6)&7)+1);break;
    case 1:w[5]=uint8_t((w[5]+2)%3);break;
    case 2:w[6]^=1;break;
    case 3:w[7]=uint8_t((w[7]+14)%15);break;
    case 4:w[8]=uint8_t((w[8]+3)%5+1);break;
    case 5:w[9]=uint8_t((w[9]+200)%210);break;
    case 6: {
        int32_t v=int32_t(uint32_t(brightness())*100u-200u)/100;
        if(v<0x38)v=0x100;
        setBrightness(v);
        break;
    }
    case 7:w[0x10]=uint8_t((w[0x10]+2)%3);break;
    case 10:w[0x13]=uint8_t((w[0x13]+2)%3);break;
    }
}
void ConsoleOption::gameDefaults() {              // 1d0840
    auto& w=gameWork_;
    const auto live=data_.image().subspan(SystemData::gameOption,0x98);
    std::fill_n(live.begin(),4,uint8_t(0));
    if(page_==0) {
        w[0xc]=0;w[0xd]=1;w[0xe]=w[0xf]=0;        // BRIGHT 100
        w[4]=4;w[5]=0;w[8]=2;w[9]=100;w[6]=0;w[7]=0;
    } else {
        w[0x15]=tables_.kyouchiDefault;w[0x14]=tables_.mikiriDefault;w[0x10]=0;
        w[0x11]=tables_.mikiriDefault;w[0x12]=tables_.kyouchiDefault;w[0x13]=0;
    }
    // Only the visible page is reset, but the whole work copy (including
    // its BRIGHT word and bytes 0..3) replaces the live block.
    std::copy(w.begin(),w.end(),live.begin());
    gameState_=0;
}
void ConsoleOption::gameDiscard() {
    // Cancel in edit: restore the previewed BRIGHT, then reload the work copy.
    const auto live=data_.image().subspan(SystemData::gameOption,0x98);
    std::copy_n(gameWork_.begin()+0xc,4,live.begin()+0xc);
    std::copy(live.begin(),live.end(),gameWork_.begin());
    gameState_=0;
}
OptionText ConsoleOption::gameValue(int item,int cursor,int state,int x,int y,int alpha) const {
    const auto& w=gameWork_;
    const auto& fmt=tables_.text[T::GameFormat];
    std::string s;
    switch(item) {
    case 0:s=formatValue(fmt[0],w[4],{});break;
    case 1:s=pick(tables_.text[T::GameTime],w[5]);break;
    case 2:s=pick(tables_.text[T::GameMode],w[6]);break;
    case 3:s=pick(tables_.text[T::CpuMatchPoint],w[7]);break;
    case 4:s=formatValue(fmt[0],w[8],{});break;
    case 5:s=formatValue(fmt[0],w[9],{});break;
    case 6:s=formatValue(fmt[0],int32_t(uint32_t(brightness())*100u-5600u)/200,{});break;  // live word
    case 7:s=pick(tables_.text[T::Spirits1P],w[0x10]);break;
    case 8:s=formatValue(fmt[1],w[0x11]>>1,fmt[2]);break;
    case 9:s=formatValue(fmt[1],w[0x12]>>1,fmt[2]);break;
    case 10:s=pick(tables_.text[T::Spirits2P],w[0x13]);break;
    case 11:s=formatValue(fmt[1],w[0x14]>>1,fmt[2]);break;
    case 12:s=formatValue(fmt[1],w[0x15]>>1,fmt[2]);break;
    }
    const bool editing=cursor==item&&state==1;
    return {std::move(s),x+valueX,y,argb(alpha,editing?red:white),editing};
}
void ConsoleOption::gameRows(int first,int last,int x,uint32_t labelAlpha,int valueAlpha,int cursor,int state,bool plain) {
    // 1d0f18 (page) and 1d1e20 (slide): rows, then DEFAULT SETTING and EXIT.
    auto colour=tables_.gameColour;
    if(!plain&&state!=1)colour.at(cursor)=red;
    const auto& label=tables_.text[T::GameLabel];
    int y=rowY;
    auto tint=[&](int i){return plain?0xffffffffu:labelAlpha+colour[i];};
    for(int i=first;i<last;++i,y+=rowStep) {
        draw.texts.push_back({label[i],x,y,tint(i),false});
        draw.texts.push_back(gameValue(i,cursor,state,x,y,valueAlpha));
    }
    draw.texts.push_back({label[13],x,y,tint(13),false});
    draw.texts.push_back({label[14],x,y+rowStep,tint(14),false});
}
void ConsoleOption::tickGame(const std::array<MenuPad,2>& pads,Tick& r) {
    const auto live=data_.image().subspan(SystemData::gameOption,0x98);
    auto moved=[&]{setHelp(T::GameHelp,1,gameCursor_);r.sounds.push_back(0x20);frame_=0;};
    for(unsigned seat=0;seat<2;++seat) {
        unsigned in=0;
        if(chrome.inputReady()&&gameState_!=4&&slideState_==2)in=gameInput(pads[seat]);
        if(in&0x100) {
            if(gameState_==0){gameState_=1;frame_=0;}
            else if(gameState_==1)gameState_=2;
            r.sounds.push_back(0);
        }
        if(gameState_!=1) {
            // Also reached in state 2, before the commit below.
            if(in&0x400){leave(r,gameState_);r.sounds.push_back(0x25);frame_=0;}
            else if(in&0x2000) {
                gameCursor_=(gameCursor_+14)%15;
                if(page_==0){if(gameCursor_==12)gameCursor_=6;}
                else if(gameCursor_==6)gameCursor_=14;
                moved();
            } else if(in&0x4000) {
                gameCursor_=(gameCursor_+1)%15;
                if(page_==0){if(gameCursor_==7)gameCursor_=13;}
                else if(gameCursor_==0)gameCursor_=7;
                moved();
            } else if(in&0x1800) {
                // Page previous (800) and next (1000) both toggle the page;
                // they differ only in the slide direction.
                page_=(page_+1)%2;
                slideState_=in&0x800?0:1;
                gameCursor_=page_==0?0:7;
                setHelp(T::GameHelp,1,gameCursor_);
                chrome.restartLegend();
                slideCounter_=0;
                r.sounds.push_back(0x20);frame_=0;
            }
        }
        if(gameState_==1) {
            const int c=gameCursor_;
            if(c<13) {
                const bool gauge=c==8||c==9||c==11||c==12;   // jump table 656db0
                if(in&0x400){gameDiscard();r.sounds.push_back(0x25);frame_=0;}
                else if(gauge) {
                    // 1d0c98 / 1d0d80: gauges move in steps of two over 0..200.
                    static constexpr std::array<int,13> offset{0,0,0,0,0,0,0,0,0x11,0x12,0,0x14,0x15};
                    auto& v=gameWork_[offset[c]];
                    if(in&0x50){v=uint8_t((v+2)%202);r.sounds.push_back(0x20);}
                    else if(in&0xa0){v=uint8_t((v+200)%202);r.sounds.push_back(0x20);}
                } else if(in&6){gameDecrement();r.sounds.push_back(0x20);}
                else if(in&9){gameIncrement();r.sounds.push_back(0x20);}
            }
            // Confirm on these rows enters state 1 and acts in the same visit.
            if(gameCursor_==13){gameDefaults();r.sounds.push_back(0);}
            if(gameCursor_==14){leave(r,gameState_);r.sounds.push_back(0);}
        }
        if(gameState_==2) {
            // Commit: keep the previewed BRIGHT, then publish the work copy.
            std::copy_n(live.begin()+0xc,4,gameWork_.begin()+0xc);
            std::copy(gameWork_.begin(),gameWork_.end(),live.begin());
            gameState_=0;
            r.sounds.push_back(0);frame_=0;
        }
    }
    // 1cf738 is sampled before 1ce660 here, unlike the other three pages.
    const int a=chrome.contentAlpha();
    draw.cursor=gameCursor_;draw.state=gameState_;draw.frame=frame_;draw.alpha=a;draw.banner=1;
    draw.whiteScreen=false;
    if(slideState_==2) {
        drawFrame(true,page_,2);
        gameRows(page_==1?7:0,page_==1?13:7,rowX,argb(a&0xff,0),a,gameCursor_,gameState_,false);
    } else {
        // 1d1e20 with the cubic Bezier 1d21a0(counter/15): the outgoing page
        // runs 0 -> x0 with control points x0,x0; the incoming one x1 -> 0
        // with control points 0,0. 1ce660 is not called, so the frame
        // counters hold and the legend restarts when the slide ends.
        const int x0=slideState_==1?-0x280:0x280;
        auto ease=[&](int p0,int p1,int p2,int p3) {
            const ScalarFloat one{tables_.scalar[T::EaseOne]},three{tables_.scalar[T::EaseThree]};
            const ScalarFloat t=ScalarFloat::integer(slideCounter_).div(ScalarFloat::integer(15));
            const ScalarFloat u=one.sub(t);
            const ScalarFloat t3=t.mul(t).mul(t);
            ScalarFloat f1=u.mul(three);
            const ScalarFloat u3=u.mul(u).mul(u);
            const ScalarFloat f3=f1.mul(u).mul(t);
            f1=f1.mul(t).mul(t);
            // mula.s, madda.s, madda.s, madd.s: each product and sum rounds separately.
            ScalarFloat acc=u3.mul(ScalarFloat::integer(p0));
            acc=acc.add(f3.mul(ScalarFloat::integer(p1)));
            acc=acc.add(f1.mul(ScalarFloat::integer(p2)));
            return acc.add(t3.mul(ScalarFloat::integer(p3))).truncate();
        };
        draw.sliding=true;
        draw.slideCounter=slideCounter_;
        draw.slideOutX=ease(0,x0,x0,x0);
        draw.slideInX=ease(-x0,0,0,0);
        gameRows(page_==0?7:0,page_==0?13:7,draw.slideOutX+rowX,0,0xff,-1,0,true);
        gameRows(page_==0?0:7,page_==0?7:13,draw.slideInX+rowX,0,0xff,-1,0,true);
        if(slideCounter_>=15)slideState_=2;
        ++slideCounter_;
    }
    ++frame_;
    drawHelp();
}

// ---- SOUND SETTING, 1dbb00 --------------------------------------------
void ConsoleOption::soundCommit(Tick& r) {        // 1dc0e0: the selected item only
    auto& w=soundWork_;
    switch(soundCursor_) {
    case 0:data_.setting(3)=w[3];r.soundOutputs.push_back(w[3]);break;
    case 1:
        data_.setting(4)=w[4];
        mixerVolume=volumeWord(w[4],T::CommitScale,T::CommitUnit);
        break;
    case 2:data_.setting(6)=w[6];break;
    case 3:data_.setting(5)=w[5];break;
    }
}
void ConsoleOption::soundRevert(Tick& r) {        // 1dc2b0
    auto& w=soundWork_;
    switch(soundCursor_) {
    case 0:w[3]=data_.setting(3);r.soundOutputs.push_back(w[3]);break;
    case 1:
        w[4]=data_.setting(4);
        mixerVolume=volumeWord(w[4],T::RevertScale,T::RevertUnit);
        break;
    case 2:w[6]=data_.setting(6);break;
    case 3:w[5]=data_.setting(5);break;
    }
}
void ConsoleOption::tickSound(const std::array<MenuPad,2>& pads,Tick& r) {
    auto& w=soundWork_;
    for(unsigned seat=0;seat<2;++seat) {
        unsigned in=0;
        if(chrome.inputReady()&&soundState_!=4)in=soundInput(pads[seat]);
        if(in&0x100) {
            if(soundState_==0){soundState_=1;frame_=0;}
            else if(soundState_==1)soundState_=2;
            r.sounds.push_back(0);
        }
        if(soundState_!=1) {
            if(in&0x200){leave(r,soundState_);r.sounds.push_back(0x25);}
            else if(in&0xc00) {
                soundCursor_=(soundCursor_+(in&0x400?5:1))%6;
                setHelp(T::SoundHelp,2,soundCursor_);
                frame_=0;
                r.sounds.push_back(0x20);
            }
        }
        if(soundState_==1) {
            const int c=soundCursor_;
            if(c<4) {
                if(in&0x200){soundRevert(r);soundState_=0;frame_=0;r.sounds.push_back(0x25);}
                else if(c==1) {
                    // Repeating up/right and down/left step the volume over 0..100.
                    if(in&0x50){w[4]=uint8_t((w[4]+1)%101);r.sounds.push_back(0x20);}
                    else if(in&0xa0){w[4]=uint8_t((w[4]+100)%101);r.sounds.push_back(0x20);}
                } else if(in&0xf) {
                    // 1dbf60 / 1dbfe0: every pressed direction toggles the byte.
                    w[c==0?3:c==2?6:5]^=1;
                    r.sounds.push_back(0x20);
                }
            }
            if(soundCursor_==4) {
                // 1dbee8 also clears the three unedited leading bytes.
                w={0,0,0,0,100,0,0};
                mixerVolume=tables_.mixerDefault;
                for(unsigned i=0;i<7;++i)data_.setting(i)=w[i];
                soundState_=0;
                r.sounds.push_back(0);
            } else if(soundCursor_==5){leave(r,soundState_);r.sounds.push_back(0);}
        }
        if(soundState_==2) {
            soundCommit(r);
            soundState_=0;frame_=0;
            r.sounds.push_back(0);
        }
    }
    drawFrame(false,0,0);
    const int a=chrome.contentAlpha();
    draw.cursor=soundCursor_;draw.state=soundState_;draw.frame=frame_;draw.alpha=a;draw.banner=3;
    draw.whiteScreen=false;
    auto colour=tables_.soundColour;
    if(soundState_!=1)colour.at(soundCursor_)=red;
    const auto& label=tables_.text[T::SoundLabel];
    const auto& fmt=tables_.text[T::SoundFormat];
    int y=rowY;
    for(int i=0;i<4;++i,y+=rowStep) {
        draw.texts.push_back({label[i],rowX,y,argb(a&0xff,colour[i]),false});
        std::string s=i==0?pick(tables_.text[T::SoundOutput],w[3]):i==1?formatValue(fmt[0],w[4],fmt[1]):
                      i==2?pick(tables_.text[T::SoundBgm],w[6]):pick(tables_.text[T::SoundVoice],w[5]);
        const bool editing=soundCursor_==i&&soundState_==1;
        draw.texts.push_back({std::move(s),rowX+valueX,y,argb(a,editing?red:white),editing});
    }
    draw.texts.push_back({label[4],rowX,y,argb(a&0xff,colour[4]),false});
    draw.texts.push_back({label[5],rowX,y+rowStep,argb(a&0xff,colour[5]),false});
    ++frame_;
    drawHelp();
}

// ---- SAVE/LOAD, 1d3140 --------------------------------------------------
void ConsoleOption::tickSave(const std::array<MenuPad,2>& pads,Tick& r) {
    for(unsigned seat=0;seat<2;++seat) {
        unsigned in=0;
        if(chrome.inputReady()&&saveState_!=4) {  // 1d38f8
            const auto& p=pads[seat];
            if(p.pressed&0x404)in=0x20;
            if(p.pressed&0x20a)in|=0x10;
            if(p.repeat&0x10)in|=0x40;
            if(p.repeat&0x20)in|=0x80;
            if(p.pressed&0x10)in|=1;
            if(p.pressed&0x20)in|=2;
            if(p.pressed&0x80)in|=4;
            if(p.pressed&0x40)in|=8;
        }
        if(in&0x10) {
            r.sounds.push_back(0);
            if(saveCursor_==2) {
                if(saveState_==0)saveState_=1;
                else if(saveState_==1)saveState_=2;
            } else if(saveCursor_==0) {           // 1d3498: 1b8cf0, 10f958
                ++r.saveRequests;
                if(save)save();
            } else if(saveCursor_==1) {           // 1b8cf0, 10f088, 1b8b88
                ++r.loadRequests;
                if(load)load();
                // The unpack runs whether or not the card read succeeded.
                mixerVolume=unpackedMixerVolume(tables_,data_.setting(4));
                autoSaveWork_=data_.autoSave();
            } else if(saveCursor_==3)leave(r,saveState_);
        }
        if(saveState_==0) {
            // Not exclusive with the confirm above: SAVE and LOAD stay in
            // state 0, so a direction or cancel in the same word still acts.
            if(in&0xc0) {
                saveCursor_=(saveCursor_+(in&0x40?3:1))%4;
                setHelp(T::SaveHelp,3,saveCursor_);
                r.sounds.push_back(0x20);
            } else if(in&0x20){leave(r,saveState_);r.sounds.push_back(0x25);}
        }
        if(saveState_==1) {
            if(in&0x20){saveState_=0;autoSaveWork_=data_.autoSave();r.sounds.push_back(0x25);}
            else if(in&0xf){autoSaveWork_^=1;r.sounds.push_back(0x20);}
        }
        if(saveState_==2) {
            saveState_=0;
            data_.setAutoSave(autoSaveWork_);
            r.sounds.push_back(0);
        }
    }
    drawFrame(false,0,0);
    const int a=chrome.contentAlpha();
    draw.cursor=saveCursor_;draw.state=saveState_;draw.frame=frame_;draw.alpha=a;draw.banner=4;
    draw.whiteScreen=false;
    for(int i=0;i<4;++i)
        draw.texts.push_back({tables_.text[T::SaveLabel][i],rowX,rowY+rowStep*i,
                              argb(a,i==saveCursor_&&saveState_!=1?red:white),false});
    const bool editing=saveCursor_==2&&saveState_==1;
    draw.texts.push_back({pick(tables_.text[T::AutoSave],unsigned(autoSaveWork_)),0x170,0x88,
                          argb(a,editing?red:white),editing});
    ++frame_;
    drawHelp();
}
}
