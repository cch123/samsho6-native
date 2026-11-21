#include "combat_music.hpp"
#include <algorithm>
#include <fstream>
#include <stdexcept>
#include <string>
#include <vector>

namespace ss6 {
namespace {
constexpr size_t halfBuffer=0x8000;
constexpr unsigned pitch=0x761;
// 214438 lowers the fading stream volume (3b4c) by this step every visit.
constexpr int fadeStep=0x222;

std::vector<uint8_t> readFile(const std::filesystem::path& path,size_t limit) {
    std::ifstream in(path,std::ios::binary|std::ios::ate);
    if(!in||in.tellg()<0||size_t(in.tellg())>limit)throw std::runtime_error("Missing music asset: "+path.string());
    std::vector<uint8_t> bytes(size_t(in.tellg()));
    in.seekg(0);
    if(!in.read(reinterpret_cast<char*>(bytes.data()),std::streamsize(bytes.size())))
        throw std::runtime_error("Cannot read music asset: "+path.string());
    return bytes;
}
uint32_t little32(const uint8_t* p) {return uint32_t(p[0])|uint32_t(p[1])<<8|uint32_t(p[2])<<16|uint32_t(p[3])<<24;}

// The disc has separate L/R files of equal length. Retain the exact EOF
// for the final CD transfer, including streams ending partway through a half.
CombatSoundSample loadSide(const std::filesystem::path& path,size_t expected,const std::vector<uint8_t>& tail) {
    auto bytes=readFile(path,8u<<20);
    if(bytes.size()!=expected)throw std::runtime_error("Truncated music stream: "+path.string());
    // The IOP transfers a whole 32 KiB SPU half even after a short final
    // CD read. The catalogue holds what its cache still contains there
    // (extract_stage_music.py: the disc after a one-read stream, otherwise
    // the previous 160-sector fill; audible on the character-select loop).
    const auto playbackBytes=(expected+halfBuffer-1)/halfBuffer*halfBuffer;
    if(tail.size()!=playbackBytes-expected)throw std::runtime_error("Invalid music stream tail");
    bytes.insert(bytes.end(),tail.begin(),tail.end());
    CombatSoundSample result;
    result.pitch=pitch;
    result.pcm.reserve(playbackBytes/16*28+3);
    SpuAdpcmState history;
    for(size_t offset=0;offset<playbackBytes;offset+=16) {
        auto pcm=decodeSpuAdpcmBlock(std::span<const uint8_t,16>(bytes.data()+offset,16),history);
        result.pcm.insert(result.pcm.end(),pcm.begin(),pcm.end());
    }
    // The IOP rewrites the on-disc loop flags for its two-half SPU buffer.
    // At EOF its next CD read starts from sector zero of the same file.
    // The shipped tracks start with a zero predictor, so this also preserves
    // the decoded stream across the wrap. Keep three taps for interpolation.
    std::array<int16_t,3> first{result.pcm[0],result.pcm[1],result.pcm[2]};
    result.pcm.insert(result.pcm.end(),first.begin(),first.end());
    return result;
}
}
CombatMusic::CombatMusic(const std::filesystem::path& assets):assets_(assets) {
    // music_streams.bin (extract_stage_music.py): per soundtrack and track
    // the byte length, whether the arranged recording has its own files,
    // and the bytes completing the final SPU half of each channel.
    const auto bytes=readFile(assets/"music_streams.bin",4u<<20);
    const std::string magic="S6BGMv01";
    if(bytes.size()<12||!std::equal(magic.begin(),magic.end(),bytes.begin())||little32(bytes.data()+8)!=catalogue_.size())
        throw std::runtime_error("Invalid music stream catalogue");
    size_t at=12;
    for(auto& e:catalogue_) {
        if(bytes.size()-at<8)throw std::runtime_error("Truncated music stream catalogue");
        e.bytes=little32(bytes.data()+at);e.own=bytes[at+5]!=0;
        const size_t tail=size_t(bytes[at+6])|size_t(bytes[at+7])<<8;
        at+=8;
        if(bytes.size()-at<2*tail||tail>=halfBuffer)throw std::runtime_error("Truncated music stream catalogue");
        for(auto& side:e.tail){side.assign(bytes.begin()+long(at),bytes.begin()+long(at+tail));at+=tail;}
    }
    if(at!=bytes.size())throw std::runtime_error("Trailing music stream catalogue data");
}
bool CombatMusic::exists(int variant,int track) const {
    return (variant==0||variant==1)&&track>=0&&track<tracks;
}
void CombatMusic::request(const Request& r,int volume) {
    // 214210 opens \BGMd\BGMnn_L/R.VB; a non-zero soundtrack byte selects
    // the arranged directories BGM3/BGM4. Tracks beyond 27 have no file.
    if(!exists(r.variant,r.track))throw std::invalid_argument("Unsupported music track");
    const int key=r.variant*tracks+r.track;
    auto cached=std::find_if(tracks_.begin(),tracks_.end(),[key](const Track& t){return t.key==key;});
    if(cached!=tracks_.end()) {
        slot_=unsigned(cached-tracks_.begin());
    } else {
        const auto& e=catalogue_[size_t(key)];
        const auto stem=std::string("bgm")+(r.track<10?"0":"")+std::to_string(r.track)+(e.own?"a":"")+"_";
        Track loaded;
        loaded.key=key;
        for(unsigned i=0;i<2;++i)
            loaded.sides[i]=loadSide(assets_/(stem+(i?"r.vb":"l.vb")),e.bytes,e.tail[i]);
        loaded.samples=unsigned(loaded.sides[0].pcm.size()-3);
        // An EE request precedes KOFF. Until the next service, the mixer can
        // still read both sides of the currently playing track. Replace the
        // other slot even if several requests arrive before that service.
        slot_=playingSlot_^1;
        tracks_[slot_]=std::move(loaded);
    }
    // A zero repeat flag makes the IRX schedule the one-shot KOFF (2c18) on
    // the next half-buffer IRQ after EOF. The final uploaded half has not
    // reached playback, so a one-shot stream is heard one half short. The
    // IRX does not test EOF after its initial two-half upload: a two-half
    // stream (BGM23, one-shot in the sound test) uploads one half past EOF
    // and is heard complete. Its repeating form (which no caller requests:
    // 213ff0 redirects track 23 to the jingle) would play that half once.
    request_=r;
    repeat_=r.repeat;
    constexpr unsigned half=unsigned(halfBuffer/16*28);
    const unsigned samples=tracks_[slot_].samples;
    endSample_=samples-(repeat_||samples<=2*half?0:half);
    fadeStop_=r.fadeStop;
    released_=!r.preload;
    volume_=std::clamp(volume,0,0x3fff);
    phase_=Phase::StopPrevious;
}
void CombatMusic::release(int volume) {
    released_=true;
    volume_=std::clamp(volume,0,0x3fff);
}
void CombatMusic::stop(bool streaming) {
    // 214150 stops the IOP immediately; the EE can still have a request
    // before its own OPEN/PLAY stages. A ready request no longer has data.
    if(phase_==Phase::Ready||phase_==Phase::Loading)phase_=Phase::Idle;
    // After a 214060 request the stop asks the IOP for the stream volume
    // (213db0, which also ends the stream). A non-zero answer starts the
    // fade 3b50: the next visit writes the first lowered volume, the IOP
    // keys off on the service after it, and the request machine waits in
    // its state 1 until the fade has run out.
    if(fadeStop_&&streaming&&volume_>0) {fading_=true;fadeLevel_=volume_;keyOff_=1;}
}
int CombatMusic::requestState() const {
    switch(phase_) {
    case Phase::StopPrevious:return 0;
    case Phase::WaitFade:return 1;
    case Phase::WaitIdle:return 2;
    case Phase::Open:return 3;
    case Phase::WaitOpen:return 4;
    case Phase::RequestDMA:return 5;
    default:return -1;
    }
}
void CombatMusic::reset() {
    phase_=Phase::Idle;released_=false;ticksToReady_=0;fading_=false;fadeLevel_=keyOff_=0;
}
CombatMusic::Event CombatMusic::tick(bool streaming) {
    Event event=Event::None;
    switch(phase_) {
    case Phase::Idle:break;
    case Phase::StopPrevious:
        phase_=Phase::WaitFade;
        stop(streaming);
        if(!fading_)event=Event::Silence;
        break;
    case Phase::WaitFade:if(!fading_)phase_=Phase::WaitIdle;break;
    case Phase::WaitIdle:phase_=Phase::Open;break;
    case Phase::Open:phase_=Phase::WaitOpen;break;
    case Phase::WaitOpen:phase_=Phase::RequestDMA;break;
    case Phase::RequestDMA:
        // 3650 performs two sequential initial disc reads. Each executes
        // DelayThread(100000) even with data already ready. Use the ready-disc
        // path on the 60 Hz host; physical seek latency is device-dependent.
        ticksToReady_=12;
        phase_=Phase::Loading;
        break;
    case Phase::Loading:
        if(--ticksToReady_>0)break;
        phase_=Phase::Ready;
        [[fallthrough]];
    case Phase::Ready:
        if(released_) {playingSlot_=slot_;phase_=Phase::Idle;event=Event::KeyOn;}
        break;
    }
    // 214438 runs after the request machine on the same 2142c0 visit.
    if(fading_) {
        fadeLevel_-=fadeStep;
        if(fadeLevel_<0) {fading_=false;fadeLevel_=0;}
    }
    if(keyOff_==1) {keyOff_=2;if(event==Event::None)event=Event::Fade;}
    else if(keyOff_==2) {keyOff_=0;if(event==Event::None)event=Event::Silence;}
    return event;
}
}
