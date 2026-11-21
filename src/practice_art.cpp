#include "practice_art.hpp"
#include "scalar_float.hpp"
#include <algorithm>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <stdexcept>

namespace ss6 {
namespace {
using Context=EditArt::Context;
// 17c228(base - layer) for a layer constant of this module. EditArt::layer is
// the same routine keyed by the constants of edit_art.bin.
float layer(const EditArt& art,Context& c,float constant) {
    const float z=eeSub(c.list.cursorBase,constant);
    const float out=eeSub(z,c.list.cursor);
    c.list.cursor=eeAdd(c.list.cursor,art.assets().f(0x5f1f08));
    return out;
}
// 318358 on the stored bytes: the menu strings are plain ASCII.
int length(const std::string& s) {return int(std::strlen(s.c_str()));}
template<class... Args> std::string format(const std::string& pattern,Args... args) {
    // 317a10 with the format strings of the executable (practice_mode.bin).
    char buffer[64];
    std::snprintf(buffer,sizeof buffer,pattern.c_str(),args...);
    return buffer;
}
// 2109b0 / 2118a0: the pair of blinking edit arrows around a value. The right
// arrow sits 14 pixels per character plus 27 behind the left one.
void arrows(const EditArt& art,Context& c,int x,int y,float w,float h,const std::string& value) {
    EditBox box;
    box.x=float(x);box.y=float(y);box.w=w;box.h=h;
    box.outer=box.inner=box.fill=0xffffffff;
    art.arrow(c,box,true);
    box.x=box.x+float(length(value)*14+27);
    art.arrow(c,box,false);
}
// 2118a0: gauge sub-window, lifted 200 depth units above the menu (17c250).
void gaugeWindow(const EditArt& art,const PracticeArtTables& t,Context& c,const PracticeMenu& m,const PracticeSettings& s,
                 const PracticeTables& text) {
    if(!m.active)return;
    const int x=m.slide.x+0xae,y=m.slide.y+0x76,labelX=m.slide.x+0xba;
    c.list.cursorBase=t.f(0x664ef0);
    EditBox box;
    art.focus(c,box,m.focused!=0);
    box.x=float(x);box.y=float(y);box.w=t.f(0x664ef4);box.h=t.f(0x664ef8);box.style=1;
    art.window(c,box,0);
    const int cursor=s.a[4];
    const bool blink=(m.counter&0x3f)>=0x19;
    for(int row=0;row<6;++row) {
        const int rowY=y+row*0x11+0xe;
        c.pen.colour=m.level==1&&cursor==row?EditArt::rowColour(true,true):0xffffffff;
        art.text(c,text.text(PracticeTables::GaugeRows,row),labelX,rowY,0);
        const auto& percent=text.text(PracticeTables::Misc,PracticeTables::PercentFormat);
        const std::string value=row<2?text.text(PracticeTables::GaugeLong,s.b[size_t(6+row)])
                               :format(percent,int(s.b[size_t(6+row)])+(row>=4));
        if(cursor==row&&m.level==2&&blink)arrows(art,c,x+0xf0,rowY-1,t.f(0x664efc),t.f(0x664f00),value);
        c.pen.colour=cursor==row&&m.level==2?EditArt::rowColour(true,true):0xffffffff;
        art.text(c,value,x+0x104,rowY,0);
    }
    c.list.cursorBase=0;
}
}

PracticeArtTables::PracticeArtTables(const std::filesystem::path& assets) {
    std::ifstream in(assets/"practice_art.bin",std::ios::binary);
    std::vector<uint8_t> raw((std::istreambuf_iterator<char>(in)),std::istreambuf_iterator<char>());
    if(raw.size()<8||std::memcmp(raw.data(),"PAR1",4))throw std::runtime_error("practice_art.bin is missing or foreign");
    uint32_t count;std::memcpy(&count,raw.data()+4,4);
    if(raw.size()!=8+size_t(count)*8+16)throw std::runtime_error("practice_art.bin has an unexpected layout");
    for(uint32_t i=0;i<count;++i) {
        uint32_t at;float value;
        std::memcpy(&at,raw.data()+8+8*i,4);std::memcpy(&value,raw.data()+12+8*i,4);
        floats_.emplace_back(at,value);
    }
    std::sort(floats_.begin(),floats_.end());
    std::copy_n(raw.data()+8+size_t(count)*8,keyIcons.size(),keyIcons.begin());
}
float PracticeArtTables::f(uint32_t address) const {
    const auto it=std::lower_bound(floats_.begin(),floats_.end(),std::pair<uint32_t,float>(address,-1e30f));
    if(it==floats_.end()||it->first!=address)throw std::logic_error("Practice art constant is not extracted");
    return it->second;
}

void applyPracticeHelp(EditFrame& frame,const std::vector<PracticeHelp>& requests,const PracticeTables& tables) {
    for(const auto& r:requests) {
        switch(r.kind) {
        case PracticeHelp::Text:case PracticeHelp::List:frame.setMessage(r.id,r.arg);break;   // 182268 / 1827c0
        case PracticeHelp::Skill: {
            // 1820f8 with the name pointer of the record: a NULL name clears the text.
            if(r.id<0) {frame.messageText=tables.text(PracticeTables::Misc,PracticeTables::ActionFallback);frame.hasMessage=true;}
            else {
                const uint32_t name=tables.skill(r.id).name;
                frame.hasMessage=name!=0xffffffffu;
                frame.messageText=frame.hasMessage?tables.string(name):std::string();
            }
            break;
        }
        case PracticeHelp::Page:frame.setLayout(r.id);break;
        case PracticeHelp::Open:frame.open();break;
        case PracticeHelp::Close:frame.close();break;
        case PracticeHelp::Snap:
            // 182700: every bar jumps to its retracted position.
            for(EditFrame::Bar* bar:{&frame.title,&frame.message,static_cast<EditFrame::Bar*>(&frame.keys),
                                     static_cast<EditFrame::Bar*>(&frame.extra)}) {
                bar->slide.snap(bar->slide.outX,bar->slide.outY);bar->open=0;
            }
            break;
        default:throw std::invalid_argument("Unknown practice help request");
        }
    }
}

void drawPracticeClock(const EditArt& art,Context& c,const PracticeClock& clock,const PracticeTables& tables) {
    c.pen.middle=true;                                   // 17e200
    if(clock.shown) {
        c.pen.colour=0xffff8080;
        const auto& pattern=tables.text(PracticeTables::Misc,clock.play?PracticeTables::PlayClock:PracticeTables::RecClock);
        art.text(c,format(pattern,clock.seconds,clock.thousandths),0x70,0x78,0);
    }
    c.pen.front=c.pen.middle=false;                      // 17e210
}

void drawPracticeData(const EditArt& art,const PracticeArtTables& t,Context& c,bool practice,const PracticeDamage& damage,
                      const PracticeKeyHistory& keys,const PracticeTables& text) {
    const MenuCanvas& canvas=art.canvas();
    c.list.colour=0xffffffff;                            // 13a2c8: 3db900
    c.pen.middle=true;                                   // 17e200
    c.pen.colour=0xffffffff;
    c.list.cursorBase=t.f(0x5e1aac);                     // 17c250(200): the history lies behind the damage box
    const uint32_t plate=c.seat?0xc0400000:0xc0000040;
    const float iconLayer=t.f(0x5e1ab0),plateLayer=t.f(0x5e1ab8);
    int index=keys.index,x=600;
    for(int n=0;n<24;++n) {
        const unsigned entry=keys.shown.at(size_t(index));
        // A word with bit 0x4000 (icon 0x1e) has a second icon column.
        const int width=entry&0x4000?0x2c:0x18,inset=entry&0x4000?10:0;
        x-=width;
        int rows=0;
        if(entry==0)rows=1;                              // an empty column still gets its plate
        else if(entry==0x10) {                           // neutral alone
            rows=1;
            const float z=layer(art,c,iconLayer);
            art.icon(c,t.keyIcons[4],float(x),t.f(0x5e1ab4),z);
        } else {
            // Icons of the set bits stack downwards, 24 pixels each; the
            // neutral bit is skipped and bit 14 uses its own column and row offset.
            int drop=0;
            for(int bit=0;bit<15;++bit) {
                if(!(entry>>bit&1)||bit==4)continue;
                const float y=float(bit==14?drop+0x5b:drop+0x57);
                const float z=layer(art,c,iconLayer);
                drop+=0x18;++rows;
                art.icon(c,t.keyIcons[size_t(bit)],float(bit==14?x+2:x+inset),y,z);
            }
        }
        const float z=layer(art,c,plateLayer);
        canvas.rectangle(c.list,x,0x55,width,rows*0x18+4,plate,z);
        index=index>0?index-1:23;
    }
    c.list.cursorBase=0;                                 // 17c250(0)
    if(practice) {                                       // 13a3c4: battle type 123a0c0 == 1
        const float z=layer(art,c,plateLayer);
        canvas.rectangle(c.list,0x138,0x74,0xf0,0x42,plate,z);
        c.pen.colour=damage.newCombo?0xff808080:0xffffffff;
        art.text(c,format(text.text(PracticeTables::Misc,PracticeTables::Damage),int(damage.last)),0x140,0x78,0);
        art.text(c,format(text.text(PracticeTables::Misc,PracticeTables::TotalDamage),int(damage.total)),0x140,0x8c,0);
        c.pen.colour=damage.total==damage.maxDamage&&damage.total!=0?0xffff8080:0xffffffff;
        art.text(c,format(text.text(PracticeTables::Misc,PracticeTables::MaxDamage),int(damage.maxDamage)),0x140,0xa4,0);
    }
    c.pen.front=c.pen.middle=false;                      // 17e210
}

void drawPracticeDisplays(const EditArt& art,const PracticeArtTables& tables,Context& c,const PracticeState& practice,
                          const PracticeDamage& damage,const PracticeKeyHistory& keys,const std::array<int,2>& recordIndex,
                          const PracticeTables& text) {
    c.seat=unsigned(practice.localSeat());
    drawPracticeClock(art,c,practiceClock(practice,recordIndex),text);
    if(practice.settings.dataDisplay())drawPracticeData(art,tables,c,practice.practice(),damage,keys,text);
}

void drawPracticeMenu(const EditArt& art,const PracticeArtTables& t,Context& c,const PracticeMenu& m,const PracticeSettings& s,
                      const PracticeTables& text) {
    if(!m.active)return;
    const int X=m.slide.x,Y=m.slide.y,cursor=m.rows.value;
    const bool gauge=m.gaugeWindow();
    // While the gauge sub-window is open the menu is drawn unfocused.
    const bool lit=m.focused&&!gauge;
    EditBox box;
    art.focus(c,box,lit);
    box.x=float(X);box.y=float(Y);box.w=t.f(0x664dac);box.h=t.f(0x664db0);box.style=1;
    art.window(c,box,0);
    c.pen.colour=0xffffffff;
    art.markup(c,text.text(PracticeTables::Misc,PracticeTables::Legend),1,false,float(X+0x1e4),float(Y+0xe4));
    const bool blink=(m.counter&0x3f)>=0x19;
    const float arrowW=t.f(0x664db4),arrowH=t.f(0x664db8);
    for(int row=0;row<12;++row) {
        // Three blocks: rows 0-1, 2-8 and 9-11.
        const int y=Y+row*0x11+(row<2?0xe:row<9?0x1f:0x30);
        if(!lit)c.pen.colour=EditArt::rowColour(false,row==cursor);
        else c.pen.colour=m.level==0&&row==cursor?EditArt::rowColour(true,true):0xffffffff;
        art.text(c,text.text(PracticeTables::Rows,row),X+0x1c,y,0);
        const auto colour=[&](int level) {
            c.pen.colour=!lit?0xffb0b0b0:row==cursor&&m.level==level?EditArt::rowColour(true,true):0xffffffff;
        };
        std::string value;bool has=true;
        switch(row) {
        case 2:value=text.text(PracticeTables::CpuType,s.a[2]);break;
        case 3:value=text.text(PracticeTables::Ukemi,s.a[3]);break;
        case 4:
            value=format(text.text(PracticeTables::Misc,PracticeTables::GaugeFormat),
                         text.text(PracticeTables::GaugeShort,s.b[6]).c_str(),int(s.b[8]),int(s.b[10])+1,
                         text.text(PracticeTables::GaugeShort,s.b[7]).c_str(),int(s.b[9]),int(s.b[11])+1);
            break;
        case 5:value=text.text(PracticeTables::Items,s.a[5]);break;
        case 6:value=text.text(PracticeTables::OffOn,s.a[6]);break;
        default:has=false;break;
        }
        if(has) {
            if(row==cursor&&m.level==1&&!gauge&&blink)arrows(art,c,X+0xec,y-1,arrowW,arrowH,value);
            colour(1);
            art.text(c,value,X+0x100,y,0);
        }
        // Second level: the option of the selected CPU TYPE (slots 0..5).
        const int slot=PracticeSettings::optionSlot(row,s.a[size_t(row)]);
        if(slot<0||slot>=6)continue;
        const int option=s.b[size_t(slot)];
        std::string second;
        if(slot==0)second=option==9&&m.standNinth>=0?text.text(PracticeTables::Misc,m.standNinth):text.text(PracticeTables::Stand,option);
        else if(slot==1)second=text.text(PracticeTables::Crouch,option);
        else if(slot<=4)second=text.text(PracticeTables::Jump,option);
        else second=text.text(PracticeTables::Action,option);
        if(row==cursor&&m.level==2&&blink)arrows(art,c,X+0x160,y-1,arrowW,arrowH,second);
        colour(2);
        art.text(c,second,X+0x174,y,0);
    }
    if(gauge)gaugeWindow(art,t,c,m,s,text);
}

void drawPracticeConfirm(const EditArt& art,Context& c,const PracticeConfirm& d,const PracticeTables& text) {
    if(!d.active||!d.focused)return;
    const float z=art.layer(c,0x665268);
    art.canvas().rectangle(c.list,0,0xa0,0x280,0x6c,0xc0000000,z);
    c.pen.front=true;                                    // 17e1f0
    const auto& message=text.text(PracticeTables::Misc,d.prompt);
    const int span=length(message)*0x16;
    c.pen.colour=0xffffffff;
    art.text(c,message,0x140-((span<0?span+3:span)>>2),0xbc,2);
    c.pen.colour=EditArt::rowColour(true,d.choice.value==0);
    art.text(c,art.assets().text(EditArtAssets::Yes),0xf8,0xe4,2);
    c.pen.colour=EditArt::rowColour(true,d.choice.value!=0);
    art.text(c,art.assets().text(EditArtAssets::No),0x15e,0xe4,2);
    c.pen.front=c.pen.middle=false;                      // 17e210
}

PracticeWindowDraw drawPracticeWindow(const EditArt& art,const PracticeArtTables& tables,Context& c,const PracticeWindow& w,
                                      const PracticeState& practice,const EditFrame& help,const PracticeTables& text,
                                      const std::function<void()>& subWindows) {
    PracticeWindowDraw out;
    c.seat=unsigned(practice.localSeat());
    if(w.dim>0) {
        // 17f964: the plane darkens the battle and the menu layers behind the skill detail window.
        const float z=layer(art,c,tables.f(0x5f20b0));
        art.canvas().rectangle(c.list,0,0,0x280,0x1c0,uint32_t(w.dim)<<24,z);
    }
    if(w.menuDrawn()) {
        // 1817f0 inside 182600: with a battle behind the frame no backdrop is
        // submitted and no depth step is taken.
        if(help.backdrop!=-1) {
            out.battleDim=true;
            EditFrame bars=help;bars.backdrop=-1;
            art.frame(c,bars);
        } else art.frame(c,help);
        drawPracticeMenu(art,tables,c,w.menu,practice.settings,text);
    }
    if(subWindows)subWindows();
    drawPracticeConfirm(art,c,w.confirm,text);
    return out;
}
}
