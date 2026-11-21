#include "console_gallery.hpp"
#include <algorithm>
#include <cstring>
#include <stdexcept>

namespace ss6 {
namespace {
constexpr int topMenuDestructor=0x1d24f0,illustrationDestructor=0x13edb0,soundDestructor=0x13e0a8,
              endingDestructor=0x182a48,debugEndingDestructor=0x13f438;
template<class T> T read(std::span<const uint8_t> bytes,size_t& at) {
    if(at+sizeof(T)>bytes.size())throw std::runtime_error("Truncated console_gallery.bin");
    T v;std::memcpy(&v,bytes.data()+at,sizeof v);at+=sizeof v;return v;
}
std::vector<GalleryData::SoundRecord> records(std::span<const uint8_t> bytes) {
    std::vector<GalleryData::SoundRecord> out(bytes.size()/6);
    size_t at=0;
    for(auto& r:out){r.key=read<int16_t>(bytes,at);r.type=read<uint8_t>(bytes,at);++at;r.id=read<uint16_t>(bytes,at);}
    return out;
}
std::vector<GalleryData::LyricLine> lyricLines(std::span<const uint8_t> bytes) {
    size_t at=0;
    std::vector<GalleryData::LyricLine> out(read<uint32_t>(bytes,at));
    for(auto& line:out) {
        line.base=read<int32_t>(bytes,at);
        line.glyphs.resize(read<uint32_t>(bytes,at));
        for(auto& g:line.glyphs){g.code=read<uint16_t>(bytes,at);g.time=read<int32_t>(bytes,at);}
    }
    return out;
}
// 13dc50: leading records whose key is `key` or -1. The first record of a
// character block carries the character id, its continuation rows -1.
int leading(const std::vector<GalleryData::SoundRecord>& list,size_t from,int key) {
    int n=0;
    while(from+size_t(n)<list.size()&&(list[from+size_t(n)].key==key||list[from+size_t(n)].key==-1))++n;
    return n;
}
std::string_view label(const std::vector<std::string>& table,int index) {
    return size_t(index)<table.size()?std::string_view(table[size_t(index)]):std::string_view();
}
void flush(std::vector<int>& tones,std::vector<GalleryEvent>& events) {
    for(int tone:tones)events.push_back({GalleryEvent::Tone,-1,tone,0});
    tones.clear();
}
// 1822a0 runs the menu background setup again in every gallery sub-scene
// (17ea48 is 1 for modes 13/14): one library RNG draw, counters cleared.
void resetBackground(MenuChrome& chrome,GameRandom& random) {
    chrome.enter(int(random.nextLibrary()));
}
}

GalleryData::GalleryData(const std::filesystem::path& assets) {
    const AssetSections file(assets/"console_gallery.bin");
    topLabels=file.strings("TOPL");topHelp=file.strings("TOPH");
    const auto scroll=file.section("TOPS");
    topHelpScroll.assign(scroll.begin(),scroll.end());
    extraIllustrations=file.strings("ILEX");
    categories=file.strings("SCAT");bgmVersions=file.strings("SBGM");languages=file.strings("SNAR");
    common=file.strings("SCOM").at(0);endingHelp=file.strings("ENDH").at(0);lyricKeys=file.strings("LYRK").at(0);
    bgmLabels=file.strings("LBGM");voiceLabels=file.strings("LVOI");
    effectLabels=file.strings("LSE_");narrationLabels=file.strings("LNAR");
    commonSounds=records(file.section("RCOM"));bgm=records(file.section("RBGM"));
    narration=records(file.section("RNAR"));characterSounds=records(file.section("RCHR"));
    lyrics={lyricLines(file.section("LYR0")),lyricLines(file.section("LYR1"))};
    if(topLabels.size()!=4||topHelp.size()!=4||topHelpScroll.size()!=4||extraIllustrations.size()!=6
       ||categories.size()!=3||bgmVersions.size()!=2||languages.size()!=2)
        throw std::runtime_error("Invalid console_gallery.bin");
}

void GalleryTopMenu::enter(const GalleryData& data,MenuChrome& chrome,GameRandom& random) {
    events.clear();
    chrome.enter(int(random.nextLibrary()));
    leaving=0;
    chrome.setHelp(int(data.topHelp[size_t(row)].size()));
    events.push_back({GalleryEvent::EffectsStop,0,0,0});
}
void GalleryTopMenu::leave() {
    events.push_back({GalleryEvent::GameDataReset,0,0,0});
    events.push_back({GalleryEvent::Scene,topMenuDestructor,int(GalleryScene::Title),0});
    leaving=1;
}
void GalleryTopMenu::tick(const GalleryData& data,MenuChrome& chrome,const std::array<MenuPad,2>& pads) {
    events.clear();
    for(unsigned s=0;s<2;++s) {
        // 1d28e8. Both pads are polled; a request by seat 0 masks seat 1 in
        // the same visit through the latch.
        unsigned command=0;
        if(chrome.inputReady()&&!leaving) {
            if(pads[s].pressed&0x404)command=8;
            if(pads[s].pressed&0x20a)command|=4;
            if(pads[s].repeat&0x10)command|=1;
            if(pads[s].repeat&0x20)command|=2;
        }
        if(command&3) {
            row=(row+(command&1?3:1))%4;
            chrome.setHelp(int(data.topHelp[size_t(row)].size()));
            events.push_back({GalleryEvent::Tone,-1,0x20,0});
        } else if(command&8) {
            leave();
            events.push_back({GalleryEvent::Tone,-1,0x25,0});
        } else if(command&4) {
            static constexpr GalleryScene next[]{GalleryScene::Ending,GalleryScene::SoundTest,GalleryScene::Illustrations};
            if(row==3)leave();
            else if(row>=0&&row<3) {
                events.push_back({GalleryEvent::Scene,topMenuDestructor,int(next[row]),0});
                leaving=1;
            }
            operatingSeat=s==1;   // 178f70, after every confirm including EXIT
            events.push_back({GalleryEvent::Tone,-1,0,0});
        }
    }
    chrome.advance();
    alpha=chrome.contentAlpha();
    const bool scroll=data.topHelpScroll[size_t(row)]==1;
    const int length=int(data.topHelp[size_t(row)].size());
    helpX[0]=chrome.helpPosition(data.topHelpScroll[size_t(row)]==1,length,0);
    if(scroll)helpX[1]=chrome.helpPosition(true,length,1);
}

void IllustrationViewer::enter(unsigned operatingSeat,const SystemData& system,const MenuWidgetData& widgets,
                               const GalleryData& data,MenuChrome& chrome,GameRandom& random) {
    events.clear();
    seat=operatingSeat;state=0;previous=-1;
    hideUi=0;centreX=0x140;centreY=0xe0;size=0x1b8;
    resetBackground(chrome,random);
    guide.init(widgets);
    guide.setLayout(8,seat);
    list.init(widgets,rows);
    list.selector.setFlag(MenuSelector::LargeText,true);
    list.fillCharacters(system,9,0,false,true,false);
    characterRows=list.count();
    for(const auto& name:data.extraIllustrations)list.append(name);
    if(seat)list.panel.reset(0x2ea,0x50,0x15a,0x50,0x10);
    else list.panel.reset(-0x180,0x50,0x10,0x50,0x10);
}
int IllustrationViewer::imageId() const {
    const int row=list.selector.current;
    return row<characterRows?list.selected():row-characterRows+0x31;
}
void IllustrationViewer::tick(const WidgetPad& pad) {
    events.clear();
    std::vector<int> tones;
    guide.tick();
    const int code=list.update(pad,tones);
    flush(tones,events);
    if(state!=previous) {
        if(state==0) {
            guide.open();guide.setLayout(8,seat);guide.setMessage(0x37,0);
            list.panel.open();list.active=list.shown=1;
        } else if(state==1) {
            if(previous<=0){hideUi=0;centreX=0x140;centreY=0xe0;size=0x1b8;}
            guide.open();guide.setLayout(9,seat);guide.setMessage(0x38,0);
            list.panel.close();list.active=0;
        } else if(state==-1) {
            list.panel.close();list.active=0;guide.close();
        }
        previous=state;
        return;
    }
    const bool reset=(pad.pressed&0x202)||(pad.pressed&8);
    const bool back=pad.pressed&0x404;
    if(previous==0) {
        if(code==MenuSelector::Confirm)state=1;
        else if(code==MenuSelector::Cancel)state=-1;
    } else if(previous==-1) {
        if(list.panel.idle()) {
            events.push_back({GalleryEvent::Scene,illustrationDestructor,int(GalleryScene::TopMenu),0});
            state=-2;
        }
    } else if(previous==1) {
        if(reset) {
            centreX=0x140;centreY=0xe0;size=0x1b8;
            events.push_back({GalleryEvent::Tone,-1,0,0});
        } else if(back) {
            events.push_back({GalleryEvent::Tone,-1,0x24,0});
            state=0;
        } else {
            // The picture moves against the pressed direction, faster when enlarged.
            const int step=size/0xa0+4;
            if(pad.held&0x80)centreX-=step;else if(pad.held&0x40)centreX+=step;
            if(pad.held&0x20)centreY-=step;else if(pad.held&0x10)centreY+=step;
            // Clamp with the size of this visit, before the zoom below.
            const int half=size/2;
            if(centreX+half<0x80)centreX=0x80-half;
            else if(centreX-half>=0x201)centreX=half+0x200;
            if(centreY+half<0x80)centreY=0x80-half;
            else if(centreY-half>=0x141)centreY=half+0x140;
            if(pad.held&0x100000)size=std::min(size+8,0x708);
            else if(pad.held&0x400000)size=std::max(size-8,0x1b8);
            if(pad.pressed&0x80000)hideUi=!hideUi;
        }
    }
    if(state!=previous)list.active=0;
}

void SoundTest::enter(unsigned operatingSeat,const SystemData& system,const MenuWidgetData& widgets,
                      const GalleryData& data,MenuChrome& chrome,GameRandom& random) {
    events.clear();
    system_=&system;data_=&data;
    seat=operatingSeat;state=0;previous=-1;
    lyricAlpha=lyricCounter=lyricDrawCounter=0;lyricSet=-1;
    resetBackground(chrome,random);
    guide.init(widgets);
    guide.setLayout(6,seat);
    static constexpr int panels[2][3][4]{
        {{-0x180,0x50,0x10,0x50},{-0x180,0xae,0x10,0xae},{0x2d0,0x50,0x140,0x50}},
        {{0x34c,0x50,0x1bc,0x50},{0x2f8,0xae,0x168,0xae},{-0x180,0x50,0x10,0x50}}};
    for(unsigned i=0;i<3;++i) {
        lists[i].init(widgets,rows);
        lists[i].selector.setFlag(MenuSelector::LargeText,true);
        if(i==0)lists[0].fill(data.categories,3);
        const auto& p=panels[seat?1:0][i];
        lists[i].panel.reset(p[0],p[1],p[2],p[3],0x10);
    }
    // The track list confirms silently so the menu tone does not mask the sample.
    lists[2].selector.setFlag(MenuSelector::SilentConfirm,true);
}
void SoundTest::fillSecond(int category) {
    auto& second=lists[1];
    int openX=0x1d4,closedX=0x364;
    if(category==0)second.fill(data_->bgmVersions,2);
    else if(category==1) {
        second.fillCharacters(*system_,8,0,false,true,false);
        second.append(data_->common);
        openX=0x15a;closedX=0x2ea;
    } else if(category==2)second.fill(data_->languages,2);
    if(seat==1&&category>=0&&category<3){second.panel.openX=openX;second.panel.closedX=closedX;}
    second.select(0);
    events.push_back({GalleryEvent::MusicStop,0,0,0});
}
void SoundTest::fillTracks(int category,int character,bool commonRow) {
    auto& tracks=lists[2];
    const auto visible=[](int n){return n<0xb?n:0xa;};
    int openX=0,closedX=0;
    if(category==0) {
        const int n=leading(data_->bgm,0,0);
        tracks.resize(n,visible(n));
        for(int i=0;i<n;++i) {
            tracks.setItem(unsigned(i),label(data_->bgmLabels,i));
            const auto& r=data_->bgm[size_t(i)];
            // Type 1 tracks are requested with flag 0; +64 carries that to play().
            ids[size_t(i)]=int16_t(r.type==1?r.id+0x64:r.id);
        }
        openX=0xa8;closedX=-0xe8;
    } else if(category==1) {
        const std::vector<GalleryData::SoundRecord>* list=&data_->commonSounds;
        size_t from=0;
        int n,rowCount;
        if(commonRow) {
            events.push_back({GalleryEvent::LoadBank,0,0,0});
            n=rowCount=leading(*list,0,0);
        } else {
            events.push_back({GalleryEvent::LoadBank,0,character,0});
            events.push_back({GalleryEvent::LoadBank,1,character<0x14?0x33:0x34,0});
            list=&data_->characterSounds;
            // 13dc18 scans for the block header without a bound.
            while(from<list->size()&&(*list)[from].key!=character)++from;
            n=leading(*list,from,character);
            rowCount=character!=0x2b?n+1:n;
        }
        tracks.resize(rowCount,visible(rowCount));
        int k=0;
        if(!commonRow&&character!=0x2b) {
            // Row 0 of a character is the name call 1e7ba0, not a list record.
            ids[0]=-1;tracks.setItem(0,label(data_->voiceLabels,0));k=1;
        }
        for(int i=0;i<n;++i)
            if((*list)[from+size_t(i)].type==0) {
                tracks.setItem(unsigned(k),label(data_->voiceLabels,k));
                ids[size_t(k++)]=int16_t((*list)[from+size_t(i)].id);
            }
        for(int i=0,j=0;i<n;++i)
            if((*list)[from+size_t(i)].type==1) {
                tracks.setItem(unsigned(k+j),label(data_->effectLabels,j));
                ids[size_t(k+j)]=int16_t((*list)[from+size_t(i)].id);++j;
            }
        openX=0x86;closedX=-0x10a;
    } else if(category==2) {
        const int n=leading(data_->narration,0,0);
        tracks.resize(n,visible(n));
        for(int i=0;i<n;++i) {
            tracks.setItem(unsigned(i),label(data_->narrationLabels,i));
            ids[size_t(i)]=int16_t(data_->narration[size_t(i)].id);
        }
        openX=0x40;closedX=-0x150;
    }
    if(seat==1&&category>=0&&category<3){tracks.panel.openX=openX;tracks.panel.closedX=closedX;}
    tracks.selector.setCursor(0);
    tracks.top=ListWidget::followTop(tracks.selector.current,tracks.visible,tracks.top,tracks.count());
}
void SoundTest::play(int category,int second,int character,bool commonRow) {
    const int row=lists[2].selector.current;
    const int id=ids[size_t(row)];
    if(category==0) {
        // 43d056 is overwritten for the request and restored afterwards.
        events.push_back({GalleryEvent::Music,id>=0x64?id-0x64:id,id>=0x64?0:1,second!=0});
        musicRequested_=true;
        lyricCounter=0;
        if(row==5){lyricSet=second;guide.setMessage(0x30,category);}
        else {lyricSet=-1;guide.setMessage(0x2d,category);}
    } else if(category==1) {
        if(id==-1)events.push_back({GalleryEvent::BankTone,1,character<0x14?character+3:character-0x14,0});
        else events.push_back({GalleryEvent::BattleSound,0,id,commonRow?0:character});
    } else if(category==2) {
        const int language=second!=0;
        if(unsigned(id-2)<0x2a)events.push_back({GalleryEvent::LoadBank,0,id-2,0});
        else events.push_back({GalleryEvent::NarrationCheck,0,0,language});
        events.push_back({GalleryEvent::Voice,0x31,id,language});
    }
}
bool SoundTest::lyricWrap() const {
    if(!lyricAlpha)return false;
    return (lyricSet==0&&lyricCounter>=0x33ae)||(lyricSet==1&&lyricCounter>=0x23c8);
}
void SoundTest::tick(const WidgetPad& pad,bool streamPlaying) {
    events.clear();
    musicRequested_=false;
    std::vector<int> tones;
    auto& first=lists[0];auto& second=lists[1];auto& tracks=lists[2];
    guide.tick();
    // All three lists run every visit; only the active one reads the pad.
    const int code1=first.update(pad,tones);
    const int code2=second.update(pad,tones);
    const int sel2=second.selector.current,category=first.selector.current;
    const int character=second.selected();
    const bool commonRow=sel2==second.count()-1;
    tracks.selector.setFlag(MenuSelector::Locked,false);
    const int code3=tracks.update(pad,tones);
    flush(tones,events);
    if(state!=previous) {
        switch(state) {
        case -1:
            first.panel.close();second.panel.close();first.active=second.active=0;guide.close();
            break;
        case 0:
            guide.open();first.panel.open();first.active=first.shown=1;
            second.panel.close();second.active=0;tracks.panel.close();tracks.active=0;
            guide.setMessage(0x2c,category);
            break;
        case 1:
            if(previous<state)fillSecond(category);
            guide.setMessage(0x2d,category);guide.open();
            first.active=0;second.panel.open();second.active=second.shown=1;
            tracks.panel.close();tracks.active=0;
            break;
        case 2:
            if(previous<state) {
                lyricAlpha=0;lyricSet=-1;
                fillTracks(category,character,commonRow);
                guide.setMessage(0x2d,category);
            }
            guide.open();first.panel.open();first.shown=1;second.panel.open();second.shown=1;
            first.active=second.active=0;tracks.panel.open();tracks.active=tracks.shown=1;
            break;
        case 3:
            guide.close();first.panel.close();second.panel.close();first.active=second.active=0;
            tracks.panel.close();tracks.active=0;
            break;
        }
        previous=state;
    } else {
        switch(previous) {
        case -1:
            if(first.panel.idle()) {
                events.push_back({GalleryEvent::NarrationLoad,0,0,system_->setting(5)});
                state=-2;
                events.push_back({GalleryEvent::Scene,soundDestructor,int(GalleryScene::TopMenu),0});
            }
            break;
        case 0:
            if(code1==MenuSelector::Confirm)state=1;
            else if(code1==MenuSelector::Cancel)state=-1;
            else if(unsigned(code1-1)<3)guide.setMessage(0x2c,category);
            break;
        case 1:
            if(code2==MenuSelector::Confirm)state=2;
            else if(code2==MenuSelector::Cancel)state=0;
            break;
        case 2:
            if(code3==MenuSelector::Confirm)play(category,sel2,character,commonRow);
            else if(code3==MenuSelector::Cancel)state=1;
            else if((pad.pressed&0x80000)&&lyricSet!=-1) {
                events.push_back({GalleryEvent::Tone,-1,0,0});state=3;
            }
            break;
        case 3:
            if(lyricAlpha>=0xff&&(pad.pressed&0x8060e)) {
                events.push_back({GalleryEvent::Tone,-1,0,0});state=2;
            }
            break;
        }
        if(state!=previous)first.active=second.active=tracks.active=0;
    }
    // 214060 ends in 213d80, which clears the stream word 5a9e6c at once:
    // the visit that requests a track always restarts the counter.
    lyricCounter=streamPlaying&&!musicRequested_?lyricCounter+1:0;
    lyricAlpha=std::clamp(lyricAlpha+(previous==3?8:-8),0,0xff);
    // The overlay is drawn before the wrap test clears the counter.
    lyricDrawCounter=lyricCounter;
    if(lyricWrap())lyricCounter=0;
}
std::vector<SoundTest::LyricDraw> SoundTest::lyricGlyphs() const {
    std::vector<LyricDraw> out;
    if(!lyricAlpha||(lyricSet!=0&&lyricSet!=1))return out;
    const auto& lines=data_->lyrics[size_t(lyricSet)];
    int x=lyricSet?0x1e0:0x230;
    const int gap=lyricSet?0x48:0x14;
    for(size_t l=0;l<lines.size();++l) {
        const auto& glyphs=lines[l].glyphs;
        int y=0x48;
        for(size_t g=0;g<glyphs.size();++g,y+=0x12) {
            const int start=lines[l].base+glyphs[g].time;
            // The last glyph of a line has no successor time: its end is 0.
            const int end=g+1<glyphs.size()?lines[l].base+glyphs[g+1].time:0;
            int r=0x20,gr=0x10,b=0x10;
            if(lyricDrawCounter>=start) {
                if(end<lyricDrawCounter){r=0x30;gr=0x40;b=0x60;}
                else {
                    const int duration=end-start,half=duration/2,elapsed=lyricDrawCounter-start;
                    if(duration<=0)r=gr=b=0;
                    else if(elapsed<half){r=0xff;gr=b=0;}
                    else {
                        const int d=duration-half,e=elapsed-half;
                        gr=b=(e*64/d)&0xff;
                        r=((d-e)*0xcf/d+0x30)&0xff;
                    }
                }
            }
            out.push_back({glyphs[g].code,x,y,uint8_t(r),uint8_t(gr),uint8_t(b)});
        }
        x-=0x1a;
        if((l+1)%7==0)x-=gap;
    }
    return out;
}

void EndingViewer::enterScene(const GalleryData& data,MenuChrome& chrome,GameRandom& random) {
    events.clear();
    character=0;chosen=false;
    chrome.enter(int(random.nextLibrary()));
    chrome.setHelp(int(data.endingHelp.size()));
}
void EndingViewer::beginSelection(unsigned operatingSeat,const SystemData& system,const MenuWidgetData& widgets,
                                  MenuChrome& chrome,GameRandom& random) {
    events.clear();
    seat=operatingSeat;state=0;previous=-1;countdown=0x10;chosen=false;
    resetBackground(chrome,random);
    guide.init(widgets);
    guide.setLayout(0xa,seat);
    list.init(widgets,rows);
    list.selector.setFlag(MenuSelector::LargeText,true);
    list.fillCharacters(system,9,0,false,false,true);
    if(seat)list.panel.reset(0x2ea,0x50,0x15a,0x50,0x10);
    else list.panel.reset(-0x180,0x50,0x10,0x50,0x10);
    list.select(character);
}
void EndingViewer::tick(const WidgetPad& pad) {
    events.clear();
    if(chosen)return;
    std::vector<int> tones;
    guide.tick();
    const int code=list.update(pad,tones);
    flush(tones,events);
    events.push_back({GalleryEvent::MusicStop,0,0,0});   // 13f58c: requested on every visit
    if(state!=previous) {
        if(state==-1){list.panel.close();list.active=0;guide.close();}
        else if(state==0) {
            guide.open();guide.setLayout(0xa,seat);guide.setMessage(0x39,0);
            list.panel.open();list.shown=list.active=1;
        }
        previous=state;
    } else {
        if(state==-1) {
            if(list.panel.idle()) {
                events.push_back({GalleryEvent::Scene,fromGallery?endingDestructor:debugEndingDestructor,
                                  int(GalleryScene::TopMenu),0});
                state=-2;
            }
        } else if(state==0) {
            if(code==MenuSelector::Confirm) {
                const int id=list.selected();
                // With no ending seen the list is one "UNDEFINED" row whose id
                // is -1; the original then calls the null pointer at 4eefe4
                // (ending table index -1). The native port ignores the confirm.
                if(id>=0) {
                    character=id;chosen=true;
                    events.push_back({GalleryEvent::EndingChosen,id,0,0});
                    return;   // 13f4a8 returns before its draw and yield
                }
            } else if(code==MenuSelector::Cancel)state=-1;
        }
        if(state!=previous)list.active=0;
    }
    if(countdown>0&&--countdown==0)events.push_back({GalleryEvent::MusicStop,0,0,0});
}
}
