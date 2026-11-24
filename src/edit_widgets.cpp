#include "asset_files.hpp"
#include "edit_widgets.hpp"
#include <algorithm>
#include <fstream>
#include <iterator>
#include <stdexcept>

namespace ss6 {
void EditSlide::configure(int ox,int oy,int ix,int iy,int frames) {
    inY=iy;duration=frames;outX=ox;outY=oy;inX=ix;
    snap(outX,outY);
    retracted=1;
}
void EditSlide::snap(int px,int py) {
    targetX=startX=x=px;targetY=startY=y=py;remaining=0;
}
static void start(EditSlide& s,int tx,int ty) { // 17f3c0
    s.remaining=s.duration;s.targetX=tx;s.targetY=ty;s.startX=s.x;s.startY=s.y;
    if(s.x==tx&&s.y==ty)s.remaining=0;
    s.retracted=0;
}
void EditSlide::slideIn() {
    // The comparison is against the current target, not the position: a
    // slide already heading in keeps its progress and its state word.
    if(targetX!=inX||targetY!=inY)start(*this,inX,inY);
}
void EditSlide::slideOut() {
    if(targetX==outX&&targetY==outY)return;
    start(*this,outX,outY);
    retracted=1;
}
int EditSlide::update() {
    if(remaining>0) {
        const int r=--remaining;
        // Signed 32-bit products, truncating division, X and Y separately.
        x=(r*startX+(duration-r)*targetX)/duration;
        y=(r*startY+(duration-r)*targetY)/duration;
        if(r>0)return 2;
    }
    return retracted==0;
}
int editPageScroll(int event,int,int visible,int scroll,int rows) {
    int v=event==3?scroll+visible:event==2?scroll-visible:scroll;
    if(v<0)return 0;
    return std::min(v,rows-visible);
}
int editFollowScroll(int cursor,int visible,int scroll,int rows) {
    int v=std::min(cursor,scroll);
    if(rows<v+visible)v=rows-visible;
    if(cursor>=v+visible)v=cursor-visible+1;
    return std::max(v,0);
}

void EditListCursor::init() {
    cursor=0;flags=5;
    setRange(0,1,1,0);
}
void EditListCursor::setRange(int lo,int hi,int stride,int pageRows) {
    if(lo==hi)++hi;
    if(hi<lo)std::swap(lo,hi);
    min=lo;max=hi;step=stride?stride:1;page=pageRows<hi?pageRows:0;
    setCursor(cursor);
}
void EditListCursor::setCursor(int value) {
    if(flags&4)cursor=value;
    else cursor=value<min?min:value<max?value:max-1;
}
// 20e498: word (row + 31 if negative) >> 5, bit row & 31, so rows -31..-1
// alias the top bits of word 0. Indices outside the native bitmap are
// treated as enabled; the original reads its neighbours.
static int bitmapWord(int row) {
    const int word=(row<0?row+31:row)>>5;
    return word>=0&&word<16?word:-1;
}
void EditListCursor::disableRow(int row) {
    if(const int word=bitmapWord(row);flags&0x800&&word>=0)disabled[word]|=1u<<(row&31);
}
void EditListCursor::enableRow(int row) {
    if(const int word=bitmapWord(row);flags&0x800&&word>=0)disabled[word]&=~(1u<<(row&31));
}
bool EditListCursor::rowDisabled(int row) const {
    const int word=bitmapWord(row);
    return flags&0x800&&word>=0&&(disabled[word]>>(row&31)&1);
}
int EditListCursor::update(const MenuPad& pad,std::vector<int>& sounds) {
    const int old=cursor;
    const uint32_t p=pad.pressed,r=pad.repeat;
    const bool confirm=(!(flags&0x20000)&&(p&8))||(p&0x202);
    const bool cancel=!confirm&&(p&0x404);
    auto reject=[&](uint32_t silent) {
        if(!(flags&silent))sounds.push_back(EditSoundCancel);
        return EditRejected;
    };
    if(confirm) {
        if(flags&0x10||rowDisabled(old))return reject(0x300);
        if(!(flags&0x300))sounds.push_back(EditSoundConfirm);
        return EditConfirm;
    }
    if(cancel) {
        // A refused cancel is silenced by the cancel mask 500, not by 300.
        if(flags&0x20)return reject(0x500);
        if(!(flags&0x500))sounds.push_back(EditSoundCancel);
        return EditCancel;
    }
    int d=0;
    if(flags&2)d=r&0x40?-step:r&0x80?step:0;
    if(flags&1&&d==0)d=r&0x10?-step:r&0x20?step:0;
    if(flags&8)d=-d;
    if(flags&0x40000)d=0;
    const int n=old+d;
    cursor=n>=max?(flags&4?min:max-1):n<min?(flags&4?max-1:min):n;
    const bool silent=flags&0x80;
    if(cursor!=old) {
        if(!silent)sounds.push_back(EditSoundMove);
        return EditMoved;
    }
    if(page<0)return EditNone;
    // The shoulder-button jumps request the move sound before the cursor
    // is compared, so a jump that cannot move is still audible.
    int event=EditMoved;
    if(page>0&&r&0x100000) {
        if(!silent)sounds.push_back(EditSoundMove);
        cursor=std::max(0,cursor-page*step);event=EditPageBack;
    } else if(page>0&&r&0x400000) {
        if(!silent)sounds.push_back(EditSoundMove);
        cursor=std::min(cursor+page*step,max-1);event=EditPageForward;
    } else if(r&0x200000) {
        if(!silent)sounds.push_back(EditSoundMove);
        cursor=0;
    } else if(r&0x800000) {
        if(!silent)sounds.push_back(EditSoundMove);
        cursor=max-1;
    }
    return cursor!=old?event:EditNone;
}

static std::vector<uint8_t> readAll(const std::filesystem::path& file) {
    std::ifstream in(resolveAsset(file),std::ios::binary);
    if(!in)throw std::runtime_error("Missing asset: "+file.string());
    return {std::istreambuf_iterator<char>(in),{}};
}
namespace {
struct Reader {
    const std::vector<uint8_t>& data;size_t at;
    uint8_t byte() {return data.at(at++);}
    std::string text() {
        const size_t n=byte();const size_t size=n|size_t(byte())<<8;
        if(at+size>data.size())throw std::runtime_error("Truncated edit asset string");
        std::string s(data.begin()+at,data.begin()+at+size);at+=size;return s;
    }
};
}
EditWidgetAssets::EditWidgetAssets(const std::filesystem::path& assets) {
    const auto data=readAll(assets/"edit_widgets.bin");
    if(data.size()<6||!std::equal(data.begin(),data.begin()+4,"EDWG"))throw std::runtime_error("Invalid edit_widgets.bin");
    Reader in{data,4};
    const size_t n=in.byte();const size_t rows=n|size_t(in.byte())<<8;
    for(size_t i=0;i<rows;++i)helpIds.push_back(in.byte());
    for(size_t i=0;i<rows;++i)helpTexts.push_back(in.text());
    for(auto& id:characterOrder)id=in.byte();
    for(auto& name:characterNames)name=in.text();
    menuTitle=in.text();undefinedRow=in.text();helpFallback=in.text();
    for(auto& name:exNames)name=in.text();
    if(in.at!=data.size())throw std::runtime_error("Trailing bytes in edit_widgets.bin");
}
const std::string& EditWidgetAssets::help(int id,int sub) const {
    for(size_t i=0;i<helpIds.size();++i) {
        if(helpIds[i]!=id)continue;
        // The sub index is added without a range check; it can step into a
        // neighbouring id's rows (a descriptor byte outside its category).
        const long row=long(i)+sub;
        return row>=0&&row<long(helpTexts.size())?helpTexts[size_t(row)]:helpFallback;
    }
    return helpFallback;
}

EditListMenu::EditListMenu(const EditWidgetAssets& assets):title(assets.menuTitle),assets_(&assets) {
    slide.reset();list.init();
    setRows(1,1);
}
void EditListMenu::setRows(int count,int visibleCount) {
    list.setFlag(12,false);list.setFlag(13,false);
    if(count<=0)count=1;
    if(visibleCount==-1)visibleCount=count;
    visibleRows=std::min(visibleCount,count);
    list.setRange(0,count,1,visibleRows);
    list.setCursor(list.cursor);
    scroll=editFollowScroll(list.cursor,visibleRows,scroll,list.max);
    rows.assign(0x200,assets_->undefinedRow);
    if(list.flag(16)){width=0x92;height=visibleRows*0x15+0x1a;}
    else if(list.flag(15)){width=0x7a;height=visibleRows*17+0x18;}
    else {width=0x74;height=visibleRows*9+0x16;}
}
void EditListMenu::setStrings(const std::vector<std::string>& strings,int visibleCount) {
    if(strings.empty())return;
    const int count=int(strings.size());
    setRows(count,visibleCount);
    for(int row=count;row-->0;)setRow(unsigned(row),strings[row]);
}
void EditListMenu::setRow(unsigned row,const std::string& text) {
    if(row>=0x200)return;
    rows[row]=text;
    const int length=int(text.size());
    const int wanted=list.flag(16)?(length>>1)*0x14+0x1c:list.flag(15)?(length<<4)+0x1c:length*10+0x1a;
    width=std::max(width,wanted);
}
int EditListMenu::update(const MenuPad& pad,std::vector<int>& sounds) {
    const int state=slide.update();
    if(state==0){visible=active=0;return EditNone;}
    if(state!=1||!visible||!active)return EditNone;
    const int event=list.update(pad,sounds);
    scroll=editPageScroll(event,list.cursor,visibleRows,scroll,list.max);
    scroll=editFollowScroll(list.cursor,visibleRows,scroll,list.max);
    return event;
}
void EditListMenu::buildCharacterList(const SystemData& data,int visibleCount,int firstRow,bool includeEx,
                                      bool includeKuroko,bool useEndingTable) {
    list.setFlag(16,true);
    characterIds.fill(-1);
    int count=0;
    auto add=[&](int id) {
        const int row=firstRow+count++;
        if(row>=0&&row<int(characterIds.size()))characterIds[row]=int16_t(id);
    };
    for(unsigned i=0;i<0x31;++i) {
        const unsigned id=assets_->characterOrder[i];
        const bool listed=id==0x2b?includeKuroko:useEndingTable?data.option(0x47+id)!=0:data.option(0x16+id)==0;
        if(listed)add(int(id));
    }
    if(includeEx&&data.option(0x94))for(unsigned i=0;i<4;++i)add(assets_->characterOrder[0x31+i]);
    setRows(count+firstRow,visibleCount);
    for(int i=0;i<count;++i) {
        const int row=firstRow+i,id=row>=0&&row<int(characterIds.size())?characterIds[row]:-1;
        if(id<0)continue;
        if(id<0x32){if(id<49)setRow(unsigned(row),assets_->characterNames[id]);}
        else setRow(unsigned(row),assets_->exNames[id==73?1:id==72?2:id==75?3:id==74?4:0]);
    }
    list.setFlag(13,true);
}
int EditListMenu::selected() const {
    if(!list.flag(13))return list.cursor;
    return list.cursor>=0&&list.cursor<int(characterIds.size())?characterIds[list.cursor]:-1;
}
void EditListMenu::select(int id) {
    int target=id;
    if(list.flag(13)) {
        const auto found=std::find(characterIds.begin(),characterIds.end(),int16_t(id));
        if(found!=characterIds.end())target=int(found-characterIds.begin());
    }
    list.setCursor(target);
    scroll=editFollowScroll(list.cursor,visibleRows,scroll,list.max);
}
}
