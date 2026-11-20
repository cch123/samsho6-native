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
// The disc has separate L/R files of equal length. Retain the exact EOF
// for the final CD transfer, including streams ending partway through a half.
constexpr std::array<size_t,10> stageBytes{
    1212416,2793472,1474560,1605632,1499136,1417216,1417216,1605632,1556480,1671168
};

CombatSoundSample loadSide(const std::filesystem::path& path,size_t expected) {
    std::ifstream in(path,std::ios::binary|std::ios::ate);
    if(!in||in.tellg()!=std::streamoff(expected))
        throw std::runtime_error("Missing or truncated music stream: "+path.string());
    std::vector<uint8_t> bytes(expected);
    in.seekg(0);
    if(!in.read(reinterpret_cast<char*>(bytes.data()),std::streamsize(expected)))
        throw std::runtime_error("Cannot read music stream: "+path.string());
    CombatSoundSample result;
    result.pitch=pitch;
    const auto playbackBytes=(expected+halfBuffer-1)/halfBuffer*halfBuffer;
    result.pcm.reserve(playbackBytes/16*28+3);
    SpuAdpcmState history;
    for(size_t offset=0;offset<playbackBytes;offset+=16) {
        // The IOP transfers a whole 32 KiB SPU half even after a short
        // final CD read. Its untouched tail still holds the preceding
        // 160-sector cache fill (audible on the character-select loop).
        constexpr size_t cdCacheBytes=160*2048;
        const size_t source=offset<expected?offset:offset-cdCacheBytes;
        auto pcm=decodeSpuAdpcmBlock(std::span<const uint8_t,16>(bytes.data()+source,16),history);
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
void CombatMusic::request(int variant,int tone,bool preload,int volume) {
    const bool stage=tone>=5&&tone<5+int(stageBytes.size());
    // Both title soundtrack selections point at identical stereo payloads
    // under BGM1 and BGM3. Other installed streams use the default variant.
    const bool title=tone==1;
    if((variant!=0&&!(title&&variant==1))||(!stage&&!title&&tone!=2&&tone!=24))
        throw std::invalid_argument("Unsupported versus music track");
    auto cached=std::find_if(tracks_.begin(),tracks_.end(),[tone](const Track& t){return t.tone==tone;});
    if(cached!=tracks_.end()) {
        slot_=unsigned(cached-tracks_.begin());
    } else {
        const size_t size=stage?stageBytes[size_t(tone-5)]:title?819200:tone==2?1294336:163840;
        const auto stem=std::string("bgm")+(tone<10?"0":"")+std::to_string(tone)+"_";
        Track loaded;
        loaded.tone=tone;
        for(unsigned i=0;i<2;++i)
            loaded.sides[i]=loadSide(assets_/(stem+(i?"r.vb":"l.vb")),size);
        // 2c18 schedules the one-shot KOFF on the next half-buffer IRQ.
        // The final uploaded half has not reached playback. This leaves
        // 24 audible halves for the title and four for the victory cue.
        const bool oneShot=title||tone==24;
        loaded.endSample=unsigned(loaded.sides[0].pcm.size()-3-(oneShot?halfBuffer/16*28:0));
        // An EE request precedes KOFF. Until the next service, the mixer can
        // still read both sides of the currently playing track. Replace the
        // other slot even if several requests arrive before that service.
        slot_=playingSlot_^1;
        tracks_[slot_]=std::move(loaded);
    }
    // 1282d0 requests track 2 with the repeat flag set and starts it
    // immediately. The stage stream uses a separate release after preload.
    repeat_=stage||tone==2;
    released_=!preload;
    volume_=std::clamp(volume,0,0x3fff);
    phase_=Phase::StopPrevious;
}
void CombatMusic::release(int volume) {
    released_=true;
    volume_=std::clamp(volume,0,0x3fff);
}
void CombatMusic::stop() {
    // 214150 stops the IOP immediately; the EE can still have a request
    // before its own OPEN/PLAY stages. A ready request no longer has data.
    if(phase_==Phase::Ready||phase_==Phase::Loading)phase_=Phase::Idle;
}
void CombatMusic::reset() {
    phase_=Phase::Idle;released_=false;ticksToReady_=0;
}
CombatMusic::Event CombatMusic::tick() {
    switch(phase_) {
    case Phase::Idle:return Event::None;
    case Phase::StopPrevious:phase_=Phase::WaitFade;return Event::Silence;
    case Phase::WaitFade:phase_=Phase::WaitIdle;break;
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
        if(released_) {playingSlot_=slot_;phase_=Phase::Idle;return Event::KeyOn;}
        break;
    }
    return Event::None;
}
}
