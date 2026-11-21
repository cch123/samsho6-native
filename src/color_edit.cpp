#include "color_edit.hpp"
#include <cstring>
#include <fstream>
#include <iterator>
#include <stdexcept>

namespace ss6 {
namespace {
using Event=ColorEditEvent;
constexpr size_t imageTable=SystemData::editData;  // 5735cc = image + 4
constexpr size_t palAllBytes=266240;

uint16_t get16(std::span<const uint8_t> bytes,size_t offset) {
    return uint16_t(bytes[offset]|bytes[offset+1]<<8);
}
void put16(std::span<uint8_t> bytes,size_t offset,uint16_t value) {
    bytes[offset]=uint8_t(value);bytes[offset+1]=uint8_t(value>>8);
}
// 17f528: page events move the window by one page before clamping.
int pageScroll(int event,int visible,int scroll,int rows) {
    int v=event==3?scroll+visible:event==2?scroll-visible:scroll;
    if(v<0)return 0;
    return rows-visible<v?rows-visible:v;
}
// 17f560: keep the cursor inside the window.
int followScroll(int cursor,int visible,int scroll,int rows) {
    int v=cursor<scroll?cursor:scroll;
    if(rows<v+visible)v=rows-visible;
    if(!(cursor<v+visible))v=cursor-visible+1;
    return v<0?0:v;
}
// Stored bank of a part (13c9bc, 13cbb8): 3 -> 2, weapon -> 1 except for
// character 25, whose weapon shares the body bank.
int storedBank(int character,int part) {
    return part==3?2:part==2?(character!=25?1:0):0;
}
uint32_t swatchWord(uint16_t v) {
    return 0xff000000u+(uint32_t(v>>10&0x1f)<<19)+(uint32_t(v)<<6&0xf800)+(uint32_t(v&0x1f)<<3);
}
}

ColorEditTables::ColorEditTables(const std::filesystem::path& assets) {
    std::ifstream in(assets/"color_edit.bin",std::ios::binary);
    const std::vector<uint8_t> raw((std::istreambuf_iterator<char>(in)),std::istreambuf_iterator<char>());
    if(raw.size()!=2364||std::memcmp(raw.data(),"CEDT\1\0\0\0",8))throw std::runtime_error("Unexpected color_edit.bin");
    const auto word=[&](size_t at){uint32_t v;std::memcpy(&v,raw.data()+at,4);return v;};
    std::memcpy(auxBank.data(),raw.data()+8,52);
    std::memcpy(order.data(),raw.data()+60,0x35);
    auxBias=int32_t(word(116));
    for(size_t i=0;i<24;++i)cacheSlots[i]=word(120+4*i);
    for(size_t i=0;i<51;++i) {
        const size_t at=216+0x24*i;
        preview[i].id=int32_t(word(at));
        for(size_t p=0;p<4;++p)preview[i].part[p]={int32_t(word(at+4+8*p)),int32_t(word(at+8+8*p))};
        weaponY[i]=int32_t(word(2052+4*i));
    }
    for(size_t i=0;i<27;++i){const uint32_t bits=word(2256+4*i);std::memcpy(&scalars[i],&bits,4);}
}
bool ColorEditTables::partExists(int character,int part) const {
    if(part<0||part>3)return true;
    return preview.at(size_t(character)).part[size_t(part)][0]!=-1;
}

EditPaletteSource resolveEditPaletteSource(const ColorEditTables& tables,uint32_t key,int bank) {
    using Table=EditPaletteSource::Table;
    const uint32_t owner=key>>16&3,k=key&0xffff;
    EditPaletteSource r;
    if(!owner) {
        r.table=Table::PalAll;r.group=k*32+uint32_t(bank);r.bank=bank;r.identity=k*32+uint32_t(bank)+0x10000;
        return r;
    }
    const int character=int(k/5),aux=tables.aux(character);
    // Character 33 owns two auxiliary banks (aux and aux + 1); both edit
    // the single stored bank 2 and share one cache identity.
    if(character==33?(bank==aux||bank==aux+1):(bank==aux&&bank>=3))bank=2;
    r.bank=bank;
    r.identity=k*32+uint32_t(bank)+(0x10000u<<owner);
    r.table=Table::PalAll;r.group=k*32+uint32_t(bank);
    if(bank<3) {
        if(key&0x40000){r.table=owner==1?Table::RuntimeP1:Table::RuntimeP2;r.group=k*3+uint32_t(bank);}
        else if(key&0x80000){r.table=owner==1?Table::NetworkP1:Table::NetworkP2;r.group=uint32_t(bank);}
        else {r.table=Table::SaveImage;r.group=k*3+uint32_t(bank);}
    }
    return r;
}
uint32_t selectedPaletteKey(unsigned side,unsigned character,unsigned button,bool edited) {
    return 0x40000u+character*5+button+(edited?(side?0x20000u:0x10000u):0u);
}

StandaloneEditPaletteCache::StandaloneEditPaletteCache(const ColorEditTables& tables,SystemData& data,std::span<uint8_t> palAll)
    :tables_(tables),data_(data),palAll_(palAll) {
    if(palAll.size()!=palAllBytes)throw std::runtime_error("Unexpected original palette arena");
    identity.fill(0xffffffff);
}
void StandaloneEditPaletteCache::reset() {identity.fill(0xffffffff);reference.fill(0);busy.fill(0);}
int StandaloneEditPaletteCache::resolve(uint32_t key,int bank) {
    const auto source=resolveEditPaletteSource(tables_,key,bank);
    for(size_t i=0;i<24;++i)if(!busy[i]&&identity[i]==source.identity){reference[i]=1;return int(tables_.cacheSlots[i]);}
    size_t slot=24;
    for(size_t i=0;i<24;++i)if(!busy[i]&&identity[i]==0xffffffff){slot=i;break;}
    if(slot==24)for(size_t i=0;i<24;++i)if(!busy[i]&&!reference[i]){slot=i;break;}
    if(slot==24)return -1;
    std::span<uint8_t> bytes;
    if(source.table==EditPaletteSource::Table::PalAll)bytes=palAll_;
    else if(source.table==EditPaletteSource::Table::SaveImage)bytes=std::span<uint8_t>(data_.image()).subspan(imageTable,0x6180);
    else throw std::runtime_error("Runtime and network palette tables are outside the standalone cache");
    const size_t at=size_t(source.group)*32;
    if(at+32>bytes.size())throw std::runtime_error("Palette group outside its table");
    // 115f08 clears the first colour in the SOURCE table before the copy,
    // so allocating an edited bank changes the save image itself.
    put16(bytes,at,0);
    const size_t row=tables_.cacheSlots[slot];
    for(size_t i=0;i<16;++i)colours[row*16+i]=get16(bytes,at+2*i);
    identity[slot]=source.identity;reference[slot]=1;
    return int(row);
}
void StandaloneEditPaletteCache::poke(int row,unsigned entry,uint16_t colour) {
    // A failed lookup (-1) makes 13ca58 store below the colour array; no
    // editor path exhausts the 24 entries, so that store is not modelled.
    if(row>=0&&row<32&&entry<16)colours[size_t(row)*16+entry]=colour;
}

EditPreviewPose colorEditSprite(const ColorEditTables& tables,int character,bool visible,int part,int colour,int x0) {
    const auto& k=tables.scalars;
    EditPreviewPose r;
    r.paletteKey=uint32_t(colour)+0x10000;
    if(!visible)return r;
    const int ch=character;
    const float half=float(x0)*k[1],base=half+k[2];
    float x=base,y=0;
    if(part==4) {
        if(ch==33)x=base+k[3];
        else if(ch==35||ch==37||ch==18||ch==21)x=base+k[4];
        else if(ch==24)x=base-k[5];
        else if(ch==19)x=base+k[5];
        else if(ch==27)x=base+k[6];
        else if(ch==13)x=base-k[7];
        else if(ch==43)x=base+k[5];
        else if(ch==48)x=base-k[7];
    } else if(part==2) {
        const float weapon=half+k[8];
        x=weapon;y=float(tables.weaponY.at(size_t(ch))+0x30);
        if(ch==27)x=weapon-k[5];
        else if(ch==26)x=weapon+k[6];
        else if(ch==29)x=weapon+k[9];
        else if(ch==34)x=weapon-k[5];
    } else if(part==3) {
        if(ch==11){x=half+k[8];y=k[10];}
        else if(ch==2||ch==16)y=k[10];
        else if(ch==32)x=base+k[11];
        else if(ch==33)x=base+k[12];
    } else if(part==1) {
        if(ch==15)x=base+k[4];
        else if(ch==35)x=base+k[5];
        else if(ch==22)x=base+k[12];
        else if(ch==25){x=base+k[4];y=k[10];}
        else if(ch==18)x=base+k[6];
        else if(ch==32)x=base+k[11];
        else if(ch==27)x=base+k[13];
        else if(ch==13)x=base+k[9];
        else if(ch==48)x=base-k[11];
    }
    if(part!=2&&ch==20)x+=k[14];
    else if(part!=2&&ch==43)x+=k[4];
    else if(ch==46||ch==47)x+=k[15];
    else if(ch==48)x+=k[3];
    r.x=x;r.y=y;
    if(part>=0&&part<4) {
        const auto& pose=tables.preview.at(size_t(ch)).part[size_t(part)];
        r.action=pose[0];r.record=pose[1]-1;
    } else {r.action=0x380;r.record=0;}
    r.hidden=r.action==-1;
    if(r.hidden)r.record=0;   // object+28 keeps its old value
    r.flip=ch==11&&part==3;
    return r;
}
EditPreviewPose colorEditCheckPose(const ColorEditTables& tables,int character,bool visible,int colour,int pose,int x0) {
    const auto& k=tables.scalars;
    EditPreviewPose r;
    r.paletteKey=uint32_t(colour)+0x10000;
    if(!visible)return r;
    const int ch=character;
    float x=float(x0)*k[17]+k[19]+k[18];
    if(pose==2) {
        r.action=0xe3;r.record=0;
        if(ch==17)x+=k[20];
    } else if(pose==1) {
        r.action=0x198;r.record=2;x-=k[21];
    } else {
        r.action=0xa4;r.record=0;
        if(ch==4)x+=k[22];
        else if(ch==5||ch==15||ch==25)x-=k[18];
        else if(ch==39)x+=k[23];
        else if(ch==2)x+=k[24];
        else if(ch==8)x+=k[18];
        else if(ch==19)x+=k[25];
    }
    r.hidden=false;r.x=x;r.y=0;
    return r;
}

void ColorEdit::Slide::configure(int ox,int oy,int ix,int iy,int frames) {
    inX=ix;inY=iy;duration=frames;outX=ox;outY=oy;
    targetX=x=startX=ox;targetY=y=startY=oy;remaining=0;state=1;
}
void ColorEdit::Slide::start(int tx,int ty) {
    remaining=duration;targetX=tx;targetY=ty;startX=x;startY=y;
    if(x==tx&&y==ty)remaining=0;
}
// 17f468 / 17f4b0 leave the retracted flag alone when the slide already
// aims at the requested end.
void ColorEdit::Slide::in() {
    if(targetX==inX&&targetY==inY)return;
    start(inX,inY);state=0;
}
void ColorEdit::Slide::out() {
    if(targetX==outX&&targetY==outY)return;
    start(outX,outY);state=1;
}
int ColorEdit::Slide::tick() {
    if(remaining>0) {
        const int r=--remaining;
        x=(startX*r+targetX*(duration-r))/duration;
        y=(startY*r+targetY*(duration-r))/duration;
        if(r>0)return 2;
    }
    return state==0?1:0;
}

void ColorEdit::List::range(int lo,int hi,int stride,int pageSize) {
    if(lo==hi)++hi;
    if(hi<lo)std::swap(lo,hi);
    min=lo;max=hi;step=stride?stride:1;page=pageSize<hi?pageSize:0;
    set(cursor);
}
void ColorEdit::List::set(int value) {
    if(value<min)cursor=(flags&4)?max-1:min;
    else if(value<max)cursor=value;
    else cursor=(flags&4)?min:max-1;
}
int ColorEdit::List::update(const ColorEditPad& pad,std::vector<ColorEditEvent>& events) {
    const auto sound=[&](int id){events.push_back({Event::Sound,id});};
    const int old=cursor;
    const uint32_t p=pad.pressed,r=pad.repeat;
    const bool confirm=((p&8)&&!(flags&0x20000))||(p&0x202);
    if(confirm) {
        if((flags&0x10)||rowDisabled(cursor)){if(!(flags&0x300))sound(0x24);return 6;}
        if(!(flags&0x300))sound(0);
        return 4;
    }
    if(p&0x404) {
        // A refused cancel tests mask 500, a refused confirm mask 300.
        if(flags&0x20){if(!(flags&0x500))sound(0x24);return 6;}
        if(!(flags&0x500))sound(0x24);
        return 5;
    }
    int d=0;
    if(flags&2)d=(r&0x40)?-step:(r&0x80)?step:0;
    if((flags&1)&&d==0)d=(r&0x10)?-step:(r&0x20)?step:0;
    if(flags&8)d=-d;
    if(flags&0x40000)d=0;
    const int n=old+d;
    cursor=n;
    if(n>=max)cursor=(flags&4)?min:max-1;
    else if(n<min)cursor=(flags&4)?max-1:min;
    if(cursor!=old){if(!(flags&0x80))sound(0x20);return 1;}
    if(page<0)return 0;
    // The shoulder keys sound even when the cursor is already at the end.
    int event=1;
    if(page>0&&(r&0x100000)) {
        if(!(flags&0x80))sound(0x20);
        cursor=std::max(0,cursor-page*step);event=2;
    } else if(page>0&&(r&0x400000)) {
        if(!(flags&0x80))sound(0x20);
        cursor=std::min(max-1,cursor+page*step);event=3;
    } else if(r&0x200000) {
        if(!(flags&0x80))sound(0x20);
        cursor=0;
    } else if(r&0x800000) {
        if(!(flags&0x80))sound(0x20);
        cursor=max-1;
    }
    return cursor!=old?event:0;
}

void ColorEdit::Panel::rows(int count,int shown) {
    list.flag(12,false);list.flag(13,false);
    if(count<=0)count=1;
    if(shown==-1||shown>=count)shown=count;
    visibleRows=shown;
    list.range(0,count,1,shown);
    list.set(list.cursor);
    scroll=followScroll(list.cursor,visibleRows,scroll,list.max);
}
int ColorEdit::Panel::update(const ColorEditPad& pad,std::vector<ColorEditEvent>& events,int scrollEvent) {
    const int moving=slide.tick();
    if(moving==0){visible=active=0;return 0;}
    if(moving!=1||!visible||!active)return 0;
    const int event=list.update(pad,events);
    scroll=pageScroll(scrollEvent<0?event:scrollEvent,visibleRows,scroll,list.max);
    scroll=followScroll(list.cursor,visibleRows,scroll,list.max);
    return event;
}

ColorEdit::ColorEdit(const ColorEditTables& tables,SystemData& data,std::span<const uint8_t> palAll,EditPaletteCache& cache)
    :tables_(tables),data_(data),palAll_(palAll),cache_(cache) {
    if(palAll.size()!=palAllBytes)throw std::runtime_error("Unexpected original palette arena");
    emit(Event::FrameKind,2);
    // 20eae0(A, 6, 0, 0, 0, 0): the 49 ordered fighters without Kuroko
    // (43) and without the fighters still locked in g_GameOption.
    characterMenu.list.flag(16,true);
    characterIds.fill(-1);
    int count=0;
    for(size_t i=0;i<0x31;++i) {
        const unsigned id=tables.order[i];
        if(id!=43&&!data.fighterLocked(id))characterIds[size_t(count++)]=int16_t(id);
    }
    characterMenu.rows(count,6);
    characterMenu.list.flag(13,true);
    characterMenu.slide.configure(-0x130,0x50,0x10,0x50,16);
    colourMenu.slide.configure(-0x130,0xec,0x10,0xec,16);
    colourMenu.list.flag(16,true);
    colourMenu.rows(5,5);
    copyMenu.slide.configure(0x2e4,0x82,0x1a4,0x82,16);
    copyMenu.list.flag(16,true);
    copyMenu.rows(2,5);
    partPanel.list.flag(0,false);partPanel.list.flag(1,true);
    partPanel.slide.configure(-0x130,0x30,0x10,0x30,16);
    swatchPanel.list.range(0,15,1,4);
    swatch.fill(0xffffffff);
    swatchPanel.list.flag(0,false);swatchPanel.list.flag(1,true);
    swatchPanel.slide.configure(0x280,0x30,0x140,0x30,16);
    sliderPanel.list.range(0,3,1,-1);
    valueList.range(0,0x20,1,8);
    valueList.flag(0,false);valueList.flag(1,true);valueList.flag(4,true);valueList.flag(5,true);
    sliderPanel.slide.configure(0x280,0xce,0x140,0xce,16);
    dialog.slide.configure(1,0,0,0,16);
    dialog.list.range(0,2,1,0);
    dialog.list.flag(0,false);dialog.list.flag(1,true);
    emit(Event::CameraInit);
    emit(Event::SpriteUnload);portraitEnabled=1;spriteLoaded=0;
    emit(Event::SpriteLoad,0);spriteLoaded=1;loadedCharacter=0;
    cache_.reset();emit(Event::CacheReset);
    emit(Event::PortraitSet,0);
    emit(Event::ObjectAction,0,3);
    emit(Event::ObjectPlace,1,0,0);
    emit(Event::ObjectAction,1,0);
    emit(Event::ObjectPlace,2,0,0);
    emit(Event::ObjectAction,2,0xa4);
}
int ColorEdit::character() const {
    const int cursor=characterMenu.list.cursor;
    return (characterMenu.list.flags&0x2000)?characterIds.at(size_t(cursor)):cursor;
}
uint32_t ColorEdit::sliderWord() const {
    return (uint32_t(field[0])<<19)|(uint32_t(field[2])<<3)|(uint32_t(field[1])<<11)|0xff000000u;
}
void ColorEdit::loadSlider(uint32_t word) {
    field={uint8_t((word>>16&0xff)>>3),uint8_t((word>>8&0xff)>>3),uint8_t((word&0xff)>>3)};
    backup=field;
    valueList.cursor=field[size_t(sliderPanel.list.cursor)];
}
int ColorEdit::sliderUpdate(const ColorEditPad& pad) {
    auto& s=sliderPanel;
    const int moving=s.slide.tick();
    if(moving==0){s.visible=s.active=0;return 0;}
    if(moving!=1||!s.visible||!s.active)return 0;
    const int event=s.list.update(pad,events_);
    const size_t channel=size_t(s.list.cursor);
    if(event==4){backup=field;return 4;}
    if(event==5){field=backup;return 5;}
    if(event>=1&&event<=3){valueList.cursor=field[channel];return 0;}
    // Confirm and cancel never reach the value list: the channel list
    // has already answered them.
    const int value=valueList.update(pad,events_);
    if(value>=1&&value<=3){field[channel]=uint8_t(valueList.cursor);return value;}
    return 0;
}
void ColorEdit::buildParts(int ch) {
    int rows=3+(tables_.partExists(ch,2)?1:0)+(tables_.partExists(ch,3)?1:0);
    partCharacter=ch;partRows=rows;
    partPanel.list.range(0,rows,1,0);
    partId={0,1,2,3,4};
    int n=2;
    if(tables_.partExists(ch,2))partId[size_t(n++)]=2;
    if(tables_.partExists(ch,3))partId[size_t(n++)]=3;
    // Every row but the last ("whole figure") can be confirmed.
    partPanel.list.flags|=0x800;
    for(int i=0;i<n;++i)partPanel.list.disabled&=~(1u<<i);
    partPanel.list.disabled|=1u<<n;
    partId[size_t(n)]=4;
    partPanel.list.set(0);
    partPanel.scroll=followScroll(partPanel.list.cursor,partPanel.visibleRows,partPanel.scroll,partPanel.list.max);
}
void ColorEdit::loadSwatches(int ch,int part,int colour) {
    if(!tables_.partExists(ch,part)||part==4){swatch.fill(0xff000000);return;}
    const auto table=std::span<const uint8_t>(data_.image()).subspan(imageTable,0x6180);
    const size_t base=size_t((ch*5+colour)*0x30+storedBank(ch,part)*16);
    for(size_t i=0;i<15;++i)swatch[i]=swatchWord(get16(table,(base+i+1)*2));
}
void ColorEdit::write(uint32_t word,int ch,int part,int index,int colour) {
    const uint16_t c=uint16_t(0x8000|(word>>9&0x7c00)|(word>>6&0x3e0)|((word&0xff)>>3));
    const int key=ch*5+colour;
    const int cacheBank=part==3?tables_.aux(ch)+tables_.auxBias:storedBank(ch,part);
    const auto table=std::span<uint8_t>(data_.image()).subspan(imageTable,0x6180);
    put16(table,size_t(key*0x30+storedBank(ch,part)*16+index+1)*2,c);
    cache_.poke(cache_.resolve(uint32_t(key)|0x10000,cacheBank),unsigned(index+1),c);
    // 13cb60: character 33's second auxiliary bank resolves to the same
    // stored bank, so this repeats the store into the same cache row.
    if(ch==33&&part==3)cache_.poke(cache_.resolve(uint32_t(colour+0xa5)|0x10000,cacheBank+1),unsigned(index+1),c);
}
void ColorEdit::restore(int ch,int part,int colour) {
    const int key=ch*5+colour;
    // 13cc18 reads the auxiliary byte unsigned; the dialog is reachable
    // only for parts that exist, which all have a real auxiliary bank.
    const int sourceBank=part==3?int(tables_.auxBank.at(size_t(ch)))+tables_.auxBias:storedBank(ch,part);
    const size_t source=size_t(key*512+sourceBank*16)*2,target=size_t(key*0x30+storedBank(ch,part)*16)*2;
    const auto table=std::span<uint8_t>(data_.image()).subspan(imageTable,0x6180);
    if(source+32>palAll_.size())throw std::runtime_error("Stock palette outside the arena");
    std::memcpy(table.data()+target,palAll_.data()+source,32);
    // 13cc8c: for character 33 the same sixteen stock colours are also
    // stored in the 16 entries after stored bank 2, i.e. over the BODY bank
    // of the next colour number (of character 34 for colour 4).
    if(ch==33&&part==3)std::memcpy(table.data()+target+32,palAll_.data()+source,32);
}
void ColorEdit::partHelp(int ch) {
    const int p=part();
    emit(Event::Help,0x25,(ch==11&&p==3)?2:p);
    // 13ccf0
    emit(Event::KeyHint,p==4?0:1);
    emit(p==4?Event::SecondHintHide:Event::SecondHintShow);
}
void ColorEdit::entry(int state,int ch) {
    auto& A=characterMenu;auto& B=colourMenu;auto& C=copyMenu;auto& P=partPanel;auto& R=swatchPanel;auto& S=sliderPanel;auto& D=dialog;
    const auto show=[](Panel& w,int active){w.slide.in();w.visible=1;w.active=active;};
    const auto hide=[](Panel& w){w.slide.out();w.active=0;};
    switch(state) {
    case -1:
        hide(A);emit(Event::FrameClose);
        break;
    case 0:
        portrait=1;emit(Event::FrameOpen);emit(Event::FrameKind,2);
        show(A,1);hide(B);
        if(cur_<state) {   // first entry only, not the return from the colour list
            cache_.reset();emit(Event::CacheReset);
            emit(Event::PortraitSet,ch);emit(Event::ObjectAction,0,4);
        }
        emit(Event::Help,0x23,0);
        break;
    case 1:
        emit(Event::FrameKind,2);portrait=1;emit(Event::FrameOpen);
        show(A,0);show(B,1);hide(P);hide(R);hide(S);
        emit(Event::SecondHintHide);
        if(state<cur_) {
            emit(Event::SpriteUnload);portraitEnabled=1;spriteLoaded=0;
            emit(Event::ObjectAction,0,4);
        }
        emit(Event::Help,0x24,0);
        break;
    case 2:
        emit(Event::FrameKind,3);emit(Event::FrameOpen);emit(Event::HeaderHide);emit(Event::SecondHint,0xb);
        show(P,1);show(R,0);show(S,0);hide(A);hide(B);hide(D);
        if(cur_<state) {
            cache_.reset();emit(Event::CacheReset);
            emit(Event::SpriteLoad,ch);spriteLoaded=1;loadedCharacter=ch;
            emit(Event::ObjectPlace,1,0xfa,0x3c);emit(Event::ObjectAction,1,0);
            emit(Event::ObjectPlace,2,0,0);emit(Event::ObjectAction,2,0xa4);
            buildParts(ch);
        }
        loadSwatches(ch,part(),colour());
        loadSlider(swatch[size_t(R.list.cursor)]);
        partHelp(ch);
        break;
    case 3:
        emit(Event::SecondHint,0xc);emit(Event::SecondHintShow);
        show(P,0);show(R,1);show(S,0);hide(C);
        if(state<cur_)loadSwatches(ch,part(),colour());
        loadSlider(swatch[size_t(R.list.cursor)]);
        emit(Event::Help,0x26,0);
        break;
    case 4:
        show(P,0);show(R,0);show(S,1);
        emit(Event::Help,0x27,0);emit(Event::SecondHintHide);
        break;
    case 5:
        emit(Event::SecondHint,0xd);emit(Event::SecondHintShow);
        show(C,1);show(P,0);show(R,0);show(S,0);
        emit(Event::Help,0x28,C.list.cursor);
        break;
    case 6:
        emit(Event::SecondHint,0xd);emit(Event::SecondHintShow);
        P.active=0;
        D.slide.in();D.visible=1;D.active=1;
        D.list.set(1);   // the dialog opens on "no"
        D.scroll=followScroll(D.list.cursor,D.visibleRows,D.scroll,D.list.max);
        break;
    default:break;
    }
}
void ColorEdit::update(int state,int ch,bool select,const std::array<int,7>& ev) {
    const auto moved=[](int e){return e>=1&&e<=3;};
    const auto apply=[&]{write(sliderWord(),ch,part(),swatchPanel.list.cursor,colour());};
    switch(state) {
    case -1:
        if(characterMenu.slide.settled()){emit(Event::AutoSave);next_=-2;emit(Event::SceneSwitch);}
        break;
    case 0:
        if(ev[0]==4)next_=1;
        else if(ev[0]==5)next_=-1;
        else if(moved(ev[0])){cache_.reset();emit(Event::CacheReset);emit(Event::PortraitSet,ch);emit(Event::ObjectAction,0,3);}
        break;
    case 1:
        if(ev[1]==4)next_=2;
        else if(ev[1]==5)next_=0;
        else if(moved(ev[1])){cache_.reset();emit(Event::CacheReset);}
        break;
    case 2:
        if(ev[3]==4)next_=3;
        else if(ev[3]==5)next_=1;
        else if(moved(ev[3])) {
            loadSwatches(ch,part(),colour());
            loadSlider(swatch[size_t(swatchPanel.list.cursor)]);
            partHelp(ch);
        } else if(select&&part()!=4&&tables_.partExists(ch,part()))next_=6;
        break;
    case 3:
        if(ev[4]==4)next_=4;
        else if(ev[4]==5)next_=2;
        else if(select)next_=5;
        else if(moved(ev[4]))loadSlider(swatch[size_t(swatchPanel.list.cursor)]);
        break;
    case 4:
        // Every slider step is stored at once; cancel stores the backup.
        if(ev[5]==4||ev[5]==5){next_=3;apply();}
        else if(moved(ev[5]))apply();
        break;
    case 5:
        if(ev[2]==4) {
            if(copyMenu.list.cursor==0)clipboard=sliderWord();
            else loadSlider((clipboard&0xffffff)+0xff000000u);
            next_=3;apply();
        } else if(ev[2]==5||select)next_=3;
        else if(moved(ev[2]))emit(Event::Help,0x28,copyMenu.list.cursor);
        break;
    case 6:
        if(ev[6]==4) {
            next_=2;
            restore(ch,part(),colour());
            // The swatch row is refreshed by the entry of state 2; here the
            // slider reloads from the not yet refreshed swatch.
            loadSlider(swatch[size_t(swatchPanel.list.cursor)]);
            cache_.reset();emit(Event::CacheReset);
        } else if(ev[6]==5||select)next_=2;
        break;
    default:break;
    }
}
const std::vector<ColorEditEvent>& ColorEdit::tick(const ColorEditPad& pad) {
    if(!first_)events_.clear();
    first_=false;
    std::array<int,7> ev{};
    ev[0]=characterMenu.update(pad,events_);
    ev[1]=colourMenu.update(pad,events_);
    ev[2]=copyMenu.update(pad,events_);
    ev[3]=partPanel.update(pad,events_);
    // 20f648 hands the seat number, not the list event, to 17f528; a seat
    // is never 2 or 3, so the swatch window is never paged.
    ev[4]=swatchPanel.update(pad,events_,0);
    ev[5]=sliderUpdate(pad);
    ev[6]=dialog.update(pad,events_);
    if(ev[6]==4&&dialog.list.cursor)ev[6]=5;   // 2129bc: confirming "no" is a cancel
    const int ch=character();
    const bool select=pad.pressed&0x80000;
    if(next_!=cur_) {
        // A state change consumes one visit: entry actions only.
        portrait=0;
        entry(next_,ch);
        cur_=next_;
    } else {
        update(cur_,ch,select,ev);
        if(next_!=cur_)for(Panel* w:{&characterMenu,&colourMenu,&copyMenu,&partPanel,&swatchPanel,&sliderPanel,&dialog})w->active=0;
    }
    const bool both=(pad.held&0xa00000)==0xa00000;
    preview.portraitVisible=portrait;preview.colour=colour();
    preview.part=part();preview.x0=partPanel.slide.x;
    preview.spriteVisible=partPanel.visible?!both:0;
    preview.poseVisible=partPanel.visible?both:0;
    preview.pose=(pad.held&0x100000)?1:(pad.held&0x400000)?2:0;
    highlight=cur_==5?copyMenu.list.cursor+1:0;
    return events_;
}
}
