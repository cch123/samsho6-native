#include "combat_audio.hpp"
#include <algorithm>
#include <cmath>
#include <numbers>
#include <stdexcept>

namespace ss6 {
namespace {
using InterpolationTable=std::array<std::array<int16_t,4>,256>;

// Four phase-dependent SPU coefficients, reconstructed from the published
// interpolation response (Near/nocash/Ryphecha, also documented in PCSX2's
// SPU2/interpolate_table.h). Build once; the audio loop stays integer-only.
const InterpolationTable& weights() {
    static const auto table=[] {
        constexpr double pi=std::numbers::pi;
        std::array<double,512> kernel{};
        double total=0;
        for(unsigned i=0;i<kernel.size();++i) {
            const double k=i+0.5;
            const double a=2*pi*k/1023;
            const double window=0.42+0.50*std::cos(a)+0.08*std::cos(2*a);
            total+=(kernel[i]=std::sin(pi*k/500)*window/k);
        }
        InterpolationTable result{};
        for(unsigned phase=0;phase<result.size();++phase) {
            const std::array<unsigned,4> offsets{256+phase,phase,255-phase,511-phase};
            std::array<double,4> w{};
            double sum=0;
            for(unsigned j=0;j<4;++j)sum+=(w[j]=kernel[offsets[j]]*(32640.0*128/total));
            for(unsigned j=0;j<4;++j)result[phase][j]=int16_t(std::lround(w[j]+(32640.0-sum)/4));
        }
        return result;
    }();
    return table;
}
int applyVolume(int sample,int gain) {
    return (sample*gain)>>15;
}
}

CombatAudio::CombatAudio(const std::filesystem::path& assets):bank_(assets),music_(assets) {
    weights();
}
void CombatAudio::clearVoices() {
    queue_={};read_=write_=transfer_=0;
}
void CombatAudio::reset() {
    channels_={};players_={};common_=50;nextEffect_=14;clearVoices();music_.reset();
}
int CombatAudio::playEffect(const CombatSoundSample* sample,int volumeCode) {
    // ADPCMST.IRX e40: no priority comparison or free-slot scan. Even a
    // silent entry consumes a slot, and wrapping replaces its old sample.
    const unsigned id=nextEffect_;
    nextEffect_=id==21?14:id+1;
    auto& channel=channels_[id];
    channel={};
    channel.sample=sample;
    if(sample)channel.volume=int(std::clamp((int64_t(volumeCode)+1)*1024-1,int64_t(0),int64_t(0x3fff)));
    return int(id);
}
int CombatAudio::play(int bank,int tone) {
    if(bank<0||bank>2||tone<0)return 0;
    const auto* sample=bank_.bankEffect(bank?players_[bank-1]:common_,unsigned(tone));
    return playEffect(sample,sample?sample->volumeCode:0);
}
// 212d80 applies the music setting to the same resident sample used by
// 212d40. The caller omits the request entirely when that setting is zero.
int CombatAudio::playResidentJingle(int tone,int volumeCode) {
    if(tone<0)return 0;
    return playEffect(bank_.residentVoice(unsigned(tone)),volumeCode);
}
int CombatAudio::playVoice(int character,int tone,unsigned voiceVariant) {
    if(tone<0||voiceVariant>1)return 0;
    if(character==50)return playResidentJingle(tone,15);
    const CombatSoundSample* sample=nullptr;
    unsigned channel=2;
    if(character==49) {
        // 21358c remaps the spoken name to the selected fighter's
        // last two BVOICE1 entries. Option 43d055 also selects which
        // complete NAL bank supplies the other lines (including the title).
        if((tone>=2&&tone<44)||(tone>=89&&tone<94)||tone==100) {
            character=tone==100?42:tone>=89?tone-45:tone-2;
            if(unsigned(character)!=players_[0]&&unsigned(character)!=players_[1])return 0;
            tone=int(bank_.voiceCount(unsigned(character)))-2+int(voiceVariant);
        } else {
            sample=bank_.narrator(unsigned(tone<44?tone:tone-42),voiceVariant);
            channel=4;
        }
    }
    if(channel!=4) {
        if(unsigned(character)!=players_[0]&&unsigned(character)!=players_[1])return 0;
        channel=unsigned(character)==players_[0]?2:3;
        // 213448..213480 plays the first eight lines of character 29
        // from the resident bank before indexing its streamed lines.
        if(character==29) {
            if(tone<8) {
                playResidentJingle(tone+4,15);
                // The wrapper returns success, while the nested resident
                // request alone returns the rotating physical SE channel.
                return 1;
            }
            tone-=8;
        }
        sample=bank_.fighterVoice(unsigned(character),unsigned(tone));
    }
    if(!sample)return 0;
    // 213378/213040 overwrite the next of four slots, even if it is still
    // pending. Players using the same character share voice channel 2.
    queue_[write_]={sample,channel,true};
    write_=(write_+1)%queue_.size();
    return -1;
}
void CombatAudio::requestMusic(MusicEntry entry,int variant,int track,int flag,int volume) {
    // 213ff0 plays track 23 as the resident jingle 212d80(12): it scales the
    // music volume 5a9e78 to a code (skipped when zero) and leaves both the
    // request block and any running stream untouched.
    if(entry==MusicEntry::Play&&track==23) {
        if(volume)playResidentJingle(12,volume>>9);
        return;
    }
    if(!music_.exists(variant,track))return; // 214210 would open a file the disc lacks
    music_.request({variant,track,flag!=0,entry==MusicEntry::Preload,entry==MusicEntry::Gallery},volume);
}
// The battle and menu callers of the original pass these repeat flags:
// 13abb0 2140b8(stage + 5, 1); 1282d0 213ff0(2, 1); title 1 and 1e7ce8(24) zero.
void CombatAudio::preloadMusic(int variant,int track) {requestMusic(MusicEntry::Preload,variant,track,1,0);}
void CombatAudio::startMusic(int volume) {music_.release(volume);}
void CombatAudio::playMusic(int variant,int track,int volume) {requestMusic(MusicEntry::Play,variant,track,track==2,volume);}
void CombatAudio::stopMusic() {
    music_.stop(bool(channels_[0].sample));
    if(!music_.fading()) {channels_[0]={};channels_[1]={};}
}
void CombatAudio::loadBank(int group,int bank) {
    if(group<0||group>2||bank<0)return;
    // 1e79c8 first stops the effect voices (1e7a78 -> 213be8(1)); 212dd8's
    // 2135e0 then stops a running stream until the IOP reports idle.
    stopGroup(1);
    if(channels_[0].sample)stopMusic();
    if(group)players_[size_t(group-1)]=unsigned(bank);
    else common_=unsigned(bank);
}
void CombatAudio::tick() {
    const auto change=music_.tick(bool(channels_[0].sample));
    if(change==CombatMusic::Event::Fade) {
        // 214438's first lowered volume reaches both stream voices once.
        for(unsigned i=0;i<2;++i)if(channels_[i].sample)channels_[i].volume=music_.fadeLevel();
    } else if(change!=CombatMusic::Event::None) {
        for(unsigned i=0;i<2;++i) {
            auto& voice=channels_[i];
            voice={};
            if(change==CombatMusic::Event::KeyOn) {
                voice.sample=&music_.track().sides[i];
                voice.streamEnd=music_.endSample();
                voice.repeat=music_.repeat();
                voice.volume=music_.volume();
            }
        }
    }
    // 213660 performs at most one EE queue stage per service: IOP ready,
    // start SIF transfer, then publish its completion. Assets are resident.
    auto& request=queue_[read_];
    if(!request.pending)return;
    if(++transfer_!=3)return;
    auto& channel=channels_[request.channel];
    channel={};channel.sample=request.sample;
    // 213e78 sets the global streamed-voice volume code to 16. IRX 1838
    // scales this group in steps of 512, distinct from the short SE table.
    channel.volume=(16+1)*512-1;
    request={};transfer_=0;read_=(read_+1)%queue_.size();
}
void CombatAudio::stop(int channel) {
    // ADPCMST 84c masks out BGM voices 0 and 1; KOFF enters release, it
    // does not remove a later queued request addressing this physical voice.
    if(channel>=2&&unsigned(channel)<channels_.size()&&channels_[channel].sample)
        channels_[channel].envelope=Envelope::Release;
}
void CombatAudio::stopGroup(int group) {
    constexpr std::array<uint32_t,4> masks{3,0x3fc000,0x3c,0x3fffff};
    if(group<0||unsigned(group)>=masks.size())return;
    for(unsigned i=0;i<channels_.size();++i)
        if((masks[group]&(1u<<i))&&channels_[i].sample)channels_[i].envelope=Envelope::Release;
}

int CombatAudio::Channel::next() {
    if(!sample)return 0;
    if(streamEnd&&position>=(uint64_t(streamEnd)<<12)) {
        if(!repeat) {sample=nullptr;return 0;}
        position-=uint64_t(streamEnd)<<12;
    }
    const unsigned index=unsigned(position>>12);
    // The core fetches four samples when the FIFO is at most twelve ahead.
    // Reaching a non-repeating END during that fetch mutes the voice, even
    // though its decoded FIFO still contains a few trailing samples.
    if(!streamEnd&&decoded<=index+12) {
        decoded+=4;
        if(decoded>=sample->pcm.size()) {sample=nullptr;return 0;}
    }
    switch(envelope) {
    case Envelope::Attack:
        level=std::min(32767,level+14336);
        if(level==32767)envelope=Envelope::Decay;
        break;
    case Envelope::Decay:
        level+=(-16384*level)>>15;
        envelope=Envelope::Sustain;
        break;
    case Envelope::Sustain:
        if(++sustainTicks==32768) {level=std::min(32767,level+4);sustainTicks=0;}
        break;
    case Envelope::Release:
        level=std::max(0,level-16384);
        if(!level) {sample=nullptr;return 0;}
        break;
    }
    const auto& coefficient=weights()[(position>>4)&255];
    int value=0;
    for(unsigned tap=0;tap<4;++tap)value+=applyVolume(sample->pcm[index+tap],coefficient[tap]);
    position+=sample->pitch;
    return applyVolume(applyVolume(value,level),volume*2);
}
void CombatAudio::render(std::span<int16_t> output) {
    if(output.size()%2)throw std::invalid_argument("Stereo output needs complete sample pairs");
    for(size_t i=0;i<output.size();i+=2) {
        int mix=0;
        for(size_t j=2;j<channels_.size();++j)mix+=channels_[j].next();
        // EE 213948 sets both master registers on core 1 to 0x3fff. The
        // hardware clamps the summed voices before the final gain.
        for(unsigned side=0;side<2;++side)
            output[i+side]=int16_t(applyVolume(std::clamp(mix+channels_[side].next(),-32768,32767),0x7ffe));
    }
}
}
