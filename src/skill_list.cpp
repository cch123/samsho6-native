#include "skill_list.hpp"
#include <algorithm>
#include <cstring>
#include <stdexcept>

namespace ss6 {
namespace {
uint32_t rgb(const uint8_t* c) {return 0xff000000u|uint32_t(c[0])<<16|uint32_t(c[1])<<8|c[2];}
}

SkillListData::SkillListData(const std::filesystem::path& assets) {
    const AssetSections file(assets/"skill_list.bin");
    texts=file.strings("TEXT");
    categories=file.strings("CATS");
    commonRows=file.strings("ROWS");
    const char* tags[2]={"CMNR","CHRR"};
    for(int t=0;t<2;++t) {
        const auto raw=file.section(tags[t]);
        if(raw.size()%12)throw std::runtime_error("Invalid skill_list.bin records");
        tables[t].resize(raw.size()/12);
        for(size_t i=0;i<tables[t].size();++i) {
            const uint8_t* p=raw.data()+12*i;
            const auto u16=[&](size_t o){return uint16_t(p[o]|p[o+1]<<8);};
            Record& r=tables[t][i];
            r={int16_t(u16(0)),p[2],p[3],u16(4),{u16(6),u16(8),u16(10)}};
            for(auto index:r.text)if(index>=texts.size())throw std::runtime_error("Invalid skill_list.bin text index");
            if(r.type>6)throw std::runtime_error("Invalid skill_list.bin record type");
        }
        if(tables[t].empty()||tables[t][0].id<0)throw std::runtime_error("Invalid skill_list.bin table");
    }
    const auto colours=file.section("COLR"),bars=file.section("BARC"),rects=file.section("ICON"),constants=file.section("CNST");
    const auto literals=file.strings("LITS");
    if(colours.size()!=27||bars.size()!=36||rects.size()!=sizeof icons||constants.size()!=24||literals.size()!=3
       ||categories.size()!=2||commonRows.size()!=10)
        throw std::runtime_error("Invalid skill_list.bin");
    std::memcpy(nameColour.data(),colours.data(),21);
    std::memcpy(shadowColour.data(),colours.data()+21,6);
    std::memcpy(barColour.data(),bars.data(),36);
    std::memcpy(icons.data(),rects.data(),sizeof icons);
    space=literals[0];exitLabel=literals[1];
    int32_t c[6];
    std::memcpy(c,constants.data(),sizeof c);
    barX=c[0];smallGlyphY=c[1];iconX=c[2];exitY=c[3];scrollBarWidth=c[4];scrollBarHeight=c[5];
}
int SkillListData::find(int table,int id) const {
    const auto& records=tables[size_t(table)];
    for(size_t i=0;i<records.size();++i)if(records[i].id==id)return int(i);
    return -1;
}
int SkillListData::lines(int table,int first,int id) const {
    const auto& records=tables[size_t(table)];
    if(first<0||(records[size_t(first)].id!=id&&records[size_t(first)].id!=-1))return 0;
    int count=0;
    for(size_t r=size_t(first);r<records.size()&&(records[r].id==id||records[r].id==-1);++r)
        for(unsigned column=0;column<3;++column) {
            const auto line=text(records[r],column);
            if(line.empty())continue;
            for(size_t at=0;at!=std::string_view::npos;at=skillNextLine(line,at))++count;
        }
    return count;
}

size_t skillNextLine(std::string_view text,size_t at) {
    const auto byte=[&](size_t i){return i<text.size()?static_cast<unsigned char>(text[i]):0u;};
    unsigned c=byte(at++);
    if(!c)return std::string_view::npos;
    for(;;) {
        if(c=='C') {
            // The byte after a 'C' is consumed without being tested as a new 'C'.
            const unsigned d=byte(at++);
            if(!d)return std::string_view::npos;
            if(d=='R')return at;
        }
        c=byte(at);
        if(!c)return std::string_view::npos;
        ++at;
    }
}

int skillIconCode(unsigned char a,unsigned char b,int& dx,int& dy) {
    dx=dy=0;
    const auto place=[&](int icon,int px,int py){dx=px;dy=py;return icon;};
    switch(a) {
    case 'I':
        switch(b) {
        case 'W':return 0xe;          // weapon in hand
        case 'H':return 0xf;          // bare hands
        case 'A':return 9;
        case 'B':return 0xa;
        case 'C':return 0xb;
        case 'D':return 0xc;
        case 'E':return 0xd;
        case 'Z':return 0x27;         // any slash button
        default:return unsigned(b-'1')<9?b-'1':-1;   // numeric-keypad direction
        }
    case 'G':
        // Spirit emblem; the offset is applied even when the digit is invalid.
        dx=-1;dy=-2;
        return unsigned(b-'1')<9?b-0x21:-1;
    case 'L':return unsigned(b-'1')<2?place(b-0x12,0,5):-1;   // L1, L2
    case 'R':return unsigned(b-'1')<2?place(b-0x10,0,5):-1;   // R1, R2
    case 'S':
        if(b=='C')return 0x2d;
        if(b=='T')return place(0x1e,3,2);                     // START
        if(b=='L')return place(0x1d,3,4);                     // SELECT
        return -1;
    case 'B':
        if(b=='O')return place(0x19,2,3);
        if(b=='X')return place(0x1a,2,3);
        if(b=='T')return place(0x1c,2,3);
        if(b=='S')return place(0x1b,2,3);
        if(b=='P')return place(0x23,2,1);
        return -1;
    case 'O':return b=='R'?0x2a:-1;
    case 'P':return b=='L'?0x29:-1;
    default:return -1;
    }
}

size_t skillLayoutLine(const SkillListData& data,std::string_view text,size_t at,int x,int y,int size,bool plain,
                       const SkillUnlocks& unlocks,uint32_t colour,std::vector<SkillDraw>& out) {
    const auto byte=[&](size_t i){return i<text.size()?static_cast<unsigned char>(text[i]):0u;};
    const int advance=size==1?20:24;
    bool hidden=false;
    for(;;) {
        const unsigned a=byte(at);
        if(!a)return std::string_view::npos;
        const unsigned b=byte(at+1);
        if(!b)return std::string_view::npos;
        at+=2;
        if(a=='C'&&b=='R')return at;
        if(a=='M'&&b=='S'){if(!unlocks.matsuri)hidden=true;continue;}
        if(hidden)continue;
        if(a>=0x80) {
            out.push_back({SkillDraw::Glyph,int(a<<8|b),x,size==1?y+data.smallGlyphY:y,0,0,size,colour});
            x+=advance;
            continue;
        }
        // Every ASCII path that does not end in an icon steps back one byte,
        // so the second byte of the pair opens the next pair.
        if(a==' ') {
            out.push_back({SkillDraw::Ascii,0,x,y,0,0,size,colour});
            x+=advance>>1;--at;
            continue;
        }
        if(plain){--at;continue;}
        if(a=='E'&&b=='X') {
            out.push_back({SkillDraw::Ascii,1,x+data.iconX,y+data.exitY,0,0,size,colour});
            x+=2*advance+1;--at;
            continue;
        }
        int dx,dy;
        const int icon=skillIconCode(static_cast<unsigned char>(a),static_cast<unsigned char>(b),dx,dy);
        if(icon<0){--at;continue;}
        // 17e038 draws nothing for the "SC" icon while Matsuri is locked.
        const int width=icon==0x2d&&!unlocks.matsuri?0:data.icons[size_t(icon)].w;
        out.push_back({SkillDraw::Icon,icon,x+data.iconX+dx,y+dy,width,0,0,0});
        x+=width+dx+3;
    }
}

void skillPage(const SkillListData& data,int table,int first,int id,int x,int y,int scroll,int lines,int gap,
               const SkillUnlocks& unlocks,std::vector<SkillDraw>& out) {
    const auto& records=data.tables[size_t(table)];
    if(first<0)return;
    for(size_t r=size_t(first);r<records.size()&&(records[r].id==id||records[r].id==-1);++r) {
        const auto& rec=records[r];
        if(scroll<=0&&rec.type!=6) {
            out.push_back({SkillDraw::Bar,rec.type,data.barX,y+8,0x220,(rec.flags&8?4:0)+0x11,0,0});
            const auto icon=[&](int which,int px,int py) {
                const int width=which==0x2d&&!unlocks.matsuri?0:data.icons[size_t(which)].w;
                out.push_back({SkillDraw::Icon,which,px,py,width,0,0,0});
            };
            int left=0;
            if(rec.flags&2){icon(0xf,x-0x16,y+3);left=-0x16;}
            if(rec.flags&1){left-=0x16;icon(0xe,x+left,y+3);}
            if(rec.flags&4)icon(0x2d,x+0x208,y+2);
            int px=x+0x1fe;
            for(int bit=8;bit>=0;--bit) {
                if(!(rec.spirits>>bit&1))continue;
                if(bit==6?!unlocks.ma:bit==7?!unlocks.kemono:bit==8?!unlocks.matsuri:false)continue;
                px-=0x18;
                icon(0x10+bit,px,y);
            }
        }
        for(unsigned column=0;column<3;++column) {
            // A type-6 record shows its middle column only.
            const std::string_view text=rec.type==6&&column!=1?std::string_view():data.text(rec,column);
            if(text.empty())continue;
            for(size_t at=0;;) {
                size_t next;
                if(scroll>0){next=skillNextLine(text,at);--scroll;}
                else {
                    --lines;
                    if(column==0) {
                        // Name: two offset passes with icons, then the coloured
                        // pass, which skips every ASCII byte.
                        const uint32_t shadow=rgb(data.shadowColour[rec.type==1?0:1].data());
                        skillLayoutLine(data,text,at,x+1,y+1,2,false,unlocks,shadow,out);
                        skillLayoutLine(data,text,at,x+3,y+2,2,false,unlocks,shadow,out);
                        next=skillLayoutLine(data,text,at,x,y,2,true,unlocks,rgb(data.nameColour[rec.type].data()),out);
                    } else next=skillLayoutLine(data,text,at,x,y,1,false,unlocks,0xffffffffu,out);
                    y+=0x1b;
                }
                if(lines<=0)return;
                if(next==std::string_view::npos)break;
                at=next;
            }
        }
        if(scroll<=0){y+=gap;if(rec.flags&8)y-=0xe;}
    }
}

void fillCommonRows(ListWidget& list,const SkillListData& data,const SystemData& system,CommonRows& rows,int visibleRows) {
    list.selector.setFlag(MenuSelector::LargeText,true);
    std::fill(rows.begin(),rows.begin()+9,int16_t(-1));
    int count=1;
    for(int spirit=0;spirit<9;++spirit) {
        bool keep=true;
        if(spirit==6)keep=system.option(0x7f)!=0;
        // Kemono is also listed while any of the four animal fighters (2c..2f) is selectable.
        else if(spirit==7)keep=system.option(0x80)!=0||!system.option(0x42)||!system.option(0x43)||!system.option(0x44)||!system.option(0x45);
        else if(spirit==8)keep=system.option(0x7e)!=0;
        if(keep)rows[size_t(count++)]=int16_t(spirit);
    }
    list.resize(count,visibleRows);
    list.setItem(0,data.commonRows[0]);
    for(int row=1;row<count;++row)list.setItem(unsigned(row),data.commonRows[size_t(1+rows[size_t(row)])]);
    list.selector.setFlag(MenuSelector::MenuRows,true);
}
int commonSelection(const ListWidget& list,const CommonRows& rows) {
    const int cursor=list.selector.current;
    if(!list.selector.flag(MenuSelector::MenuRows))return cursor;
    return size_t(cursor)<rows.size()?rows[size_t(cursor)]+1:-1;
}

void SkillDetail::init(const SkillListData& tables) {
    *this=SkillDetail{};
    data=&tables;
    panel.reset(0,0,0,0,1);   // 17f308
    selector.init();
    selector.setFlag(MenuSelector::Wrap,false);
}
void SkillDetail::open(int categoryRow,int id) {
    if(category==categoryRow&&selection==id)return;
    category=categoryRow;selection=id;
    // Any other row keeps the previous record pointer.
    if(categoryRow==0||categoryRow==1){table=categoryRow;first=data->find(table,id);if(first<0)table=-1;}
    const int count=first<0?0:data->lines(table,first,id);
    // The cursor is the first visible line; the range leaves the last twelve on screen.
    selector.setRange(0,std::max(1,count-0xb),1,pageLines);
    selector.page=pageLines;   // stored after 20e028, also when it does not fit the range
    selector.setCursor(0);
    top=0;
}
int SkillDetail::update(const WidgetPad& pad,std::vector<int>& tones) {
    if(!shown||!active)return 0;
    const int code=selector.update(pad,tones);
    top=ListWidget::pageTop(code,visible,top,selector.max);
    top=ListWidget::followTop(selector.current,visible,top,selector.max);
    return code;
}
void SkillDetail::draw(const SkillUnlocks& unlocks,std::vector<SkillDraw>& out) const {
    if(drawn())skillPage(*data,table,first,selection,pageX,pageY,top,pageLines,recordGap,unlocks,out);
}

SkillListWindow::SkillListWindow(const SkillListData& data,const MenuWidgetData& widgets,const SystemData& system)
    :data_(data),widgets_(widgets),system_(system) {}
void SkillListWindow::enter(unsigned operatingSeat) {
    seat=operatingSeat;
    state=0;last=-1;dim=0;
    guide.init(widgets_);
    guide.setLayout(5,seat);
    list.init(widgets_,characterRows);
    list.selector.setFlag(MenuSelector::LargeText,true);
    list.fill(data_.categories,2);
    if(seat)list.panel.reset(0x34c,0x50,0x1bc,0x50,0x10);else list.panel.reset(-0x180,0x50,0x10,0x50,0x10);
    sub.init(widgets_,characterRows);
    sub.selector.setFlag(MenuSelector::LargeText,true);
    if(seat)sub.panel.reset(0x360,0x98,0x1d0,0x98,0x10);else sub.panel.reset(-0x180,0x98,0x10,0x98,0x10);
    detail.init(data_);
    detail.panel.reset(0,0,0,0,0x10);
}
SkillListWindow::Result SkillListWindow::tick(const WidgetPad& pad) {
    Result out;
    guide.tick();
    const int listCode=list.update(pad,out.tones);
    const int subCode=sub.update(pad,out.tones);
    const int detailCode=detail.update(pad,out.tones);
    if(state!=last) {
        switch(state) {
        case 0:
            list.panel.open();list.active=list.shown=1;
            sub.panel.close();sub.active=0;
            guide.open();
            guide.setMessage(0x29,list.selector.current);
            break;
        case 1:
            if(last<=0) {
                if(list.selector.current) {
                    sub.fillCharacters(system_,9,0,true,false,false);
                    // The operating fighter is preselected only over a battle scene.
                    if(!GuideWindow::menuBackdrop(gameMode))sub.select(listId);
                    if(seat==1){sub.panel.openX=0x158;sub.panel.closedX=0x2e8;}
                } else {
                    fillCommonRows(sub,data_,system_,commonRows,9);
                    sub.selector.setCursor(0);
                    sub.top=ListWidget::followTop(sub.selector.current,sub.visible,sub.top,sub.selector.max);
                    if(seat==1){sub.panel.openX=0x1d0;sub.panel.closedX=0x360;}
                }
                guide.setMessage(list.selector.current?0x2b:0x2a,0);
            }
            list.panel.open();list.active=0;list.shown=1;
            sub.panel.open();sub.shown=sub.active=1;
            guide.open();
            break;
        case 2:
            if(last<2)detail.open(list.selector.current,list.selector.current?sub.selected():commonSelection(sub,commonRows));
            list.panel.close();list.active=0;
            sub.panel.close();sub.active=0;
            guide.close();
            break;
        case -1:
            list.panel.close();list.active=0;
            sub.panel.close();sub.active=0;
            detail.panel.close();detail.active=0;
            guide.close();
            break;
        default:break;
        }
        detail.active=state==2;
        detail.shown=state>=2;
        last=state;
    } else {
        switch(last) {
        case 0:
            if(listCode==MenuSelector::Confirm)state=1;
            else if(listCode==MenuSelector::Cancel)state=-1;
            else if(listCode>=MenuSelector::Moved&&listCode<=MenuSelector::PageForward)guide.setMessage(0x29,list.selector.current);
            break;
        case 1:
            if(subCode==MenuSelector::Confirm)state=2;
            else if(subCode==MenuSelector::Cancel)state=0;
            break;
        case 2:
            if(detailCode==MenuSelector::Confirm||detailCode==MenuSelector::Cancel)state=1;
            break;
        case -1:
            if(list.panel.idle()) {
                // In a menu mode the scene is replaced and the task idles in
                // state -2; over a battle 1da7e8 suspends the task with state 0
                // pending, which reopens the list on the next wake.
                if(GuideWindow::menuBackdrop(gameMode)){out.event=LeaveScene;state=-2;}
                else {out.event=ReturnToPause;state=0;}
            }
            break;
        default:break;
        }
        if(state!=last)list.active=sub.active=detail.active=0;
    }
    dim=std::clamp(last<2?dim-8:dim+8,0,0xa0);
    return out;
}
SkillListWindow::Draw SkillListWindow::draw() const {
    Draw out;
    out.dim=dim;
    detail.draw(SkillUnlocks(system_),out.page);
    if(detail.drawn()&&detail.scrollBar()) {
        out.scrollBar=true;
        out.scrollX=detail.panel.x+0x268;out.scrollY=detail.panel.y+0x28;
        out.scrollTotal=detail.scrollTotal();out.scrollTop=detail.top;
    }
    return out;
}
}
