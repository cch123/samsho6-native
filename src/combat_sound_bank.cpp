#include "combat_sound_bank.hpp"

#include <algorithm>
#include <array>
#include <fstream>
#include <span>
#include <stdexcept>

namespace ss6 {
namespace {

uint32_t little32(const uint8_t* p) {
    return uint32_t(p[0]) | uint32_t(p[1]) << 8 | uint32_t(p[2]) << 16 | uint32_t(p[3]) << 24;
}

void decode(CombatSoundSample& sample) {
    SpuAdpcmState history;
    int loopStart = 0;
    sample.pcm.reserve(sample.raw.size() / 16 * 28);
    for (size_t block = 0; block < sample.raw.size(); block += 16) {
        unsigned flags = sample.raw[block + 1];
        if (flags > 7) throw std::runtime_error("Invalid combat sound ADPCM flags");
        if (flags & 4) loopStart = int(sample.pcm.size());
        auto pcm = decodeSpuAdpcmBlock(std::span<const uint8_t,16>(sample.raw.data()+block,16),history);
        sample.pcm.insert(sample.pcm.end(),pcm.begin(),pcm.end());
        if (flags & 1) {
            if (flags & 2) {
                sample.loopStart = loopStart;
                sample.loopEnd = int(sample.pcm.size());
            }
            // Each shipped sample has an additional flag-7 silent guard. The
            // preceding flag-1 block already stopped playback on the SPU.
            return;
        }
    }
    throw std::runtime_error("Unterminated combat sound sample");
}

void decodeGroup(std::vector<CombatSoundSample>& group,std::span<const uint8_t> header,std::span<const uint8_t> body,
                 unsigned count,bool effect,bool resident) {
    const auto size=body.size();

    group.reserve(count);
    for (unsigned tone = 0; tone < count; ++tone) {
        const uint8_t* entry = header.data() + 16 + tone * 8;
        uint32_t length = little32(entry), offset = little32(entry + 4);
        auto& sample = group.emplace_back();
        sample.sourceOffset = offset;
        sample.pitch = effect ? 0x3b0 : 0x761;
        if (effect) {
        sample.volumeCode = uint16_t(length);
        length >>= 16;
        } else if (resident) {
        sample.volumeCode = 15; // Resident BVOICE1[49] is keyed by 212d40.
        }
        if (!length || length % 16 || offset % 64 || offset > size || length > size - offset)
        throw std::runtime_error("Invalid combat sound sample extent");
        auto encoded = body.subspan(offset, length);
        sample.raw.assign(encoded.begin(), encoded.end());
        decode(sample);
    }
}

const CombatSoundSample* lookup(const std::vector<CombatSoundSample>& group, unsigned tone) {
    return tone < group.size() ? &group[tone] : nullptr;
}

}

std::array<int16_t,28> decodeSpuAdpcmBlock(std::span<const uint8_t,16> block,SpuAdpcmState& history) {
    constexpr std::array<int,5> recentWeight{0,60,115,98,122};
    constexpr std::array<int,5> olderWeight{0,0,-52,-55,-60};
    unsigned filter = block[0] >> 4, shift = block[0] & 15;
    if (filter >= recentWeight.size() || shift > 12)
        throw std::runtime_error("Invalid SPU2 ADPCM prediction parameters");
    std::array<int16_t,28> samples{};
    for (unsigned i=0;i<samples.size();++i) {
        int nibble = (block[2+i/2] >> (4*(i%2))) & 15;
        if (nibble >= 8) nibble -= 16;
        // SPU2 rounds the combined prediction and feeds the saturated sample
        // back into both this block and the next.
        int prediction = (history.recent*recentWeight[filter] + history.older*olderWeight[filter] + 32) >> 6;
        int value = std::clamp(((nibble*4096) >> shift) + prediction,-32768,32767);
        samples[i] = int16_t(value);
        history.older = history.recent;
        history.recent = value;
    }
    return samples;
}

CombatSoundBank::CombatSoundBank(const std::filesystem::path& directory):directory_(directory) {
    std::ifstream file(directory / "combat_sound_bank.bin", std::ios::binary | std::ios::ate);
    if (!file || file.tellg() < 8 || file.tellg() > 4 * 1024 * 1024)
        throw std::runtime_error("Invalid combat sound bank");
    std::vector<uint8_t> bytes(static_cast<size_t>(file.tellg()));
    file.seekg(0);
    if (!file.read(reinterpret_cast<char*>(bytes.data()), std::streamsize(bytes.size())))
        throw std::runtime_error("Truncated combat sound bank");
    const std::array<uint8_t, 8> magic{'S','6','A','D','P','C','M','1'};
    if (!std::equal(magic.begin(), magic.end(), bytes.begin()))
        throw std::runtime_error("Unknown combat sound bank version");

    constexpr std::array<unsigned, 6> strides{0x250, 0x250, 0x110, 0x110, 0x210, 0x210};
    constexpr std::array<unsigned, 6> counts{70, 49, 15, 13, 47, 47};
    std::span<const uint8_t> rest(bytes);
    rest = rest.subspan(magic.size());
    for (size_t g = 0; g < groups_.size(); ++g) {
        if (rest.size() < strides[g]) throw std::runtime_error("Truncated combat sound directory");
        auto header = rest.first(strides[g]);
        rest = rest.subspan(strides[g]);
        unsigned count = little32(header.data() + 4), size = little32(header.data() + 8);
        if (count != counts[g] || size > rest.size())
            throw std::runtime_error("Invalid combat sound group");
        auto body = rest.first(size);
        rest = rest.subspan(size);
        decodeGroup(groups_[g],header,body,count,g<2,g==3);
    }
    if (!rest.empty()) throw std::runtime_error("Trailing combat sound data");
}

const CombatSoundSample* CombatSoundBank::find(unsigned bank, unsigned tone) const {
    // EE 212dd8 loads Haohmaru's group 0 at both players' separate SPU addresses.
    if (bank > 2) return nullptr;
    return lookup(groups_[bank ? 1 : 0], tone);
}
const CombatSoundSample* CombatSoundBank::voice(unsigned tone) const {
    return lookup(groups_[2], tone);
}
const std::vector<CombatSoundSample>& CombatSoundBank::characterGroup(unsigned id,bool voice) {
    if(id==0)return groups_[voice?2:1];
    const auto key=std::make_pair(id,voice);
    if(auto it=extra_.find(key);it!=extra_.end())return it->second;
    const auto stem=std::string(voice?"vs_voice_":"vs_sounds_")+(id<10?"0":"")+std::to_string(id);
    std::ifstream in(directory_/(stem+".bin"),std::ios::binary|std::ios::ate);
    if(!in||in.tellg()<0||in.tellg()>2*1024*1024)throw std::runtime_error("Missing character sound group: "+stem);
    const unsigned stride=voice?0x110:0x250;
    std::vector<uint8_t> raw(static_cast<size_t>(in.tellg()));in.seekg(0);
    if(raw.size()<stride||!in.read(reinterpret_cast<char*>(raw.data()),raw.size()))throw std::runtime_error("Truncated character sound group");
    const unsigned count=little32(raw.data()+4);
    if(count>(stride-16)/8||little32(raw.data()+8)!=raw.size()-stride)throw std::runtime_error("Invalid character sound directory");
    const std::span<const uint8_t> bytes(raw);
    std::vector<CombatSoundSample> decoded;
    decodeGroup(decoded,bytes.first(stride),bytes.subspan(stride),count,!voice,false);
    return extra_.emplace(key,std::move(decoded)).first->second;
}
const CombatSoundSample* CombatSoundBank::fighterEffect(unsigned id,unsigned tone){return lookup(characterGroup(id,false),tone);}
const CombatSoundSample* CombatSoundBank::bankEffect(unsigned id,unsigned tone){return id==50?find(0,tone):fighterEffect(id,tone);}
const CombatSoundSample* CombatSoundBank::fighterVoice(unsigned id,unsigned tone){return lookup(characterGroup(id,true),tone);}
unsigned CombatSoundBank::voiceCount(unsigned id){return unsigned(characterGroup(id,true).size());}
const CombatSoundSample* CombatSoundBank::residentVoice(unsigned tone) const {
    return lookup(groups_[3], tone);
}
const CombatSoundSample* CombatSoundBank::narrator(unsigned tone, unsigned variant) const {
    return variant < 2 ? lookup(groups_[4 + variant], tone) : nullptr;
}

}
