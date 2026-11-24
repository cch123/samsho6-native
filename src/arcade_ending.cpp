#include "asset_files.hpp"
#include "arcade_ending.hpp"
#include "motion.hpp"
#include "system_data.hpp"

#include <algorithm>
#include <bit>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <numeric>
#include <stdexcept>
#include <string>

namespace ss6 {
inline namespace arcade_scene {
namespace {
constexpr int width=640,height=480;
constexpr uint32_t hidden=0x400000;

std::vector<uint8_t> load(const std::filesystem::path& file,size_t size=0) {
    std::ifstream in(resolveAsset(file),std::ios::binary|std::ios::ate);
    if(!in||(size&&in.tellg()!=static_cast<std::streamoff>(size)))
        throw std::runtime_error("Invalid ending resource: "+file.string());
    std::vector<uint8_t> bytes(static_cast<size_t>(in.tellg()));
    in.seekg(0);
    if(!in.read(reinterpret_cast<char*>(bytes.data()),std::streamsize(bytes.size())))
        throw std::runtime_error("Truncated ending resource: "+file.string());
    return bytes;
}
uint32_t word(const std::vector<uint8_t>& b,size_t at) {
    if(at+4>b.size())throw std::runtime_error("Ending asset is truncated");
    return uint32_t(b[at])|uint32_t(b[at+1])<<8|uint32_t(b[at+2])<<16|uint32_t(b[at+3])<<24;
}
int16_t half(const uint8_t* p) {return int16_t(uint16_t(p[0]|p[1]<<8));}
float real(uint32_t v) {return std::bit_cast<float>(v);}
uint32_t bits(float v) {return std::bit_cast<uint32_t>(v);}
int32_t sw(uint32_t v) {return std::bit_cast<int32_t>(v);}
// 120660..120690: the low product word, then an arithmetic shift.
int32_t scaled(uint32_t value,uint32_t delta) {return sw(value*delta)>>8;}
// Characters 113028 hands to 1130f8 / 1131d8: every byte below 0x80 except
// the line feed, and every two-byte code.
template<class F> void cells(std::string_view text,F&& each) {
    for(size_t i=0;i<text.size();++i) {
        const unsigned c=uint8_t(text[i]);
        if(c==0x0a){each(std::string_view(),true);continue;}
        if(c<0x80){each(text.substr(i,1),false);continue;}
        if(i+1>=text.size())break;
        each(text.substr(i,2),false);++i;
    }
}
std::string name(const char* format,int n) {
    char buffer[32];std::snprintf(buffer,sizeof buffer,format,n);return buffer;
}
void mix(uint8_t* dst,const int* source) {
    // Cd + ((Cs - Cd) * As >> 7), arithmetic shift, clamped.
    for(int c=0;c<3;++c) {
        const int d=dst[c],v=d+(((source[c]-d)*source[3])>>7);
        dst[c]=uint8_t(std::clamp(v,0,255));
    }
}
int floorDiv(int a,int b) {int q=a/b;if((a%b)&&((a<0)!=(b<0)))--q;return q;}
}

// ---------------------------------------------------------------------------
EndingData::EndingData(const std::filesystem::path& assets) {
    const auto data=load(assets/"arcade_ending.bin");
    if(data.size()<20||std::memcmp(data.data(),"AED1",4)||word(data,4)!=1||word(data,8)!=scriptCount)
        throw std::runtime_error("Invalid arcade_ending.bin");
    const size_t count=word(data,12),pool=word(data,16);
    size_t at=20;
    directory_.resize(scriptCount);
    for(auto& d:directory_)for(auto& v:d){v=word(data,at);at+=4;}
    records_.resize(count);
    for(auto& r:records_) {
        const auto op=word(data,at);
        if(op>=uint32_t(EndingOp::Count))throw std::runtime_error("Invalid ending opcode");
        r.op=EndingOp(op);
        for(unsigned i=0;i<6;++i)r.a[i]=word(data,at+4+4*i);
        at+=28;
    }
    for(const auto& d:directory_)if(size_t(d[0])+d[1]>count)throw std::runtime_error("Invalid ending script directory");
    if(at+pool>data.size())throw std::runtime_error("Ending asset is truncated");
    strings_.assign(data.begin()+std::ptrdiff_t(at),data.begin()+std::ptrdiff_t(at+pool));
    if(strings_.empty()||strings_.back())throw std::runtime_error("Invalid ending string pool");
    at+=pool;at+=(4-at%4)%4;
    for(auto& v:portrait){v=real(word(data,at));at+=4;}
    for(auto& v:background){v=real(word(data,at));at+=4;}
    for(auto& v:flash){v=real(word(data,at));at+=4;}
    for(auto& row:balloons)for(auto& v:row){v=sw(word(data,at));at+=4;}
    for(auto& row:pictures)for(auto& v:row){v=sw(word(data,at));at+=4;}
    for(auto& v:glyphColours){v=word(data,at);at+=4;}
    objectScale_=word(data,at);at+=4;
    if(at!=data.size())throw std::runtime_error("Unexpected arcade_ending.bin size");
    aid_=load(assets/"aid_99a.bin",0x1800);
    act_=load(assets/"act_99a.bin");
    if(act_.size()%60)throw std::runtime_error("Invalid act_99a.bin");
}
std::span<const EndingRecord> EndingData::script(unsigned index) const {
    const auto& d=directory_.at(index);
    return {records_.data()+d[0],d[1]};
}
std::string_view EndingData::text(uint32_t offset) const {
    if(offset>=strings_.size())throw std::out_of_range("Ending string offset");
    return std::string_view(strings_.data()+offset);
}
const uint8_t* EndingData::record(unsigned action,int step) const {
    // 1212c0: signed AID start plus the step, 60 bytes per record.
    if(action>=0x800)throw std::out_of_range("Ending ACT action");
    const int index=half(aid_.data()+2*action)+step;
    if(index<0||size_t(index+1)*60>act_.size())throw std::out_of_range("Ending ACT record");
    return act_.data()+size_t(index)*60;
}

// ---------------------------------------------------------------------------
void EndingFade::beginFrame() {
    blank=false;
    if(flash>0){--flash;blank=true;}
    if(level==0x100&&(mode&2))blank=true;
}
bool EndingFade::endFrame() {
    const bool quad=blank;
    blank=false;        // 113bc8, delay slot of the 116588 call
    // 116b9c: the level moves by the step and stops at 3ebf1c / 3ebf20.
    level+=step;
    if(step>0&&ceiling<level)level=ceiling;
    if(step<0&&level<floor)level=floor;
    return quad;
}
void EndingFade::reset() {
    tones.fill(0);
    ceiling=0x100;colour=0;level=step=0;floor=flash=0;blank=false;
}

// ---------------------------------------------------------------------------
void EndingPlayback::begin(Mode mode,unsigned script,int colour,bool gallery,bool alternateText) {
    mode_=mode;script_=script;colour_=colour;gallery_=gallery;
    program_.clear();
    const auto records=data_->script(script);
    if(mode==Mode::StaffRoll||!alternateText)program_.assign(records.begin(),records.end());
    if(mode==Mode::Playback) {
        // 182ba4: 1a1830(0, 4); 1a1740(0x40).
        program_.push_back({EndingOp::FadeOut,{0,4}});
        program_.push_back({EndingOp::Wait,{0x40}});
    }
    pc_=0;block_=Block::None;skipped_=false;started_=false;
}
void EndingPlayback::beginFrame() {
    fade.beginFrame();
    frame=EndingFrame{};
    // The dispatcher 112838 lists the tasks before it runs any: a picture task
    // created or killed by this visit changes the next frame, not this one.
    frame.picture=picture;frame.pictureHalf=pictureHalf;frame.pictureBlank=frame.blank=fade.blank;
    frame.pictureFadeMode=fade.mode;frame.pictureFadeLevel=fade.level;frame.pictureFadeColour=fade.colour;
    frame.reveal=reveal;frame.glyphStart=glyphs;
}
void EndingPlayback::endFrame() {
    frame.camera=camera;frame.cameraOffset=cameraOffset;
    frame.flashColour=fade.colour;
    frame.fade=fade;
    frame.flash=fade.endFrame();
}
bool EndingPlayback::tick(uint32_t pressed,bool locked,uint32_t delta,std::vector<EndingEvent>& events) {
    beginFrame();
    const bool finished=visit(pressed,locked,delta,events);
    endFrame();
    return finished;
}
void EndingPlayback::idle(uint32_t delta,std::vector<EndingEvent>& events) {
    portraits();
    // 1a2158 also moves the camera by 4efa90 / 4efa94 here.
    camera[0]+=float(cameraDelta[0]);camera[1]+=float(cameraDelta[1]);
    stepObjects(delta,events);
}
void EndingPlayback::resetObjects(std::vector<EndingEvent>& events) {
    // 182858: only the first word of object 0 and the eight flag words are written.
    objects[0][0]=0;
    for(auto& o:objects)o[0x38/4]=hidden;
    events.push_back({EndingEvent::PaletteReset});
    events.push_back({EndingEvent::TextColours,int32_t(data_->glyphColours[0]),int32_t(data_->glyphColours[1])});
}
void EndingPlayback::finish(std::vector<EndingEvent>& events) {
    block_=Block::None;pc_=program_.size();
    if(mode_!=Mode::Playback)return;
    // 182bb8: also the longjmp target of the skip.
    fade.reset();
    portrait={-1,-1};
    resetObjects(events);
    reveal=-1;
    picture=false;events.push_back({EndingEvent::BackgroundClear});
    events.push_back({EndingEvent::MusicStop});
    if(gallery_)events.push_back({EndingEvent::MenuBackdrop,galleryRow()});
}
bool EndingPlayback::visit(uint32_t pressed,bool locked,uint32_t delta,std::vector<EndingEvent>& events) {
    if(!started_) {
        started_=true;
        if(mode_==Mode::Playback) {
            // 182a98 entry. 3ebf18, 3d3aa0, the camera and the picture task are left alone.
            fade.reset();
            portrait={-1,-1};
            resetObjects(events);
        }
    } else if(block_!=Block::None) {
        // Behind the yield inside 1a2218: the abort test, then the loop condition.
        if(!locked) {
            bool abort=false;
            if(gallery_) {
                if(pressed&0x404){events.push_back({EndingEvent::Sound,-1,0x25});abort=true;}
            } else if(pressed&8)abort=true;
            if(abort) {
                // longjmp(4efb40): to 182bb8 for the playback, to 182e18 for the staff roll.
                skipped_=true;
                finish(events);
                return true;
            }
        }
        bool more=false;
        switch(block_) {
        case Block::Wait:more=counter_!=0;break;
        case Block::Message:more=hold_>0;break;
        case Block::RollShow:more=limit_>0;break;
        case Block::RollScroll:more=counter_<total_;break;
        default:break;
        }
        if(more){iterate(pressed,locked,delta,events);return false;}
        block_=Block::None;
    }
    while(pc_<program_.size()) {
        const auto& r=program_[pc_++];
        const int n=sw(r.a[0]);
        switch(r.op) {
        case EndingOp::Wait:case EndingOp::WaitB:
            if(n<=0)continue;
            counter_=n;block_=Block::Wait;break;
        case EndingOp::MessageShow:
            renderer_=n;hold_=0xb4;counter_=0;block_=Block::Message;break;
        case EndingOp::RollShow:
            origin_=0xf2-14*int(roll.size());
            if(n<=0)continue;
            limit_=n;counter_=0;block_=Block::RollShow;break;
        case EndingOp::RollScroll:
            hold_=int(roll.size())*0x1c+0x10;total_=hold_+n;
            reveal=-1;
            if(total_<=0)continue;
            counter_=0;block_=Block::RollScroll;break;
        default:execute(r,events);continue;
        }
        iterate(pressed,locked,delta,events);
        return false;
    }
    finish(events);
    return true;
}
void EndingPlayback::portraits() {
    frame.portraits=true;frame.portrait=portrait;frame.blank=fade.blank;
}
void EndingPlayback::iterate(uint32_t pressed,bool locked,uint32_t delta,std::vector<EndingEvent>& events) {
    portraits();
    frame.lines.clear();frame.balloon=0;
    switch(block_) {
    case Block::Wait:--counter_;break;
    case Block::Message: {
        reveal=counter_/4;++counter_;
        const bool done=page(renderer_);
        if(done)--hold_;
        // 1a1b7c: any of 0x707 completes the page, or ends a complete one.
        if(!locked&&(pressed&0x707)) {
            if(done)hold_=0;
            else counter_=0x2710;
        }
        break;
    }
    case Block::RollShow: {
        // 1a2048: the hold only runs once the previous frame drew every glyph it was allowed.
        const int previous=glyphs,r=counter_/4;
        glyphs=0;
        if(previous<r)--limit_;
        ++counter_;reveal=r;
        frame.reveal=reveal;frame.glyphStart=0;
        for(size_t i=0;i<roll.size();++i) {
            const auto text=data_->text(roll[i]);
            line(roll[i],0x140-6*int(text.size()),origin_+0x1c*int(i));
        }
        break;
    }
    case Block::RollScroll: {
        frame.reveal=reveal;frame.glyphStart=glyphs;
        int y=-std::min(hold_,counter_);
        for(size_t i=0;i<roll.size();++i,y+=0x1c) {
            // 1a1f6c: only lines whose top lies in (-0x1f7, 0] below the bottom edge.
            if(uint32_t(y+0x1f7)>=0x1f7)continue;
            const auto text=data_->text(roll[i]);
            line(roll[i],0x140-6*int(text.size()),y+0x1e0);
        }
        ++counter_;
        break;
    }
    default:break;
    }
    // 1a2158.
    camera[0]+=float(cameraDelta[0]);camera[1]+=float(cameraDelta[1]);
    stepObjects(delta,events);
}
void EndingPlayback::line(uint32_t text,int x,int y) {
    frame.lines.push_back({text,x,y});
    if(frame.blank)return;       // 1130f8 / 1131d8 return before counting
    cells(data_->text(text),[&](std::string_view,bool feed) {
        if(feed)return;
        if(reveal>=0&&glyphs>=reveal)return;
        ++glyphs;
    });
}
bool layoutEndingPage(const EndingData& data,int renderer,std::span<const uint32_t> message,int balloon,
                      int leftPortrait,int reveal,bool blank,EndingFrame& frame) {
    frame.lines.clear();frame.balloon=0;frame.reveal=reveal;frame.glyphStart=0;
    const int limit=renderer==3||renderer==4?3:4;
    const int n=std::min(int(message.size()),limit);
    int x=0x2b,y=0,pitch=0x1c;
    bool centred=false;
    switch(renderer) {
    case 1:x=leftPortrait<0x34?0xd5:0x2b;y=(4-n)*14+0x36;break;      // 1a2468
    case 2:y=(4-n)*14+0x126;break;                                    // 1a2540
    case 5:y=(4-n)*14+0xc8;break;                                     // 1a25f0
    case 3: {                                                          // 1a26b0
        int id=balloon;
        if(id>=6)id-=5;
        if(id<0||id>=int(data.balloons.size()))throw std::out_of_range("Ending balloon id");
        const auto& r=data.balloons[size_t(id)];
        frame.balloon=balloon;
        x=r[7]+r[1];y=r[8]+r[2]+(3-n)*14;pitch=0x18;
        break;
    }
    case 4:y=(3-n)*0xc+0x16e;pitch=0x18;centred=true;break;            // 1a2870
    default:return false;                                              // 1a1c38: no renderer, never complete
    }
    int glyphs=0;
    for(int i=0;i<n;++i) {
        const auto text=data.text(message[size_t(i)]);
        frame.lines.push_back({message[size_t(i)],centred?0x140-6*int(text.size()):x,y+pitch*i});
        if(blank)continue;
        cells(text,[&](std::string_view,bool feed) {
            if(!feed&&!(reveal>=0&&glyphs>=reveal))++glyphs;
        });
    }
    frame.glyphEnd=glyphs;
    return glyphs<reveal;
}
bool EndingPlayback::page(int renderer) {
    const bool done=layoutEndingPage(*data_,renderer,message,balloon,portrait[0],reveal,frame.blank,frame);
    // Renderers 1..5 clear 3d3ab0; an unknown renderer leaves it.
    if(renderer>=1&&renderer<=5)glyphs=frame.glyphEnd;
    return done;
}
void EndingPlayback::loadBackground(int id,std::vector<EndingEvent>& events) {
    if(id<0xc) {
        // 50e080[id]: battle stage loader; 50e04c = 0.
        events.push_back({EndingEvent::BackgroundStage,id});
        return;
    }
    int file,part;
    if(id<0x64){file=(id-0xc)/2+1;part=(id-0xc)&1;}
    else {
        if(id-0x64>=int(data_->pictures.size()))throw std::out_of_range("Ending background id");
        file=data_->pictures[size_t(id-0x64)][0];part=data_->pictures[size_t(id-0x64)][1];
    }
    if(picture)throw std::logic_error("Second ending picture task");
    picture=true;pictureHalf=part&1;
    events.push_back({EndingEvent::BackgroundPicture,file,part});
}
void EndingPlayback::execute(const EndingRecord& r,std::vector<EndingEvent>& events) {
    const auto& a=r.a;
    const auto object=[&]()->EndingObject& {return objects.at(a[0]);};
    switch(r.op) {
    case EndingOp::Background:loadBackground(sw(a[0]),events);break;
    case EndingOp::BackgroundSwitch:
        picture=false;events.push_back({EndingEvent::BackgroundClear});
        loadBackground(sw(a[0]),events);break;
    case EndingOp::Camera:camera={real(a[0]),real(a[1]),real(a[2])};break;
    case EndingOp::CameraOffset:cameraOffset={real(a[0]),real(a[1]),real(a[2])};break;
    case EndingOp::ObjectStart: {
        // 120378 -> 1202e8, 120d10.
        auto& o=object();
        const uint32_t bank=a[1];
        o[0xc0/4]=0;
        o[0x38/4]=a[5]|0x10000000u;o[0x34/4]=0;
        o[0x40/4]=bits(float(sw(a[3])));o[0x44/4]=bits(float(sw(a[4])));
        o[0x1c/4]=bank*5;o[0x24/4]=bank*32+(a[2]&0x1f);
        o[0x70/4]=data_->objectScale();o[0x30/4]=0x100;
        o[0xc/4]=o[0x10/4]=0;o[0x14/4]=bank;
        o[0x20/4]=o[0x28/4]=o[0x2c/4]=0;
        for(unsigned i=0x4c;i<=0x60;i+=4)o[i/4]=0;
        enterRecord(o,events);
        break;
    }
    case EndingOp::ObjectAction: {
        // 120390 with resource 99 bound (46a9a0 == 0x63) and object+0xcc != 0xb.
        auto& o=object();
        o[0x24/4]=o[0x14/4]*32+a[1];
        o[0x38/4]|=0x10000000u;
        o[0x28/4]=o[0x2c/4]=o[0x3c/4]=o[0xc0/4]=0;
        enterRecord(o,events);
        break;
    }
    case EndingOp::ObjectVelocity:object()[0x50/4]=a[1];object()[0x5c/4]=a[2];break;
    case EndingOp::ObjectColour: {
        auto& o=object();
        o[0x38/4]|=0x1800000u;o[0x8c/4]=a[1];o[0x90/4]=a[2];o[0x98/4]=a[3];o[0xa0/4]=a[4];o[0xa8/4]=a[5];
        break;
    }
    case EndingOp::ObjectPalette: {
        auto& o=object();
        o[0x1c/4]=o[0x14/4]*5+uint32_t(colour_);
        break;
    }
    case EndingOp::Music:events.push_back({EndingEvent::Music,sw(a[0]),sw(a[1])});break;
    case EndingOp::Sound:events.push_back({EndingEvent::Sound,sw(a[0]),sw(a[1])});break;
    case EndingOp::CameraDelta:cameraDelta={sw(a[0]),sw(a[1])};break;
    case EndingOp::TextColours:events.push_back({EndingEvent::TextColours,sw(a[0]),sw(a[1])});break;
    case EndingOp::Portrait: {
        if(a[0]!=1&&a[0]!=2)break;
        const unsigned side=a[0]-1;
        const int32_t old=portrait[side];
        portrait[side]=sw(a[1]);
        // 1a1958: a new texture only for 0..0x30 and only when the id changes.
        if(a[1]<0x31&&sw(a[1])!=old)events.push_back({EndingEvent::Portrait,int32_t(side),sw(a[1])});
        break;
    }
    case EndingOp::MessageClear:message.clear();break;
    case EndingOp::MessageAdd:
        if(message.size()>=4)throw std::logic_error("Ending message list overflow");
        message.push_back(a[0]);break;
    case EndingOp::FadeIn:fade.mode=2;fade.level=0x100;fade.colour=a[0];fade.step=-sw(a[1]);break;
    case EndingOp::FadeOut:fade.mode=2;fade.level=0;fade.colour=a[0];fade.step=sw(a[1]);break;
    case EndingOp::Flash:fade.colour=a[0];fade.flash=sw(a[1]);break;
    case EndingOp::RollClear:roll.clear();break;
    case EndingOp::RollAdd:
        if(roll.size()>=32)throw std::logic_error("Ending roll list overflow");
        roll.push_back(a[0]);break;
    case EndingOp::FadeWrite:fade.colour=a[0];fade.level=std::clamp(sw(a[1]),0,0x100);fade.step=0;break;
    case EndingOp::FadeMode:fade.mode=sw(a[0]);break;
    case EndingOp::FadeRange: {
        const int first=sw(a[0]),end=std::min(first+sw(a[1]),0x400);
        for(int i=std::max(first,0);i<end;++i)fade.tones[size_t(i)]=uint16_t(a[2]);
        break;
    }
    case EndingOp::PaletteBake:events.push_back({EndingEvent::PaletteBake,sw(a[0]),sw(a[1]),fade.colour,uint32_t(fade.level)});break;
    case EndingOp::PaletteSave:events.push_back({EndingEvent::PaletteSave});break;
    case EndingOp::ObjectStore:
        if(a[1]%4||a[1]>=0x138)throw std::logic_error("Ending object store");
        object()[a[1]/4]=a[2];break;
    default:throw std::logic_error("Ending opcode outside execute");
    }
}
void EndingPlayback::enterRecord(EndingObject& o,std::vector<EndingEvent>& events) {
    // 120d10 for object+0xcc < 2.
    if(o[0xcc/4]>=2)throw std::runtime_error("Ending object kind is not ported");
    const uint32_t action=o[0x24/4];
    bool mute=action==0x188||action==0x189||action==0x18e||action==0x18f;
    const uint8_t* rec=data_->record(action,sw(o[0x28/4]));
    const uint32_t header=uint32_t(rec[0])|uint32_t(rec[1])<<8|uint32_t(rec[2])<<16|uint32_t(rec[3])<<24;
    o[0x3c/4]=0;o[0xd8/4]=rec[2];
    if(header&0x1000)o[0xfc/4]|=0x100000u;else o[0xfc/4]&=~0x100000u;   // halfword +0xfe, bit 0x10
    o[0x104/4]&=~0x18000u;
    if(header&0x400)throw std::runtime_error("Ending ACT attachment is not ported");
    const int cmd=half(rec+0x38);
    if(cmd==0x4000)mute=true;
    if(cmd&&!(o[0x104/4]&0x200)&&!mute&&((o[0x38/4]&0x10000000u)||!(cmd&0x8000))) {
        if(cmd&0x4000)throw std::runtime_error("Ending ACT retained voice is not ported");
        events.push_back({EndingEvent::ObjectSound,sw(o[0xc/4]),cmd,o[0x14/4]});   // 1e8298
    }
    if(o[0x38/4]&0x2000000u)return;              // 120f10: velocity-driven objects ignore ACT motion
    if(header&0x800)o[0xfc/4]|=0x800000u;
    const uint32_t f104=o[0x104/4];
    if(f104&0x40)return;
    if(o[0xc0/4]&&!(f104&1))return;
    if(f104&0xc00)throw std::runtime_error("Ending ACT velocity scale is not ported");
    MotionCommand command;
    command.kind=half(rec+0x20);
    for(unsigned i=0;i<6;++i)command.values[i]=half(rec+0x22+2*i);
    if(command.kind==2||command.kind==4||command.kind==6||command.kind==8||command.kind==0x10||command.kind==0x12)
        o[0xfc/4]|=0x800000u;
    MotionState m{sw(o[0x4c/4]),sw(o[0x50/4]),sw(o[0x54/4]),sw(o[0x58/4]),sw(o[0x5c/4]),sw(o[0x60/4]),0,0};
    enterMotion(m,command,(o[0x108/4]&0x200)!=0,(f104&0x80)!=0);
    o[0x4c/4]=uint32_t(m.dx);o[0x50/4]=uint32_t(m.vx);o[0x54/4]=uint32_t(m.ax);
    o[0x58/4]=uint32_t(m.dy);o[0x5c/4]=uint32_t(m.vy);o[0x60/4]=uint32_t(m.ay);
}
void EndingPlayback::stepObjects(uint32_t delta,std::vector<EndingEvent>& events) {
    for(auto& o:objects) {
        if(o[0x38/4]&hidden)continue;
        // 120618.
        const uint32_t flags=o[0x38/4];
        if(!(o[0x104/4]&0x20)) {
            if(flags&0x2000000u) {
                o[0x40/4]=bits(real(o[0x40/4])+float(scaled(o[0x50/4],delta)));
                o[0x44/4]=bits(real(o[0x44/4])+float(scaled(o[0x5c/4],delta)));
            } else {
                const uint32_t vx=o[0x50/4],vy=o[0x5c/4];
                o[0x4c/4]+=uint32_t(scaled(vx,delta));o[0x58/4]+=uint32_t(scaled(vy,delta));
                o[0x50/4]=vx+uint32_t(scaled(o[0x54/4],delta));o[0x5c/4]=vy+uint32_t(scaled(o[0x60/4],delta));
            }
        }
        if(o[0xc8/4]==1)throw std::runtime_error("Ending object position commit is not ported");
        if(flags&0x1000000u) {
            // 121308: per-channel colour steps, each clamped to 0..255.
            const uint32_t c=o[0x8c/4];
            const auto channel=[&](unsigned shift,uint32_t step) {return uint32_t(std::clamp(int((c>>shift)&255)+sw(step),0,255))<<shift;};
            o[0x8c/4]=channel(24,o[0x90/4])|channel(16,o[0x98/4])|channel(8,o[0xa0/4])|channel(0,o[0xa8/4]);
        }
        // 120880 -> 1207e8.
        if(!(o[0x104/4]&2)) {
            frame.objects.push_back(o);
            frame.objects.back()[78]=frame.objects.back()[79]=0;
        }
        // 120ac8.
        const uint32_t action=o[0x24/4];
        const int32_t step=sw(o[0x28/4]);
        const uint8_t* rec=data_->record(action,step);
        const int32_t time=sw(o[0x2c/4]+delta);
        o[0x2c/4]=uint32_t(time);
        if(time<int32_t(half(rec+0x34))*256)continue;
        const uint32_t header=uint32_t(rec[0])|uint32_t(rec[1])<<8;
        if(header&0x4000) {
            // 120b40: a landing record waits until the truncated height plus the pending step is not above ground.
            const float y=float(int32_t(real(o[0x44/4]))),dy=float(sw(o[0x58/4])>>16);
            const float next=(flags&0x40000u)?y-dy:y+dy;
            if(int32_t(next)>0)continue;
            o[0x3c/4]|=0x100;o[0x44/4]=0;o[0x58/4]=o[0x5c/4]=o[0x60/4]=0;
        }
        o[0x2c/4]&=0xff;
        int32_t next=step+1;
        o[0x28/4]=uint32_t(next);
        const int32_t count=int32_t(data_->records(action));
        if(next>=count) {
            if(header&0x8000)throw std::runtime_error("Ending ACT jump is not ported");
            const int kind=half(rec+0x3a);
            o[0xc0/4]=1;
            if(kind==2) {
                next=0;o[0x28/4]=0;o[0x38/4]=flags&0xefffffffu;
            } else {
                next=count-1;o[0x28/4]=uint32_t(next);
                o[0x3c/4]=(o[0x3c/4]&~0xffu)|uint32_t(kind);
            }
        }
        if(next!=step)enterRecord(o,events);
    }
}

// ---------------------------------------------------------------------------
void ArcadeEnding::enter(ArcadeRun& run,bool alternateText) {
    run.game.challengerInhibit=1;     // 182980: g+30
    phase=Phase::Entry;alternateText_=alternateText;nameEntryRuns_=false;nameCommitted=false;
    nameEntry=ArcadeNameEntry{};
    events.clear();
}
void ArcadeEnding::leave(ArcadeRun& run) {
    run.game.challengerInhibit=0;
    run.resetScore();
    run.clearStartHold();
}
void ArcadeEnding::tick(ArcadeRun& run,std::array<uint32_t,2> pressed,uint32_t delta) {
    events.clear();nameCommitted=false;
    playback.beginFrame();
    // Task 1c9928 (tag 1775) was created by the first coroutine visit, so the
    // dispatcher runs it from the second frame on.
    if(nameEntryRuns_&&nameEntry.tick(run,pressed[seat])){nameEntryRuns_=false;nameCommitted=true;}
    bool created=false;
    switch(phase) {
    case Phase::Entry: {
        seat=run.game.mode==1?0u:1u;
        const auto& player=run.players[seat];
        // 182de4 / 182df0: clear records in g_GameOption.
        run.system().option(size_t(0x81+player.spirit))=1;
        run.system().option(size_t(0x47+player.character))=1;
        created=nameEntry.begin(run);                                   // 1c9830
        colour_=player.colour;
        playback.begin(EndingPlayback::Mode::Playback,unsigned(player.character),player.colour,false,alternateText_);
        phase=Phase::Playback;
        [[fallthrough]];
    }
    case Phase::Playback:
        if(!playback.visit(pressed[seat],nameEntry.active,delta,events))break;
        // 182dfc: 112a70(fa1); 1e7ad0().
        playback.picture=false;events.push_back({EndingEvent::BackgroundClear});
        events.push_back({EndingEvent::MusicStop});
        // 182e0c: 19c1c8 under a fresh setjmp, unless the alternate text version is selected.
        if(alternateText_){exit(run,delta);break;}
        playback.begin(EndingPlayback::Mode::StaffRoll,EndingData::staffRoll,colour_,false,false);
        phase=Phase::StaffRoll;
        [[fallthrough]];
    case Phase::StaffRoll:
        if(playback.visit(pressed[seat],nameEntry.active,delta,events))exit(run,delta);
        break;
    case Phase::Leaving:
        playback.idle(delta,events);
        break;
    }
    if(created)nameEntryRuns_=true;
    playback.endFrame();
}

void ArcadeEnding::exit(ArcadeRun& run,uint32_t delta) {
    // 182e34: 112a70(fa1); 1e7ad0(); g+34 = 1; 1252f0(1, 1, 182a48, 138340); then 1a2118 / 1a2158 for ever.
    playback.picture=false;events.push_back({EndingEvent::BackgroundClear});
    events.push_back({EndingEvent::MusicStop});
    run.game.levelEnding=1;
    run.request(1,1,0x182a48,ArcadeScene::GameOver);
    events.push_back({EndingEvent::Exit,1,1,0x182a48,uint32_t(ArcadeScene::GameOver)});
    phase=Phase::Leaving;
    playback.idle(delta,events);
}

// ---------------------------------------------------------------------------
EndingArt::EndingArt(std::filesystem::path assets):assets_(std::move(assets)) {rebuild();}
void EndingArt::apply(const EndingEvent& e) {
    switch(e.kind) {
    case EndingEvent::BackgroundPicture: {
        picture_=load(assets_/name("ed_bg%02d.tex",e.a),1024*1024);
        const auto pal=load(assets_/name("ed_bg%02d.pal",e.a),512);
        // 1a4b90: 116478(0x200, count, data) after clearing the first colour.
        for(unsigned i=0;i<256;++i)source[0x200+i]=i?uint16_t(pal[2*i]|pal[2*i+1]<<8):uint16_t(0);
        break;
    }
    case EndingEvent::Portrait: {
        const unsigned side=unsigned(e.a)&1;
        portrait_[side]=load(assets_/name("demo_%02d.tex",e.b),256*256);
        const auto pal=load(assets_/name("demo_%02d.pal",e.b),512);
        // 1a19c0 / 1a1a80: 116478(0xc0 | 0x1c0, 0x40, data + 0x180).
        for(unsigned i=0;i<0x40;++i)source[(side?0x1c0u:0xc0u)+i]=uint16_t(pal[0x180+2*i]|pal[0x181+2*i]<<8);
        break;
    }
    case EndingEvent::PaletteBake: {
        // 1174b8: the current fade is written into the source table.
        const int level=int(e.d),rest=0x100-level;
        const int r=int((e.c>>19)&31)*level,g=int((e.c>>11)&31)*level,b=int((e.c>>3)&31)*level;
        for(int i=std::max(e.a,0);i<std::min(e.a+e.b,0x400);++i) {
            const int v=source[size_t(i)];
            const int nr=((v>>10)&31)*rest+r,ng=((v>>5)&31)*rest+g,nb=(v&31)*rest+b;
            source[size_t(i)]=v&0x8000?uint16_t(((nr<<2)&0x7c00)+((ng>>3)&0x3e0)+((nb>>8)&0x1f))|0x8000:uint16_t(0);
        }
        break;
    }
    case EndingEvent::PaletteSave:saved=source;break;
    default:return;
    }
    rebuild();
}
void EndingArt::setFade(const EndingFade& fade) {fade_=fade;rebuild();}
void EndingArt::rebuild() {
    // 116588 for 16-bit entries: tone = (3ebf30[i] | 3ebf18), bit 1 ignored at level 0;
    // bits 0 / 2 select the grey ramp, bit 1 the interpolation toward 3ec730.
    const uint32_t mask=fade_.level?0xffffffffu:~2u;
    for(unsigned i=0;i<1024;++i) {
        auto& out=colours_[i];out={};
        const unsigned v=source[i];
        if(!(v&0x8000))continue;
        const uint32_t mode=(fade_.tones[i]|uint32_t(fade_.mode))&mask;
        int c[3]={int((v>>10)&31),int((v>>5)&31),int(v&31)};
        if(mode&5)c[0]=c[1]=c[2]=(c[0]*10+c[1]*16+c[2]*6)>>5;
        if(mode&2)for(int k=0;k<3;++k)
            c[k]=((c[k]*(256-fade_.level)+int((fade_.colour>>(19-8*k))&31)*fade_.level)>>8)&31;
        for(int k=0;k<3;++k)out[size_t(k)]=uint8_t(c[k]<<3);
        out[3]=128;
    }
}
void EndingArt::rasterise(const MenuCanvas& canvas,const MenuDrawList& list,std::span<uint8_t> rgba) const {
    if(rgba.size()!=size_t(width)*height*4)throw std::invalid_argument("Expected a 640x480 ending surface");
    std::vector<unsigned> order(list.records.size());
    std::iota(order.begin(),order.end(),0u);
    std::stable_sort(order.begin(),order.end(),[&](unsigned a,unsigned b) {return list.records[a].z<list.records[b].z;});
    MenuDrawList pending;
    const auto flush=[&] {
        if(pending.records.empty())return;
        canvas.rasterise(pending,rgba);pending.records.clear();
    };
    const auto integral=[](float value) {
        if(value!=std::floor(value)||std::abs(value)>32768)throw std::invalid_argument("Ending quad needs integral geometry");
        return int(value);
    };
    for(const unsigned at:order) {
        const auto& q=list.records[at];
        const bool quad=q.kind==MenuPrimitive::Quad;
        const bool own=quad&&(q.slot==4||q.slot==0x22||q.slot==0x23);
        if(quad&&(q.slot==0x1f||q.slot==0x20))continue;
        if(!own){pending.records.push_back(q);continue;}
        flush();
        const std::vector<uint8_t>& sheet=q.slot==4?picture_:portrait_[q.slot-0x22];
        const int size=q.slot==4?1024:256,base=q.slot==4?0x200:q.slot==0x22?0:0x100;
        if(sheet.empty())continue;
        const int x0=integral(q.x),y0=integral(q.y),x1=integral(q.x+q.w),y1=integral(q.y+q.h);
        const int u0=integral(q.u),v0=integral(q.v),u1=integral(q.u+q.uw),v1=integral(q.v+q.vh);
        if(x0==x1||y0==y1)continue;
        int mod[4];
        for(int c=0;c<4;++c)mod[c]=int((q.colour>>(8*c))&255);
        for(int py=std::max(0,std::min(y0,y1));py<std::min(height,std::max(y0,y1));++py) {
            // Texel under the pixel centre.
            const int tv=v0+floorDiv((2*py+1-2*y0)*(v1-v0),2*(y1-y0));
            for(int px=std::max(0,std::min(x0,x1));px<std::min(width,std::max(x0,x1));++px) {
                const int tu=u0+floorDiv((2*px+1-2*x0)*(u1-u0),2*(x1-x0));
                if(tu<0||tv<0||tu>=size||tv>=size)continue;
                const auto& texel=colours_[size_t(base+sheet[size_t(tv)*size_t(size)+size_t(tu)])];
                int source[4];
                for(int c=0;c<4;++c)source[c]=std::min(255,texel[size_t(c)]*mod[c]/128);
                auto* dst=rgba.data()+4*(size_t(py)*width+size_t(px));
                if(q.additive)for(int c=0;c<3;++c)dst[c]=uint8_t(std::min(255,dst[c]+source[c]));
                else mix(dst,source);
            }
        }
    }
    flush();
}

// ---------------------------------------------------------------------------
void drawEnding(MenuCanvas& canvas,MenuDrawList& list,const EndingData& data,const EndingFrame& frame,bool frameEnd) {
    // While 3ec73c is set the submitters still run (and consume the depth
    // tie-break 3db8f4) but 1149d0 / 114c10 drop the primitive.
    const auto guarded=[&](bool blank,auto&& submit) {
        const size_t before=list.records.size();
        submit();
        if(blank)list.records.resize(before);
    };
    const auto& b=data.background;
    const auto& p=data.portrait;
    if(frame.picture) {
        canvas.setFade((frame.pictureFadeMode&2)!=0,frame.pictureFadeLevel,frame.pictureFadeColour);
        // 1a4c20: a 640x480 window of the 1024x1024 sheet at v = 1 or 482.
        list.colour=0xffffffffu;list.blend=0;
        guarded(frame.pictureBlank,[&]{canvas.sprite(list,4,0,0,b[4],b[3],b[2],b[0],frame.pictureHalf?b[1]:b[0],b[3],b[2]);});
    }
    canvas.setFade((frame.fade.mode&2)!=0,frame.fade.level,frame.fade.colour);
    if(frame.portraits) {
        if(frame.portrait[0]>=0) {       // 1a22a8
            list.blend=1;
            guarded(frame.blank,[&]{canvas.rectangle(list,0,int(p[1]),int(p[3]),int(p[0]),0xc0404040u,p[2]);});
            if(frame.portrait[0]<0x31)guarded(frame.blank,[&]{canvas.sprite(list,0x22,0,p[1],p[2],p[4],p[0],0,0,p[4],p[0]);});
        }
        if(frame.portrait[1]>=0) {       // 1a2380: mirrored
            list.blend=1;
            guarded(frame.blank,[&]{canvas.rectangle(list,0,int(p[6]),int(p[8]),int(p[5]),0xc0404040u,p[7]);});
            if(frame.portrait[1]<0x31)guarded(frame.blank,[&]{canvas.sprite(list,0x23,p[10],p[6],p[7],p[9],p[5],p[9],0,p[11],p[5]);});
        }
    }
    if(frame.balloon) {
        int id=frame.balloon;const bool flip=id>=6;
        if(flip)id-=5;
        const auto& r=data.balloons.at(size_t(id));
        const float w=float(r[5]),h=float(r[6]);
        guarded(frame.blank,[&] {
            const size_t before=list.records.size();
            canvas.sprite(list,r[0],float(r[1]),float(r[2]),p[12],w,h,flip?float(r[3]+r[5]):float(r[3]),float(r[4]),flip?-w:w,h);
            if(list.records.size()==before)return;
            // 108118 (10849c): texel coordinates above size-1 become size-1 (512x512 sheets).
            auto& q=list.records.back();
            const float u1=std::min(q.u+q.uw,511.f),v1=std::min(q.v+q.vh,511.f);
            q.u=std::min(q.u,511.f);q.v=std::min(q.v,511.f);q.uw=u1-q.u;q.vh=v1-q.v;
        });
    }
    if(!frame.blank&&!frame.lines.empty()) {
        // 1130f8 / 1131d8: text depth 114e40(3d3aac) around every glyph.
        const int saved=list.textDepth;
        list.textDepth=int(10000000.0f-list.asciiDepth*100.0f);
        int count=frame.glyphStart;
        for(const auto& line:frame.lines) {
            int x=line.x,y=line.y;
            cells(data.text(line.text),[&](std::string_view cell,bool feed) {
                if(feed){x=line.x;y+=0x18;return;}
                if(!(frame.reveal>=0&&count>=frame.reveal)) {
                    canvas.text24(list,cell,x,y,255,255,255,255);
                    ++count;
                }
                x+=cell.size()==1?12:24;
            });
        }
        list.textDepth=saved;
    }
    if(!frameEnd)return;
    // 113b28 takes its depth before it tests 3ec73c.
    if(frame.flash)canvas.rectangle(list,0,0,int(data.flash[2]),int(data.flash[1]),frame.flashColour|0xff000000u,data.flash[0]);
    else canvas.depth(list,data.flash[0]);
}
}
}
