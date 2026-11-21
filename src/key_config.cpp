#include "key_config.hpp"
#include <cstring>
#include <stdexcept>

namespace ss6 {
namespace {
constexpr size_t maskAt(unsigned player,unsigned slot) {return SystemData::keyMasks+0x20*player+4*slot;}
// 2122ec..212404: the first pressed bit in this order is the captured button.
constexpr std::array<uint32_t,10> captureOrder{4,2,1,0x400,0x200,0x100,0x100000,0x200000,0x400000,0x800000};
}

KeyConfigAssets::KeyConfigAssets(const std::filesystem::path& assets) {
    const AssetSections file(assets/"pause_menu.bin");
    const auto text=file.strings("KEYS");
    if(text.size()!=12)throw std::runtime_error("Unexpected key-configuration string table");
    for(size_t i=0;i<10;++i)rows[i]=text[i];
    legend=text[10];unset=text[11];
    const auto words=file.section("PRES");
    if(words.size()!=sizeof presets)throw std::runtime_error("Unexpected key preset table");
    std::memcpy(presets.data(),words.data(),sizeof presets);
}

uint32_t keyMask(const SystemData& system,unsigned player,unsigned slot) {
    return uint32_t(system.word(maskAt(player,slot)));
}
void assignKeyMask(SystemData& system,unsigned player,unsigned slot,uint32_t mask) {
    if(mask) {
        for(unsigned i=0;i<8;++i) {
            if(keyMask(system,player,i)!=mask)continue;
            system.setWord(maskAt(player,i),int32_t(keyMask(system,player,slot)));
            break;
        }
    }
    system.setWord(maskAt(player,slot),int32_t(mask));
}
void applyKeyPreset(SystemData& system,const KeyConfigAssets& assets,unsigned player,unsigned preset) {
    // 178e50 stores the preset byte first and writes nothing for ids above 2.
    if(preset>2)return;
    for(unsigned i=0;i<8;++i)system.setWord(maskAt(player,i),int32_t(assets.presets[preset][i]));
}
int keyGlyph(uint32_t mask) {
    switch(mask) {
    case 2:return 0x19;
    case 4:return 0x1a;
    case 0x400:return 0x1b;
    case 0x200:return 0x1c;
    case 0x100000:return 0x1f;
    case 0x200000:return 0x20;
    case 0x400000:return 0x21;
    case 0x800000:return 0x22;
    default:return -1;
    }
}
bool keyMasksFactory(const SystemData& system,const KeyConfigAssets& assets) {
    for(unsigned p=0;p<2;++p)
        for(unsigned i=0;i<5;++i)
            if(keyMask(system,p,i)!=assets.presets[0][i])return false;
    return true;
}

void KeyConfigWidget::init(GuideWindow* window) {
    for(auto& s:selector) {
        s.init();
        s.setRange(0,10,1,-1);
        // Bit 6 has no reader in 20e128. Confirm and cancel are refused
        // silently, so only cursor movement produces a tone.
        s.setFlag(6,true);
        s.setFlag(MenuSelector::RefuseConfirm,true);
        s.setFlag(MenuSelector::RefuseCancel,true);
        s.setFlag(MenuSelector::Silent,true);
    }
    guide=window;
}
int KeyConfigWidget::update(const std::array<WidgetPad,2>& pads,SystemData& system,const KeyConfigAssets& assets,
                            std::vector<int>& tones) {
    const int motion=panel.tick();
    if(motion!=1) {
        if(motion==0)shown=active=0;
        return 0;
    }
    // First pass: either seat leaves with 80000, or with a confirm button
    // on EXIT. Seat 0 is examined first and its exit hides seat 1's input.
    std::array<bool,2> confirm{};
    for(unsigned seat=0;seat<2;++seat) {
        const uint32_t pressed=pads[seat].pressed;
        bool leave=false;
        if(pressed&0x80000)leave=true;
        else confirm[seat]=(pressed&0x20a)!=0;
        if(confirm[seat]&&selector[seat].current==ExitRow)leave=true;
        if(leave){tones.push_back(0);return Leave;}
    }
    for(unsigned seat=0;seat<2;++seat) {
        auto& s=selector[seat];
        const int row=s.current;
        if(row<8) {
            const uint32_t pressed=pads[seat].pressed;
            // Left or right clears the slot; a captured button never moves the cursor.
            if(pressed&0xc0){assignKeyMask(system,seat,unsigned(row),0);continue;}
            bool captured=false;
            for(uint32_t mask:captureOrder)
                if(pressed&mask){assignKeyMask(system,seat,unsigned(row),mask);captured=true;break;}
            if(captured)continue;
        } else if(row==DefaultRow&&confirm[seat]) {
            tones.push_back(0);
            presetId[seat]=0;applyKeyPreset(system,assets,seat,0);   // 178d38
            continue;
        }
        if(s.update(pads[seat],tones)==MenuSelector::Moved&&guide)guide->setMessage(0x20,s.current);
    }
    return 0;
}
KeyConfigDraw KeyConfigWidget::draw(const SystemData& system) const {
    KeyConfigDraw d;
    d.visible=shown!=0;
    if(!d.visible)return d;
    const int x=panel.x,y=panel.y;
    d.boxX=x-0x18;d.boxY=y-8;
    d.legendX=x+0xe0;d.legendY=y+0xf2;
    const int left=x+0xc,top=y+0x10;
    d.labelX=left;
    for(int row=0;row<10;++row) {
        const bool a=selector[0].current==row,b=selector[1].current==row;
        d.labelColour[size_t(row)]=a?(b?0xffff00ffu:0xff0000ffu):(b?0xffff0000u:0xffffffffu);
        // EXIT is set six pixels below the grid.
        d.labelY[size_t(row)]=top+0x19*row+(row==ExitRow?6:0);
    }
    for(unsigned seat=0;seat<2;++seat) {
        for(unsigned slot=0;slot<8;++slot) {
            auto& c=d.cells[seat][slot];
            c.glyph=keyGlyph(keyMask(system,seat,slot));
            const int column=int(seat)*100;
            // Face-button icons are three pixels right of the shoulder icons.
            c.x=left+column+(c.glyph<0?0x10c:c.glyph>=0x19&&c.glyph<=0x1c?0x10b:0x108);
            c.y=top+0x19*int(slot);
            c.cursor=selector[seat].current==int(slot);
            c.cursorX=left+0xfc+column;c.cursorY=top+0x19*int(slot)-7;
            c.cursorColour=seat?0xffc04040u:0xff4040c0u;
        }
    }
    return d;
}

unsigned KeyConfigWindow::operatingSeat(unsigned gameMode,unsigned pauseOwner,unsigned editSeat) {
    if(gameMode==3)return pauseOwner==1;                 // 1da838
    if(gameMode==0xd||gameMode==0xe)return editSeat;     // word 12d35c4
    switch(gameMode) {
    case 2:case 5:case 8:case 0xa:case 0xc:case 0x10:case 0x12:return 1;
    default:return 0;
    }
}
void KeyConfigWindow::start(const MenuWidgetData& tables,unsigned seat) {
    closing=finished=false;
    guide.init(tables);
    guide.setLayout(0,seat);
    guide.open();
    widget=KeyConfigWidget{};
    widget.init(&guide);
    widget.panel.reset(seat?-0x230:0x2d0,0x58,0x50,0x58,0x10);
    widget.panel.open();
    widget.active=widget.shown=1;
}
KeyConfigWindow::Result KeyConfigWindow::tick(const std::array<WidgetPad,2>& pads,SystemData& system,
                                              const KeyConfigAssets& assets,bool optionScene,std::vector<int>& tones) {
    Result r;
    guide.tick();
    const int code=widget.update(pads,system,assets,tones);
    if(finished)return r;
    if(closing) {
        if(!widget.panel.idle())return r;
        closing=false;
        if(optionScene){r.optionScene=true;finished=true;return r;}
        // The pause path re-arms the window before the task is put to
        // sleep, so the next activation resumes with the slide-in.
        r.returnedToPause=true;
        widget.panel.open();widget.shown=1;
        guide.open();widget.active=1;
        return r;
    }
    if(code==4||code==5) {
        widget.panel.close();closing=true;
        widget.active=0;
        guide.close();
    }
    return r;
}
}
