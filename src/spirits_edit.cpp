#include "spirits_edit.hpp"
#include <algorithm>
#include <cstdio>
#include <fstream>
#include <iterator>
#include <stdexcept>

namespace ss6 {
SpiritsEditAssets::SpiritsEditAssets(const std::filesystem::path& assets) {
    const auto file=assets/"spirits_edit.bin";
    std::ifstream in(file,std::ios::binary);
    if(!in)throw std::runtime_error("Missing asset: "+file.string());
    const std::vector<uint8_t> data{std::istreambuf_iterator<char>(in),{}};
    if(data.size()<4+2*options.size()||!std::equal(data.begin(),data.begin()+4,"SPED"))
        throw std::runtime_error("Invalid spirits_edit.bin");
    size_t at=4;
    for(auto& o:options){o.category=data[at++];o.cost=int8_t(data[at++]);}
    auto text=[&] {
        if(at+2>data.size())throw std::runtime_error("Truncated spirits_edit.bin");
        const size_t n=data[at]|size_t(data[at+1])<<8;at+=2;
        if(at+n>data.size())throw std::runtime_error("Truncated spirits_edit.bin");
        std::string s(data.begin()+at,data.begin()+at+n);at+=n;return s;
    };
    for(auto& c:categories)c.romaji=text();
    for(auto& c:categories)c.japanese=text();
    for(auto& o:options)o.romaji=text();
    for(auto& o:options)o.japanese=text();
    for(auto& s:slotNames)s=text();
    panelTitle=text();emptyRow=text();optionTitle=text();pointFormat=text();
    if(at!=data.size())throw std::runtime_error("Trailing bytes in spirits_edit.bin");
}
int SpiritsEditAssets::first(unsigned category) const {
    for(size_t i=0;i<options.size();++i)if(options[i].category==category)return int(i);
    return 0;
}
int SpiritsEditAssets::count(unsigned category) const {
    return int(std::count_if(options.begin(),options.end(),[&](const Option& o){return o.category==category;}));
}

std::span<uint8_t,16> spiritSlot(SystemData& data,unsigned slot) {
    if(slot>=8)throw std::out_of_range("Custom spirit slot");
    return data.image().subspan(SystemData::records4d7068+16*slot).first<16>();
}
SpiritDescriptor readSpiritSlot(const SystemData& data,unsigned slot) {
    SpiritDescriptor d{};
    // 1527c8 leaves the destination untouched for slot >= 8.
    if(slot<8)std::copy_n(data.image().begin()+SystemData::records4d7068+16*slot,16,d.begin());
    return d;
}
SpiritDescriptor defaultSpirit(const SpiritsEditAssets& assets) {
    SpiritDescriptor d{};
    for(unsigned c=0;c<16;++c)d[c]=uint8_t(assets.first(c));
    d[0]=2;d[14]=0x2c;d[1]=5;d[2]=9;d[4]=0x16;
    return d;
}
void restoreDefaultSpirits(SystemData& data,const SpiritsEditAssets& assets) {
    const auto d=defaultSpirit(assets);
    for(unsigned slot=0;slot<8;++slot)std::copy(d.begin(),d.end(),spiritSlot(data,slot).begin());
}
int spiritPointsUsed(const SpiritsEditAssets& assets,const SpiritDescriptor& d) {
    int used=0;
    for(uint8_t option:d)used+=assets.cost(option);
    return used;
}
int spiritPointsLeft(const SpiritsEditAssets& assets,const SpiritDescriptor& d,int slot) {
    return (slot<6?50:300)-spiritPointsUsed(assets,d);
}
std::vector<SpiritIcon> spiritIcons(const SpiritDescriptor& d) {
    std::vector<SpiritIcon> out;
    auto put=[&](int group,int icon){out.push_back({int16_t(group),int16_t(icon)});};
    static constexpr int8_t gauge[]{10,6,7,8},maximum[]{10,11,12},secret[]{10,13,14},
                            slash[]{10,15,16,17,18,19},special[]{10,20,21,22,23,25,24};
    if(d[0]<4)put(0,gauge[d[0]]);
    if(d[1]>=4&&d[1]<7)put(1,maximum[d[1]-4]);
    if(d[2]>=7&&d[2]<10)put(2,secret[d[2]-7]);
    if(d[3]>=10&&d[3]<16)put(3,slash[d[3]-10]);
    if(d[4]>=16&&d[4]<23)put(4,special[d[4]-16]);
    if(d[10]==0x24)put(0x21,0x2a);
    if(d[5]==0x18)put(5,0x23);else if(d[5]==0x19)put(5,0x25);
    if(d[6]==0x1b)put(5,0x24);else if(d[6]==0x1c)put(5,0x26);
    if(d[7]==0x1e)put(5,0x1f);
    if(d[8]==0x20)put(5,0x20);
    if(d[9]==0x22)put(5,0x1c);
    if(d[11]==0x26)put(5,0x28);
    if(d[12]==0x28)put(5,0x1b);
    if(d[13]==0x2a)put(5,0x1e);
    if(d[14]==0x2c)put(5,0x29);
    if(d[15]==0x2e)put(5,0x27);
    return out;
}
std::optional<SpiritDescriptor> spiritDescriptor(const SystemData& data,int subMode,unsigned player,unsigned slot,
                                                 const NetworkSpirits* network) {
    if(slot>=8)return std::nullopt;
    if(subMode==6) {
        // The network buffer has no native owner unless the caller supplies one.
        if(!network||player>=network->players.size())return std::nullopt;
        return network->players[player][slot];
    }
    return readSpiritSlot(data,slot);
}
std::optional<SpiritDescriptor> actorSpiritDescriptor(const SystemData& data,int subMode,int system,unsigned player,
                                                      unsigned slot,const NetworkSpirits* network) {
    if(system!=6)return std::nullopt;
    return spiritDescriptor(data,subMode,player,slot,network);
}
int actorSpiritOption(const SystemData& data,int subMode,int system,unsigned player,unsigned slot,
                      unsigned category,const NetworkSpirits* network) {
    const auto d=actorSpiritDescriptor(data,subMode,system,player,slot,network);
    return d&&category<16?(*d)[category]:-1;
}

void SpiritPanel::construct(const SpiritsEditAssets& assets) {
    title=assets.panelTitle;visibleRows=1;width=0x80;active=visible=scroll=0;
    slide.reset();list.init();
    setRows(1,1,assets);
}
void SpiritPanel::setRows(int count,int visibleCount,const SpiritsEditAssets& assets) {
    if(count<=0)count=1;
    if(visibleCount==-1||visibleCount>=count)visibleCount=count;
    visibleRows=visibleCount;
    list.setRange(0,count,1,visibleRows);
    list.setCursor(list.cursor);
    scroll=editFollowScroll(list.cursor,visibleRows,scroll,list.max);
    cost.fill(0);label.fill(assets.emptyRow);value.fill({});
    nameChars=int(title.size());valueChars=0;
    width=0x92;height=visibleRows*0x15+0x16;
}
void SpiritPanel::setRow(unsigned row,const std::string& left,const std::string& right,int points) {
    if(row>=32)return;
    cost[row]=points;label[row]=left;value[row]=right;
    nameChars=std::max(nameChars,int(left.size()));
    valueChars=std::max(valueChars,int(right.size()));
    width=(nameChars+valueChars)*9+0x3c;
}

SpiritEditor::SpiritEditor(SystemData& data,const SpiritsEditAssets& assets):data_(&data),assets_(&assets) {
    categories.construct(assets);
    categories.setRows(16,9,assets);
    categories.slide.configure(-0x1d4,0x70,0xc,0x70,16);
    options.construct(assets);
    options.title=assets.optionTitle;
    options.slide.configure(0x320,0xbe,0x190,0xbe,16);
    load(0);
    buildOptions(0);
}
void SpiritEditor::load(int slotIndex) {
    slot=slotIndex;
    // The CHAIN COMBO category is listed only for the 300-point slots.
    categories.list.max=slot<6?15:16;
    categories.list.setCursor(0);
    categories.scroll=editFollowScroll(categories.list.cursor,categories.visibleRows,categories.scroll,categories.list.max);
    if(unsigned(slot)<8)descriptor=readSpiritSlot(*data_,unsigned(slot));
    refresh();
    buildOptions(categories.list.cursor);
}
void SpiritEditor::refresh() {
    for(unsigned c=0;c<16;++c) {
        const unsigned chosen=descriptor[c];
        static const std::string none;
        categories.setRow(c,assets_->categories[c].japanese,
                          chosen<assets_->options.size()?assets_->options[chosen].japanese:none,assets_->cost(chosen));
        first[c]=assets_->first(c);
    }
    categories.width=0x182;categories.nameChars=0x10;categories.valueChars=0x12;
    char text[32];
    std::snprintf(text,sizeof text,assets_->pointFormat.c_str(),spiritPointsLeft(*assets_,descriptor,slot));
    categories.title=text;
}
void SpiritEditor::buildOptions(int category) {
    const unsigned c=unsigned(category)&15;
    const int available=spiritPointsLeft(*assets_,descriptor,slot)+assets_->cost(descriptor[c]);
    options.list.attachBitmap();
    const int rows=assets_->count(c);
    options.setRows(rows,rows,*assets_);
    int row=0;
    for(const auto& o:assets_->options) {
        if(o.category!=c)continue;
        options.setRow(unsigned(row),o.japanese,{},o.cost);
        // Unaffordable options are refused; a refund (negative cost) never is.
        // Rows beyond this category keep their previous bitmap state.
        if(available<o.cost&&o.cost>=0)options.list.disableRow(row);
        else options.list.enableRow(row);
        ++row;
    }
    options.list.setCursor(int(descriptor[c])-first[c]);
    options.scroll=editFollowScroll(options.list.cursor,options.visibleRows,options.scroll,options.list.max);
    const int offset=(categories.list.cursor-categories.scroll)*0x15;
    if(c==4){--options.nameChars;options.width-=9;}
    options.slide.inX=std::min(0x272-options.width,0x1b0);
    // The panel jumps vertically to the highlighted category row, kept
    // inside the category panel, and only its X coordinate slides.
    int y=categories.slide.y+offset;
    const int bottom=categories.slide.y+categories.height;
    if(y+options.height-0x15>=bottom)y=bottom-options.height+0x15;
    options.slide.y=options.slide.outY=options.slide.inY=y;
    options.slide.slideIn();
    options.active=0;options.visible=1;
}
void SpiritEditor::commit() {
    const unsigned c=unsigned(categories.list.cursor)&15;
    descriptor[c]=uint8_t(first[c]+options.list.cursor);
    // 152830: the working table is rewritten on every confirmed option.
    if(unsigned(slot)<8)std::copy(descriptor.begin(),descriptor.end(),spiritSlot(*data_,unsigned(slot)).begin());
    refresh();
}
void SpiritEditor::help() {
    helpId=focus?categories.list.cursor+0x10:0xf;
    helpSub=focus?options.list.cursor:categories.list.cursor;
    ++helpRevision;
}
int SpiritEditor::update(const MenuPad& pad,std::vector<int>& sounds) {
    const int a=categories.slide.update(),b=options.slide.update();
    if(focus) {
        if(b==0){options.visible=options.active=0;return EditNone;}
        if(b!=1||!options.visible||!options.active)return EditNone;
        const int event=options.list.update(pad,sounds);
        options.scroll=editPageScroll(event,options.list.cursor,options.visibleRows,options.scroll,options.list.max);
        options.scroll=editFollowScroll(options.list.cursor,options.visibleRows,options.scroll,options.list.max);
        if(event==EditConfirm||event==EditCancel) {
            if(event==EditConfirm)commit();
            focus=0;categories.active=1;options.active=0;
            help();
        } else if(event>=EditMoved&&event<=EditPageForward)help();
        return EditNone;
    }
    if(a==0){categories.visible=categories.active=0;return EditNone;}
    if(a!=1||!categories.visible||!categories.active)return EditNone;
    const int event=categories.list.update(pad,sounds);
    categories.scroll=editPageScroll(event,categories.list.cursor,categories.visibleRows,categories.scroll,categories.list.max);
    categories.scroll=editFollowScroll(categories.list.cursor,categories.visibleRows,categories.scroll,categories.list.max);
    if(event==EditConfirm) {
        categories.active=0;focus=1;
        buildOptions(categories.list.cursor);
        options.active=1;
        help();
    } else if(event>=EditMoved&&event<=EditPageForward) {
        buildOptions(categories.list.cursor);
        help();
    }
    return event;
}
void SpiritEditor::show() {
    focus=0;
    categories.slide.slideIn();categories.visible=categories.active=1;
    options.slide.slideIn();options.visible=1;options.active=0;
}
void SpiritEditor::hide() {
    focus=0;
    categories.slide.slideOut();categories.active=0;
    options.slide.slideOut();options.active=0;
}
void SpiritEditor::setActive(bool on) {
    categories.active=on&&!focus;
    options.active=on&&focus;
}

SpiritsEdit::SpiritsEdit(SystemData& data,const SpiritsEditAssets& assets,const EditWidgetAssets& widgets,GameRandom& random)
    :slots(widgets),editor(data,assets),data_(&data),widgets_(&widgets) {
    chrome.enter(int(random.nextLibrary()));
    slots.slide.configure(-0x130,0x50,0x10,0x50,16);
    slots.list.setFlag(16,true);
    const int count=spiritSlotCount(data);
    if(count==8)slots.setStrings({assets.slotNames.begin(),assets.slotNames.end()},8);
    else {
        slots.setRows(6,6);
        for(unsigned i=0;i<6;++i)slots.setRow(i,assets.slotNames[i]);
    }
    editor.hide();
    summary.reset();
    summary.configure(0x2c2,0x70,0xe2,0x70,16);
    summary.slideOut();
    helpSeen_=editor.helpRevision;
}
std::vector<SpiritIcon> SpiritsEdit::summaryIcons() const {
    // 17eac8 reads the highlighted slot through 152758(0, slot).
    const auto d=spiritDescriptor(*data_,0,0,unsigned(slots.list.cursor));
    return d?spiritIcons(*d):std::vector<SpiritIcon>{};
}
SpiritsEditResult SpiritsEdit::tick(const MenuPad& pad) {
    SpiritsEditResult result;
    summary.update();
    // Both owners are sampled before the state switch; inactive ones return 0.
    const int slotEvent=slots.update(pad,result.sounds);
    const int editorEvent=editor.update(pad,result.sounds);
    if(helpSeen_!=editor.helpRevision){helpSeen_=editor.helpRevision;helpId=editor.helpId;helpSub=editor.helpSub;}
    if(next!=state) {
        // A state change spends one visit on its entry actions only.
        switch(next) {
        case 7:
            frameOpen=true;
            slots.slide.slideIn();slots.visible=1;
            summary.slideIn();slots.active=1;
            editor.hide();
            helpId=0x21;helpSub=1;
            break;
        case 8:
            if(state<8)editor.load(slots.list.cursor);
            editor.show();
            slots.slide.slideOut();slots.active=0;
            summary.slideOut();
            break;
        case -1:
            slots.slide.slideOut();slots.active=0;
            summary.slideOut();
            frameOpen=false;
            break;
        }
        state=next;
        return result;
    }
    switch(state) {
    case 7:
        if(slotEvent==EditConfirm)next=8;
        else if(slotEvent==EditCancel)next=-1;
        break;
    case 8:
        if(editorEvent==EditCancel)next=7;
        break;
    case -1:
        if(slots.slide.settled()) {
            result.autoSave=data_->autoSave()!=0;
            result.exitToTitle=true;
            next=-2;
        }
        break;
    }
    if(next!=state){slots.active=0;editor.setActive(false);}
    return result;
}
}
