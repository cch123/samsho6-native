#include "asset_files.hpp"
#include "menu_widgets.hpp"
#include <algorithm>
#include <cstring>
#include <fstream>
#include <stdexcept>

namespace ss6 {
namespace {
uint32_t word(std::span<const uint8_t> bytes,size_t at) {
    if(at+4>bytes.size())throw std::runtime_error("Truncated menu table");
    uint32_t v;std::memcpy(&v,bytes.data()+at,4);return v;
}
template<class T,size_t N> void copyBytes(std::span<const uint8_t> from,size_t at,std::array<T,N>& to) {
    if(at+N>from.size())throw std::runtime_error("Truncated menu layout table");
    std::memcpy(to.data(),from.data()+at,N);
}
}
AssetSections::AssetSections(const std::filesystem::path& file):file_(file) {
    std::ifstream in(resolveAsset(file),std::ios::binary);
    bytes_.assign(std::istreambuf_iterator<char>(in),std::istreambuf_iterator<char>());
    if(!in||bytes_.size()<4)throw std::runtime_error("Missing menu table: "+file.string());
}
std::span<const uint8_t> AssetSections::section(std::string_view tag) const {
    const std::span<const uint8_t> all(bytes_);
    size_t at=4;
    for(uint32_t n=word(all,0);n;--n) {
        const uint32_t size=word(all,at+4);
        if(at+8+size>all.size())break;
        if(std::memcmp(all.data()+at,tag.data(),4)==0)return all.subspan(at+8,size);
        at+=8+size;
    }
    throw std::runtime_error("Missing section "+std::string(tag)+" in "+file_.string());
}
std::vector<std::string> AssetSections::strings(std::string_view tag) const {
    const auto data=section(tag);
    std::vector<std::string> out(word(data,0));
    size_t at=4;
    for(auto& s:out) {
        if(at+2>data.size())throw std::runtime_error("Truncated string table");
        const size_t n=data[at]|data[at+1]<<8;
        if(at+2+n>data.size())throw std::runtime_error("Truncated string table");
        s.assign(reinterpret_cast<const char*>(data.data())+at+2,n);
        at+=2+n;
    }
    return out;
}

MenuWidgetData::MenuWidgetData(const std::filesystem::path& assets) {
    const AssetSections file(assets/"menu_widgets.bin");
    characterNames=file.strings("NAME");
    exNames=file.strings("EXNM");
    undefined=file.strings("UNDF").at(0);
    messages=file.strings("MSGT");
    keyHelp=file.strings("KEYS");
    const auto keys=file.section("MSGK");
    messageKeys.assign(keys.begin(),keys.end());
    copyBytes(file.section("ORDR"),0,order);
    const auto layouts=file.section("LAYT");
    copyBytes(layouts,0,backdrop);copyBytes(layouts,11,titleRect);
    copyBytes(layouts,22,lowMessageBar);copyBytes(layouts,33,keyCase);
    const auto rects=file.section("RECT");
    if(characterNames.size()!=49||exNames.size()!=5||keyHelp.size()!=5||messages.size()!=messageKeys.size()
       ||rects.size()!=sizeof titleRects)
        throw std::runtime_error("Invalid menu_widgets.bin");
    std::memcpy(titleRects.data(),rects.data(),sizeof titleRects);
}
int MenuWidgetData::message(int key,int sub) const {
    // The scan compares only the key byte; `sub` is added without a bound
    // or key check, so (2d,1) addresses the 2e record.
    for(size_t i=0;i<messageKeys.size();++i)
        if(messageKeys[i]==key)return int(i)+sub;
    return -1;
}
std::string_view MenuWidgetData::messageText(int record) const {
    return record>=0&&size_t(record)<messages.size()?std::string_view(messages[record]):std::string_view();
}
std::string_view MenuWidgetData::characterName(int id) const {
    if(id<0x32)return characterNames.at(size_t(id));
    const int ex=id-0x32;
    return exNames[ex>=0x16&&ex<=0x19?size_t(ex-0x16):4];
}

void SlidePanel::configure(int cx,int cy,int ox,int oy,int frames) {
    closedX=cx;closedY=cy;openX=ox;openY=oy;duration=frames;
}
void SlidePanel::reset(int cx,int cy,int ox,int oy,int frames) {
    configure(cx,cy,ox,oy,frames);snap(closedX,closedY);closing=1;
}
void SlidePanel::snap(int px,int py) {
    targetX=x=startX=px;targetY=y=startY=py;left=0;
}
void SlidePanel::slide(int px,int py,int frames) {
    duration=left=frames;
    targetX=px;targetY=py;startX=x;startY=y;
    if(x==px&&y==py)left=0;
    closing=0;
}
void SlidePanel::open() {
    if(targetX!=openX||targetY!=openY)slide(openX,openY,duration);
}
void SlidePanel::close() {
    if(targetX==closedX&&targetY==closedY)return;
    slide(closedX,closedY,duration);closing=1;
}
int SlidePanel::tick() {
    if(left>0) {
        const int t=--left;
        if(duration) {
            x=(t*startX+(duration-t)*targetX)/duration;
            y=(t*startY+(duration-t)*targetY)/duration;
        }
        if(t>0)return 2;
    }
    return closing==0;
}

void MenuSelector::init() {
    current=0;flags=5;setRange(0,1,1,0);
}
void MenuSelector::setRange(int lo,int hi,int stride,int pageRows) {
    if(lo==hi)++hi;
    if(hi<lo)std::swap(lo,hi);
    min=lo;max=hi;step=stride?stride:1;
    page=pageRows<hi?pageRows:0;
    setCursor(current);
}
void MenuSelector::setCursor(int value) {
    // With the wrap flag the range fix-up is dead code: 20e0d0 stores the
    // wrapped value and its common exit (20e100) overwrites it with the
    // argument, so an out-of-range cursor survives until the next 20e128.
    if(flags&4)current=value;
    else current=value<min?min:value>=max?max-1:value;
}
bool MenuSelector::itemDisabled(int item) const {
    if(!(flags&0x800)||!disabled)return false;
    const int index=(item<0?item+0x1f:item)>>5;
    return index>=0&&size_t(index)<disabled->size()&&((*disabled)[size_t(index)]>>(item&31)&1);
}
int MenuSelector::update(const WidgetPad& pad,std::vector<int>& tones) {
    const int old=current;
    const bool confirm=(flags&0x20000)?(pad.pressed&0x202)!=0:(pad.pressed&8)||(pad.pressed&0x202);
    const bool cancel=!confirm&&(pad.pressed&0x404);
    if(confirm) {
        if((flags&0x10)||itemDisabled(old)) {
            if(!(flags&0x300))tones.push_back(0x24);
            return Refused;
        }
        if(!(flags&0x300))tones.push_back(0);
        return Confirm;
    }
    if(cancel) {
        // A refused cancel tests 500, unlike a refused confirm (300).
        if(!(flags&0x500))tones.push_back(0x24);
        return flags&0x20?Refused:Cancel;
    }
    int delta=0;
    if(flags&2) {
        if(pad.repeat&0x40)delta=-step;
        else if(pad.repeat&0x80)delta=step;
    }
    if((flags&1)&&delta==0) {
        if(pad.repeat&0x10)delta=-step;
        else if(pad.repeat&0x20)delta=step;
    }
    if(flags&8)delta=-delta;
    if(flags&0x40000)delta=0;
    current=old+delta;
    if(current>=max)current=flags&4?min:max-1;
    else if(current<min)current=flags&4?max-1:min;
    const auto moveTone=[&]{if(!(flags&0x80))tones.push_back(0x20);};
    if(current!=old){moveTone();return Moved;}
    if(page<0)return Idle;
    // The four paging branches request the tone even when the cursor stays.
    if(page>0&&(pad.repeat&0x100000)) {
        moveTone();current=std::max(current-page*step,0);
        return current!=old?PageBack:Idle;
    }
    if(page>0&&(pad.repeat&0x400000)) {
        moveTone();current=std::min(current+page*step,max-1);
        return current!=old?PageForward:Idle;
    }
    if(pad.repeat&0x200000){moveTone();current=0;return current!=old?Moved:Idle;}
    if(pad.repeat&0x800000){moveTone();current=max-1;return current!=old?Moved:Idle;}
    return Idle;
}

void ListWidget::init(const MenuWidgetData& tables,CharacterRows& characterRows) {
    data=&tables;rows=&characterRows;
    visible=1;width=0x80;top=shown=active=0;
    panel.reset(0,0,0,0,1);
    selector.disabled=nullptr;
    selector.init();
    resize(1,1);
}
void ListWidget::resize(int count,int visibleRows) {
    selector.setFlag(MenuSelector::MenuRows,false);
    selector.setFlag(MenuSelector::CharacterRows,false);
    if(count<=0)count=1;
    if(visibleRows==-1)visibleRows=count;
    visible=std::min(visibleRows,count);
    selector.setRange(0,count,1,visible);   // paging only when the list scrolls
    selector.setCursor(selector.current);
    top=followTop(selector.current,visible,top,selector.max);
    items.fill(data->undefined);
    if(selector.flag(MenuSelector::LargeText)){width=0x92;height=visible*21+0x1a;}
    else if(selector.flag(MenuSelector::MediumText)){width=0x7a;height=visible*17+0x18;}
    else {width=0x74;height=visible*9+0x16;}
}
void ListWidget::setItem(unsigned index,std::string_view text) {
    if(index>=capacity)return;
    items[index]=text;
    if(!text.data())return;
    const int length=int(text.size());
    const int need=selector.flag(MenuSelector::LargeText)?(length>>1)*20+0x1c
                  :selector.flag(MenuSelector::MediumText)?length*16+0x1c:length*10+0x1a;
    width=std::max(width,need);
}
void ListWidget::fill(std::span<const std::string> table,int visibleRows) {
    const int count=int(table.size());
    if(!count)return;
    resize(count,visibleRows==-1?count:visibleRows);
    for(int i=count;i--;)setItem(unsigned(i),table[size_t(i)]);
}
void ListWidget::fillCharacters(const SystemData& system,int visibleRows,int first,bool withExtra,bool withKuroko,bool byEnding) {
    selector.setFlag(MenuSelector::LargeText,true);
    rows->fill(-1);
    int n=0;
    const auto put=[&](int id){if(size_t(first+n)<rows->size())(*rows)[size_t(first+n)]=int16_t(id);++n;};
    for(int k=0;k<0x31;++k) {
        const unsigned c=data->order[size_t(k)];
        const bool keep=c==0x2b?withKuroko:byEnding?system.option(0x47+c)!=0:system.option(0x16+c)==0;
        if(keep)put(int(c));
    }
    if(withExtra&&system.option(0x94))
        for(int k=0;k<4;++k)put(data->order[size_t(0x31+k)]);
    resize(first+n,visibleRows);
    for(int j=0;j<n;++j)setItem(unsigned(first+j),data->characterName((*rows)[size_t(first+j)]));
    selector.setFlag(MenuSelector::CharacterRows,true);
}
void ListWidget::append(std::string_view text) {
    if(unsigned(selector.max)<capacity)items[size_t(selector.max)]=text;
    ++selector.max;
}
void ListWidget::select(int id) {
    int row=id;
    if(selector.flag(MenuSelector::CharacterRows)) {
        const auto found=std::find(rows->begin(),rows->end(),id);
        if(found!=rows->end())row=int(found-rows->begin());
    }
    selector.setCursor(row);
    top=followTop(selector.current,visible,top,selector.max);
}
int ListWidget::selected() const {
    if(!selector.flag(MenuSelector::CharacterRows))return selector.current;
    return size_t(selector.current)<rows->size()?(*rows)[size_t(selector.current)]:-1;
}
int ListWidget::update(const WidgetPad& pad,std::vector<int>& tones) {
    const int motion=panel.tick();
    // A list that has finished closing hides itself and drops the focus.
    if(motion==0){shown=active=0;return 0;}
    if(motion!=1||!shown||!active)return 0;
    const int code=selector.update(pad,tones);
    top=pageTop(code,visible,top,selector.max);
    top=followTop(selector.current,visible,top,selector.max);
    return code;
}
uint32_t ListWidget::rowColour(bool active,bool selected) {
    return active?(selected?0xffff0000u:0xffffffffu):(selected?0xffa00000u:0xffb0b0b0u);
}
int ListWidget::pageTop(int code,int visibleRows,int topRow,int count) {
    int v=topRow;
    if(code==MenuSelector::PageForward)v=topRow+visibleRows;
    if(code==MenuSelector::PageBack)v=topRow-visibleRows;
    if(v<0)return 0;
    return std::min(v,count-visibleRows);
}
int ListWidget::followTop(int cursor,int visibleRows,int topRow,int count) {
    int v=std::min(topRow,cursor);
    if(count<v+visibleRows)v=count-visibleRows;
    if(cursor>=v+visibleRows)v=cursor-visibleRows+1;
    return std::max(v,0);
}

void GuideWindow::init(const MenuWidgetData& tables) {
    *this=GuideWindow{};
    data=&tables;
    // Each bar constructor is 17f308 followed by its layout setter with -1.
    // Only the title setter configures its panel for an unknown layout.
    for(GuideBar* bar:{&title,&message,static_cast<GuideBar*>(&keys),static_cast<GuideBar*>(&extra)})
        bar->panel.reset(0,0,0,0,1);
    title.panel.reset(0,-0x90,0,0x10,0x10);title.configured=1;
    messageRecord=data->message(0x22,-1);
}
void GuideWindow::setLayout(int value,unsigned seat) {
    if(layout==value)return;
    layout=value;
    if(unsigned(value)<0xb) {
        backdrop=data->backdrop[size_t(value)];
        if(title.layout!=value) {
            title.layout=value;
            if(title.configured)title.panel.configure(0,-0x90,0,0x10,0x10);
            else title.panel.reset(0,-0x90,0,0x10,0x10);
            title.configured=1;
            titleRect=data->titleRect[size_t(value)];
        }
        if(message.layout!=value) {
            message.layout=value;
            const bool low=data->lowMessageBar[size_t(value)];
            const int cy=low?0x1f6:0x21c,oy=low?0x156:0x17c;
            if(message.configured)message.panel.configure(0,cy,0,oy,0x10);
            else message.panel.reset(0,cy,0,oy,0x10);
            message.configured=1;
            messageRecord=data->message(0x22,value);
        }
        setKeys(keys,value,seat);
    }
    if(!initialised) {
        // 182770: the first layout snaps every bar to its closed position.
        for(GuideBar* bar:{&title,&message,static_cast<GuideBar*>(&keys),static_cast<GuideBar*>(&extra)}) {
            bar->panel.snapClosed();bar->open=0;
        }
        initialised=1;
    }
    setKeys(extra,0xb,seat);
}
void GuideWindow::setKeys(GuideKeys& bar,int value,unsigned seat) {
    if(bar.layout==value)return;
    bar.layout=value;
    if(unsigned(value)>=0xe)return;
    const auto place=[&](int cx,int cy,int ox,int oy) {
        if(bar.configured)bar.panel.configure(cx,cy,ox,oy,0x10);
        else bar.panel.reset(cx,cy,ox,oy,0x10);
        bar.configured=1;
    };
    const auto metrics=[&]{bar.width=0x140;bar.height=0x1c;bar.textX=0x1a;bar.textY=2;};
    switch(data->keyCase[size_t(value)]) {
    case 0:
        // 181960 (layout 0): the "open" position is the off-screen one and
        // neither the size nor the text is written.
        if(seat==1)place(0,0x192,-0x190,0x192);else place(0x140,0x192,0x2d0,0x192);
        break;
    case 1:
        metrics();bar.text=0;place(0x2d0,0x158,0x140,0x158);
        break;
    case 2:
        metrics();bar.text=0;
        if(seat==1)place(-0x190,0x192,0,0x192);else place(0x2d0,0x192,0x140,0x192);
        break;
    case 3:
        metrics();bar.text=value==9?1:0;
        if(seat==1)place(-0x190,0x158,0,0x158);else place(0x2d0,0x158,0x140,0x158);
        break;
    default:
        metrics();place(0x2d0,0x13c,0x140,0x13c);
        bar.text=value==0xb?2:value==0xc?4:3;
        break;
    }
}
void GuideWindow::tick() {
    title.panel.tick();message.panel.tick();keys.panel.tick();extra.panel.tick();
}
void GuideWindow::open() {
    title.panel.open();title.shown=title.open=1;
    message.panel.open();message.shown=message.open=1;
    keys.panel.open();keys.open=keys.shown=1;
    extra.panel.close();extra.open=0;
}
void GuideWindow::close() {
    for(GuideBar* bar:{&title,&message,static_cast<GuideBar*>(&keys),static_cast<GuideBar*>(&extra)}) {
        bar->panel.close();bar->open=0;
    }
}
bool GuideWindow::menuBackdrop(unsigned gameMode) {
    // 17ea48: modes with a battle scene behind the window keep it visible.
    return !(gameMode<=12&&(0x1fceu>>gameMode&1));
}
}
